from __future__ import annotations

import shutil
from pathlib import Path

from src.utils.io import ensure_dir
from src.utils.types import ImageObject


class NanoBananaRefiner:
    def __init__(self, config: dict) -> None:
        self.config = config

    def refine(
        self,
        *,
        image_id: str,
        crop_path: Path,
        output_dir: Path,
        page_no: int,
        crop_bbox: list[int],
        content_type: str,
    ) -> ImageObject:
        ensure_dir(output_dir)
        refined_path = output_dir / f"{image_id}{crop_path.suffix or '.png'}"
        shutil.copy2(crop_path, refined_path)
        mode = "nanobanana_passthrough"
        if self.config.get("enabled"):
            mode = "nanobanana_pending"
        return ImageObject(
            image_id=image_id,
            origin_page=page_no,
            crop_bbox=crop_bbox,
            clean_path=str(refined_path),
            refinement_mode=mode,
            source_kind=content_type,
            uncertain=bool(self.config.get("enabled")),
        )
