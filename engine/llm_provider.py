"""Pluggable providers for JSON-formatted LLM completions."""

from __future__ import annotations

from engine.i18n import t

import json
import os
import sqlite3
from typing import Protocol

import anthropic
import openai

from . import db


class LLMOutputError(Exception):
    """Raised when a provider cannot produce a syntactically valid JSON object."""


class LLMProvider(Protocol):
    def complete_json(self, system: str, user: str) -> dict:
        """Send a system+user prompt, return a parsed JSON dict.

        Implementations must retry at most once internally if the raw response
        isn't valid JSON, by re-prompting with an explicit "上次输出不是合法 JSON，
        请只输出一个 JSON 对象，不要有任何其他文字" instruction appended. If the
        second attempt also fails to parse, raise LLMOutputError.
        """

        ...


def _parse_json_object(raw_text: str) -> dict:
    """Parse a JSON object, tolerating explanatory text around the object."""

    stripped = raw_text.strip()
    candidates = [stripped]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("response does not contain a JSON object")


class AnthropicProvider:
    """Anthropic implementation of the common JSON completion interface."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    @staticmethod
    def _response_text(response) -> str:
        return "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        )

    def _complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return self._response_text(response)

    def complete_json(self, system: str, user: str) -> dict:
        raw_text = self._complete(system, user)
        try:
            return _parse_json_object(raw_text)
        except ValueError:
            retry_user = (
                f"{user}\n\n上次输出：\n{raw_text}\n\n"
                "上次输出不是合法 JSON，请只输出一个 JSON 对象，不要有任何其他文字"
            )
            retry_text = self._complete(system, retry_user)
            try:
                return _parse_json_object(retry_text)
            except ValueError as exc:
                raise LLMOutputError(retry_text) from exc


class OpenAICompatibleProvider:
    """Provider for OpenAI-compatible chat completion APIs."""

    def __init__(self, api_key: str, model: str, base_url: str):
        self.model = model
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

    def _complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content

    def complete_json(self, system: str, user: str) -> dict:
        raw_text = self._complete(system, user)
        try:
            return _parse_json_object(raw_text)
        except ValueError:
            retry_user = (
                f"{user}\n\n上次输出：\n{raw_text}\n\n"
                "上次输出不是合法 JSON，请只输出一个 JSON 对象，不要有任何其他文字"
            )
            retry_text = self._complete(system, retry_user)
            try:
                return _parse_json_object(retry_text)
            except ValueError as exc:
                raise LLMOutputError(retry_text) from exc


def _openai_compatible_factory(base_url: str):
    def factory(api_key: str, model: str) -> "OpenAICompatibleProvider":
        return OpenAICompatibleProvider(
            api_key=api_key, model=model, base_url=base_url
        )

    return factory


def _custom_provider_placeholder_factory(**_kwargs):
    """"自定义 API"在注册表里的占位工厂——不会被正常调用到（见 PROVIDER_REGISTRY 里
    "custom" 那条的注释），真正的构造逻辑在 get_provider() 里，因为 base_url 要在
    运行时从数据库设置里读，注册表本身在模块加载时就建好了，读不到运行时的设置。
    """

    raise RuntimeError(
        t('custom 供应商必须通过 get_provider() 构造（需要额外传 base_url），不能直接从注册表实例化')
    )


PROVIDER_REGISTRY: dict[str, type] = {
    "anthropic": AnthropicProvider,
    "openai": _openai_compatible_factory("https://api.openai.com/v1"),
    "deepseek": _openai_compatible_factory("https://api.deepseek.com/v1"),
    "kimi": _openai_compatible_factory("https://api.moonshot.cn/v1"),
    # 真实反馈排查（2026-09 查证阿里云官方文档）：DashScope 的 API key 是绑定"控制台
    # 区域"的——大陆控制台开的 key 只认大陆这个域名，国际/新加坡控制台开的 key 只认
    # 国际域名，两边配错了会直接 401，报错信息看着完全不像是"账号区域配错了"，很容易
    # 被误以为是"这个工具不支持阿里云"。拆成两个供应商条目，让人一眼能选对，而不是
    # 猜一个域名不对就放弃。
    "qwen": _openai_compatible_factory(
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
    "qwen_intl": _openai_compatible_factory(
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    ),
    "grok": _openai_compatible_factory("https://api.x.ai/v1"),
    # OpenRouter：一个 key 走一个聚合网关，能选一大堆模型（包括阿里自己的 Qwen 系列）——
    # 跟直接开 DashScope 账号的价格是一样的（官方报价 2026-09 查证：qwen/qwen-turbo
    # 同样是输入 $0.05／输出 $0.20 每百万 token，OpenRouter 没有加价），对已经有 OpenRouter
    # 账号的人更省事，不用另外为了 Qwen 单独开一个阿里云账号。
    "openrouter": _openai_compatible_factory("https://openrouter.ai/api/v1"),
    # MiniMax：国内厂商，OpenAI 兼容模式的 base_url——用的是国际/全球这一个域名
    # （2026-09 查证官方文档 platform.minimax.io/docs/api-reference/text-chat-openai）。
    # MiniMax 大陆版的 OpenAI 兼容域名当时查到的信息前后矛盾（不同资料写的不一样），
    # 没能从官方文档里确认下来，所以先只接国际版这一个；用大陆账号 key 的话大概率会
    # 认证失败，这种情况改用下面的"自定义 API"，自己填大陆那个 base_url。
    "minimax": _openai_compatible_factory("https://api.minimax.io/v1"),
    # "自定义 API"——同事们各有各习惯用的供应商，不可能每一家都在这个列表里单独接一遍；
    # 只要对方提供的是 OpenAI 兼容的 chat completions 接口（绝大部分国内外供应商现在都有
    # 这个兼容模式，哪怕主推的是自己的原生接口），填一个 base_url + api key + 模型名就能用，
    # 不需要改代码。这里注册的工厂函数只是个占位——base_url 是运行时才从设置里读出来的
    # （每个用户填的不一样），不能像上面几家一样在注册表里写死，真正的构造逻辑在
    # get_provider() 里对 "custom" 单独处理，这个占位工厂正常不会被调用到；如果真的被
    # 调用到（说明 get_provider 的特判逻辑被绕过去了），报错比返回一个查不到 base_url
    # 的实例更容易在测试/使用时第一时间发现问题。
    "custom": _custom_provider_placeholder_factory,
}

PROVIDER_API_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    # 大陆和国际是两个不同控制台开出来的、互不通用的 key，各自存一份、各自读一个
    # 环境变量名，不会因为共用同一个变量名而把两边的 key 搞混。
    "qwen_intl": "DASHSCOPE_INTL_API_KEY",
    "grok": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "custom": "CUSTOM_API_KEY",
}

# 真实反馈排查（2026-09 查证阿里云、MiniMax 官方文档）：qwen-turbo 官方文档已经标注
# "不再更新"，推荐迁移到 qwen-flash；qwen3-max 是当前这一代旗舰（qwen-max 是上一代）。
# MiniMax 的模型系列现在是 M2 往后按小版本号迭代（M2 → M2.5 → M2.7 → M3），M3 是当前
# 旗舰、支持百万级上下文和图片/视频输入。
PROVIDER_DEFAULT_MODEL: dict[str, str] = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-5",
    "deepseek": "deepseek-chat",
    "kimi": "moonshot-v1-8k",
    "qwen": "qwen-plus",
    "qwen_intl": "qwen-plus",
    "grok": "grok-4",
    # OpenRouter 上模型名要带厂商前缀；qwen-turbo 官方已经标注"不再更新，建议迁移到
    # qwen-flash"，换成 qwen3.8-flash（当前最便宜的档位，见 PROVIDER_MODEL_PRESETS）。
    "openrouter": "qwen/qwen3.8-flash",
    "minimax": "MiniMax-M2",
    # "custom" 没有默认模型——base_url 都是用户自己填的，猜不出对方那边有什么模型。
    "custom": "",
}

# 下拉框预设——只覆盖研究/验证过命名规律的几家（Anthropic、DeepSeek、Qwen、MiniMax、
# OpenRouter），价格数字是 2026-09 查证的官方报价，会变但短期内够用来大致排序。没有
# 覆盖到的供应商（OpenAI/Kimi/Grok/custom）直接退回手动填模型名——这些家目前没有
# 核实过完整的分级命名规律，与其编几个自己也不确定对不对的型号名放进下拉框，不如
# 让用户照供应商自己的文档手填，至少不会给出一个看着像官方推荐、实则是编造的选项。
#
# 真实反馈"匹配这个模型太少了"——Qwen/OpenRouter 这两份原来只挑了 3～4 个代表性
# 档位，这次直接查了阿里云官方定价接口和 OpenRouter 官方模型列表接口（不是查文档
# 页面，是两边各自的实时数据源），按"淘汰的不用加"的要求过滤掉——阿里云这边
# qwen-turbo 官方文档写的是"不再更新、建议迁移到 qwen-flash"，不放进来；其余测试用的
# 开源权重系列（qwen3-8b/14b/30b/235b 这些，需要自己管理参数量级选型，不是这个场景
# 会用到的东西）、代码/数学专用模型（跟这个工具的分类/翻译场景无关）也没有列进来，
# 保持这是一份"通用聊天/分类/翻译能直接用"的列表，不是阿里云全部模型目录。
PROVIDER_MODEL_PRESETS: dict[str, list[tuple[str, str]]] = {
    "anthropic": [
        ("claude-haiku-4-5-20251001", "Claude Haiku 4.5 —— 最快最便宜"),
        ("claude-sonnet-5", "Claude Sonnet 5 —— 质量成本均衡（推荐）"),
        ("claude-opus-5", "Claude Opus 5 —— 最强，也最贵"),
    ],
    "deepseek": [
        ("deepseek-chat", "DeepSeek Chat —— 常规对话/分类任务（推荐）"),
        ("deepseek-reasoner", "DeepSeek Reasoner —— 带推理链，更慢更贵"),
    ],
    "qwen": [
        ("qwen-flash", "Qwen Flash —— ¥0.15/¥1.5 每百万 token，最便宜，简单任务/大批量首选"),
        ("qwen-plus", "Qwen Plus —— ¥0.8/¥2 每百万 token，性价比均衡（推荐）"),
        ("qwen-long", "Qwen Long —— ¥0.5/¥2，超长文本/长上下文任务专用"),
        ("qwen-mt-turbo", "Qwen MT Turbo —— 专用翻译模型，比通用聊天模型翻译更准（翻译场景推荐）"),
        ("qwen3.7-plus", "Qwen3.7-Plus —— 新一代 Plus，质量比 qwen-plus 更高"),
        ("qwen3-max", "Qwen3-Max —— 上一代旗舰"),
        ("qwen3.8-max", "Qwen3.8-Max —— 当前旗舰"),
    ],
    "minimax": [
        ("MiniMax-M2", "MiniMax-M2 —— 性价比最高（推荐）"),
        ("MiniMax-M2.5", "MiniMax-M2.5 —— 编程/工具调用更强"),
        ("MiniMax-M3", "MiniMax-M3 —— 当前旗舰，百万级上下文，支持图片/视频输入"),
    ],
}
# 国际/新加坡账号是同一套型号目录，只是按美元计价（比大陆贵六到七成，具体数字
# 这次没有逐个查证），下拉框里不重复标一遍不确定的价格，价格以 DashScope
# International 控制台实际显示为准——型号名本身跟大陆完全一样。
PROVIDER_MODEL_PRESETS["qwen_intl"] = [
    ("qwen-flash", "Qwen Flash —— 最便宜，简单任务/大批量首选"),
    ("qwen-plus", "Qwen Plus —— 性价比均衡（推荐）"),
    ("qwen-long", "Qwen Long —— 超长文本/长上下文任务专用"),
    ("qwen-mt-turbo", "Qwen MT Turbo —— 专用翻译模型，比通用聊天模型翻译更准（翻译场景推荐）"),
    ("qwen3.7-plus", "Qwen3.7-Plus —— 新一代 Plus，质量比 qwen-plus 更高"),
    ("qwen3-max", "Qwen3-Max —— 上一代旗舰"),
    ("qwen3.8-max", "Qwen3.8-Max —— 当前旗舰"),
]


# 翻译这个用途文本量通常远大于分类/洞察（每道题的每个选项、每条开放题原文都要过一遍），
# 全用 Anthropic 旗舰模型价格差距很大。DeepSeek 中文互联网语料训练、中译英/英译中的
# 语感公认扎实，量大的翻译场景命中缓存还能进一步打折；Qwen 系列报价通常更低（尤其是
# 专门的翻译模型 qwen-mt-*，见 PROVIDER_MODEL_PRESETS["qwen"]），但选 DeepSeek 做
# 默认推荐是因为它是主力聊天模型，长文本翻译稳定性验证得比专用翻译模型更多，Qwen
# 系列作为"还要更省"的备选（这两家都已经在 PROVIDER_REGISTRY 里，不需要新增供应商
# 接入代码）。具体单价随时间会变，仅供首页设置页预选默认值用，不影响用户自己改。
TRANSLATION_RECOMMENDED_PROVIDER = "deepseek"

# OpenRouter 一个 key 能选任意厂商的模型，模型名必须带厂商前缀（比如"qwen/qwen-turbo"）——
# 手输很容易漏斜杠、拼错厂商名。这里给一份常用模型的预设，按价格从便宜到贵排列。
# 真实反馈"匹配的模型太少了"——这份原来只有 5 个代表性档位，这次直接查了 OpenRouter
# 官方模型列表接口（不是文档页面，是接口本身返回的实时数据，446 个模型里挑出来的），
# 覆盖到 OpenAI/Anthropic/Google/Meta/Mistral/DeepSeek/Qwen/xAI 这几个主要厂商各自的
# 便宜档和旗舰档；价格是 2026-09 查证的官方报价（OpenRouter 上是原价透传，没有加价），
# 会随时间变化，仅供大致排序参考。UI 上选了预设之外的模型还可以自己填，不锁死——
# OpenRouter 本身有几千个模型，预设只是常用捷径，不是全部选项。原来这份只在"翻译
# 专用"那个下拉框用（变量名带 TRANSLATION），现在通用模型选择器也用同一套预设了，
# 并进了 PROVIDER_MODEL_PRESETS，不再单独留一个变量名。
PROVIDER_MODEL_PRESETS["openrouter"] = [
    ("deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash —— $0.15／$0.60，便宜好用"),
    ("qwen/qwen3.8-flash", "Qwen3.8 Flash —— $0.15／$0.47，最便宜"),
    ("google/gemini-3.1-flash-lite", "Gemini 3.1 Flash Lite —— $0.25／$1.50"),
    ("mistralai/mistral-small-2603", "Mistral Small —— $0.15／$0.60"),
    ("meta-llama/llama-4-maverick", "Llama 4 Maverick —— $0.20／$0.80，开源模型"),
    ("openai/gpt-5.6-luna", "GPT-5.6 Luna —— $0.20／$1.20，OpenAI 便宜/快速档"),
    ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5 —— $1／$5，最快最便宜的 Claude"),
    ("deepseek/deepseek-v4-pro-0813", "DeepSeek V4 Pro —— $0.66／$1.98，当前旗舰（推荐）"),
    ("google/gemini-3.8-flash", "Gemini 3.8 Flash —— $0.75／$3.75，当前 Flash 旗舰"),
    ("qwen/qwen3.8-max-0902", "Qwen3.8 Max —— $2／$6，当前旗舰"),
    ("anthropic/claude-sonnet-5", "Claude Sonnet 5 —— $2／$10，质量成本均衡"),
    ("mistralai/mistral-medium-3-5", "Mistral Medium 3.5 —— $1.50／$7.50，当前旗舰"),
    ("openai/gpt-5.6-sol", "GPT-5.6 Sol —— $2／$10，OpenAI 当前旗舰"),
    ("x-ai/grok-4.6", "Grok 4.6 —— $2／$6，当前旗舰"),
    ("google/gemini-3.1-pro-preview", "Gemini 3.1 Pro —— $2／$12，仍是 preview 阶段"),
    ("anthropic/claude-opus-5", "Claude Opus 5 —— $5／$25，最强最贵"),
]


def get_provider(conn: sqlite3.Connection, purpose: str = "general") -> LLMProvider:
    """Construct the configured LLM provider from database settings and env.

    purpose："general"（分类、AI 洞察等）跟 llm_provider/llm_model 这两个通用设置走；
    "translation"（题目/选项/开放题翻译）优先看有没有单独配置的 llm_provider::translation /
    llm_model::translation——没配置就退回复用通用设置，不强制每个人都多填一次。这样默认
    行为不变，只有想省钱、专门给翻译配一个便宜供应商的人需要多填这一块。
    """

    if purpose == "general":
        name = db.get_setting(conn, "llm_provider", default="anthropic")
        model_key = "llm_model"
    else:
        name = db.get_setting(conn, f"llm_provider::{purpose}", default=None)
        if name is None:
            name = db.get_setting(conn, "llm_provider", default="anthropic")
            model_key = "llm_model"
        else:
            model_key = f"llm_model::{purpose}"

    if name not in PROVIDER_REGISTRY or name not in PROVIDER_API_KEY_ENV:
        raise ValueError(t('未知的 LLM 供应商: {name}', name=name))

    model = db.get_setting(conn, model_key, default=PROVIDER_DEFAULT_MODEL.get(name, ""))

    env_name = PROVIDER_API_KEY_ENV[name]
    api_key = db.get_setting(conn, f"api_key::{name}", default=None) or os.environ.get(
        env_name
    )
    if not api_key:
        raise RuntimeError(
            t('缺少 {name} 的 API key：请在设置里填写，或设置环境变量 {env_name}（缺少环境变量 {env_name}）', name=name, env_name=env_name)
        )

    if name == "custom":
        # "custom"（自定义 API）的 base_url 是每个用户自己填的，PROVIDER_REGISTRY 里
        # 那个工厂只是个占位（模块加载时就建好了，读不到运行时的设置），这里单独构造。
        # 不区分 purpose（通用/翻译共用同一个 base_url 设置）——理由跟 api_key 共用
        # 存储位置一样：选了"自定义"多半是同一个账号/同一个网关，只是模型名可能不同，
        # 不需要每个用途都填一遍 base_url。
        base_url = db.get_setting(conn, "custom_base_url", default=None) or os.environ.get(
            "CUSTOM_BASE_URL"
        )
        if not base_url:
            raise RuntimeError(
                t('选用了「自定义 API」但没有填 base_url：请在设置里填写，或设置环境变量 CUSTOM_BASE_URL')
            )
        if not model:
            raise RuntimeError(t('选用了「自定义 API」但没有填模型名：请在设置里填写'))
        return OpenAICompatibleProvider(api_key=api_key, model=model, base_url=base_url)

    return PROVIDER_REGISTRY[name](api_key=api_key, model=model)
