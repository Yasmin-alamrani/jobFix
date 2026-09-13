"""DOCX export via python-docx, with right-to-left done properly.

Word stores direction in two places, and an Arabic CV needs both:

  w:bidi on a paragraph   the paragraph runs right to left: it starts at the
                          right margin, and its bullet sits on the right.
  w:rtl on a run          this run of text is right-to-left script.

Arabic runs are split from Latin ones, so "PostgreSQL" inside an Arabic bullet
is its own left-to-right run and cannot be reversed. Complex-script size and
bold (w:szCs, w:bCs) are set alongside the Latin ones; without them Word shows
Arabic at its default size and never in bold, whatever the paragraph says.

The font is Arial, not the faces the PDF embeds. A DOCX does not carry its
fonts, and Arial -- Arabic glyphs included -- is present in Word on Windows and
macOS and in Google Docs, so it renders the same wherever the file is opened.

python-docx does not expose most of these properties, so they are written as
XML, inserted in the order the OOXML schema requires. Word forgives misordered
elements; stricter readers, LibreOffice and some ATS parsers among them, do not.
"""
from __future__ import annotations

import io
import re

from docx import Document as new_document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

from .document import SEPARATOR, Document

FONT = "Arial"
BODY_PT = 10.5
NAME_PT = 18
HEADING_PT = 12

_ARABIC_RUN = re.compile(
    r"[؀-ۿݐ-ݿࢠ-ࣿ]+"
    r"(?:\s+[؀-ۿݐ-ݿࢠ-ࣿ]+)*"
)

# Child order inside w:rPr, w:pPr and w:sectPr, from ECMA-376. An element is
# inserted before the first of its successors already present.
_RPR = ["w:rStyle", "w:rFonts", "w:b", "w:bCs", "w:i", "w:iCs", "w:caps", "w:smallCaps",
        "w:strike", "w:dstrike", "w:outline", "w:shadow", "w:emboss", "w:imprint",
        "w:noProof", "w:snapToGrid", "w:vanish", "w:webHidden", "w:color", "w:spacing",
        "w:w", "w:kern", "w:position", "w:sz", "w:szCs", "w:highlight", "w:u", "w:effect",
        "w:bdr", "w:shd", "w:fitText", "w:vertAlign", "w:rtl", "w:cs", "w:em", "w:lang",
        "w:eastAsianLayout", "w:specVanish", "w:oMath"]
_PPR = ["w:pStyle", "w:keepNext", "w:keepLines", "w:pageBreakBefore", "w:framePr",
        "w:widowControl", "w:numPr", "w:suppressLineNumbers", "w:pBdr", "w:shd", "w:tabs",
        "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
        "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd",
        "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents",
        "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment",
        "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr",
        "w:pPrChange"]
_SECTPR = ["w:headerReference", "w:footerReference", "w:footnotePr", "w:endnotePr",
           "w:type", "w:pgSz", "w:pgMar", "w:paperSrc", "w:pgBorders", "w:lnNumType",
           "w:pgNumType", "w:cols", "w:formProt", "w:vAlign", "w:noEndnote", "w:titlePg",
           "w:textDirection", "w:bidi", "w:rtlGutter", "w:docGrid", "w:printerSettings",
           "w:sectPrChange"]


def _put(parent, order: list[str], tag: str, **attrs: str):
    """Set a single child element, replacing any existing one, in schema order."""
    for old in parent.findall(qn(tag)):
        parent.remove(old)
    element = OxmlElement(tag)
    for name, value in attrs.items():
        element.set(qn(name), value)
    parent.insert_element_before(element, *order[order.index(tag) + 1:])
    return element


def _half_points(pt: float) -> str:
    return str(int(round(pt * 2)))


