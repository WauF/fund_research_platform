import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from exposure.graph import build_graph
from exposure.lookthrough import look_through
from schemas.holding import AssetType, Holding, ReportKind, WeightBasis

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Fixture JSON'unu sözlük olarak yükle."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def graph_from(*fixtures: dict):
    """Bir veya daha fazla fixture'ın holding satırlarından tek graf kur."""
    holdings = [
        Holding.model_validate(holding) for fixture in fixtures for holding in fixture["holdings"]
    ]
    return build_graph(holdings)


def assert_contributions(result, leaf: str, expected: list[tuple[list[str], float]]) -> None:
    """Katkı yollarını ve kayan noktalı ağırlıklarını sırayla doğrula."""
    actual = result.contributions[leaf]
    assert [path for path, _ in actual] == [path for path, _ in expected]
    assert [weight for _, weight in actual] == pytest.approx([weight for _, weight in expected])


def test_slide8_exposures_paths_coverage_and_total() -> None:
    fixture = load_fixture("slide8.json")
    result = look_through(graph_from(fixture), "FUND:FA")

    assert result.exposures == pytest.approx(fixture["expected"]["lookthrough"])
    assert_contributions(
        result,
        "ISIN:TRAASELS91H2",
        [
            (["FUND:FA", "ISIN:TRAASELS91H2"], 0.30),
            (["FUND:FA", "FUND:FB", "ISIN:TRAASELS91H2"], 0.20),
        ],
    )
    assert_contributions(
        result,
        "ISIN:TRATUPRS91E8",
        [
            (["FUND:FA", "FUND:FB", "ISIN:TRATUPRS91E8"], 0.12),
            (["FUND:FA", "FUND:FC", "ISIN:TRATUPRS91E8"], 0.06),
            (["FUND:FA", "FUND:FB", "FUND:FC", "ISIN:TRATUPRS91E8"], 0.024),
        ],
    )
    assert result.unresolved == pytest.approx({"FUND:FD": 0.028})
    assert result.cut_off == {}
    assert result.coverage == pytest.approx(0.972)
    assert result.total == pytest.approx(1.0)


@pytest.mark.parametrize("fixture_name", ["unresolved.json", "deep.json"])
def test_small_fixtures_match_expected(fixture_name: str) -> None:
    fixture = load_fixture(fixture_name)
    result = look_through(graph_from(fixture), f"FUND:{fixture['root']}")

    assert result.exposures == pytest.approx(fixture["expected"]["lookthrough"])
    assert result.coverage == pytest.approx(fixture["expected"]["coverage"])
    assert result.total == pytest.approx(fixture["expected"]["total"])


def test_cycle_is_reported_and_converges() -> None:
    fixture = load_fixture("cycle.json")
    result = look_through(graph_from(fixture), f"FUND:{fixture['root']}", cutoff=0)

    assert result.cycles == fixture["expected_cycles"]
    assert result.exposures == pytest.approx(
        {
            "ISIN:TRAASELS91H2": 0.501010101010101,
            "NAME:TR DEVLET TAHVILI": 0.498989898989899,
        },
        abs=1e-10,
    )
    assert result.total == pytest.approx(1.0, abs=1e-10)
    assert result.coverage == pytest.approx(1.0)


def test_gtm_gal_real_data_matches_expected() -> None:
    gtm = load_fixture("gtm_2026_09.json")
    gal = load_fixture("gal_2026_09.json")
    expected = load_fixture("gtm_gal_2026_09_expected.json")["expected"]
    result = look_through(graph_from(gtm, gal), "FUND:GTM", cutoff=0)

    assert result.exposures == pytest.approx(expected["lookthrough"])
    assert result.unresolved == {}
    assert result.cut_off == {}
    assert result.coverage == pytest.approx(1.0)
    assert result.total == pytest.approx(1.0)
    assert result.report_dates == {"GAL": "2026-09-30", "GTM": "2026-09-30"}
    assert result.reference_date == "2026-09-30"
    assert result.max_date_gap_days == 0

    for leaf in ("NAME:TERS REPO", "CASH:TRY"):
        contributions = {tuple(path): weight for path, weight in result.contributions[leaf]}
        detail = expected["both_paths_detail"][leaf]
        assert contributions[("FUND:GTM", leaf)] == pytest.approx(detail["direct_in_gtm"])
        assert contributions[("FUND:GTM", "FUND:GAL", leaf)] == pytest.approx(detail["via_gal"])


def test_gtm_without_gal_is_unresolved() -> None:
    gtm = load_fixture("gtm_2026_09.json")
    result = look_through(graph_from(gtm), "FUND:GTM")
    gal_weight = gtm["expected"]["lookthrough"]["UNRESOLVED:FUND:GAL"]

    assert result.exposures["UNRESOLVED:FUND:GAL"] == pytest.approx(gal_weight)
    assert result.unresolved == pytest.approx({"FUND:GAL": gal_weight})
    assert result.cut_off == {}
    assert result.coverage == pytest.approx(1 - gal_weight)


