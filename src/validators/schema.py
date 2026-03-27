from __future__ import annotations


ALLOWED_ITEM_TYPES = {"text", "table", "equation", "chem_equation", "image"}


def validate_question_schema(questions: list) -> list[dict]:
    findings: list[dict] = []
    for question in questions:
        for index, item in enumerate(question.items, start=1):
            item_type = item.get("type")
            if item_type not in ALLOWED_ITEM_TYPES:
                findings.append(
                    {
                        "question_no": question.question_no,
                        "category": "schema",
                        "severity": "high",
                        "message": f"unsupported_item_type:{item_type}",
                        "asset": f"question_{question.question_no:03d}_item_{index}",
                    }
                )
    return findings
