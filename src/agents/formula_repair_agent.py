from __future__ import annotations

import re

from src.agents.llm_runner import AgentLLMRunner, decision_payload, ensure_runner_available, runner_is_strict
from src.agents.prompt_registry import get_agent_prompt
from src.models.decisions import FormulaRepairDecision
from src.normalize.chem_normalizer import normalize_chem_equation
from src.normalize.formula_normalizer import normalize_formula


CHEM_TOKEN = re.compile(r"([A-Z][a-z]?)(\d+)")


class FormulaRepairAgent:
    prompt_name = "formula_repair_agent"

    def __init__(self, runner: AgentLLMRunner | None = None) -> None:
        self.prompt = get_agent_prompt(self.prompt_name)
        self.runner = runner

    def resolve(self, block_id: str, block_type: str, ocr_text: str) -> FormulaRepairDecision:
        ensure_runner_available(self.runner, self.prompt_name)
        if block_type == "chem_equation":
            normalized, valid = normalize_chem_equation(ocr_text)
            target = CHEM_TOKEN.sub(r"\1_{\2}", normalized).replace("->", " rightarrow ")
            flags = ["subscript_inferred"] if target != normalized else []
            fallback = FormulaRepairDecision(
                block_id=block_id,
                kind="chem_equation",
                normalized_repr=normalized,
                target_repr_type="hancom_equation_source",
                target_repr=target.strip(),
                confidence=0.83 if valid else 0.4,
                flags=flags,
                needs_review=not valid,
            )
            return self._try_llm(block_id, block_type, ocr_text, fallback) or fallback

        normalized, valid = normalize_formula(ocr_text)
        fallback = FormulaRepairDecision(
            block_id=block_id,
            kind="equation",
            normalized_repr=normalized,
            target_repr_type="hancom_equation_source",
            target_repr=normalized,
            confidence=0.84 if valid else 0.42,
            flags=[],
            needs_review=not valid,
        )
        return self._try_llm(block_id, block_type, ocr_text, fallback) or fallback

    def _try_llm(self, block_id: str, block_type: str, ocr_text: str, fallback: FormulaRepairDecision) -> FormulaRepairDecision | None:
        if not self.runner:
            return None
        try:
            result = self.runner.complete_json(
                agent_name=self.prompt_name,
                prompt=self.prompt,
                payload={
                    "block_id": block_id,
                    "block_type": block_type,
                    "ocr_text": ocr_text,
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
        return FormulaRepairDecision(
            block_id=block_id,
            kind=result.get("kind", fallback.kind),
            normalized_repr=result.get("normalized_repr", fallback.normalized_repr),
            target_repr_type=result.get("target_repr_type", fallback.target_repr_type),
            target_repr=result.get("target_repr", fallback.target_repr),
            confidence=float(result.get("confidence", fallback.confidence)),
            flags=list(result.get("flags", fallback.flags)),
            needs_review=bool(result.get("needs_review", fallback.needs_review)),
        )
