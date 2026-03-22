from __future__ import annotations

from pathlib import Path

from src.restore.inpaint import inpaint_image
from src.restore.upscale import upscale_image


def restore_image(image_path: Path, mask_path: Path, restored_dir: Path, radius: int, factor: float) -> tuple[Path, str]:
    inpainted_path = restored_dir / f"{image_path.stem}_inpaint.png"
    upscaled_path = restored_dir / f"{image_path.stem}_clean.png"
    inpaint_image(image_path, mask_path, inpainted_path, radius)
    upscale_image(inpainted_path, upscaled_path, factor)
    return upscaled_path, "inpaint_then_upscale"
