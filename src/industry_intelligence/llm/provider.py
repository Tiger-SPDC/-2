"""LLM Provider 抽象层：统一接口，不绑定单一厂商或模型。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(Exception):
    """LLM 调用、配置或解析错误。"""


class LLMProvider(ABC):
    """大模型提供方抽象。

    实现约定：
    - :meth:`generate` 返回纯文本回复；
    - :meth:`generate_structured` 返回可 JSON 序列化的 dict；
    - 出错抛 :class:`LLMError`，不返回 None / 空结果。
    """

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """发送 prompt，返回纯文本回复。"""

    @abstractmethod
    def generate_structured(
        self, prompt: str, json_schema: dict[str, object]
    ) -> dict[str, object]:
        """发送 prompt，返回符合 ``json_schema`` 的 JSON 对象。"""
