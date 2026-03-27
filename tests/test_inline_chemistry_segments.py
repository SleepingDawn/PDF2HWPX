from __future__ import annotations

from src.utils.text_analysis import chemistry_token_to_hancom, split_inline_chemistry_segments


def test_split_inline_chemistry_segments_extracts_q1_isotopes() -> None:
    text = "(1) Rutherford experiment에서 α particles(⁴₂He²⁺)를 gold nuclei (¹⁹⁷Au⁷⁹⁺)을 향해"
    segments = split_inline_chemistry_segments(text)
    equation_scripts = [segment["script"] for segment in segments if segment["type"] == "equation"]
    assert any("He" in script for script in equation_scripts)
    assert any("Au" in script for script in equation_scripts)


def test_split_inline_chemistry_segments_extracts_q2_ions() -> None:
    text = "A⁺B⁻(g)을 형성할 때, A⁺(g)와 B⁻(g)가 필요하다."
    segments = split_inline_chemistry_segments(text)
    equation_scripts = [segment["script"] for segment in segments if segment["type"] == "equation"]
    assert "A^{+}B^{-}(g)" in equation_scripts
    assert "A^{+}(g)" in equation_scripts
    assert "B^{-}(g)" in equation_scripts


def test_chemistry_token_to_hancom_handles_known_tokens() -> None:
    assert chemistry_token_to_hancom("⁴₂He²⁺") is not None
    assert chemistry_token_to_hancom("¹⁹⁷Au⁷⁹⁺") is not None


def test_split_inline_chemistry_segments_extracts_q3_salts() -> None:
    text = "AgCl과 Agl의 용해도를 비교하시오."
    segments = split_inline_chemistry_segments(text.replace("Agl", "AgI"))
    equation_scripts = [segment["script"] for segment in segments if segment["type"] == "equation"]
    assert "AgCl" in equation_scripts
    assert "AgI" in equation_scripts


def test_split_inline_chemistry_segments_extracts_general_formulas() -> None:
    text = "[FeCl4]-와 [Co(CO)6]3+, H2O의 배치를 비교하시오."
    segments = split_inline_chemistry_segments(text)
    equation_scripts = [segment["script"] for segment in segments if segment["type"] == "equation"]
    assert "[FeCl_{4}]^{-}" in equation_scripts
    assert "[Co(CO)_{6}]^{3+}" in equation_scripts
    assert "H_{2}O" in equation_scripts


def test_split_inline_chemistry_segments_extracts_q4_reaction_tokens() -> None:
    text = "(1) 4주기 원소에서 M2+(g) + 6H2O(l)→ [M(H2O)6]2+"
    segments = split_inline_chemistry_segments(text)
    equation_scripts = [segment["script"] for segment in segments if segment["type"] == "equation"]
    assert "M^{2+}(g)" in equation_scripts
    assert "H_{2}O(l)" in equation_scripts
    assert "[M(H_{2}O)_{6}]^{2+}" in equation_scripts
