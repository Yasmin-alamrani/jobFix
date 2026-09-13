"""PDF export: the layout as HTML, rendered by WeasyPrint.

WeasyPrint is used because it shapes text through Pango and HarfBuzz, which is
what Arabic needs -- letters join, and a line mixing Arabic with "PostgreSQL" is
laid out by the bidirectional algorithm rather than left to chance. The text
layer stays selectable, which is the whole point of an ATS-friendly export.

Two safety properties hold whatever a CV contains:

  - Every string from the CV is HTML-escaped. A bullet reading
    `<img src="http://169.254.169.254/">` prints as those characters.
  - The renderer's URL fetcher refuses everything except the bundled font
    files. Even a markup bug could not make an export fetch a URL or read a
    local file into the PDF -- the same SSRF boundary the job-intake path has,
    applied to the one other place this app turns text into requests.

Fonts are the bundled Noto Sans (Latin) and Tajawal (Arabic), SIL OFL with the
licences beside them, embedded and subset, so the PDF looks the same on every
machine and never depends on what the reader has installed.

**Why Tajawal, and not Noto's Arabic faces.** The obvious choice was Noto Naskh
Arabic, and it renders beautifully -- but its text layer is unreadable. It
draws letters from dotless skeletons plus separate dot glyphs, and the PDF's
glyph-to-text map cannot put them back together: "ياسمين" extracts as "ياسميOن".
Noto Sans Arabic and Noto Kufi Arabic are built the same way. Six Arabic fonts
were rendered and parsed back; Tajawal extracted as well as the system Arial
reference, and an Arabic CV whose text cannot be read is not ATS-friendly
however it looks.

Two limits remain with every font tried, and are properties of PDF text
extraction rather than of the font: a lam-alef ligature can come back with its
letters swapped, and a line mixing Arabic with digits or Latin text can come
back out of order. The DOCX has neither problem, which is why the interface
recommends the Word file for Arabic applications.
"""
from __future__ import annotations

import functools
import html
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from .document import SEPARATOR, Document

FONTS = (Path(__file__).parent / "fonts").resolve()
_FONT_FILES = {
    ("Noto Sans", "normal"): "NotoSans-Regular.ttf",
    ("Noto Sans", "bold"): "NotoSans-Bold.ttf",
    ("Tajawal", "normal"): "Tajawal-Regular.ttf",
    ("Tajawal", "bold"): "Tajawal-Bold.ttf",
}

# Where dyld looks when a library is named without a path. Setting the variable
# replaces this list rather than extending it, so it is restated in full.
_DYLD_DEFAULTS = (str(Path.home() / "lib"), "/usr/local/lib", "/lib", "/usr/lib")


class ExportUnavailable(RuntimeError):
    """The PDF renderer cannot run on this machine."""


def _ensure_library_path() -> None:
    """Let WeasyPrint find Homebrew's Pango on macOS.

    WeasyPrint loads Pango by bare library name. When the dynamic loader
    cannot find it, cffi falls back to `ctypes.util.find_library`, which reads
    DYLD_FALLBACK_LIBRARY_PATH from `os.environ` at call time -- so adding
    Homebrew's directory here, before the import, is enough. Without it, every
    developer would have to export the variable before starting the server.
    """
    if sys.platform != "darwin":
        return
    current = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    parts = [p for p in current.split(":") if p] or list(_DYLD_DEFAULTS)
    for directory in ("/opt/homebrew/lib", "/usr/local/lib"):
        if Path(directory).is_dir() and directory not in parts:
            parts.append(directory)
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(parts)


@functools.lru_cache(maxsize=1)
def _weasyprint():
    """Import WeasyPrint on first use, not at startup.

    A missing Pango then costs the PDF button, not the whole API: the rest of
    the app, DOCX export included, keeps working and the user is told why.
    (lru_cache does not cache exceptions, so a fixed install is picked up.)
    """
    _ensure_library_path()
    try:
        import weasyprint
    except (ImportError, OSError) as exc:
        raise ExportUnavailable(
            "PDF export needs WeasyPrint and the Pango library, and Pango could not "
            "be loaded. On macOS run `brew install pango`, then restart the server. "
            "Word export still works."
        ) from exc
    return weasyprint


def is_bundled_font(url: str) -> bool:
    """True only for a .ttf directly inside the bundled fonts directory.

    The path is resolved before it is compared. A prefix check on the URL would
    pass `file:///…/fonts/../../etc/passwd`, which starts with the fonts URI and
    ends somewhere else entirely.
    """
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return False
    path = Path(unquote(parsed.path)).resolve()
    return path.parent == FONTS and path.suffix == ".ttf" and path.is_file()


