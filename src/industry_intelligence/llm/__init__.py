"""LLM Provider 抽象（Phase 2）：统一接口 + DeepSeek 实现。"""

from industry_intelligence.llm.deepseek_provider import DeepSeekProvider
from industry_intelligence.llm.prompts import load_prompt
from industry_intelligence.llm.provider import LLMError, LLMProvider

__all__ = ["DeepSeekProvider", "LLMError", "LLMProvider", "load_prompt"]
