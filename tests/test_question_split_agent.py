from src.agents.question_split_agent import QuestionSplitAgent
from src.models.decisions import QuestionAnchor, QuestionAnchorDecision
from src.models.evidence import PageEvidence


def test_question_split_agent_keeps_fallback_order_without_llm() -> None:
    agent = QuestionSplitAgent()
    fallback = QuestionAnchorDecision(
        question_anchors=[
            QuestionAnchor(question_no=2, page_no=1, bbox=[1400, 200, 1800, 260]),
            QuestionAnchor(question_no=1, page_no=1, bbox=[150, 900, 900, 980]),
            QuestionAnchor(question_no=3, page_no=2, bbox=[160, 250, 900, 320]),
            QuestionAnchor(question_no=5, page_no=2, bbox=[1400, 600, 1850, 660]),
            QuestionAnchor(question_no=4, page_no=2, bbox=[170, 1200, 920, 1270]),
        ],
        sequence_ok=False,
        missing_numbers=[],
        uncertain_anchors=[],
        confidence=0.66,
    )

    result = agent.resolve(
        page_evidences=[
            PageEvidence(page_no=1, ocr_page_ref="", thumbnail_path=""),
            PageEvidence(page_no=2, ocr_page_ref="", thumbnail_path=""),
        ],
        question_pages=[1, 2],
        fallback=fallback,
    )

    assert [anchor.question_no for anchor in result.question_anchors] == [2, 1, 3, 5, 4]
    assert result.sequence_ok is False
