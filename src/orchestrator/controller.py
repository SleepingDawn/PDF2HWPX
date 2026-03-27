from __future__ import annotations

import hashlib
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from PIL import Image

from src.adapters import ClovaGeneralAdapter, ClovaTemplateAdapter, OpenDataLoaderLayoutAdapter
from src.agents import AgentLLMRunner, AnswerAlignmentAgent, BlockTypingAgent, ExamMetaAgent, FormulaRepairAgent, QATriageAgent, QuestionSegmentationAgent, QuestionSplitAgent, SectionSplitAgent
from src.build.hwpx_writer import HwpxWriter
from src.build.pdf_preview_writer import PdfPreviewWriter
from src.build.render_model import RenderDocument
from src.ingest.renderer import render_pages
from src.layout import LayoutPlanner
from src.models.common import Issue, PageAsset, RunPaths, RunResult
from src.models.evidence import QuestionPackage, QuestionPageRange
from src.models.render import QuestionRenderModel, RenderItem
from src.ocr.table_ocr import build_simple_table
from src.orchestrator.state import PipelineState
from src.executors import BlockOcrExecutor, FormulaBuilder, NanoBananaRefiner, NoteBuilder, TableBuilder
from src.evidence import PageEvidenceBuilder, build_document_noise_profile
from src.evidence.document_noise_profile import is_noise_line
from src.qa.checklist_writer import write_checklist
from src.qa.verification import validate_hwpx_structure
from src.utils.bbox import contains, union_boxes
from src.utils.io import ensure_dir, write_json
from src.utils.text_analysis import repair_scientific_ocr_text, should_inline_equation_in_text, split_inline_chemistry_segments
from src.utils.types import AnswerNote, ChecklistIssue, Question
from src.validators import collect_validation_findings, validate_render_questions


