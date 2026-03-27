from src.agents.block_typing_agent import BlockTypingAgent
from src.models.evidence import BlockTypeCandidate


def test_block_typing_agent_prefers_text_for_prose_with_inline_ions() -> None:
    decision = BlockTypingAgent().resolve(
        block_id="q1_b2",
        ocr_text="(1) Rutherford experiment에서 a particles(He2+)를 향해 설명하시오.",
        type_candidates=[
            BlockTypeCandidate(type="equation", score=0.74),
            BlockTypeCandidate(type="text", score=0.3),
        ],
        surrounding_text="다음 물음을 보고 서술하시오.",
        has_table_lines=False,
        has_image_texture=False,
    )

    assert decision.final_type == "text"
