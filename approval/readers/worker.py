"""Subprocess boundary provides a hard wall-clock limit for native parsers."""
import json
import sys
from pathlib import Path
from .pdf import PdfReader
from .docx import DocxReader
from .text import TextReader

if __name__ == "__main__":
    options = json.loads(sys.stdin.read())
    path = Path(options["path"])
    readers = {".pdf": PdfReader(options["ocr"], options["languages"]), ".docx": DocxReader(), ".txt": TextReader()}
    try:
        pages = readers[path.suffix.lower()].read(path)
        print(json.dumps([p.model_dump() for p in pages], ensure_ascii=False))
    except Exception as exc:
        # No document contents or absolute paths in operational errors.
        print(type(exc).__name__, file=sys.stderr)
        sys.exit(1)
