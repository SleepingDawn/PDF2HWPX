from __future__ import annotations

from pathlib import Path

import cv2

from src.utils.io import ensure_dir


def upscale_image(image_path: Path, output_path: Path, factor: float) -> Path:
    ensure_dir(output_path.parent)
    image = cv2.imread(str(image_path))
    width = int(image.shape[1] * factor)
    height = int(image.shape[0] * factor)
    resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(str(output_path), resized)
    return output_path
