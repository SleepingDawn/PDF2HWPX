from __future__ import annotations

import re
from pathlib import Path

from src.utils.types import ExamMeta


SCHOOL_FIXTURES = {
    "세종과고": "세종과학고등학교",
    "세종과학고": "세종과학고등학교",
}

SUBJECT_FIXTURES = {
    "AP일반화학1": "AP 일반 화학Ⅰ",
    "AP일반화학Ⅰ": "AP 일반 화학Ⅰ",
}


def parse_filename_meta(path: Path) -> ExamMeta:
    basename = path.stem
    parts = re.split(r"[-_]", basename)
    year = next((part for part in parts if re.fullmatch(r"20\d{2}", part)), None)
    semester = None
    grade = None
    school = None
    exam_type = None
    subject = None

    for part in parts:
        if re.fullmatch(r"[123]-[12]", part):
            grade_digit, semester_digit = part.split("-")
            grade = f"{grade_digit}학년"
            semester = f"{semester_digit}학기"
        elif part in SCHOOL_FIXTURES:
            school = SCHOOL_FIXTURES[part]
        elif part in SUBJECT_FIXTURES:
            subject = SUBJECT_FIXTURES[part]
        elif "기말" in part:
            exam_type = "기말"
        elif "중간" in part:
            exam_type = "중간"

    tagline = None
    if year and school and grade and semester and exam_type:
        tagline = f"({year}년 {school} {grade} {semester} {exam_type})"

    meta_source = {}
    if year:
        meta_source["year"] = "filename"
    if school:
        meta_source["school"] = "filename"
    if grade:
        meta_source["grade"] = "filename"
    if semester:
        meta_source["semester"] = "filename"
    if exam_type:
        meta_source["exam_type"] = "filename"

    return ExamMeta(
        source_pdf=str(path),
        basename=basename,
        year=year,
        school=school,
        grade=grade,
        semester=semester,
        exam_type=exam_type,
        subject=subject,
        tagline=tagline,
        confidence=0.45 if meta_source else 0.0,
        meta_source=meta_source,
    )
