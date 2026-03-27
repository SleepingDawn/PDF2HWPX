from __future__ import annotations


def validate_table_items(questions: list) -> list[dict]:
    findings: list[dict] = []
    for question in questions:
        for index, item in enumerate(question.items, start=1):
            if item.get("type") != "table":
                continue
            table = item.get("object")
            if table is None:
                findings.append(
                    {
                        "question_no": question.question_no,
                        "category": "table",
                        "severity": "high",
                        "message": "missing_table_object",
                        "asset": f"question_{question.question_no:03d}_item_{index}",
                    }
                )
                continue
            if table.n_rows <= 0 or table.n_cols <= 0:
                findings.append(
                    {
                        "question_no": question.question_no,
                        "category": "table",
                        "severity": "high",
                        "message": "invalid_table_dimensions",
                        "asset": f"question_{question.question_no:03d}_item_{index}",
                    }
                )
            for cell in table.cells:
                if cell.row < 0 or cell.col < 0 or cell.row >= table.n_rows or cell.col >= table.n_cols:
                    findings.append(
                        {
                            "question_no": question.question_no,
                            "category": "table",
                            "severity": "medium",
                            "message": "table_cell_out_of_bounds",
                            "asset": f"question_{question.question_no:03d}_item_{index}",
                        }
                    )
                    break
            filled = 0
            nonempty_cols: set[int] = set()
            for cell in table.cells:
                fragments = [fragment.get("text", "").strip() for fragment in cell.content if isinstance(fragment, dict)]
                if any(fragments):
                    filled += 1
                    nonempty_cols.add(cell.col)
            if table.cells:
                fill_ratio = filled / len(table.cells)
                if fill_ratio < 0.6:
                    findings.append(
                        {
                            "question_no": question.question_no,
                            "category": "table",
                            "severity": "medium",
                            "message": "sparse_table_structure",
                            "asset": f"question_{question.question_no:03d}_item_{index}",
                        }
                    )
                    continue
            if table.n_cols > 1 and len(nonempty_cols) / max(1, table.n_cols) < 0.75:
                findings.append(
                    {
                        "question_no": question.question_no,
                        "category": "table",
                        "severity": "medium",
                        "message": "table_missing_content_columns",
                        "asset": f"question_{question.question_no:03d}_item_{index}",
                    }
                )
    return findings
