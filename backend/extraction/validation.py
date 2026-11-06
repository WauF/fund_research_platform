"""Check extracted records against the document and the report's own totals.

Nothing here rejects a record. A failed check adds an Issue and sets status = needs_review, so the
record is kept out of results but is still there for the review screen (presentation, slide 10).
The LLM proposes; this module verifies (slide 9).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from extraction import isin as isin_mod
from schemas.holding import FUND_LIKE, AssetType, Holding, ReportSummary, Status, WeightBasis

# Tolerances. The weight tolerance is the ±3% from the presentation; the TL tolerances absorb
# rounding of printed values (two decimals per row).
WEIGHT_TOLERANCE = Decimal("0.03")
VALUE_REL_TOLERANCE = Decimal("0.005")
SUMMARY_ABS_TOLERANCE = Decimal("1.00")


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    row_no: int | None = None  # None: the issue concerns the whole report


@dataclass
class ValidationResult:
    holdings: list[Holding]
    summary: ReportSummary | None
    issues: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def normalize_text(text: str) -> str:
    """Casefold, unify Unicode forms and collapse all whitespace to single spaces.

    The LLM may re-wrap a quote, and PDF text breaks lines mid-cell, so quotes are compared on this
    form. Characters are not otherwise changed: a quote must still be verbatim.
    """
    text = unicodedata.normalize("NFKC", text).replace("İ", "i").replace("I", "ı")
    return re.sub(r"\s+", " ", text.casefold()).strip()


def quote_in_page(quote: str, page_text: str) -> bool:
    """Is the quote on the page? Whitespace and line breaks are ignored on both sides."""
    q = normalize_text(quote)
    return bool(q) and q.replace(" ", "") in normalize_text(page_text).replace(" ", "")


def _check_holding(h: Holding, pages: Sequence[str], known_isins: set[str] | None) -> list[Issue]:
    issues: list[Issue] = []

    def add(code: str, message: str) -> None:
        issues.append(Issue(code, message, h.row_no))

    if h.page > len(pages):
        add("page_out_of_range", f"page {h.page} does not exist (document has {len(pages)})")
    elif not quote_in_page(h.quote, pages[h.page - 1]):
        add("quote_not_found", f"quote not found on page {h.page}")

    if h.isin is not None:
        if not isin_mod.is_valid(h.isin):
            add("isin_check_digit", f"{h.isin} fails the ISIN check digit")
        elif known_isins is not None and h.isin not in known_isins:
            match = isin_mod.resolve_against_known(h.isin, known_isins)
            hint = f"; did you mean {match}?" if match else ""
            add("isin_unknown", f"{h.isin} is not a known ISIN{hint}")

    # A domestic fund or ETF needs its KAP code for look-through; a foreign ETF is a leaf.
    domestic = h.isin is None or h.isin.startswith("TR")
    if h.asset_type in FUND_LIKE and domestic and h.held_fund_code is None:
        add("fund_code_missing", "fund or ETF row without held_fund_code: look-through stops here")
    return issues


def _check_totals(holdings: Sequence[Holding], summary: ReportSummary) -> list[Issue]:
    issues: list[Issue] = []

    gap = summary.components_gap()
    if abs(gap) > SUMMARY_ABS_TOLERANCE:
        issues.append(
            Issue("summary_components_mismatch", f"summary components differ from total by {gap}")
        )

    # Rows outside the portfolio value: derivatives carry a notional value, and foreign currency
    # rows with a 0 portfolio weight are counted under cash equivalents (IDY, ECA, TPC).
    valued = [h for h in holdings if h.asset_type is not AssetType.DERIVATIVE and h.weight != 0]
    value_sum = sum((h.value for h in valued), Decimal(0))
    if summary.portfolio_value and valued:
        rel = abs(value_sum - summary.portfolio_value) / summary.portfolio_value
        if rel > VALUE_REL_TOLERANCE:
            issues.append(
                Issue(
                    "holdings_value_mismatch",
                    f"rows sum to {value_sum}, portfolio value is {summary.portfolio_value}"
                    f" ({rel:.2%} apart)",
                )
            )

    # The weights of all rows must add up to what their base implies: 1 for portfolio weights,
    # FPD / FTD for total weights. Rows with an unknown base cannot be checked this way.
    expected = {
        WeightBasis.PORTFOLIO: Decimal(1),
        WeightBasis.TOTAL: summary.portfolio_share(),
    }
    bases = {h.weight_basis for h in holdings}
    if len(bases) == 1 and (basis := bases.pop()) in expected:
        weight_sum = sum((h.weight for h in holdings), Decimal(0))
        if abs(weight_sum - expected[basis]) > WEIGHT_TOLERANCE:
            issues.append(
                Issue(
                    "weights_mismatch",
                    f"{basis} weights sum to {weight_sum:.4f}, expected {expected[basis]:.4f}",
                )
            )
    return issues


def validate_report(
    holdings: Sequence[Holding],
    summary: ReportSummary | None,
    pages: Sequence[str],
    known_isins: set[str] | None = None,
) -> ValidationResult:
    """Validate one report's records.

    pages: the document text, one string per page (as the extractor saw it).
    known_isins: ISINs known from the corpus; enables the OCR-safe check.

    A row-level issue marks that row needs_review. A report-level issue (totals) marks every row
    and the summary needs_review, because we cannot tell which row is wrong.
    """
    issues: list[Issue] = []
    for h in holdings:
        issues.extend(_check_holding(h, pages, known_isins))

    if summary is None:
        issues.append(Issue("summary_missing", "no fund total value table: totals not checked"))
    else:
        if summary.page > len(pages) or not quote_in_page(summary.quote, pages[summary.page - 1]):
            issues.append(Issue("summary_quote_not_found", "summary quote not found"))
        issues.extend(_check_totals(holdings, summary))

    report_level = any(i.row_no is None for i in issues)
    flagged_rows = {i.row_no for i in issues if i.row_no is not None}

    def mark(record):
        return record.model_copy(update={"status": Status.NEEDS_REVIEW})

    out_holdings = [mark(h) if report_level or h.row_no in flagged_rows else h for h in holdings]
    out_summary = mark(summary) if summary is not None and report_level else summary
    return ValidationResult(out_holdings, out_summary, issues)
