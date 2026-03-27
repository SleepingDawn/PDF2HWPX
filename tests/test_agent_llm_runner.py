from __future__ import annotations

from pathlib import Path

import pytest

from src.agents import AgentLLMRunner, BlockTypingAgent, ExamMetaAgent, SectionSplitAgent


class FakeRunner:
    def __init__(self, response: dict) -> None:
        self.response = response

    def complete_json(self, **kwargs) -> dict:
        return dict(self.response)


def test_exam_meta_agent_accepts_llm_override() -> None:
    agent = ExamMetaAgent(
        FakeRunner(
            {
                "year": "2025",
                "school": "테스트고등학교",
                "grade": "2학년",
                "semester": "2학기",
                "exam_type": "중간",
                "subject": "화학",
                "tagline": "(2025년 테스트고등학교 2학년 2학기 중간)",
                "field_sources": {"year": "llm"},
                "confidence": 0.99,
                "needs_review": False,
            }
        )
    )

    decision = agent.resolve(Path("2024-세종과고-기말.pdf"), ["2024", "세종과고", "기말"], ["2024학년도 기말"])

    assert decision.year == "2025"
    assert decision.school == "테스트고등학교"
    assert decision.confidence == 0.99


def test_block_typing_agent_accepts_llm_override() -> None:
    agent = BlockTypingAgent(
        FakeRunner(
            {
                "final_type": "image",
                "confidence": 0.88,
                "reasons": ["llm override"],
                "needs_review": True,
            }
        )
    )

    decision = agent.resolve(
        block_id="b1",
        ocr_text="x^2 + y^2 = r^2",
        type_candidates=[],
        surrounding_text="",
        has_table_lines=False,
        has_image_texture=False,
    )

    assert decision.final_type == "image"
    assert decision.needs_review is True


def test_agent_llm_runner_raises_when_strict_mode_has_no_model() -> None:
    runner = AgentLLMRunner(
        {
            "enabled": False,
            "strict_mode": True,
            "base_url": "",
            "model": "",
            "api_key": "",
        }
    )

    with pytest.raises(RuntimeError):
        runner.complete_json(agent_name="exam_meta_agent", prompt="x", payload={})


def test_section_split_agent_fails_in_strict_mode_without_model() -> None:
    agent = SectionSplitAgent(
        keywords=["정답"],
        runner=AgentLLMRunner(
            {
                "enabled": False,
                "strict_mode": True,
                "base_url": "",
                "model": "",
                "api_key": "",
            }
        ),
    )

    with pytest.raises(RuntimeError):
        agent.resolve(
            [
                {
                    "page_no": 1,
                    "top_lines": ["문제"],
                    "keyword_hits": [],
                    "anchor_scores": {"question_style": 0.9, "answer_style": 0.1},
                }
            ]
        )
