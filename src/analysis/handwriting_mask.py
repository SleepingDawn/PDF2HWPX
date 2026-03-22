from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from src.utils.io import ensure_dir


def build_handwriting_mask(image_path: Path, output_path: Path, config: dict) -> Path:
    ensure_dir(output_path.parent)
    image = cv2.imread(str(image_path))
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    blue_mask = cv2.inRange(
        hsv,
        np.array(config["handwriting_blue_lower"], dtype=np.uint8),
        np.array(config["handwriting_blue_upper"], dtype=np.uint8),
    )
    red_mask_1 = cv2.inRange(
        hsv,
        np.array(config["handwriting_red_lower_1"], dtype=np.uint8),
        np.array(config["handwriting_red_upper_1"], dtype=np.uint8),
    )
    red_mask_2 = cv2.inRange(
        hsv,
        np.array(config["handwriting_red_lower_2"], dtype=np.uint8),
        np.array(config["handwriting_red_upper_2"], dtype=np.uint8),
    )
    mask = cv2.bitwise_or(blue_mask, cv2.bitwise_or(red_mask_1, red_mask_2))
    cv2.imwrite(str(output_path), mask)
    return output_path
