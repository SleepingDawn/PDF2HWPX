from __future__ import annotations

import base64
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests


class ClovaOcrClient:
    def __init__(self, config: dict[str, Any]) -> None:
        raw_invoke_url = config.get("invoke_url") or os.getenv("CLOVA_OCR_INVOKE_URL", "")
        self.invoke_url = self._normalize_invoke_url(raw_invoke_url)
        self.secret_key = config.get("secret_key") or os.getenv("CLOVA_OCR_SECRET", "")
        self.version = config.get("version", "V2")
        self.language = config.get("language", "ko")
        self.timeout_seconds = int(config.get("timeout_seconds", 60))
        self.table_detection = bool(config.get("table_detection", True))

    @property
    def enabled(self) -> bool:
        return bool(self.invoke_url and self.secret_key)

    def run(self, image_path: Path) -> list[dict[str, Any]]:
        if not self.enabled:
            raise RuntimeError("Clova OCR is not configured. Set invoke_url and secret_key.")

        encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        payload = {
            "version": self.version,
            "requestId": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "lang": self.language,
            "images": [
                {
                    "format": image_path.suffix.lstrip(".").lower() or "png",
                    "name": image_path.stem,
                    "data": encoded,
                }
            ],
            "enableTableDetection": self.table_detection,
        }
        response = requests.post(
            self.invoke_url,
            headers={
                "Content-Type": "application/json",
                "X-OCR-SECRET": self.secret_key,
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return self._to_lines(response.json())

    def _normalize_invoke_url(self, invoke_url: str) -> str:
        if not invoke_url:
            return ""
        parsed = urlparse(invoke_url)
        if parsed.scheme == "http" and parsed.netloc.endswith("ncloud.com"):
            return urlunparse(parsed._replace(scheme="https"))
        return invoke_url

    def _to_lines(self, response_json: dict[str, Any]) -> list[dict[str, Any]]:
        images = response_json.get("images", [])
        if not images:
            return []
        image = images[0]
        fields = image.get("fields", [])
        lines: list[dict[str, Any]] = []
        current_words: list[dict[str, Any]] = []

        def flush_line() -> None:
            nonlocal current_words
            if not current_words:
                return
            xs = [word["bbox"][0] for word in current_words] + [word["bbox"][2] for word in current_words]
            ys = [word["bbox"][1] for word in current_words] + [word["bbox"][3] for word in current_words]
            lines.append(
                {
                    "bbox": [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))],
                    "text": " ".join(word["text"] for word in current_words).strip(),
                    "confidence": sum(word["confidence"] for word in current_words) / max(1, len(current_words)),
                }
            )
            current_words = []

        for field in fields:
            vertices = field.get("boundingPoly", {}).get("vertices", [])
            if len(vertices) < 4:
                continue
            xs = [int(vertex.get("x", 0)) for vertex in vertices]
            ys = [int(vertex.get("y", 0)) for vertex in vertices]
            current_words.append(
                {
                    "bbox": [min(xs), min(ys), max(xs), max(ys)],
                    "text": field.get("inferText", "").strip(),
                    "confidence": float(field.get("inferConfidence", 0.0)),
                }
            )
            if field.get("lineBreak"):
                flush_line()

        flush_line()
        return [line for line in lines if line["text"]]
