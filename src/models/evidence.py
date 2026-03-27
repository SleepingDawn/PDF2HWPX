from __future__ import annotations

from dataclasses import dataclass, field

from src.models.common import BBox


@dataclass
class AnchorCandidate:
    text: str
    bbox: BBox
    score: float


@dataclass
class PageEvidence:
    page_no: int
    ocr_page_ref: str
    thumbnail_path: str
    top_lines: list[str] = field(default_factory=list)
    keyword_hits: list[str] = field(default_factory=list)
    question_anchor_candidates: list[AnchorCandidate] = field(default_factory=list)
    answer_anchor_candidates: list[AnchorCandidate] = field(default_factory=list)
    has_table_candidate: bool = False
    has_dense_handwriting: bool = False


@dataclass
class QuestionPageRange:
    page_no: int
    bbox: BBox


@dataclass
class QuestionPackage:
    question_no: int
    question_pages: list[int]
    page_ranges: list[QuestionPageRange]
    rough_text: str
    candidate_blocks: list[dict] = field(default_factory=list)
    answer_pages: list[int] = field(default_factory=list)
    note_candidate_ref: str | None = None
    state: str = "packaged"


@dataclass
class DocumentNoiseProfile:
    header_bottom: int | None = None
    footer_top: int | None = None
    header_patterns: list[str] = field(default_factory=list)
    footer_patterns: list[str] = field(default_factory=list)


@dataclass
class BlockTypeCandidate:
    type: str
    score: float


@dataclass
class BlockEvidence:
    block_id: str
    question_no: int
    page_no: int
    bbox: BBox
    crop_path: str
    ocr_text: str
    ocr_confidence: float
    type_candidates: list[BlockTypeCandidate] = field(default_factory=list)
    has_handwriting_overlap: bool = False
    table_candidate: bool = False
    coarse_ocr_text: str | None = None
    coarse_ocr_confidence: float | None = None
    ocr_engine: str = "page_ocr"
    final_type: str | None = None
    final_type_confidence: float | None = None
    needs_review: bool = False
