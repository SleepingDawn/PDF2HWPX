from __future__ import annotations

from src.models.decisions import FormulaRepairDecision
from src.models.render import RenderItem


class FormulaBuilder:
    def build(self, item_id: str, source_block_id: str, decision: FormulaRepairDecision) -> RenderItem:
        return RenderItem(
            item_id=item_id,
            type=decision.kind,
            source_block_id=source_block_id,
            content=decision.normalized_repr,
            target_repr=decision.target_repr,
            uncertain=decision.needs_review,
        )
