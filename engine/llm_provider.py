"""Pluggable providers for JSON-formatted LLM completions."""

from __future__ import annotations

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


PROVIDER_REGISTRY: dict[str, type] = {
    "anthropic": AnthropicProvider,
    "openai": _openai_compatible_factory("https://api.openai.com/v1"),
    "deepseek": _openai_compatible_factory("https://api.deepseek.com/v1"),
    "kimi": _openai_compatible_factory("https://api.moonshot.cn/v1"),
    "qwen": _openai_compatible_factory(
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
    "grok": _openai_compatible_factory("https://api.x.ai/v1"),
    # OpenRouter：一个 key 走一个聚合网关，能选一大堆模型（包括阿里自己的 Qwen 系列）——
    # 跟直接开 DashScope 账号的价格是一样的（官方报价 2026-09 查证：qwen/qwen-turbo
    # 同样是输入 $0.05／输出 $0.20 每百万 token，OpenRouter 没有加价），对已经有 OpenRouter
    # 账号的人更省事，不用另外为了 Qwen 单独开一个阿里云账号。
    "openrouter": _openai_compatible_factory("https://openrouter.ai/api/v1"),
}

PROVIDER_API_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "kimi": "MOONSHOT_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "grok": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

PROVIDER_DEFAULT_MODEL: dict[str, str] = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-5",
    "deepseek": "deepseek-chat",
    "kimi": "moonshot-v1-8k",
    "qwen": "qwen-plus",
    "grok": "grok-4",
    # OpenRouter 上模型名要带厂商前缀；qwen-turbo 是最便宜的一档，跟这版翻译专用推荐的
    # 定位一致（见 TRANSLATION_RECOMMENDED_PROVIDER 那段注释）。
    "openrouter": "qwen/qwen-turbo",
}


# 翻译这个用途文本量通常远大于分类/洞察（每道题的每个选项、每条开放题原文都要过一遍），
# 全用 Anthropic 旗舰模型价格差距很大。DeepSeek 是中文互联网语料训练、中译英/英译中的
# 语感公认扎实，官方报价（2026-09 查证）off-peak 输入 $0.15／输出 $0.6 每百万 token，
# 命中缓存的输入只要 $0.003／百万——量大的翻译场景基本能吃满缓存折扣；Qwen-Turbo 报价
# 更低（$0.05／$0.20 每百万 token），但"turbo"档位是通义千问最轻量的一档，短选项名翻译
# 够用，长一点的开放题原文翻译稳定性没有 DeepSeek 主力聊天模型验证得多，所以选 DeepSeek
# 做默认推荐，Qwen-Turbo 作为"还要更省"的备选（这两家都已经在 PROVIDER_REGISTRY 里，
# 不需要新增供应商接入代码）。仅供首页设置页预选默认值用，不影响用户自己改。
TRANSLATION_RECOMMENDED_PROVIDER = "deepseek"

# OpenRouter 一个 key 能选任意厂商的模型，模型名必须带厂商前缀（比如"qwen/qwen-turbo"）——
# 手输很容易漏斜杠、拼错厂商名。这里给一份常用中英翻译场景的预设，按价格从便宜到贵排列
# （官方报价 2026-09 查证，OpenRouter 上是原价透传，没有加价）；UI 上选了预设之外的模型
# 还可以自己填，不锁死——OpenRouter 本身有几千个模型，预设只是常用捷径，不是全部选项。
OPENROUTER_TRANSLATION_MODEL_PRESETS: list[tuple[str, str]] = [
    ("qwen/qwen-turbo", "Qwen Turbo —— 最便宜，$0.05／$0.20 每百万 token"),
    ("deepseek/deepseek-chat", "DeepSeek Chat —— $0.15／$0.60，中文语感扎实（推荐）"),
    ("qwen/qwen-plus", "Qwen Plus —— $0.40／$1.20，比 Turbo 质量高一档"),
    ("openai/gpt-4o-mini", "GPT-4o mini —— $0.15／$0.60"),
    ("anthropic/claude-haiku-4.5", "Claude Haiku 4.5 —— $1／$5，最贵，质量最稳"),
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
        raise ValueError(f"未知的 LLM 供应商: {name}")

    model = db.get_setting(conn, model_key, default=PROVIDER_DEFAULT_MODEL.get(name, ""))

    env_name = PROVIDER_API_KEY_ENV[name]
    api_key = db.get_setting(conn, f"api_key::{name}", default=None) or os.environ.get(
        env_name
    )
    if not api_key:
        raise RuntimeError(
            f"缺少 {name} 的 API key：请在设置里填写，或设置环境变量 {env_name}"
            f"（缺少环境变量 {env_name}）"
        )
    return PROVIDER_REGISTRY[name](api_key=api_key, model=model)
