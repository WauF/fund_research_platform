"""Score extracted rows against a hand-labelled gold file (success criterion 1).

Gold files: data/gold/<CODE>_2026-09.csv, one row per printed row of the portfolio table
(docs/notes/gold-set-rehberi.md). Rows are compared as the report prints them: weights on the basis
the gold file uses (FPD), before the conversion to total value.

How rows are matched and scored:
- A predicted row matches a gold row with the same ISIN (or both without one) and the same value.
  Each gold row is matched at most once, so repeated lots (Garanti) are counted one by one.
  A wrong value or ISIN therefore counts twice: a row the extractor invented and a row it missed.
- A matched row is correct if asset type and fund code also agree. Precision = correct / predicted,
  recall = correct / gold, F1 their harmonic mean.
- Weight error is reported separately, in percentage points, over matched rows on the same basis
  (target: at most 0.10 points).
A gold file that still has draft rows (notes starting with TASLAK) is reported as unverified: its
numbers are not an accuracy measurement.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from schemas.holding import Holding

DRAFT_MARK = "TASLAK"


@dataclass(frozen=True)
class GoldRow:
    row_no: int
    isin: str | None
    value: Decimal
    weight: Decimal
    weight_basis: str
    asset_type: str
    held_fund_code: str | None
    draft: bool


@dataclass
class Score:
    gold_rows: int
    predicted_rows: int
    matched: int
    correct: int
    weight_errors_pp: list[Decimal] = field(default_factory=list)
    basis_mismatches: int = 0
    mistakes: list[str] = field(default_factory=list)  # human-readable, for the review
    gold_verified: bool = True

    @property
    def precision(self) -> float:
        return self.correct / self.predicted_rows if self.predicted_rows else 0.0

    @property
    def recall(self) -> float:
        return self.correct / self.gold_rows if self.gold_rows else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    @property
    def max_weight_error_pp(self) -> Decimal | None:
        return max(self.weight_errors_pp, default=None)

    @property
    def mean_weight_error_pp(self) -> Decimal | None:
        errors = self.weight_errors_pp
        return sum(errors, Decimal(0)) / len(errors) if errors else None


def read_gold(path: Path) -> list[GoldRow]:
    with open(path, encoding="utf-8") as f:
        return [
            GoldRow(
                row_no=int(r["row_no"]),
                isin=r["isin"] or None,
                value=Decimal(r["value"]),
                weight=Decimal(r["weight"]),
                weight_basis=r["weight_basis"],
                asset_type=r["asset_type"],
                held_fund_code=r["held_fund_code"] or None,
                draft=(r.get("notes") or "").startswith(DRAFT_MARK),
            )
            for r in csv.DictReader(f)
        ]


def _key(isin: str | None, value: Decimal) -> tuple[str, Decimal]:
    return (isin or "", value.quantize(Decimal("0.01")))


def score(predicted: Sequence[Holding], gold: Sequence[GoldRow]) -> Score:
    unmatched: dict[tuple[str, Decimal], list[GoldRow]] = defaultdict(list)
    for g in gold:
        unmatched[_key(g.isin, g.value)].append(g)

    result = Score(len(gold), len(predicted), 0, 0, gold_verified=not any(g.draft for g in gold))
    for h in predicted:
        candidates = unmatched.get(_key(h.isin, h.value))
        if not candidates:
            result.mistakes.append(f"row {h.row_no}: not in gold ({h.isin}, {h.value})")
            continue
        g = candidates.pop(0)
        result.matched += 1
        wrong = [
            name
            for name, ours, theirs in (
                ("asset_type", h.asset_type.value, g.asset_type),
                ("held_fund_code", h.held_fund_code, g.held_fund_code),
            )
            if ours != theirs
        ]
        if wrong:
            result.mistakes.append(f"row {h.row_no} (gold {g.row_no}): wrong {', '.join(wrong)}")
        else:
            result.correct += 1
        if h.weight_basis.value == g.weight_basis:
            result.weight_errors_pp.append(abs(h.weight - g.weight) * 100)
        else:
            result.basis_mismatches += 1
    for rows in unmatched.values():
        result.mistakes.extend(f"gold row {g.row_no}: missed ({g.isin}, {g.value})" for g in rows)
    return result
