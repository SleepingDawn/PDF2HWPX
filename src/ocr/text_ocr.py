from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from rapidocr_onnxruntime import RapidOCR

from src.ocr.clova_ocr import ClovaOcrClient


class TextOcrEngine:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = deepcopy(config or {})
        self.backend = self._resolve_backend()
        self.force_page_ocr = bool(self.config.get("force_page_ocr", False) or self.backend == "clova")
        self.engine = RapidOCR()
        self.clova = ClovaOcrClient(self.config.get("clova", {}))

    def _resolve_backend(self) -> str:
        backend = str(self.config.get("backend", "auto")).lower()
        if backend == "auto":
            candidate = ClovaOcrClient(self.config.get("clova", {}))
            return "clova" if candidate.enabled else "rapidocr"
        return backend

    def run(self, image_path: Path) -> list[dict[str, Any]]:
        if self.backend == "clova" and self.clova.enabled:
            return self.clova.run(image_path)
        result, _ = self.engine(str(image_path))
        lines = []
        for item in result or []:
            box, text, confidence = item
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            lines.append(
                {
                    "bbox": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
                    "text": text,
                    "confidence": float(confidence),
                }
            )
        return lines
