from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import re

import cv2
from PIL import Image

from src.models.common import BBox, Issue, PageAsset
from src.models.evidence import BlockEvidence, BlockTypeCandidate, DocumentNoiseProfile, QuestionPackage
from src.models.ocr import NormalizedOCRPage, OCRLine, OCRWord
from src.utils.bbox import box_area, contains, intersects, union_boxes
from src.utils.text_analysis import looks_like_equation_line, looks_like_prose_line


_CHEM_REACTION_PATTERN = re.compile(r"(->|→|⇌|<=>)")


def classify_block_text(text: str) -> list[BlockTypeCandidate]:
    stripped = text.strip()
    if not stripped:
        return [BlockTypeCandidate(type="unknown", score=0.0)]
    chem_score = 0.0
    equation_score = 0.0
    if _CHEM_REACTION_PATTERN.search(stripped) and any(char.isupper() for char in stripped):
        chem_score = 0.82
    if looks_like_prose_line(stripped):
        return [
            BlockTypeCandidate(type="text", score=0.94),
            BlockTypeCandidate(type="equation", score=0.06),
        ]
    if looks_like_equation_line(stripped) and len(stripped) < 160:
        equation_score = max(equation_score, 0.74)
    if chem_score:
        return [
            BlockTypeCandidate(type="chem_equation", score=chem_score),
            BlockTypeCandidate(type="equation", score=0.45),
            BlockTypeCandidate(type="text", score=0.18),
        ]
    if equation_score:
        return [
            BlockTypeCandidate(type="equation", score=equation_score),
            BlockTypeCandidate(type="text", score=0.3),
        ]
    return [
        BlockTypeCandidate(type="text", score=0.9),
        BlockTypeCandidate(type="equation", score=0.1),
    ]


