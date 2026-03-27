from __future__ import annotations

from src.adapters import ClovaTemplateAdapter


def test_clova_template_adapter_describes_usage_plan() -> None:
    adapter = ClovaTemplateAdapter(
        {
            "invoke_url": "https://example.com/ocr",
            "secret_key": "secret",
            "template_id": "tmpl-1",
            "match_keywords": ["세종과고", "AP일반화학"],
            "target_fields": ["school", "subject"],
        }
    )

    plan = adapter.describe_plan(pdf_stem="2024-세종과고-AP일반화학1-기말", page_count=8)

    assert plan["enabled"] is True
    assert plan["keyword_match"] is True
    assert plan["should_apply"] is True
    assert plan["apply_pages"] == [1]


def test_clova_template_adapter_extracts_fields(monkeypatch, tmp_path) -> None:
    adapter = ClovaTemplateAdapter(
        {
            "invoke_url": "https://example.com/ocr",
            "secret_key": "secret",
            "template_id": "tmpl-1",
        }
    )

    def fake_analyze_raw(image_path, extra_body=None):
        assert extra_body == {"templateIds": ["tmpl-1"]}
        return {
            "images": [
                {
                    "fields": [
                        {"name": "school", "inferText": "세종과학고등학교"},
                        {"name": "subject", "inferText": "AP 일반 화학Ⅰ"},
                    ]
                }
            ]
        }

    monkeypatch.setattr(adapter.client, "analyze_raw", fake_analyze_raw)
    image_path = tmp_path / "page.png"
    image_path.write_bytes(b"fake")

    result = adapter.analyze_first_page(image_path=image_path, output_path=tmp_path / "template.json")

    assert result["applied"] is True
    assert result["fields"]["school"] == "세종과학고등학교"
    assert result["fields"]["subject"] == "AP 일반 화학Ⅰ"