class PipelineController:
    def __init__(self, config: dict, output_dir: Path, work_dir: Path) -> None:
        self.config = config
        self.output_dir = output_dir
        self.work_dir = work_dir
        clova_config = config.get("ocr", {}).get("clova", {})
        template_config = dict(clova_config)
        template_config.update(clova_config.get("template", {}))
        template_config.pop("template", None)
        self.ocr_adapter = ClovaGeneralAdapter(clova_config)
        self.template_adapter = ClovaTemplateAdapter(template_config)
        self.opendataloader_adapter = OpenDataLoaderLayoutAdapter(config.get("analysis", {}).get("opendataloader", {}))
        self.agent_llm_runner = AgentLLMRunner(config.get("agents", {}).get("llm", {}))
        self.agent_config = config.get("agents", {})
        self.page_evidence_builder = PageEvidenceBuilder(config)
        self.exam_meta_agent = ExamMetaAgent(self._runner_for("exam_meta"))
        self.section_split_agent = SectionSplitAgent(config.get("analysis", {}).get("answer_section_keywords", []), self._runner_for("section_split"))
        self.question_seg_agent = QuestionSegmentationAgent(runner=self._runner_for("question_segmentation"))
        self.question_split_agent = QuestionSplitAgent(self._runner_for("question_segmentation"))
        self.answer_alignment_agent = AnswerAlignmentAgent(self._runner_for("answer_alignment"))
        precise_confidence_threshold = float(config.get("ocr", {}).get("precise_block_confidence_threshold", 0.9))
        self.block_executor = BlockOcrExecutor(self.ocr_adapter, precise_confidence_threshold=precise_confidence_threshold)
        self.block_typing_agent = BlockTypingAgent(self._runner_for("block_typing"))
        self.formula_repair_agent = FormulaRepairAgent(self._runner_for("formula_repair"))
        self.formula_builder = FormulaBuilder()
        self.nanobanana_refiner = NanoBananaRefiner(config.get("image_refine", {}))
        self.table_builder = TableBuilder()
        self.note_builder = NoteBuilder()
        self.layout_planner = LayoutPlanner(first_page_no=int(config.get("layout", {}).get("first_page_no", 1)))
        self.qa_triage_agent = QATriageAgent(self._runner_for("qa_triage"))

    def _runner_for(self, agent_key: str):
        agent_settings = self.agent_config.get(agent_key, {})
        if isinstance(agent_settings, dict) and not agent_settings.get("enabled", True):
            return None
        return self.agent_llm_runner

    def run(self, pdf_path: Path) -> RunResult:
        state = self.intake(pdf_path)
        state = self.render_pages(state)
        state = self.analyze_layout(state)
        state = self.describe_template_usage(state)
        state = self.ocr_pages_with_clova(state)
        state = self.build_noise_profile(state)
        state = self.build_page_evidence(state)
        state = self.resolve_exam_meta(state)
        state = self.resolve_section_split(state)
        state = self.resolve_question_anchors(state)
        state = self.package_questions(state)
        state = self.refine_questions(state)
        state = self.build_notes(state)
        state = self.plan_layout(state)
        state = self.run_qa_triage(state)
        return self.write_outputs(state)

    def intake(self, pdf_path: Path) -> PipelineState:
        run_id = f"{pdf_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_dir = ensure_dir(self.work_dir / run_id)
        paths = RunPaths(
            run_dir=run_dir,
            pages_dir=ensure_dir(run_dir / "pages"),
            thumbs_dir=ensure_dir(run_dir / "thumbs"),
            ocr_dir=ensure_dir(run_dir / "ocr"),
            evidence_dir=ensure_dir(run_dir / "evidence"),
            decisions_dir=ensure_dir(run_dir / "decisions"),
            questions_dir=ensure_dir(run_dir / "questions"),
            crops_dir=ensure_dir(run_dir / "crops"),
            layout_dir=ensure_dir(run_dir / "layout"),
            output_dir=ensure_dir(self.output_dir),
        )
        return PipelineState(input_pdf=pdf_path, config=self.config, run_id=run_id, paths=paths)

    def render_pages(self, state: PipelineState) -> PipelineState:
        import fitz

        with fitz.open(state.input_pdf) as document:
            rendered_pages = render_pages(document, state.paths.pages_dir, dpi=int(self.config.get("render", {}).get("dpi", 300)))
        for page in rendered_pages:
            thumbnail_path = state.paths.thumbs_dir / f"page_{page.page_no:04d}.jpg"
            self._write_thumbnail(page.image_path, thumbnail_path)
            state.page_assets[page.page_no] = PageAsset(
                page_no=page.page_no,
                image_path=page.image_path,
                thumbnail_path=thumbnail_path,
                width=page.width,
                height=page.height,
                pdf_width=page.pdf_width,
                pdf_height=page.pdf_height,
                extracted_text=page.text,
                extracted_words=list(page.words),
                page_hash=self._file_hash(page.image_path),
            )
        return state

    def analyze_layout(self, state: PipelineState) -> PipelineState:
        state.opendataloader_doc = self.opendataloader_adapter.analyze_pdf(
            state.input_pdf,
            state.paths.run_dir / "opendataloader",
            state.page_assets,
        )
        return state

    def ocr_pages_with_clova(self, state: PipelineState) -> PipelineState:
        for page_no, asset in state.page_assets.items():
            raw_output_path = state.paths.ocr_dir / f"page_{page_no:04d}_raw.json"
            norm_output_path = state.paths.ocr_dir / f"page_{page_no:04d}_norm.json"
            state.ocr_pages[page_no] = self.ocr_adapter.analyze_page(
                page_no=page_no,
                image_path=asset.image_path,
                width=asset.width,
                height=asset.height,
                raw_output_path=raw_output_path,
                norm_output_path=norm_output_path,
                extracted_text=asset.extracted_text,
                extracted_words=asset.extracted_words,
            )
        return state

    def describe_template_usage(self, state: PipelineState) -> PipelineState:
        plan = self.template_adapter.describe_plan(pdf_stem=state.input_pdf.stem, page_count=len(state.page_assets))
        write_json(state.paths.decisions_dir / "template_hook.json", plan)
        if plan.get("should_apply") and state.page_assets:
            first_page = state.page_assets[min(state.page_assets)]
            extraction = self.template_adapter.analyze_first_page(
                image_path=first_page.image_path,
                output_path=state.paths.decisions_dir / "template_fields.json",
            )
            write_json(state.paths.decisions_dir / "template_fields.json", extraction)
        return state

    def build_page_evidence(self, state: PipelineState) -> PipelineState:
        for page_no, ocr_page in state.ocr_pages.items():
            evidence = self.page_evidence_builder.build(ocr_page, str(state.page_assets[page_no].thumbnail_path))
            state.page_evidences[page_no] = evidence
            write_json(state.paths.evidence_dir / f"page_{page_no:04d}.json", evidence)
        return state

    def build_noise_profile(self, state: PipelineState) -> PipelineState:
        state.noise_profile = build_document_noise_profile(state.ocr_pages)
        write_json(state.paths.decisions_dir / "document_noise_profile.json", state.noise_profile)
        return state

    def resolve_exam_meta(self, state: PipelineState) -> PipelineState:
        filename_tokens = [token for token in re.split(r"[-_]", state.input_pdf.stem) if token]
        first_page_lines = state.ocr_pages[min(state.ocr_pages)].lines if state.ocr_pages else []
        state.exam_meta = self.exam_meta_agent.resolve(
            state.input_pdf,
            filename_tokens,
            [line.text for line in first_page_lines[:8]],
        )
        self._merge_template_meta(state)
        write_json(state.paths.decisions_dir / "exam_meta.json", state.exam_meta)
        return state

    def resolve_section_split(self, state: PipelineState) -> PipelineState:
        section_pages = [self.page_evidence_builder.to_section_page(state.page_evidences[page_no]) for page_no in sorted(state.page_evidences)]
        state.section_split = self.section_split_agent.resolve(section_pages)
        write_json(state.paths.decisions_dir / "section_split.json", state.section_split)
        return state

    def resolve_question_anchors(self, state: PipelineState) -> PipelineState:
        question_pages = state.section_split.question_pages if state.section_split else sorted(state.page_evidences)
        evidences = [state.page_evidences[page_no] for page_no in sorted(state.page_evidences)]
        if state.opendataloader_doc is not None:
            odl_candidates = self.opendataloader_adapter.collect_question_anchor_candidates(state.opendataloader_doc, question_pages)
            write_json(state.paths.decisions_dir / "question_anchor_candidates_odl.json", odl_candidates)
            self._merge_odl_anchor_candidates(evidences, odl_candidates)
        detected = self.question_seg_agent.resolve(evidences, question_pages)
        state.question_anchors = self.question_split_agent.resolve(evidences, question_pages, detected)
        write_json(state.paths.decisions_dir / "question_anchors.json", state.question_anchors)
        self._record_question_anchor_issues(state)
        return state

    def package_questions(self, state: PipelineState) -> PipelineState:
        anchors = state.question_anchors.question_anchors if state.question_anchors else []
        question_pages = state.section_split.question_pages if state.section_split else sorted(state.page_assets)
        page_order = {page_no: index for index, page_no in enumerate(question_pages)}
        packages: list[QuestionPackage] = []
        for index, anchor in enumerate(anchors):
            next_anchor = anchors[index + 1] if index + 1 < len(anchors) else None
            page_ranges = self._question_page_ranges(anchor, next_anchor, anchors, question_pages, state)
            if not page_ranges:
                state.issues.append(
                    Issue(
                        question_no=anchor.question_no,
                        block_id=None,
                        severity="high",
                        category="question_package",
                        message="문항 anchor에서 유효한 페이지 범위를 만들지 못했습니다.",
                        asset=f"question_{anchor.question_no:03d}",
                    )
                )
                continue
            rough_text = self._collect_question_text(page_ranges, state)
            package = QuestionPackage(
                question_no=anchor.question_no,
                question_pages=sorted({page_range.page_no for page_range in page_ranges}),
                page_ranges=page_ranges,
                rough_text=rough_text,
                answer_pages=state.section_split.answer_pages if state.section_split else [],
            )
            question_dir = ensure_dir(state.paths.questions_dir / f"q{anchor.question_no:03d}")
            write_json(question_dir / "package.json", package)
            packages.append(package)

        packages.sort(key=lambda item: (page_order.get(item.question_pages[0], 10**6), item.question_no))
        state.question_packages = packages
        return state

    def _merge_odl_anchor_candidates(self, evidences, odl_candidates: dict[int, list[dict]]) -> None:
        for evidence in evidences:
            page_candidates = odl_candidates.get(evidence.page_no, [])
            existing = {(candidate.text, tuple(candidate.bbox)) for candidate in evidence.question_anchor_candidates}
            for candidate in page_candidates:
                key = (candidate.text, tuple(candidate.bbox))
                if key in existing:
                    continue
                evidence.question_anchor_candidates.append(candidate)
                existing.add(key)

    def _record_question_anchor_issues(self, state: PipelineState) -> None:
        if not state.question_anchors:
            return
        if not state.question_anchors.question_anchors:
            state.issues.append(
                Issue(
                    question_no=None,
                    block_id=None,
                    severity="high",
                    category="question_anchors",
                    message="문항 anchor를 확정하지 못했습니다.",
                    asset="question_anchors.json",
                )
            )
            return
        if state.question_anchors.missing_numbers:
            state.issues.append(
                Issue(
                    question_no=None,
                    block_id=None,
                    severity="high",
                    category="question_anchors",
                    message=f"문항 번호가 누락되었습니다: {state.question_anchors.missing_numbers}",
                    asset="question_anchors.json",
                )
            )
        if state.question_anchors.uncertain_anchors:
            state.issues.append(
                Issue(
                    question_no=None,
                    block_id=None,
                    severity="medium",
                    category="question_anchors",
                    message=f"문항 anchor가 불확실합니다: {state.question_anchors.uncertain_anchors}",
                    asset="question_anchors.json",
                )
            )

    def refine_questions(self, state: PipelineState) -> PipelineState:
        question_models: list[QuestionRenderModel] = []
        for package in state.question_packages:
            question_dir = ensure_dir(state.paths.questions_dir / f"q{package.question_no:03d}")
            blocks, issues = self.block_executor.build_blocks(
                package=package,
                page_assets=state.page_assets,
                ocr_pages=state.ocr_pages,
                crops_dir=question_dir / "crops",
                noise_profile=state.noise_profile,
            )
            self._apply_block_typing(blocks)
            state.issues.extend(issues)
            write_json(question_dir / "blocks.json", blocks)
            render_model = self._build_question_render_model(package, blocks, state)
            write_json(question_dir / "render_model.json", render_model)
            question_models.append(render_model)
        state.question_models = question_models
        return state

    def build_notes(self, state: PipelineState) -> PipelineState:
        if state.section_split and state.section_split.has_answer_section:
            question_numbers = [package.question_no for package in state.question_packages]
            answer_blocks = self.note_builder.collect_blocks(state.section_split.answer_pages, state.ocr_pages)
            state.answer_alignment = self.answer_alignment_agent.resolve(answer_blocks, question_numbers)
            state.answer_notes = self.note_builder.build(
                state.section_split.answer_pages,
                state.ocr_pages,
                question_numbers,
                state.answer_alignment,
            )
            write_json(state.paths.decisions_dir / "answer_alignment.json", state.answer_alignment)
            for question_no in state.answer_alignment.missing_notes:
                state.issues.append(
                    Issue(
                        question_no=question_no,
                        block_id=None,
                        severity="medium",
                        category="answer_alignment",
                        message="해설 매핑이 누락되었습니다.",
                        asset=f"question_{question_no:03d}",
                    )
                )
        else:
            from src.models.decisions import AnswerAlignmentDecision

            state.answer_alignment = AnswerAlignmentDecision(
                note_map=[],
                missing_notes=[],
                extra_notes=[],
                confidence=1.0,
                needs_review=False,
            )
            state.answer_notes = {}
        write_json(state.paths.decisions_dir / "answer_alignment.json", state.answer_alignment)
        write_json(state.paths.decisions_dir / "answer_notes.json", state.answer_notes)
        return state

    def plan_layout(self, state: PipelineState) -> PipelineState:
        legacy_questions = self._to_legacy_questions(state.question_models, state.answer_notes)
        layout_plan = self.layout_planner.plan(legacy_questions)
        write_json(state.paths.layout_dir / "layout_plan.json", layout_plan)
        return state

    def run_qa_triage(self, state: PipelineState) -> PipelineState:
        triage = self.qa_triage_agent.resolve(state.issues, len(state.question_models))
        write_json(state.paths.decisions_dir / "qa_triage.json", triage)
        by_question: dict[int, list[dict]] = {}
        for issue in triage.issues:
            if issue.get("question_no") is None:
                continue
            by_question.setdefault(int(issue["question_no"]), []).append(issue)
        for model in state.question_models:
            for issue in by_question.get(model.question_no, []):
                if issue.get("insert_marker") and "qa_review_required" not in model.uncertainties:
                    model.uncertainties.append("qa_review_required")
                    for item in model.items:
                        if item.type == "text" and item.content:
                            item.content = f"[불확실] {item.content}"
                            break
        return state

    def write_outputs(self, state: PipelineState) -> RunResult:
        legacy_questions = self._to_legacy_questions(state.question_models, state.answer_notes)
        validation_findings = collect_validation_findings(legacy_questions)
        for finding in validation_findings:
            state.issues.append(
                Issue(
                    question_no=finding.get("question_no"),
                    block_id=None,
                    severity=finding.get("severity", "high"),
                    category=finding.get("category", "final_consistency"),
                    message=finding.get("message", "validation_failed"),
                    asset=finding.get("asset", state.run_id),
                )
            )
        output_hwpx = state.paths.output_dir / f"{state.input_pdf.stem}.hwpx"
        output_pdf = state.paths.output_dir / f"{state.input_pdf.stem}.pdf"
        legacy_notes = self._to_legacy_notes(state.answer_notes)
        render_document = RenderDocument(title=state.input_pdf.stem, questions=legacy_questions, notes=legacy_notes)
        HwpxWriter(output_hwpx).write(render_document)
        PdfPreviewWriter(output_pdf).write(render_document)
        state.verification = validate_hwpx_structure(output_hwpx)
        write_json(state.paths.decisions_dir / "hwpx_verification.json", state.verification)

        checklist_path = state.paths.output_dir / f"{state.input_pdf.stem}_checklist.txt"
        checklist_issues = self._to_checklist_issues(state.issues, output_hwpx.name)
        if checklist_issues:
            write_checklist(checklist_path, output_hwpx.name, checklist_issues)
        elif checklist_path.exists():
            checklist_path.unlink()

        return RunResult(
            hwpx_path=str(output_hwpx),
            checklist_path=str(checklist_path) if checklist_issues else None,
            questions=len(legacy_questions),
            has_answer_section=bool(state.section_split and state.section_split.has_answer_section),
            verification=state.verification,
            run_dir=str(state.paths.run_dir),
            issues=list(state.issues),
        )

    def _question_page_ranges(self, anchor, next_anchor, anchors, question_pages: list[int], state: PipelineState) -> list[QuestionPageRange]:
        page_ranges: list[QuestionPageRange] = []
        if anchor.page_no not in question_pages:
            return page_ranges
        page_asset = state.page_assets[anchor.page_no]
        page_anchors = [item for item in anchors if item.page_no == anchor.page_no]
        x0, x1 = self._column_bounds(anchor, page_anchors, page_asset.width)
        same_column_next = self._next_same_column_anchor(anchor, page_anchors, page_asset.width)
        y1 = page_asset.height if same_column_next is None else max(anchor.bbox[1] + 10, same_column_next.bbox[1] - 4)
        footer_top = state.noise_profile.footer_top if state.noise_profile else None
        if footer_top is not None and y1 > footer_top:
            y1 = max(anchor.bbox[3] + 8, footer_top - 12)
        page_ranges.append(QuestionPageRange(page_no=anchor.page_no, bbox=[x0, anchor.bbox[1], x1, y1]))
        return page_ranges

    def _collect_question_text(self, page_ranges: list[QuestionPageRange], state: PipelineState) -> str:
        if state.opendataloader_doc is not None:
            rough_text = self.opendataloader_adapter.collect_question_text(state.opendataloader_doc, page_ranges).strip()
            if rough_text:
                return rough_text
        texts: list[str] = []
        for page_range in page_ranges:
            ocr_page = state.ocr_pages[page_range.page_no]
            use_word_lines = (page_range.bbox[2] - page_range.bbox[0]) < max(1, int(ocr_page.width * 0.85))
            if use_word_lines:
                words = [word for word in ocr_page.words if contains(page_range.bbox, word.bbox, margin=8)]
                rows: list[list] = []
                for word in sorted(words, key=lambda item: (item.bbox[1], item.bbox[0])):
                    if not rows or abs(word.bbox[1] - rows[-1][-1].bbox[1]) > 28:
                        rows.append([word])
                    else:
                        rows[-1].append(word)
                for row in rows:
                    text = " ".join(word.text for word in sorted(row, key=lambda item: item.bbox[0]) if word.text.strip()).strip()
                    xs = [word.bbox[0] for word in row] + [word.bbox[2] for word in row]
                    ys = [word.bbox[1] for word in row] + [word.bbox[3] for word in row]
                    row_bbox = [min(xs), min(ys), max(xs), max(ys)]
                    if text and not is_noise_line(state.noise_profile, text, row_bbox, ocr_page.height):
                        texts.append(text)
                continue
            for line in ocr_page.lines:
                if contains(page_range.bbox, line.bbox, margin=8) and not is_noise_line(state.noise_profile, line.text, line.bbox, ocr_page.height):
                    texts.append(line.text)
        return "\n".join(texts)

    def _column_bounds(self, anchor, page_anchors, page_width: int) -> tuple[int, int]:
        centers = [((item.bbox[0] + item.bbox[2]) / 2) for item in page_anchors]
        if len(centers) < 2:
            return (0, page_width)
        spread = max(centers) - min(centers)
        if spread < page_width * 0.2:
            return (0, page_width)
        split_x = page_width // 2
        center = (anchor.bbox[0] + anchor.bbox[2]) / 2
        if center <= split_x:
            return (0, split_x - 8)
        return (split_x + 8, page_width)

    def _next_same_column_anchor(self, anchor, page_anchors, page_width: int):
        anchor_bounds = self._column_bounds(anchor, page_anchors, page_width)
        candidates = []
        for item in page_anchors:
            if item.question_no == anchor.question_no:
                continue
            item_bounds = self._column_bounds(item, page_anchors, page_width)
            if item_bounds != anchor_bounds:
                continue
            if item.bbox[1] <= anchor.bbox[1]:
                continue
            candidates.append(item)
        if not candidates:
            return None
        return min(candidates, key=lambda item: item.bbox[1])

    def _build_question_render_model(self, package: QuestionPackage, blocks, state: PipelineState) -> QuestionRenderModel:
        items: list[RenderItem] = []
        uncertainties: list[str] = []
        item_index = 1
        bbox_union = union_boxes(block.bbox for block in blocks) if blocks else [0, 0, 0, 0]
        for block in blocks:
            block_type = block.final_type or (block.type_candidates[0].type if block.type_candidates else "unknown")
            if block_type == "table":
                ocr_tables = [asdict(table) for table in state.ocr_pages[block.page_no].tables]
                table_object, stable = self.table_builder.build(
                    table_id=f"q{package.question_no}_tbl{item_index}",
                    bbox=block.bbox,
                    ocr_tables=ocr_tables,
                )
                if table_object is not None and stable:
                    items.append(
                        RenderItem(
                            item_id=f"q{package.question_no}_i{item_index}",
                            type="table",
                            source_block_id=block.block_id,
                            object_ref=table_object,
                            uncertain=block.needs_review,
                        )
                    )
                else:
                    image_object = self.nanobanana_refiner.refine(
                        image_id=f"q{package.question_no}_tblimg{item_index}",
                        crop_path=Path(block.crop_path),
                        output_dir=state.paths.questions_dir / f"q{package.question_no:03d}" / "nanobanana",
                        page_no=block.page_no,
                        crop_bbox=block.bbox,
                        content_type="table",
                    )
                    items.append(
                        RenderItem(
                            item_id=f"q{package.question_no}_i{item_index}",
                            type="image",
                            source_block_id=block.block_id,
                            object_ref=image_object,
                            uncertain=True,
                        )
                    )
                    uncertainties.append("table_preserved_as_image")
            elif block_type in {"equation", "chem_equation"}:
                if block_type == "chem_equation" and should_inline_equation_in_text(block.ocr_text):
                    content = repair_scientific_ocr_text(block.ocr_text)
                    segments = split_inline_chemistry_segments(content)
                    items.append(
                        RenderItem(
                            item_id=f"q{package.question_no}_i{item_index}",
                            type="text",
                            source_block_id=block.block_id,
                            content=content,
                            segments=segments,
                            uncertain=block.needs_review,
                        )
                    )
                    if block.needs_review:
                        uncertainties.append("equation_conversion_low_confidence")
                else:
                    decision = self.formula_repair_agent.resolve(block.block_id, block_type, block.ocr_text)
                    items.append(self.formula_builder.build(f"q{package.question_no}_i{item_index}", block.block_id, decision))
                    if decision.needs_review or block.needs_review:
                        uncertainties.append("equation_conversion_low_confidence")
            elif block_type == "image":
                image_object = self.nanobanana_refiner.refine(
                    image_id=f"q{package.question_no}_img{item_index}",
                    crop_path=Path(block.crop_path),
                    output_dir=state.paths.questions_dir / f"q{package.question_no:03d}" / "nanobanana",
                    page_no=block.page_no,
                    crop_bbox=block.bbox,
                    content_type="image",
                )
                items.append(
                    RenderItem(
                        item_id=f"q{package.question_no}_i{item_index}",
                        type="image",
                        source_block_id=block.block_id,
                        object_ref=image_object,
                        uncertain=image_object.uncertain,
                    )
                )
                if image_object.uncertain:
                    uncertainties.append("image_refine_pending")
            else:
                content = repair_scientific_ocr_text(block.ocr_text)
                segments = split_inline_chemistry_segments(content)
                items.append(
                    RenderItem(
                        item_id=f"q{package.question_no}_i{item_index}",
                        type="text",
                        source_block_id=block.block_id,
                        content=content,
                        segments=segments,
                        uncertain=block.ocr_confidence < float(self.config.get("ocr", {}).get("confidence_threshold", 0.78)) or block.needs_review,
                    )
                )
                if block.ocr_confidence < float(self.config.get("ocr", {}).get("confidence_threshold", 0.78)) or block.needs_review:
                    uncertainties.append("ocr_confidence_below_threshold")
            item_index += 1

        if not items:
            items = [
                RenderItem(
                    item_id=f"q{package.question_no}_i1",
                    type="text",
                    source_block_id=f"q{package.question_no}_fallback",
                    content="[불확실]",
                    uncertain=True,
                )
            ]
            uncertainties.append("ambiguous_question_anchor")

        return QuestionRenderModel(
            question_no=package.question_no,
            pages=package.question_pages,
            bbox_union=bbox_union,
            items=items,
            tagline=state.exam_meta.tagline if state.exam_meta else None,
            uncertainties=sorted(set(uncertainties)),
        )

    def _apply_block_typing(self, blocks) -> None:
        for index, block in enumerate(blocks):
            surrounding_parts: list[str] = []
            if index > 0:
                surrounding_parts.append(blocks[index - 1].ocr_text)
            if index + 1 < len(blocks):
                surrounding_parts.append(blocks[index + 1].ocr_text)
            decision = self.block_typing_agent.resolve(
                block_id=block.block_id,
                ocr_text=block.ocr_text,
                type_candidates=block.type_candidates,
                surrounding_text=" ".join(part for part in surrounding_parts if part),
                has_table_lines=block.table_candidate,
                has_image_texture=any(candidate.type == "image" and candidate.score >= 0.9 for candidate in block.type_candidates),
            )
            block.final_type = decision.final_type
            block.final_type_confidence = decision.confidence
            block.needs_review = decision.needs_review

    def _to_legacy_questions(self, question_models: list[QuestionRenderModel], answer_notes) -> list[Question]:
        questions: list[Question] = []
        for model in question_models:
            items = []
            for item in model.items:
                payload = {"type": item.type}
                if item.type == "table":
                    payload["object"] = item.object_ref or build_simple_table(f"q{model.question_no}_fallback", [["[불확실]"]])
                elif item.type in {"equation", "chem_equation"}:
                    payload["target"] = item.target_repr or item.content or ""
                elif item.type == "image":
                    payload["object"] = item.object_ref
                else:
                    payload["content"] = item.content or ""
                    if item.segments:
                        payload["segments"] = list(item.segments)
                items.append(payload)
            questions.append(
                Question(
                    question_no=model.question_no,
                    pages=model.pages,
                    bbox_union=model.bbox_union,
                    has_note=model.question_no in answer_notes and answer_notes[model.question_no].exists,
                    note_ref_no=model.question_no if model.question_no in answer_notes and answer_notes[model.question_no].exists else None,
                    items=items,
                    tagline=model.tagline,
                    uncertainties=list(model.uncertainties),
                )
            )
        return questions

    def _to_legacy_notes(self, notes: dict[int, object]) -> dict[int, AnswerNote]:
        return {
            question_no: AnswerNote(
                question_no=question_no,
                exists=note.exists,
                blocks=list(note.blocks),
                raw_text=note.raw_text,
                has_explanation=note.has_explanation,
                uncertainties=list(note.uncertainties),
            )
            for question_no, note in notes.items()
        }

    def _to_checklist_issues(self, issues: list[Issue], hwpx_name: str) -> list[ChecklistIssue]:
        checklist: list[ChecklistIssue] = []
        for issue in issues:
            if issue.question_no is None:
                continue
            checklist.append(
                ChecklistIssue(
                    question_no=issue.question_no,
                    severity=issue.severity,
                    category=issue.category,
                    message=issue.message,
                    page=issue.question_no,
                    asset=issue.asset or hwpx_name,
                )
            )
        return checklist

    def _write_thumbnail(self, image_path: Path, thumbnail_path: Path) -> None:
        with Image.open(image_path) as image:
            copy = image.copy()
            copy.thumbnail((480, 480))
            copy.save(thumbnail_path, format="JPEG", quality=82)

    def _file_hash(self, path: Path) -> str:
        digest = hashlib.sha1()
        digest.update(path.read_bytes())
        return digest.hexdigest()

    def _merge_template_meta(self, state: PipelineState) -> None:
        template_path = state.paths.decisions_dir / "template_fields.json"
        if not template_path.exists() or state.exam_meta is None:
            return
        import json

        template_result = json.loads(template_path.read_text(encoding="utf-8"))
        fields = template_result.get("fields", {})
        mapping = {
            "school": ["school", "학교", "school_name"],
            "subject": ["subject", "과목", "subject_name"],
            "exam_type": ["exam_type", "시험구분", "시험", "exam"],
            "year": ["year", "년도", "학년도"],
            "grade": ["grade", "학년"],
            "semester": ["semester", "학기"],
        }
        for attr, aliases in mapping.items():
            current = getattr(state.exam_meta, attr)
            if current:
                continue
            for alias in aliases:
                value = fields.get(alias)
                if value:
                    setattr(state.exam_meta, attr, value)
                    state.exam_meta.field_sources[attr] = "template"
                    break
        if state.exam_meta.year and state.exam_meta.school and state.exam_meta.grade and state.exam_meta.semester and state.exam_meta.exam_type:
            state.exam_meta.tagline = f"({state.exam_meta.year}년 {state.exam_meta.school} {state.exam_meta.grade} {state.exam_meta.semester} {state.exam_meta.exam_type})"
