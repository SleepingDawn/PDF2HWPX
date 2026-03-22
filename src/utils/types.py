from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any


def json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return {key: json_ready(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [json_ready(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass
class ChecklistIssue:
    question_no: int
    severity: str
    category: str
    message: str
    page: int
    asset: str


@dataclass
class ExamMeta:
    source_pdf: str
    basename: str
    year: str | None = None
    school: str | None = None
    grade: str | None = None
    semester: str | None = None
    exam_type: str | None = None
    subject: str | None = None
    tagline: str | None = None
    confidence: float = 0.0
    meta_source: dict[str, str] = field(default_factory=dict)


@dataclass
class TableCell:
    row: int
    col: int
    rowspan: int
    colspan: int
    content: list[dict[str, str]]


@dataclass
class TableObject:
    table_id: str
    n_rows: int
    n_cols: int
    cells: list[TableCell]
    width_policy: str = "fit_to_column"
    anchor: str = "inline_center"


@dataclass
class ImageObject:
    image_id: str
    origin_page: int
    crop_bbox: list[int]
    clean_path: str
    mask_path: str
    removed_handwriting: bool
    restoration_mode: str
    anchor: str = "inline_center"
    width_policy: str = "fit_to_column"
    uncertain: bool = False


@dataclass
class Question:
    question_no: int
    pages: list[int]
    bbox_union: list[int]
    has_note: bool = False
    note_ref_no: int | None = None
    items: list[dict[str, Any]] = field(default_factory=list)
    tagline: str | None = None
    uncertainties: list[str] = field(default_factory=list)
    start_page: int | None = None
    start_column: str | None = None


@dataclass
class AnswerNote:
    question_no: int
    exists: bool
    blocks: list[dict[str, Any]] = field(default_factory=list)
    raw_text: str = ""
    has_explanation: bool = False
    uncertainties: list[str] = field(default_factory=list)
