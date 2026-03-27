from __future__ import annotations

from PIL import Image, ImageDraw

from src.evidence.question_evidence import QuestionEvidenceBuilder
from src.models.common import PageAsset
from src.models.evidence import QuestionPackage, QuestionPageRange
from src.models.ocr import NormalizedOCRPage, OCRLine


def test_question_evidence_detects_image_blocks(tmp_path) -> None:
    image_path = tmp_path / "page.png"
    image = Image.new("RGB", (1000, 1400), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 80), "1. Sample question", fill="black")
    draw.rectangle((180, 300, 780, 900), outline="black", width=6, fill="#dddddd")
    image.save(image_path)

    asset = PageAsset(
        page_no=1,
        image_path=image_path,
        thumbnail_path=image_path,
        width=1000,
        height=1400,
        pdf_width=1000,
        pdf_height=1400,
        extracted_text="1. Sample question",
        extracted_words=[],
        page_hash="x",
    )
    ocr_page = NormalizedOCRPage(
        page_no=1,
        image_path=str(image_path),
        width=1000,
        height=1400,
        lines=[OCRLine(line_id="l1", text="1. Sample question", bbox=[60, 80, 320, 120], confidence=0.98)],
        words=[],
        tables=[],
        raw_ref=None,
        backend="test",
    )
    package = QuestionPackage(
        question_no=1,
        question_pages=[1],
        page_ranges=[QuestionPageRange(page_no=1, bbox=[0, 0, 1000, 1400])],
        rough_text="1. Sample question",
    )

    blocks, issues = QuestionEvidenceBuilder().build(
        package=package,
        page_assets={1: asset},
        ocr_pages={1: ocr_page},
        crops_dir=tmp_path / "crops",
    )

    assert not issues
    assert any(block.type_candidates[0].type == "image" for block in blocks)
