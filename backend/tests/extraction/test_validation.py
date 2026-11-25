"""Validation tests: every injected fault is flagged (success criterion 2).

The records are a reduced IRF report (28.09–02.10.2026): its non-fund rows plus one fund, with the
page text as pdfplumber prints it. Values are real; the summary is scaled to these rows.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from extraction.baseline import ReportMeta, parse_report
from extraction.validation import (
    fund_code_in_quote,
    normalize_text,
    quote_in_page,
    validate_report,
    value_in_quote,
)
from schemas.holding import AssetType, Holding, ReportKind, ReportSummary, Status, WeightBasis

NETGL_LINE = "NETGL TL NET 60.000,00 25,520000 16/09/26 16,290000 977.400,00 100,00 0,29 0,26"
TEB_LINE = (
    "TEB A.Ş. TL 01/10/26 0 35,00 9.745.000,00 30/09/26 9.754.344,52 35,000000 9.754.344,52 "
    "100,00 2,93 2,58"
)
BGP_LINE = (
    "BGP-AK PORTFÖY TL AK 5.884.985,00 6,796958 29/09/26 6,809489 40.073.740,62 12,93 12,02 10,59"
)
# Not IRF rows: a VİOP future (notional value) and a foreign currency row (IDY), for the tests
# of rows that stay out of the value sum.
FUTURE_LINE = "F_AKBNK1026 TL 250,00 62,253000 15.563.250,00 0,00 0,00"
USD_LINE = "USD USD FED USD 319.515,13 48,930300 15.633.971,17 0,00 0,00 2,89"
PAGE_1 = f"""IRF-İSTANBUL PORTFÖY BİRİNCİ FON SEPETİ FONU
Eylül-2026
HİSSE SENETLERİ
{NETGL_LINE}
GLOBAL
TRENETG00027
MEVDUAT
{TEB_LINE}
DİĞER
Y.Fonu Türk
{BGP_LINE}
ÜÇÜNCÜ PARA PORTFÖY
TRYAKPO00625
{FUTURE_LINE}
{USD_LINE}
"""
PAGE_2 = """IV-FON TOPLAM DEĞERİ TABLOSU
A-)FON PORTFÖY DEĞERİ 50.805.485,14
FON TOPLAM DEĞERİ 50.805.485,14 100,00 %
"""
PAGES = [PAGE_1, PAGE_2]

DATA = Path(__file__).parent / "data"
IRF_PAGES = json.loads((DATA / "irf_2026-09_pages.json").read_text(encoding="utf-8"))["pages"]
IRF_META = ReportMeta("IRF", date(2026, 9, 28), date(2026, 10, 2), ReportKind.WEEKLY)

SCOPE = dict(
    fund_code="IRF",
    period_start=date(2026, 9, 28),
    period_end=date(2026, 10, 2),
    report_kind=ReportKind.WEEKLY,
    extraction_run_id=uuid4(),
)


def row(row_no, name, asset_type, value, weight, quote, **extra):
    return Holding(
        **SCOPE,
        page=1,
        row_no=row_no,
        name=name,
        asset_type=asset_type,
        value=Decimal(value),
        weight=Decimal(weight),
        weight_basis=WeightBasis.PORTFOLIO,
        quote=quote,
        **extra,
    )


def good_rows():
    return [
        row(1, "NETGL", AssetType.EQUITY, "977400.00", "0.0192", NETGL_LINE, isin="TRENETG00027"),
        row(2, "TEB A.Ş.", AssetType.DEPOSIT, "9754344.52", "0.1920", TEB_LINE),
        row(3, "BGP-AK PORTFÖY", AssetType.FUND, "40073740.62", "0.7888", BGP_LINE,
            isin="TRYAKPO00625", held_fund_code="BGP"),
    ]  # fmt: skip


def good_summary(**overrides):
    values = dict(
        SCOPE,
        page=2,
        quote="FON TOPLAM DEĞERİ 50.805.485,14",
        portfolio_value=Decimal("50805485.14"),
        total_value=Decimal("50805485.14"),
    )
    values.update(overrides)
    return ReportSummary(**values)


def codes(result):
    return sorted(i.code for i in result.issues)


def test_clean_report_passes():
    result = validate_report(good_rows(), good_summary(), PAGES)
    assert result.ok, result.issues
    assert all(h.status is Status.OK for h in result.holdings)


# --- row-level faults: only that row goes to review -------------------------------------------


def test_wrong_check_digit_flagged():
    rows = good_rows()
    rows[2] = rows[2].model_copy(update={"isin": "TRYAKPO00626"})
    result = validate_report(rows, good_summary(), PAGES)
    assert codes(result) == ["isin_check_digit"]
    assert [h.status for h in result.holdings] == [Status.OK, Status.OK, Status.NEEDS_REVIEW]


def test_quote_not_in_document_flagged():
    rows = good_rows()
    quote = NETGL_LINE.replace("60.000,00", "70.000,00")
    rows[0] = rows[0].model_copy(update={"quote": quote})
    result = validate_report(rows, good_summary(), PAGES)
    assert codes(result) == ["quote_not_found"]
    assert result.holdings[0].status is Status.NEEDS_REVIEW


def test_quote_on_wrong_page_flagged():
    rows = good_rows()
    rows[0] = rows[0].model_copy(update={"page": 2})
    assert codes(validate_report(rows, good_summary(), PAGES)) == ["quote_not_found"]


def test_page_out_of_range_flagged():
    rows = good_rows()
    rows[0] = rows[0].model_copy(update={"page": 9})
    assert codes(validate_report(rows, good_summary(), PAGES)) == ["page_out_of_range"]


def test_fund_without_code_flagged():
    rows = good_rows()
    rows[2] = rows[2].model_copy(update={"held_fund_code": None})
    assert codes(validate_report(rows, good_summary(), PAGES)) == ["fund_code_missing"]


def test_foreign_etf_without_code_is_a_leaf():
    rows = good_rows()
    rows[2] = rows[2].model_copy(
        update={"asset_type": AssetType.ETF, "isin": "US77926X3200", "held_fund_code": None}
    )
    assert validate_report(rows, good_summary(), PAGES).ok


def test_ocr_isin_resolved_against_known():
    rows = good_rows()
    rows[2] = rows[2].model_copy(update={"isin": "TRYNRPOO0789"})
    known = {"TRYAKPO00625", "TRENETG00027", "TRYNRPO00789"}
    result = validate_report(rows, good_summary(), PAGES, known_isins=known)
    assert codes(result) == ["isin_unknown"]
    assert "TRYNRPO00789" in result.issues[0].message


# --- report-level faults: every row goes to review --------------------------------------------


def test_misread_weight_flags_whole_report():
    # Slide 10: "20,00%" read as "2,00%" -> the total is off by more than 3 points.
    rows = good_rows()
    rows[1] = rows[1].model_copy(update={"weight": Decimal("0.0192")})
    result = validate_report(rows, good_summary(), PAGES)
    assert "weights_mismatch" in codes(result)
    assert all(h.status is Status.NEEDS_REVIEW for h in result.holdings)
    assert result.summary.status is Status.NEEDS_REVIEW


def test_missing_row_flags_value_sum():
    result = validate_report(good_rows()[:2], good_summary(), PAGES)
    assert {"holdings_value_mismatch", "weights_mismatch"} <= set(codes(result))


def test_summary_components_mismatch():
    summary = good_summary(receivables=Decimal("1000"))
    assert "summary_components_mismatch" in codes(validate_report(good_rows(), summary, PAGES))


def test_missing_summary_flags_report():
    result = validate_report(good_rows(), None, PAGES)
    assert codes(result) == ["summary_missing"]
    assert all(h.status is Status.NEEDS_REVIEW for h in result.holdings)


def test_derivative_notional_not_in_value_sum():
    rows = good_rows() + [
        row(4, "F_AKBNK1026", AssetType.DERIVATIVE, "15563250.00", "0", FUTURE_LINE)
    ]
    assert validate_report(rows, good_summary(), PAGES).ok


def test_zero_weight_currency_row_not_in_value_sum():
    # IDY: 'USD USD FED USD 319.515,13 ... 15.633.971,17 0,00 0,00 2,89' is counted under cash
    # equivalents, not the portfolio value.
    rows = good_rows() + [row(4, "USD", AssetType.CASH, "15633971.17", "0", USD_LINE)]
    assert validate_report(rows, good_summary(), PAGES).ok


def test_total_weight_basis_uses_portfolio_share():
    # Weights of total value (FTD) add up to FPD / FTD, not to 1.
    rows = [
        h.model_copy(update={"weight": h.weight / 2, "weight_basis": WeightBasis.TOTAL})
        for h in good_rows()
    ]
    summary = good_summary(total_value=Decimal("101610970.28"), receivables=Decimal("50805485.14"))
    assert validate_report(rows, summary, PAGES).ok


def test_input_records_are_not_mutated():
    rows = good_rows()
    rows[0] = rows[0].model_copy(update={"isin": "TRENETG00028"})
    validate_report(rows, good_summary(), PAGES)
    assert rows[0].status is Status.OK


# --- quote matching -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "quote",
    [
        "BGP-AK PORTFÖY TL AK 5.884.985,00",
        "bgp-ak portföy tl ak 5.884.985,00",  # case
        "BGP-AK  PORTFÖY\nTL AK 5.884.985,00",  # re-wrapped
        "ÜÇÜNCÜ PARA PORTFÖY TRYAKPO00625",  # spans a line break
        "İSTANBUL PORTFÖY",  # dotted capital I
    ],
)
def test_quote_found(quote):
    assert quote_in_page(quote, PAGE_1)


@pytest.mark.parametrize("quote", ["", "   ", "BGP-AK PORTFÖY TL AK 5.884.986,00"])
def test_quote_not_found(quote):
    assert not quote_in_page(quote, PAGE_1)


def test_normalize_text():
    assert normalize_text("  İSTANBUL\n  Portföy ") == normalize_text("istanbul portföy")


# --- faults injected into the real IRF report (28.09–02.10.2026, all 23 rows) ------------------
# Each one passed validation before the row-level checks: too small for the totals, or invisible
# to them (a wrong fund code).


@pytest.fixture(scope="module")
def irf():
    return parse_report(IRF_PAGES, IRF_META)


def irf_with(irf, code, **update):
    """IRF's rows with one fund row changed."""
    return [h.model_copy(update=update) if h.held_fund_code == code else h for h in irf.holdings]


