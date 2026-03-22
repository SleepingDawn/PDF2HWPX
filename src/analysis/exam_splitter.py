from __future__ import annotations

import re


def split_question_and_answer_sections(page_texts: list[str], keywords: list[str]) -> dict:
    keywords = [keyword if isinstance(keyword, str) else " ".join(map(str, keyword)) for keyword in keywords]
    question_pages: list[int] = []
    answer_pages: list[int] = []
    split_index: int | None = None
    strong_candidates: list[int] = []
    weak_candidates: list[int] = []

    for page_no, text in enumerate(page_texts, start=1):
        lowered = text.lower()
        if page_no > 1 and any(keyword.lower() in lowered for keyword in keywords):
            numbered_answers = len(re.findall(r"^\s*\d+[.)]\s*(정답|해설|풀이)?", text, flags=re.MULTILINE))
            if "정답" in text or "정답 및 풀이" in text:
                strong_candidates.append(page_no)
            elif numbered_answers >= 3 and "- 끝 -" not in text:
                weak_candidates.append(page_no)

    if strong_candidates:
        split_index = strong_candidates[0]
    elif weak_candidates:
        split_index = weak_candidates[0]

    for page_no, _text in enumerate(page_texts, start=1):
        if split_index is None or page_no < split_index:
            question_pages.append(page_no)
        else:
            answer_pages.append(page_no)

    if not question_pages:
        question_pages = list(range(1, len(page_texts) + 1))
        answer_pages = []
        split_index = None

    return {
        "question_pages": question_pages,
        "answer_pages": answer_pages,
        "has_answer_section": bool(answer_pages),
        "split_page": split_index,
    }
