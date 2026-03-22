from __future__ import annotations

import re
from pathlib import Path


class FormulaOcrEngine:
    def extract(self, image_path: Path, fallback_text: str = "") -> dict:
        del image_path
        text = fallback_text.strip()
        if not text:
            return {"source_repr": "latex", "source": "", "target_repr": "hancom_eq", "target": "", "confidence": 0.0}
        text = text.replace("×", "*").replace("÷", "/").replace("−", "-")
        text = re.sub(r"\s+", " ", text)
        return {
            "source_repr": "text",
            "source": text,
            "target_repr": "hancom_eq",
            "target": text,
            "confidence": 0.62,
        }
