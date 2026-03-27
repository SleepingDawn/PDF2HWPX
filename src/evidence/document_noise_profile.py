from __future__ import annotations

from collections import defaultdict

from src.models.evidence import DocumentNoiseProfile
from src.models.ocr import NormalizedOCRPage
from src.utils.text_analysis import canonicalize_repeated_text


_FOOTER_KEYWORDS = ("저작권", "다음 면", "세종과학고등학교", "- 끝")


def build_document_noise_profile(ocr_pages: dict[int, NormalizedOCRPage]) -> DocumentNoiseProfile:
    if not ocr_pages:
        return DocumentNoiseProfile()

    buckets: dict[tuple[str, str], list[tuple[int, list[int], str]]] = defaultdict(list)
    for page in ocr_pages.values():
        for line in page.lines:
            text = line.text.strip()
            if not text:
                continue
            canonical = canonicalize_repeated_text(text)
            if line.bbox[1] >= int(page.height * 0.8) or any(keyword in text for keyword in _FOOTER_KEYWORDS):
                buckets[("footer", canonical)].append((page.page_no, line.bbox, text))
            elif line.bbox[3] <= int(page.height * 0.18):
                buckets[("header", canonical)].append((page.page_no, line.bbox, text))

    header_patterns: list[str] = []
    footer_patterns: list[str] = []
    header_bottom: int | None = None
    footer_top: int | None = None

    for (region, canonical), items in buckets.items():
        pages = {page_no for page_no, _, _ in items}
        sample = items[0][2]
        if len(pages) < 2 and not any(keyword in sample for keyword in _FOOTER_KEYWORDS):
            continue
        if region == "header":
            if len(pages) < 3:
                continue
            if len(sample.strip()) < 12:
                continue
            if canonical.startswith("#. "):
                continue
            header_patterns.append(canonical)
            band_bottom = max(bbox[3] for _, bbox, _ in items)
            header_bottom = band_bottom if header_bottom is None else max(header_bottom, band_bottom)
        else:
            footer_patterns.append(canonical)
            band_top = min(bbox[1] for _, bbox, _ in items)
            footer_top = band_top if footer_top is None else min(footer_top, band_top)

    return DocumentNoiseProfile(
        header_bottom=header_bottom,
        footer_top=footer_top,
        header_patterns=sorted(set(header_patterns)),
        footer_patterns=sorted(set(footer_patterns)),
    )


def is_noise_line(profile: DocumentNoiseProfile | None, text: str, bbox: list[int], page_height: int) -> bool:
    if profile is None:
        return False
    canonical = canonicalize_repeated_text(text)
    if profile.footer_top is not None and bbox[1] >= profile.footer_top - 6:
        if canonical in profile.footer_patterns or any(keyword in text for keyword in _FOOTER_KEYWORDS):
            return True
    if profile.header_bottom is not None and bbox[3] <= profile.header_bottom + 6 and canonical in profile.header_patterns:
        return True
    if bbox[1] >= int(page_height * 0.92) and any(keyword in text for keyword in _FOOTER_KEYWORDS):
        return True
    return False
