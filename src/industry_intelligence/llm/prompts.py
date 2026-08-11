"""提示词模板加载：config/prompts/{name}.md。"""

from __future__ import annotations

from pathlib import Path

from industry_intelligence.llm.provider import LLMError


def load_prompt(name: str, config_dir: str | Path = "config") -> str:
    """加载 ``config/prompts/{name}.md`` 模板内容。

    只接受纯文件名（不含路径分隔符），防止路径穿越。
    """
    if not name or name != Path(name).name:
        raise LLMError(f"Invalid prompt name: {name!r}")
    path = Path(config_dir) / "prompts" / f"{name}.md"
    if not path.is_file():
        raise LLMError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")
