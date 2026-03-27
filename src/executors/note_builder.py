from __future__ import annotations

import re

from src.models.decisions import AnswerAlignmentDecision
from src.models.render import AnswerNoteRenderModel
from src.models.ocr import NormalizedOCRPage


NOTE_PATTERN = re.compile(r"^\s*(\d+)[.)]\s*(.*)")


class NoteBuilder:
    def collect_blocks(self, answer_pages: list[int], ocr_pages: dict[int, NormalizedOCRPage]) -> list[dict]:
        blocks: list[dict] = []
        for page_no in answer_pages:
            for index, line in enumerate(ocr_pages[page_no].lines, start=1):
                text = line.text.strip()
                if not text:
                    continue
                blocks.append(
                    {
                        "block_id": f"a{page_no}_b{index}",
                        "page_no": page_no,
                        "text": text,
                        "bbox": line.bbox,
                    }
                )
        return blocks

    def build(
        self,
        answer_pages: list[int],
        ocr_pages: dict[int, NormalizedOCRPage],
        expected_question_numbers: list[int],
        alignment: AnswerAlignmentDecision,
    ) -> dict[int, AnswerNoteRenderModel]:
        blocks = self.collect_blocks(answer_pages, ocr_pages)
        block_index = {block["block_id"]: index for index, block in enumerate(blocks)}
        grouped: dict[int, list[str]] = {number: [] for number in expected_question_numbers}

        for span in alignment.note_map:
            if span.start_block_id not in block_index or span.end_block_id not in block_index:
                continue
            start = block_index[span.start_block_id]
            end = block_index[span.end_block_id]
            current_question: int | None = None
            for block in blocks[start : end + 1]:
                match = NOTE_PATTERN.match(block["text"])
                if match:
                    current_question = int(match.group(1))
                    remainder = match.group(2).strip()
                    if current_question == span.question_no and remainder:
                        grouped[current_question].append(remainder)
                    continue
                if current_question == span.question_no:
                    grouped.setdefault(current_question, []).append(block["text"])

        notes: dict[int, AnswerNoteRenderModel] = {}
        for question_no in expected_question_numbers:
            texts = [text for text in grouped.get(question_no, []) if text]
            notes[question_no] = AnswerNoteRenderModel(
                question_no=question_no,
                exists=bool(texts),
                blocks=[{"type": "text", "content": text} for text in texts],
                raw_text="\n".join(texts),
                has_explanation=bool(texts),
                uncertainties=["missing_note"] if question_no in alignment.missing_notes else [],
            )
        return notes
