"""Store weights on the fund total value (FTD), as look-through needs (decision 0009).

Validation runs on the weights as the report prints them, usually FPD (share of the portfolio
value), where the weights of all rows must add up to 1. The records are then stored on FTD: a
parent fund owns a share of the child fund's total value, not of its portfolio.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from schemas.holding import AssetType, Holding, ReportSummary, WeightBasis

FOUR_PLACES = Decimal("0.0001")  # weights are printed with 2 decimals of a percent


def to_total_basis(
    holdings: Sequence[Holding],
    summary: ReportSummary | None,
    printed_total: Mapping[int, Decimal | None] | None = None,
) -> list[Holding]:
    """The holdings with weights of the fund total value. Run validation (on FPD) first.

    - total rows are kept as they are;
    - portfolio rows take the printed FTD weight if the extractor read one (printed_total, by
      row_no; the baseline does), otherwise value / total value, rounded to 4 places;
    - derivative rows without a printed FTD scale their own weight (FPD x portfolio / total):
      their value is not value / base (validation leaves them out of the sums too), and a template
      that prints the notional amount would otherwise get a weight of notional / total. In the
      standard template the two agree: 163 derivative rows, value / total value at most 0.0001;
    - unknown rows cannot be converted and are kept: the caller must not use them for look-through.
    Without a summary there is no total value, so the records are returned unchanged.
    The status of each row (from validation) is kept.
    """
    if summary is None:
        return list(holdings)
    printed_total = printed_total or {}
    converted = []
    for h in holdings:
        if h.weight_basis is not WeightBasis.PORTFOLIO:
            converted.append(h)
            continue
        weight = printed_total.get(h.row_no)
        if weight is None and h.asset_type is AssetType.DERIVATIVE:
            weight = (h.weight * summary.portfolio_share()).quantize(FOUR_PLACES)
        elif weight is None:
            weight = (h.value / summary.total_value).quantize(FOUR_PLACES)
        converted.append(h.model_copy(update={"weight": weight, "weight_basis": WeightBasis.TOTAL}))
    return converted
