from src.evidence import PageEvidenceBuilder
from src.models.ocr import NormalizedOCRPage, OCRLine, OCRWord


def test_page_evidence_builder_prefers_word_level_question_anchors() -> None:
    builder = PageEvidenceBuilder({"analysis": {"question_anchor_pattern": r"^\d+\.", "answer_section_keywords": []}})
    page = NormalizedOCRPage(
        page_no=1,
        image_path="page.png",
        width=2480,
        height=3505,
        lines=[
            OCRLine(
                line_id="l1",
                text="9. left question 11. right question",
                bbox=[100, 300, 2100, 350],
                confidence=0.99,
            )
        ],
        words=[
            OCRWord(word_id="w1", text="9.", bbox=[100, 300, 140, 350], confidence=1.0),
            OCRWord(word_id="w2", text="left", bbox=[150, 300, 220, 350], confidence=1.0),
            OCRWord(word_id="w3", text="question", bbox=[230, 300, 360, 350], confidence=1.0),
            OCRWord(word_id="w4", text="11.", bbox=[1300, 300, 1370, 350], confidence=1.0),
            OCRWord(word_id="w5", text="right", bbox=[1380, 300, 1460, 350], confidence=1.0),
            OCRWord(word_id="w6", text="question", bbox=[1470, 300, 1600, 350], confidence=1.0),
        ],
    )

    evidence = builder.build(page, thumbnail_path="thumb.jpg")

    assert [candidate.text for candidate in evidence.question_anchor_candidates] == ["9. left question", "11. right question"]
