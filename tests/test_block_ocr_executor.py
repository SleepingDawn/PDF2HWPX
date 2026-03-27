from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from src.adapters import ClovaGeneralAdapter
from src.executors import BlockOcrExecutor
from src.models.common import PageAsset
from src.models.evidence import QuestionPackage, QuestionPageRange
from src.models.ocr import NormalizedOCRPage, OCRLine


def test_block_executor_runs_crop_ocr_fallback(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    image = Image.new("RGB", (800, 1000), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((40, 80), "2H2 + O2 -> 2H2O", fill="black")
    image.save(image_path)

    adapter = ClovaGeneralAdapter({"invoke_url": "", "secret_key": ""})
    executor = BlockOcrExecutor(adapter)
    package = QuestionPackage(
        question_no=1,
        question_pages=[1],
        page_ranges=[QuestionPageRange(page_no=1, bbox=[0, 0, 800, 1000])],
        rough_text="2H2 + O2 -> 2H2O",
    )
    page_asset = PageAsset(
        page_no=1,
        image_path=image_path,
        thumbnail_path=image_path,
        width=800,
        height=1000,
        pdf_width=800,
        pdf_height=1000,
        extracted_text="2H2 + O2 -> 2H2O",
        extracted_words=[],
        page_hash="x",
    )
    ocr_page = NormalizedOCRPage(
        page_no=1,
        image_path=str(image_path),
        width=800,
        height=1000,
        lines=[OCRLine(line_id="p1_l1", text="2H2 + O2 -> 2H2O", bbox=[40, 80, 260, 120], confidence=0.91)],
        words=[],
        tables=[],
        raw_ref=None,
        backend="test",
    )

    blocks, issues = executor.build_blocks(
        package=package,
        page_assets={1: page_asset},
        ocr_pages={1: ocr_page},
        crops_dir=tmp_path / "crops",
    )

    assert not issues
    assert blocks
    assert blocks[0].ocr_engine == "block_ocr"
    assert blocks[0].coarse_ocr_text == "2H2 + O2 -> 2H2O"
