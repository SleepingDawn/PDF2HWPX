from __future__ import annotations

from pathlib import Path

from src.adapters import ClovaGeneralAdapter
from src.evidence.question_evidence import QuestionEvidenceBuilder
from src.models.common import Issue, PageAsset
from src.models.evidence import BlockEvidence, DocumentNoiseProfile, QuestionPackage
from src.models.ocr import NormalizedOCRPage


class BlockOcrExecutor:
    def __init__(self, ocr_adapter: ClovaGeneralAdapter, precise_confidence_threshold: float = 0.9) -> None:
        self.builder = QuestionEvidenceBuilder()
        self.ocr_adapter = ocr_adapter
        self.precise_confidence_threshold = precise_confidence_threshold

    def build_blocks(
        self,
        *,
        package: QuestionPackage,
        page_assets: dict[int, PageAsset],
        ocr_pages: dict[int, NormalizedOCRPage],
        crops_dir: Path,
        noise_profile: DocumentNoiseProfile | None = None,
    ) -> tuple[list[BlockEvidence], list[Issue]]:
        blocks, issues = self.builder.build(
            package=package,
            page_assets=page_assets,
            ocr_pages=ocr_pages,
            crops_dir=crops_dir,
            noise_profile=noise_profile,
        )
        precise_dir = crops_dir.parent / "block_ocr"
        for block in blocks:
            if not self._should_refine_block(block):
                continue
            raw_output_path = precise_dir / f"{block.block_id}_raw.json"
            norm_output_path = precise_dir / f"{block.block_id}_norm.json"
            normalized = self.ocr_adapter.analyze_crop(
                crop_id=block.block_id,
                image_path=Path(block.crop_path),
                raw_output_path=raw_output_path,
                norm_output_path=norm_output_path,
                fallback_text=block.ocr_text,
                page_no=block.page_no,
            )
            refined_lines = [line.text for line in normalized.lines if line.text.strip()]
            refined_text = "\n".join(refined_lines).strip()
            if refined_text:
                block.coarse_ocr_text = block.ocr_text
                block.coarse_ocr_confidence = block.ocr_confidence
                block.ocr_text = refined_text
                block.ocr_confidence = max((line.confidence for line in normalized.lines), default=block.ocr_confidence)
                block.ocr_engine = "block_ocr"
        return blocks, issues

    def _should_refine_block(self, block: BlockEvidence) -> bool:
        if block.table_candidate:
            return False
        if any(candidate.type == "image" and candidate.score >= 0.9 for candidate in block.type_candidates):
            return False
        if block.ocr_confidence < self.precise_confidence_threshold:
            return True
        top_type = block.type_candidates[0].type if block.type_candidates else "text"
        return top_type in {"equation", "chem_equation"} and block.ocr_confidence < 0.98
