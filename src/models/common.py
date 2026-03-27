from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


BBox = list[int]


@dataclass
class RunPaths:
    run_dir: Path
    pages_dir: Path
    thumbs_dir: Path
    ocr_dir: Path
    evidence_dir: Path
    decisions_dir: Path
    questions_dir: Path
    crops_dir: Path
    layout_dir: Path
    output_dir: Path


@dataclass
class PageAsset:
    page_no: int
    image_path: Path
    thumbnail_path: Path
    width: int
    height: int
    pdf_width: float
    pdf_height: float
    extracted_text: str
    extracted_words: list[dict]
    page_hash: str


@dataclass
class Issue:
    question_no: int | None
    block_id: str | None
    severity: str
    category: str
    message: str
    asset: str


@dataclass
class RunResult:
    hwpx_path: str
    checklist_path: str | None
    questions: int
    has_answer_section: bool
    verification: dict
    run_dir: str
    issues: list[Issue] = field(default_factory=list)
