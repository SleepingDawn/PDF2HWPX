from __future__ import annotations

from src.agents.llm_runner import AgentLLMRunner, decision_payload, ensure_runner_available, runner_is_strict
from src.agents.prompt_registry import get_agent_prompt
from src.models.block import BlockTypingDecision
from src.models.evidence import BlockTypeCandidate
from src.utils.text_analysis import looks_like_equation_line, looks_like_prose_line


class BlockTypingAgent:
    prompt_name = "block_typing_agent"

    def __init__(self, runner: AgentLLMRunner | None = None) -> None:
        self.prompt = get_agent_prompt(self.prompt_name)
        self.runner = runner

    def resolve(
        self,
        *,
        block_id: str,
        ocr_text: str,
        type_candidates: list[BlockTypeCandidate],
        surrounding_text: str,
        has_table_lines: bool,
        has_image_texture: bool,
    ) -> BlockTypingDecision:
        ensure_runner_available(self.runner, self.prompt_name)
        text = ocr_text.strip()
        candidate_map = {candidate.type: candidate.score for candidate in type_candidates}
        reasons: list[str] = []

        if has_table_lines or candidate_map.get("table", 0.0) >= 0.9:
            reasons.append("table evidence dominates the crop")
            fallback = BlockTypingDecision(block_id=block_id, final_type="table", confidence=0.96, reasons=reasons, needs_review=False)
            return self._try_llm(block_id, ocr_text, type_candidates, surrounding_text, has_table_lines, has_image_texture, fallback) or fallback

        if candidate_map.get("image", 0.0) >= 0.9:
            reasons.append("image candidate score is dominant")
            fallback = BlockTypingDecision(block_id=block_id, final_type="image", confidence=0.92, reasons=reasons, needs_review=False)
            return self._try_llm(block_id, ocr_text, type_candidates, surrounding_text, has_table_lines, has_image_texture, fallback) or fallback

        chemistry_context = any(token in surrounding_text for token in ["반응식", "화학식", "화학 반응", "다음 식"])
        if any(token in text for token in ["->", "→", "⇌", "<=>"]) and any(char.isupper() for char in text):
            reasons.append("reaction arrow token detected")
            if chemistry_context:
                reasons.append("surrounding context indicates chemistry")
            fallback = BlockTypingDecision(
                block_id=block_id,
                final_type="chem_equation",
                confidence=0.9 if chemistry_context else 0.84,
                reasons=reasons,
                needs_review=False,
            )
            return self._try_llm(block_id, ocr_text, type_candidates, surrounding_text, has_table_lines, has_image_texture, fallback) or fallback

        if looks_like_prose_line(text):
            reasons.append("line looks like prose despite inline symbols")
            fallback = BlockTypingDecision(block_id=block_id, final_type="text", confidence=0.9, reasons=reasons, needs_review=False)
            return self._try_llm(block_id, ocr_text, type_candidates, surrounding_text, has_table_lines, has_image_texture, fallback) or fallback

        if looks_like_equation_line(text) and len(text) < 180:
            reasons.append("equation-like symbols detected")
            fallback = BlockTypingDecision(block_id=block_id, final_type="equation", confidence=0.82, reasons=reasons, needs_review=False)
            return self._try_llm(block_id, ocr_text, type_candidates, surrounding_text, has_table_lines, has_image_texture, fallback) or fallback

        if has_image_texture:
            reasons.append("image texture requested by upstream signal")
            fallback = BlockTypingDecision(block_id=block_id, final_type="image", confidence=0.75, reasons=reasons, needs_review=True)
            return self._try_llm(block_id, ocr_text, type_candidates, surrounding_text, has_table_lines, has_image_texture, fallback) or fallback

        if not text:
            reasons.append("crop OCR is empty")
            fallback = BlockTypingDecision(block_id=block_id, final_type="unknown", confidence=0.2, reasons=reasons, needs_review=True)
            return self._try_llm(block_id, ocr_text, type_candidates, surrounding_text, has_table_lines, has_image_texture, fallback) or fallback

        top = max(type_candidates, key=lambda item: item.score, default=BlockTypeCandidate(type="text", score=0.5))
        reasons.append("defaulting to strongest remaining candidate")
        fallback = BlockTypingDecision(
            block_id=block_id,
            final_type=top.type,
            confidence=max(0.55, top.score),
            reasons=reasons,
            needs_review=top.score < 0.7,
        )
        return self._try_llm(block_id, ocr_text, type_candidates, surrounding_text, has_table_lines, has_image_texture, fallback) or fallback

    def _try_llm(self, block_id: str, ocr_text: str, type_candidates: list[BlockTypeCandidate], surrounding_text: str, has_table_lines: bool, has_image_texture: bool, fallback: BlockTypingDecision) -> BlockTypingDecision | None:
        if not self.runner:
            return None
        try:
            result = self.runner.complete_json(
                agent_name=self.prompt_name,
                prompt=self.prompt,
                payload={
                    "block_id": block_id,
                    "ocr_text": ocr_text,
                    "type_candidates": [decision_payload(candidate) for candidate in type_candidates],
                    "surrounding_text": surrounding_text,
                    "has_table_lines": has_table_lines,
                    "has_image_texture": has_image_texture,
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
        return BlockTypingDecision(
            block_id=block_id,
            final_type=result.get("final_type", fallback.final_type),
            confidence=float(result.get("confidence", fallback.confidence)),
            reasons=list(result.get("reasons", fallback.reasons)),
            needs_review=bool(result.get("needs_review", fallback.needs_review)),
        )
