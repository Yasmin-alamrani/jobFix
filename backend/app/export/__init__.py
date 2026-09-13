"""Export a CV version as PDF and DOCX.

One layout model (`document.py`) is built from the profile once, then handed
to two renderers. Headings, section order, date formats and text direction are
decided in exactly one place, so the PDF and the Word file cannot drift apart.
"""
