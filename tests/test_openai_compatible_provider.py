from types import SimpleNamespace
from unittest.mock import call, patch

import pytest

from engine import db
from engine.llm_provider import (
    LLMOutputError,
    OpenAICompatibleProvider,
    PROVIDER_DEFAULT_MODEL,
    PROVIDER_REGISTRY,
    get_provider,
)


def _response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_openai_compatible_provider_parses_valid_json():
    with patch("engine.llm_provider.openai.OpenAI") as client_class:
        client_class.return_value.chat.completions.create.return_value = _response(
            '{"answer": "ok"}'
        )

        provider = OpenAICompatibleProvider(
            "fake-key", model="test-model", base_url="https://example.com/v1"
        )

        assert provider.complete_json("system", "user") == {"answer": "ok"}
        client_class.assert_called_once_with(
            api_key="fake-key", base_url="https://example.com/v1"
        )
        client_class.return_value.chat.completions.create.assert_called_once_with(
            model="test-model",
            messages=[
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
        )


def test_openai_compatible_provider_retries_once_then_raises():
    with patch("engine.llm_provider.openai.OpenAI") as client_class:
        client_class.return_value.chat.completions.create.side_effect = [
            _response("not json"),
            _response("still not json"),
        ]
        provider = OpenAICompatibleProvider(
            "fake-key", model="test-model", base_url="https://example.com/v1"
        )

        with pytest.raises(LLMOutputError, match="still not json"):
            provider.complete_json("system", "original request")

        create = client_class.return_value.chat.completions.create
        assert create.call_count == 2
        retry_messages = create.call_args_list[1].kwargs["messages"]
        assert retry_messages[0] == {"role": "system", "content": "system"}
        assert "not json" in retry_messages[1]["content"]
        assert "上次输出不是合法 JSON" in retry_messages[1]["content"]


def test_openai_compatible_provider_uses_correct_base_url_per_factory():
    expected = {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "kimi": "https://api.moonshot.cn/v1",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "grok": "https://api.x.ai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }

    with patch("engine.llm_provider.openai.OpenAI") as client_class:
        for name in expected:
            PROVIDER_REGISTRY[name](api_key=f"{name}-key", model=f"{name}-model")

        assert client_class.call_args_list == [
            call(api_key=f"{name}-key", base_url=base_url)
            for name, base_url in expected.items()
        ]


def test_get_provider_prefers_settings_table_key_over_env_var(
    tmp_path, monkeypatch
):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "openai")
    db.set_setting(conn, "llm_model", "gpt-5")
    db.set_setting(conn, "api_key::openai", "from-settings-table")
    monkeypatch.setenv("OPENAI_API_KEY", "from-env-should-be-ignored")

    with patch("engine.llm_provider.openai.OpenAI") as client_class:
        provider = get_provider(conn)

    client_class.assert_called_once_with(
        api_key="from-settings-table", base_url="https://api.openai.com/v1"
    )
    assert provider.model == "gpt-5"
    conn.close()


def test_get_provider_falls_back_to_env_var_when_settings_table_empty(
    tmp_path, monkeypatch
):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")

    with patch("engine.llm_provider.openai.OpenAI") as client_class:
        get_provider(conn)

    client_class.assert_called_once_with(
        api_key="from-env", base_url="https://api.deepseek.com/v1"
    )
    conn.close()


def test_get_provider_uses_default_model_when_not_configured(tmp_path, monkeypatch):
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "from-env")

    with patch("engine.llm_provider.openai.OpenAI"):
        provider = get_provider(conn)

    assert provider.model == PROVIDER_DEFAULT_MODEL["qwen"]
    conn.close()


def test_get_provider_supports_openrouter_with_qwen_flash_default(tmp_path, monkeypatch):
    # 走 OpenRouter 聚合网关，而不是直连 DashScope——同一套 OpenAI 兼容客户端，只是
    # base_url/模型名前缀不一样，不需要专门给 OpenRouter 写新的 provider 类。默认模型
    # 从 qwen-turbo 换成了 qwen3.8-flash——阿里云官方文档说 qwen-turbo"不再更新，
    # 建议迁移到 qwen-flash"，默认值跟着换成当前推荐的档位。
    conn = db.init_db(str(tmp_path / "survey.sqlite"))
    db.set_setting(conn, "llm_provider::translation", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")

    with patch("engine.llm_provider.openai.OpenAI") as client_class:
        provider = get_provider(conn, purpose="translation")

    client_class.assert_called_once_with(
        api_key="from-env", base_url="https://openrouter.ai/api/v1"
    )
    assert provider.model == "qwen/qwen3.8-flash"
    conn.close()
