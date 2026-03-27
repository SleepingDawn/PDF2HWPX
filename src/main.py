from __future__ import annotations

import argparse
from pathlib import Path

from src.pipeline import ExamHwpxPipeline
from src.utils.env import load_dotenv
from src.utils.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert a single exam PDF into a HWPX package.")
    parser.add_argument("--input", required=True, help="Path to one PDF file.")
    parser.add_argument("--output-dir", default="artifacts/exports/default")
    parser.add_argument("--work-dir", default="artifacts/runs/default")
    parser.add_argument("--debug", action="store_true", default=True)
    parser.add_argument("--config", default="config/default.yaml")
    return parser


def main() -> None:
    configure_logging()
    load_dotenv()
    args = build_parser().parse_args()
    pipeline = ExamHwpxPipeline(config_path=Path(args.config), output_dir=Path(args.output_dir), work_dir=Path(args.work_dir), debug=args.debug)
    pipeline.run(Path(args.input))


if __name__ == "__main__":
    main()
