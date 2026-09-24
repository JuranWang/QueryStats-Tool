from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine import db
from engine.llm_provider import AnthropicProvider, LLMOutputError, OpenAICompatibleProvider, get_provider


def _response(*texts: str):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text) for text in texts]
    )


def test_anthropic_provider_parses_valid_json_and_combines_text_blocks():
    with patch("engine.llm_provider.anthropic.Anthropic") as client_class:
        client_class.return_value.messages.create.return_value = _response(
            '{"answer":', ' "ok"}'
        )
        provider = AnthropicProvider("fake-key", model="test-model")

        assert provider.complete_json("system", "user") == {"answer": "ok"}
        client_class.return_value.messages.create.assert_called_once_with(
            model="test-model",
            max_tokens=4096,
            system="system",
            messages=[{"role": "user", "content": "user"}],
        )


def test_anthropic_provider_extracts_json_from_markdown_fence():
    with patch("engine.llm_provider.anthropic.Anthropic") as client_class:
        client_class.return_value.messages.create.return_value = _response(
            '```json\n{"answer": "ok"}\n```'
        )
        provider = AnthropicProvider("fake-key")

        assert provider.complete_json("system", "user") == {"answer": "ok"}
        assert client_class.return_value.messages.create.call_count == 1


def test_anthropic_provider_retries_once_then_raises_for_invalid_json():
    with patch("engine.llm_provider.anthropic.Anthropic") as client_class:
        client_class.return_value.messages.create.side_effect = [
            _response("not json"),
            _response("still not json"),
        ]
        provider = AnthropicProvider("fake-key")

        with pytest.raises(LLMOutputError, match="still not json"):
            provider.complete_json("system", "original request")

        assert client_class.return_value.messages.create.call_count == 2
        retry_message = client_class.return_value.messages.create.call_args_list[1].kwargs[
            "messages"
        ][0]["content"]
        assert "not json" in retry_message
        assert "上次输出不是合法 JSON" in retry_message


def test_get_provider_reads_settings_and_constructs_anthropic(tmp_path, monkeypatch):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "anthropic")
    db.set_setting(conn, "llm_model", "configured-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")

    provider = get_provider(conn)

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "configured-model"
    conn.close()


def test_get_provider_requires_configured_api_key(tmp_path, monkeypatch):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # 显式指定供应商，不依赖"什么都不配置时默认是哪个供应商"这件事——这条测试
    # 要测的是"没配 key 该报错"，不是"默认供应商是 anthropic"，两件事不该耦合在
    # 一起（后者以后可能因为别的原因变化，不该连带把这条测试测坏或测假）。
    db.set_setting(conn, "llm_provider", "anthropic")

    with pytest.raises(RuntimeError, match="缺少环境变量 ANTHROPIC_API_KEY"):
        get_provider(conn)
    conn.close()


def test_get_provider_translation_purpose_falls_back_to_general_when_unset(tmp_path, monkeypatch):
    # 没单独配置"翻译专用"供应商——purpose="translation" 应该跟 purpose="general" 拿到
    # 一样的供应商/模型，不是报错、也不是默默换成别的默认值。
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "anthropic")
    db.set_setting(conn, "llm_model", "configured-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")

    provider = get_provider(conn, purpose="translation")

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "configured-model"
    conn.close()


def test_get_provider_translation_purpose_uses_override_when_configured(tmp_path, monkeypatch):
    # 单独配了翻译专用供应商（比如更便宜的 DeepSeek）——purpose="translation" 要用这份配置，
    # purpose="general"（默认值）不受影响，还是原来配的 anthropic。
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "anthropic")
    db.set_setting(conn, "llm_model", "configured-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")

    db.set_setting(conn, "llm_provider::translation", "deepseek")
    db.set_setting(conn, "llm_model::translation", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-deepseek-key")

    translation_provider = get_provider(conn, purpose="translation")
    general_provider = get_provider(conn)

    assert isinstance(translation_provider, OpenAICompatibleProvider)
    assert translation_provider.model == "deepseek-chat"
    assert isinstance(general_provider, AnthropicProvider)
    assert general_provider.model == "configured-model"
    conn.close()


def test_get_provider_constructs_minimax_as_openai_compatible(tmp_path, monkeypatch):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "minimax")
    db.set_setting(conn, "llm_model", "MiniMax-Text-01")
    monkeypatch.setenv("MINIMAX_API_KEY", "fake-minimax-key")

    provider = get_provider(conn)

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "MiniMax-Text-01"
    conn.close()


