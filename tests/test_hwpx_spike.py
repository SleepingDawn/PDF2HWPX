from __future__ import annotations

import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from src.build.hwpx_writer import HwpxWriter
from src.build.render_model import RenderDocument
from src.build.layout_planner import assign_question_starts
from src.ocr.table_ocr import build_simple_table
from src.utils.types import AnswerNote, ImageObject, Question


def test_hwpx_spike(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    image = Image.new("RGB", (200, 100), color="white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 180, 80), outline="black", width=2)
    image.save(image_path)

    questions = [
        Question(
            question_no=1,
            pages=[1],
            bbox_union=[0, 0, 100, 100],
            has_note=True,
            note_ref_no=1,
            items=[
                {"type": "text", "content": "첫 번째 문제"},
                {"type": "equation", "target": "x^2 + y^2 = r^2"},
                {"type": "table", "object": build_simple_table("q1_tbl1", [["A", "B"], ["1", "2"]])},
                {
                    "type": "image",
                    "object": ImageObject(
                        image_id="q1_img1",
                        origin_page=1,
                        crop_bbox=[0, 0, 200, 100],
                        clean_path=str(image_path),
                        refinement_mode="nanobanana_passthrough",
                    ),
                },
            ],
            tagline="(2024년 세종과학고등학교 3학년 1학기 기말)",
        ),
        Question(
            question_no=2,
            pages=[1],
            bbox_union=[0, 0, 100, 100],
            has_note=True,
            note_ref_no=2,
            items=[
                {"type": "text", "content": "두 번째 문제"},
                {"type": "equation", "target": "2H2 + O2 -> 2H2O"},
            ],
            tagline="(2024년 세종과학고등학교 3학년 1학기 기말)",
        ),
    ]
    assign_question_starts(questions)
    notes = {
        1: AnswerNote(question_no=1, exists=True, blocks=[{"type": "text", "content": "1번 해설"}], raw_text="1번 해설", has_explanation=True),
        2: AnswerNote(question_no=2, exists=True, blocks=[{"type": "text", "content": "2번 해설"}], raw_text="2번 해설", has_explanation=True),
    }

    output = tmp_path / "spike.hwpx"
    HwpxWriter(output).write(RenderDocument(title="spike", questions=questions, notes=notes))

    with zipfile.ZipFile(output, "r") as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")
        content_hpf = archive.read("Contents/content.hpf").decode("utf-8")
        assert 'colCount="2"' in section
        assert "1. " in section
        assert "2. " in section
        assert "<hp:equation" in section
        assert "<hp:tbl" in section
        assert "<hp:pic" in section
        assert "<hp:endNote" in section
        assert "x^2 + y^2 = r^2" in section
        assert "2H2 + O2 -&gt; 2H2O" in section
        assert "Contents/section0.xml" in content_hpf
        assert "BinData/image1.png" in content_hpf