def _font_properties(rpr, *, size: float | None = None, bold: bool = False) -> None:
    _put(rpr, _RPR, "w:rFonts", **{"w:ascii": FONT, "w:hAnsi": FONT, "w:cs": FONT,
                                   "w:eastAsia": FONT})
    if bold:
        _put(rpr, _RPR, "w:b")
        _put(rpr, _RPR, "w:bCs")
    if size is not None:
        _put(rpr, _RPR, "w:sz", **{"w:val": _half_points(size)})
        _put(rpr, _RPR, "w:szCs", **{"w:val": _half_points(size)})


def segments(text: str) -> list[tuple[str, bool]]:
    """Split text into (piece, is_arabic) runs, in logical order."""
    out: list[tuple[str, bool]] = []
    position = 0
    for match in _ARABIC_RUN.finditer(text):
        if match.start() > position:
            out.append((text[position:match.start()], False))
        out.append((match.group(0), True))
        position = match.end()
    if position < len(text):
        out.append((text[position:], False))
    return out


def _write(paragraph, text: str, *, rtl_doc: bool, bold: bool = False,
           size: float | None = None) -> None:
    if rtl_doc:
        _put(paragraph._p.get_or_add_pPr(), _PPR, "w:bidi")
    for piece, arabic in segments(text):
        run = paragraph.add_run(piece)
        rpr = run._r.get_or_add_rPr()
        if bold or size is not None:
            _font_properties(rpr, size=size, bold=bold)
        if arabic:
            _put(rpr, _RPR, "w:rtl")


def _style_defaults(document, lang: str) -> None:
    normal = document.styles["Normal"]
    rpr = normal.element.get_or_add_rPr()
    _font_properties(rpr, size=BODY_PT)
    _put(rpr, _RPR, "w:lang", **{"w:val": "ar-SA" if lang == "ar" else "en-US",
                                 "w:bidi": "ar-SA"})
    normal.paragraph_format.space_after = Pt(2)
    normal.paragraph_format.line_spacing = 1.15

    heading = document.styles["Heading 1"]
    heading_rpr = heading.element.get_or_add_rPr()
    _font_properties(heading_rpr, size=HEADING_PT, bold=True)
    heading.font.color.rgb = RGBColor(0, 0, 0)
    heading.paragraph_format.space_before = Pt(10)
    heading.paragraph_format.space_after = Pt(3)


def render_docx(doc: Document) -> bytes:
    rtl = doc.direction == "rtl"
    document = new_document()
    _style_defaults(document, doc.lang)

    section = document.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.left_margin = section.right_margin = Mm(18)
    section.top_margin = section.bottom_margin = Mm(16)
    if rtl:
        _put(section._sectPr, _SECTPR, "w:bidi")

    if doc.name:
        _write(document.add_paragraph(), doc.name, rtl_doc=rtl, bold=True, size=NAME_PT)
    if doc.contact:
        _write(document.add_paragraph(), SEPARATOR.join(doc.contact), rtl_doc=rtl)

    for part in doc.sections:
        # A real Heading 1, not bold body text: Word's navigation pane, screen
        # readers and parsers that walk the document outline all find it.
        _write(document.add_paragraph(style="Heading 1"), part.heading, rtl_doc=rtl)
        if part.text:
            _write(document.add_paragraph(), part.text, rtl_doc=rtl)
        for entry in part.entries:
            if entry.title:
                title = document.add_paragraph()
                title.paragraph_format.keep_with_next = True
                title.paragraph_format.space_before = Pt(4)
                _write(title, entry.title, rtl_doc=rtl, bold=True)
            if entry.detail:
                detail = document.add_paragraph()
                detail.paragraph_format.keep_with_next = bool(entry.bullets or entry.text)
                _write(detail, entry.detail, rtl_doc=rtl)
            if entry.text:
                _write(document.add_paragraph(), entry.text, rtl_doc=rtl)
            for bullet in entry.bullets:
                _write(document.add_paragraph(style="List Bullet"), bullet, rtl_doc=rtl)

    properties = document.core_properties
    properties.title = doc.title or doc.name
    properties.author = doc.name
    properties.language = "ar-SA" if doc.lang == "ar" else "en-US"

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
