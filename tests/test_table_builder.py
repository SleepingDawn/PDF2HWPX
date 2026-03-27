from __future__ import annotations

from src.executors.table_builder import TableBuilder


def test_table_builder_returns_none_when_only_fake_grid_would_be_invented() -> None:
    table_object, stable = TableBuilder().build(
        table_id="tbl1",
        bbox=[0, 0, 100, 100],
        ocr_tables=[],
    )

    assert table_object is None
    assert stable is False


def test_table_builder_rejects_sparse_clova_table() -> None:
    table_object, stable = TableBuilder().build(
        table_id="tbl2",
        bbox=[0, 0, 100, 100],
        ocr_tables=[
            {
                "bbox": [0, 0, 100, 100],
                "n_rows": 4,
                "n_cols": 3,
                "cells": [
                    {"row": 0, "col": 0, "text": "A"},
                    {"row": 0, "col": 1, "text": ""},
                    {"row": 0, "col": 2, "text": ""},
                    {"row": 1, "col": 0, "text": "B"},
                    {"row": 1, "col": 1, "text": ""},
                    {"row": 1, "col": 2, "text": ""},
                    {"row": 2, "col": 0, "text": "C"},
                    {"row": 2, "col": 1, "text": ""},
                    {"row": 2, "col": 2, "text": ""},
                    {"row": 3, "col": 0, "text": "D"},
                    {"row": 3, "col": 1, "text": ""},
                    {"row": 3, "col": 2, "text": ""},
                ],
            }
        ],
    )

    assert table_object is None
    assert stable is False
