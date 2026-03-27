from __future__ import annotations

import re

from src.agents.llm_runner import AgentLLMRunner, decision_payload, ensure_runner_available, runner_is_strict
from src.agents.prompt_registry import get_agent_prompt
from src.models.decisions import SectionSplitDecision


class SectionSplitAgent:
    prompt_name = "section_split_agent"

    def __init__(self, keywords: list[str], runner: AgentLLMRunner | None = None) -> None:
        self.keywords = [keyword for keyword in keywords if keyword]
        self.prompt = get_agent_prompt(self.prompt_name)
        self.runner = runner

    def resolve(self, pages: list[dict], question_count_hint: int | None = None) -> SectionSplitDecision:
        ensure_runner_available(self.runner, self.prompt_name)
        split_page: int | None = None
        evidence: list[str] = []
        for page in pages:
            page_no = int(page["page_no"])
            text_blob = "\n".join(page.get("top_lines", []))
            keyword_hits = page.get("keyword_hits", [])
            top_keyword_hits = [keyword for keyword in keyword_hits if keyword in text_blob]
            answer_style = float(page.get("anchor_scores", {}).get("answer_style", 0.0))
            has_explicit_answer_header = "정답" in top_keyword_hits or len(set(top_keyword_hits)) >= 2
            if page_no > 1 and has_explicit_answer_header:
                split_page = page_no
                evidence.extend(f"page {page_no} top lines contain '{keyword}'" for keyword in top_keyword_hits)
                break
            if page_no > 1 and answer_style >= 0.9 and re.search(r"^\s*\d+[.)]", text_blob, flags=re.MULTILINE):
                split_page = page_no
                evidence.append(f"page {page_no} numbering resembles answer style")
                break

        if split_page is None:
            question_pages = [int(page["page_no"]) for page in pages]
            decision = SectionSplitDecision(
                has_answer_section=False,
                question_pages=question_pages,
                answer_pages=[],
                split_page=None,
                evidence=["answer section not found"],
                confidence=0.62,
                needs_review=False,
            )
            return self._try_llm(pages, question_count_hint, decision) or decision

        question_pages = [int(page["page_no"]) for page in pages if int(page["page_no"]) < split_page]
        answer_pages = [int(page["page_no"]) for page in pages if int(page["page_no"]) >= split_page]
        if not question_pages:
            question_pages = [page["page_no"] for page in pages]
            answer_pages = []
            split_page = None
        confidence = 0.97 if answer_pages else 0.62
        decision = SectionSplitDecision(
            has_answer_section=bool(answer_pages),
            question_pages=question_pages,
            answer_pages=answer_pages,
            split_page=split_page,
            evidence=evidence,
            confidence=confidence,
            needs_review=False,
        )
        return self._try_llm(pages, question_count_hint, decision) or decision

    def _try_llm(self, pages: list[dict], question_count_hint: int | None, fallback: SectionSplitDecision) -> SectionSplitDecision | None:
        if not self.runner:
            return None
        try:
            result = self.runner.complete_json(
                agent_name=self.prompt_name,
                prompt=self.prompt,
                payload={
                    "pages": pages,
                    "question_count_hint": question_count_hint,
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
        return SectionSplitDecision(
            has_answer_section=bool(result.get("has_answer_section", fallback.has_answer_section)),
            question_pages=[int(page) for page in result.get("question_pages", fallback.question_pages)],
            answer_pages=[int(page) for page in result.get("answer_pages", fallback.answer_pages)],
            split_page=result.get("split_page", fallback.split_page),
            evidence=list(result.get("evidence", fallback.evidence)),
            confidence=float(result.get("confidence", fallback.confidence)),
            needs_review=bool(result.get("needs_review", fallback.needs_review)),
        )
