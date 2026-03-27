from __future__ import annotations


def validate_question_numbering(questions: list) -> list[dict]:
    findings: list[dict] = []
    if not questions:
        return [
            {
                "question_no": None,
                "category": "numbering",
                "severity": "high",
                "message": "no_questions",
                "asset": "document",
            }
        ]

    numbers = [question.question_no for question in questions]
    seen: set[int] = set()
    for number in numbers:
        if number in seen:
            findings.append(
                {
                    "question_no": number,
                    "category": "numbering",
                    "severity": "high",
                    "message": "duplicate_question_number",
                    "asset": f"question_{number:03d}",
                }
            )
        seen.add(number)

    expected = list(range(min(numbers), max(numbers) + 1))
    missing = sorted(set(expected) - set(numbers))
    for number in missing:
        findings.append(
            {
                "question_no": number,
                "category": "numbering",
                "severity": "medium",
                "message": "missing_question_number",
                "asset": f"question_{number:03d}",
            }
        )
    return findings
