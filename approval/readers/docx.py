from pathlib import Path
from zipfile import ZipFile
from docx import Document
from approval.core.models import Page
from approval.core.quality import text_quality

class DocxReader:
    def read(self, path: Path) -> list[Page]:
        with ZipFile(path) as archive:
            if sum(x.file_size for x in archive.infolist()) > 50_000_000:
                raise ValueError("docx_expansion_limit")
        doc = Document(path)
        pieces = []
        for item in doc.iter_inner_content():
            if hasattr(item, "text"): pieces.append(item.text)
            else: pieces.extend(" | ".join(c.text for c in row.cells) for row in item.rows)
        text = "\n".join(pieces)
        ok, warnings = text_quality(text)
        # DOCX pagination is renderer-dependent. Segment 1 is not a physical page.
        return [Page(number=1, text=text, method="docx", usable=ok,
            warnings=warnings + ["logical_segment_not_physical_page", "embedded_images_not_ocr_processed"])]
