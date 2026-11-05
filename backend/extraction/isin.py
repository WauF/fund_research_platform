"""ISIN validation and repair candidates.

Cases seen in the reports (docs/notes/veri-bulgulari.md, 2.4):
- An ISIN split over two lines: 'TRMDLYWWWW' + 'W9'
- 'W'-padded fund ISINs (TRMDLYWWWWW9) are valid ISINs
- OCR mixes up 'O' and '0': 'TRYNRPOO0789' (correct: TRYNRPO00789)

CAUTION: the check digit does not catch every OCR error. 'TRYNRPOO0789' and 'TRYNRPO00789' are
both valid, because a letter (O = 24) and a digit (0) expand to digit strings of different length
and Luhn sometimes misses the swap. ISINs read by OCR must therefore be matched against known
ISINs (corpus, other reports): resolve_against_known().

Repair candidates are suggestions only: the record still goes to needs_review; a person decides.
"""

from __future__ import annotations

import itertools
import re

_SHAPE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
# Characters OCR commonly confuses
_OCR_SWAPS = {"O": "0", "0": "O", "I": "1", "1": "I", "S": "5", "5": "S", "B": "8", "8": "B"}


def normalize(text: str) -> str:
    """Drop whitespace and line breaks, upper-case."""
    return re.sub(r"\s+", "", text).upper()


def check_digit(body: str) -> int:
    """ISO 6166 (Luhn) check digit for the first 11 characters."""
    if len(body) != 11:
        raise ValueError("the check digit needs exactly 11 characters")
    digits = "".join(str(int(c, 36)) for c in body)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - total % 10) % 10


def is_valid(isin: str) -> bool:
    s = normalize(isin)
    return bool(_SHAPE.match(s)) and check_digit(s[:11]) == int(s[11])


def join_parts(*parts: str) -> str | None:
    """Join an ISIN split over lines; return it only if the result is valid."""
    s = normalize("".join(parts))
    return s if is_valid(s) else None


def ocr_candidates(isin: str, max_swaps: int = 2) -> list[str]:
    """All valid variants after swapping OCR look-alikes (O/0, I/1, S/5, B/8).

    A valid input is kept in the list, because valid does not mean correct (see the module
    docstring). At most max_swaps characters are changed.
    """
    s = normalize(isin)
    if len(s) != 12:
        return []
    found: list[str] = [s] if is_valid(s) else []
    positions = [i for i, c in enumerate(s) if c in _OCR_SWAPS]
    for k in range(1, max_swaps + 1):
        for combo in itertools.combinations(positions, k):
            chars = list(s)
            for i in combo:
                chars[i] = _OCR_SWAPS[chars[i]]
            cand = "".join(chars)
            if is_valid(cand) and cand not in found:
                found.append(cand)
    return found


def resolve_against_known(isin: str, known: set[str], max_swaps: int = 2) -> str | None:
    """Match an OCR-read ISIN to a set of known ISINs.

    Returns the candidate if exactly one is known; None if none or several are (the record stays
    needs_review).
    """
    hits = [c for c in ocr_candidates(isin, max_swaps) if c in known]
    return hits[0] if len(hits) == 1 else None