class QuestionEvidenceBuilder:
    def build(
        self,
        *,
        package: QuestionPackage,
        page_assets: dict[int, PageAsset],
        ocr_pages: dict[int, NormalizedOCRPage],
        crops_dir: Path,
        noise_profile: DocumentNoiseProfile | None = None,
    ) -> tuple[list[BlockEvidence], list[Issue]]:
        blocks: list[BlockEvidence] = []
        issues: list[Issue] = []
        block_index = 1
        for page_range in package.page_ranges:
            ocr_page = ocr_pages[page_range.page_no]
            page_asset = page_assets[page_range.page_no]
            accepted_tables = [
                table
                for table in ocr_page.tables
                if contains(page_range.bbox, table.bbox, margin=16) and self._looks_like_structured_table(table)
            ]
            accepted_table_boxes = [table.bbox for table in accepted_tables]
            image_boxes = self._detect_image_boxes(page_asset.image_path, page_range.bbox, ocr_page)
            excluded_boxes = accepted_table_boxes + [self._expand_box(box, 24) for box in image_boxes]

            for line in self._question_lines(ocr_page, page_range.bbox, noise_profile, excluded_boxes):
                if self._is_chart_label_near_image(line, image_boxes):
                    continue
                block_id = f"q{package.question_no}_b{block_index}"
                crop_path = self._save_crop(page_asset.image_path, line.bbox, crops_dir / f"{block_id}.png")
                candidates = classify_block_text(line.text)
                blocks.append(
                    BlockEvidence(
                        block_id=block_id,
                        question_no=package.question_no,
                        page_no=page_range.page_no,
                        bbox=line.bbox,
                        crop_path=str(crop_path),
                        ocr_text=line.text,
                        ocr_confidence=line.confidence,
                        type_candidates=candidates,
                        has_handwriting_overlap=False,
                        table_candidate=False,
                    )
                )
                block_index += 1

            for table in accepted_tables:
                block_id = f"q{package.question_no}_b{block_index}"
                crop_path = self._save_crop(page_asset.image_path, table.bbox, crops_dir / f"{block_id}.png")
                blocks.append(
                    BlockEvidence(
                        block_id=block_id,
                        question_no=package.question_no,
                        page_no=page_range.page_no,
                        bbox=table.bbox,
                        crop_path=str(crop_path),
                        ocr_text=" ".join(cell.text for cell in table.cells if cell.text),
                        ocr_confidence=table.confidence,
                        type_candidates=[
                            BlockTypeCandidate(type="table", score=0.95),
                            BlockTypeCandidate(type="text", score=0.05),
                        ],
                        has_handwriting_overlap=False,
                        table_candidate=True,
                    )
                )
                block_index += 1

            for image_bbox in image_boxes:
                block_id = f"q{package.question_no}_b{block_index}"
                crop_path = self._save_crop(page_asset.image_path, image_bbox, crops_dir / f"{block_id}.png")
                blocks.append(
                    BlockEvidence(
                        block_id=block_id,
                        question_no=package.question_no,
                        page_no=page_range.page_no,
                        bbox=image_bbox,
                        crop_path=str(crop_path),
                        ocr_text="",
                        ocr_confidence=0.0,
                        type_candidates=[
                            BlockTypeCandidate(type="image", score=0.95),
                            BlockTypeCandidate(type="text", score=0.05),
                        ],
                        has_handwriting_overlap=False,
                        table_candidate=False,
                        ocr_engine="image_detector",
                    )
                )
                block_index += 1

        if not blocks:
            issues.append(
                Issue(
                    question_no=package.question_no,
                    block_id=None,
                    severity="high",
                    category="question_package",
                    message="문항 패키지에서 블록을 추출하지 못했습니다.",
                    asset=f"question_{package.question_no:03d}",
                )
            )
        return blocks, issues

    def _question_lines(
        self,
        ocr_page: NormalizedOCRPage,
        bbox: BBox,
        noise_profile: DocumentNoiseProfile | None,
        excluded_boxes: list[BBox] | None = None,
    ) -> list[OCRLine]:
        excluded_boxes = excluded_boxes or []
        words = [
            word
            for word in ocr_page.words
            if contains(bbox, word.bbox, margin=8) and not any(intersects(word.bbox, excluded_bbox) for excluded_bbox in excluded_boxes)
        ]
        if words:
            return self._synthetic_lines_from_words(ocr_page, words, noise_profile)

        from src.evidence.document_noise_profile import is_noise_line

        return [
            line
            for line in ocr_page.lines
            if contains(bbox, line.bbox, margin=8)
            and not any(intersects(line.bbox, excluded_bbox) for excluded_bbox in excluded_boxes)
            and not is_noise_line(noise_profile, line.text, line.bbox, ocr_page.height)
        ]

    def _synthetic_lines_from_words(
        self,
        ocr_page: NormalizedOCRPage,
        words: list[OCRWord],
        noise_profile: DocumentNoiseProfile | None,
    ) -> list[OCRLine]:
        rows: list[list[OCRWord]] = []
        for word in sorted(words, key=lambda item: (item.bbox[1], item.bbox[0])):
            if not rows or abs(word.bbox[1] - rows[-1][-1].bbox[1]) > 28:
                rows.append([word])
            else:
                rows[-1].append(word)

        synthetic: list[OCRLine] = []
        from src.evidence.document_noise_profile import is_noise_line

        for index, row in enumerate(rows, start=1):
            row = sorted(row, key=lambda item: item.bbox[0])
            for segment_index, segment in enumerate(self._split_row_segments(row, ocr_page.width), start=1):
                text = " ".join(word.text.strip() for word in segment if word.text.strip()).strip()
                if not text:
                    continue
                xs = [word.bbox[0] for word in segment] + [word.bbox[2] for word in segment]
                ys = [word.bbox[1] for word in segment] + [word.bbox[3] for word in segment]
                row_bbox = [min(xs), min(ys), max(xs), max(ys)]
                if is_noise_line(noise_profile, text, row_bbox, ocr_page.height):
                    continue
                synthetic.append(
                    OCRLine(
                        line_id=f"p{ocr_page.page_no}_qb{index}_{segment_index}",
                        text=text,
                        bbox=row_bbox,
                        confidence=sum(word.confidence for word in segment) / max(1, len(segment)),
                    )
                )
        return synthetic

    def _split_row_segments(self, row: list[OCRWord], page_width: int) -> list[list[OCRWord]]:
        if not row:
            return []
        segments: list[list[OCRWord]] = [[row[0]]]
        heights = [max(1, word.bbox[3] - word.bbox[1]) for word in row]
        gap_threshold = max(64, int(sum(heights) / max(1, len(heights)) * 1.6))
        for previous, word in zip(row, row[1:]):
            gap = word.bbox[0] - previous.bbox[2]
            if gap >= gap_threshold:
                segments.append([word])
            else:
                segments[-1].append(word)
        return segments

    def _looks_multi_lane(self, ocr_page: NormalizedOCRPage, bbox: BBox, excluded_boxes: list[BBox]) -> bool:
        words = [
            word
            for word in ocr_page.words
            if contains(bbox, word.bbox, margin=8) and not any(intersects(word.bbox, excluded_bbox) for excluded_bbox in excluded_boxes)
        ]
        if len(words) < 10:
            return False
        width = bbox[2] - bbox[0]
        split_x = bbox[0] + width * 0.5
        left = [word for word in words if ((word.bbox[0] + word.bbox[2]) / 2) < split_x - width * 0.08]
        right = [word for word in words if ((word.bbox[0] + word.bbox[2]) / 2) > split_x + width * 0.08]
        if len(left) < 4 or len(right) < 4:
            return False
        row_signals = 0
        rows: list[list[OCRWord]] = []
        for word in sorted(words, key=lambda item: (item.bbox[1], item.bbox[0])):
            if not rows or abs(word.bbox[1] - rows[-1][-1].bbox[1]) > 28:
                rows.append([word])
            else:
                rows[-1].append(word)
        for row in rows:
            centers = [((word.bbox[0] + word.bbox[2]) / 2) for word in row]
            if any(center < split_x - width * 0.08 for center in centers) and any(center > split_x + width * 0.08 for center in centers):
                row_signals += 1
            if row_signals >= 2:
                return True
        return False

    def _expand_box(self, bbox: BBox, margin: int) -> BBox:
        return [bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin]

    def _is_chart_label_near_image(self, line: OCRLine, image_boxes: list[BBox]) -> bool:
        text = line.text.strip()
        if not text or not image_boxes:
            return False
        if not self._looks_like_chart_label(text):
            return False
        expanded = self._expand_box(line.bbox, 140)
        return any(intersects(expanded, image_box) for image_box in image_boxes)

    def _looks_like_chart_label(self, text: str) -> bool:
        stripped = re.sub(r"\s+", " ", text.strip())
        if not stripped:
            return False
        if len(stripped) <= 14 and re.fullmatch(r"[\dA-Za-z가-힣+\-().,/→§ ]+", stripped):
            tokens = stripped.split()
            if len(tokens) <= 3:
                return True
        if re.fullmatch(r"[+\-]?\d+(?:\.\d+)?(?:\s+[+\-]?\d+(?:\.\d+)?)*", stripped):
            return True
        if stripped in {"(가)", "(나)", "(다)", "(라)", "Contour plots", "Line scan", "x", "y", "z", "A→", "B→", ">"}:
            return True
        return False

    def _looks_like_structured_table(self, table) -> bool:
        if table.n_rows <= 1 or table.n_cols <= 1:
            return False
        filled_cells = [cell for cell in table.cells if cell.text.strip()]
        if len(filled_cells) < 4:
            return False
        if self._looks_like_lookup_grid(table, filled_cells):
            return True
        if self._looks_like_key_value_table(table, filled_cells):
            return True
        fill_ratio = len(filled_cells) / max(1, len(table.cells))
        if fill_ratio < 0.5:
            return False
        nonempty_cols = {cell.col for cell in filled_cells}
        if len(nonempty_cols) < 2:
            return False
        long_cells = sum(1 for cell in filled_cells if len(cell.text.strip()) >= 40)
        if long_cells > len(filled_cells) // 2:
            return False
        joined = " ".join(cell.text.strip() for cell in filled_cells[:6]).strip()
        if joined and looks_like_prose_line(joined) and table.n_rows <= 3:
            return False
        return True

    def _looks_like_lookup_grid(self, table, filled_cells) -> bool:
        if table.n_rows < 2 or table.n_cols < 3:
            return False
        if len(filled_cells) != len(table.cells):
            return False
        short_cells = sum(1 for cell in filled_cells if len(cell.text.strip()) <= 8)
        if short_cells < len(filled_cells) - 1:
            return False
        numeric_cells = sum(1 for cell in filled_cells if cell.text.strip().isdigit())
        alpha_cells = sum(1 for cell in filled_cells if any(ch.isalpha() or "\uac00" <= ch <= "\ud7a3" for ch in cell.text))
        return numeric_cells >= 1 and alpha_cells >= 2

    def _looks_like_key_value_table(self, table, filled_cells) -> bool:
        if table.n_cols != 2 or table.n_rows < 2:
            return False
        row_map: dict[int, dict[int, str]] = {}
        for cell in filled_cells:
            row_map.setdefault(int(cell.row), {})[int(cell.col)] = cell.text.strip()
        complete_rows = [row for row in row_map.values() if row.get(0) and row.get(1)]
        if len(complete_rows) < max(2, table.n_rows - 1):
            return False
        labelish = sum(1 for row in complete_rows if len(row[0]) <= 40)
        valueish = sum(1 for row in complete_rows if len(row[1]) <= 20)
        return labelish >= max(2, len(complete_rows) - 1) and valueish >= max(2, len(complete_rows) - 1)

    def union_bbox(self, blocks: list[BlockEvidence]) -> BBox:
        return union_boxes(block.bbox for block in blocks)

    def _save_crop(self, image_path: Path, bbox: BBox, crop_path: Path) -> Path:
        crop_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(image_path) as image:
            x0, y0, x1, y1 = bbox
            x0 = max(0, x0)
            y0 = max(0, y0)
            x1 = min(image.width, x1)
            y1 = min(image.height, y1)
            image.crop((x0, y0, x1, y1)).save(crop_path)
        return crop_path

    def _detect_image_boxes(self, image_path: Path, question_bbox: BBox, ocr_page: NormalizedOCRPage) -> list[BBox]:
        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            return []
        x0, y0, x1, y1 = question_bbox
        crop = image[y0:y1, x0:x1]
        if crop.size == 0:
            return []
        thresh = cv2.threshold(crop, 225, 255, cv2.THRESH_BINARY_INV)[1]
        mask = thresh.copy()
        for line in ocr_page.lines:
            if not contains(question_bbox, line.bbox, margin=8):
                continue
            lx0, ly0, lx1, ly1 = line.bbox
            cv2.rectangle(mask, (max(0, lx0 - x0 - 6), max(0, ly0 - y0 - 6)), (max(0, lx1 - x0 + 6), max(0, ly1 - y0 + 6)), 0, thickness=-1)
        for table in ocr_page.tables:
            if not contains(question_bbox, table.bbox, margin=8):
                continue
            tx0, ty0, tx1, ty1 = table.bbox
            cv2.rectangle(mask, (max(0, tx0 - x0 - 6), max(0, ty0 - y0 - 6)), (max(0, tx1 - x0 + 6), max(0, ty1 - y0 + 6)), 0, thickness=-1)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates: list[BBox] = []
        region_area = max(1, (x1 - x0) * (y1 - y0))
        for contour in contours:
            cx, cy, w, h = cv2.boundingRect(contour)
            if w < 80 or h < 80:
                continue
            area = w * h
            if area < max(5000, int(region_area * 0.004)):
                continue
            bbox = [x0 + cx, y0 + cy, x0 + cx + w, y0 + cy + h]
            if any(intersects(bbox, table.bbox) for table in ocr_page.tables):
                continue
            candidates.append(bbox)

        deduped: list[BBox] = []
        for bbox in sorted(candidates, key=lambda item: (item[1], item[0])):
            overlap = False
            for other in deduped:
                inter = [max(bbox[0], other[0]), max(bbox[1], other[1]), min(bbox[2], other[2]), min(bbox[3], other[3])]
                if box_area(inter) > 0:
                    overlap = True
                    break
            if not overlap:
                deduped.append(bbox)
        return deduped
