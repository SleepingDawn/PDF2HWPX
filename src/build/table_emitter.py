from __future__ import annotations

from lxml import etree

from src.utils.types import TableObject


def emit_table(parent: etree._Element, table: TableObject) -> None:
    table_element = etree.SubElement(parent, "table", rows=str(table.n_rows), cols=str(table.n_cols), anchor=table.anchor)
    for cell in table.cells:
        cell_element = etree.SubElement(
            table_element,
            "cell",
            row=str(cell.row),
            col=str(cell.col),
            rowspan=str(cell.rowspan),
            colspan=str(cell.colspan),
        )
        cell_element.text = " ".join(item["text"] for item in cell.content if item["type"] == "text")
