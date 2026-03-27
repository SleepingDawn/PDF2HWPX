from __future__ import annotations

from dataclasses import dataclass, field

from src.models.common import BBox


@dataclass
class RenderItem:
    item_id: str
    type: str
    source_block_id: str
    content: str | None = None
    target_repr: str | None = None
    segments: list[dict[str, str]] = field(default_factory=list)
    uncertain: bool = False
    object_ref: object | None = None


@dataclass
class QuestionRenderModel:
    question_no: int
    pages: list[int]
    bbox_union: BBox
    items: list[RenderItem] = field(default_factory=list)
    tagline: str | None = None
    uncertainties: list[str] = field(default_factory=list)


@dataclass
class AnswerNoteRenderModel:
    question_no: int
    exists: bool
    blocks: list[dict] = field(default_factory=list)
    raw_text: str = ""
    has_explanation: bool = False
    uncertainties: list[str] = field(default_factory=list)
