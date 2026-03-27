from __future__ import annotations

from pathlib import Path

from PIL import Image

from src.evidence.question_evidence import QuestionEvidenceBuilder
from src.models.common import PageAsset
from src.models.evidence import QuestionPackage, QuestionPageRange
from src.models.ocr import NormalizedOCRPage, OCRLine, OCRTable, OCRTableCell, OCRWord


def test_question_evidence_builder_excludes_text_lines_inside_structured_tables(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (1200, 1600), "white").save(image_path)
    builder = QuestionEvidenceBuilder()
    ocr_page = NormalizedOCRPage(
        page_no=1,
        image_path=str(image_path),
        width=1200,
        height=1600,
        lines=[
            OCRLine(line_id="l1", text="표 밖 본문", bbox=[100, 100, 300, 140], confidence=0.99),
            OCRLine(line_id="l2", text="A 1", bbox=[120, 420, 260, 455], confidence=0.99),
            OCRLine(line_id="l3", text="B 2", bbox=[280, 420, 420, 455], confidence=0.99),
        ],
        tables=[
            OCRTable(
                table_id="t1",
                bbox=[100, 380, 500, 620],
                confidence=0.99,
                n_rows=2,
                n_cols=2,
                cells=[
                    OCRTableCell(row=0, col=0, rowspan=1, colspan=1, bbox=[110, 390, 240, 470], text="A", confidence=0.99),
                    OCRTableCell(row=0, col=1, rowspan=1, colspan=1, bbox=[250, 390, 390, 470], text="B", confidence=0.99),
                    OCRTableCell(row=1, col=0, rowspan=1, colspan=1, bbox=[110, 480, 240, 560], text="1", confidence=0.99),
                    OCRTableCell(row=1, col=1, rowspan=1, colspan=1, bbox=[250, 480, 390, 560], text="2", confidence=0.99),
                ],
            )
        ],
    )
    package = QuestionPackage(question_no=1, question_pages=[1], page_ranges=[QuestionPageRange(page_no=1, bbox=[0, 0, 1200, 1600])], rough_text="")
    page_asset = PageAsset(
        page_no=1,
        image_path=image_path,
        thumbnail_path=image_path,
        width=1200,
        height=1600,
        pdf_width=1200.0,
        pdf_height=1600.0,
        extracted_text="",
        extracted_words=[],
        page_hash="x",
    )

    blocks, issues = builder.build(
        package=package,
        page_assets={1: page_asset},
        ocr_pages={1: ocr_page},
        crops_dir=tmp_path / "crops",
        noise_profile=None,
    )

    assert issues == []
    texts = [block.ocr_text for block in blocks if not block.table_candidate]
    assert texts == ["표 밖 본문"]
    table_blocks = [block for block in blocks if block.table_candidate]
    assert len(table_blocks) == 1


def test_question_evidence_builder_keeps_false_table_as_text_when_structure_is_sparse(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (1200, 1600), "white").save(image_path)
    builder = QuestionEvidenceBuilder()
    ocr_page = NormalizedOCRPage(
        page_no=1,
        image_path=str(image_path),
        width=1200,
        height=1600,
        lines=[
            OCRLine(line_id="l1", text="실험 과정", bbox=[120, 420, 320, 455], confidence=0.99),
            OCRLine(line_id="l2", text="1 시약을 넣는다.", bbox=[120, 470, 520, 505], confidence=0.99),
        ],
        tables=[
            OCRTable(
                table_id="t1",
                bbox=[100, 380, 600, 620],
                confidence=0.99,
                n_rows=4,
                n_cols=2,
                cells=[
                    OCRTableCell(row=0, col=0, rowspan=1, colspan=1, bbox=[110, 390, 200, 430], text="1", confidence=0.99),
                    OCRTableCell(row=0, col=1, rowspan=1, colspan=1, bbox=[210, 390, 560, 430], text="", confidence=0.99),
                    OCRTableCell(row=1, col=0, rowspan=1, colspan=1, bbox=[110, 440, 200, 480], text="2", confidence=0.99),
                    OCRTableCell(row=1, col=1, rowspan=1, colspan=1, bbox=[210, 440, 560, 480], text="긴 설명 문장입니다. 표라기보다 실험 절차에 가깝습니다.", confidence=0.99),
                ],
            )
        ],
    )
    package = QuestionPackage(question_no=1, question_pages=[1], page_ranges=[QuestionPageRange(page_no=1, bbox=[0, 0, 1200, 1600])], rough_text="")
    page_asset = PageAsset(
        page_no=1,
        image_path=image_path,
        thumbnail_path=image_path,
        width=1200,
        height=1600,
        pdf_width=1200.0,
        pdf_height=1600.0,
        extracted_text="",
        extracted_words=[],
        page_hash="x",
    )

    blocks, issues = builder.build(
        package=package,
        page_assets={1: page_asset},
        ocr_pages={1: ocr_page},
        crops_dir=tmp_path / "crops",
        noise_profile=None,
    )

    assert issues == []
    assert all(not block.table_candidate for block in blocks)
    assert any("실험 과정" in block.ocr_text for block in blocks)


