from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


PUA_REPLACEMENTS = {
    "\ue034": "1",
    "\ue035": "2",
    "\ue036": "3",
    "\ue037": "4",
    "\ue038": "5",
    "\ue039": "6",
    "\ue03a": "7",
    "\ue03b": "8",
    "\ue03c": "9",
    "\ue03d": "0",
    "\ue044": "(",
    "\ue045": ")",
    "\ue046": "-",
    "\ue048": "+",
    "\ue049": "[",
    "\ue04a": "]",
    "\ue054": "/",
}

SUPERSCRIPT_MAP = str.maketrans({
    "0": "⁰",
    "1": "¹",
    "2": "²",
    "3": "³",
    "4": "⁴",
    "5": "⁵",
    "6": "⁶",
    "7": "⁷",
    "8": "⁸",
    "9": "⁹",
    "+": "⁺",
    "-": "⁻",
})

SUBSCRIPT_MAP = str.maketrans({
    "0": "₀",
    "1": "₁",
    "2": "₂",
    "3": "₃",
    "4": "₄",
    "5": "₅",
    "6": "₆",
    "7": "₇",
    "8": "₈",
    "9": "₉",
})


def _apply_isotope_superscripts(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        mass = match.group(1).translate(SUPERSCRIPT_MAP)
        symbol = match.group(2)
        charge = (match.group(3) or "").translate(SUPERSCRIPT_MAP)
        return f"{mass}{symbol}{charge}"

    text = re.sub(r"(?<![A-Za-z0-9.])(\d{1,3})([A-Z][a-z]?)(\d*[+-])(?=\)|\s|$)", replace, text)
    text = re.sub(r"(?<![A-Za-z0-9.])(\d{1,3})([A-Z][a-z]?)(?=\b)", lambda m: f"{m.group(1).translate(SUPERSCRIPT_MAP)}{m.group(2)}", text)
    return text


def _apply_charge_superscripts(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        charge = match.group(2)
        return f"{token}{charge.translate(SUPERSCRIPT_MAP)}"

    patterns = [
        r"([A-Za-z\]\)])\s+(\d*[+-])(?=\((?:aq|g|l|s)\))",
        r"([A-Za-z\]\)])(\d*[+-])(?=\((?:aq|g|l|s)\))",
        r"([A-Za-z\]\)])(\d*[+-])(?=[A-Z])",
        r"([A-Za-z\]\)])(\d*[+-])(?=\s|[^A-Za-z0-9]|$)",
        r"([A-Za-z\]\)])(\d*[+-])(?=$)",
    ]
    for pattern in patterns:
        text = re.sub(pattern, replace, text)
    return text


def _apply_chemical_subscripts(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return match.group(1) + match.group(2).translate(SUBSCRIPT_MAP)

    return re.sub(r"([A-Za-z\)])(\d+)", replace, text)


def _normalize_chemistry_tokens(text: str) -> str:
    token_pattern = re.compile(r"(?<![A-Za-z])(?:\d{1,3})?(?:\[[A-Za-z0-9()+\-\]]+\]|[A-Z][A-Za-z0-9()+\-\[\]]{0,20})(?:\((?:aq|g|l|s)\))?(?:\d*[+-])?")

    def replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if not any(char.isdigit() for char in token) and "[" not in token and "+" not in token and "-" not in token:
            return token
        normalized = _apply_isotope_superscripts(token)
        normalized = _apply_charge_superscripts(normalized)
        normalized = _apply_chemical_subscripts(normalized)
        return normalized

    return token_pattern.sub(replace, text)


def sanitize_exam_text(text: str) -> str:
    for source, target in PUA_REPLACEMENTS.items():
        text = text.replace(source, target)
    text = re.sub(r"\(\s*([gls])\s*\)", r"(\1)", text)
    text = re.sub(r"\(\s*aq\s*\)", "(aq)", text)
    text = re.sub(r"([A-Za-z\]\)])\s+(\d*[+-])(?=\((?:aq|g|l|s)\))", r"\1\2", text)
    text = re.sub(r"([A-Za-z0-9])\s*([+-])\s*([A-Za-z])", r"\1\2\3", text)
    text = re.sub(r"([A-Za-z])\s*([+-])\s*(\()", r"\1\2\3", text)
    text = re.sub(r"(\((?:aq|g|l|s)\))\+", r"\1 + ", text)
    text = re.sub(r"(\((?:aq|g|l|s)\))\-", r"\1 - ", text)
    text = _normalize_chemistry_tokens(text)
    text = re.sub(r"\s*-\s*>\s*", "->", text)
    text = re.sub(r"\s*<\s*=\s*>\s*", "<=>", text)
    text = re.sub(r"\s+", " ", text)
    return normalize_text(text)


INLINE_CHEM_TOKEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:"
    r"[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,3}[A-Z][a-z]?[⁰¹²³⁴⁵⁶⁷⁸⁹]*[⁺⁻]?"
    r"|"
    r"\d+[A-Z][a-z]?(?:[₀₁₂₃₄₅₆₇₈₉\d][A-Za-z]?)*(?:\((?:aq|g|l|s)\))?(?:[⁰¹²³⁴⁵⁶⁷⁸⁹\d]*[⁺⁻+-])?"
    r"|"
    r"\[[A-Za-z0-9₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻()+\-\]]+\](?:[⁰¹²³⁴⁵⁶⁷⁸⁹\d]*[⁺⁻+-])?"
    r"|"
    r"(?:[A-Z][a-z]?(?:[₀₁₂₃₄₅₆₇₈₉\d][A-Za-z]?)*)"
    r"(?:[⁰¹²³⁴⁵⁶⁷⁸⁹\d]*[⁺⁻+-])?"
    r"(?:\((?:aq|g|l|s)\))?"
    r"(?:[A-Z][a-z]?(?:[₀₁₂₃₄₅₆₇₈₉\d][A-Za-z]?)*(?:[⁰¹²³⁴⁵⁶⁷⁸⁹\d]*[⁺⁻+-])?(?:\((?:aq|g|l|s)\))?)*"
    r")"
)


def split_inline_chemistry_segments(text: str) -> list[dict[str, str]]:
    segments: list[dict[str, str]] = []
    cursor = 0
    for match in INLINE_CHEM_TOKEN_PATTERN.finditer(text):
        token = match.group(0)
        if len(token) < 2:
            continue
        if not _looks_like_chemistry_token(token):
            continue
        if match.start() > cursor:
            plain = text[cursor:match.start()]
            if plain:
                segments.append({"type": "text", "text": plain})
        segments.append({"type": "equation", "script": token})
        cursor = match.end()
    if cursor < len(text):
        tail = text[cursor:]
        if tail:
            segments.append({"type": "text", "text": tail})
    return segments or [{"type": "text", "text": text}]


def _looks_like_chemistry_token(token: str) -> bool:
    if "(aq)" in token or "(g)" in token or "(l)" in token or "(s)" in token:
        return True
    if any(char in token for char in "[]₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻"):
        return True
    if re.search(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,3}[A-Z][a-z]?", token):
        return True
    if re.search(r"[A-Z][a-z]?\d", token):
        return True
    if re.search(r"\d+[A-Z][a-z]?[⁺⁻+-]", token):
        return True
    if re.search(r"\d+[A-Z][a-z]?(?:[₀₁₂₃₄₅₆₇₈₉\d])", token):
        return True
    if re.fullmatch(r"[A-Z][a-z]?[⁺⁻+-]", token):
        return True
    if re.fullmatch(r"[A-Z]\((?:aq|g|l|s)\)", token):
        return True
    return False
