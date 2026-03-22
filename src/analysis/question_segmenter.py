from __future__ import annotations

from collections import defaultdict

from src.utils.bbox import union_boxes
from src.utils.types import Question


def segment_questions(layouts: list[dict], tagline: str | None) -> list[Question]:
    anchors: list[tuple[int, int, list[int]]] = []
    for layout in layouts:
        for anchor in layout["anchors"]:
            anchors.append((anchor["question_no"], layout["page_no"], anchor["bbox"]))
    anchors.sort()

    if not anchors:
        all_boxes = [block["bbox"] for layout in layouts for block in layout["blocks"]]
        return [Question(question_no=1, pages=[layout["page_no"] for layout in layouts], bbox_union=union_boxes(all_boxes), tagline=tagline, uncertainties=["ambiguous_question_anchor"])]

    blocks_by_page = {layout["page_no"]: layout["blocks"] for layout in layouts}
    questions: list[Question] = []
    grouped_pages = defaultdict(list)
    grouped_boxes = defaultdict(list)
    for question_no, page_no, bbox in anchors:
        grouped_pages[question_no].append(page_no)
        grouped_boxes[question_no].append(bbox)
        for block in blocks_by_page.get(page_no, []):
            grouped_boxes[question_no].append(block["bbox"])

    for question_no in sorted(grouped_pages):
        question = Question(
            question_no=question_no,
            pages=sorted(set(grouped_pages[question_no])),
            bbox_union=union_boxes(grouped_boxes[question_no]),
            tagline=tagline,
        )
        questions.append(question)
    return questions
