from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from src.evidence.ocr_normalizer import normalize_clova_page, synthesize_page_from_pdf
from src.models.ocr import NormalizedOCRPage
from src.ocr.clova_ocr import ClovaOcrClient
from src.utils.io import write_json


class ClovaGeneralAdapter:
    def __init__(self, config: dict[str, Any]) -> None:
        self.client = ClovaOcrClient(config)
        self.config = config

    def analyze_page(
        self,
        *,
        page_no: int,
        image_path: Path,
        width: int,
        height: int,
        raw_output_path: Path,
        norm_output_path: Path,
        extracted_text: str = "",
        extracted_words: list[dict] | None = None,
    ) -> NormalizedOCRPage:
        extracted_words = extracted_words or []
        if not self.client.enabled:
            normalized = synthesize_page_from_pdf(
                page_no=page_no,
                image_path=str(image_path),
                width=width,
                height=height,
                extracted_text=extracted_text,
                extracted_words=extracted_words,
                raw_ref=None,
            )
            write_json(norm_output_path, normalized)
            return normalized

        raw_response = self._request_with_fallbacks(image_path)
        write_json(raw_output_path, raw_response)
        normalized_payload = self.client.normalize_response(raw_response)
        normalized = normalize_clova_page(
            page_no=page_no,
            image_path=str(image_path),
            width=width,
            height=height,
            raw_ref=str(raw_output_path),
            raw_response=raw_response,
            normalized_payload=normalized_payload,
        )
        write_json(norm_output_path, normalized)
        return normalized

    def analyze_crop(
        self,
        *,
        crop_id: str,
        image_path: Path,
        raw_output_path: Path,
        norm_output_path: Path,
        fallback_text: str = "",
        page_no: int = 0,
    ) -> NormalizedOCRPage:
        if not self.client.enabled:
            normalized = synthesize_page_from_pdf(
                page_no=page_no,
                image_path=str(image_path),
                width=0,
                height=0,
                extracted_text=fallback_text,
                extracted_words=[],
                raw_ref=None,
            )
            write_json(norm_output_path, normalized)
            return normalized

        raw_response = self._request_with_fallbacks(image_path)
        write_json(raw_output_path, raw_response)
        normalized_payload = self.client.normalize_response(raw_response)
        normalized = normalize_clova_page(
            page_no=page_no,
            image_path=str(image_path),
            width=0,
            height=0,
            raw_ref=str(raw_output_path),
            raw_response=raw_response,
            normalized_payload=normalized_payload,
        )
        write_json(norm_output_path, normalized)
        return normalized

    def _request_with_fallbacks(self, image_path: Path) -> dict:
        try:
            return self.client.analyze_raw(image_path)
        except requests.RequestException:
            resized_path = image_path
            return self.client.analyze_raw(resized_path)