def test_question_evidence_builder_splits_wide_multilane_rows_using_words(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (2400, 1600), "white").save(image_path)
    builder = QuestionEvidenceBuilder()
    ocr_page = NormalizedOCRPage(
        page_no=1,
        image_path=str(image_path),
        width=2400,
        height=1600,
        lines=[],
        words=[
            OCRWord(word_id="w1", text="13.", bbox=[120, 120, 180, 160], confidence=0.99),
            OCRWord(word_id="w2", text="왼쪽", bbox=[220, 120, 340, 160], confidence=0.99),
            OCRWord(word_id="w3", text="서술", bbox=[360, 120, 470, 160], confidence=0.99),
            OCRWord(word_id="w4", text="(1)", bbox=[1380, 120, 1450, 160], confidence=0.99),
            OCRWord(word_id="w5", text="오른쪽", bbox=[1490, 120, 1650, 160], confidence=0.99),
            OCRWord(word_id="w6", text="문항", bbox=[1670, 120, 1780, 160], confidence=0.99),
            OCRWord(word_id="w7", text="추가", bbox=[140, 220, 240, 260], confidence=0.99),
            OCRWord(word_id="w8", text="설명", bbox=[260, 220, 360, 260], confidence=0.99),
            OCRWord(word_id="w9", text="답안", bbox=[1410, 220, 1510, 260], confidence=0.99),
            OCRWord(word_id="w10", text="영역", bbox=[1530, 220, 1630, 260], confidence=0.99),
        ],
    )
    lines = builder._question_lines(ocr_page, [0, 0, 2400, 1600], None, [])
    assert [line.text for line in lines] == ["13. 왼쪽 서술", "(1) 오른쪽 문항", "추가 설명", "답안 영역"]


def test_question_evidence_builder_excludes_text_near_detected_image_boxes(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (1200, 1600), "white").save(image_path)
    builder = QuestionEvidenceBuilder()
    ocr_page = NormalizedOCRPage(
        page_no=1,
        image_path=str(image_path),
        width=1200,
        height=1600,
        lines=[],
        words=[
            OCRWord(word_id="w1", text="도식", bbox=[140, 420, 220, 455], confidence=0.99),
            OCRWord(word_id="w2", text="라벨", bbox=[230, 420, 320, 455], confidence=0.99),
            OCRWord(word_id="w3", text="본문", bbox=[140, 120, 220, 155], confidence=0.99),
            OCRWord(word_id="w4", text="설명", bbox=[230, 120, 320, 155], confidence=0.99),
        ],
    )
    lines = builder._question_lines(ocr_page, [0, 0, 700, 1600], None, [[100, 380, 500, 620]])
    assert [line.text for line in lines] == ["본문 설명"]


def test_question_evidence_chart_label_filter_marks_short_plot_labels_near_images() -> None:
    builder = QuestionEvidenceBuilder()
    assert builder._looks_like_chart_label("-4.0")
    assert builder._looks_like_chart_label("(다)")
    assert builder._looks_like_chart_label("Contour plots")
    assert not builder._looks_like_chart_label("에너지가 가장 높은 wave function")


