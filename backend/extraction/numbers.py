"""Parse numbers and percentages as printed in KAP portfolio reports.

Reports use two number formats (docs/notes/veri-bulgulari.md, 2.4):
- "tr": 378.395.976,36  (thousands ".", decimal ",")  most managers (İstanbul, Ak, Ziraat, ...)
- "en": 975,489,543.87  (thousands ",", decimal ".")  Garanti and Yapı Kredi

The format is known per report family and passed in. It is never guessed: "1,234" means 1.234 in
one format and 1234 in the other. Input that does not match the format raises ValueError instead of
being converted silently.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Literal

NumberFormat = Literal["tr", "en"]

_SEP = {"tr": (".", ","), "en": (",", ".")}  # (thousands, decimal)
_MINUS = "-−–"  # hyphen, minus sign, en dash
_MISSING = {"", "-", "–", "−"}


def _pattern(fmt: NumberFormat) -> re.Pattern[str]:
    th, dec = (re.escape(c) for c in _SEP[fmt])
    # 12 | 1.234 | 1.234.567 | 1234567, each with an optional decimal part
    return re.compile(rf"^(?:\d{{1,3}}(?:{th}\d{{3}})+|\d+)(?:{dec}\d+)?$")


_PATTERNS = {f: _pattern(f) for f in ("tr", "en")}


def parse_number(text: str, fmt: NumberFormat) -> Decimal | None:
    """'1.234,56' -> Decimal('1234.56') with fmt='tr'. Empty or '-' -> None.

    Handles a leading minus (also the Unicode minus) and parentheses: '(11,11)' -> -11.11.
    """
    if fmt not in _SEP:
        raise ValueError(f"unknown number format: {fmt!r}")
    s = text.strip().replace(" ", "").replace(" ", "")
    if s in _MISSING:
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if s and s[0] in _MINUS:
        negative, s = not negative, s[1:]
    if not _PATTERNS[fmt].match(s):
        raise ValueError(f"{text!r} does not match number format {fmt!r}")
    th, dec = _SEP[fmt]
    value = Decimal(s.replace(th, "").replace(dec, "."))
    return -value if negative else value


def parse_percent(text: str, fmt: NumberFormat) -> Decimal | None:
    """Percent to fraction: '%2,98' -> 0.0298, '0.07%' -> 0.0007, '12,02' -> 0.1202.

    The caller knows the column is a percentage, so a bare number is read as percent too.
    """
    s = text.strip().replace("%", "").strip()
    value = parse_number(s, fmt)
    return None if value is None else value / 100


_TR_HINT = re.compile(r"\d{1,3}(?:\.\d{3})+,\d+")
_EN_HINT = re.compile(r"\d{1,3}(?:,\d{3})+\.\d+")


def detect_format(lines: Iterable[str]) -> NumberFormat | None:
    """Fallback only: guess the format from unambiguous numbers in the text.

    Counts only numbers with both a thousands and a decimal separator. Returns None when there is
    no evidence or the evidence is mixed. The primary source is the format of the report family.
    """
    tr = en = 0
    for line in lines:
        tr += len(_TR_HINT.findall(line))
        en += len(_EN_HINT.findall(line))
    if tr == en:
        return None
    if min(tr, en) * 10 > max(tr, en):  # mixed text: do not decide
        return None
    return "tr" if tr > en else "en"
