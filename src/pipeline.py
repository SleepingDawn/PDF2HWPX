from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import re

import cv2

from src.analysis.answer_segmenter import segment_answer_notes
from src.analysis.exam_splitter import split_question_and_answer_sections
from src.analysis.layout_analyzer import analyze_page_layout
from src.analysis.question_segmenter import segment_questions
from src.build.hwpx_writer import HwpxWriter
from src.build.layout_planner import assign_question_starts
from src.build.render_model import RenderDocument
from src.ingest.filename_meta import parse_filename_meta
from src.ingest.pdf_loader import load_pdf
from src.ingest.renderer import render_pages
from src.normalize.chem_normalizer import normalize_chem_equation
from src.normalize.formula_normalizer import normalize_formula
from src.normalize.note_formatter import format_answer_note
from src.normalize.text_normalizer import normalize_text, sanitize_exam_text, split_inline_chemistry_segments
from src.ocr.formula_ocr import FormulaOcrEngine
from src.ocr.table_ocr import extract_table_from_page
from src.ocr.text_ocr import TextOcrEngine
from src.qa.checklist_writer import write_checklist
from src.qa.uncertainty_checker import build_uncertainty_issues
from src.qa.verification import validate_hwpx_structure
from src.restore.image_selector import restore_image
from src.utils.io import ensure_dir, load_yaml, write_json
from src.utils.logging import get_logger
from src.utils.types import AnswerNote, ExamMeta, ImageObject, Question, TableCell, TableObject
from src.utils.bbox import contains, intersects, union_boxes


