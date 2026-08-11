"""LLM Provider 单元测试：DeepSeek 实现与提示词加载。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from industry_intelligence.config.models import LLMConfig
from industry_intelligence.llm import DeepSeekProvider, LLMError, load_prompt


def _completion(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


@pytest.fixture
def mock_openai():
    with mock.patch("openai.OpenAI") as mock_cls:
        client = mock_cls.return_value
        client.chat.completions.create.return_value = _completion("")
        yield mock_cls


def _provider() -> DeepSeekProvider:
    return DeepSeekProvider(LLMConfig(), api_key="test-key")


def test_missing_api_key_raises() -> None:
    with pytest.raises(LLMError, match="DEEPSEEK_API_KEY not set"):
        DeepSeekProvider(LLMConfig())


def test_generate_returns_text(mock_openai) -> None:
    mock_openai.return_value.chat.completions.create.return_value = _completion(
        "hello world"
    )
    provider = _provider()
    assert provider.generate("hi") == "hello world"
    create = mock_openai.return_value.chat.completions.create
    create.assert_called_once()
    kwargs = create.call_args.kwargs
    assert kwargs["model"] == "deepseek-chat"
    assert kwargs["temperature"] == 0.1


def test_generate_empty_content(mock_openai) -> None:
    mock_openai.return_value.chat.completions.create.return_value = _completion("")
    assert _provider().generate("hi") == ""


def test_generate_structured(mock_openai) -> None:
    mock_openai.return_value.chat.completions.create.return_value = _completion(
        '{"event_type_id": "financing"}'
    )
    result = _provider().generate_structured("p", {"type": "object"})
    assert result == {"event_type_id": "financing"}


def test_generate_structured_invalid_json_raises(mock_openai) -> None:
    mock_openai.return_value.chat.completions.create.return_value = _completion(
        "not json"
    )
    with pytest.raises(LLMError, match="invalid JSON"):
        _provider().generate_structured("p", {})


def test_generate_structured_non_object_raises(mock_openai) -> None:
    mock_openai.return_value.chat.completions.create.return_value = _completion(
        "[1, 2, 3]"
    )
    with pytest.raises(LLMError, match="JSON object"):
        _provider().generate_structured("p", {})


def test_api_key_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    with mock.patch("openai.OpenAI") as mock_cls:
        DeepSeekProvider(LLMConfig())
        mock_cls.assert_called_once()
        assert mock_cls.call_args.kwargs["api_key"] == "env-key"


def test_load_prompt_ok(project_root) -> None:
    text = load_prompt("classification", config_dir=project_root / "config")
    assert "事件类型" in text


def test_load_prompt_missing_raises(tmp_path) -> None:
    with pytest.raises(LLMError, match="not found"):
        load_prompt("no_such_prompt", config_dir=tmp_path)


def test_load_prompt_rejects_path_traversal(tmp_path) -> None:
    with pytest.raises(LLMError, match="Invalid prompt name"):
        load_prompt("../secret", config_dir=tmp_path)
