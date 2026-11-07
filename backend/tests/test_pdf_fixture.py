from datetime import date
from decimal import Decimal

import pytest

from evaluations.pdf_fixture import normalize_holdings_to_total
from schemas.holding import (
    AssetType,
    Holding,
    ReportKind,
    ReportSummary,
    WeightBasis,
)


def _holding(quote: str, weight: str, value: str = "40073740.62") -> Holding:
    return Holding(
        fund_code="IRF",
        period_start=date(2026, 9, 28),
        period_end=date(2026, 10, 2),
        report_kind=ReportKind.WEEKLY,
        page=1,
        quote=quote,
        extraction_run_id="2f1d7c9e-5b1a-4c3e-9f0a-3b6d2e8c1a47",
        row_no=1,
        name="BGP-AK PORTFÖY",
        asset_type=AssetType.FUND,
        held_fund_code="BGP",
        value=Decimal(value),
        weight=Decimal(weight),
        weight_basis=WeightBasis.PORTFOLIO,
    )


def _summary() -> ReportSummary:
    return ReportSummary(
        fund_code="IRF",
        period_start=date(2026, 9, 28),
        period_end=date(2026, 10, 2),
        report_kind=ReportKind.WEEKLY,
        page=2,
        quote="FON TOPLAM DEĞERİ 378.395.976,36 100,00 %",
        extraction_run_id="2f1d7c9e-5b1a-4c3e-9f0a-3b6d2e8c1a47",
        portfolio_value=Decimal("332870561.22"),
        total_value=Decimal("378395976.36"),
    )


def test_uses_printed_ftd_weight_when_pdf_has_both_columns() -> None:
    holding = _holding(
        "BGP-AK PORTFÖY TL AK 5.884.985,00 6,796958 29/09/26 "
        "6,809489 40.073.740,62 12,93 12,02 10,59",
        "0.1202",
    )

    normalized = normalize_holdings_to_total([holding], _summary())[0]

    assert normalized.weight == Decimal("0.1059")
    assert normalized.weight_basis is WeightBasis.TOTAL


def test_falls_back_to_portfolio_share_without_printed_ftd_column() -> None:
    holding = _holding("BGP TL 40.073.740,62 12,93 12,02", "0.1202")

    normalized = normalize_holdings_to_total([holding], _summary())[0]

    assert normalized.weight == pytest.approx(Decimal("0.1202") * _summary().portfolio_share())
    assert normalized.weight_basis is WeightBasis.TOTAL
