from __future__ import annotations

import re
from pathlib import Path

import cv2

from src.analysis.handwriting_mask import build_handwriting_mask
from src.utils.bbox import intersects, union_boxes


def _classify_text(text: str) -> str:
    stripped = text.strip()
    if re.search(r"[A-Z][a-z]?\d", stripped) and any(token in stripped for token in ["->", "→", "⇌", "+"]):
        return "chem_equation"
    if any(token in stripped for token in ["=", "∫", "√", "Σ", "/", "^"]):
        return "equation"
    return "text"


def _detect_tables(image_path: Path) -> list[list[int]]:
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    thresh = cv2.threshold(image, 210, 255, cv2.THRESH_BINARY_INV)[1]
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
    horizontal = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_h)
    vertical = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_v)
    lines = cv2.bitwise_or(horizontal, vertical)
    contours, _ = cv2.findContours(lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    page_area = image.shape[0] * image.shape[1]
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w <= 120 or h <= 60:
            continue
        if (w * h) > page_area * 0.45:
            continue
        crop_h = horizontal[y:y + h, x:x + w]
        crop_v = vertical[y:y + h, x:x + w]
        horizontal_runs = cv2.countNonZero(cv2.reduce(crop_h, 1, cv2.REDUCE_MAX))
        vertical_runs = cv2.countNonZero(cv2.reduce(crop_v, 0, cv2.REDUCE_MAX))
        if horizontal_runs < 2 or vertical_runs < 2:
            continue
        boxes.append([x, y, x + w, y + h])
    boxes.sort(key=lambda box: (box[1], box[0]))
    return boxes


def _group_rows(words: list[dict], tolerance: int = 24) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda item: (item["bbox"][1], item["bbox"][0])):
        center_y = (word["bbox"][1] + word["bbox"][3]) / 2
        if not rows:
            rows.append([word])
            continue
        last_center = sum((item["bbox"][1] + item["bbox"][3]) / 2 for item in rows[-1]) / len(rows[-1])
        if abs(center_y - last_center) <= tolerance:
            rows[-1].append(word)
        else:
            rows.append([word])
    return [sorted(row, key=lambda item: item["bbox"][0]) for row in rows]


def _detect_word_tables(words: list[dict], page_width: int, page_height: int) -> list[list[int]]:
    candidate_rows: list[dict] = []
    for row in _group_rows(words):
        if len(row) < 2 or len(row) > 8:
            continue
        gaps = [row[index + 1]["bbox"][0] - row[index]["bbox"][2] for index in range(len(row) - 1)]
        max_gap = max(gaps, default=0)
        if max_gap < max(120, page_width // 18):
            continue
        candidate_rows.append(
            {
                "separator_x": row[gaps.index(max_gap)]["bbox"][2] + max_gap // 2,
                "bbox": union_boxes(word["bbox"] for word in row),
                "words": row,
            }
        )

    boxes: list[list[int]] = []
    streak: list[dict] = []
    for row in candidate_rows:
        if not streak:
            streak = [row]
            continue
        prev = streak[-1]
        same_band = abs(row["separator_x"] - prev["separator_x"]) <= 120 and row["bbox"][1] - prev["bbox"][3] <= 110
        if same_band:
            streak.append(row)
        else:
            if len(streak) >= 3:
                box = union_boxes(item["bbox"] for item in streak)
                if (box[2] - box[0]) > page_width * 0.18 and (box[3] - box[1]) > page_height * 0.06:
                    boxes.append(box)
            streak = [row]
    if len(streak) >= 3:
        box = union_boxes(item["bbox"] for item in streak)
        if (box[2] - box[0]) > page_width * 0.18 and (box[3] - box[1]) > page_height * 0.06:
            boxes.append(box)
    return boxes


def _dedupe_boxes(boxes: list[list[int]], tolerance: int = 24) -> list[list[int]]:
    deduped: list[list[int]] = []
    for box in sorted(boxes, key=lambda item: (item[1], item[0])):
        if any(
            abs(box[0] - other[0]) <= tolerance
            and abs(box[1] - other[1]) <= tolerance
            and abs(box[2] - other[2]) <= tolerance
            and abs(box[3] - other[3]) <= tolerance
            for other in deduped
        ):
            continue
        deduped.append(box)
    return deduped


def _detect_images(image_path: Path, text_boxes: list[list[int]], table_boxes: list[list[int]], min_area_ratio: float) -> list[list[int]]:
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    height, width = image.shape[:2]
    page_area = max(1, height * width)
    thresh = cv2.threshold(image, 210, 255, cv2.THRESH_BINARY_INV)[1]

    mask = thresh.copy()
    for x0, y0, x1, y1 in text_boxes + table_boxes:
        cv2.rectangle(mask, (max(0, x0 - 8), max(0, y0 - 8)), (min(width, x1 + 8), min(height, y1 + 8)), 0, thickness=-1)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[list[int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < page_area * min_area_ratio:
            continue
        if area > page_area * 0.42:
            continue
        if w < 80 or h < 80:
            continue
        candidate = [x, y, x + w, y + h]
        if any(intersects(candidate, table_box) for table_box in table_boxes):
            continue
        boxes.append(candidate)
    boxes.sort(key=lambda box: (box[1], box[0]))
    return boxes


def analyze_page_layout(page: dict, output_mask_path: Path, config: dict) -> dict:
    image_path = Path(page["image_path"])
    text_blocks = []
    anchors = []
    for word in page["words"]:
        block_type = _classify_text(word["text"])
        text_blocks.append(
            {
                "bbox": word["bbox"],
                "type": block_type,
                "text": word["text"],
                "confidence": word.get("confidence", 0.95),
                "block_no": word.get("block_no"),
                "line_no": word.get("line_no"),
                "word_no": word.get("word_no"),
            }
        )
        if re.fullmatch(config["question_anchor_pattern"], word["text"]):
            anchors.append({"question_no": int(word["text"].rstrip(".")), "bbox": word["bbox"]})

    image = cv2.imread(str(image_path))
    table_boxes = _dedupe_boxes(_detect_tables(image_path) + _detect_word_tables(page["words"], image.shape[1], image.shape[0]))
    table_blocks = [{"bbox": box, "type": "table"} for box in table_boxes]
    mask_path = build_handwriting_mask(image_path, output_mask_path, config)
    image_boxes = _detect_images(
        image_path=image_path,
        text_boxes=[item["bbox"] for item in text_blocks],
        table_boxes=table_boxes,
        min_area_ratio=config["image_min_area_ratio"],
    )
    image_blocks = [{"bbox": box, "type": "image"} for box in image_boxes]

    return {
        "page_no": page["page_no"],
        "blocks": text_blocks + table_blocks + image_blocks,
        "anchors": anchors,
        "mask_path": str(mask_path),
    }
