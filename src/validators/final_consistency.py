from __future__ import annotations

from src.validators.formula import validate_formula_items
from src.validators.numbering import validate_question_numbering
from src.validators.schema import validate_question_schema
from src.validators.table import validate_table_items

def validate_render_questions(questions: list) -> list[str]:
    problems: list[str] = []
    if not questions:
        problems.append("no_questions")
        return problems
    numbers = [question.question_no for question in questions]
    if len(numbers) != len(set(numbers)):
        problems.append("duplicate_question_numbers")
    for question in questions:
        if not question.items:
            problems.append(f"empty_question_items:{question.question_no}")
    return problems


def collect_validation_findings(questions: list) -> list[dict]:
    findings: list[dict] = []
    findings.extend(validate_question_schema(questions))
    findings.extend(validate_question_numbering(questions))
    findings.extend(validate_formula_items(questions))
    findings.extend(validate_table_items(questions))
    for problem in validate_render_questions(questions):
        question_no = None
        if ":" in problem:
            _, suffix = problem.split(":", 1)
            question_no = int(suffix)
        findings.append(
            {
                "question_no": question_no,
                "category": "final_consistency",
                "severity": "high",
                "message": problem,
                "asset": "document" if question_no is None else f"question_{question_no:03d}",
            }
        )
    return findings
