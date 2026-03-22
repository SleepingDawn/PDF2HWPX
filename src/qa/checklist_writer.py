from __future__ import annotations

from pathlib import Path

from src.utils.io import write_text
from src.utils.types import ChecklistIssue


def write_checklist(path: Path, hwpx_name: str, issues: list[ChecklistIssue]) -> None:
    lines = [f"파일명: {hwpx_name}", ""]
    for issue in issues:
        lines.extend(
            [
                f"[Q{issue.question_no}][{issue.category}][{issue.severity}]",
                issue.message,
                f"page: {issue.page}",
                f"asset: {issue.asset}",
                "",
            ]
        )
    write_text(path, "\n".join(lines).rstrip() + "\n")
