from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

from src.utils.io import ensure_dir


@dataclass
class RenderedPage:
    page_no: int
    image_path: Path
    width: int
    height: int
    pdf_width: float
    pdf_height: float
    text: str
    words: list[dict]


def _word_to_dict(word: tuple[float, float, float, float, str, int, int, int], scale_x: float, scale_y: float) -> dict:
    x0, y0, x1, y1, text, block_no, line_no, word_no = word
    return {
        "bbox": [int(x0 * scale_x), int(y0 * scale_y), int(x1 * scale_x), int(y1 * scale_y)],
        "text": text,
        "block_no": block_no,
        "line_no": line_no,
        "word_no": word_no,
    }


def render_pages(document: fitz.Document, output_dir: Path, dpi: int = 220) -> list[RenderedPage]:
    ensure_dir(output_dir)
    pages: list[RenderedPage] = []
    matrix = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    for index, page in enumerate(document, start=1):
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        image_path = output_dir / f"page_{index:03d}.png"
        pixmap.save(image_path)
        scale_x = pixmap.width / max(1.0, float(page.rect.width))
        scale_y = pixmap.height / max(1.0, float(page.rect.height))
        words = [_word_to_dict(word, scale_x, scale_y) for word in page.get_text("words")]
        pages.append(
            RenderedPage(
                page_no=index,
                image_path=image_path,
                width=pixmap.width,
                height=pixmap.height,
                pdf_width=float(page.rect.width),
                pdf_height=float(page.rect.height),
                text=page.get_text("text"),
                words=words,
            )
        )
    return pages