def irf_row(irf, code):
    return next(h for h in irf.holdings if h.held_fund_code == code)


def test_irf_clean_passes(irf):
    assert validate_report(irf.holdings, irf.summary, IRF_PAGES).ok


@pytest.mark.parametrize("factor", [Decimal(10), Decimal("0.1")])
def test_irf_small_row_value_and_weight_scaled(irf, factor):
    # TMV is 0.08% of IRF: x10 or /10 on both value and weight keeps value / weight consistent.
    tmv = irf_row(irf, "TMV")
    rows = irf_with(irf, "TMV", value=tmv.value * factor, weight=tmv.weight * factor)
    result = validate_report(rows, irf.summary, IRF_PAGES)
    assert ("value_not_in_quote", tmv.row_no) in {(i.code, i.row_no) for i in result.issues}
    assert "holdings_value_mismatch" in codes(result)


def test_irf_small_row_weight_x5(irf):
    tmv = irf_row(irf, "TMV")
    result = validate_report(irf_with(irf, "TMV", weight=tmv.weight * 5), irf.summary, IRF_PAGES)
    assert codes(result) == ["weight_value_mismatch"]
    flagged = [h.held_fund_code for h in result.holdings if h.status is Status.NEEDS_REVIEW]
    assert flagged == ["TMV"]  # a row-level issue: the other 22 rows stay ok


