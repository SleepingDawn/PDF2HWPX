from __future__ import annotations


def validate_formula_items(questions: list) -> list[dict]:
    findings: list[dict] = []
    for question in questions:
        for index, item in enumerate(question.items, start=1):
            item_type = item.get("type")
            if item_type not in {"equation", "chem_equation"}:
                continue
            target = (item.get("target") or "").strip()
            if not target:
                findings.append(
                    {
                        "question_no": question.question_no,
                        "category": "formula",
                        "severity": "high",
                        "message": "empty_formula_target",
                        "asset": f"question_{question.question_no:03d}_item_{index}",
                    }
                )
                continue
            if item_type == "chem_equation" and not any(token in target for token in ["->", "rightarrow", "⇌", "<=>"]):
                findings.append(
                    {
                        "question_no": question.question_no,
                        "category": "formula",
                        "severity": "medium",
                        "message": "chem_equation_missing_arrow",
                        "asset": f"question_{question.question_no:03d}_item_{index}",
                    }
                )
            if item_type == "equation" and not any(token in target for token in ["=", "^", "√", "/", "+", "-"]):
                findings.append(
                    {
                        "question_no": question.question_no,
                        "category": "formula",
                        "severity": "medium",
                        "message": "equation_missing_operator",
                        "asset": f"question_{question.question_no:03d}_item_{index}",
                    }
                )
    return findings
