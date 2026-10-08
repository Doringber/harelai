from pathlib import Path
import subprocess
import tempfile
import pymupdf
from approval.core.models import Page
from approval.core.quality import text_quality

class PdfReader:
    def __init__(self, ocr=False, languages="eng"):
        self.ocr, self.languages = ocr, languages

    def read(self, path: Path) -> list[Page]:
        result = []
        with pymupdf.open(path) as doc:
            if doc.needs_pass: raise ValueError("encrypted_pdf")
            if len(doc) == 0 or len(doc) > 100: raise ValueError("page_limit")
            for n, page in enumerate(doc, 1):
                text = page.get_text("text")
                ok, warnings = text_quality(text)
                method = "native"
                # Large page image + little text is a common partial scan, even if a header is readable.
                area = page.rect.width * page.rect.height
                image_area = sum((i['bbox'][2]-i['bbox'][0]) * (i['bbox'][3]-i['bbox'][1]) for i in page.get_image_info())
                if image_area > .4 * area and len(text.strip()) < 150:
                    ok = False
                    warnings += ["possible_partial_scan"]
                if not ok and self.ocr:
                    try:
                        with tempfile.TemporaryDirectory() as tmp:
                            image = Path(tmp) / "page.png"
                            page.get_pixmap(dpi=200).save(image)
                            proc = subprocess.run(["tesseract", str(image), "stdout", "-l", self.languages],
                                capture_output=True, timeout=30, check=True)
                            text = proc.stdout.decode("utf-8", errors="strict")
                            ok, ocr_warnings = text_quality(text)
                            warnings += ocr_warnings
                            method = "ocr"
                    except (OSError, subprocess.SubprocessError, UnicodeError):
                        warnings += ["ocr_failed"]
                        ok = False
                result.append(Page(number=n, text=text, method=method, usable=ok, warnings=warnings))
        return result