def test_qwen_coding_plan_uses_its_own_dedicated_base_url(tmp_path, monkeypatch):
    """真实反馈复现的 bug：内部团队共享的 Qwen key 是"Coding Plan"套餐（sk-sp-xxx），
    配到普通按量付费的 qwen 供应商（dashscope.aliyuncs.com/compatible-mode/v1）上
    直接 401 Incorrect API key provided——阿里云官方文档确认 Coding Plan 必须配
    它自己专属的域名（coding.dashscope.aliyuncs.com/v1），两者不能混用。"""

    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "qwen_coding_plan")
    monkeypatch.setenv("DASHSCOPE_CODING_PLAN_API_KEY", "sk-sp-fake-coding-plan-key")

    provider = get_provider(conn)

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider._client.base_url == "https://coding.dashscope.aliyuncs.com/v1/"
    # Coding Plan 有自己独立的一套版本化模型名，不是 qwen-plus/qwen-flash 这些
    # 按量付费的通用名字，默认模型也要跟着换，不能沿用普通 qwen 的默认值。
    assert provider.model == "qwen3.7-plus"
    conn.close()


def test_qwen_coding_plan_intl_uses_its_own_dedicated_base_url(tmp_path, monkeypatch):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "qwen_coding_plan_intl")
    monkeypatch.setenv("DASHSCOPE_CODING_PLAN_INTL_API_KEY", "sk-sp-fake-coding-plan-key")

    provider = get_provider(conn)

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider._client.base_url == "https://coding-intl.dashscope.aliyuncs.com/v1/"
    conn.close()


def test_get_provider_custom_reads_base_url_from_settings(tmp_path, monkeypatch):
    # "自定义 API"——同事各自用的供应商不在预置列表里，填 base_url + api key + 模型名
    # 就该能用，不需要改代码。
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "custom")
    db.set_setting(conn, "llm_model", "some-vendors-model-name")
    db.set_setting(conn, "custom_base_url", "https://example-vendor.com/v1")
    monkeypatch.setenv("CUSTOM_API_KEY", "fake-custom-key")

    provider = get_provider(conn)

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "some-vendors-model-name"
    assert provider._client.base_url == "https://example-vendor.com/v1/"
    conn.close()


def test_get_provider_custom_without_base_url_raises_clear_error(tmp_path, monkeypatch):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "custom")
    db.set_setting(conn, "llm_model", "some-model")
    monkeypatch.delenv("CUSTOM_BASE_URL", raising=False)
    monkeypatch.setenv("CUSTOM_API_KEY", "fake-custom-key")

    with pytest.raises(RuntimeError, match="没有填 base_url"):
        get_provider(conn)
    conn.close()


def test_get_provider_custom_without_model_raises_clear_error(tmp_path, monkeypatch):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "custom")
    db.set_setting(conn, "custom_base_url", "https://example-vendor.com/v1")
    monkeypatch.setenv("CUSTOM_API_KEY", "fake-custom-key")

    with pytest.raises(RuntimeError, match="没有填模型名"):
        get_provider(conn)
    conn.close()


def test_delete_setting_clears_override_back_to_default(tmp_path):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider::translation", "deepseek")

    db.delete_setting(conn, "llm_provider::translation")

    assert db.get_setting(conn, "llm_provider::translation", default=None) is None
    conn.close()
