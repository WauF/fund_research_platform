"""Schema tests. Values come from the IRF report of 28.09–02.10.2026 (link: data/corpus.csv)."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from schemas.holding import AssetType, Holding, ReportKind, ReportSummary, Status, WeightBasis

IRF_SCOPE = dict(
    fund_code="IRF",
    period_start=date(2026, 9, 28),
    period_end=date(2026, 10, 2),
    report_kind=ReportKind.WEEKLY,
    extraction_run_id="test-run",
)


def bgp_row(**overrides):
    """The BGP row of the IRF report (page 2)."""
    row = dict(
        IRF_SCOPE,
        page=2,
        quote=(
            "BGP-AK PORTFÖY TL AK 5.884.985,00 6,796958 29/09/26 6,809489 40.073.740,62"
            " 12,93 12,02 10,59"
        ),
        row_no=1,
        name="AK PORTFÖY ÜÇÜNCÜ PARA PİYASASI (TL) FONU",
        asset_type=AssetType.FUND,
        isin="TRYAKPO00625",
        instrument_code="BGP",
        held_fund_code="BGP",
        nominal=Decimal("5884985"),
        value=Decimal("40073740.62"),
        weight=Decimal("0.1059"),
        weight_basis=WeightBasis.TOTAL,
    )
    row.update(overrides)
    return row


def irf_summary(**overrides):
    s = dict(
        IRF_SCOPE,
        page=3,
        quote="FON TOPLAM DEĞERİ 378.395.976,36 100,00 %",
        portfolio_value=Decimal("332870561.22"),
        cash_equivalents=Decimal("1085.71"),
        receivables=Decimal("56572172.96"),
        liabilities=Decimal("-11047843.53"),
        total_value=Decimal("378395976.36"),
    )
    s.update(overrides)
    return s


class TestHolding:
    def test_valid_fund_row(self):
        h = Holding(**bgp_row())
        assert h.status is Status.OK
        assert h.held_fund_code == "BGP"

    def test_cash_like_row_needs_no_isin(self):
        h = Holding(
            **bgp_row(
                asset_type=AssetType.DEPOSIT,
                isin=None,
                instrument_code=None,
                held_fund_code=None,
                name="TEB A.Ş. mevduat",
            )
        )
        assert h.isin is None

    @pytest.mark.parametrize("weight", [Decimal("-1.01"), Decimal("1.01")])
    def test_weight_out_of_range_rejected(self, weight):
        with pytest.raises(ValidationError):
            Holding(**bgp_row(weight=weight))

    def test_short_position_allowed(self):
        # IRB, page 1: AEFES TL ANADOLU -64.900,00 ... -1.170.796,00 -0,26 -0,21 -0,21
        h = Holding(
            **bgp_row(
                asset_type=AssetType.EQUITY,
                isin="TRAAEFES91A9",
                held_fund_code=None,
                nominal=Decimal("-64900"),
                value=Decimal("-1170796.00"),
                weight=Decimal("-0.0021"),
            )
        )
        assert h.value < 0 and h.weight < 0

    @pytest.mark.parametrize("isin", ["TRYAKPO0062", "trYAKPO00625", "TRYAKPO0062X", "TRMDLYWWWW"])
    def test_isin_shape_enforced(self, isin):
        with pytest.raises(ValidationError):
            Holding(**bgp_row(isin=isin))

    def test_bad_check_digit_passes_schema(self):
        # The check digit is not the schema's job: an OCR error must reach review, not vanish.
        h = Holding(**bgp_row(isin="TRYAKPO00626"))
        assert h.isin == "TRYAKPO00626"

    def test_held_fund_code_only_on_fund_like_rows(self):
        with pytest.raises(ValidationError, match="held_fund_code"):
            Holding(**bgp_row(asset_type=AssetType.EQUITY))

    def test_etf_may_carry_fund_code_different_from_ticker(self):
        # In the SUA report the ticker is GMSTR; the KAP fund code is FGS.
        h = Holding(
            **bgp_row(
                asset_type=AssetType.ETF, instrument_code="GMSTR", held_fund_code="FGS", isin=None
            )
        )
        assert (h.instrument_code, h.held_fund_code) == ("GMSTR", "FGS")

    def test_garanti_lots_are_separate_rows(self):
        lots = [Holding(**bgp_row(row_no=i)) for i in (1, 2)]
        assert lots[0].row_no != lots[1].row_no

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            Holding(**bgp_row(report_date="2026-10-02"))

    def test_period_order(self):
        with pytest.raises(ValidationError, match="period_end"):
            Holding(**bgp_row(period_start=date(2026, 10, 3)))

    def test_weekly_period_max_seven_days(self):
        with pytest.raises(ValidationError, match="weekly"):
            Holding(**bgp_row(period_start=date(2026, 9, 1), period_end=date(2026, 9, 30)))

    def test_monthly_period_allowed(self):
        h = Holding(
            **bgp_row(
                period_start=date(2026, 9, 1),
                period_end=date(2026, 9, 30),
                report_kind=ReportKind.MONTHLY,
            )
        )
        assert h.report_kind is ReportKind.MONTHLY

    def test_empty_quote_rejected(self):
        with pytest.raises(ValidationError):
            Holding(**bgp_row(quote="  "))


class TestReportSummary:
    def test_irf_components_match_total(self):
        s = ReportSummary(**irf_summary())
        assert s.components_gap() == Decimal("0")

    def test_irf_portfolio_share(self):
        s = ReportSummary(**irf_summary())
        assert round(s.portfolio_share(), 4) == Decimal("0.8797")

    def test_positive_liabilities_rejected(self):
        # Garanti/Ziraat print liabilities as positive; the parser must flip the sign.
        with pytest.raises(ValidationError):
            ReportSummary(**irf_summary(liabilities=Decimal("11047843.53")))

    def test_gap_reported_not_rejected(self):
        s = ReportSummary(**irf_summary(receivables=Decimal("0")))
        assert s.components_gap() == Decimal("-56572172.96")

    def test_garanti_portfolio_above_total(self):
        # GTM: the portfolio value is 100.33% of the total value.
        s = ReportSummary(
            **irf_summary(
                fund_code="GTM",
                portfolio_value=Decimal("978697019.44"),
                cash_equivalents=Decimal("209749.16"),
                receivables=Decimal("1583928.25"),
                liabilities=Decimal("-5001152.98"),
                total_value=Decimal("975489543.87"),
            )
        )
        assert s.portfolio_share() > 1
        assert s.components_gap() == Decimal("0")
