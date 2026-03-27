from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from src.build.render_model import RenderDocument
from src.utils.io import ensure_dir


class PdfPreviewWriter:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.page_width, self.page_height = A4
        try:
            pdfmetrics.getFont("HYSMyeongJo-Medium")
        except KeyError:
            pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
        self.font_name = "HYSMyeongJo-Medium"

    def write(self, document: RenderDocument) -> Path:
        ensure_dir(self.output_path.parent)
        pdf = canvas.Canvas(str(self.output_path), pagesize=A4)
        pdf.setTitle(document.title)
        margin_x = 42
        margin_y = 42
        cursor_y = self.page_height - margin_y
        pdf.setFont(self.font_name, 11)
        for question in document.questions:
            blocks = self._question_blocks(question)
            needed_height = self._estimate_height(blocks)
            if cursor_y - needed_height < margin_y:
                pdf.showPage()
                pdf.setFont(self.font_name, 11)
                cursor_y = self.page_height - margin_y
            pdf.setFont(self.font_name, 12)
            pdf.drawString(margin_x, cursor_y, f"문항 {question.question_no}")
            cursor_y -= 18
            pdf.setFont(self.font_name, 10)
            for block in blocks:
                if block["type"] == "image":
                    cursor_y = self._draw_image(pdf, Path(block["path"]), margin_x, cursor_y, self.page_width - margin_x * 2)
                    cursor_y -= 10
                    continue
                for line in simpleSplit(block["text"], self.font_name, 10, self.page_width - margin_x * 2):
                    if cursor_y < margin_y + 24:
                        pdf.showPage()
                        pdf.setFont(self.font_name, 10)
                        cursor_y = self.page_height - margin_y
                    pdf.drawString(margin_x, cursor_y, line)
                    cursor_y -= 14
            cursor_y -= 8
        pdf.save()
        return self.output_path

    def _question_blocks(self, question) -> list[dict]:
        blocks: list[dict] = []
        for item in question.items:
            item_type = item.get("type")
            if item_type == "image":
                image_object = item.get("object")
                blocks.append({"type": "image", "path": getattr(image_object, "clean_path", "")})
                continue
            if item_type == "table":
                table_object = item.get("object")
                cell_texts = []
                for cell in getattr(table_object, "cells", []):
                    fragments = [fragment.get("text", "") for fragment in cell.content if isinstance(fragment, dict)]
                    if fragments:
                        cell_texts.append(" ".join(part for part in fragments if part))
                blocks.append({"type": "text", "text": " | ".join(cell_texts)})
                continue
            text = item.get("target") or item.get("content") or ""
            if text:
                blocks.append({"type": "text", "text": text})
        return blocks

    def _estimate_height(self, blocks: list[dict]) -> int:
        total = 24
        for block in blocks:
            if block["type"] == "image":
                total += 180
            else:
                total += max(14, 14 * len(simpleSplit(block["text"], self.font_name, 10, self.page_width - 84)))
        return total + 24

    def _draw_image(self, pdf: canvas.Canvas, image_path: Path, x: float, cursor_y: float, max_width: float) -> float:
        if not image_path.exists():
            return cursor_y
        image = ImageReader(str(image_path))
        width, height = image.getSize()
        if not width or not height:
            return cursor_y
        scale = min(max_width / width, 180 / height, 1.0)
        draw_w = width * scale
        draw_h = height * scale
        bottom_y = cursor_y - draw_h
        if bottom_y < 42:
            pdf.showPage()
            pdf.setFont(self.font_name, 10)
            cursor_y = self.page_height - 42
            bottom_y = cursor_y - draw_h
        pdf.drawImage(image, x, bottom_y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
        return bottom_y
