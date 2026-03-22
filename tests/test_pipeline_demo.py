from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from src.pipeline import ExamHwpxPipeline


def _make_demo_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("Helvetica", 14)
    c.drawString(50, 800, "2024 세종과학고등학교 3학년 1학기 기말")
    c.drawString(50, 760, "1. Calculate x^2 + y^2 = r^2")
    c.drawString(50, 730, "2. Balance 2H2 + O2 -> 2H2O")
    c.showPage()
    c.drawString(50, 800, "정답 및 풀이")
    c.drawString(50, 760, "1. 정답: r^2 해설: 피타고라스")
    c.drawString(50, 730, "2. 정답: 2H2O 해설: 반응식")
    c.save()


def test_pipeline_end_to_end(tmp_path: Path) -> None:
    pdf_path = tmp_path / "2024-3-1-세종과고-AP일반화학1-②기말.pdf"
    _make_demo_pdf(pdf_path)

    pipeline = ExamHwpxPipeline(
        config_path=Path("config/default.yaml"),
        output_dir=tmp_path / "output",
        work_dir=tmp_path / "work",
        debug=True,
    )
    result = pipeline.run(pdf_path)

    assert Path(result["hwpx_path"]).exists()
    assert result["questions"] >= 1
    assert result["verification"]["valid"] is True
    run_debug = next((tmp_path / "work").iterdir()) / "debug"
    assert (run_debug / "exam_meta_candidate.json").exists()
    assert (run_debug / "layout_plan.json").exists()
