"""Deterministic resume structure analysis.

Everything an ATS actually trips over is measured here in Python, not asked of
the model. An LLM looking at a rendered page cannot reliably tell you whether
the text layer is extractable, whether the columns will be interleaved on
parse, or whether the contact line sits in a header that most parsers drop --
and it should not be guessing at facts that decide a score.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF

# Section headings an ATS is likely to recognise. Anything else risks the
# section's content being filed under the previous heading.
STANDARD_SECTIONS = {
    "experience", "work experience", "professional experience", "employment",
    "employment history", "education", "skills", "technical skills", "summary",
    "professional summary", "profile", "objective", "projects", "certifications",
    "licenses", "publications", "languages", "awards", "volunteer", "references",
    "achievements", "training", "courses",
}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
# Saudi mobile numbers appear as +966 5X, 00966, or a local 05X.
PHONE_RE = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
SAUDI_PHONE_RE = re.compile(r"(?:\+?966|00966)\s?5\d{8}|\b05\d{8}\b")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s]+", re.I)
ARABIC_RE = re.compile(r"[؀-ۿ]")

# Fraction of a page's area covered by images before we treat it as a scan.
_SCAN_IMAGE_COVERAGE = 0.5
# A page with fewer extractable characters than this is not carrying real text.
_MIN_CHARS_PER_PAGE = 100


@dataclass
class ParseReport:
    """Measured facts about the document. No opinions, no scores."""

    page_count: int = 0
    char_count: int = 0
    is_scanned: bool = False
    has_extractable_text: bool = True
    multi_column_pages: list[int] = field(default_factory=list)
    table_pages: list[int] = field(default_factory=list)
    header_footer_text: list[str] = field(default_factory=list)
    non_embedded_fonts: list[str] = field(default_factory=list)
    detected_sections: list[str] = field(default_factory=list)
    nonstandard_headings: list[str] = field(default_factory=list)
    has_email: bool = False
    has_phone: bool = False
    has_saudi_phone: bool = False
    phone_e164_ok: bool = True
    arabic_char_ratio: float = 0.0
    primary_language: str = "en"
    text: str = ""

    @property
    def is_bilingual(self) -> bool:
        return 0.05 < self.arabic_char_ratio < 0.95


def _blocks(page: fitz.Page) -> list[tuple[fitz.Rect, str]]:
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:  # 0 == text
            continue
        txt = "".join(
            span["text"] for line in b.get("lines", []) for span in line.get("spans", [])
        ).strip()
        if txt:
            out.append((fitz.Rect(b["bbox"]), txt))
    return out


def _is_multi_column(page: fitz.Page) -> bool:
    """True when text blocks sit side by side across several vertical bands.

    A single side-by-side pair is usually a header or a date aligned right; a
    genuine two-column layout repeats down the page, which is what interleaves
    on extraction.
    """
    blocks = [r for r, _ in _blocks(page)]
    if len(blocks) < 4:
        return False

    page_mid = page.rect.width / 2
    bands = 0
    for i, a in enumerate(blocks):
        for b in blocks[i + 1 :]:
            vertical_overlap = min(a.y1, b.y1) - max(a.y0, b.y0)
            if vertical_overlap <= 5:
                continue
            # Disjoint horizontally, and straddling the page midline.
            if a.x1 < b.x0 or b.x1 < a.x0:
                left, right = (a, b) if a.x0 < b.x0 else (b, a)
                if left.x1 < page_mid < right.x0:
                    bands += 1
                    break
    return bands >= 3


def _has_table(page: fitz.Page) -> bool:
    try:
        return len(page.find_tables().tables) > 0
    except Exception:  # find_tables is best-effort across PyMuPDF versions
        return False


def _header_footer(page: fitz.Page) -> list[str]:
    """Text in the top/bottom 6% of the page -- many parsers discard this band."""
    margin = page.rect.height * 0.06
    found = []
    for rect, txt in _blocks(page):
        if rect.y1 < margin or rect.y0 > page.rect.height - margin:
            found.append(txt)
    return found


def _headings(doc: fitz.Document) -> tuple[list[str], list[str]]:
    """Find headings by *styling*, then split into recognised vs unrecognised.

    Reading headings off raw text lines produced constant false positives --
    a name, a job title and a date range all look like headings as plain
    strings. Real headings are set apart visually, so we look for lines that
    are bold or set larger than the body text.
    """
    lines: list[tuple[str, float, bool]] = []
    sizes: list[float] = []

    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                txt = "".join(s["text"] for s in spans).strip()
                if not txt:
                    continue
                size = max(s["size"] for s in spans)
                # Bit 4 of the span flags marks a bold face.
                bold = any(s["flags"] & (1 << 4) for s in spans)
                lines.append((txt, size, bold))
                sizes.append(size)

    if not lines:
        return [], []

    body_size = sorted(sizes)[len(sizes) // 2]

    standard, nonstandard = [], []
    for txt, size, bold in lines:
        if len(txt) < 3 or len(txt.split()) > 5:
            continue
        if txt.startswith(("-", "\u2022", "*", "\u00b7")):
            continue
        # Set apart from the body: larger, bold, or fully capitalised.
        looks_like_heading = size > body_size * 1.1 or bold or txt.isupper()
        if not looks_like_heading:
            continue
        key = re.sub(r"[^a-z\s]", "", txt.lower()).strip()
        if not key:
            continue
        if key in STANDARD_SECTIONS:
            standard.append(key)
        elif not any(c.isdigit() for c in txt) and "," not in txt:
            nonstandard.append(txt)
    return standard, nonstandard


def parse_pdf(path: Path) -> ParseReport:
    report = ParseReport()
    doc = fitz.open(path)
    report.page_count = doc.page_count

    chunks: list[str] = []
    embedded_ok: set[str] = set()
    not_embedded: set[str] = set()

    for i, page in enumerate(doc, start=1):
        page_text = page.get_text()
        chunks.append(page_text)

        image_area = sum(fitz.Rect(img["bbox"]).get_area() for img in page.get_image_info())
        coverage = image_area / page.rect.get_area() if page.rect.get_area() else 0
        if len(page_text.strip()) < _MIN_CHARS_PER_PAGE and coverage > _SCAN_IMAGE_COVERAGE:
            report.is_scanned = True

        if _is_multi_column(page):
            report.multi_column_pages.append(i)
        if _has_table(page):
            report.table_pages.append(i)
        report.header_footer_text.extend(_header_footer(page))

        for font in page.get_fonts(full=True):
            name, is_embedded = font[3], bool(font[1])
            (embedded_ok if is_embedded else not_embedded).add(name)

    standard, nonstandard = _headings(doc)
    doc.close()

    text = "\n".join(chunks)
    report.text = text
    report.char_count = len(text.strip())
    report.has_extractable_text = report.char_count >= _MIN_CHARS_PER_PAGE
    report.non_embedded_fonts = sorted(not_embedded - embedded_ok)

    report.detected_sections = sorted(set(standard))
    report.nonstandard_headings = sorted(set(nonstandard))[:10]

    report.has_email = bool(EMAIL_RE.search(text))
    phone_match = PHONE_RE.search(text)
    report.has_phone = bool(phone_match)
    report.has_saudi_phone = bool(SAUDI_PHONE_RE.search(text))
    # A local 05X number is correct domestically but not reachable from abroad.
    if report.has_saudi_phone:
        report.phone_e164_ok = bool(re.search(r"\+966", text))

    arabic = len(ARABIC_RE.findall(text))
    letters = len(re.findall(r"[^\W\d_]", text, re.UNICODE)) or 1
    report.arabic_char_ratio = arabic / letters
    report.primary_language = "ar" if report.arabic_char_ratio > 0.5 else "en"

    return report
