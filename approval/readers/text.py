from pathlib import Path
from approval.core.models import Page
from approval.core.quality import text_quality

class TextReader:
    def read(self, path: Path) -> list[Page]:
        raw = path.read_bytes()
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        text = raw.decode(encoding, errors="strict")
        ok, warnings = text_quality(text)
        return [Page(number=1, text=text, method="text", usable=ok, warnings=warnings)]
