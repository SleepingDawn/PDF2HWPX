from __future__ import annotations

from src.normalize.text_normalizer import normalize_text


def format_answer_note(text: str) -> str:
    return normalize_text(text)