def test_irf_dropped_row(irf):
    # The loss of ICN (0.05%) is below the 3-point weight tolerance; the value sum catches it.
    rows = [h for h in irf.holdings if h.held_fund_code != "ICN"]
    result = validate_report(rows, irf.summary, IRF_PAGES)
    assert codes(result) == ["holdings_value_mismatch"]
    assert all(h.status is Status.NEEDS_REVIEW for h in result.holdings)


def test_irf_fund_row_relabelled(irf):
    # 'BGP-AK PORTFÖY ...' labelled as DLY: look-through would follow the wrong sub-fund.
    result = validate_report(irf_with(irf, "BGP", held_fund_code="DLY"), irf.summary, IRF_PAGES)
    assert codes(result) == ["fund_code_not_in_quote"]


@pytest.mark.parametrize(
    "code, quote",
    [
        ("BGP", "BGP-AK PORTFÖY TL AK 5.884.985,00"),
        ("IOO", "IOO - İŞ PORTFÖY TL"),
        ("CKL", "(CKL) YAPI KREDİ"),
        ("FGS", "GMSTR TL QNB 1.000,00"),  # exchange ticker of FGS (decision 0003)
    ],
)
def test_fund_code_in_quote(code, quote):
    assert fund_code_in_quote(code, quote)


@pytest.mark.parametrize("code, quote", [("BGP", "BGPX TL 1,00"), ("DLY", "BGP-AK PORTFÖY")])
def test_fund_code_not_in_quote(code, quote):
    assert not fund_code_in_quote(code, quote)


@pytest.mark.parametrize(
    "value, quote",
    [
        ("977400.00", "NETGL TL NET 60.000,00 977.400,00 100,00"),
        ("977400.00", "NETGL USD 60,000.00 977,400.00 100.00"),
        ("-1250.50", "AKBNK TL -100,00 -1.250,50 -0,10"),
        ("977400.00", "NETGL TL 977400,00"),
        ("977400.000000", "NETGL TL NET 60.000,00 977.400,00 100,00"),  # NUMERIC(24,6) from the DB
        ("977400", "NETGL TL NET 60.000,00 977.400,00 100,00"),
    ],
)
def test_value_in_quote(value, quote):
    assert value_in_quote(Decimal(value), quote)


@pytest.mark.parametrize("value", ["97740.000", "9774000.00", "97740.000000"])
def test_value_not_in_quote(value):
    assert not value_in_quote(Decimal(value), "NETGL TL NET 60.000,00 977.400,00 100,00")


def test_irf_revalidated_from_db_precision(irf):
    # Review on #19: records read back from the database carry 6 decimals. They must still pass.
    rows = [
        h.model_copy(update={"value": h.value.quantize(Decimal("0.000001"))}) for h in irf.holdings
    ]
    assert validate_report(rows, irf.summary, IRF_PAGES).ok
