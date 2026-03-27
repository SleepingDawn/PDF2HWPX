from __future__ import annotations

import re
from pathlib import Path

from src.agents.llm_runner import AgentLLMRunner, decision_payload, ensure_runner_available, runner_is_strict
from src.agents.prompt_registry import get_agent_prompt
from src.models.decisions import ExamMetaDecision


SCHOOL_FIXTURES = {
    "세종과고": "세종과학고등학교",
    "세종과학고": "세종과학고등학교",
    "세종과학고등학교": "세종과학고등학교",
}

SUBJECT_FIXTURES = {
    "AP일반화학1": "AP 일반 화학Ⅰ",
    "AP일반화학Ⅰ": "AP 일반 화학Ⅰ",
    "AP 일반 화학1": "AP 일반 화학Ⅰ",
    "AP 일반 화학Ⅰ": "AP 일반 화학Ⅰ",
}


class ExamMetaAgent:
    prompt_name = "exam_meta_agent"

    def __init__(self, runner: AgentLLMRunner | None = None) -> None:
        self.prompt = get_agent_prompt(self.prompt_name)
        self.runner = runner

    def resolve(self, pdf_path: Path, filename_tokens: list[str], first_page_lines: list[str]) -> ExamMetaDecision:
        ensure_runner_available(self.runner, self.prompt_name)
        joined_first_page = " ".join(first_page_lines)
        basename = pdf_path.stem
        decision = ExamMetaDecision(source_pdf=str(pdf_path), basename=basename)

        year = self._find_year(filename_tokens, joined_first_page)
        if year:
            decision.year = year
            decision.field_sources["year"] = "first_page" if year in joined_first_page else "filename"

        school = self._find_school(filename_tokens, joined_first_page)
        if school:
            decision.school = school
            decision.field_sources["school"] = "first_page" if school in joined_first_page else "filename"

        grade = self._find_from_patterns([r"[123]학년"], filename_tokens, joined_first_page)
        if grade:
            decision.grade = grade
            decision.field_sources["grade"] = "first_page" if grade in joined_first_page else "filename"

        semester = self._find_from_patterns([r"[12]학기"], filename_tokens, joined_first_page)
        if semester:
            decision.semester = semester
            decision.field_sources["semester"] = "first_page" if semester in joined_first_page else "filename"

        exam_type = self._find_exam_type(filename_tokens, joined_first_page)
        if exam_type:
            decision.exam_type = exam_type
            decision.field_sources["exam_type"] = "first_page" if exam_type in joined_first_page else "filename"

        subject = self._find_subject(filename_tokens, joined_first_page)
        if subject:
            decision.subject = subject
            decision.field_sources["subject"] = "first_page" if subject in joined_first_page else "filename"

        if decision.year and decision.school and decision.grade and decision.semester and decision.exam_type:
            decision.tagline = f"({decision.year}년 {decision.school} {decision.grade} {decision.semester} {decision.exam_type})"
        decision.confidence = self._confidence(decision)
        decision.needs_review = decision.confidence < 0.7
        llm_decision = self._try_llm(pdf_path, filename_tokens, first_page_lines, decision)
        return llm_decision or decision

    def _try_llm(self, pdf_path: Path, filename_tokens: list[str], first_page_lines: list[str], fallback: ExamMetaDecision) -> ExamMetaDecision | None:
        if not self.runner:
            return None
        try:
            result = self.runner.complete_json(
                agent_name=self.prompt_name,
                prompt=self.prompt,
                payload={
                    "source_pdf": str(pdf_path),
                    "filename_tokens": filename_tokens,
                    "first_page_lines": first_page_lines,
                    "fallback": decision_payload(fallback),
                },
            )
        except Exception:
            if runner_is_strict(self.runner):
                raise
            return None
        if not result:
            if runner_is_strict(self.runner):
                raise RuntimeError(f"{self.prompt_name} returned no result in strict mode.")
            return None
        return ExamMetaDecision(
            source_pdf=str(pdf_path),
            basename=pdf_path.stem,
            year=result.get("year"),
            school=result.get("school"),
            grade=result.get("grade"),
            semester=result.get("semester"),
            exam_type=result.get("exam_type"),
            subject=result.get("subject"),
            tagline=result.get("tagline"),
            field_sources=dict(result.get("field_sources", {})),
            confidence=float(result.get("confidence", fallback.confidence)),
            needs_review=bool(result.get("needs_review", fallback.needs_review)),
        )

    def _find_year(self, filename_tokens: list[str], first_page: str) -> str | None:
        for candidate in filename_tokens + [first_page]:
            match = re.search(r"(20\d{2})", candidate)
            if match:
                return match.group(1)
        return None

    def _find_school(self, filename_tokens: list[str], first_page: str) -> str | None:
        for token in filename_tokens + [first_page]:
            for key, value in SCHOOL_FIXTURES.items():
                if key in token:
                    return value
        return None

    def _find_subject(self, filename_tokens: list[str], first_page: str) -> str | None:
        for token in filename_tokens + [first_page]:
            for key, value in SUBJECT_FIXTURES.items():
                if key in token:
                    return value
        return None

    def _find_from_patterns(self, patterns: list[str], filename_tokens: list[str], first_page: str) -> str | None:
        for pattern in patterns:
            regex = re.compile(pattern)
            for token in filename_tokens + [first_page]:
                match = regex.search(token)
                if match:
                    return match.group(0)
        return None

    def _find_exam_type(self, filename_tokens: list[str], first_page: str) -> str | None:
        for token in filename_tokens + [first_page]:
            if "기말" in token:
                return "기말"
            if "중간" in token:
                return "중간"
        return None

    def _confidence(self, decision: ExamMetaDecision) -> float:
        filled = sum(
            1
            for value in [
                decision.year,
                decision.school,
                decision.grade,
                decision.semester,
                decision.exam_type,
                decision.subject,
            ]
            if value
        )
        return round(min(0.98, filled / 6 + (0.15 if decision.tagline else 0.0)), 2)
