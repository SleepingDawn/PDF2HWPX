from src.agents.question_seg_agent import QuestionSegmentationAgent
from src.models.evidence import AnchorCandidate, PageEvidence


def test_question_segmentation_ignores_zero_and_preserves_page_order() -> None:
    agent = QuestionSegmentationAgent()
    evidences = [
        PageEvidence(
            page_no=1,
            ocr_page_ref="",
            thumbnail_path="",
            question_anchor_candidates=[
                AnchorCandidate(text="2. second", bbox=[100, 400, 300, 450], score=0.9),
                AnchorCandidate(text="1. first", bbox=[100, 100, 300, 150], score=0.9),
            ],
        ),
        PageEvidence(
            page_no=2,
            ocr_page_ref="",
            thumbnail_path="",
            question_anchor_candidates=[
                AnchorCandidate(text="0. noise", bbox=[100, 100, 300, 150], score=0.9),
                AnchorCandidate(text="3. third", bbox=[100, 200, 300, 250], score=0.9),
            ],
        ),
    ]

    decision = agent.resolve(evidences, question_pages=[1, 2])

    assert [anchor.question_no for anchor in decision.question_anchors] == [1, 2, 3]
    assert [anchor.page_no for anchor in decision.question_anchors] == [1, 1, 2]
    assert 0 not in decision.uncertain_anchors


def test_question_segmentation_does_not_fabricate_anchor_when_empty() -> None:
    agent = QuestionSegmentationAgent()

    decision = agent.resolve(
        [PageEvidence(page_no=1, ocr_page_ref="", thumbnail_path="")],
        question_pages=[1],
    )

    assert decision.question_anchors == []
