import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from exposure.graph import build_graph, node_key
from schemas.holding import AssetType, Holding, ReportKind, WeightBasis

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "slide8.json"


def load_holdings() -> list[Holding]:
    """Slayt 8 fixture satırlarını ortak şemayla doğrulayarak yükle."""
    rows = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["holdings"]
    return [Holding.model_validate(row) for row in rows]


def make_holding(**overrides) -> Holding:
    """Kimlik birim testleri için geçerli bir Holding üret."""
    values = {
        "fund_code": "FA",
        "period_start": date(2026, 9, 1),
        "period_end": date(2026, 9, 30),
        "report_kind": ReportKind.MONTHLY,
        "page": 1,
        "quote": "ASELSAN fixture satırı",
        "extraction_run_id": "fixture:FA:2026-09",
        "row_no": 1,
        "name": "ASELSAN",
        "asset_type": AssetType.EQUITY,
        "isin": "TRAASELS91H2",
        "value": Decimal("0"),
        "weight": Decimal("0.1"),
        "weight_basis": WeightBasis.PORTFOLIO,
    }
    values.update(overrides)
    return Holding.model_validate(values)


def test_node_key_uses_held_fund_code_for_fund() -> None:
    holding = make_holding(asset_type=AssetType.FUND, held_fund_code="FB", isin=None, name="Fund B")
    assert node_key(holding) == "FUND:FB"


def test_node_key_groups_cash_in_try() -> None:
    holding = make_holding(asset_type=AssetType.CASH, isin=None, name="Nakit")
    assert node_key(holding) == "CASH:TRY"


def test_node_key_uses_isin_when_present() -> None:
    holding = make_holding()
    assert node_key(holding) == "ISIN:TRAASELS91H2"


def test_node_key_normalizes_name_without_isin() -> None:
    holding = make_holding(asset_type=AssetType.BOND, isin=None, name="  tr   devlet tahvili  ")
    assert node_key(holding) == "NAME:TR DEVLET TAHVILI"


def test_same_isin_has_same_key_across_funds_and_names() -> None:
    first = make_holding(isin="TRAAKBNK91N6", name="Akbank")
    second = make_holding(isin="TRAAKBNK91N6", name="AKBANK T.A.Ş.")
    assert node_key(first) == node_key(second) == "ISIN:TRAAKBNK91N6"


def test_slide8_edges_and_weights() -> None:
    graph = build_graph(load_holdings())

    assert graph.number_of_edges() == 10
    assert graph["FUND:FA"]["FUND:FB"]["weight"] == pytest.approx(0.40)
    assert graph["FUND:FB"]["FUND:FC"]["weight"] == pytest.approx(0.20)
    assert graph["FUND:FC"]["ISIN:TRATUPRS91E8"]["weight"] == pytest.approx(0.30)
    assert set(graph.predecessors("ISIN:TRAASELS91H2")) == {"FUND:FA", "FUND:FB"}
    assert sum(data["weight"] for _, _, data in graph.out_edges("FUND:FA", data=True)) == (
        pytest.approx(1.0)
    )


def test_slide8_node_kinds_and_unresolved_status() -> None:
    graph = build_graph(load_holdings())

    for fund in ("FUND:FA", "FUND:FB", "FUND:FC", "FUND:FD"):
        assert graph.nodes[fund]["kind"] == "fund"
    for leaf in (
        "ISIN:TRAASELS91H2",
        "ISIN:TRATUPRS91E8",
        "NAME:TR DEVLET TAHVILI",
        "CASH:TRY",
    ):
        assert graph.nodes[leaf]["kind"] == "leaf"

    assert graph.nodes["FUND:FD"]["unresolved"] is True
    assert all(
        graph.nodes[fund]["unresolved"] is False for fund in ("FUND:FA", "FUND:FB", "FUND:FC")
    )


def test_duplicate_edges_are_summed() -> None:
    holdings = [
        make_holding(row_no=1, weight=Decimal("0.10")),
        make_holding(row_no=2, name="ASELSAN ELEKTRONİK", weight=Decimal("0.05")),
    ]

    graph = build_graph(holdings)

    assert graph.number_of_edges() == 1
    assert graph["FUND:FA"]["ISIN:TRAASELS91H2"]["weight"] == pytest.approx(0.15)


def test_empty_holdings_returns_empty_graph() -> None:
    graph = build_graph([])
    assert graph.number_of_nodes() == 0
    assert graph.number_of_edges() == 0


def test_build_graph_validates_dictionary_input() -> None:
    row = make_holding().model_dump(mode="json")
    graph = build_graph([row])  # type: ignore[list-item]
    assert graph["FUND:FA"]["ISIN:TRAASELS91H2"]["weight"] == pytest.approx(0.1)


def test_build_graph_accepts_pydantic_holding_and_linked_etf() -> None:
    holding = Holding(
        fund_code="IRF",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
        report_kind=ReportKind.MONTHLY,
        page=2,
        quote="GMSTR BYF satırı",
        extraction_run_id="exposure-test",
        row_no=1,
        name="ALTIN KATILIM BORSA YATIRIM FONU",
        asset_type=AssetType.ETF,
        instrument_code="GMSTR",
        held_fund_code="FGS",
        value=Decimal("105900"),
        weight=Decimal("0.1059"),
        weight_basis=WeightBasis.TOTAL,
    )

    graph = build_graph([holding])

    assert graph["FUND:IRF"]["FUND:FGS"]["weight"] == pytest.approx(0.1059)
    assert graph.nodes["FUND:FGS"]["kind"] == "fund"
    assert graph.nodes["FUND:FGS"]["unresolved"] is True


def test_fund_period_end_uses_latest_date_and_unresolved_has_none() -> None:
    holdings = [
        make_holding(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            asset_type=AssetType.FUND,
            held_fund_code="FX",
            isin=None,
            name="Fund X",
            weight=Decimal("0.5"),
        ),
        make_holding(row_no=2, weight=Decimal("0.5")),
    ]

    graph = build_graph(holdings)

    assert graph.nodes["FUND:FA"]["period_end"] == "2026-09-30"
    assert graph.nodes["FUND:FX"]["period_end"] is None
