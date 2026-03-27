from __future__ import annotations

from pydantic import BaseModel, Field

from src.agents.llm_runner import AgentLLMRunner, decision_payload, ensure_runner_available, runner_is_strict
from src.agents.prompt_registry import get_agent_prompt
from src.models.decisions import QuestionAnchor, QuestionAnchorDecision
from src.models.evidence import PageEvidence


class _QuestionSplitAnchorPayload(BaseModel):
    question_no: int
    page_no: int
    bbox: list[int] = Field(min_length=4, max_length=4)


class _QuestionSplitDecisionPayload(BaseModel):
    question_anchors: list[_QuestionSplitAnchorPayload]
    sequence_ok: bool
    missing_numbers: list[int]
    uncertain_anchors: list[int]
    confidence: float


class QuestionSplitAgent:
    prompt_name = "question_split_agent"

    def __init__(self, runner: AgentLLMRunner | None = None) -> None:
        self.prompt = get_agent_prompt(self.prompt_name)
        self.runner = runner

    def resolve(self, page_evidences: list[PageEvidence], question_pages: list[int], fallback: QuestionAnchorDecision) -> QuestionAnchorDecision:
        ensure_runner_available(self.runner, self.prompt_name)
        filtered = QuestionAnchorDecision(
            question_anchors=[
                anchor
                for anchor in fallback.question_anchors
                if anchor.question_no > 0 and anchor.page_no in question_pages
            ],
            sequence_ok=fallback.sequence_ok,
            missing_numbers=list(fallback.missing_numbers),
            uncertain_anchors=list(fallback.uncertain_anchors),
            confidence=fallback.confidence,
        )
        return self._try_llm(page_evidences, question_pages, filtered) or filtered

    def _try_llm(self, page_evidences: list[PageEvidence], question_pages: list[int], fallback: QuestionAnchorDecision) -> QuestionAnchorDecision | None:
        if not self.runner:
            return None
        result = None
        try:
            result = self.runner.complete_structured(
                agent_name=self.prompt_name,
                prompt=self.prompt,
                payload={
                    "question_pages": question_pages,
                    "page_evidences": [decision_payload(evidence) for evidence in page_evidences],
                    "fallback": decision_payload(fallback),
                },
                schema=_QuestionSplitDecisionPayload,
            )
        except Exception:
            if runner_is_strict(self.runner):
                raise
            result = None
        if not result:
            try:
                result = self.runner.complete_json(
                    agent_name=self.prompt_name,
                    prompt=self.prompt,
                    payload={
                        "question_pages": question_pages,
                        "page_evidences": [decision_payload(evidence) for evidence in page_evidences],
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
        anchors = [
            QuestionAnchor(
                question_no=int(anchor["question_no"]),
                page_no=int(anchor["page_no"]),
                bbox=[int(value) for value in anchor["bbox"]],
            )
            for anchor in result.get("question_anchors", [])
            if int(anchor.get("question_no", 0)) > 0
        ]
        return QuestionAnchorDecision(
            question_anchors=anchors or fallback.question_anchors,
            sequence_ok=bool(result.get("sequence_ok", fallback.sequence_ok)),
            missing_numbers=[int(number) for number in result.get("missing_numbers", fallback.missing_numbers)],
            uncertain_anchors=[int(number) for number in result.get("uncertain_anchors", fallback.uncertain_anchors)],
            confidence=float(result.get("confidence", fallback.confidence)),
        )
