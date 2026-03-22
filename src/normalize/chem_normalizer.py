from __future__ import annotations

import re


CHEM_PATTERN = re.compile(r"([A-Z][a-z]?\d*)+")


def normalize_chem_equation(text: str) -> tuple[str, bool]:
    candidate = text.strip().replace("→", "->").replace("⇌", "<=>")
    candidate = re.sub(r"\s+", " ", candidate)
    valid = any(token in candidate for token in ["->", "<=>"]) and bool(CHEM_PATTERN.search(candidate))
    return candidate, valid
