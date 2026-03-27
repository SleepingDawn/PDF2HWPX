from src.agents.section_split_agent import SectionSplitAgent


def test_section_split_uses_top_line_keywords_for_answer_pages() -> None:
    agent = SectionSplitAgent(keywords=["정답", "풀이"])

    decision = agent.resolve(
        [
            {
                "page_no": 1,
                "top_lines": ["문항 시작", "1. 다음 물음을 풀고 풀이 과정을 쓰시오."],
                "keyword_hits": ["풀이"],
                "anchor_scores": {"question_style": 0.9, "answer_style": 0.95},
            },
            {
                "page_no": 8,
                "top_lines": ["정답과 풀이", "<서술형>"],
                "keyword_hits": ["정답", "풀이"],
                "anchor_scores": {"question_style": 0.1, "answer_style": 0.95},
            },
        ]
    )

    assert decision.has_answer_section is True
    assert decision.split_page == 8
    assert decision.question_pages == [1]
    assert decision.answer_pages == [8]
