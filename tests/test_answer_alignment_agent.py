from __future__ import annotations

from src.agents import AnswerAlignmentAgent
from src.executors import NoteBuilder
from src.models.ocr import NormalizedOCRPage, OCRLine


def test_answer_alignment_maps_spans_and_builds_notes() -> None:
    blocks = [
        {"block_id": "a2_b1", "page_no": 2, "text": "정답 및 풀이", "bbox": [0, 0, 10, 10]},
        {"block_id": "a2_b2", "page_no": 2, "text": "1. 정답: r^2", "bbox": [0, 0, 10, 10]},
        {"block_id": "a2_b3", "page_no": 2, "text": "해설: 피타고라스", "bbox": [0, 0, 10, 10]},
        {"block_id": "a2_b4", "page_no": 2, "text": "2. 정답: 2H2O", "bbox": [0, 0, 10, 10]},
        {"block_id": "a2_b5", "page_no": 2, "text": "해설: 반응식", "bbox": [0, 0, 10, 10]},
    ]
    alignment = AnswerAlignmentAgent().resolve(blocks, [1, 2, 3])

    assert [span.question_no for span in alignment.note_map] == [1, 2]
    assert alignment.missing_notes == [3]

    ocr_page = NormalizedOCRPage(
        page_no=2,
        image_path="x",
        width=100,
        height=100,
        lines=[
            OCRLine(line_id="l1", text="정답 및 풀이", bbox=[0, 0, 10, 10], confidence=1.0),
            OCRLine(line_id="l2", text="1. 정답: r^2", bbox=[0, 0, 10, 10], confidence=1.0),
            OCRLine(line_id="l3", text="해설: 피타고라스", bbox=[0, 0, 10, 10], confidence=1.0),
            OCRLine(line_id="l4", text="2. 정답: 2H2O", bbox=[0, 0, 10, 10], confidence=1.0),
            OCRLine(line_id="l5", text="해설: 반응식", bbox=[0, 0, 10, 10], confidence=1.0),
        ],
        words=[],
        tables=[],
        raw_ref=None,
        backend="test",
    )
    notes = NoteBuilder().build([2], {2: ocr_page}, [1, 2, 3], alignment)

    assert notes[1].exists is True
    assert notes[2].exists is True
    assert notes[3].exists is False
    assert notes[3].uncertainties == ["missing_note"]
