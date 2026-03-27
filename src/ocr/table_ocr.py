from __future__ import annotations

from src.utils.bbox import box_area, intersection
from src.utils.types import TableCell, TableObject


def build_simple_table(table_id: str, rows: list[list[str]]) -> TableObject:
    cells: list[TableCell] = []
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(rows[row_index]):
            cells.append(
                TableCell(
                    row=row_index,
                    col=col_index,
                    rowspan=1,
                    colspan=1,
                    content=[{"type": "text", "text": value}],
                )
            )
    return TableObject(table_id=table_id, n_rows=len(rows), n_cols=max((len(row) for row in rows), default=0), cells=cells)


def _overlap_ratio(box_a: list[int], box_b: list[int]) -> float:
    inter_area = box_area(intersection(box_a, box_b))
    if inter_area <= 0:
        return 0.0
    return inter_area / max(1, min(box_area(box_a), box_area(box_b)))


def _table_from_clova(table_id: str, ocr_tables: list[dict], bbox: list[int]) -> TableObject | None:
    best = None
    best_score = -1.0
    best_area_delta = None
    for table in ocr_tables:
        score = _overlap_ratio(table.get("bbox", [0, 0, 0, 0]), bbox)
        area_delta = abs(box_area(table.get("bbox", [0, 0, 0, 0])) - box_area(bbox))
        if score > best_score or (score == best_score and (best_area_delta is None or area_delta < best_area_delta)):
            best = table
            best_score = score
            best_area_delta = area_delta
    if not best or best_score < 0.45:
        return None
    cells = [
        TableCell(
            row=int(cell.get("row", 0)),
            col=int(cell.get("col", 0)),
            rowspan=int(cell.get("rowspan", 1)),
            colspan=int(cell.get("colspan", 1)),
            content=[{"type": "text", "text": (cell.get("text") or "").strip()}],
        )
        for cell in best.get("cells", [])
    ]
    if not cells:
        return None
    table_object = TableObject(
        table_id=table_id,
        n_rows=int(best.get("n_rows", 0)) or 1,
        n_cols=int(best.get("n_cols", 0)) or 1,
        cells=cells,
    )
    if not _is_reliable_table(table_object):
        return None
    return table_object


def _is_reliable_table(table: TableObject) -> bool:
    if table.n_rows <= 0 or table.n_cols <= 0:
        return False
    if table.n_rows == 1 and table.n_cols == 1:
        return False
    filled = 0
    nonempty_rows: set[int] = set()
    nonempty_cols: set[int] = set()
    for cell in table.cells:
        fragments = [fragment.get("text", "").strip() for fragment in cell.content if isinstance(fragment, dict)]
        if any(fragment for fragment in fragments):
            filled += 1
            nonempty_rows.add(cell.row)
            nonempty_cols.add(cell.col)
    if filled == 0 or len(table.cells) < max(2, min(4, table.n_rows * table.n_cols)):
        return False
    fill_ratio = filled / max(1, len(table.cells))
    if fill_ratio < 0.6:
        return False
    row_coverage = len(nonempty_rows) / max(1, table.n_rows)
    if row_coverage < 0.75:
        return False
    if table.n_cols > 1:
        col_coverage = len(nonempty_cols) / max(1, table.n_cols)
        if col_coverage < 0.75:
            return False
    return True


def extract_table_from_page(table_id: str, bbox: list[int], ocr_tables: list[dict] | None = None) -> tuple[TableObject | None, bool]:
    clova_table = _table_from_clova(table_id, ocr_tables or [], bbox)
    if clova_table is not None:
        return clova_table, True
    return None, False
