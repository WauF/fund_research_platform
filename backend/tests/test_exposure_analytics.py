"""Matris doğrulaması, HHI ve fon örtüşmesi testleri."""

import json
from pathlib import Path

import pytest

from exposure.analytics import (
    compare_methods,
    direct_exposures,
    fund_overlap,
    herfindahl_hirschman,
    matrix_look_through,
)
from exposure.graph import build_graph
from exposure.lookthrough import look_through
from schemas.holding import Holding

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Fixture JSON'unu yükle."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def graph_from(*fixtures: dict):
    """Fixture holding'lerini doğrulayıp tek graf kur."""
    holdings = [Holding.model_validate(row) for fixture in fixtures for row in fixture["holdings"]]
    return build_graph(holdings)


@pytest.mark.parametrize("fixture_name", ["slide8.json", "deep.json", "unresolved.json"])
def test_matrix_and_recursive_methods_match(fixture_name: str) -> None:
    fixture = load_fixture(fixture_name)
    comparison = compare_methods(graph_from(fixture), f"FUND:{fixture['root']}")

    assert comparison.matches
    assert comparison.max_abs_difference <= 1e-9
    assert comparison.matrix == pytest.approx(comparison.recursive, abs=1e-9)


def test_matrix_matches_real_gtm_gal_expected_values() -> None:
    gtm = load_fixture("gtm_2026_09.json")
    gal = load_fixture("gal_2026_09.json")
    expected = load_fixture("gtm_gal_2026_09_expected.json")["expected"]["lookthrough"]

    assert matrix_look_through(graph_from(gtm, gal), "FUND:GTM") == pytest.approx(
        expected, abs=1e-9
    )


def test_matrix_solves_convergent_cycles_and_matches_recursive() -> None:
    cycle = load_fixture("cycle.json")
    graph = graph_from(cycle)

    matrix = matrix_look_through(graph, "FUND:FA")
    recursive = look_through(graph, "FUND:FA", cutoff=0).exposures

    assert matrix == pytest.approx(recursive, abs=1e-9)
    assert matrix == pytest.approx(
        {
            "ISIN:TRAASELS91H2": 0.501010101010101,
            "NAME:TR DEVLET TAHVILI": 0.498989898989899,
        }
    )


def test_hhi_matches_real_fixture_before_and_after_lookthrough() -> None:
    gtm = load_fixture("gtm_2026_09.json")
    gal = load_fixture("gal_2026_09.json")
    graph = graph_from(gtm, gal)
    expected = load_fixture("gtm_gal_2026_09_expected.json")["expected"]

    before = herfindahl_hirschman(direct_exposures(graph, "FUND:GTM"))
    after = herfindahl_hirschman(look_through(graph, "FUND:GTM", cutoff=0).exposures)

    assert before == pytest.approx(expected["hhi_reported"], abs=1e-10)
    assert after == pytest.approx(expected["hhi_lookthrough"], abs=1e-10)


def test_overlap_is_symmetric_and_reports_shared_positions() -> None:
    first = {"A": 0.50, "B": 0.30, "C": 0.20}
    second = {"A": 0.20, "B": 0.50, "D": 0.30}

    forward = fund_overlap(first, second)
    backward = fund_overlap(second, first)

    assert forward.score == pytest.approx(0.50)
    assert forward.shared == pytest.approx({"A": 0.20, "B": 0.30})
    assert backward.score == pytest.approx(forward.score)


def test_hhi_and_overlap_normalize_incomplete_portfolios() -> None:
    incomplete = {"A": 0.40, "B": 0.40}

    assert herfindahl_hirschman(incomplete) == pytest.approx(0.5)
    assert fund_overlap(incomplete, {"A": 0.25, "B": 0.25}).score == pytest.approx(1.0)


def test_negative_weights_use_gross_exposure_and_opposite_sides_do_not_overlap() -> None:
    assert herfindahl_hirschman({"LONG": 0.6, "SHORT": -0.4}) == pytest.approx(0.52)
    assert fund_overlap({"A": -0.5}, {"A": -0.2}).score == pytest.approx(1.0)
    assert fund_overlap({"A": -0.5}, {"A": 0.2}).score == 0.0
