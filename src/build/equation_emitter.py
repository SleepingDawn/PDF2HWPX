from __future__ import annotations

from lxml import etree


def emit_equation(parent: etree._Element, equation_text: str) -> None:
    element = etree.SubElement(parent, "equation")
    element.text = equation_text
