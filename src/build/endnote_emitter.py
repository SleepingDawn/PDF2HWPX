from __future__ import annotations

from lxml import etree

from src.utils.types import AnswerNote


def emit_endnote(parent: etree._Element, note: AnswerNote) -> None:
    note_element = etree.SubElement(parent, "endnote", question_no=str(note.question_no))
    for block in note.blocks:
        block_element = etree.SubElement(note_element, block["type"])
        block_element.text = block.get("content", "")
