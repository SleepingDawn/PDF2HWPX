from __future__ import annotations

from lxml import etree

from src.utils.types import ImageObject


def emit_image(parent: etree._Element, image: ImageObject, media_ref: str) -> None:
    etree.SubElement(
        parent,
        "image",
        id=image.image_id,
        src=media_ref,
        anchor=image.anchor,
        width_policy=image.width_policy,
        uncertain=str(image.uncertain).lower(),
    )
