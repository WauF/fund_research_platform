"""Shared data contract for extraction (package A), look-through (B) and the API (C).

The schema enforces *structure* only: types, ranges and cross-field consistency. Semantic checks
(ISIN check digit, total tolerance, quote found in the document) run in extraction.validation
and set status = needs_review instead of rejecting the record, so a faulty record is never lost:
it goes to human review.

Rationale and examples: docs/notes/veri-bulgulari.md and docs/decisions/.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

FUND_CODE = r"^[A-Z0-9]{2,6}$"
ISIN_SHAPE = r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$"  # shape only; the check digit is a semantic check


class AssetType(StrEnum):
    EQUITY = "equity"
    BOND = "bond"  # government and corporate debt, lease certificates (kira sertifikası)
    FUND = "fund"  # investment fund units (yatırım fonu)
    ETF = "etf"  # exchange-traded fund (BYF), domestic or foreign
    DEPOSIT = "deposit"  # time deposit, participation account (mevduat, katılım hesabı)
    REPO = "repo"  # repo, reverse repo, sale-with-promise-to-buy
    DERIVATIVE = "derivative"  # VİOP futures, options
    CASH = "cash"  # cash collateral, cash equivalents (hazır değerler)
    OTHER = "other"


FUND_LIKE = {AssetType.FUND, AssetType.ETF}


class WeightBasis(StrEnum):
    PORTFOLIO = "portfolio"  # FPD: share of the fund portfolio value
    TOTAL = "total"  # FTD: share of the fund total value
    UNKNOWN = "unknown"  # report gives one ratio without its base (Astra, Ünlü, Ziraat)


class ReportKind(StrEnum):
    MONTHLY = "monthly"
    WEEKLY = "weekly"


class Status(StrEnum):
    OK = "ok"
    NEEDS_REVIEW = "needs_review"


class _ReportScoped(BaseModel):
    """Fields every record taken from one report carries."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    fund_code: str = Field(pattern=FUND_CODE, description="KAP fund code of the reporting fund")
    period_start: date
    period_end: date
    report_kind: ReportKind
    page: int = Field(ge=1, description="PDF page the value is on (1-based)")
    quote: str = Field(min_length=1, description="Verbatim text from the document; checked later")
    extraction_run_id: str = Field(min_length=1)
    status: Status = Status.OK

    @model_validator(mode="after")
    def _period_order(self):
        if self.period_end < self.period_start:
            raise ValueError("period_end is before period_start")
        if self.report_kind is ReportKind.WEEKLY and (self.period_end - self.period_start).days > 7:
            raise ValueError("a weekly report cannot cover more than 7 days")
        return self


class Holding(_ReportScoped):
    """One row of the portfolio value table (Fon Portföy Değeri Tablosu).

    Garanti reports list the same ISIN once per purchase lot; rows are kept apart by row_no and
    summed per ISIN before look-through.
    """

    row_no: int = Field(ge=1, description="Row order within the report; separates lots")
    name: str = Field(min_length=1)
    asset_type: AssetType
    isin: str | None = Field(default=None, pattern=ISIN_SHAPE)
    instrument_code: str | None = Field(
        default=None,
        description="Ticker or fund code as printed in the report (e.g. AEFES.E, GMSTR)",
    )
    held_fund_code: str | None = Field(
        default=None,
        pattern=FUND_CODE,
        description="KAP fund code if the row is a fund or ETF; may differ from the ticker",
    )
    # Short positions (açığa satış) and write-downs are printed with a negative nominal, value and
    # weight (IRB, AP7, TYH equities; TPC ETFs; GTF, TPF bonds), so signs are not restricted.
    nominal: Decimal | None = None
    value: Decimal = Field(description="Total value of the row, in currency; negative if short")
    currency: str = Field(default="TRY", pattern=r"^[A-Z]{3}$")
    weight: Decimal = Field(ge=-1, le=1, description="Fraction, not percent (12.02% -> 0.1202)")
    weight_basis: WeightBasis

    @model_validator(mode="after")
    def _fund_link(self):
        if self.held_fund_code is not None and self.asset_type not in FUND_LIKE:
            raise ValueError("held_fund_code is only allowed on fund or etf rows")
        return self


class ReportSummary(_ReportScoped):
    """Fund total value table (section IV). The total tolerance check relies on these.

    Some reports print liabilities as a positive number (Garanti, Ziraat); here they are always
    zero or negative. Fixing the sign is the parser's job.
    """

    portfolio_value: Decimal = Field(ge=0, description="A) Fund portfolio value (FPD)")
    cash_equivalents: Decimal = Field(default=Decimal(0), ge=0, description="B) Hazır değerler")
    receivables: Decimal = Field(default=Decimal(0), ge=0, description="C) Alacaklar")
    other_assets: Decimal = Field(default=Decimal(0), description="D) Diğer varlıklar")
    liabilities: Decimal = Field(default=Decimal(0), le=0, description="E) Borçlar, negative")
    total_value: Decimal = Field(gt=0, description="Fund total value (FTD)")
    currency: str = Field(default="TRY", pattern=r"^[A-Z]{3}$")

    def components_gap(self) -> Decimal:
        """Sum of the components minus the reported total value.

        Validation compares this with a tolerance; the schema does not reject on it.
        """
        parts = (
            self.portfolio_value
            + self.cash_equivalents
            + self.receivables
            + self.other_assets
            + self.liabilities
        )
        return parts - self.total_value

    def portfolio_share(self) -> Decimal:
        """FPD / FTD: 0.8797 for IRF, 1.0033 for GTM, so weights need not add up to 100%."""
        return self.portfolio_value / self.total_value
