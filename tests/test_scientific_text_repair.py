from __future__ import annotations

from src.utils.text_analysis import repair_scientific_ocr_text, should_inline_equation_in_text


def test_repair_scientific_ocr_text_restores_known_particle_and_ion_patterns() -> None:
    text = "(1) Rutherford experiment에서 a particles(He2+)를 gold nuclei (197 Au 79 + )을 향해"
    repaired = repair_scientific_ocr_text(text)
    assert "α particles(⁴₂He²⁺)" in repaired
    assert "¹⁹⁷Au⁷⁹⁺" in repaired


def test_repair_scientific_ocr_text_restores_angstrom_symbol() -> None:
    text = "거리(r)가 0.5 8일 때, electrostatic force(N)를 계산하시오."
    repaired = repair_scientific_ocr_text(text)
    assert "0.5Å일 때" in repaired


def test_repair_scientific_ocr_text_repairs_q2_ionic_notation() -> None:
    text = "lonic bond를 형성하는 A +B (g)이 있고, A +(g)와 B (g)의 핵간 거리는 2.27 A 이다."
    repaired = repair_scientific_ocr_text(text)
    assert "Ionic bond" in repaired
    assert "A⁺B⁻(g)" in repaired
    assert "A⁺(g)" in repaired
    assert "B⁻(g)의" in repaired
    assert "2.27Å" in repaired


def test_repair_scientific_ocr_text_does_not_convert_numbered_list_markers_to_angstrom() -> None:
    text = "1 A (g)과 B(g) 거리가 ∞일 때"
    repaired = repair_scientific_ocr_text(text)
    assert "1Å" not in repaired


def test_repair_scientific_ocr_text_repairs_q4_hydration_formula() -> None:
    text = "(1) 4주기 원소에서 M 2+(g) + 6H,0(1)→ [M(H2O)6]2+"
    repaired = repair_scientific_ocr_text(text)
    assert "M2+(g)" in repaired
    assert "6H2O(l)" in repaired


def test_should_inline_equation_in_text_detects_prose_plus_reaction() -> None:
    text = "(1) 4주기 원소에서 M2+(g) + 6H2O(l)→ [M(H2O)6]2+"
    assert should_inline_equation_in_text(text) is True


def test_repair_scientific_ocr_text_repairs_q5_complex_ocr_noise() -> None:
    text = "1 [Co(NH2CH2CH2NH2)2C|2]+ 2 [Fe(H2O)4Br2]*"
    repaired = repair_scientific_ocr_text(text)
    assert "[Co(NH2CH2CH2NH2)2Cl2]+" in repaired
    assert "[Fe(H2O)4Br2]+" in repaired