class ExamHwpxPipeline:
    def __init__(self, config_path: Path, output_dir: Path, work_dir: Path, debug: bool = True) -> None:
        self.config = load_yaml(config_path)
        self.output_dir = output_dir
        self.work_dir = work_dir
        self.debug = debug
        self.logger = get_logger("exam_hwpx_builder")
        self.formula_ocr = FormulaOcrEngine()
        self.text_ocr = TextOcrEngine(self.config.get("ocr", {}))

    def run(self, input_pdf: Path) -> dict:
        run_id = f"{input_pdf.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_dir = ensure_dir(self.work_dir / run_id)
        pages_dir = ensure_dir(run_dir / "pages")
        masks_dir = ensure_dir(run_dir / "masks")
        restored_dir = ensure_dir(run_dir / "restored")
        debug_dir = ensure_dir(run_dir / "debug")
        crops_dir = ensure_dir(run_dir / "question_crops")

        loaded = load_pdf(input_pdf)
        rendered_pages = render_pages(loaded.document, pages_dir, dpi=self.config["render"]["dpi"])
        rendered_page_dicts = [self._page_to_dict(page) for page in rendered_pages]

        filename_meta = parse_filename_meta(input_pdf)
        first_page_text = normalize_text(rendered_pages[0].text) if rendered_pages else ""
        exam_meta = self._merge_meta(filename_meta, first_page_text)
        write_json(debug_dir / "exam_meta_candidate.json", asdict(exam_meta))

        page_texts = [page.text for page in rendered_pages]
        split_result = split_question_and_answer_sections(page_texts, self.config["analysis"]["answer_section_keywords"])
        write_json(debug_dir / "section_split.json", split_result)

        question_page_set = set(split_result["question_pages"])
        question_layouts = []
        for page in rendered_page_dicts:
            if page["page_no"] not in question_page_set:
                continue
            layout = analyze_page_layout(page, masks_dir / f"page_{page['page_no']:03d}_mask.png", self.config["analysis"])
            write_json(debug_dir / f"layout_page_{page['page_no']:03d}.json", layout)
            question_layouts.append(layout)

        questions = segment_questions(question_layouts, exam_meta.tagline)
        answer_notes = self._build_answer_notes(split_result["answer_pages"], rendered_pages)
        self._assemble_question_items(questions, question_layouts, rendered_page_dicts, answer_notes, restored_dir, crops_dir)
        assign_question_starts(questions, first_page_no=self.config["layout"]["first_page_no"])
        write_json(debug_dir / "questions.json", questions)
        write_json(debug_dir / "answer_notes.json", answer_notes)
        write_json(debug_dir / "layout_plan.json", [{"question_no": q.question_no, "start_page": q.start_page, "start_column": q.start_column} for q in questions])

        output_hwpx = ensure_dir(self.output_dir) / f"{input_pdf.stem}.hwpx"
        writer = HwpxWriter(output_hwpx)
        render_document = RenderDocument(title=input_pdf.stem, questions=questions, notes=answer_notes)
        writer.write(render_document)
        verification = validate_hwpx_structure(output_hwpx)
        write_json(debug_dir / "hwpx_verification.json", verification)

        issues = build_uncertainty_issues(questions, str(output_hwpx))
        checklist_path = self.output_dir / f"{input_pdf.stem}_checklist.txt"
        if issues:
            write_checklist(checklist_path, output_hwpx.name, issues)
        elif checklist_path.exists():
            checklist_path.unlink()

        return {
            "hwpx_path": str(output_hwpx),
            "checklist_path": str(checklist_path) if issues else None,
            "questions": len(questions),
            "has_answer_section": split_result["has_answer_section"],
            "verification": verification,
        }

    def _merge_meta(self, filename_meta: ExamMeta, first_page_text: str) -> ExamMeta:
        meta = filename_meta
        if not meta.year:
            match = next((token for token in first_page_text.split() if token.isdigit() and len(token) == 4), None)
            if match:
                meta.year = match
                meta.meta_source["year"] = "first_page"
        if not meta.exam_type:
            if "기말" in first_page_text:
                meta.exam_type = "기말"
                meta.meta_source["exam_type"] = "first_page"
            elif "중간" in first_page_text:
                meta.exam_type = "중간"
                meta.meta_source["exam_type"] = "first_page"
        if not meta.grade:
            for grade in ["1학년", "2학년", "3학년"]:
                if grade in first_page_text:
                    meta.grade = grade
                    meta.meta_source["grade"] = "first_page"
                    break
        if not meta.semester:
            for semester in ["1학기", "2학기"]:
                if semester in first_page_text:
                    meta.semester = semester
                    meta.meta_source["semester"] = "first_page"
                    break
        if not meta.school and "세종과학고" in first_page_text:
            meta.school = "세종과학고등학교"
            meta.meta_source["school"] = "first_page"
        if meta.year and meta.school and meta.grade and meta.semester and meta.exam_type:
            meta.tagline = f"({meta.year}년 {meta.school} {meta.grade} {meta.semester} {meta.exam_type})"
            meta.confidence = 0.85
        return meta

    def _page_to_dict(self, page) -> dict:
        words = list(page.words)
        text = page.text
        if self.text_ocr.force_page_ocr or not words or not text.strip():
            ocr_lines = self.text_ocr.run(page.image_path)
            words = [
                {
                    "bbox": line["bbox"],
                    "text": line["text"],
                    "block_no": index,
                    "line_no": index,
                    "word_no": 0,
                    "confidence": line["confidence"],
                }
                for index, line in enumerate(ocr_lines)
            ]
            text = "\n".join(line["text"] for line in ocr_lines)
        return {
            "page_no": page.page_no,
            "image_path": str(page.image_path),
            "width": page.width,
            "height": page.height,
            "pdf_width": page.pdf_width,
            "pdf_height": page.pdf_height,
            "text": text,
            "words": words,
        }

    def _build_answer_notes(self, answer_pages: list[int], rendered_pages: list) -> dict[int, AnswerNote]:
        answer_texts = [rendered_pages[page_no - 1].text for page_no in answer_pages]
        notes = segment_answer_notes(answer_texts)
        for note in notes.values():
            note.raw_text = format_answer_note(note.raw_text)
            if self._is_low_quality_note(note):
                note.exists = False
                note.has_explanation = False
                note.blocks = []
        return notes

    def _is_low_quality_note(self, note: AnswerNote) -> bool:
        text = normalize_text(note.raw_text)
        if not text:
            return True
        stripped = re.sub(r"^[0-9]+[.)]?\s*", "", text)
        stripped = re.sub(r"[\s,.\-–:;]+", "", stripped)
        if len(stripped) < 4:
            return True
        return False

    def _assemble_question_items(
        self,
        questions: list[Question],
        layouts: list[dict],
        rendered_pages: list[dict],
        answer_notes: dict[int, AnswerNote],
        restored_dir: Path,
        crops_dir: Path,
    ) -> None:
        page_map = {page["page_no"]: page for page in rendered_pages}
        layout_map = {layout["page_no"]: layout for layout in layouts}
        uncertainty_marker = self.config["normalize"]["uncertainty_marker"]
        confidence_threshold = self.config["ocr"]["confidence_threshold"]

        for question in questions:
            question.has_note = question.question_no in answer_notes
            question.note_ref_no = question.question_no if question.has_note else None
            question.items = []
            if not question.pages:
                question.uncertainties.append("ambiguous_question_page")
                continue
            question_regions = self._build_question_regions(question, layouts, page_map)
            all_region_boxes: list[list[int]] = []
            ordered_elements: list[dict] = []
            image_index = 1
            table_index = 1

            for region in question_regions:
                page_no = region["page_no"]
                bbox = region["bbox"]
                anchor_bbox = region["anchor_bbox"]
                all_region_boxes.append(bbox)
                page_layout = layout_map.get(page_no, {"blocks": [], "mask_path": ""})
                page_info = page_map[page_no]
                region_blocks = [
                    block
                    for block in page_layout["blocks"]
                    if intersects(block["bbox"], bbox)
                ]
                explicit_table_blocks = [block for block in region_blocks if block["type"] == "table" and contains(bbox, block["bbox"], margin=16)]
                image_blocks = [block for block in region_blocks if block["type"] == "image" and contains(bbox, block["bbox"], margin=24)]
                equation_blocks = [block for block in region_blocks if block["type"] == "equation"]
                chem_blocks = [block for block in region_blocks if block["type"] == "chem_equation"]
                object_boxes = [block["bbox"] for block in explicit_table_blocks + image_blocks + equation_blocks + chem_blocks]
                text_blocks = [
                    block
                    for block in region_blocks
                    if block["type"] == "text"
                    and not intersects(block["bbox"], self._expand_box(anchor_bbox, 16))
                    and not any(intersects(block["bbox"], self._expand_box(object_bbox, 8)) for object_bbox in object_boxes)
                ]
                text_blocks.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
                text_lines = self._build_text_lines(text_blocks, page_info["height"])
                inline_tables, remaining_lines = self._extract_inline_tables(text_lines, question.question_no, table_index)
                table_index += len(inline_tables)

                question_crop_path = crops_dir / f"q{question.question_no}_p{page_no}.png"
                self._crop_region(Path(page_info["image_path"]), bbox, question_crop_path)

                if any(block.get("confidence", 1.0) < confidence_threshold for block in text_blocks):
                    question.uncertainties.append("ocr_confidence_below_threshold")

                for line in remaining_lines:
                    ordered_elements.append(
                        {
                            "page_no": page_no,
                            "bbox": self._line_bbox(line),
                            "kind": "text_line",
                            "line": line,
                        }
                    )

                for table_info in inline_tables:
                    ordered_elements.append(
                        {
                            "page_no": page_no,
                            "bbox": table_info["bbox"],
                            "kind": "table",
                            "item": {"type": "table", "object": table_info["table"]},
                        }
                    )

                for block in sorted(equation_blocks, key=lambda item: (item["bbox"][1], item["bbox"][0])):
                    normalized, valid = normalize_formula(block["text"])
                    if not valid:
                        normalized = f"{normalized} {uncertainty_marker}".strip()
                        question.uncertainties.append("equation_conversion_low_confidence")
                    ordered_elements.append(
                        {
                            "page_no": page_no,
                            "bbox": block["bbox"],
                            "kind": "object",
                            "item": {"type": "equation", "target": normalized or block["text"]},
                        }
                    )

                for block in sorted(chem_blocks, key=lambda item: (item["bbox"][1], item["bbox"][0])):
                    normalized, valid = normalize_chem_equation(block["text"])
                    if not valid:
                        normalized = f"{block['text']} {uncertainty_marker}".strip()
                        question.uncertainties.append("chemical_equation_normalization_failed")
                    ordered_elements.append(
                        {
                            "page_no": page_no,
                            "bbox": block["bbox"],
                            "kind": "object",
                            "item": {"type": "chem_equation", "target": normalized},
                        }
                    )

                for block in explicit_table_blocks:
                    table, ok = extract_table_from_page(
                        table_id=f"q{question.question_no}_tbl{table_index}",
                        image_path=Path(page_info["image_path"]),
                        bbox=self._clip_box(block["bbox"], page_info["width"], page_info["height"]),
                        words=page_info["words"],
                    )
                    if not ok:
                        question.uncertainties.append("table_structure_incomplete")
                    for cell in table.cells:
                        merged_text = " ".join(part.get("text", "") for part in cell.content if part.get("type") == "text").strip()
                        cell.content = self._cell_content_segments(merged_text)
                    ordered_elements.append(
                        {
                            "page_no": page_no,
                            "bbox": block["bbox"],
                            "kind": "object",
                            "item": {"type": "table", "object": table},
                        }
                    )
                    table_index += 1

                for block in image_blocks:
                    table_from_image = self._promote_image_block_to_table(
                        block=block,
                        page_info=page_info,
                        question_no=question.question_no,
                        table_index=table_index,
                    )
                    if table_from_image is not None:
                        ordered_elements.append(
                            {
                                "page_no": page_no,
                                "bbox": block["bbox"],
                                "kind": "object",
                                "item": {"type": "table", "object": table_from_image},
                            }
                        )
                        table_index += 1
                        continue
                    crop_bbox = self._clip_box(block["bbox"], page_info["width"], page_info["height"])
                    raw_crop_path = crops_dir / f"q{question.question_no}_img{image_index}_raw.png"
                    self._crop_region(Path(page_info["image_path"]), crop_bbox, raw_crop_path)
                    mask_crop_path = crops_dir / f"q{question.question_no}_img{image_index}_mask.png"
                    self._crop_region(Path(page_layout["mask_path"]), crop_bbox, mask_crop_path)
                    restored_path, restoration_mode = restore_image(
                        image_path=raw_crop_path,
                        mask_path=mask_crop_path,
                        restored_dir=restored_dir,
                        radius=self.config["restore"]["inpaint_radius"],
                        factor=self.config["restore"]["upscale_factor"],
                    )
                    image_object = ImageObject(
                        image_id=f"q{question.question_no}_img{image_index}",
                        origin_page=page_no,
                        crop_bbox=crop_bbox,
                        clean_path=str(restored_path),
                        mask_path=str(mask_crop_path),
                        removed_handwriting=True,
                        restoration_mode=restoration_mode,
                    )
                    ordered_elements.append(
                        {
                            "page_no": page_no,
                            "bbox": block["bbox"],
                            "kind": "object",
                            "item": {"type": "image", "object": image_object},
                        }
                    )
                    image_index += 1

            ordered_elements.sort(key=lambda item: (item["page_no"], item["bbox"][1], item["bbox"][0]))
            question.items.extend(self._finalize_question_items(ordered_elements, question.question_no, uncertainty_marker, bool(question.uncertainties)))
            if question.uncertainties and not question.items:
                question.items.append({"type": "text", "content": uncertainty_marker})
            if all_region_boxes:
                question.bbox_union = union_boxes(all_region_boxes)

    def _build_question_regions(self, question: Question, layouts: list[dict], page_map: dict[int, dict]) -> list[dict]:
        layout_map = {layout["page_no"]: layout for layout in layouts}
        regions: list[dict] = []
        footer_margin = 120
        for page_no in question.pages:
            page = page_map[page_no]
            layout = layout_map.get(page_no)
            if not layout:
                continue
            anchor = next((item for item in layout["anchors"] if item["question_no"] == question.question_no), None)
            if not anchor:
                continue
            page_width = page["width"]
            page_height = page["height"]
            column_mid = page_width // 2
            anchor_center = (anchor["bbox"][0] + anchor["bbox"][2]) / 2
            column_left = 0 if anchor_center < column_mid else column_mid
            column_right = column_mid if anchor_center < column_mid else page_width
            next_anchor_y = page_height - footer_margin
            for candidate in layout["anchors"]:
                candidate_center = (candidate["bbox"][0] + candidate["bbox"][2]) / 2
                same_column = (candidate_center < column_mid) == (anchor_center < column_mid)
                if not same_column:
                    continue
                if candidate["question_no"] <= question.question_no:
                    continue
                if candidate["bbox"][1] <= anchor["bbox"][1]:
                    continue
                next_anchor_y = min(next_anchor_y, candidate["bbox"][1] - 20)
            regions.append(
                {
                    "page_no": page_no,
                    "bbox": [
                        max(0, column_left + 8),
                        max(0, anchor["bbox"][1] - 24),
                        min(page_width, column_right - 8),
                        max(anchor["bbox"][3] + 24, next_anchor_y),
                    ],
                    "anchor_bbox": anchor["bbox"],
                }
            )
        return regions

    def _compose_question_text(self, blocks: list[dict], page_height: int) -> str:
        return self._compose_question_text_from_lines(self._build_text_lines(blocks, page_height))

    def _build_text_lines(self, blocks: list[dict], page_height: int) -> list[list[dict]]:
        filtered = [
            block
            for block in blocks
            if block["type"] == "text"
            and block["bbox"][1] < int(page_height * 0.9)
            and not any(token in block["text"] for token in ["저작권", "다음 면에 계속됩니다", "총", "세종과학고등학교"])
        ]
        if not filtered:
            return []
        has_pdf_line_keys = all(block.get("block_no") is not None and block.get("line_no") is not None for block in filtered)
        lines: list[list[dict]] = []
        if has_pdf_line_keys:
            line_map: dict[tuple[int, int], list[dict]] = {}
            for block in filtered:
                key = (block["block_no"], block["line_no"])
                line_map.setdefault(key, []).append(block)
            lines = sorted(
                (sorted(line, key=lambda item: (item.get("word_no", 0), item["bbox"][0])) for line in line_map.values()),
                key=lambda line: (
                    min(item["bbox"][1] for item in line),
                    min(item["bbox"][0] for item in line),
                ),
            )
        else:
            for block in sorted(filtered, key=lambda item: (item["bbox"][1], item["bbox"][0])):
                center_y = (block["bbox"][1] + block["bbox"][3]) / 2
                if not lines:
                    lines.append([block])
                    continue
                last_center_y = sum((item["bbox"][1] + item["bbox"][3]) / 2 for item in lines[-1]) / len(lines[-1])
                if abs(center_y - last_center_y) <= self.config["ocr"]["paragraph_join_max_gap"]:
                    lines[-1].append(block)
                else:
                    lines.append([block])
        return self._merge_visual_lines(lines)

    def _compose_question_text_from_lines(self, lines: list[list[dict]], question_no: int | None = None) -> str:
        line_texts = []
        for line in lines:
            ordered = sorted(line, key=lambda item: item["bbox"][0])
            line_text = normalize_text(" ".join(item["text"] for item in ordered))
            if line_text:
                line_texts.append(line_text)
        paragraph = normalize_text(" ".join(line_texts))
        if question_no is not None:
            paragraph = self._strip_question_lead(paragraph, question_no)
        return sanitize_exam_text(paragraph)

    def _finalize_question_items(
        self,
        ordered_elements: list[dict],
        question_no: int,
        uncertainty_marker: str,
        has_uncertainty: bool,
    ) -> list[dict]:
        items: list[dict] = []
        line_buffer: list[list[dict]] = []
        previous_page = None
        previous_y = None

        def flush_buffer() -> None:
            nonlocal line_buffer
            if not line_buffer:
                return
            paragraph = self._compose_question_text_from_lines(line_buffer, question_no)
            if paragraph:
                for chunk in self._split_subquestion_paragraphs(paragraph):
                    segments = split_inline_chemistry_segments(chunk)
                    if any(segment["type"] == "equation" for segment in segments):
                        items.append({"type": "rich_text", "content": chunk, "segments": segments})
                    else:
                        items.append({"type": "text", "content": chunk})
            line_buffer = []

        for element in ordered_elements:
            if element["kind"] == "text_line":
                line_bbox = element["bbox"]
                if previous_page is None or previous_page != element["page_no"]:
                    flush_buffer()
                elif previous_y is not None and line_bbox[1] - previous_y > 120:
                    flush_buffer()
                line_buffer.append(element["line"])
                previous_page = element["page_no"]
                previous_y = line_bbox[3]
                continue
            flush_buffer()
            items.append(element["item"])
            previous_page = element["page_no"]
            previous_y = element["bbox"][3]

        flush_buffer()
        if has_uncertainty and items and items[0]["type"] == "text":
            items[0]["content"] = f"{items[0]['content']} {uncertainty_marker}".strip()
        return items

    def _merge_visual_lines(self, lines: list[list[dict]]) -> list[list[dict]]:
        if not lines:
            return []
        merged: list[list[dict]] = []
        for line in sorted(
            [sorted(line, key=lambda item: item["bbox"][0]) for line in lines],
            key=lambda line: (min(item["bbox"][1] for item in line), min(item["bbox"][0] for item in line)),
        ):
            current_y = min(item["bbox"][1] for item in line)
            if not merged:
                merged.append(line)
                continue
            previous = merged[-1]
            previous_y = min(item["bbox"][1] for item in previous)
            previous_right = max(item["bbox"][2] for item in previous)
            current_left = min(item["bbox"][0] for item in line)
            if abs(current_y - previous_y) <= 26 and current_left >= previous_right - 40:
                merged[-1] = sorted(previous + line, key=lambda item: item["bbox"][0])
            else:
                merged.append(line)
        return merged

    def _strip_question_lead(self, text: str, question_no: int) -> str:
        pattern = re.compile(rf"^\s*(?:{question_no}\s*[.)]|{question_no}\s*번)\s*")
        stripped = text
        while True:
            updated = pattern.sub("", stripped, count=1)
            if updated == stripped:
                break
            stripped = updated
        if stripped != text:
            return normalize_text(stripped)
        return text

    def _extract_inline_tables(self, lines: list[list[dict]], question_no: int, table_index_start: int) -> tuple[list[dict], list[list[dict]]]:
        if not lines:
            return [], []
        gap_threshold = 120
        used_indexes: set[int] = set()
        tables: list[dict] = []
        index = 0
        while index < len(lines):
            row_candidates: list[list[str]] = []
            center_candidates: list[list[int]] = []
            cursor = index
            while cursor < len(lines):
                row = sorted(lines[cursor], key=lambda item: item["bbox"][0])
                row_texts, row_centers = self._split_row_into_cells(row, gap_threshold)
                if len(row_texts) < 2:
                    break
                if center_candidates:
                    if len(row_texts) != len(center_candidates[0]):
                        break
                    if max(abs(a - b) for a, b in zip(row_centers, center_candidates[0])) > 180:
                        break
                if any(not text for text in row_texts):
                    break
                row_candidates.append(row_texts)
                center_candidates.append(row_centers)
                cursor += 1
            if (
                len(row_candidates) >= 2
                and self._looks_like_table(row_candidates)
            ):
                table_id = f"q{question_no}_tbl{table_index_start + len(tables)}"
                tables.append(
                    {
                        "table": self._build_inline_table(table_id, row_candidates),
                        "bbox": union_boxes(self._line_bbox(lines[line_index]) for line_index in range(index, cursor)),
                    }
                )
                used_indexes.update(range(index, cursor))
                index = cursor
            else:
                index += 1
        remaining_lines = [line for idx, line in enumerate(lines) if idx not in used_indexes]
        return tables, remaining_lines

    def _split_row_into_cells(self, row: list[dict], gap_threshold: int) -> tuple[list[str], list[int]]:
        clusters: list[list[dict]] = []
        for word in row:
            if not clusters:
                clusters.append([word])
                continue
            previous = clusters[-1][-1]
            gap = word["bbox"][0] - previous["bbox"][2]
            if gap >= gap_threshold:
                clusters.append([word])
            else:
                clusters[-1].append(word)
        texts = [normalize_text(" ".join(item["text"] for item in cluster)) for cluster in clusters]
        texts = [sanitize_exam_text(text) for text in texts]
        centers = [int((cluster[0]["bbox"][0] + cluster[-1]["bbox"][2]) / 2) for cluster in clusters]
        return texts, centers

    def _build_inline_table(self, table_id: str, row_candidates: list[list[str]]) -> TableObject:
        cells: list[TableCell] = []
        n_cols = max(len(row) for row in row_candidates)
        for row_index, row_values in enumerate(row_candidates):
            for col_index in range(n_cols):
                text = row_values[col_index] if col_index < len(row_values) else ""
                cells.append(TableCell(row=row_index, col=col_index, rowspan=1, colspan=1, content=self._cell_content_segments(text)))
        return TableObject(table_id=table_id, n_rows=len(row_candidates), n_cols=n_cols, cells=cells)

    def _looks_like_table(self, row_candidates: list[list[str]]) -> bool:
        texts = [text for row in row_candidates for text in row]
        digit_like = any(any(char.isdigit() for char in text) for text in texts)
        keyword_like = any(any(token in text for token in ["원소", "원자번호", "energy", "affinity", "거리", "질량", "부피", "농도"]) for text in texts)
        long_enough = sum(len(text.replace(" ", "")) for text in texts) >= 18
        pua_count = sum(sum(0xE000 <= ord(char) <= 0xF8FF for char in text) for text in texts)
        total_chars = max(1, sum(len(text) for text in texts))
        pua_ratio = pua_count / total_chars
        consistent_cols = len({len(row) for row in row_candidates}) == 1
        if pua_ratio > 0.2:
            return False
        if not consistent_cols:
            return False
        if len(row_candidates) >= 2 and max(len(row) for row in row_candidates) >= 3 and long_enough:
            return True
        if len(row_candidates) >= 3 and long_enough:
            return True
        return (digit_like or keyword_like) and long_enough

    def _line_bbox(self, line: list[dict]) -> list[int]:
        return union_boxes(item["bbox"] for item in line)

    def _expand_box(self, bbox: list[int], margin: int) -> list[int]:
        return [bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin]

    def _split_subquestion_paragraphs(self, text: str) -> list[str]:
        pattern = re.compile(r"(?<!\S)(\((?:\d+|[가-힣])\)|[①-⑳])\s*")
        matches = list(pattern.finditer(text))
        if not matches:
            return [text]

        segments: list[str] = []
        lead = normalize_text(text[:matches[0].start()])
        if lead:
            segments.append(lead)

        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            chunk = normalize_text(text[start:end])
            if chunk:
                segments.append(chunk)
        return segments or [text]

    def _promote_image_block_to_table(
        self,
        block: dict,
        page_info: dict,
        question_no: int,
        table_index: int,
    ) -> TableObject | None:
        words = [
            {
                "bbox": word["bbox"],
                "text": word["text"],
                "block_no": word.get("block_no"),
                "line_no": word.get("line_no"),
                "word_no": word.get("word_no"),
                "type": "text",
            }
            for word in page_info["words"]
            if contains(block["bbox"], word["bbox"], margin=8)
        ]
        if len(words) < 6:
            return None
        lines = self._build_text_lines(words, page_info["height"])
        tables, remaining_lines = self._extract_inline_tables(lines, question_no, table_index)
        if len(tables) != 1:
            return None
        if remaining_lines:
            remaining_text = self._compose_question_text_from_lines(remaining_lines)
            if remaining_text and len(remaining_text.replace(" ", "")) > 12:
                return None
        return tables[0]["table"]

    def _cell_content_segments(self, text: str) -> list[dict[str, str]]:
        segments = split_inline_chemistry_segments(sanitize_exam_text(text))
        return [
            {"type": "text", "text": segment["text"]}
            if segment["type"] == "text"
            else {"type": "equation", "script": segment["script"]}
            for segment in segments
        ]

    def _crop_region(self, image_path: Path, bbox: list[int], output_path: Path) -> None:
        image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if image is None:
            return
        x0, y0, x1, y1 = self._clip_box(bbox, image.shape[1], image.shape[0])
        crop = image[y0:y1, x0:x1]
        if crop.size == 0:
            return
        cv2.imwrite(str(output_path), crop)

    def _clip_box(self, bbox: list[int], width: int, height: int) -> list[int]:
        x0, y0, x1, y1 = bbox
        return [
            max(0, min(width, int(x0))),
            max(0, min(height, int(y0))),
            max(0, min(width, int(x1))),
            max(0, min(height, int(y1))),
        ]
