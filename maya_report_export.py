"""Export Maya's review-only weekly pattern report as a Word document."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

from maya_product_features import pattern_report

ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "Maya Reports" / "Weekly Pattern Reports"

CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>'''

ROOT_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''


def _document_xml(title: str, report: str) -> str:
    paragraphs = [f"<w:p><w:r><w:rPr><w:b/><w:sz w:val=\"32\"/></w:rPr><w:t>{escape(title)}</w:t></w:r></w:p>"]
    paragraphs.append('<w:p><w:r><w:t>Review-only report. Maya does not treat this document as approved memory.</w:t></w:r></w:p>')
    paragraphs.append(f'<w:p><w:r><w:t>Saved: {escape(datetime.now(timezone.utc).isoformat())}</w:t></w:r></w:p>')
    for line in report.splitlines():
        text = line if line else " "
        paragraphs.append(f'<w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p>')
    body = "".join(paragraphs)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{body}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body>
</w:document>'''


def _next_path() -> tuple[int, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    number = 1
    while (REPORT_DIR / f"Week {number}.docx").exists():
        number += 1
    return number, REPORT_DIR / f"Week {number}.docx"


def export_weekly_report(report: str | None = None) -> str:
    report = report or pattern_report()
    week, output = _next_path()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("word/document.xml", _document_xml(f"Maya Weekly Pattern Report — Week {week}", report))
    return (
        f"Saved Maya's weekly pattern report as Week {week}: {output}\n"
        "The document is review-only and does not update approved memory."
    )


if __name__ == "__main__":
    print(export_weekly_report())
