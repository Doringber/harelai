"""Read supported documents into text with stable page/paragraph locations."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import zipfile
import xml.etree.ElementTree as ET

import pymupdf


@dataclass
class Document:
    id: str
    role: str
    path: Path
    sha256: str
    units: list[dict]
    reader: str

    @property
    def text(self):
        return '\n'.join(unit['text'] for unit in self.units)

    def manifest(self):
        return {'id': self.id, 'role': self.role, 'path': str(self.path),
                'sha256': self.sha256, 'reader': self.reader, 'units': len(self.units)}


def read_document(path: Path, document_id: str, role: str, *, ocr=False,
                  tessdata=None, ocr_language='eng+heb') -> Document:
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    units = []
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        with pymupdf.open(path) as pdf:
            for index, page in enumerate(pdf, 1):
                text = page.get_text()
                used_ocr = False
                images = page.get_image_info()
                large_image = any(pymupdf.Rect(image['bbox']).get_area() > page.rect.get_area() * 0.2 for image in images)
                needs_ocr = large_image or (not text.strip() and (images or page.get_drawings()))
                if needs_ocr or (ocr and images):
                    if not ocr:
                        raise ValueError(f'Page {index} contains scanned content; enable OCR for scanned PDFs')
                    textpage = page.get_textpage_ocr(language=ocr_language, dpi=200,
                                                    full=not bool(text.strip()), tessdata=tessdata)
                    text = page.get_text(textpage=textpage)
                    used_ocr = True
                    if not text.strip():
                        raise ValueError(f'OCR found no text on page {index}')
                if text.strip():
                    units.append({'text': text, 'page': index, 'ocr': used_ocr})
        reader = 'pdf'
    elif suffix == '.docx':
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
        ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
        paragraph_numbers = {id(p): i for i, p in enumerate(root.iter(f'{ns}p'), 1)}
        def paragraph_text(paragraph):
            pieces = []
            for node in paragraph.iter():
                if node.tag == f'{ns}t': pieces.append(node.text or '')
                elif node.tag == f'{ns}tab': pieces.append('\t')
                elif node.tag in (f'{ns}br', f'{ns}cr'): pieces.append('\n')
            return ''.join(pieces)
        body = root.find(f'{ns}body')
        if body is None: raise ValueError('DOCX has no document body')
        def walk(element):
            if element.tag == f'{ns}p':
                text = paragraph_text(element)
                if text.strip(): units.append({'text': text, 'paragraph': paragraph_numbers[id(element)]})
            elif element.tag == f'{ns}tr':
                paragraphs = list(element.iter(f'{ns}p'))
                text = '\t'.join(paragraph_text(p) for p in paragraphs)
                if text.strip():
                    units.append({'text': text, 'paragraph': paragraph_numbers[id(paragraphs[0])],
                                  'paragraph_end': paragraph_numbers[id(paragraphs[-1])]})
            else:
                for child in element: walk(child)
        walk(body)
        reader = 'docx'
    else:
        raise ValueError(f'Unsupported document format: {suffix}; use PDF or DOCX')
    if not units:
        raise ValueError('No text found; the document is empty or requires OCR')
    return Document(document_id, role, path, digest, units, reader)


def text_chunks(text: str, size=6000):
    """UTF-8 byte budget with overlap: all characters reach at least one model call."""
    if not 32 <= size <= 8000:
        raise ValueError('chunk_size must be between 32 and 8000 UTF-8 bytes')
    data = text.encode('utf-8')
    start = 0
    overlap = min(300, size // 4)
    while start < len(data):
        end = min(start + size, len(data))
        while end < len(data) and data[end] & 0xC0 == 0x80:
            end -= 1
        yield data[start:end].decode('utf-8')
        if end == len(data): break
        start = end - overlap
        while data[start] & 0xC0 == 0x80:
            start += 1
