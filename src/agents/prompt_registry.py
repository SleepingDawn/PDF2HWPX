from __future__ import annotations

from functools import lru_cache
from pathlib import Path


PROMPTS_PATH = Path(__file__).resolve().parents[2] / "prompts.md"


@lru_cache(maxsize=1)
def load_agent_prompts() -> dict[str, str]:
    content = PROMPTS_PATH.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in content.splitlines():
        if line.startswith("## "):
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[3:].strip()
            current_lines = []
            continue
        if current_key is not None:
            current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()
    return sections


def get_agent_prompt(name: str) -> str:
    prompts = load_agent_prompts()
    if name not in prompts:
        raise KeyError(f"Prompt '{name}' not found in {PROMPTS_PATH}")
    return prompts[name]
