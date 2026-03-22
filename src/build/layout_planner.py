from __future__ import annotations

from src.utils.types import Question


def assign_question_starts(questions: list[Question], first_page_no: int = 1) -> list[Question]:
    page_no = first_page_no
    column_order = ["left", "right"]
    for index, question in enumerate(questions):
        question.start_page = page_no
        question.start_column = column_order[index % 2]
        if question.start_column == "right":
            page_no += 1
    return questions
