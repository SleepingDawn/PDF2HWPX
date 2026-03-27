from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BlockTypingDecision:
    block_id: str
    final_type: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    needs_review: bool = False
