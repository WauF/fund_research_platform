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
from extraction.baseline import ETF_TICKERS
from schemas.holding import FUND_LIKE, AssetType, Holding, ReportSummary, Status, WeightBasis

# Tolerances. The weight tolerance is the ±3% from the presentation; the TL tolerances absorb
# rounding of printed values (two decimals per row).
WEIGHT_TOLERANCE = Decimal("0.03")
SUMMARY_ABS_TOLERANCE = Decimal("1.00")
# Rows sum vs portfolio value. Measured on the 23 standard-template reports of September 2026:
# the largest gap is 0.009% (IRB), so 0.02% leaves 2x headroom and still catches a dropped row of
# 0.05% (ICN in IRF). Revisit when the LLM covers the other templates.
VALUE_REL_TOLERANCE = Decimal("0.0002")
# One row's weight vs value / base value, as a fraction (0.0005 = 0.05 percentage points).
# Measured: clean rows differ by at most 0.00028 (PBI). Two rows printed wrong by the report itself
# exceed it and are flagged on purpose (BGP deposit 6,05 for 5,71%; TPC USD collateral).
ROW_WEIGHT_TOLERANCE = Decimal("0.0005")


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


def _number_forms(value: Decimal) -> set[str]:
    """How a value can be printed: 1.234,56 (tr), 1,234.56 (en), or without thousands separators.

    The value keeps its printed decimals (Decimal("977400.00")), so x10 or /10 gives other text.
    """
    en = f"{abs(value):,}"
    tr = en.replace(",", "_").replace(".", ",").replace("_", ".")
    return {en, tr, en.replace(",", ""), tr.replace(".", "")}


def value_in_quote(value: Decimal, quote: str) -> bool:
    """Is the value printed as a whole token in the quote? Signs and brackets are ignored."""
    tokens = {t.strip("-()") for t in quote.split()}
    return bool(tokens & _number_forms(value))


def fund_code_in_quote(code: str, quote: str) -> bool:
    """Is the KAP fund code (or an exchange ticker known for it, GMSTR for FGS) a word in the quote?

    'BGP-AK PORTFÖY', '(CKL) YAPI', 'IOO - İŞ' all count; 'BGPX' does not.
    """
    names = {code} | {ticker for ticker, kap in ETF_TICKERS.items() if kap == code}
    return any(re.search(rf"(?<![A-Z0-9]){re.escape(n)}(?![A-Z0-9])", quote) for n in names)


def _check_holding(h: Holding, pages: Sequence[str], known_isins: set[str] | None) -> list[Issue]:
    issues: list[Issue] = []

    def add(code: str, message: str) -> None:
        issues.append(Issue(code, message, h.row_no))

    if h.page > len(pages):
        add("page_out_of_range", f"page {h.page} does not exist (document has {len(pages)})")
    elif not quote_in_page(h.quote, pages[h.page - 1]):
        add("quote_not_found", f"quote not found on page {h.page}")

    # The quote is checked against the page, so the numbers and the fund code must come from it.
    # Only the quote counts, not name: name is the extractor's own reading.
    if not value_in_quote(h.value, h.quote):
        add("value_not_in_quote", f"value {h.value} is not printed in the quote")
    if h.held_fund_code is not None and not fund_code_in_quote(h.held_fund_code, h.quote):
        add("fund_code_not_in_quote", f"{h.held_fund_code} does not appear in the quote")

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


def _check_row_weights(holdings: Sequence[Holding], summary: ReportSummary) -> list[Issue]:
    """Each row's weight must match value / base: the portfolio value for FPD, total for FTD.

    Catches a weight misread on a row too small to move the weight total (IRF TMV is 0.08%).
    Skipped where the weight is not value / base: derivatives (notional value), 0-weight currency
    rows (counted under cash equivalents) and rows with an unknown base.
    """
    base = {WeightBasis.PORTFOLIO: summary.portfolio_value, WeightBasis.TOTAL: summary.total_value}
    issues = []
    for h in holdings:
        value_base = base.get(h.weight_basis)
        if not value_base or h.asset_type is AssetType.DERIVATIVE or h.weight == 0:
            continue
        implied = h.value / value_base
        if abs(implied - h.weight) > ROW_WEIGHT_TOLERANCE:
            issues.append(
                Issue(
                    "weight_value_mismatch",
                    f"weight {h.weight:.4f}, but value / {h.weight_basis} value is {implied:.4f}",
                    h.row_no,
                )
            )
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
                    f" ({rel:.3%} apart)",
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
        issues.extend(_check_row_weights(holdings, summary))
        issues.extend(_check_totals(holdings, summary))

    report_level = any(i.row_no is None for i in issues)
    flagged_rows = {i.row_no for i in issues if i.row_no is not None}

    def mark(record):
        return record.model_copy(update={"status": Status.NEEDS_REVIEW})

    out_holdings = [mark(h) if report_level or h.row_no in flagged_rows else h for h in holdings]
    out_summary = mark(summary) if summary is not None and report_level else summary
    return ValidationResult(out_holdings, out_summary, issues)
