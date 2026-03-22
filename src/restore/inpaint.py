from __future__ import annotations

from pathlib import Path

import cv2

from src.utils.io import ensure_dir


def inpaint_image(image_path: Path, mask_path: Path, output_path: Path, radius: int) -> Path:
    ensure_dir(output_path.parent)
    image = cv2.imread(str(image_path))
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    restored = cv2.inpaint(image, mask, radius, cv2.INPAINT_TELEA)
    cv2.imwrite(str(output_path), restored)
    return output_path
