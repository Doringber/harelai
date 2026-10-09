"""Read a PDF into plain text."""
from pathlib import Path

import pymupdf


def read_pdf(path: Path) -> str:
    with pymupdf.open(path) as pdf:
        return "\n".join(page.get_text() for page in pdf)
