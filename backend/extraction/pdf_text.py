"""PDF to text, one string per page (decision 0006: pdfplumber).

Page numbers matter: every extracted record cites its page, and validation looks for the quote on
that page. The text returned here is exactly what validation and the review screen should see.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber

# Broken font mappings seen in KAP PDFs (docs/notes/veri-bulgulari.md, 2.4). Applied only where a
# caller asks for it, for matching headers; quotes are always taken from the unrepaired text.
_REPAIRS = str.maketrans({"Ġ": "İ", "ġ": "ş", "Ģ": "Ş"})


def extract_pages(path: str | Path) -> list[str]:
    """Text of each page. An empty string marks a page without a text layer (scanned: needs OCR)."""
    with pdfplumber.open(path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def is_scanned(pages: list[str]) -> bool:
    """True if no page has text: the PDF is an image and needs OCR first."""
    return not any(p.strip() for p in pages)


def repair_encoding(text: str) -> str:
    """Undo known broken font mappings (ECA: 'BĠRĠNCĠ' -> 'BİRİNCİ', 'ALIġ' -> 'ALIş')."""
    return text.translate(_REPAIRS)
