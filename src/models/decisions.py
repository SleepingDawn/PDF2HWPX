from __future__ import annotations

from dataclasses import dataclass, field

from src.models.common import BBox


@dataclass
class ExamMetaDecision:
    source_pdf: str
    basename: str
    year: str | None = None
    school: str | None = None
    grade: str | None = None
    semester: str | None = None
    exam_type: str | None = None
    subject: str | None = None
    tagline: str | None = None
    field_sources: dict[str, str] = field(default_factory=dict)
    confidence: float = 0.0
    needs_review: bool = False


@dataclass
class SectionSplitDecision:
    has_answer_section: bool
    question_pages: list[int]
    answer_pages: list[int]
    split_page: int | None
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_review: bool = False


@dataclass
class QuestionAnchor:
    question_no: int
    page_no: int
    bbox: BBox


@dataclass
class QuestionAnchorDecision:
    question_anchors: list[QuestionAnchor] = field(default_factory=list)
    sequence_ok: bool = True
    missing_numbers: list[int] = field(default_factory=list)
    uncertain_anchors: list[int] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class FormulaRepairDecision:
    block_id: str
    kind: str
    normalized_repr: str
    target_repr_type: str
    target_repr: str
    confidence: float
    flags: list[str] = field(default_factory=list)
    needs_review: bool = False


@dataclass
class NoteSpan:
    question_no: int
    start_block_id: str
    end_block_id: str


@dataclass
class AnswerAlignmentDecision:
    note_map: list[NoteSpan] = field(default_factory=list)
    missing_notes: list[int] = field(default_factory=list)
    extra_notes: list[int] = field(default_factory=list)
    confidence: float = 0.0
    needs_review: bool = False


@dataclass
class QATriageDecision:
    document_status: str
    issues: list[dict] = field(default_factory=list)
