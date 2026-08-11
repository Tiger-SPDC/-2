"""DeepSeek 大模型实现（OpenAI 兼容 API，base_url 指向 DeepSeek）。"""

from __future__ import annotations

import json
import os
import time

import openai
from openai.types.chat import ChatCompletionMessageParam

from industry_intelligence.config.models import LLMConfig
from industry_intelligence.llm.provider import LLMError, LLMProvider

#: json_object 空/非法响应时的重试次数与退避间隔（秒）。
#: deepseek-v4-flash 偶发返回空内容，尤以长结构化输出（分析师、Review）为甚，
#: 短退避后重试可显著提升成功率。
_JSON_RETRY_ATTEMPTS = 3
_JSON_RETRY_BACKOFF_SECONDS = 2.0


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
        """请求 JSON 结构化输出并解析为 dict。

        使用 ``json_object``（传统 JSON mode）：DeepSeek API 不提供 OpenAI 新版
        ``json_schema`` 结构化输出（实测返回 "This response_format type is
        unavailable now"）。schema 通过 prompt 注入（各模板已内嵌字段说明并
        含 "json" 关键词，满足 json_object 模式的引导要求）；返回内容在
        调用方按字段容忍解析。
        """
        user_prompt = prompt
        # DeepSeek json_object 模式只检查 user 消息：不含 "json" 时自动补一句，
        # 保证任意调用方（如分析师把模板放 system 消息、user 仅为注入数据）都满足要求。
        if "json" not in user_prompt.lower():
            user_prompt = user_prompt + "\n\n请只输出一个 json 对象，不要输出其它文字。"
        content = self._request_json(user_prompt)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMError(f"LLM returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise LLMError("LLM structured output must be a JSON object")
        return parsed

    def _request_json(self, user_prompt: str) -> str:
        """发起 json_object 请求；空/非法 JSON 时自动重试并退避。

        deepseek-v4-flash 偶发返回空或截断内容，多次重试可显著提升
        长结构化输出（如 4 分析师、Review Agent）的成功率。首次返回
        合法 JSON 时直接返回；非法 JSON 仅重试（让调用方在末次尝试后
        抛出解析错误）。
        """
        for attempt in range(_JSON_RETRY_ATTEMPTS):
            completion = self._client.chat.completions.create(
                model=self._config.model,
                messages=self._messages(user_prompt),
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
                response_format={"type": "json_object"},
            )
            content = completion.choices[0].message.content or ""
            if content:
                if attempt == 0:
                    try:
                        json.loads(content)
                    except json.JSONDecodeError:
                        pass  # 非法 JSON → 退避后重试
                    else:
                        return content
                else:
                    return content
            if attempt < _JSON_RETRY_ATTEMPTS - 1:
                time.sleep(_JSON_RETRY_BACKOFF_SECONDS)
        return ""

    def _messages(self, prompt: str) -> list[ChatCompletionMessageParam]:
        if self._system_prompt:
            return [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": prompt},
            ]
        return [{"role": "user", "content": prompt}]
