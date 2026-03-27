from __future__ import annotations

import base64
import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests

from src.utils.bbox import union_boxes


class ClovaOcrClient:
    def __init__(self, config: dict[str, Any]) -> None:
        raw_invoke_url = config.get("invoke_url") or os.getenv("CLOVA_OCR_INVOKE_URL", "")
        self.invoke_url = self._normalize_invoke_url(raw_invoke_url)
        self.secret_key = config.get("secret_key") or os.getenv("CLOVA_OCR_SECRET", "")
        self.version = config.get("version", "V2")
        self.language = config.get("language", "ko")
        self.timeout_seconds = int(config.get("timeout_seconds", 60))
        self.table_detection = bool(config.get("table_detection", True))
        self.cache_enabled = bool(config.get("cache_enabled", True))
        self.cache_dir = Path(config.get("cache_dir", "work/ocr_cache/clova"))
        self.last_from_cache = False

    @property
    def enabled(self) -> bool:
        return bool(self.invoke_url and self.secret_key)

    def analyze_raw(self, image_path: Path, extra_body: dict[str, Any] | None = None) -> dict[str, Any]:
        cache_path = self._cache_path(image_path, extra_body)
        if self.cache_enabled and cache_path.exists():
            self.last_from_cache = True
            return json.loads(cache_path.read_text(encoding="utf-8"))

        response_json = self._request(image_path, extra_body=extra_body)
        self.last_from_cache = False
        if self.cache_enabled:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(response_json, ensure_ascii=False, indent=2), encoding="utf-8")
        return response_json

    def normalize_response(self, response_json: dict[str, Any]) -> dict[str, Any]:
        return {
            "backend": "clova",
            "lines": self._to_lines(response_json),
            "tables": self._to_tables(response_json),
        }

    def analyze(self, image_path: Path, extra_body: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.normalize_response(self.analyze_raw(image_path, extra_body=extra_body))

    def run(self, image_path: Path) -> list[dict[str, Any]]:
        return self.analyze(image_path)["lines"]

    def _cache_path(self, image_path: Path, extra_body: dict[str, Any] | None = None) -> Path:
        digest = self._cache_digest(image_path, extra_body)
        return self.cache_dir / f"{digest}.json"

    def _cache_digest(self, image_path: Path, extra_body: dict[str, Any] | None = None) -> str:
        sha = hashlib.sha1()
        sha.update(image_path.read_bytes())
        sha.update(self.version.encode("utf-8"))
        sha.update(self.language.encode("utf-8"))
        sha.update(str(self.table_detection).encode("utf-8"))
        sha.update(self.invoke_url.encode("utf-8"))
        if extra_body:
            sha.update(json.dumps(extra_body, sort_keys=True, ensure_ascii=False).encode("utf-8"))
        return sha.hexdigest()

    def _request(self, image_path: Path, extra_body: dict[str, Any] | None = None) -> dict[str, Any]:
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
        if extra_body:
            payload.update(extra_body)
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
        return response.json()

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

    def _to_tables(self, response_json: dict[str, Any]) -> list[dict[str, Any]]:
        images = response_json.get("images", [])
        if not images:
            return []
        tables = images[0].get("tables", []) or []
        normalized: list[dict[str, Any]] = []
        for table_index, table in enumerate(tables, start=1):
            cells = table.get("cells", []) or []
            if not cells:
                continue
            normalized_cells: list[dict[str, Any]] = []
            for cell in cells:
                cell_bbox = self._poly_to_bbox(cell.get("boundingPoly", {}).get("vertices", []))
                cell_lines = cell.get("cellTextLines", []) or []
                line_texts: list[str] = []
                for line in cell_lines:
                    words = line.get("cellWords", []) or []
                    if words:
                        text = " ".join(word.get("inferText", "").strip() for word in words if word.get("inferText"))
                    else:
                        text = ""
                    if text:
                        line_texts.append(text)
                normalized_cells.append(
                    {
                        "row": int(cell.get("rowIndex", 0)),
                        "col": int(cell.get("columnIndex", 0)),
                        "rowspan": int(cell.get("rowSpan", 1)),
                        "colspan": int(cell.get("columnSpan", 1)),
                        "bbox": cell_bbox,
                        "text": " ".join(line_texts).strip(),
                        "confidence": float(cell.get("inferConfidence", 0.0)),
                    }
                )
            n_rows = max((cell["row"] + cell["rowspan"] for cell in normalized_cells), default=0)
            n_cols = max((cell["col"] + cell["colspan"] for cell in normalized_cells), default=0)
            bbox = self._poly_to_bbox(table.get("boundingPoly", {}).get("vertices", []))
            if bbox == [0, 0, 0, 0]:
                bbox = union_boxes(cell["bbox"] for cell in normalized_cells if cell["bbox"] != [0, 0, 0, 0])
            normalized.append(
                {
                    "id": f"clova_table_{table_index}",
                    "bbox": bbox,
                    "n_rows": n_rows,
                    "n_cols": n_cols,
                    "confidence": float(table.get("inferConfidence", 0.0)),
                    "cells": normalized_cells,
                }
            )
        return normalized

    def _poly_to_bbox(self, vertices: list[dict[str, Any]]) -> list[int]:
        if not vertices:
            return [0, 0, 0, 0]
        xs = [int(vertex.get("x", 0)) for vertex in vertices]
        ys = [int(vertex.get("y", 0)) for vertex in vertices]
        return [min(xs), min(ys), max(xs), max(ys)]
