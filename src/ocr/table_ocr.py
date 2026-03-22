from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import cv2

from src.utils.bbox import contains
from src.utils.types import TableCell, TableObject


def _dedupe_positions(values: list[int], tolerance: int = 10) -> list[int]:
    values = sorted(values)
    merged: list[int] = []
    for value in values:
        if not merged or abs(value - merged[-1]) > tolerance:
            merged.append(value)
        else:
            merged[-1] = int((merged[-1] + value) / 2)
    return merged


def _line_positions(mask, axis: str, min_length: int) -> list[int]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    positions: list[int] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if axis == "horizontal" and w >= min_length:
            positions.extend([y, y + h])
        elif axis == "vertical" and h >= min_length:
            positions.extend([x, x + w])
    return _dedupe_positions(positions)


def _grid_from_lines(image_path: Path, bbox: list[int]) -> tuple[list[int], list[int]]:
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    x0, y0, x1, y1 = bbox
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return [], []
    thresh = cv2.threshold(crop, 210, 255, cv2.THRESH_BINARY_INV)[1]
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (max(12, crop.shape[1] // 8), 1))
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(12, crop.shape[0] // 8)))
    horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_h)
    vertical = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_v)
    xs = _line_positions(vertical, "vertical", min_length=max(24, crop.shape[0] // 3))
    ys = _line_positions(horizontal, "horizontal", min_length=max(24, crop.shape[1] // 3))
    return xs, ys


def _words_in_bbox(words: list[dict], bbox: list[int]) -> list[dict]:
    return [word for word in words if contains(bbox, word["bbox"], margin=4)]


def _build_cells_from_grid(words: list[dict], bbox: list[int], xs: list[int], ys: list[int]) -> list[TableCell]:
    if len(xs) < 2 or len(ys) < 2:
        return []
    rows = len(ys) - 1
    cols = len(xs) - 1
    content_map: dict[tuple[int, int], list[str]] = defaultdict(list)
    for word in words:
        cx = (word["bbox"][0] + word["bbox"][2]) / 2 - bbox[0]
        cy = (word["bbox"][1] + word["bbox"][3]) / 2 - bbox[1]
        col = next((index for index in range(cols) if xs[index] <= cx <= xs[index + 1]), None)
        row = next((index for index in range(rows) if ys[index] <= cy <= ys[index + 1]), None)
        if row is None or col is None:
            continue
        content_map[(row, col)].append(word["text"])

    cells: list[TableCell] = []
    for row in range(rows):
        for col in range(cols):
            text = " ".join(content_map.get((row, col), []))
            cells.append(
                TableCell(
                    row=row,
                    col=col,
                    rowspan=1,
                    colspan=1,
                    content=[{"type": "text", "text": text.strip()}],
                )
            )
    return cells


def _fallback_cells(words: list[dict]) -> tuple[int, int, list[TableCell]]:
    row_map: dict[int, list[dict]] = defaultdict(list)
    for word in words:
        center_y = int((word["bbox"][1] + word["bbox"][3]) / 2)
        bucket = min(row_map.keys(), key=lambda value: abs(value - center_y)) if row_map else center_y
        if not row_map or abs(bucket - center_y) > 18:
            bucket = center_y
        row_map[bucket].append(word)

    rows_sorted = [sorted(row_words, key=lambda item: item["bbox"][0]) for _, row_words in sorted(row_map.items())]
    n_rows = len(rows_sorted)
    n_cols = max((len(row) for row in rows_sorted), default=0)
    cells: list[TableCell] = []
    for row_index, row_words in enumerate(rows_sorted):
        for col_index in range(n_cols):
            text = row_words[col_index]["text"] if col_index < len(row_words) else ""
            cells.append(
                TableCell(
                    row=row_index,
                    col=col_index,
                    rowspan=1,
                    colspan=1,
                    content=[{"type": "text", "text": text.strip()}],
                )
            )
    return n_rows, n_cols, cells


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


def extract_table_from_page(table_id: str, image_path: Path, bbox: list[int], words: list[dict]) -> tuple[TableObject, bool]:
    table_words = _words_in_bbox(words, bbox)
    xs, ys = _grid_from_lines(image_path, bbox)
    cells = _build_cells_from_grid(table_words, bbox, xs, ys)
    if cells and len(xs) >= 2 and len(ys) >= 2:
        return (
            TableObject(
                table_id=table_id,
                n_rows=len(ys) - 1,
                n_cols=len(xs) - 1,
                cells=cells,
            ),
            True,
        )

    n_rows, n_cols, fallback_cells = _fallback_cells(table_words)
    return (
        TableObject(
            table_id=table_id,
            n_rows=n_rows or 1,
            n_cols=n_cols or 1,
            cells=fallback_cells or build_simple_table(table_id, [["[불확실]"]]).cells,
        ),
        False,
    )
