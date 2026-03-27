from __future__ import annotations

from src.ocr.table_ocr import build_simple_table
from src.utils.types import Question, TableCell
from src.validators import collect_validation_findings


def test_collect_validation_findings_reports_multiple_categories() -> None:
    broken_table = build_simple_table("tbl1", [["A"]])
    broken_table.n_rows = 0
    questions = [
        Question(
            question_no=1,
            pages=[1],
            bbox_union=[0, 0, 10, 10],
            items=[
                {"type": "equation", "target": "plain text"},
                {"type": "chem_equation", "target": "H2O"},
                {"type": "table", "object": broken_table},
                {"type": "mystery"},
            ],
        ),
        Question(question_no=3, pages=[1], bbox_union=[0, 0, 10, 10], items=[]),
    ]

    findings = collect_validation_findings(questions)
    messages = {finding["message"] for finding in findings}

    assert "unsupported_item_type:mystery" in messages
    assert "missing_question_number" in messages
    assert "equation_missing_operator" in messages
    assert "chem_equation_missing_arrow" in messages
    assert "invalid_table_dimensions" in messages
    assert "empty_question_items:3" in messages


def test_collect_validation_findings_reports_sparse_table() -> None:
    sparse_table = build_simple_table("tbl2", [["A", "", ""], ["B", "", ""]])
    sparse_table.n_rows = 2
    sparse_table.n_cols = 3
    sparse_table.cells = [
        TableCell(row=0, col=0, rowspan=1, colspan=1, content=[{"type": "text", "text": "A"}]),
        TableCell(row=0, col=1, rowspan=1, colspan=1, content=[{"type": "text", "text": ""}]),
        TableCell(row=0, col=2, rowspan=1, colspan=1, content=[{"type": "text", "text": ""}]),
        TableCell(row=1, col=0, rowspan=1, colspan=1, content=[{"type": "text", "text": "B"}]),
        TableCell(row=1, col=1, rowspan=1, colspan=1, content=[{"type": "text", "text": ""}]),
        TableCell(row=1, col=2, rowspan=1, colspan=1, content=[{"type": "text", "text": ""}]),
    ]
    questions = [
        Question(
            question_no=1,
            pages=[1],
            bbox_union=[0, 0, 10, 10],
            items=[{"type": "table", "object": sparse_table}],
        )
    ]

    findings = collect_validation_findings(questions)
    messages = {finding["message"] for finding in findings}

    assert "sparse_table_structure" in messages
