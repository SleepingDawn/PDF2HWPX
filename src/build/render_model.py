from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.utils.types import AnswerNote, Question


@dataclass
class RenderDocument:
    title: str
    questions: list[Question]
    notes: dict[int, AnswerNote]
    media_paths: list[Path] = field(default_factory=list)
