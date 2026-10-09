"""Build the five text PDFs used by the fictional alternate-case demonstration."""
from pathlib import Path

import pymupdf


ROOT = Path(__file__).parent

for source in sorted(ROOT.glob("*.txt")):
    pdf = pymupdf.open()
    page = pdf.new_page()
    remaining = page.insert_textbox(
        pymupdf.Rect(48, 48, 548, 744),
        source.read_text(),
        fontname="helv",
        fontsize=11,
        lineheight=1.25,
    )
    if remaining < 0:
        raise ValueError(f"Text did not fit on one page: {source.name}")
    pdf.save(ROOT / f"{source.stem}.pdf")
    pdf.close()
