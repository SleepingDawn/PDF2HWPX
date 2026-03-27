from __future__ import annotations

import re
from typing import Iterable

from src.models.decisions import SectionSplitDecision
from src.models.evidence import AnchorCandidate, PageEvidence
from src.models.ocr import NormalizedOCRPage


class PageEvidenceBuilder:
    def __init__(self, config: dict) -> None:
        self.answer_keywords = list(config.get("analysis", {}).get("answer_section_keywords", []))
        self.question_pattern = re.compile(config.get("analysis", {}).get("question_anchor_pattern", r"^\d+\."))
        self.word_question_pattern = re.compile(r"^\d+\.(?!\d)")

    def build(self, ocr_page: NormalizedOCRPage, thumbnail_path: str) -> PageEvidence:
        top_lines = [line.text for line in ocr_page.lines[:5]]
        keyword_hits = sorted(self._keyword_hits(top_lines + [line.text for line in ocr_page.lines]))
        question_anchors = self._question_anchor_candidates(ocr_page)
        answer_anchors = [
            AnchorCandidate(text=line.text, bbox=line.bbox, score=max(0.5, line.confidence))
            for line in ocr_page.lines
            if any(keyword in line.text for keyword in self.answer_keywords)
        ]
        return PageEvidence(
            page_no=ocr_page.page_no,
            ocr_page_ref=ocr_page.raw_ref or "",
            thumbnail_path=thumbnail_path,
            top_lines=top_lines,
            keyword_hits=keyword_hits,
            question_anchor_candidates=question_anchors,
            answer_anchor_candidates=answer_anchors,
            has_table_candidate=bool(ocr_page.tables),
            has_dense_handwriting=False,
        )

    def to_section_page(self, evidence: PageEvidence) -> dict:
        question_style = 0.9 if evidence.question_anchor_candidates else 0.1
        answer_style = 0.95 if evidence.answer_anchor_candidates else 0.05
        return {
            "page_no": evidence.page_no,
            "top_lines": evidence.top_lines,
            "keyword_hits": evidence.keyword_hits,
            "anchor_scores": {
                "question_style": question_style,
                "answer_style": answer_style,
            },
        }

    def _keyword_hits(self, texts: Iterable[str]) -> set[str]:
        joined = "\n".join(texts)
        return {keyword for keyword in self.answer_keywords if keyword and keyword in joined}

    def _anchor_score(self, text: str, confidence: float) -> float:
        base = 0.9 if self.question_pattern.match(text.strip()) else 0.4
        return min(0.99, max(0.1, (base + confidence) / 2))

    def _question_anchor_candidates(self, ocr_page: NormalizedOCRPage) -> list[AnchorCandidate]:
        candidates: list[AnchorCandidate] = []
        for index, word in enumerate(ocr_page.words):
            if not self.word_question_pattern.match(word.text.strip()):
                continue
            snippet = self._anchor_snippet(ocr_page.words, index)
            candidates.append(
                AnchorCandidate(
                    text=snippet,
                    bbox=list(word.bbox),
                    score=self._anchor_score(snippet, word.confidence),
                )
            )
        if candidates:
            return candidates
        return [
            AnchorCandidate(text=line.text, bbox=line.bbox, score=self._anchor_score(line.text, line.confidence))
            for line in ocr_page.lines
            if self.question_pattern.match(line.text.strip())
        ]

    def _anchor_snippet(self, words: list, anchor_index: int) -> str:
        anchor = words[anchor_index]
        x0, y0, x1, y1 = anchor.bbox
        row_words = [
            word
            for word in words
            if abs(word.bbox[1] - y0) <= 28 and abs(word.bbox[3] - y1) <= 28 and word.bbox[0] >= x0 and word.bbox[0] <= x0 + 900
        ]
        row_words.sort(key=lambda item: item.bbox[0])
        tokens: list[str] = []
        prev_x1 = None
        for word in row_words:
            if prev_x1 is not None and word.bbox[0] - prev_x1 > 180:
                break
            tokens.append(word.text.strip())
            prev_x1 = word.bbox[2]
            if len(tokens) >= 10 or len(" ".join(tokens)) >= 80:
                break
        return " ".join(token for token in tokens if token).strip()
