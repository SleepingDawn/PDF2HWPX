from __future__ import annotations

import re


_REACTION_TOKENS = ("->", "→", "⇌", "<=>")
_FORMULA_OPERATORS = ("=", "^", "√", "∫", "Σ", "/", "±")
_PROSE_HINTS = (
    "다음",
    "서술",
    "설명",
    "물음",
    "이유",
    "자료",
    "그림",
    "조건",
    "과정",
    "답",
    "쓰시오",
    "표시",
    "계산",
    "경향성",
    "존재",
)

_SUPERSCRIPT_MAP = str.maketrans({
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
_SUPERSCRIPT_FROM_UNICODE = {
    "⁰": "0",
    "¹": "1",
    "²": "2",
    "³": "3",
    "⁴": "4",
    "⁵": "5",
    "⁶": "6",
    "⁷": "7",
    "⁸": "8",
    "⁹": "9",
    "⁺": "+",
    "⁻": "-",
}
_SUBSCRIPT_FROM_UNICODE = {
    "₀": "0",
    "₁": "1",
    "₂": "2",
    "₃": "3",
    "₄": "4",
    "₅": "5",
    "₆": "6",
    "₇": "7",
    "₈": "8",
    "₉": "9",
}

_ELEMENT = r"[A-Z][a-z]?"
_STATE = r"\((?:aq|s|l|g)\)"
_FORMULA_BODY = rf"(?:{_ELEMENT}(?:\d+)?|\([A-Za-z0-9]+\)(?:\d+)?)+"
_BRACKET_COMPLEX = rf"\[{_FORMULA_BODY}\](?:\d*[+-]|[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)?"
_SPECIES = rf"{_FORMULA_BODY}(?:\d*[+-])?{_STATE}?"
_PLACEHOLDER_ION = r"[A-Z][⁺⁻]?\(g\)"
_INLINE_CHEM_TOKEN_RE = re.compile(
    rf"([⁰¹²³⁴⁵⁶⁷⁸⁹]*[₀₁₂₃₄₅₆₇₈₉]*{_ELEMENT}[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+|{_BRACKET_COMPLEX}|{_SPECIES}|{_PLACEHOLDER_ION})"
)
_CHEM_TOKEN_SCAN_RE = re.compile(r"[\[\]A-Za-z0-9⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉()+\-→<>=,\.|*]+")


def canonicalize_repeated_text(text: str) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\d+", "#", collapsed)


def looks_like_prose_line(text: str) -> bool:
    stripped = re.sub(r"\s+", " ", text).strip()
    if not stripped:
        return False
    if any(token in stripped for token in _REACTION_TOKENS):
        return False
    if any(token in stripped for token in _FORMULA_OPERATORS):
        return False
    letters = sum(1 for char in stripped if char.isalpha() or "\uac00" <= char <= "\ud7a3")
    spaces = stripped.count(" ")
    if spaces >= 2 and letters >= max(10, int(len(stripped) * 0.35)):
        return True
    return any(hint in stripped for hint in _PROSE_HINTS) and spaces >= 1


def looks_like_equation_line(text: str) -> bool:
    stripped = re.sub(r"\s+", " ", text).strip()
    if not stripped or looks_like_prose_line(stripped):
        return False
    if any(token in stripped for token in _REACTION_TOKENS):
        return any(char.isupper() for char in stripped)
    operator_hits = sum(stripped.count(token) for token in _FORMULA_OPERATORS)
    symbolic = sum(1 for char in stripped if char in "=^√∫Σ/±()[]{}")
    digits = sum(char.isdigit() for char in stripped)
    letters = sum(1 for char in stripped if char.isalpha() or "\uac00" <= char <= "\ud7a3")
    if operator_hits >= 1 and len(stripped) < 180 and symbolic + digits >= max(3, letters // 2):
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9\[\]\(\)\+\-\.\s]+", stripped) and digits >= 2 and (stripped.count("+") + stripped.count("-")) >= 2)


def repair_scientific_ocr_text(text: str) -> str:
    repaired = re.sub(r"\blonic\b", "Ionic", text)
    repaired = _repair_alpha_particle(repaired)
    repaired = _repair_angstrom(repaired)
    repaired = _repair_isotope_notation(repaired)
    repaired = _repair_placeholder_ions(repaired)
    repaired = _repair_chemistry_like_tokens(repaired)
    return repaired


def _repair_alpha_particle(text: str) -> str:
    return re.sub(r"(?<![A-Za-z])a(?=\s+particles\b)", "α", text)


def _repair_angstrom(text: str) -> str:
    repaired = re.sub(r"(\d+(?:\.\d+)?)\s+8(?=(?:일 때|에서|이고|이면|인|를|을|,|\)|$))", r"\1Å", text)
    return re.sub(r"(\d+\.\d+)\s+A(?=(?:\s|$|\)))", r"\1Å", repaired)


def _repair_isotope_notation(text: str) -> str:
    repaired = text.replace("(He2+)", "(⁴₂He²⁺)")
    repaired = re.sub(r"(?<!\d)4He2\+", "⁴₂He²⁺", repaired)
    return re.sub(
        rf"\b(\d{{1,3}})\s*({_ELEMENT})\s*(\d{{1,2}})\s*\+\s*",
        lambda match: f"{_to_superscript(match.group(1))}{match.group(2)}{_to_superscript(match.group(3) + '+')}",
        repaired,
    )


def _repair_placeholder_ions(text: str) -> str:
    repaired = re.sub(r"\b([A-Z])\s*\+\s*([A-Z])\s*\(g\)", r"\1⁺\2⁻(g)", text)
    repaired = re.sub(r"\b([A-Z])\s*\+\s*\(g\)", r"\1⁺(g)", repaired)
    return re.sub(r"\b([A-Z])\s*\(g\)(?=\s*[가을를로의])", r"\1⁻(g)", repaired)


def _repair_chemistry_like_tokens(text: str) -> str:
    parts: list[str] = []
    last = 0
    for match in _CHEM_TOKEN_SCAN_RE.finditer(text):
        token = match.group(0)
        if not _looks_chemistry_like(token):
            continue
        parts.append(text[last:match.start()])
        parts.append(_normalize_chemistry_token(token))
        last = match.end()
    parts.append(text[last:])
    return "".join(parts)


def _looks_chemistry_like(token: str) -> bool:
    cleaned = token.strip()
    return bool(cleaned and ("[" in cleaned or any(char.isdigit() for char in cleaned)) and any(char.isupper() for char in cleaned))


def _normalize_chemistry_token(token: str) -> str:
    normalized = token.strip()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.replace("|", "l")
    normalized = normalized.replace("*", "+")
    normalized = re.sub(r"(?<=H)0(?=[\(\d\]])", "O", normalized)
    normalized = re.sub(r"(?<=\d)0(?=[A-Z])", "O", normalized)
    normalized = re.sub(r"\(([1I])\)", "(l)", normalized)
    normalized = re.sub(r"\(([aAqQ])\)", "(aq)", normalized)
    normalized = re.sub(r",(?=\d)", ".", normalized)
    normalized = _normalize_charge_spacing(normalized)
    normalized = _normalize_bracket_charge(normalized)
    return normalized


def _normalize_charge_spacing(token: str) -> str:
    return re.sub(rf"(?<![A-Za-z])({_ELEMENT})\s*(\d+[+-])(\((?:aq|s|l|g)\))", r"\1\2\3", token)


def _normalize_bracket_charge(token: str) -> str:
    return re.sub(r"(\[[A-Za-z0-9()]+\])([+-])$", r"\1\2", token)


def _to_superscript(value: str) -> str:
    return value.translate(_SUPERSCRIPT_MAP)


def split_inline_chemistry_segments(text: str) -> list[dict[str, str]]:
    segments: list[dict[str, str]] = []
    last = 0
    for match in _INLINE_CHEM_TOKEN_RE.finditer(text):
        token = match.group(0)
        script = chemistry_token_to_hancom(token)
        if not script:
            continue
        if match.start() > last:
            prefix = text[last:match.start()]
            if prefix:
                segments.append({"type": "text", "text": prefix})
        segments.append({"type": "equation", "script": script})
        last = match.end()
    if last < len(text):
        suffix = text[last:]
        if suffix:
            segments.append({"type": "text", "text": suffix})
    return segments or [{"type": "text", "text": text}]


def chemistry_token_to_hancom(token: str) -> str | None:
    if token == "A⁺B⁻(g)":
        return "A^{+}B^{-}(g)"
    if token == "A⁺(g)":
        return "A^{+}(g)"
    if token == "B⁻(g)":
        return "B^{-}(g)"
    return _unicode_chem_to_hancom(token) or _ascii_chem_to_hancom(token)


def _unicode_chem_to_hancom(token: str) -> str | None:
    isotope = re.fullmatch(r"([⁰¹²³⁴⁵⁶⁷⁸⁹]+)([₀₁₂₃₄₅₆₇₈₉]+)?([A-Z][a-z]?)([⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)", token)
    if isotope:
        mass = "".join(_SUPERSCRIPT_FROM_UNICODE[ch] for ch in isotope.group(1))
        atomic = isotope.group(2)
        charge = "".join(_SUPERSCRIPT_FROM_UNICODE.get(ch, ch) for ch in isotope.group(4))
        if atomic:
            atomic = "".join(_SUBSCRIPT_FROM_UNICODE[ch] for ch in atomic)
            return f" ^{{{mass}}}_{{{atomic}}}{isotope.group(3)}^{{{charge}}} "
        return f" ^{{{mass}}}{isotope.group(3)}^{{{charge}}} "
    ion = re.fullmatch(r"([A-Z][a-z]?)([⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)\(g\)", token)
    if ion:
        charge = "".join(_SUPERSCRIPT_FROM_UNICODE.get(ch, ch) for ch in ion.group(2))
        return f"{ion.group(1)}^{{{charge}}}(g)"
    return None


def _ascii_chem_to_hancom(token: str) -> str | None:
    state = ""
    state_match = re.search(r"(\((?:aq|s|l|g)\))$", token)
    if state_match:
        state = state_match.group(1)
        token = token[: state_match.start()]

    charge = ""
    charge_match = re.search(r"(\d*[+-])$", token)
    if charge_match:
        charge = charge_match.group(1)
        token = token[: charge_match.start()]

    if not re.search(r"[A-Z]", token):
        return None
    if re.fullmatch(r"[A-Z]{2,}", token):
        return None

    converted = re.sub(r"(\d+)", lambda match: f"_{{{match.group(1)}}}", token)
    if charge:
        converted = f"{converted}^{{{charge}}}"
    return f"{converted}{state}"


def should_inline_equation_in_text(text: str) -> bool:
    stripped = re.sub(r"\s+", " ", text).strip()
    if not stripped or not any(token in stripped for token in _REACTION_TOKENS):
        return False
    hangul = sum(1 for char in stripped if "\uac00" <= char <= "\ud7a3")
    return hangul >= 4 and stripped.count(" ") >= 2
