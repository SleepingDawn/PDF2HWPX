from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import opendataloader_pdf

from src.models.common import PageAsset
from src.models.evidence import AnchorCandidate, QuestionPageRange
from src.utils.bbox import contains, intersects


QUESTION_PATTERN = re.compile(r"^(\d+)\.\s+\S")


@dataclass
class OdlElement:
    page_no: int
    kind: str
    bbox_pdf: list[float]
    bbox_px: list[int]
    content: str
    order_index: int
    source_type: str
    children: list["OdlElement"] = field(default_factory=list)


@dataclass
class OdlDocument:
    json_path: str
    markdown_path: str | None
    page_elements: dict[int, list[OdlElement]] = field(default_factory=dict)


class OpenDataLoaderLayoutAdapter:
    def __init__(self, config: dict[str, Any]) -> None:
        self.enabled = bool(config.get("enabled", False))
        self.include_header_footer = bool(config.get("include_header_footer", False))
        self.reading_order = config.get("reading_order")

    def analyze_pdf(self, pdf_path: Path, output_dir: Path, page_assets: dict[int, PageAsset]) -> OdlDocument | None:
        if not self.enabled:
            return None
        output_dir.mkdir(parents=True, exist_ok=True)
        opendataloader_pdf.convert(
            input_path=[str(pdf_path)],
            output_dir=str(output_dir),
            format="json,markdown",
            include_header_footer=self.include_header_footer,
            reading_order=self.reading_order,
        )
        json_path = output_dir / f"{pdf_path.stem}.json"
        markdown_path = output_dir / f"{pdf_path.stem}.md"
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        page_elements = self._extract_page_elements(payload.get("kids", []), page_assets)
        return OdlDocument(
            json_path=str(json_path),
            markdown_path=str(markdown_path) if markdown_path.exists() else None,
            page_elements=page_elements,
        )

    def collect_question_anchor_candidates(self, document: OdlDocument, question_pages: list[int]) -> dict[int, list[AnchorCandidate]]:
        candidates: dict[int, list[AnchorCandidate]] = {}
        for page_no in question_pages:
            for element in document.page_elements.get(page_no, []):
                match = QUESTION_PATTERN.match(element.content.strip())
                if not match:
                    continue
                candidates.setdefault(page_no, []).append(
                    AnchorCandidate(
                        text=element.content.strip(),
                        bbox=element.bbox_px,
                        score=0.92,
                    )
                )
        return candidates

    def collect_question_text(self, document: OdlDocument, page_ranges: list[QuestionPageRange]) -> str:
        texts: list[str] = []
        for page_range in page_ranges:
            for element in document.page_elements.get(page_range.page_no, []):
                if not element.content.strip():
                    continue
                if contains(page_range.bbox, element.bbox_px, margin=6) or intersects(page_range.bbox, element.bbox_px):
                    texts.append(element.content.strip())
        return "\n".join(texts)

    def _extract_page_elements(self, roots: list[dict[str, Any]], page_assets: dict[int, PageAsset]) -> dict[int, list[OdlElement]]:
        page_elements: dict[int, list[OdlElement]] = {}
        order_index = 0

        def walk(node: Any, inherited_region: str | None = None) -> None:
            nonlocal order_index
            if not isinstance(node, dict):
                return
            source_type = str(node.get("type", ""))
            region = inherited_region
            if source_type in {"header", "footer"}:
                region = source_type
            page_no = int(node.get("page number") or 0)
            bbox_pdf = node.get("bounding box")
            content = str(node.get("content") or "").strip()
            if page_no and isinstance(bbox_pdf, list) and len(bbox_pdf) == 4 and page_no in page_assets:
                page_elements.setdefault(page_no, []).append(
                    OdlElement(
                        page_no=page_no,
                        kind=region or source_type,
                        bbox_pdf=[float(value) for value in bbox_pdf],
                        bbox_px=self._bbox_to_pixels(page_assets[page_no], bbox_pdf),
                        content=content,
                        order_index=order_index,
                        source_type=source_type,
                    )
                )
                order_index += 1
            for key in ["kids", "list items", "rows", "cells"]:
                value = node.get(key)
                if isinstance(value, list):
                    for child in value:
                        walk(child, region)

        for root in roots:
            walk(root)

        filtered: dict[int, list[OdlElement]] = {}
        for page_no, elements in page_elements.items():
            filtered[page_no] = [
                element
                for element in sorted(elements, key=lambda item: item.order_index)
                if element.kind not in {"header", "footer"} and element.source_type not in {"header", "footer"}
            ]
        return filtered

    def _bbox_to_pixels(self, page: PageAsset, bbox_pdf: list[float]) -> list[int]:
        left, bottom, right, top = bbox_pdf
        scale_x = page.width / max(page.pdf_width, 1.0)
        scale_y = page.height / max(page.pdf_height, 1.0)
        x0 = int(round(left * scale_x))
        x1 = int(round(right * scale_x))
        y0 = int(round(page.height - (top * scale_y)))
        y1 = int(round(page.height - (bottom * scale_y)))
        return [max(0, x0), max(0, y0), min(page.width, x1), min(page.height, y1)]
