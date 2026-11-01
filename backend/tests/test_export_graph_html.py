import json
import math
from pathlib import Path

import pytest

from evaluations.export_graph_html import (
    _node_effective_weights,
    calculate_radial_layout,
    prepare_graph_data,
)
from exposure.graph import build_graph
from schemas.holding import Holding

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Test fixture'ını JSON sözlüğü olarak yükle."""
    path = FIXTURES / name
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["_path"] = path
    return fixture


def effective_by_id(data: dict) -> dict[str, float]:
    """Hazırlanan HTML düğümlerini kimlikten etkin ağırlığa eşle."""
    return {node["id"]: node["effective_weight"] for node in data["nodes"]}


def test_slide8_effective_weights_and_cash_label() -> None:
    fixture = load_fixture("slide8.json")
    data = prepare_graph_data([fixture])
    effective = effective_by_id(data)

    for expected_id, expected_weight in fixture["expected"]["lookthrough"].items():
        node_id = expected_id.removeprefix("UNRESOLVED:")
        assert effective[node_id] == pytest.approx(expected_weight)

    cash = next(node for node in data["nodes"] if node["id"] == "CASH:TRY")
    assert cash["label"] == "Mevduat (tüm bankalar)"
    exported = {item["id"]: item["weight"] for item in data["lookthrough"]["exposures"]}
    assert exported == pytest.approx(fixture["expected"]["lookthrough"])
    assert data["lookthrough"]["coverage"] == pytest.approx(0.972)
    assert data["lookthrough"]["unresolved"][0]["id"] == "UNRESOLVED:FUND:FD"
    assert data["lookthrough"]["cut_off"] == []
    comparison = {item["id"]: item for item in data["lookthrough"]["comparison"]}
    assert comparison["FUND:FB"]["before_weight"] == pytest.approx(0.4)
    assert comparison["FUND:FB"]["after_weight"] == 0.0
    assert comparison["ISIN:TRAASELS91H2"]["before_weight"] == pytest.approx(0.3)
    assert comparison["ISIN:TRAASELS91H2"]["after_weight"] == pytest.approx(0.5)
    assert comparison["ISIN:TRATUPRS91E8"]["before_weight"] == 0.0
    assert comparison["ISIN:TRATUPRS91E8"]["after_weight"] == pytest.approx(0.204)


def test_gtm_gal_effective_weights_match_expected_lookthrough() -> None:
    fixtures = [load_fixture("gtm_2026_09.json"), load_fixture("gal_2026_09.json")]
    expected = load_fixture("gtm_gal_2026_09_expected.json")["expected"]["lookthrough"]
    effective = effective_by_id(prepare_graph_data(fixtures))

    for node_id, expected_weight in expected.items():
        assert effective[node_id] == pytest.approx(expected_weight)


def test_radial_layout_keeps_subfund_leaves_in_its_slice() -> None:
    fixture = load_fixture("slide8.json")
    graph = build_graph([Holding.model_validate(row) for row in fixture["holdings"]])
    root = "FUND:FA"
    fund = "FUND:FB"
    layout = calculate_radial_layout(
        graph,
        root,
        _node_effective_weights(graph, root),
        top_n=12,
        expanded_funds={fund},
    )

    assert layout["positions"][root] == {"x": 0.0, "y": 0.0}
    fund_slice = layout["fund_slices"][fund]
    for child in graph.successors(fund):
        position = layout["positions"][child]
        angle = math.atan2(position["y"], position["x"])
        distance = abs(
            math.atan2(
                math.sin(angle - fund_slice["center"]),
                math.cos(angle - fund_slice["center"]),
            )
        )
        assert distance <= fund_slice["span"] / 2
