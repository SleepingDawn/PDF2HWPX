from __future__ import annotations

from src.ocr.table_ocr import extract_table_from_page
from src.utils.types import TableObject


class TableBuilder:
    def build(self, table_id: str, bbox: list[int], ocr_tables: list[dict]) -> tuple[TableObject | None, bool]:
        return extract_table_from_page(table_id=table_id, bbox=bbox, ocr_tables=ocr_tables)