def test_question_evidence_builder_accepts_two_column_key_value_table(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (1600, 2000), "white").save(image_path)
    builder = QuestionEvidenceBuilder()
    ocr_page = NormalizedOCRPage(
        page_no=1,
        image_path=str(image_path),
        width=1600,
        height=2000,
        lines=[],
        tables=[
            OCRTable(
                table_id="t1",
                bbox=[900, 300, 1450, 600],
                confidence=0.99,
                n_rows=3,
                n_cols=2,
                cells=[
                    OCRTableCell(row=0, col=0, rowspan=1, colspan=1, bbox=[910, 310, 1180, 390], text="A⁺B⁻(g)의 핵간 거리", confidence=0.99),
                    OCRTableCell(row=0, col=1, rowspan=1, colspan=1, bbox=[1190, 310, 1440, 390], text="2.27Å", confidence=0.99),
                    OCRTableCell(row=1, col=0, rowspan=1, colspan=1, bbox=[910, 400, 1180, 480], text="A(g)의 ionization energy", confidence=0.99),
                    OCRTableCell(row=1, col=1, rowspan=1, colspan=1, bbox=[1190, 400, 1440, 480], text="5.45 eV", confidence=0.99),
                    OCRTableCell(row=2, col=0, rowspan=1, colspan=1, bbox=[910, 490, 1180, 570], text="B(g)의 electron affinity", confidence=0.99),
                    OCRTableCell(row=2, col=1, rowspan=1, colspan=1, bbox=[1190, 490, 1440, 570], text="3.39 eV", confidence=0.99),
                ],
            )
        ],
    )
    package = QuestionPackage(question_no=2, question_pages=[1], page_ranges=[QuestionPageRange(page_no=1, bbox=[800, 200, 1500, 800])], rough_text="")
    page_asset = PageAsset(
        page_no=1,
        image_path=image_path,
        thumbnail_path=image_path,
        width=1600,
        height=2000,
        pdf_width=1600.0,
        pdf_height=2000.0,
        extracted_text="",
        extracted_words=[],
        page_hash="x",
    )

    blocks, issues = builder.build(
        package=package,
        page_assets={1: page_asset},
        ocr_pages={1: ocr_page},
        crops_dir=tmp_path / "crops",
        noise_profile=None,
    )

    assert issues == []
    table_blocks = [block for block in blocks if block.table_candidate]
    assert len(table_blocks) == 1


def test_question_evidence_builder_accepts_dense_lookup_grid_table(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (1600, 2000), "white").save(image_path)
    builder = QuestionEvidenceBuilder()
    ocr_page = NormalizedOCRPage(
        page_no=1,
        image_path=str(image_path),
        width=1600,
        height=2000,
        lines=[],
        tables=[
            OCRTable(
                table_id="t1",
                bbox=[100, 300, 800, 500],
                confidence=0.99,
                n_rows=2,
                n_cols=4,
                cells=[
                    OCRTableCell(row=0, col=0, rowspan=1, colspan=1, bbox=[110, 310, 240, 390], text="원소", confidence=0.99),
                    OCRTableCell(row=0, col=1, rowspan=1, colspan=1, bbox=[250, 310, 380, 390], text="Fe", confidence=0.99),
                    OCRTableCell(row=0, col=2, rowspan=1, colspan=1, bbox=[390, 310, 520, 390], text="Co", confidence=0.99),
                    OCRTableCell(row=0, col=3, rowspan=1, colspan=1, bbox=[530, 310, 660, 390], text="Ni", confidence=0.99),
                    OCRTableCell(row=1, col=0, rowspan=1, colspan=1, bbox=[110, 400, 240, 480], text="원자번호", confidence=0.99),
                    OCRTableCell(row=1, col=1, rowspan=1, colspan=1, bbox=[250, 400, 380, 480], text="26", confidence=0.99),
                    OCRTableCell(row=1, col=2, rowspan=1, colspan=1, bbox=[390, 400, 520, 480], text="27", confidence=0.99),
                    OCRTableCell(row=1, col=3, rowspan=1, colspan=1, bbox=[530, 400, 660, 480], text="28", confidence=0.99),
                ],
            )
        ],
    )
    package = QuestionPackage(question_no=3, question_pages=[1], page_ranges=[QuestionPageRange(page_no=1, bbox=[0, 0, 1200, 1000])], rough_text="")
    page_asset = PageAsset(
        page_no=1,
        image_path=image_path,
        thumbnail_path=image_path,
        width=1600,
        height=2000,
        pdf_width=1600.0,
        pdf_height=2000.0,
        extracted_text="",
        extracted_words=[],
        page_hash="x",
    )

    blocks, issues = builder.build(
        package=package,
        page_assets={1: page_asset},
        ocr_pages={1: ocr_page},
        crops_dir=tmp_path / "crops",
        noise_profile=None,
    )

    assert issues == []
    assert any(block.table_candidate for block in blocks)
