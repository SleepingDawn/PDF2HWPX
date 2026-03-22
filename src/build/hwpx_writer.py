from __future__ import annotations

import io
import mimetypes
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from lxml import etree
from PIL import Image

from src.build.render_model import RenderDocument
from src.utils.io import ensure_dir


NS = {
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hp10": "http://www.hancom.co.kr/hwpml/2016/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hhs": "http://www.hancom.co.kr/hwpml/2011/history",
    "hm": "http://www.hancom.co.kr/hwpml/2011/master-page",
    "hpf": "http://www.hancom.co.kr/schema/2011/hpf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": "http://www.idpf.org/2007/opf/",
    "ooxmlchart": "http://www.hancom.co.kr/hwpml/2016/ooxmlchart",
    "hwpunitchar": "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar",
    "epub": "http://www.idpf.org/2007/ops",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
    "hv": "http://www.hancom.co.kr/hwpml/2011/version",
    "ocf": "urn:oasis:names:tc:opendocument:xmlns:container",
    "odf": "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "pkg": "http://www.hancom.co.kr/hwpml/2016/meta/pkg#",
}

REFERENCE_TEMPLATE_PATH = Path("/Users/seyong/Desktop/요섭쌤 화학 조교/PDF2HWPX/2024-3-1-세종과고-AP일반화학1-②기말.hwpx")
HWPUNIT_PER_MM = 283.465


def qn(prefix: str, tag: str) -> etree.QName:
    return etree.QName(NS[prefix], tag)


