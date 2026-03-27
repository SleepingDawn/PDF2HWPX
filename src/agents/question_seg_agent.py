from __future__ import annotations

import re

from src.agents.llm_runner import AgentLLMRunner, decision_payload, ensure_runner_available, runner_is_strict
from src.agents.prompt_registry import get_agent_prompt
from src.models.decisions import QuestionAnchor, QuestionAnchorDecision
from src.models.evidence import PageEvidence


class QuestionSegmentationAgent:
    prompt_name = "question_segmentation_agent"

    def __init__(self, expected_question_style: str = "number_dot", runner: AgentLLMRunner | None = None) -> None:
        self.expected_question_style = expected_question_style
        self.pattern = re.compile(r"^(\d+)\.")
        self.prompt = get_agent_prompt(self.prompt_name)
        self.runner = runner

    def resolve(self, page_evidences: list[PageEvidence], question_pages: list[int]) -> QuestionAnchorDecision:
        ensure_runner_available(self.runner, self.prompt_name)
        anchors: list[QuestionAnchor] = []
        for evidence in page_evidences:
            if evidence.page_no not in question_pages:
                continue
            for candidate in evidence.question_anchor_candidates:
                match = self.pattern.match(candidate.text.strip())
                if not match:
                    continue
                question_no = int(match.group(1))
                if question_no <= 0:
                    continue
                anchors.append(
                    QuestionAnchor(
                        question_no=question_no,
                        page_no=evidence.page_no,
                        bbox=candidate.bbox,
                    )
                )

        anchors.sort(key=lambda item: (item.page_no, item.bbox[1], item.bbox[0], item.question_no))
        deduped: list[QuestionAnchor] = []
        seen: set[int] = set()
        uncertain: list[int] = []
        for anchor in anchors:
            if anchor.question_no in seen:
                uncertain.append(anchor.question_no)
                continue
            deduped.append(anchor)
            seen.add(anchor.question_no)

        missing = []
        if deduped:
            expected = set(range(deduped[0].question_no, deduped[-1].question_no + 1))
            missing = sorted(expected - {anchor.question_no for anchor in deduped})

        confidence = 0.89 if deduped and not missing else 0.66
        decision = QuestionAnchorDecision(
            question_anchors=deduped,
            sequence_ok=not missing,
            missing_numbers=missing,
            uncertain_anchors=sorted(set(uncertain)),
            confidence=confidence,
        )
        return self._try_llm(page_evidences, question_pages, decision) or decision

    def _try_llm(self, page_evidences: list[PageEvidence], question_pages: list[int], fallback: QuestionAnchorDecision) -> QuestionAnchorDecision | None:
        if not self.runner:
            return None
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
        ]
        return QuestionAnchorDecision(
            question_anchors=anchors or fallback.question_anchors,
            sequence_ok=bool(result.get("sequence_ok", fallback.sequence_ok)),
            missing_numbers=[int(number) for number in result.get("missing_numbers", fallback.missing_numbers)],
            uncertain_anchors=[int(number) for number in result.get("uncertain_anchors", fallback.uncertain_anchors)],
            confidence=float(result.get("confidence", fallback.confidence)),
        )
