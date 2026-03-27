from __future__ import annotations

from src.models.ocr import NormalizedOCRPage, OCRLine, OCRTable, OCRTableCell, OCRWord


def normalize_clova_page(
    *,
    page_no: int,
    image_path: str,
    width: int,
    height: int,
    raw_ref: str | None,
    raw_response: dict,
    normalized_payload: dict,
) -> NormalizedOCRPage:
    lines = [
        OCRLine(
            line_id=f"p{page_no}_l{index}",
            text=(line.get("text") or "").strip(),
            bbox=[int(value) for value in line.get("bbox", [0, 0, 0, 0])],
            confidence=float(line.get("confidence", 0.0)),
        )
        for index, line in enumerate(normalized_payload.get("lines", []), start=1)
        if (line.get("text") or "").strip()
    ]
    words = _raw_words(page_no, raw_response)
    tables = _normalized_tables(page_no, normalized_payload)
    return NormalizedOCRPage(
        page_no=page_no,
        image_path=image_path,
        width=width,
        height=height,
        lines=lines,
        words=words,
        tables=tables,
        raw_ref=raw_ref,
        backend=str(normalized_payload.get("backend", "clova_general")),
    )


def synthesize_page_from_pdf(
    *,
    page_no: int,
    image_path: str,
    width: int,
    height: int,
    extracted_text: str,
    extracted_words: list[dict],
    raw_ref: str | None = None,
) -> NormalizedOCRPage:
    lines = _lines_from_words(page_no, extracted_words, extracted_text)
    words = [
        OCRWord(
            word_id=f"p{page_no}_w{index}",
            text=(word.get("text") or "").strip(),
            bbox=[int(value) for value in word.get("bbox", [0, 0, 0, 0])],
            confidence=float(word.get("confidence", 1.0)),
        )
        for index, word in enumerate(extracted_words, start=1)
        if (word.get("text") or "").strip()
    ]
    return NormalizedOCRPage(
        page_no=page_no,
        image_path=image_path,
        width=width,
        height=height,
        lines=lines,
        words=words,
        tables=[],
        raw_ref=raw_ref,
        backend="pdf_text_stub",
    )


def _lines_from_words(page_no: int, extracted_words: list[dict], extracted_text: str) -> list[OCRLine]:
    grouped: dict[tuple[int, int], list[dict]] = {}
    for word in extracted_words:
        key = (int(word.get("block_no", 0)), int(word.get("line_no", 0)))
        grouped.setdefault(key, []).append(word)

    if not grouped and extracted_text.strip():
        synthetic_lines = []
        for index, line in enumerate(extracted_text.splitlines(), start=1):
            text = line.strip()
            if not text:
                continue
            synthetic_lines.append(
                OCRLine(
                    line_id=f"p{page_no}_l{index}",
                    text=text,
                    bbox=[0, index * 40, 1000, index * 40 + 24],
                    confidence=1.0,
                )
            )
        return synthetic_lines

    lines: list[OCRLine] = []
    for index, key in enumerate(sorted(grouped), start=1):
        row = sorted(grouped[key], key=lambda item: item.get("word_no", 0))
        xs = [int(word["bbox"][0]) for word in row] + [int(word["bbox"][2]) for word in row]
        ys = [int(word["bbox"][1]) for word in row] + [int(word["bbox"][3]) for word in row]
        text = " ".join((word.get("text") or "").strip() for word in row if (word.get("text") or "").strip())
        if not text:
            continue
        confidence = sum(float(word.get("confidence", 1.0)) for word in row) / max(1, len(row))
        lines.append(
            OCRLine(
                line_id=f"p{page_no}_l{index}",
                text=text,
                bbox=[min(xs), min(ys), max(xs), max(ys)],
                confidence=confidence,
            )
        )
    return lines


def _raw_words(page_no: int, raw_response: dict) -> list[OCRWord]:
    images = raw_response.get("images", [])
    if not images:
        return []
    fields = images[0].get("fields", []) or []
    words: list[OCRWord] = []
    for index, field in enumerate(fields, start=1):
        text = (field.get("inferText") or "").strip()
        if not text:
            continue
        words.append(
            OCRWord(
                word_id=f"p{page_no}_w{index}",
                text=text,
                bbox=_poly_to_bbox(field.get("boundingPoly", {}).get("vertices", [])),
                confidence=float(field.get("inferConfidence", 0.0)),
            )
        )
    return words


def _normalized_tables(page_no: int, normalized_payload: dict) -> list[OCRTable]:
    tables: list[OCRTable] = []
    for index, table in enumerate(normalized_payload.get("tables", []), start=1):
        cells = [
            OCRTableCell(
                row=int(cell.get("row", 0)),
                col=int(cell.get("col", 0)),
                rowspan=int(cell.get("rowspan", 1)),
                colspan=int(cell.get("colspan", 1)),
                bbox=[int(value) for value in cell.get("bbox", [0, 0, 0, 0])],
                text=(cell.get("text") or "").strip(),
                confidence=float(cell.get("confidence", 0.0)),
            )
            for cell in table.get("cells", [])
        ]
        tables.append(
            OCRTable(
                table_id=str(table.get("id") or f"p{page_no}_t{index}"),
                bbox=[int(value) for value in table.get("bbox", [0, 0, 0, 0])],
                confidence=float(table.get("confidence", 0.0)),
                n_rows=int(table.get("n_rows", 0)),
                n_cols=int(table.get("n_cols", 0)),
                cells=cells,
            )
        )
    return tables


def _poly_to_bbox(vertices: list[dict]) -> list[int]:
    if not vertices:
        return [0, 0, 0, 0]
    xs = [int(vertex.get("x", 0)) for vertex in vertices]
    ys = [int(vertex.get("y", 0)) for vertex in vertices]
    return [min(xs), min(ys), max(xs), max(ys)]
