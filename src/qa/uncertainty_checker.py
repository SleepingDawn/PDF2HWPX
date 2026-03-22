from __future__ import annotations

from src.utils.types import ChecklistIssue, Question


MESSAGE_MAP = {
    "ambiguous_question_anchor": "문항 번호 검출이 애매합니다. 원본 확인이 필요합니다.",
    "ambiguous_question_page": "문항 페이지 범위가 비어 있습니다. 원본 PDF를 확인하십시오.",
    "equation_conversion_low_confidence": "수식 변환 confidence가 낮습니다. 원본과 대조가 필요합니다.",
    "chemical_equation_normalization_failed": "화학 반응식 정규화에 실패했습니다. 원본과 대조가 필요합니다.",
    "ocr_confidence_below_threshold": "본문 OCR confidence가 낮습니다. 원본과 대조가 필요합니다.",
    "table_structure_incomplete": "표 구조 복원이 불완전합니다. 셀 병합과 값 위치를 원본과 대조하십시오.",
}


def build_uncertainty_issues(questions: list[Question], output_hwpx_name: str) -> list[ChecklistIssue]:
    issues: list[ChecklistIssue] = []
    seen: set[tuple[int, str]] = set()
    for question in questions:
        for uncertainty in question.uncertainties:
            signature = (question.question_no, uncertainty)
            if signature in seen:
                continue
            seen.add(signature)
            issues.append(
                ChecklistIssue(
                    question_no=question.question_no,
                    severity="medium",
                    category=uncertainty.replace("_", "-"),
                    message=MESSAGE_MAP.get(uncertainty, uncertainty),
                    page=question.pages[0] if question.pages else 1,
                    asset=output_hwpx_name,
                )
            )
    return issues
