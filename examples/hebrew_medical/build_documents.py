"""Fictional medical packet entirely in Hebrew; all documents are DOCX."""
import json
from pathlib import Path
import zipfile
from xml.sax.saxutils import escape

ROOT = Path(__file__).parent
IDENTITY = ['שם המטופל: ישראל ישראלי', 'תאריך לידה: 1960-01-10', 'מספר רשומה רפואית (MRN): HE-1001']
DOCUMENTS = {
 'request': ['מספר בקשה: PA-HE-1001', 'הפרוצדורה המבוקשת: ביופסיה ריאתית בברונכוסקופיה רובוטית', 'קודי CPT: 31629, 31632, 77012', 'אבחנה: R91.1 נודול ריאתי', 'תאריך השירות המבוקש: 2026-11-15', 'הרופא המבקש: ד״ר דנה ישראלי', 'מוסד רפואי: המרכז הרפואי לדוגמה', 'הגישה הרובוטית בברונכוסקופיה מתאימה למיקום הנגע ולמצב המטופל ומאפשרת ביופסיה בסיכון נמוך יותר.'],
 'clinical': ['קיים נודול ריאתי החשוד לממאירות באונה הימנית העליונה.', 'מומלצת ביופסיה לצורך דגימת רקמה.', 'הגישה הרובוטית בברונכוסקופיה מתאימה למיקום הנגע ולמצב המטופל.', 'לא תועדה התוויית נגד לביצוע ההליך.'],
 'ct': ['נודול באונה הימנית העליונה בגודל 18 x 15 mm עם שוליים משוננים.', 'Lung-RADS: 4B', 'הנודול חשוד לממאירות.', 'מומלצת דגימת רקמה מן הנודול.'],
 'labs': ['בדיקות הקרישה תקינות. INR: 1.0', 'המטופל מתאים לביצוע הליך פולשני מבחינת בדיקות המעבדה.', 'אין התוויית נגד לביצוע הפרוצדורה.'],
 'pft': ['FEV1 טרום מרחיב סימפונות: 62% מהצפוי', 'DLCO: 58% מהצפוי', 'מבחינת תפקודי הריאה המטופל צפוי לסבול ברונכוסקופיה ללא מניעה.', 'אין התוויית נגד לביצוע ברונכוסקופיה.'],
}


def write_docx(path, lines):
    runs = '<w:r>' + '<w:br/>'.join(f'<w:t>{escape(line)}</w:t>' for line in lines) + '</w:r>'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:bidi/></w:pPr>' + runs + '</w:p><w:sectPr/></w:body></w:document>')


if __name__ == '__main__':
    entries = []
    for role, lines in DOCUMENTS.items():
        write_docx(ROOT / f'{role}.docx', IDENTITY + lines)
        entries.append({'id':role, 'role':role, 'path':f'{role}.docx'})
    (ROOT / 'case.json').write_text(json.dumps({'profile':'lung_biopsy','documents':entries},ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
    print(f'Fictional Hebrew medical packet written to {ROOT}')
