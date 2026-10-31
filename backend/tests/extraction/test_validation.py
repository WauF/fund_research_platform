"""Validation tests: every injected fault is flagged (success criterion 2).

The records are a reduced IRF report (28.09–02.10.2026): its non-fund rows plus one fund, with the
page text as pdfplumber prints it. Values are real; the summary is scaled to these rows.
"""

from datetime import date
from decimal import Decimal

import pytest

from extraction.validation import normalize_text, quote_in_page, validate_report
from schemas.holding import AssetType, Holding, ReportKind, ReportSummary, Status, WeightBasis

PAGE_1 = """IRF-İSTANBUL PORTFÖY BİRİNCİ FON SEPETİ FONU
Eylül-2026
HİSSE SENETLERİ
NETGL TL NET 60.000,00 25,520000 16/09/26 16,290000 977.400,00 100,00 0,29 0,26
GLOBAL
TRENETG00027
MEVDUAT
TEB A.Ş. TL 01/10/26 0 35,00 9.745.000,00 30/09/26 9.754.344,52 35,000000 9.754.344,52 \
100,00 2,93 2,58
DİĞER
Y.Fonu Türk
BGP-AK PORTFÖY TL AK 5.884.985,00 6,796958 29/09/26 6,809489 40.073.740,62 12,93 12,02 10,59
ÜÇÜNCÜ PARA PORTFÖY
TRYAKPO00625
"""
PAGE_2 = """IV-FON TOPLAM DEĞERİ TABLOSU
A-)FON PORTFÖY DEĞERİ 50.805.485,14
FON TOPLAM DEĞERİ 50.805.485,14 100,00 %
"""
PAGES = [PAGE_1, PAGE_2]

SCOPE = dict(
    fund_code="IRF",
    period_start=date(2026, 9, 28),
    period_end=date(2026, 10, 2),
    report_kind=ReportKind.WEEKLY,
    extraction_run_id="test",
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
        row(1, "NETGL", AssetType.EQUITY, "977400.00", "0.0192", "NETGL TL NET 60.000,00",
            isin="TRENETG00027"),
        row(2, "TEB A.Ş.", AssetType.DEPOSIT, "9754344.52", "0.1920",
            "TEB A.Ş. TL 01/10/26 0 35,00 9.745.000,00"),
        row(3, "BGP-AK PORTFÖY", AssetType.FUND, "40073740.62", "0.7888",
            "BGP-AK PORTFÖY TL AK 5.884.985,00", isin="TRYAKPO00625", held_fund_code="BGP"),
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
    rows[0] = rows[0].model_copy(update={"quote": "NETGL TL NET 70.000,00"})
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
    rows[2] = rows[2].model_copy(update={"isin": "TRYNRPOO0789", "quote": "BGP-AK PORTFÖY"})
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
        row(4, "F_AKBNK1026", AssetType.DERIVATIVE, "15563250.00", "0", "NETGL TL NET")
    ]
    assert validate_report(rows, good_summary(), PAGES).ok


def test_zero_weight_currency_row_not_in_value_sum():
    # IDY: 'USD USD FED USD 319.515,13 ... 15.633.971,17 0,00 0,00 2,89' is counted under cash
    # equivalents, not the portfolio value.
    rows = good_rows() + [row(4, "USD", AssetType.CASH, "15633971.17", "0", "TEB A.Ş. TL")]
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
