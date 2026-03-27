from __future__ import annotations

from dataclasses import dataclass, field

from src.models.common import BBox


@dataclass
class OCRLine:
    line_id: str
    text: str
    bbox: BBox
    confidence: float


@dataclass
class OCRWord:
    word_id: str
    text: str
    bbox: BBox
    confidence: float


@dataclass
class OCRTableCell:
    row: int
    col: int
    rowspan: int
    colspan: int
    bbox: BBox
    text: str
    confidence: float


@dataclass
class OCRTable:
    table_id: str
    bbox: BBox
    confidence: float
    n_rows: int = 0
    n_cols: int = 0
    cells: list[OCRTableCell] = field(default_factory=list)


@dataclass
class NormalizedOCRPage:
    page_no: int
    image_path: str
    width: int
    height: int
    lines: list[OCRLine] = field(default_factory=list)
    words: list[OCRWord] = field(default_factory=list)
    tables: list[OCRTable] = field(default_factory=list)
    raw_ref: str | None = None
    backend: str = "clova_general"
