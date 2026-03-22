from __future__ import annotations

import re


def normalize_formula(formula: str) -> tuple[str, bool]:
    text = formula.strip()
    if not text:
        return "", False
    text = text.replace("**", "^").replace("sqrt", "√")
    text = re.sub(r"\s+", " ", text)
    valid = any(token in text for token in ["=", "^", "/", "√", "→", "->", "⇌", "+", "-"])
    return text, valid
