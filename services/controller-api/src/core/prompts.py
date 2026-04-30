from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any


PROMPTS_ROOT = Path(__file__).resolve().parents[4] / "prompts"


def read_prompt(name: str) -> str:
    path = PROMPTS_ROOT / name
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise RuntimeError(f"Prompt file is empty: {path}")
    return content


def render_prompt_template(name: str, values: dict[str, Any]) -> str:
    template = Template(read_prompt(name))
    return template.substitute({key: str(value) for key, value in values.items()})
