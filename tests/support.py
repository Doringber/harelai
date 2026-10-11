"""Document builders and model-answer helpers shared by the test modules."""
import zipfile
from xml.sax.saxutils import escape

import pymupdf


def pdf(path, pages):
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((50, 50), text)
    doc.save(path)
    doc.close()


def docx(path, paragraphs):
    body = ''.join(f'<w:p><w:r><w:t>{escape(p)}</w:t></w:r></w:p>' for p in paragraphs)
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '</w:body></w:document>')


def fact(value, quote):
    return {"value": value, "quote": quote}
