from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.models.common import Issue, PageAsset, RunPaths
from src.models.decisions import AnswerAlignmentDecision, ExamMetaDecision, QuestionAnchorDecision, SectionSplitDecision
from src.models.evidence import DocumentNoiseProfile, PageEvidence, QuestionPackage
from src.models.ocr import NormalizedOCRPage
from src.models.render import AnswerNoteRenderModel, QuestionRenderModel


@dataclass
class PipelineState:
    input_pdf: Path
    config: dict[str, Any]
    run_id: str
    paths: RunPaths
    page_assets: dict[int, PageAsset] = field(default_factory=dict)
    ocr_pages: dict[int, NormalizedOCRPage] = field(default_factory=dict)
    noise_profile: DocumentNoiseProfile | None = None
    opendataloader_doc: Any | None = None
    page_evidences: dict[int, PageEvidence] = field(default_factory=dict)
    exam_meta: ExamMetaDecision | None = None
    section_split: SectionSplitDecision | None = None
    question_anchors: QuestionAnchorDecision | None = None
    answer_alignment: AnswerAlignmentDecision | None = None
    question_packages: list[QuestionPackage] = field(default_factory=list)
    question_models: list[QuestionRenderModel] = field(default_factory=list)
    answer_notes: dict[int, AnswerNoteRenderModel] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)
