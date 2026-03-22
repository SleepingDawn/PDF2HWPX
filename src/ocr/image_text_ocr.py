from __future__ import annotations

from pathlib import Path

from .text_ocr import TextOcrEngine


def ocr_image_text(image_path: Path) -> list[dict]:
    return TextOcrEngine().run(image_path)
