from __future__ import annotations

from typing import Iterable


def union_boxes(boxes: Iterable[list[int]]) -> list[int]:
    boxes = list(boxes)
    if not boxes:
        return [0, 0, 0, 0]
    xs0 = [box[0] for box in boxes]
    ys0 = [box[1] for box in boxes]
    xs1 = [box[2] for box in boxes]
    ys1 = [box[3] for box in boxes]
    return [min(xs0), min(ys0), max(xs1), max(ys1)]


def box_area(box: list[int]) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def intersects(box_a: list[int], box_b: list[int]) -> bool:
    return not (
        box_a[2] <= box_b[0]
        or box_a[0] >= box_b[2]
        or box_a[3] <= box_b[1]
        or box_a[1] >= box_b[3]
    )


def intersection(box_a: list[int], box_b: list[int]) -> list[int]:
    if not intersects(box_a, box_b):
        return [0, 0, 0, 0]
    return [
        max(box_a[0], box_b[0]),
        max(box_a[1], box_b[1]),
        min(box_a[2], box_b[2]),
        min(box_a[3], box_b[3]),
    ]


def contains(outer: list[int], inner: list[int], margin: int = 0) -> bool:
    return (
        inner[0] >= outer[0] - margin
        and inner[1] >= outer[1] - margin
        and inner[2] <= outer[2] + margin
        and inner[3] <= outer[3] + margin
    )