def fonts_only_fetcher():
    """A WeasyPrint URL fetcher that fetches the bundled fonts and nothing else.

    WeasyPrint 70 requires an instance of its URLFetcher class -- a plain
    function crashes on the first refused URL and, worse, makes font loading
    fail quietly back to system fonts. Subclassing keeps its file handling and
    replaces only the decision about what may be fetched. `allowed_protocols`
    alone would not be enough: file:// would still reach any file on disk.
    """
    weasyprint = _weasyprint()

    class FontsOnly(weasyprint.URLFetcher):
        def fetch(self, url, headers=None):
            if not is_bundled_font(url):
                raise ValueError(f"PDF export does not fetch {url!r}.")
            return super().fetch(url, headers)

    return FontsOnly(allowed_protocols={"file"}, allow_redirects=False)


def _css() -> str:
    faces = "\n".join(
        f"@font-face {{ font-family: '{family}'; font-weight: {weight}; "
        f"src: url('{(FONTS / file).as_uri()}'); }}"
        for (family, weight), file in _FONT_FILES.items()
    )
    return faces + """
@page { size: A4; margin: 16mm 18mm; }
html { font-size: 10.5pt; }
body { margin: 0; line-height: 1.38; color: #111; }
body.ltr { font-family: 'Noto Sans', 'Tajawal'; }
body.rtl { font-family: 'Tajawal', 'Noto Sans'; }
p { margin: 0; }
h1 { font-size: 18pt; font-weight: bold; margin: 0 0 2pt; }
.contact { margin: 0 0 6pt; }
h2 {
  font-size: 11.5pt; font-weight: bold;
  margin: 11pt 0 4pt; padding-bottom: 2pt;
  border-bottom: 0.6pt solid #777;
  break-after: avoid;
}
.entry { margin: 0 0 6pt; }
.entry-title { font-weight: bold; break-after: avoid; }
.entry-detail { color: #333; break-after: avoid; }
/* The marker is written as text on the line, not drawn by the list: parsers
   then read "• bullet" in place instead of a detached column of dots. */
ul { list-style: none; margin: 2pt 0 0; padding: 0; }
li { margin: 0 0 1.5pt; }
li::before { content: "• "; }
"""


def to_html(doc: Document) -> str:
    e = html.escape
    out = [
        f'<!doctype html><html lang="{doc.lang}" dir="{doc.direction}"><head>'
        f'<meta charset="utf-8"><title>{e(doc.title or doc.name or "CV")}</title>'
        f'<meta name="author" content="{e(doc.name)}"></head>'
        f'<body class="{doc.direction}">'
    ]
    if doc.name:
        out.append(f"<h1>{e(doc.name)}</h1>")
    if doc.contact:
        # <bdi> isolates each item, so an email or phone number keeps its own
        # direction inside a right-to-left line instead of being reordered.
        out.append('<p class="contact">'
                   + SEPARATOR.join(f"<bdi>{e(item)}</bdi>" for item in doc.contact)
                   + "</p>")
    for section in doc.sections:
        out.append(f"<section><h2>{e(section.heading)}</h2>")
        if section.text:
            out.append(f"<p>{e(section.text)}</p>")
        for entry in section.entries:
            out.append('<div class="entry">')
            if entry.title:
                out.append(f'<p class="entry-title">{e(entry.title)}</p>')
            if entry.detail:
                out.append(f'<p class="entry-detail">{e(entry.detail)}</p>')
            if entry.text:
                out.append(f"<p>{e(entry.text)}</p>")
            if entry.bullets:
                out.append("<ul>" + "".join(f"<li>{e(b)}</li>" for b in entry.bullets) + "</ul>")
            out.append("</div>")
        out.append("</section>")
    out.append("</body></html>")
    return "".join(out)


def render_pdf(doc: Document) -> bytes:
    weasyprint = _weasyprint()
    from weasyprint.text.fonts import FontConfiguration

    # @font-face is only honoured when the same FontConfiguration is given to
    # the stylesheet and to write_pdf. Without it WeasyPrint silently falls back
    # to system fonts -- the export still "works", in the wrong typeface.
    fonts = FontConfiguration()
    fetcher = fonts_only_fetcher()
    css = weasyprint.CSS(string=_css(), font_config=fonts, url_fetcher=fetcher)
    return weasyprint.HTML(string=to_html(doc), url_fetcher=fetcher).write_pdf(
        stylesheets=[css], font_config=fonts,
    )