class HwpxWriter:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self.template_parts = self._load_template_parts()

    def write(self, document: RenderDocument) -> Path:
        ensure_dir(self.output_path.parent)
        timestamp = datetime.now(timezone.utc)
        title = document.title
        media_entries = self._collect_media_entries(document)

        header_xml = self._resolve_header_xml()
        section_xml, preview_text = self._build_section(document, media_entries)
        content_hpf = self._build_content_hpf(title, timestamp, media_entries)
        settings_xml = self._build_settings()
        version_xml = self.template_parts.get("version.xml", self._build_version())
        manifest_xml = self._build_manifest()
        container_xml = self._build_container()
        rdf_xml = self._build_rdf()
        preview_png = self._build_preview_image(document)

        with zipfile.ZipFile(self.output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("mimetype", "application/hwp+zip")
            archive.writestr("version.xml", version_xml)
            archive.writestr("Contents/content.hpf", content_hpf)
            archive.writestr("Contents/header.xml", header_xml)
            archive.writestr("Contents/section0.xml", section_xml)
            archive.writestr("settings.xml", settings_xml)
            if "Contents/masterpage0.xml" in self.template_parts:
                archive.writestr("Contents/masterpage0.xml", self.template_parts["Contents/masterpage0.xml"])
            archive.writestr("META-INF/manifest.xml", manifest_xml)
            archive.writestr("META-INF/container.xml", container_xml)
            archive.writestr("META-INF/container.rdf", rdf_xml)
            archive.writestr("Preview/PrvText.txt", preview_text)
            archive.writestr("Preview/PrvImage.png", preview_png)
            for media in media_entries:
                archive.write(media["path"], arcname=media["href"])
        return self.output_path

    def _resolve_header_xml(self) -> bytes:
        raw_header = self.template_parts.get("Contents/header.xml", self._build_header())
        try:
            root = etree.fromstring(raw_header)
            self._apply_default_font_profile(root)
            return etree.tostring(root, encoding="utf-8", xml_declaration=True, pretty_print=False, standalone=True)
        except etree.XMLSyntaxError:
            fallback = etree.fromstring(self._build_header())
            self._apply_default_font_profile(fallback)
            return etree.tostring(fallback, encoding="utf-8", xml_declaration=True, pretty_print=False, standalone=True)

    def _load_template_parts(self) -> dict[str, bytes]:
        if not REFERENCE_TEMPLATE_PATH.exists():
            return {}
        parts = {}
        with zipfile.ZipFile(REFERENCE_TEMPLATE_PATH) as archive:
            for name in ["Contents/header.xml", "Contents/masterpage0.xml", "version.xml"]:
                if name in archive.namelist():
                    parts[name] = archive.read(name)
        return parts

    def _collect_media_entries(self, document: RenderDocument) -> list[dict]:
        media_entries: list[dict] = []
        counter = 1
        for question in document.questions:
            for item in question.items:
                if item["type"] != "image":
                    continue
                path = Path(item["object"].clean_path)
                suffix = path.suffix.lower() or ".png"
                media_id = f"image{counter}"
                href = f"BinData/{media_id}{suffix}"
                mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
                media_entries.append({"id": media_id, "href": href, "path": path, "mime": mime_type, "item": item["object"]})
                counter += 1
        return media_entries

    def _build_content_hpf(self, title: str, timestamp: datetime, media_entries: list[dict]) -> bytes:
        package = etree.Element(qn("opf", "package"), nsmap=NS, version="", attrib={"unique-identifier": "", "id": ""})
        metadata = etree.SubElement(package, qn("opf", "metadata"))
        etree.SubElement(metadata, qn("opf", "title"), attrib={"{http://www.w3.org/XML/1998/namespace}space": "preserve"}).text = title
        etree.SubElement(metadata, qn("opf", "language")).text = "ko"
        etree.SubElement(metadata, qn("opf", "meta"), name="creator", content="text").text = "exam_hwpx_builder"
        etree.SubElement(metadata, qn("opf", "meta"), name="lastsaveby", content="text").text = "exam_hwpx_builder"
        etree.SubElement(metadata, qn("opf", "meta"), name="CreatedDate", content="text").text = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        etree.SubElement(metadata, qn("opf", "meta"), name="ModifiedDate", content="text").text = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        manifest = etree.SubElement(package, qn("opf", "manifest"))
        etree.SubElement(manifest, qn("opf", "item"), id="header", href="Contents/header.xml", **{"media-type": "application/xml"})
        if "Contents/masterpage0.xml" in self.template_parts:
            etree.SubElement(manifest, qn("opf", "item"), id="masterpage0", href="Contents/masterpage0.xml", **{"media-type": "application/xml"})
        for media in media_entries:
            etree.SubElement(manifest, qn("opf", "item"), id=media["id"], href=media["href"], **{"media-type": media["mime"]}, isEmbeded="1")
        etree.SubElement(manifest, qn("opf", "item"), id="section0", href="Contents/section0.xml", **{"media-type": "application/xml"})
        etree.SubElement(manifest, qn("opf", "item"), id="settings", href="settings.xml", **{"media-type": "application/xml"})
        spine = etree.SubElement(package, qn("opf", "spine"))
        etree.SubElement(spine, qn("opf", "itemref"), idref="header", linear="yes")
        etree.SubElement(spine, qn("opf", "itemref"), idref="section0", linear="yes")
        return etree.tostring(package, encoding="utf-8", xml_declaration=True, pretty_print=False, standalone=True)

    def _build_header(self) -> bytes:
        head = etree.Element(qn("hh", "head"), nsmap=NS, version="1.5", secCnt="1")
        etree.SubElement(head, qn("hh", "beginNum"), page="1", footnote="1", endnote="1", pic="1", tbl="1", equation="1")
        ref_list = etree.SubElement(head, qn("hh", "refList"))
        self._append_fontfaces(ref_list)
        self._append_border_fills(ref_list)
        self._append_char_properties(ref_list)
        self._append_tab_properties(ref_list)
        self._append_numberings(ref_list)
        self._append_para_properties(ref_list)
        self._append_styles(ref_list)
        compatible = etree.SubElement(head, qn("hh", "compatibleDocument"), targetProgram="HWP201X")
        etree.SubElement(compatible, qn("hh", "layoutCompatibility"))
        doc_option = etree.SubElement(head, qn("hh", "docOption"))
        etree.SubElement(doc_option, qn("hh", "linkinfo"), path="", pageInherit="0", footnoteInherit="0")
        etree.SubElement(head, qn("hh", "trackchageConfig"), flags="56")
        etree.SubElement(head, qn("hh", "metaTag"), name="exam_hwpx_builder")
        return etree.tostring(head, encoding="utf-8", xml_declaration=True, pretty_print=False, standalone=True)

    def _append_fontfaces(self, ref_list: etree._Element) -> None:
        fontfaces = etree.SubElement(ref_list, qn("hh", "fontfaces"), itemCnt="7")
        for lang in ["HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER"]:
            fontface = etree.SubElement(fontfaces, qn("hh", "fontface"), lang=lang, fontCnt="1")
            etree.SubElement(fontface, qn("hh", "font"), id="0", face="나눔명조", type="TTF", isEmbedded="0")

    def _append_border_fills(self, ref_list: etree._Element) -> None:
        borderfills = etree.SubElement(ref_list, qn("hh", "borderFills"), itemCnt="2")
        for border_id, border_type in [("1", "NONE"), ("2", "SOLID")]:
            border_fill = etree.SubElement(
                borderfills,
                qn("hh", "borderFill"),
                id=border_id,
                threeD="0",
                shadow="0",
                centerLine="NONE",
                breakCellSeparateLine="0",
            )
            etree.SubElement(border_fill, qn("hh", "slash"), type="NONE", Crooked="0", isCounter="0")
            etree.SubElement(border_fill, qn("hh", "backSlash"), type="NONE", Crooked="0", isCounter="0")
            for side in ["leftBorder", "rightBorder", "topBorder", "bottomBorder"]:
                etree.SubElement(border_fill, qn("hh", side), type=border_type, width="0.12 mm", color="#000000")
            etree.SubElement(border_fill, qn("hh", "diagonal"), type="SOLID", width="0.12 mm", color="#000000")

    def _append_char_properties(self, ref_list: etree._Element) -> None:
        char_props = etree.SubElement(ref_list, qn("hh", "charProperties"), itemCnt="2")
        for char_id in ["0", "1"]:
            char_pr = etree.SubElement(
                char_props,
                qn("hh", "charPr"),
                id=char_id,
                height="1000",
                textColor="#000000",
                shadeColor="none",
                useFontSpace="0",
                useKerning="0",
                symMark="NONE",
                borderFillIDRef="2",
            )
            etree.SubElement(char_pr, qn("hh", "fontRef"), hangul="0", latin="0", hanja="0", japanese="0", other="0", symbol="0", user="0")
            etree.SubElement(char_pr, qn("hh", "ratio"), hangul="95", latin="95", hanja="95", japanese="95", other="95", symbol="95", user="95")
            etree.SubElement(char_pr, qn("hh", "spacing"), hangul="-5", latin="-5", hanja="-5", japanese="-5", other="-5", symbol="-5", user="-5")
            etree.SubElement(char_pr, qn("hh", "relSz"), hangul="100", latin="100", hanja="100", japanese="100", other="100", symbol="100", user="100")
            etree.SubElement(char_pr, qn("hh", "offset"), hangul="0", latin="0", hanja="0", japanese="0", other="0", symbol="0", user="0")
            etree.SubElement(char_pr, qn("hh", "underline"), type="NONE", shape="SOLID", color="#000000")
            etree.SubElement(char_pr, qn("hh", "strikeout"), shape="NONE", color="#000000")
            etree.SubElement(char_pr, qn("hh", "outline"), type="NONE")
            etree.SubElement(char_pr, qn("hh", "shadow"), type="NONE", color="#C0C0C0", offsetX="10", offsetY="10")

    def _apply_default_font_profile(self, root: etree._Element) -> None:
        for fontface in root.findall(".//hh:fontface", namespaces=NS):
            fonts = fontface.findall("hh:font", namespaces=NS)
            if not fonts:
                etree.SubElement(fontface, qn("hh", "font"), id="0", face="나눔명조", type="TTF", isEmbedded="0")
                fontface.set("fontCnt", "1")
                continue
            for index, font in enumerate(fonts):
                if index == 0:
                    font.set("face", "나눔명조")
                    font.set("id", "0")
            fontface.set("fontCnt", str(len(fonts)))

        for char_pr in root.findall(".//hh:charPr", namespaces=NS):
            char_pr.set("height", "1000")
            font_ref = char_pr.find("hh:fontRef", namespaces=NS)
            if font_ref is not None:
                for key in ["hangul", "latin", "hanja", "japanese", "other", "symbol", "user"]:
                    font_ref.set(key, "0")
            ratio = char_pr.find("hh:ratio", namespaces=NS)
            if ratio is not None:
                for key in ["hangul", "latin", "hanja", "japanese", "other", "symbol", "user"]:
                    ratio.set(key, "95")
            spacing = char_pr.find("hh:spacing", namespaces=NS)
            if spacing is not None:
                for key in ["hangul", "latin", "hanja", "japanese", "other", "symbol", "user"]:
                    spacing.set(key, "-5")
        self._ensure_center_para_property(root)

    def _ensure_center_para_property(self, root: etree._Element) -> None:
        ref_list = root.find(".//hh:refList", namespaces=NS)
        if ref_list is None:
            return
        para_props = ref_list.find("hh:paraProperties", namespaces=NS)
        if para_props is None:
            para_props = etree.SubElement(ref_list, qn("hh", "paraProperties"), itemCnt="1")
        existing = para_props.find("hh:paraPr[@id='99']", namespaces=NS)
        if existing is None:
            para_pr = etree.SubElement(
                para_props,
                qn("hh", "paraPr"),
                id="99",
                tabPrIDRef="0",
                condense="0",
                fontLineHeight="0",
                snapToGrid="1",
                suppressLineNumbers="0",
                checked="0",
            )
            etree.SubElement(para_pr, qn("hh", "align"), horizontal="CENTER", vertical="BASELINE")
            etree.SubElement(para_pr, qn("hh", "heading"), type="NONE", idRef="0", level="0")
            etree.SubElement(
                para_pr,
                qn("hh", "breakSetting"),
                breakLatinWord="KEEP_WORD",
                breakNonLatinWord="KEEP_WORD",
                widowOrphan="0",
                keepWithNext="0",
                keepLines="0",
                pageBreakBefore="0",
                lineWrap="BREAK",
            )
            etree.SubElement(para_pr, qn("hh", "autoSpacing"), eAsianEng="0", eAsianNum="0")
            switch = etree.SubElement(para_pr, qn("hp", "switch"))
            for switch_tag in ["case", "default"]:
                attrs = {qn("hp", "required-namespace"): NS["hwpunitchar"]} if switch_tag == "case" else {}
                branch = etree.SubElement(switch, qn("hp", switch_tag), attrib=attrs)
                margin = etree.SubElement(branch, qn("hh", "margin"))
                etree.SubElement(margin, qn("hc", "intent"), value="0", unit="HWPUNIT")
                etree.SubElement(margin, qn("hc", "left"), value="0", unit="HWPUNIT")
                etree.SubElement(margin, qn("hc", "right"), value="0", unit="HWPUNIT")
                etree.SubElement(margin, qn("hc", "prev"), value="0", unit="HWPUNIT")
                etree.SubElement(margin, qn("hc", "next"), value="0", unit="HWPUNIT")
                etree.SubElement(branch, qn("hh", "lineSpacing"), type="PERCENT", value="160", unit="HWPUNIT")
            etree.SubElement(
                para_pr,
                qn("hh", "border"),
                borderFillIDRef="2",
                offsetLeft="0",
                offsetRight="0",
                offsetTop="0",
                offsetBottom="0",
                connect="0",
                ignoreMargin="0",
            )
            para_props.set("itemCnt", str(len(para_props.findall("hh:paraPr", namespaces=NS))))

        styles = ref_list.find("hh:styles", namespaces=NS)
        if styles is not None and styles.find("hh:style[@id='99']", namespaces=NS) is None:
            etree.SubElement(
                styles,
                qn("hh", "style"),
                id="99",
                type="PARA",
                name="미주제목",
                engName="EndnoteTitle",
                paraPrIDRef="99",
                charPrIDRef="7",
                nextStyleIDRef="0",
                langID="1042",
                lockForm="0",
            )
            styles.set("itemCnt", str(len(styles.findall("hh:style", namespaces=NS))))

    def _append_tab_properties(self, ref_list: etree._Element) -> None:
        tabs = etree.SubElement(ref_list, qn("hh", "tabProperties"), itemCnt="1")
        etree.SubElement(tabs, qn("hh", "tabPr"), id="0", autoTabLeft="0", autoTabRight="0")

    def _append_numberings(self, ref_list: etree._Element) -> None:
        numberings = etree.SubElement(ref_list, qn("hh", "numberings"), itemCnt="1")
        numbering = etree.SubElement(numberings, qn("hh", "numbering"), id="1", start="0")
        etree.SubElement(
            numbering,
            qn("hh", "paraHead"),
            start="1",
            level="1",
            align="LEFT",
            useInstWidth="1",
            autoIndent="1",
            widthAdjust="0",
            textOffsetType="PERCENT",
            textOffset="50",
            numFormat="DIGIT",
            charPrIDRef="4294967295",
            checkable="0",
        ).text = "^1."

    def _append_para_properties(self, ref_list: etree._Element) -> None:
        para_props = etree.SubElement(ref_list, qn("hh", "paraProperties"), itemCnt="2")
        for para_id in ["0", "1"]:
            para_pr = etree.SubElement(
                para_props,
                qn("hh", "paraPr"),
                id=para_id,
                tabPrIDRef="0",
                condense="0",
                fontLineHeight="0",
                snapToGrid="1",
                suppressLineNumbers="0",
                checked="0",
            )
            etree.SubElement(para_pr, qn("hh", "align"), horizontal="JUSTIFY", vertical="BASELINE")
            etree.SubElement(para_pr, qn("hh", "heading"), type="NONE", idRef="0", level="0")
            etree.SubElement(
                para_pr,
                qn("hh", "breakSetting"),
                breakLatinWord="KEEP_WORD",
                breakNonLatinWord="KEEP_WORD",
                widowOrphan="0",
                keepWithNext="0",
                keepLines="0",
                pageBreakBefore="0",
                lineWrap="BREAK",
            )
            etree.SubElement(para_pr, qn("hh", "autoSpacing"), eAsianEng="0", eAsianNum="0")
            switch = etree.SubElement(para_pr, qn("hp", "switch"))
            for switch_tag in ["case", "default"]:
                attrs = {qn("hp", "required-namespace"): NS["hwpunitchar"]} if switch_tag == "case" else {}
                branch = etree.SubElement(switch, qn("hp", switch_tag), attrib=attrs)
                margin = etree.SubElement(branch, qn("hh", "margin"))
                etree.SubElement(margin, qn("hc", "intent"), value="0", unit="HWPUNIT")
                etree.SubElement(margin, qn("hc", "left"), value="0", unit="HWPUNIT")
                etree.SubElement(margin, qn("hc", "right"), value="0", unit="HWPUNIT")
                etree.SubElement(margin, qn("hc", "prev"), value="0", unit="HWPUNIT")
                etree.SubElement(margin, qn("hc", "next"), value="0", unit="HWPUNIT")
                etree.SubElement(branch, qn("hh", "lineSpacing"), type="PERCENT", value="160", unit="HWPUNIT")
            etree.SubElement(
                para_pr,
                qn("hh", "border"),
                borderFillIDRef="2",
                offsetLeft="0",
                offsetRight="0",
                offsetTop="0",
                offsetBottom="0",
                connect="0",
                ignoreMargin="0",
            )

    def _append_styles(self, ref_list: etree._Element) -> None:
        styles = etree.SubElement(ref_list, qn("hh", "styles"), itemCnt="3")
        etree.SubElement(styles, qn("hh", "style"), id="0", type="PARA", name="바탕글", engName="Normal", paraPrIDRef="0", charPrIDRef="0", nextStyleIDRef="0", langID="1042", lockForm="0")
        etree.SubElement(styles, qn("hh", "style"), id="14", type="PARA", name="각주", engName="Footnote", paraPrIDRef="1", charPrIDRef="0", nextStyleIDRef="14", langID="1042", lockForm="0")
        etree.SubElement(styles, qn("hh", "style"), id="15", type="PARA", name="미주", engName="Endnote", paraPrIDRef="1", charPrIDRef="0", nextStyleIDRef="15", langID="1042", lockForm="0")

    def _build_section(self, document: RenderDocument, media_entries: list[dict]) -> tuple[bytes, str]:
        sec = etree.Element(qn("hs", "sec"), nsmap=NS)
        self._append_section_properties(sec)
        para_id = 1
        ctrl_id = 2050344400
        media_map = {entry["item"].image_id: entry for entry in media_entries}
        preview_lines: list[str] = []
        has_endnotes = any(question.has_note for question in document.questions)

        for index, question in enumerate(document.questions):
            marker = f"{question.question_no}."
            first_text = True
            for item in question.items:
                item_type = item["type"]
                if item_type in {"text", "rich_text"}:
                    if first_text:
                        ctrl_id = self._append_question_paragraph(
                            sec,
                            para_id,
                            marker,
                            item,
                            question.question_no,
                            document.notes.get(question.question_no),
                            ctrl_id,
                            column_break=(index > 0),
                        )
                        preview_line = f"{marker} {item['content']}"
                    else:
                        ctrl_id = self._append_text_paragraph(sec, para_id, item, ctrl_id, column_break=False)
                        preview_line = item["content"]
                    preview_lines.append(preview_line)
                    para_id += 1
                    marker = ""
                    first_text = False
                elif item_type in {"equation", "chem_equation"}:
                    script = item["target"]
                    self._append_equation_paragraph(sec, para_id, script, ctrl_id, column_break=(index > 0 and first_text))
                    preview_lines.append(f"[수식] {script}")
                    para_id += 1
                    ctrl_id += 1
                    first_text = False
                elif item_type == "table":
                    self._append_table_paragraph(sec, para_id, item["object"], ctrl_id, column_break=(index > 0 and first_text))
                    preview_lines.append(f"[표 {item['object'].table_id}] {item['object'].n_rows}x{item['object'].n_cols}")
                    para_id += 1
                    ctrl_id += 1
                    first_text = False
                elif item_type == "image":
                    entry = media_map.get(item["object"].image_id)
                    if entry:
                        self._append_picture_paragraph(sec, para_id, entry, ctrl_id, column_break=(index > 0 and first_text))
                        preview_lines.append(f"[이미지 {item['object'].image_id}] {Path(item['object'].clean_path).name}")
                        para_id += 1
                        ctrl_id += 1
                        first_text = False
            if question.tagline:
                ctrl_id = self._append_text_paragraph(sec, para_id, {"type": "text", "content": question.tagline}, ctrl_id, column_break=False)
                preview_lines.append(question.tagline)
                para_id += 1
            if first_text:
                ctrl_id = self._append_text_paragraph(sec, para_id, {"type": "text", "content": marker}, ctrl_id, column_break=(index > 0))
                preview_lines.append(marker)
                para_id += 1
            ctrl_id = self._append_text_paragraph(sec, para_id, {"type": "text", "content": " "}, ctrl_id, column_break=False)
            para_id += 1

        if has_endnotes:
            ctrl_id = self._append_text_paragraph(sec, para_id, {"type": "text", "content": "정답 및 해설"}, ctrl_id, column_break=False, page_break=True, para_pr_id="99", char_pr_id="7", style_id="99")
            preview_lines.append("정답 및 해설")
            para_id += 1
            for question in document.questions:
                note = document.notes.get(question.question_no)
                if not note or not note.exists:
                    continue
                blocks = [block for block in note.blocks if block.get("type") == "text" and block.get("content", "").strip()]
                if not blocks:
                    continue
                first = True
                for block in blocks:
                    content = block["content"].strip()
                    if first:
                        content = self._strip_note_lead(content, question.question_no)
                        content = f"{question.question_no}) {content}".strip()
                        first = False
                    ctrl_id = self._append_text_paragraph(sec, para_id, {"type": "text", "content": content}, ctrl_id, column_break=False)
                    preview_lines.append(content)
                    para_id += 1

        return etree.tostring(sec, encoding="utf-8", xml_declaration=True, pretty_print=False, standalone=True), "\r\n".join(preview_lines)

    def _append_section_properties(self, sec: etree._Element) -> None:
        paragraph = etree.SubElement(sec, qn("hp", "p"), id="0", paraPrIDRef="0", styleIDRef="0", pageBreak="0", columnBreak="0", merged="0")
        run = etree.SubElement(paragraph, qn("hp", "run"), charPrIDRef="0")
        sec_pr = etree.SubElement(
            run,
            qn("hp", "secPr"),
            id="",
            textDirection="HORIZONTAL",
            spaceColumns="1134",
            tabStop="8000",
            tabStopVal="4000",
            tabStopUnit="HWPUNIT",
            outlineShapeIDRef="1",
            memoShapeIDRef="0",
            textVerticalWidthHead="0",
            masterPageCnt="0",
        )
        etree.SubElement(sec_pr, qn("hp", "grid"), lineGrid="0", charGrid="0", wonggojiFormat="0")
        etree.SubElement(sec_pr, qn("hp", "startNum"), pageStartsOn="BOTH", page="0", pic="0", tbl="0", equation="0")
        etree.SubElement(sec_pr, qn("hp", "visibility"), hideFirstHeader="0", hideFirstFooter="0", hideFirstMasterPage="0", border="SHOW_ALL", fill="SHOW_ALL", hideFirstPageNum="0", hideFirstEmptyLine="0", showLineNumber="0")
        etree.SubElement(sec_pr, qn("hp", "lineNumberShape"), restartType="0", countBy="0", distance="0", startNumber="0")
        page_pr = etree.SubElement(sec_pr, qn("hp", "pagePr"), landscape="WIDELY", width="59528", height="84186", gutterType="LEFT_ONLY")
        etree.SubElement(
            page_pr,
            qn("hp", "margin"),
            header=str(self._mm(25.0)),
            footer=str(self._mm(15.0)),
            gutter=str(self._mm(0.0)),
            left=str(self._mm(10.0)),
            right=str(self._mm(10.0)),
            top=str(self._mm(0.0)),
            bottom=str(self._mm(15.0)),
        )
        footnote_pr = etree.SubElement(sec_pr, qn("hp", "footNotePr"))
        etree.SubElement(footnote_pr, qn("hp", "autoNumFormat"), type="DIGIT", userChar="", prefixChar="", suffixChar=")", supscript="0")
        etree.SubElement(footnote_pr, qn("hp", "noteLine"), length="-1", type="SOLID", width="0.12 mm", color="#000000")
        etree.SubElement(footnote_pr, qn("hp", "noteSpacing"), betweenNotes="283", belowLine="567", aboveLine="850")
        etree.SubElement(footnote_pr, qn("hp", "numbering"), type="CONTINUOUS", newNum="1")
        etree.SubElement(footnote_pr, qn("hp", "placement"), place="EACH_COLUMN", beneathText="0")
        endnote_pr = etree.SubElement(sec_pr, qn("hp", "endNotePr"))
        etree.SubElement(endnote_pr, qn("hp", "autoNumFormat"), type="DIGIT", userChar="", prefixChar="", suffixChar=")", supscript="0")
        etree.SubElement(endnote_pr, qn("hp", "noteLine"), length="14692344", type="SOLID", width="0.12 mm", color="#000000")
        etree.SubElement(endnote_pr, qn("hp", "noteSpacing"), betweenNotes="0", belowLine="567", aboveLine="850")
        etree.SubElement(endnote_pr, qn("hp", "numbering"), type="CONTINUOUS", newNum="1")
        etree.SubElement(endnote_pr, qn("hp", "placement"), place="END_OF_DOCUMENT", beneathText="0")
        for fill_type in ["BOTH", "EVEN", "ODD"]:
            border_fill = etree.SubElement(sec_pr, qn("hp", "pageBorderFill"), type=fill_type, borderFillIDRef="1", textBorder="PAPER", headerInside="0", footerInside="0", fillArea="PAPER")
            etree.SubElement(border_fill, qn("hp", "offset"), left="1417", right="1417", top="1417", bottom="1417")
        if "Contents/masterpage0.xml" in self.template_parts:
            sec_pr.set("masterPageCnt", "1")
            etree.SubElement(sec_pr, qn("hp", "masterPage"), idRef="masterpage0")
        ctrl = etree.SubElement(run, qn("hp", "ctrl"))
        col_pr = etree.SubElement(ctrl, qn("hp", "colPr"), id="", type="NEWSPAPER", layout="LEFT", colCount="2", sameSz="1", sameGap="2268")
        etree.SubElement(col_pr, qn("hp", "colLine"), type="SOLID", width="0.12 mm", color="#000000")
        self._append_line_seg(paragraph, "0")

    def _append_text_paragraph(
        self,
        sec: etree._Element,
        para_id: int,
        item: dict,
        ctrl_id: int,
        column_break: bool,
        page_break: bool = False,
        para_pr_id: str = "0",
        char_pr_id: str = "0",
        style_id: str = "0",
    ) -> int:
        paragraph = etree.SubElement(
            sec,
            qn("hp", "p"),
            id=str(para_id),
            paraPrIDRef=para_pr_id,
            styleIDRef=style_id,
            pageBreak="1" if page_break else "0",
            columnBreak="1" if column_break else "0",
            merged="0",
        )
        run = etree.SubElement(paragraph, qn("hp", "run"), charPrIDRef=char_pr_id)
        ctrl_id = self._append_text_segments(run, item, ctrl_id)
        self._append_line_seg(paragraph, str(len(item.get("content", ""))))
        return ctrl_id

    def _mm(self, value: float) -> int:
        return int(round(value * HWPUNIT_PER_MM))

    def _append_question_paragraph(self, sec: etree._Element, para_id: int, marker: str, item: dict, question_no: int, note, ctrl_id: int, column_break: bool) -> int:
        paragraph = etree.SubElement(sec, qn("hp", "p"), id=str(para_id), paraPrIDRef="1", styleIDRef="0", pageBreak="0", columnBreak="1" if column_break else "0", merged="0")
        run = etree.SubElement(paragraph, qn("hp", "run"), charPrIDRef="2")
        etree.SubElement(run, qn("hp", "t")).text = f"{marker} "
        if note and note.exists:
            ctrl_id = self._append_endnote_ctrl(run, question_no, note, ctrl_id)
        ctrl_id = self._append_text_segments(run, item, ctrl_id)
        self._append_line_seg(paragraph, "0", horzsize="25796", vertsize="950", baseline="808")
        return ctrl_id

    def _append_text_segments(self, run: etree._Element, item: dict, ctrl_id: int) -> int:
        segments = item.get("segments") or [{"type": "text", "text": item.get("content", "")}]
        for segment in segments:
            if segment["type"] == "text":
                if segment["text"]:
                    etree.SubElement(run, qn("hp", "t")).text = segment["text"]
                continue
            if segment["type"] == "equation":
                ctrl_id += 1
                equation = etree.SubElement(
                    run,
                    qn("hp", "equation"),
                    id=str(ctrl_id),
                    zOrder=str(ctrl_id),
                    numberingType="EQUATION",
                    textWrap="TOP_AND_BOTTOM",
                    textFlow="BOTH_SIDES",
                    lock="0",
                    dropcapstyle="None",
                    version="Equation Version 60",
                    baseLine="72",
                    textColor="#000000",
                    baseUnit="1000",
                    lineMode="CHAR",
                    font="HancomEQN",
                )
                script = segment["script"]
                width = str(max(1000, min(9000, len(script) * 380)))
                etree.SubElement(equation, qn("hp", "sz"), width=width, widthRelTo="ABSOLUTE", height="1050", heightRelTo="ABSOLUTE", protect="0")
                etree.SubElement(equation, qn("hp", "pos"), treatAsChar="1", affectLSpacing="0", flowWithText="1", allowOverlap="0", holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="PARA", vertAlign="TOP", horzAlign="LEFT", vertOffset="0", horzOffset="0")
                etree.SubElement(equation, qn("hp", "outMargin"), left="28", right="28", top="0", bottom="0")
                etree.SubElement(equation, qn("hp", "shapeComment")).text = "본문 화학식 수식입니다."
                etree.SubElement(equation, qn("hp", "script")).text = script
        return ctrl_id

    def _append_endnote_ctrl(self, run: etree._Element, question_no: int, note, ctrl_id: int) -> int:
        ctrl = etree.SubElement(run, qn("hp", "ctrl"))
        endnote = etree.SubElement(ctrl, qn("hp", "endNote"), number=str(question_no), suffixChar="41", instId=str(ctrl_id + 9000))
        sub_list = etree.SubElement(endnote, qn("hp", "subList"), id="", textDirection="HORIZONTAL", lineWrap="BREAK", vertAlign="TOP", linkListIDRef="0", linkListNextIDRef="0", textWidth="0", textHeight="0", hasTextRef="0", hasNumRef="0")
        lead_p = etree.SubElement(sub_list, qn("hp", "p"), id="0", paraPrIDRef="2", styleIDRef="1", pageBreak="0", columnBreak="0", merged="0")
        lead_run = etree.SubElement(lead_p, qn("hp", "run"), charPrIDRef="1")
        lead_ctrl = etree.SubElement(lead_run, qn("hp", "ctrl"))
        autonum = etree.SubElement(lead_ctrl, qn("hp", "autoNum"), num=str(question_no), numType="ENDNOTE")
        etree.SubElement(autonum, qn("hp", "autoNumFormat"), type="DIGIT", userChar="", prefixChar="", suffixChar=")", supscript="0")
        etree.SubElement(lead_run, qn("hp", "t")).text = " "
        self._append_line_seg(lead_p, "0", horzsize="25796", vertsize="900", baseline="765")
        etree.SubElement(run, qn("hp", "t")).text = ""
        return ctrl_id + 1

    def _strip_note_lead(self, text: str, question_no: int) -> str:
        return text.removeprefix(f"{question_no}. ").removeprefix(f"{question_no}.").removeprefix(f"{question_no}) ").removeprefix(f"{question_no})").strip()

    def _append_equation_paragraph(self, sec: etree._Element, para_id: int, script: str, ctrl_id: int, column_break: bool) -> None:
        paragraph = etree.SubElement(sec, qn("hp", "p"), id=str(para_id), paraPrIDRef="0", styleIDRef="0", pageBreak="0", columnBreak="1" if column_break else "0", merged="0")
        run = etree.SubElement(paragraph, qn("hp", "run"), charPrIDRef="2")
        equation = etree.SubElement(
            run,
            qn("hp", "equation"),
            id=str(ctrl_id),
            zOrder=str(ctrl_id),
            numberingType="EQUATION",
            textWrap="TOP_AND_BOTTOM",
            textFlow="BOTH_SIDES",
            lock="0",
            dropcapstyle="None",
            version="Equation Version 60",
            baseLine="72",
            textColor="#000000",
            baseUnit="1000",
            lineMode="CHAR",
            font="HancomEQN",
        )
        width = str(max(1800, min(20500, len(script) * 420)))
        etree.SubElement(equation, qn("hp", "sz"), width=width, widthRelTo="ABSOLUTE", height="1177", heightRelTo="ABSOLUTE", protect="0")
        etree.SubElement(equation, qn("hp", "pos"), treatAsChar="1", affectLSpacing="0", flowWithText="1", allowOverlap="0", holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="PARA", vertAlign="TOP", horzAlign="LEFT", vertOffset="0", horzOffset="0")
        etree.SubElement(equation, qn("hp", "outMargin"), left="56", right="56", top="0", bottom="0")
        etree.SubElement(equation, qn("hp", "shapeComment")).text = "수식입니다."
        etree.SubElement(equation, qn("hp", "script")).text = script
        etree.SubElement(run, qn("hp", "t")).text = ""
        self._append_line_seg(paragraph, "0", vertsize="1177", baseline="847")

    def _append_table_paragraph(self, sec: etree._Element, para_id: int, table, ctrl_id: int, column_break: bool) -> None:
        paragraph = etree.SubElement(sec, qn("hp", "p"), id=str(para_id), paraPrIDRef="0", styleIDRef="0", pageBreak="0", columnBreak="1" if column_break else "0", merged="0")
        run = etree.SubElement(paragraph, qn("hp", "run"), charPrIDRef="2")
        tbl = etree.SubElement(
            run,
            qn("hp", "tbl"),
            id=str(ctrl_id),
            zOrder=str(ctrl_id),
            numberingType="TABLE",
            textWrap="TOP_AND_BOTTOM",
            textFlow="BOTH_SIDES",
            lock="0",
            dropcapstyle="None",
            pageBreak="CELL",
            repeatHeader="1",
            rowCnt=str(table.n_rows),
            colCnt=str(table.n_cols),
            cellSpacing="0",
            borderFillIDRef="3",
            noAdjust="0",
        )
        total_width = 25230
        row_height = 800
        etree.SubElement(tbl, qn("hp", "sz"), width=str(total_width), widthRelTo="ABSOLUTE", height=str(max(282, table.n_rows * row_height)), heightRelTo="ABSOLUTE", protect="0")
        etree.SubElement(tbl, qn("hp", "pos"), treatAsChar="1", affectLSpacing="0", flowWithText="1", allowOverlap="0", holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="COLUMN", vertAlign="TOP", horzAlign="CENTER", vertOffset="0", horzOffset="0")
        etree.SubElement(tbl, qn("hp", "outMargin"), left="283", right="283", top="283", bottom="283")
        etree.SubElement(tbl, qn("hp", "inMargin"), left="510", right="510", top="141", bottom="141")
        width_per_col = total_width // max(1, table.n_cols)
        cell_map = {(cell.row, cell.col): cell for cell in table.cells}
        for row in range(table.n_rows):
            tr = etree.SubElement(tbl, qn("hp", "tr"))
            for col in range(table.n_cols):
                cell = cell_map.get((row, col))
                if cell is None:
                    continue
                tc = etree.SubElement(tr, qn("hp", "tc"), name="", header="0", hasMargin="0", protect="0", editable="0", dirty="0", borderFillIDRef="3")
                sub_list = etree.SubElement(tc, qn("hp", "subList"), id="", textDirection="HORIZONTAL", lineWrap="BREAK", vertAlign="CENTER", linkListIDRef="0", linkListNextIDRef="0", textWidth="0", textHeight="0", hasTextRef="0", hasNumRef="0")
                cell_p = etree.SubElement(sub_list, qn("hp", "p"), id="0", paraPrIDRef="3", styleIDRef="0", pageBreak="0", columnBreak="0", merged="0")
                cell_run = etree.SubElement(cell_p, qn("hp", "run"), charPrIDRef="2")
                cell_eq_index = 0
                for idx, content in enumerate(cell.content):
                    if content["type"] == "text":
                        if idx:
                            etree.SubElement(cell_run, qn("hp", "t")).text = " "
                        etree.SubElement(cell_run, qn("hp", "t")).text = content["text"]
                    elif content["type"] == "equation":
                        cell_eq_index += 1
                        equation = etree.SubElement(
                            cell_run,
                            qn("hp", "equation"),
                            id=str(ctrl_id * 100 + row * 10 + col + cell_eq_index),
                            zOrder=str(ctrl_id * 100 + row * 10 + col + cell_eq_index),
                            numberingType="EQUATION",
                            textWrap="TOP_AND_BOTTOM",
                            textFlow="BOTH_SIDES",
                            lock="0",
                            dropcapstyle="None",
                            version="Equation Version 60",
                            baseLine="72",
                            textColor="#000000",
                            baseUnit="1000",
                            lineMode="CHAR",
                            font="HancomEQN",
                        )
                        script = content["script"]
                        width = str(max(900, min(8000, len(script) * 340)))
                        etree.SubElement(equation, qn("hp", "sz"), width=width, widthRelTo="ABSOLUTE", height="1000", heightRelTo="ABSOLUTE", protect="0")
                        etree.SubElement(equation, qn("hp", "pos"), treatAsChar="1", affectLSpacing="0", flowWithText="1", allowOverlap="0", holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="PARA", vertAlign="TOP", horzAlign="LEFT", vertOffset="0", horzOffset="0")
                        etree.SubElement(equation, qn("hp", "outMargin"), left="20", right="20", top="0", bottom="0")
                        etree.SubElement(equation, qn("hp", "shapeComment")).text = "표 셀 화학식 수식입니다."
                        etree.SubElement(equation, qn("hp", "script")).text = script
                self._append_line_seg(cell_p, "0", horzsize="11592", vertsize="950", baseline="808")
                etree.SubElement(tc, qn("hp", "cellAddr"), colAddr=str(col), rowAddr=str(row))
                etree.SubElement(tc, qn("hp", "cellSpan"), colSpan=str(cell.colspan), rowSpan=str(cell.rowspan))
                etree.SubElement(tc, qn("hp", "cellSz"), width=str(width_per_col * cell.colspan), height="282")
                etree.SubElement(tc, qn("hp", "cellMargin"), left="510", right="510", top="141", bottom="141")
        etree.SubElement(run, qn("hp", "t")).text = ""
        self._append_line_seg(paragraph, "0", vertsize="1800", baseline="1200")

    def _append_picture_paragraph(self, sec: etree._Element, para_id: int, media_entry: dict, ctrl_id: int, column_break: bool) -> None:
        image = Image.open(media_entry["path"])
        width_px, height_px = image.size
        image.close()
        width_hwp = 24247
        height_hwp = max(1000, int(width_hwp * height_px / max(1, width_px)))
        org_width = max(1, width_px * 75)
        org_height = max(1, height_px * 75)
        paragraph = etree.SubElement(sec, qn("hp", "p"), id=str(para_id), paraPrIDRef="3", styleIDRef="0", pageBreak="0", columnBreak="1" if column_break else "0", merged="0")
        run = etree.SubElement(paragraph, qn("hp", "run"), charPrIDRef="2")
        pic = etree.SubElement(
            run,
            qn("hp", "pic"),
            id=str(ctrl_id),
            zOrder=str(ctrl_id),
            numberingType="PICTURE",
            textWrap="TOP_AND_BOTTOM",
            textFlow="BOTH_SIDES",
            lock="0",
            dropcapstyle="None",
            href="",
            groupLevel="0",
            instid=str(ctrl_id + 5000),
            reverse="0",
        )
        etree.SubElement(pic, qn("hp", "offset"), x="0", y="0")
        etree.SubElement(pic, qn("hp", "orgSz"), width=str(org_width), height=str(org_height))
        etree.SubElement(pic, qn("hp", "curSz"), width=str(width_hwp), height=str(height_hwp))
        etree.SubElement(pic, qn("hp", "flip"), horizontal="0", vertical="0")
        etree.SubElement(pic, qn("hp", "rotationInfo"), angle="0", centerX=str(width_hwp // 2), centerY=str(height_hwp // 2), rotateimage="1")
        rendering_info = etree.SubElement(pic, qn("hp", "renderingInfo"))
        etree.SubElement(rendering_info, qn("hc", "transMatrix"), e1="1", e2="0", e3="0", e4="0", e5="1", e6="0")
        etree.SubElement(rendering_info, qn("hc", "scaMatrix"), e1="1", e2="0", e3="0", e4="0", e5="1", e6="0")
        etree.SubElement(rendering_info, qn("hc", "rotMatrix"), e1="1", e2="0", e3="0", e4="0", e5="1", e6="0")
        etree.SubElement(pic, qn("hc", "img"), binaryItemIDRef=media_entry["id"], bright="0", contrast="0", effect="REAL_PIC", alpha="0")
        img_rect = etree.SubElement(pic, qn("hp", "imgRect"))
        etree.SubElement(img_rect, qn("hc", "pt0"), x="0", y="0")
        etree.SubElement(img_rect, qn("hc", "pt1"), x=str(org_width), y="0")
        etree.SubElement(img_rect, qn("hc", "pt2"), x=str(org_width), y=str(org_height))
        etree.SubElement(img_rect, qn("hc", "pt3"), x="0", y=str(org_height))
        etree.SubElement(pic, qn("hp", "imgClip"), left="0", right=str(org_width), top="0", bottom=str(org_height))
        etree.SubElement(pic, qn("hp", "inMargin"), left="0", right="0", top="0", bottom="0")
        etree.SubElement(pic, qn("hp", "imgDim"), dimwidth=str(org_width), dimheight=str(org_height))
        etree.SubElement(pic, qn("hp", "effects"))
        etree.SubElement(pic, qn("hp", "sz"), width=str(width_hwp), widthRelTo="ABSOLUTE", height=str(height_hwp), heightRelTo="ABSOLUTE", protect="0")
        etree.SubElement(pic, qn("hp", "pos"), treatAsChar="1", affectLSpacing="0", flowWithText="1", allowOverlap="0", holdAnchorAndSO="0", vertRelTo="PARA", horzRelTo="COLUMN", vertAlign="TOP", horzAlign="CENTER", vertOffset="0", horzOffset="0")
        etree.SubElement(pic, qn("hp", "outMargin"), left="0", right="0", top="0", bottom="0")
        etree.SubElement(pic, qn("hp", "shapeComment")).text = f"그림입니다.\n원본 그림의 이름: {media_entry['path'].name}\n원본 그림의 크기: 가로 {width_px}pixel, 세로 {height_px}pixel"
        etree.SubElement(run, qn("hp", "t")).text = ""
        self._append_line_seg(paragraph, "0", vertsize=str(height_hwp), baseline=str(max(800, int(height_hwp * 0.85))))

    def _append_line_seg(self, paragraph: etree._Element, textpos: str, vertsize: str = "1200", baseline: str = "1020", horzsize: str = "42520") -> None:
        linesegarray = etree.SubElement(paragraph, qn("hp", "linesegarray"))
        etree.SubElement(
            linesegarray,
            qn("hp", "lineseg"),
            textpos=textpos,
            vertpos="0",
            vertsize=vertsize,
            textheight=vertsize,
            baseline=baseline,
            spacing="720",
            horzpos="0",
            horzsize=horzsize,
            flags="393216",
        )

    def _build_settings(self) -> bytes:
        settings = etree.Element(qn("ha", "HWPApplicationSetting"), nsmap={"ha": NS["ha"], "config": NS["config"]})
        etree.SubElement(settings, qn("ha", "CaretPosition"), listIDRef="0", paraIDRef="1", pos="0")
        return etree.tostring(settings, encoding="utf-8", xml_declaration=True, pretty_print=False, standalone=True)

    def _build_version(self) -> bytes:
        version = etree.Element(
            qn("hv", "HCFVersion"),
            nsmap={"hv": NS["hv"]},
            tagetApplication="WORDPROCESSOR",
            major="5",
            minor="1",
            micro="1",
            buildNumber="0",
            os="10",
            xmlVersion="1.5",
            application="exam_hwpx_builder",
            appVersion="1.0.0",
        )
        return etree.tostring(version, encoding="utf-8", xml_declaration=True, pretty_print=False, standalone=True)

    def _build_manifest(self) -> bytes:
        manifest = etree.Element(qn("odf", "manifest"), nsmap={"odf": NS["odf"]})
        return etree.tostring(manifest, encoding="utf-8", xml_declaration=True, pretty_print=False, standalone=True)

    def _build_container(self) -> bytes:
        container = etree.Element(qn("ocf", "container"), nsmap={"ocf": NS["ocf"], "hpf": NS["hpf"]})
        rootfiles = etree.SubElement(container, qn("ocf", "rootfiles"))
        etree.SubElement(rootfiles, qn("ocf", "rootfile"), **{"full-path": "Contents/content.hpf", "media-type": "application/hwpml-package+xml"})
        etree.SubElement(rootfiles, qn("ocf", "rootfile"), **{"full-path": "Preview/PrvText.txt", "media-type": "text/plain"})
        etree.SubElement(rootfiles, qn("ocf", "rootfile"), **{"full-path": "META-INF/container.rdf", "media-type": "application/rdf+xml"})
        return etree.tostring(container, encoding="utf-8", xml_declaration=True, pretty_print=False, standalone=True)

    def _build_rdf(self) -> bytes:
        rdf = etree.Element(qn("rdf", "RDF"), nsmap={"rdf": NS["rdf"]})
        description = etree.SubElement(rdf, qn("rdf", "Description"), attrib={qn("rdf", "about"): ""})
        etree.SubElement(description, qn("pkg", "hasPart"), nsmap={"pkg": NS["pkg"]}, attrib={qn("rdf", "resource"): "Contents/header.xml"})
        description = etree.SubElement(rdf, qn("rdf", "Description"), attrib={qn("rdf", "about"): "Contents/header.xml"})
        etree.SubElement(description, qn("rdf", "type"), attrib={qn("rdf", "resource"): f"{NS['pkg']}HeaderFile"})
        description = etree.SubElement(rdf, qn("rdf", "Description"), attrib={qn("rdf", "about"): ""})
        etree.SubElement(description, qn("pkg", "hasPart"), nsmap={"pkg": NS["pkg"]}, attrib={qn("rdf", "resource"): "Contents/section0.xml"})
        description = etree.SubElement(rdf, qn("rdf", "Description"), attrib={qn("rdf", "about"): "Contents/section0.xml"})
        etree.SubElement(description, qn("rdf", "type"), attrib={qn("rdf", "resource"): f"{NS['pkg']}SectionFile"})
        description = etree.SubElement(rdf, qn("rdf", "Description"), attrib={qn("rdf", "about"): ""})
        etree.SubElement(description, qn("rdf", "type"), attrib={qn("rdf", "resource"): f"{NS['pkg']}Document"})
        return etree.tostring(rdf, encoding="utf-8", xml_declaration=True, pretty_print=False, standalone=True)

    def _build_preview_image(self, document: RenderDocument) -> bytes:
        preview_source = None
        for question in document.questions:
            for item in question.items:
                if item["type"] == "image":
                    preview_source = Path(item["object"].clean_path)
                    break
            if preview_source:
                break

        if preview_source and preview_source.exists():
            image = Image.open(preview_source).convert("RGB")
        else:
            image = Image.new("RGB", (320, 240), color="white")
        image.thumbnail((320, 240))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
