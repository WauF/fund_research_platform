import json
from pathlib import Path

import pytest

from exposure.graph import build_graph
from schemas.holding import Holding, ReportSummary

FIXTURE_DIR = Path(__file__).parent / "fixtures"
GTM_DATA = json.loads((FIXTURE_DIR / "gtm_2026_09.json").read_text(encoding="utf-8"))
GAL_DATA = json.loads((FIXTURE_DIR / "gal_2026_09.json").read_text(encoding="utf-8"))
COMBINED_DATA = json.loads(
    (FIXTURE_DIR / "gtm_gal_2026_09_expected.json").read_text(encoding="utf-8")
)
GTM_ROOT = "FUND:GTM"
GAL_ROOT = "FUND:GAL"


def test_real_fixture_summaries_match_shared_schema() -> None:
    ReportSummary.model_validate(GTM_DATA["report_summary"])
    ReportSummary.model_validate(GAL_DATA["report_summary"])


def unresolved_funds(graph) -> list[str]:
    """Graftaki raporu bulunamamış fon düğümlerini sıralı döndür."""
    return sorted(
        node
        for node, data in graph.nodes(data=True)
        if data["kind"] == "fund" and data["unresolved"]
    )


@pytest.fixture(scope="module")
def gtm_graph():
    """GTM raporunu tek başına grafa dönüştür."""
    return build_graph([Holding.model_validate(row) for row in GTM_DATA["holdings"]])


@pytest.fixture(scope="module")
def gal_graph():
    """GAL raporunu tek başına grafa dönüştür."""
    return build_graph([Holding.model_validate(row) for row in GAL_DATA["holdings"]])


@pytest.fixture(scope="module")
def combined_graph():
    """GTM ve GAL holding satırlarını tek grafta birleştir."""
    rows = GTM_DATA["holdings"] + GAL_DATA["holdings"]
    return build_graph([Holding.model_validate(row) for row in rows])


def test_gtm_root_targets_and_weight_sum(gtm_graph) -> None:
    expected = GTM_DATA["expected"]
    total = sum(data["weight"] for _, _, data in gtm_graph.out_edges(GTM_ROOT, data=True))

    assert gtm_graph.out_degree(GTM_ROOT) == expected["distinct_targets_from_root"]
    assert total == pytest.approx(expected["root_out_weight_sum"])


def test_gtm_has_only_gal_as_unresolved_fund(gtm_graph) -> None:
    assert unresolved_funds(gtm_graph) == GTM_DATA["expected"]["unresolved_funds"]


def test_gtm_akbank_rows_merge_into_one_edge(gtm_graph) -> None:
    akbank_key = "ISIN:TRAAKBNK91N6"
    akbank_rows = [row for row in GTM_DATA["holdings"] if row.get("isin") == "TRAAKBNK91N6"]

    assert len(akbank_rows) == 20
    assert list(gtm_graph.predecessors(akbank_key)) == [GTM_ROOT]
    assert gtm_graph[GTM_ROOT][akbank_key]["weight"] == pytest.approx(
        GTM_DATA["expected"]["lookthrough"][akbank_key]
    )


def test_gtm_gal_rows_merge_into_one_fund_edge(gtm_graph) -> None:
    gal_rows = [row for row in GTM_DATA["holdings"] if row.get("held_fund_code") == "GAL"]
    expected = GTM_DATA["expected"]

    assert len(gal_rows) == expected["rows_for_gal"] == 2
    assert list(gtm_graph.predecessors(GAL_ROOT)) == [GTM_ROOT]
    assert gtm_graph[GTM_ROOT][GAL_ROOT]["weight"] == pytest.approx(
        expected["lookthrough"]["UNRESOLVED:FUND:GAL"]
    )


def test_gtm_all_expected_lookthrough_weights_match(gtm_graph) -> None:
    for expected_key, expected_weight in GTM_DATA["expected"]["lookthrough"].items():
        target = expected_key.removeprefix("UNRESOLVED:")
        assert gtm_graph[GTM_ROOT][target]["weight"] == pytest.approx(expected_weight)


def test_gal_root_targets_weight_sum_and_resolution(gal_graph) -> None:
    expected = GAL_DATA["expected"]
    total = sum(data["weight"] for _, _, data in gal_graph.out_edges(GAL_ROOT, data=True))

    assert gal_graph.out_degree(GAL_ROOT) == expected["distinct_targets_from_root"] == 67
    assert total == pytest.approx(expected["root_out_weight_sum"])
    assert unresolved_funds(gal_graph) == expected["unresolved_funds"] == []


def test_combined_graph_opens_gal_and_has_expected_size(combined_graph) -> None:
    assert combined_graph.nodes[GAL_ROOT]["unresolved"] is False
    assert combined_graph.out_degree(GAL_ROOT) == 67
    assert unresolved_funds(combined_graph) == COMBINED_DATA["expected"]["unresolved_funds"] == []
    assert combined_graph.number_of_nodes() == 93
    assert combined_graph.number_of_edges() == 94


def test_combined_graph_shared_leaves_have_two_predecessors(combined_graph) -> None:
    expected_shared = COMBINED_DATA["expected"]["leaves_reached_by_both_paths"]
    assert expected_shared == ["CASH:TRY", "NAME:TERS REPO"]
    for leaf in expected_shared:
        assert set(combined_graph.predecessors(leaf)) == {GTM_ROOT, GAL_ROOT}
