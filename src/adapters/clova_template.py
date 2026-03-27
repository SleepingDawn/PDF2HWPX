from __future__ import annotations

from pathlib import Path
from typing import Any

from src.ocr.clova_ocr import ClovaOcrClient
from src.utils.io import write_json


class ClovaTemplateAdapter:
    def __init__(self, config: dict) -> None:
        self.config = config
        client_config = dict(config)
        client_config.pop("template_id", None)
        client_config.pop("match_keywords", None)
        client_config.pop("target_fields", None)
        self.client = ClovaOcrClient(client_config)

    def enabled(self) -> bool:
        return bool(self.client.enabled and self.config.get("template_id"))

    def describe_plan(self, *, pdf_stem: str, page_count: int) -> dict:
        keywords = [keyword for keyword in self.config.get("match_keywords", []) if keyword]
        target_fields = [field for field in self.config.get("target_fields", []) if field]
        keyword_match = any(keyword in pdf_stem for keyword in keywords) if keywords else self.enabled()
        should_apply = self.enabled() and keyword_match and page_count >= 1
        return {
            "enabled": self.enabled(),
            "template_id": self.config.get("template_id"),
            "match_keywords": keywords,
            "target_fields": target_fields,
            "keyword_match": keyword_match,
            "should_apply": should_apply,
            "apply_pages": [1] if should_apply else [],
        }

    def analyze_first_page(self, *, image_path: Path, output_path: Path) -> dict:
        if not self.enabled():
            result = {"applied": False, "fields": {}}
            write_json(output_path, result)
            return result

        raw = self.client.analyze_raw(
            image_path,
            extra_body={"templateIds": [self.config["template_id"]]},
        )
        fields = self._extract_fields(raw)
        result = {
            "applied": True,
            "template_id": self.config["template_id"],
            "fields": fields,
            "raw": raw,
        }
        write_json(output_path, result)
        return result

    def _extract_fields(self, response_json: dict[str, Any]) -> dict[str, str]:
        images = response_json.get("images", [])
        if not images:
            return {}
        image = images[0]
        extracted: dict[str, str] = {}
        for field in image.get("fields", []) or []:
            key = self._field_name(field)
            value = self._field_value(field)
            if key and value:
                extracted[key] = value
        for item in image.get("title", []) or []:
            key = self._field_name(item)
            value = self._field_value(item)
            if key and value and key not in extracted:
                extracted[key] = value
        return extracted

    def _field_name(self, field: dict[str, Any]) -> str:
        candidates = [
            field.get("name"),
            field.get("label"),
            field.get("key"),
            field.get("inferFieldName"),
        ]
        for candidate in candidates:
            if candidate:
                return str(candidate).strip()
        return ""

    def _field_value(self, field: dict[str, Any]) -> str:
        for key in ["inferText", "value", "text", "inferFieldValue"]:
            candidate = field.get(key)
            if candidate:
                return str(candidate).strip()
        if field.get("subFields"):
            parts = [self._field_value(item) for item in field["subFields"]]
            return " ".join(part for part in parts if part).strip()
        return ""