def test_cutoff_keeps_small_fund_visible_without_opening_it() -> None:
    gtm = load_fixture("gtm_2026_09.json")
    gal = load_fixture("gal_2026_09.json")
    gal_weight = gtm["expected"]["lookthrough"]["UNRESOLVED:FUND:GAL"]

    result = look_through(graph_from(gtm, gal), "FUND:GTM", cutoff=0.03)

    assert result.cut_off == pytest.approx({"FUND:GAL": gal_weight})
    assert result.unresolved == {}
    assert result.exposures["UNRESOLVED:FUND:GAL"] == pytest.approx(gal_weight)
    assert result.coverage == pytest.approx(1 - gal_weight)


def test_path_limit_does_not_change_exposures() -> None:
    fixture = load_fixture("slide8.json")
    graph = graph_from(fixture)

    assert (
        look_through(graph, "FUND:FA", top_k_paths=1).exposures
        == look_through(graph, "FUND:FA", top_k_paths=5).exposures
    )


def test_total_matches_root_outgoing_weight() -> None:
    fixture = load_fixture("deep.json")
    graph = graph_from(fixture)
    root_total = sum(data["weight"] for _, _, data in graph.out_edges("FUND:FA", data=True))

    assert look_through(graph, "FUND:FA").total == pytest.approx(root_total)


def test_max_report_date_gap() -> None:
    holdings = [
        Holding(
            fund_code="FA",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            report_kind=ReportKind.MONTHLY,
            page=1,
            quote="FA → FB",
            extraction_run_id="2f1d7c9e-5b1a-4c3e-9f0a-3b6d2e8c1a47",
            row_no=1,
            name="Fund B",
            asset_type=AssetType.FUND,
            held_fund_code="FB",
            value=Decimal(0),
            weight=Decimal(1),
            weight_basis=WeightBasis.PORTFOLIO,
        ),
        Holding(
            fund_code="FB",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            report_kind=ReportKind.MONTHLY,
            page=1,
            quote="FB → Mevduat",
            extraction_run_id="d679199e-02b5-5d6a-85c9-d0f19ece6716",
            row_no=1,
            name="TL Mevduat",
            asset_type=AssetType.CASH,
            value=Decimal(0),
            weight=Decimal(1),
            weight_basis=WeightBasis.PORTFOLIO,
        ),
    ]

    result = look_through(build_graph(holdings), "FUND:FA")

    assert result.max_date_gap_days == 242
    assert result.reference_date == "2026-09-30"


def test_result_is_deterministic() -> None:
    fixture = load_fixture("slide8.json")
    graph = graph_from(fixture)

    assert look_through(graph, "FUND:FA") == look_through(graph, "FUND:FA")


def test_negative_cutoff_is_rejected() -> None:
    fixture = load_fixture("slide8.json")
    with pytest.raises(ValueError, match="cutoff"):
        look_through(graph_from(fixture), "FUND:FA", cutoff=-0.1)


def test_cutoff_uses_absolute_path_weight_for_short_fund() -> None:
    holdings = [
        Holding(
            fund_code="FA",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            report_kind=ReportKind.MONTHLY,
            page=1,
            quote="FA short FB",
            extraction_run_id="2f1d7c9e-5b1a-4c3e-9f0a-3b6d2e8c1a47",
            row_no=1,
            name="Fund B",
            asset_type=AssetType.FUND,
            held_fund_code="FB",
            value=Decimal("-10"),
            weight=Decimal("-0.10"),
            weight_basis=WeightBasis.PORTFOLIO,
        ),
        Holding(
            fund_code="FB",
            period_start=date(2026, 9, 1),
            period_end=date(2026, 9, 30),
            report_kind=ReportKind.MONTHLY,
            page=1,
            quote="FB cash",
            extraction_run_id="d679199e-02b5-5d6a-85c9-d0f19ece6716",
            row_no=1,
            name="TL Mevduat",
            asset_type=AssetType.CASH,
            value=Decimal("10"),
            weight=Decimal("1"),
            weight_basis=WeightBasis.PORTFOLIO,
        ),
    ]

    result = look_through(build_graph(holdings), "FUND:FA", cutoff=0.05)

    assert result.exposures == pytest.approx({"CASH:TRY": -0.10})
    assert result.cut_off == {}
    assert result.coverage == pytest.approx(1.0)


def test_irf_if_fixture_exists() -> None:
    candidates = sorted(FIXTURES.glob("irf_*.json"))
    if not candidates:
        pytest.skip("IRF fixture henüz yok")
    fixture = json.loads(candidates[0].read_text(encoding="utf-8"))

    result = look_through(graph_from(fixture), f"FUND:{fixture['root']}")

    assert result.coverage < 0.1
    assert len(result.unresolved) == 20
