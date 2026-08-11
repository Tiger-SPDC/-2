"""DeepSeek 大模型实现（OpenAI 兼容 API，base_url 指向 DeepSeek）。"""

from __future__ import annotations

import json
import os

import openai
from openai.types.chat import ChatCompletionMessageParam

from industry_intelligence.config.models import LLMConfig
from industry_intelligence.llm.provider import LLMError, LLMProvider


class DeepSeekProvider(LLMProvider):
    """通过 OpenAI SDK 调用 DeepSeek Chat Completions。

    API Key 从环境变量读取（``LLMConfig.api_key_env``），支持显式注入（测试用）。
    """

    def __init__(
        self,
        config: LLMConfig,
        system_prompt: str = "",
        api_key: str | None = None,
    ) -> None:
        self._config = config
        self._system_prompt = system_prompt
        key = api_key if api_key is not None else os.environ.get(config.api_key_env, "")
        if not key:
            raise LLMError(f"{config.api_key_env} not set")
        self._client = openai.OpenAI(api_key=key, base_url=config.base_url)

    def generate(self, prompt: str) -> str:
        """返回纯文本补全。"""
        completion = self._client.chat.completions.create(
            model=self._config.model,
            messages=self._messages(prompt),
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
        )
        return completion.choices[0].message.content or ""

    def generate_structured(
        self, prompt: str, json_schema: dict[str, object]
    ) -> dict[str, object]:
        """请求 JSON 结构化输出并解析为 dict。"""
        completion = self._client.chat.completions.create(
            model=self._config.model,
            messages=self._messages(prompt),
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": json_schema, "strict": True},
            },
        )
        content = completion.choices[0].message.content or ""
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LLMError("LLM structured output must be a JSON object")
        return parsed

    def _messages(self, prompt: str) -> list[ChatCompletionMessageParam]:
        if self._system_prompt:
            return [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": prompt},
            ]
        return [{"role": "user", "content": prompt}]
