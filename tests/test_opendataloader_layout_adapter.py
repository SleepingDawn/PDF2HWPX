from __future__ import annotations

from src.adapters.opendataloader_layout import OdlDocument, OpenDataLoaderLayoutAdapter
from src.models.common import PageAsset


def test_opendataloader_adapter_collects_question_anchor_candidates_and_filters_numeric_values(tmp_path) -> None:
    payload = [
        {
            "type": "text block",
            "page number": 1,
            "bounding box": [0, 0, 595, 842],
            "kids": [
                {
                    "type": "paragraph",
                    "page number": 1,
                    "bounding box": [42.0, 486.0, 220.0, 498.0],
                    "content": "1. 첫 번째 문항",
                },
                {
                    "type": "paragraph",
                    "page number": 1,
                    "bounding box": [480.0, 608.0, 510.0, 620.0],
                    "content": "2.27Å",
                },
                {
                    "type": "paragraph",
                    "page number": 1,
                    "bounding box": [308.0, 631.0, 552.0, 676.0],
                    "content": "2. 두 번째 문항",
                },
            ],
        }
    ]
    asset = PageAsset(
        page_no=1,
        image_path=tmp_path / "page.png",
        thumbnail_path=tmp_path / "page.png",
        width=2480,
        height=3505,
        pdf_width=595.0,
        pdf_height=842.0,
        extracted_text="",
        extracted_words=[],
        page_hash="x",
    )
    adapter = OpenDataLoaderLayoutAdapter({"enabled": True})
    page_elements = adapter._extract_page_elements(payload, {1: asset})
    candidates = adapter.collect_question_anchor_candidates(OdlDocument(json_path="", markdown_path=None, page_elements=page_elements), [1])

    assert [candidate.text for candidate in candidates[1]] == ["1. 첫 번째 문항", "2. 두 번째 문항"]
