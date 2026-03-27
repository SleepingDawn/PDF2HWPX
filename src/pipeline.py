from __future__ import annotations

from pathlib import Path

from src.orchestrator import PipelineController
from src.utils.io import load_yaml


class ExamHwpxPipeline:
    def __init__(self, config_path: Path, output_dir: Path, work_dir: Path, debug: bool = True) -> None:
        self.config = load_yaml(config_path)
        self.output_dir = output_dir
        self.work_dir = work_dir
        self.debug = debug
        self.controller = PipelineController(config=self.config, output_dir=output_dir, work_dir=work_dir)

    def run(self, input_pdf: Path) -> dict:
        result = self.controller.run(input_pdf)
        return {
            "hwpx_path": result.hwpx_path,
            "checklist_path": result.checklist_path,
            "questions": result.questions,
            "has_answer_section": result.has_answer_section,
            "verification": result.verification,
            "run_dir": result.run_dir,
            "issues": [
                {
                    "question_no": issue.question_no,
                    "block_id": issue.block_id,
                    "severity": issue.severity,
                    "category": issue.category,
                    "message": issue.message,
                    "asset": issue.asset,
                }
                for issue in result.issues
            ],
        }
