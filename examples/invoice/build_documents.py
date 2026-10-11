"""Build fictional PDF/DOCX packets for a different task, with bilingual inputs."""
import json
from pathlib import Path
import zipfile
from xml.sax.saxutils import escape

import pymupdf

ROOT = Path(__file__).parent


def pdf(name, pages):
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        page.insert_text((50, 50), text, fontsize=12)
    document.save(ROOT / name)
    document.close()


def docx(name, paragraphs):
    body = ''.join(f'<w:p><w:pPr><w:bidi/></w:pPr><w:r><w:t>{escape(text)}</w:t></w:r></w:p>' for text in paragraphs)
    with zipfile.ZipFile(ROOT / name, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels', '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + body + '<w:sectPr/></w:body></w:document>')


def case(name, invoice, receipt):
    data = {'profile': 'invoice_payment', 'documents': [
        {'id':'invoice-1','role':'invoice','path':invoice},
        {'id':'receipt-1','role':'receipt','path':receipt}]}
    (ROOT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


if __name__ == '__main__':
    pdf('invoice.pdf', ['Invoice Number: INV-1001\nVendor: Example Supplies Ltd.\nTotal amount: 850.00 USD'])
    pdf('over_limit.pdf', ['Invoice Number: INV-1001\nVendor: Example Supplies Ltd.\nTotal amount: 1850.00 USD'])
    pdf('long_invoice.pdf', ['This is a fictional invoice packet.\nNo invoice values are recorded on this cover page.',
        'General delivery terms for fictional supplies.\nThis page does not state an amount or invoice number.',
        'Invoice Number: INV-1001\nVendor: Example Supplies Ltd.\nTotal amount: 850.00 USD'])
    docx('receipt.docx', ['מספר חשבונית: INV-1001', 'הסחורה התקבלה במלואה.'])
    docx('missing_goods.docx', ['מספר חשבונית: INV-1001', 'הסחורה לא התקבלה.'])
    case('case.json', 'invoice.pdf', 'receipt.docx')
    case('over_limit_case.json', 'over_limit.pdf', 'receipt.docx')
    case('missing_goods_case.json', 'invoice.pdf', 'missing_goods.docx')
    case('long_case.json', 'long_invoice.pdf', 'receipt.docx')
    # Raster-only PDF: OCR must recover English and Hebrew from its pixels.
    original = pymupdf.open()
    page = original.new_page()
    page.insert_htmlbox(pymupdf.Rect(48,48,548,744), '<p>Invoice Number: INV-1001</p><p>Vendor: Example Supplies Ltd.</p><p>Total amount: 850.00 USD</p><p dir="rtl">מסמך בדיקה לדוגמה בעברית</p>')
    image = page.get_pixmap(matrix=pymupdf.Matrix(2,2))
    scanned = pymupdf.open(); page = scanned.new_page()
    page.insert_image(page.rect, stream=image.tobytes('png'))
    scanned.save(ROOT / 'scanned_invoice.pdf', deflate=True); scanned.close(); original.close()
    case('scanned_case.json', 'scanned_invoice.pdf', 'receipt.docx')
    print(f'Fictional documents written to {ROOT}')
