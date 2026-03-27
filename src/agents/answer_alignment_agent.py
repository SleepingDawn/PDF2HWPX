from __future__ import annotations

import json
import re

from src.agents.llm_runner import AgentLLMRunner, decision_payload, ensure_runner_available, runner_is_strict
from src.agents.prompt_registry import get_agent_prompt
from src.models.decisions import AnswerAlignmentDecision, NoteSpan


TOP_LEVEL_NOTE_PATTERN = re.compile(r"^\s*(?:\()?(\d+)(?:\))?[.)]?\s*(.*)$")


class AnswerAlignmentAgent:
    prompt_name = "answer_alignment_agent"

    def __init__(self, runner: AgentLLMRunner | None = None) -> None:
        self.prompt = get_agent_prompt(self.prompt_name)
        self.runner = runner

    def resolve(self, answer_blocks: list[dict], expected_question_numbers: list[int]) -> AnswerAlignmentDecision:
        ensure_runner_available(self.runner, self.prompt_name)
        anchors: list[tuple[int, int]] = []
        extra_notes: list[int] = []

        for index, block in enumerate(answer_blocks):
            match = TOP_LEVEL_NOTE_PATTERN.match(block["text"])
            if not match:
                continue
            question_no = int(match.group(1))
            anchors.append((question_no, index))
            if question_no not in expected_question_numbers and question_no not in extra_notes:
                extra_notes.append(question_no)

        note_map: list[NoteSpan] = []
        seen_questions: set[int] = set()
        for anchor_index, (question_no, start_index) in enumerate(anchors):
            if question_no in seen_questions or question_no not in expected_question_numbers:
                continue
            end_index = len(answer_blocks) - 1
            if anchor_index + 1 < len(anchors):
                end_index = anchors[anchor_index + 1][1] - 1
            note_map.append(
                NoteSpan(
                    question_no=question_no,
                    start_block_id=answer_blocks[start_index]["block_id"],
                    end_block_id=answer_blocks[end_index]["block_id"],
                )
            )
            seen_questions.add(question_no)

        missing_notes = [number for number in expected_question_numbers if number not in seen_questions]
        confidence = 0.91 if not missing_notes else 0.76
        fallback = AnswerAlignmentDecision(
            note_map=note_map,
            missing_notes=missing_notes,
            extra_notes=sorted(extra_notes),
            confidence=confidence,
            needs_review=bool(missing_notes or extra_notes),
        )
        return self._try_llm(answer_blocks, expected_question_numbers, fallback) or fallback

    def _try_llm(self, answer_blocks: list[dict], expected_question_numbers: list[int], fallback: AnswerAlignmentDecision) -> AnswerAlignmentDecision | None:
        if not self.runner:
            return None
        try:
            result = self.runner.complete_json(
                agent_name=self.prompt_name,
                prompt=self.prompt,
                payload={
                    "answer_blocks": answer_blocks,
                    "expected_question_numbers": expected_question_numbers,
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
        note_map = self._coerce_note_map(result.get("note_map", []))
        return AnswerAlignmentDecision(
            note_map=note_map or fallback.note_map,
            missing_notes=[int(number) for number in result.get("missing_notes", fallback.missing_notes)],
            extra_notes=[int(number) for number in result.get("extra_notes", fallback.extra_notes)],
            confidence=float(result.get("confidence", fallback.confidence)),
            needs_review=bool(result.get("needs_review", fallback.needs_review)),
        )

    def _coerce_note_map(self, raw_note_map) -> list[NoteSpan]:
        if isinstance(raw_note_map, str):
            try:
                raw_note_map = json.loads(raw_note_map)
            except Exception:
                return []
        if not isinstance(raw_note_map, list):
            return []
        spans: list[NoteSpan] = []
        for item in raw_note_map:
            if isinstance(item, str):
                try:
                    item = json.loads(item)
                except Exception:
                    continue
            if not isinstance(item, dict):
                continue
            question_no = item.get("question_no")
            start_block_id = item.get("start_block_id")
            end_block_id = item.get("end_block_id")
            if question_no is None or not start_block_id or not end_block_id:
                continue
            spans.append(
                NoteSpan(
                    question_no=int(question_no),
                    start_block_id=str(start_block_id),
                    end_block_id=str(end_block_id),
                )
            )
        return spans
