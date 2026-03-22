from __future__ import annotations

import re

from src.utils.types import AnswerNote


def segment_answer_notes(page_texts: list[str]) -> dict[int, AnswerNote]:
    lines: list[str] = []
    for text in page_texts:
        lines.extend(text.splitlines())

    notes: dict[int, AnswerNote] = {}
    current_no: int | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current_no, buffer
        if current_no is None or not buffer:
            return
        chunk = "\n".join(buffer).strip()
        notes[current_no] = AnswerNote(
            question_no=current_no,
            exists=True,
            blocks=[{"type": "text", "content": line.strip()} for line in buffer if line.strip()],
            raw_text=chunk,
            has_explanation=("해설" in chunk or "풀이" in chunk or len(chunk) > 0),
        )
        buffer = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^(\d{1,2})(?!\d)(?:[.)])?\s*(.*)$", line)
        if match:
            candidate_no = int(match.group(1))
            remainder = match.group(2).strip()
            if 1 <= candidate_no <= 99 and (remainder or len(line) <= 4):
                flush()
                current_no = candidate_no
                if remainder:
                    buffer.append(f"{candidate_no}. {remainder}")
                else:
                    buffer.append(f"{candidate_no}.")
                continue
        if current_no is not None:
            buffer.append(line)

    flush()
    return notes
