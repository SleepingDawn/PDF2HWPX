from __future__ import annotations

from src.build.layout_planner import assign_question_starts


class LayoutPlanner:
    def __init__(self, first_page_no: int = 1) -> None:
        self.first_page_no = first_page_no

    def plan(self, questions: list) -> list[dict]:
        assign_question_starts(questions, first_page_no=self.first_page_no)
        return [
            {
                "question_no": question.question_no,
                "start_page": question.start_page,
                "start_column": question.start_column,
            }
            for question in questions
        ]
