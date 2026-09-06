"""Generate PDF fixtures so parser behaviour is tested against real documents."""
import fitz
from pathlib import Path

OUT = Path(__file__).parent / "fixtures"
OUT.mkdir(exist_ok=True)

CLEAN = """Yasmin Al Amrani
Riyadh, Saudi Arabia | +966 512345678 | yasmin@example.com

SUMMARY
Backend engineer with four years building payment systems.

EXPERIENCE
Senior Backend Engineer, Tamara - Riyadh
2022 - Present
Built settlement reconciliation handling 2M transactions monthly.
Reduced payout latency from 4 hours to 12 minutes.

Backend Engineer, Foodics - Riyadh
2020 - 2022
Designed the merchant payouts API used by 8000 restaurants.

EDUCATION
BSc Computer Science, King Saud University, 2020

SKILLS
Python, PostgreSQL, Django, AWS, Kafka, Docker
"""


def clean_cv():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(60, 60, 540, 760), CLEAN, fontsize=10, fontname="helv")
    doc.save(OUT / "clean_single_column.pdf"); doc.close()


def two_column_cv():
    """Sidebar left, content right, repeated down the page."""
    doc = fitz.open()
    page = doc.new_page()
    left = "SKILLS\nPython\nPostgreSQL\nDjango\nAWS\nKafka\n\nLANGUAGES\nArabic\nEnglish\n\nCONTACT\nRiyadh\n+966512345678"
    right = CLEAN
    page.insert_textbox(fitz.Rect(40, 60, 190, 760), left, fontsize=9, fontname="helv")
    page.insert_textbox(fitz.Rect(320, 60, 560, 760), right, fontsize=9, fontname="helv")
    doc.save(OUT / "two_column.pdf"); doc.close()


def scanned_cv():
    """Text rendered to a raster image, then placed -- no text layer at all."""
    src = fitz.open()
    p = src.new_page()
    p.insert_textbox(fitz.Rect(60, 60, 540, 760), CLEAN, fontsize=10, fontname="helv")
    pix = p.get_pixmap(dpi=150)
    src.close()

    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, pixmap=pix)
    doc.save(OUT / "scanned.pdf"); doc.close()


def arabic_cv():
    """Bilingual AR/EN CV. Needs a real Arabic face -- base-14 helv has no
    Arabic glyphs and silently drops the text."""
    doc = fitz.open()
    page = doc.new_page()
    font_path = "/System/Library/Fonts/GeezaPro.ttc"
    page.insert_font(fontname="geeza", fontfile=font_path)
    ar = ("\u064a\u0627\u0633\u0645\u064a\u0646 \u0627\u0644\u0639\u0645\u0631\u0627\u0646\u064a\n"
          "\u0627\u0644\u0631\u064a\u0627\u0636\u060c \u0627\u0644\u0645\u0645\u0644\u0643\u0629 \u0627\u0644\u0639\u0631\u0628\u064a\u0629 \u0627\u0644\u0633\u0639\u0648\u062f\u064a\u0629\n"
          "\u0645\u0647\u0646\u062f\u0633\u0629 \u0628\u0631\u0645\u062c\u064a\u0627\u062a\n"
          "\u0627\u0644\u062e\u0628\u0631\u0629 \u0627\u0644\u0639\u0645\u0644\u064a\u0629\n"
          "\u0645\u0647\u0646\u062f\u0633\u0629 \u0628\u0631\u0645\u062c\u064a\u0627\u062a \u0623\u0648\u0644\u0649\u060c \u062a\u0645\u0627\u0631\u0627\n"
          "\u0627\u0644\u062a\u0639\u0644\u064a\u0645\n"
          "\u0628\u0643\u0627\u0644\u0648\u0631\u064a\u0648\u0633 \u0639\u0644\u0648\u0645 \u062d\u0627\u0633\u0628\u060c \u062c\u0627\u0645\u0639\u0629 \u0627\u0644\u0645\u0644\u0643 \u0633\u0639\u0648\u062f\n")
    page.insert_textbox(fitz.Rect(60, 60, 540, 420), ar, fontsize=13, fontname="geeza")
    page.insert_textbox(fitz.Rect(60, 430, 540, 700),
                        "EXPERIENCE\nSenior Software Engineer, Tamara - Riyadh\n"
                        "EDUCATION\nBSc Computer Science, King Saud University\n"
                        "yasmin@example.com | +966512345678\n",
                        fontsize=11, fontname="helv")
    doc.save(OUT / "arabic.pdf"); doc.close()


if __name__ == "__main__":
    clean_cv(); two_column_cv(); scanned_cv(); arabic_cv()
    for f in sorted(OUT.glob("*.pdf")):
        print(f"{f.name}: {f.stat().st_size} bytes")
