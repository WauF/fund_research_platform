"""Bir veya daha fazla holding JSON'undan etkileşimli exposure grafiği dışa aktar."""

from __future__ import annotations

import argparse
import json
import math
import sys
import webbrowser
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import networkx as nx

BACKEND_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = BACKEND_DIR / "evaluations" / "results"
TEMPLATE_PATH = BACKEND_DIR / "evaluations" / "templates" / "graph.html"
sys.path.insert(0, str(BACKEND_DIR))

from evaluations.pdf_fixture import load_pdf_fixture  # noqa: E402
from exposure.analytics import (  # noqa: E402
    compare_methods,
    direct_exposures,
    fund_overlap,
    herfindahl_hirschman,
)
from exposure.graph import build_graph, node_key  # noqa: E402
from exposure.lookthrough import look_through  # noqa: E402
from schemas.holding import Holding  # noqa: E402

R1 = 350.0
R2 = 750.0
PATH_FLOOR = 1e-12
MAX_PATH_STEPS = 1_000_000


def _edge_contribution(
    source: str, target: str, graph: nx.DiGraph, effective: dict[str, float]
) -> float:
    """Bir kenarın kökten bakınca etkin katkısını döndür."""
    return effective.get(source, 0.0) * float(graph[source][target].get("weight", 0.0))


def _visible_targets(
    graph: nx.DiGraph,
    source: str,
    effective: dict[str, float],
    top_n: int,
) -> tuple[list[str], list[str]]:
    """Fon hedeflerini daima, toplam hedef sayısını mümkünse N ile sınırla."""
    targets = sorted(
        graph.successors(source),
        key=lambda target: (-abs(_edge_contribution(source, target, graph, effective)), target),
    )
    funds = [target for target in targets if graph.nodes[target].get("kind") == "fund"]
    leaves = [target for target in targets if graph.nodes[target].get("kind") != "fund"]
    leaf_limit = max(0, top_n - len(funds))
    return [*funds, *leaves[:leaf_limit]], leaves[leaf_limit:]


def _angle_distance(first: float, second: float) -> float:
    """İki açının çember üzerindeki en kısa mutlak farkını hesapla."""
    return abs(math.atan2(math.sin(first - second), math.cos(first - second)))


def _remaining_angles(count: int, slices: list[tuple[float, float]]) -> list[float]:
    """Dilimlerin dışında kalan çemberi saat yönünde eşit aralıklara böl."""
    if count == 0:
        return []
    samples = 7200
    allowed = []
    for index in range(samples):
        # Ekranda -90° üst yönüdür; buradan saat yönünde ilerle.
        angle = -math.pi / 2 + 2 * math.pi * index / samples
        # Dilim sınırında etiket ve paylaşılan düğümler için küçük bir koridor bırak.
        if all(
            _angle_distance(angle, center) > span / 2 + math.radians(8) for center, span in slices
        ):
            allowed.append(angle)
    if not allowed:
        return [-math.pi / 2 + 2 * math.pi * index / count for index in range(count)]
    return [allowed[round(index * len(allowed) / count) % len(allowed)] for index in range(count)]


def calculate_radial_layout(
    graph: nx.DiGraph,
    root: str,
    effective: dict[str, float],
    top_n: int = 12,
    expanded_funds: set[str] | None = None,
) -> dict[str, Any]:
    """Kök halkası ve alt-fon dilimleri için deterministik radyal koordinatlar üret."""
    expanded = expanded_funds or set()
    positions: dict[str, dict[str, float]] = {root: {"x": 0.0, "y": 0.0}}
    root_targets, root_hidden = _visible_targets(graph, root, effective, top_n)
    root_items = [*root_targets]
    root_other = f"OTHER:{root}"
    if root_hidden:
        root_items.append(root_other)

    opened = [
        target
        for target in root_targets
        if target in expanded
        and graph.nodes[target].get("kind") == "fund"
        and graph.out_degree(target)
    ]
    fund_slices: dict[str, dict[str, float]] = {}
    for index, fund in enumerate(opened):
        visible, hidden = _visible_targets(graph, fund, effective, top_n)
        visible_count = len(visible) + bool(hidden)
        span = math.radians(min(140.0, max(60.0, 25.0 * math.sqrt(max(visible_count, 1)))))
        center = 2 * math.pi * index / max(len(opened), 1)
        fund_slices[fund] = {"center": center, "span": span}
        positions[fund] = {"x": R1 * math.cos(center), "y": R1 * math.sin(center)}

    other_root_items = [item for item in root_items if item not in opened]
    slice_pairs = [(item["center"], item["span"]) for item in fund_slices.values()]
    root_angles = _remaining_angles(len(other_root_items), slice_pairs)
    ordered_root_items = sorted(
        other_root_items,
        key=lambda item: (
            -sum(_edge_contribution(root, target, graph, effective) for target in root_hidden)
            if item == root_other
            else -_edge_contribution(root, item, graph, effective),
            item,
        ),
    )
    for item, angle in zip(ordered_root_items, root_angles, strict=True):
        positions[item] = {"x": R1 * math.cos(angle), "y": R1 * math.sin(angle)}

    for fund in opened:
        visible, hidden = _visible_targets(graph, fund, effective, top_n)
        fund_other = f"OTHER:{fund}"
        children = [*visible, *([fund_other] if hidden else [])]
        shared = [
            child
            for child in children
            if child in graph and graph.in_degree(child) > 1 and root in graph.predecessors(child)
        ]
        outer = [child for child in children if child not in shared]
        center = fund_slices[fund]["center"]
        span = fund_slices[fund]["span"]
        if len(outer) == 1:
            outer_angles = [center]
        else:
            outer_angles = [
                center - span * 0.42 + span * 0.84 * index / max(len(outer) - 1, 1)
                for index in range(len(outer))
            ]
        two_rows = len(outer) > 10
        for index, (child, angle) in enumerate(zip(outer, outer_angles, strict=True)):
            radius = R2 + (120.0 if two_rows and index % 2 else 0.0)
            positions[child] = {"x": radius * math.cos(angle), "y": radius * math.sin(angle)}
        for index, child in enumerate(shared):
            # Paylaşılan düğümleri yaprak ışınlarının dışına, dilim sınırına yasla.
            side = -1 if index % 2 == 0 else 1
            layer = index // 2
            offset = side * span * 0.48
            angle = center + offset
            radius = (R1 + R2) / 2 + layer * 55.0
            positions[child] = {"x": radius * math.cos(angle), "y": radius * math.sin(angle)}

    return {"positions": positions, "fund_slices": fund_slices}


def calculate_full_radial_layout(
    graph: nx.DiGraph,
    root: str,
    effective: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Bütün erişilebilir düğümleri çakışmayan eş merkezli halkalara yerleştir."""
    positions: dict[str, dict[str, float]] = {root: {"x": 0.0, "y": 0.0}}
    depths = nx.single_source_shortest_path_length(graph, root)
    levels: defaultdict[int, list[str]] = defaultdict(list)
    primary_parent: dict[str, str] = {}
    branch: dict[str, str] = {root: root}

    for node, depth in sorted(depths.items(), key=lambda item: (item[1], item[0])):
        if node == root:
            continue
        parents = [parent for parent in graph.predecessors(node) if depths.get(parent) == depth - 1]
        parent = max(
            parents,
            key=lambda candidate: (
                _edge_contribution(candidate, node, graph, effective),
                candidate,
            ),
            default=root,
        )
        primary_parent[node] = parent
        branch[node] = node if parent == root else branch.get(parent, parent)
        levels[depth].append(node)

    root_order = {
        node: index
        for index, node in enumerate(
            sorted(
                levels.get(1, []),
                key=lambda target: (
                    -_edge_contribution(root, target, graph, effective),
                    target,
                ),
            )
        )
    }
    previous_radius = 0.0
    for depth in sorted(levels):
        ordered = sorted(
            levels[depth],
            key=lambda node: (
                root_order.get(branch[node], len(root_order)),
                primary_parent.get(node, ""),
                -effective.get(node, 0.0),
                node,
            ),
        )
        # Büyük halkalarda düğümler arasında en az yaklaşık 32 px yay mesafesi bırak.
        capacity_radius = len(ordered) * 32.0 / (2 * math.pi)
        radius = max(R1 + (depth - 1) * 360.0, previous_radius + 280.0, capacity_radius)
        previous_radius = radius
        for index, node in enumerate(ordered):
            angle = -math.pi / 2 + 2 * math.pi * index / max(len(ordered), 1)
            positions[node] = {
                "x": radius * math.cos(angle),
                "y": radius * math.sin(angle),
            }
    return positions


def parse_args() -> argparse.Namespace:
    """JSON yollarını ve tarayıcıda açma seçeneğini al."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", nargs="+", type=Path, help="Bir veya daha fazla fixture JSON")
    parser.add_argument("--open", action="store_true", dest="open_browser")
    return parser.parse_args()


def load_fixture(path: Path) -> dict[str, Any]:
    """Fixture JSON'unu veya corpus PDF'ini çizim için yükle."""
    resolved = (path if path.is_absolute() else Path.cwd() / path).resolve()
    if resolved.suffix.casefold() == ".pdf":
        return load_pdf_fixture(resolved)
    with resolved.open(encoding="utf-8") as fixture_file:
        fixture = json.load(fixture_file)
    missing = {"root", "holdings"} - fixture.keys()
    if missing:
        raise ValueError(f"Fixture alanları eksik: {', '.join(sorted(missing))}")
    fixture["_path"] = resolved
    return fixture


def _node_effective_weights(graph: nx.DiGraph, root: str) -> dict[str, float]:
    """Ara fonların görsel boyutu için bütün yakınsayan yolların ağırlıklarını ileri taşı."""
    weights: defaultdict[str, float] = defaultdict(float)
    stack = [(root, 1.0)]
    steps = 0
    while stack:
        source, contribution = stack.pop()
        weights[source] += contribution
        for _, target, edge_data in graph.out_edges(source, data=True):
            next_contribution = contribution * float(edge_data.get("weight", 0.0))
            if abs(next_contribution) >= PATH_FLOOR:
                stack.append((target, next_contribution))
        steps += 1
        if steps > MAX_PATH_STEPS:
            raise ValueError(
                "Görsel ağırlık yolları yakınsamıyor; cycle ağırlıklarını kontrol edin"
            )
    return dict(weights)


def _asset_type(holding: dict[str, Any]) -> str:
    """Asset type değerini enum veya düz metinden küçük harfli metne dönüştür."""
    value = holding.get("asset_type", "other")
    return str(getattr(value, "value", value)).casefold()


def _short_name(node: str, rows: list[dict[str, Any]], kind: str) -> str:
    """Düğüm türüne göre kısa ve kararlı bir kullanıcı etiketi üret."""
    if node.startswith("FUND:"):
        return node.removeprefix("FUND:")
    if node.startswith("CASH:"):
        currency = node.removeprefix("CASH:")
        return "Mevduat (tüm bankalar)" if currency == "TRY" else f"Nakit / mevduat ({currency})"
    if kind == "bond" and node.startswith("ISIN:"):
        return node.removeprefix("ISIN:")
    names = {str(row.get("name", "")).strip() for row in rows if row.get("name")}
    name = min(names, key=lambda item: (len(item), item.casefold())) if names else node
    return name if len(name) <= 18 else f"{name[:17]}…"


def _node_type(
    graph: nx.DiGraph,
    node: str,
    root: str,
    rows: list[dict[str, Any]],
) -> str:
    """HTML renk sözleşmesindeki düğüm türünü belirle."""
    if node == root:
        return "root"
    if graph.nodes[node].get("kind") == "fund":
        return "unresolved" if graph.nodes[node].get("unresolved") else "fund"
    asset_types = {_asset_type(row) for row in rows}
    if "equity" in asset_types:
        return "equity"
    if "bond" in asset_types:
        return "bond"
    if asset_types & {"cash", "deposit"} or node.startswith("CASH:"):
        return "cash"
    return "other"


def _report_data(fixtures: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Özet kartı için kullanılan raporların kod, tarih ve dosya adlarını çıkar."""
    reports: list[dict[str, str]] = []
    for fixture in fixtures:
        summary = fixture.get("report_summary") or {}
        code = str(summary.get("fund_code") or fixture["root"])
        date = str(summary.get("period_end") or fixture.get("period_end") or "tarih yok")
        fixture_path = fixture.get("_path")
        reports.append(
            {
                "code": code,
                "date": date,
                "file": Path(fixture_path).name if fixture_path else f"{code}.json",
            }
        )
    return reports


def _analytics_data(
    graph: nx.DiGraph,
    root: str,
    node_labels: dict[str, str],
) -> dict[str, Any]:
    """Matris kontrolü, HHI ve fonlar arası overlap sonuçlarını HTML için hazırla."""
    method = compare_methods(graph, root)
    largest_differences = sorted(
        method.differences.items(), key=lambda item: (-abs(item[1]), item[0])
    )[:5]

    funds = sorted(
        node
        for node in graph
        if graph.nodes[node].get("kind") == "fund" and graph.out_degree(node) > 0
    )
    distributions: dict[str, dict[str, float]] = {}
    hhi_rows: list[dict[str, Any]] = []
    for fund in funds:
        direct = direct_exposures(graph, fund)
        opened = look_through(graph, fund, cutoff=0).exposures
        distributions[fund] = opened
        reported_hhi = herfindahl_hirschman(direct)
        lookthrough_hhi = herfindahl_hirschman(opened)
        hhi_rows.append(
            {
                "fund": fund,
                "label": node_labels.get(fund, fund.removeprefix("FUND:")),
                "reported": reported_hhi,
                "lookthrough": lookthrough_hhi,
                "change": lookthrough_hhi - reported_hhi,
                "reported_effective_positions": 1 / reported_hhi if reported_hhi else 0.0,
                "lookthrough_effective_positions": 1 / lookthrough_hhi if lookthrough_hhi else 0.0,
            }
        )

    overlap_rows: list[dict[str, Any]] = []
    for first, second in combinations(funds, 2):
        overlap = fund_overlap(distributions[first], distributions[second])
        shared = sorted(overlap.shared.items(), key=lambda item: (-item[1], item[0]))
        overlap_rows.append(
            {
                "first": first,
                "second": second,
                "first_label": node_labels.get(first, first.removeprefix("FUND:")),
                "second_label": node_labels.get(second, second.removeprefix("FUND:")),
                "score": overlap.score,
                "shared_count": len(shared),
                "top_shared": [
                    {
                        "id": node,
                        "label": node_labels.get(
                            node.removeprefix("UNRESOLVED:"),
                            node.removeprefix("UNRESOLVED:"),
                        ),
                        "weight": weight,
                    }
                    for node, weight in shared[:5]
                ],
            }
        )
    overlap_rows.sort(
        key=lambda item: (
            item["first"] != root and item["second"] != root,
            -item["score"],
            item["first"],
            item["second"],
        )
    )
    hhi_rows.sort(key=lambda item: (item["fund"] != root, item["fund"]))
    return {
        "matrix_comparison": {
            "matches": method.matches,
            "tolerance": method.tolerance,
            "max_abs_difference": method.max_abs_difference,
            "recursive_total": sum(method.recursive.values()),
            "matrix_total": sum(method.matrix.values()),
            "leaf_count": len(method.recursive.keys() | method.matrix.keys()),
            "largest_differences": [
                {
                    "id": node,
                    "label": node_labels.get(
                        node.removeprefix("UNRESOLVED:"),
                        node.removeprefix("UNRESOLVED:"),
                    ),
                    "difference": difference,
                }
                for node, difference in largest_differences
            ],
        },
        "hhi": hhi_rows,
        "overlap": overlap_rows,
    }


def prepare_graph_data(fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    """Fixture'ları vis-network için düğüm, kenar ve özet verisine dönüştür."""
    if not fixtures:
        raise ValueError("En az bir fixture gerekli")
    root = f"FUND:{str(fixtures[0]['root']).upper()}"
    holdings = [holding for fixture in fixtures for holding in fixture["holdings"]]
    validated = [Holding.model_validate(holding) for holding in holdings]
    full_graph = build_graph(validated)
    if root not in full_graph:
        raise ValueError(f"Kök düğüm grafta bulunamadı: {root}")
    reachable = {root, *nx.descendants(full_graph, root)}
    graph = full_graph.subgraph(reachable).copy()
    result = look_through(graph, root, top_k_paths=12, cutoff=0)
    effective = _node_effective_weights(graph, root)

    rows_by_node: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    edge_rows: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for holding in holdings:
        source = f"FUND:{holding['fund_code']}"
        target = node_key(holding)
        if source in graph and target in graph:
            rows_by_node[target].append(holding)
            edge_rows[(source, target)].append(holding)

    nodes: list[dict[str, Any]] = []
    for node in graph:
        rows = rows_by_node[node]
        node_type = _node_type(graph, node, root, rows)
        parents = sorted(graph.predecessors(node))
        direct_weights = {
            parent: float(graph[parent][node].get("weight", 0.0)) for parent in parents
        }
        first_row = rows[0] if rows else {}
        exposure_key = f"UNRESOLVED:{node}" if node_type == "unresolved" else node
        node_contributions = result.contributions.get(exposure_key, [])
        if (
            exposure_key in result.exposures
        ):  # Yaprak ağırlığının tek kaynağı look-through motorudur.
            effective[node] = result.exposures[exposure_key]
        paths = [path for path, _ in node_contributions]
        nodes.append(
            {
                "id": node,
                "label": _short_name(node, rows, node_type),
                "type": node_type,
                "effective_weight": effective.get(node, 0.0),
                "direct_weight": max(direct_weights.values(), default=1.0 if node == root else 0.0),
                "direct_weights": direct_weights,
                "parents": parents,
                "row_count": len(rows),
                "isin": node.removeprefix("ISIN:") if node.startswith("ISIN:") else None,
                "page": first_row.get("page"),
                "quote": first_row.get("quote", ""),
                "paths": paths if paths else ([[root]] if node == root else []),
                "contributions": [
                    {"path": path, "weight": contribution}
                    for path, contribution in node_contributions
                ],
                "opened_fund": graph.nodes[node].get("kind") == "fund"
                and graph.out_degree(node) > 0,
                "child_count": graph.out_degree(node),
                "multi_path": len(node_contributions) > 1 or len(parents) > 1,
                "full_name": str(first_row.get("name") or _short_name(node, rows, node_type)),
            }
        )

    edges: list[dict[str, Any]] = []
    for source, target, edge_data in graph.edges(data=True):
        weight = float(edge_data.get("weight", 0.0))
        edges.append(
            {
                "id": f"{source}->{target}",
                "source": source,
                "target": target,
                "weight": weight,
                "effective_weight": effective.get(source, 0.0) * weight,
                "row_count": len(edge_rows[(source, target)]),
            }
        )

    unresolved = sorted(
        (node for node in nodes if node["type"] == "unresolved"),
        key=lambda node: node["effective_weight"],
        reverse=True,
    )
    opened_funds = {
        node
        for node in graph
        if node != root and graph.nodes[node].get("kind") == "fund" and graph.out_degree(node) > 0
    }
    layouts: dict[str, Any] = {
        "radial": {},
        "drilldown": {},
        "full": {"positions": calculate_full_radial_layout(graph, root, effective)},
    }
    for top_n in range(1, 41):
        layouts["radial"][str(top_n)] = {
            "collapsed": calculate_radial_layout(graph, root, effective, top_n),
            "expanded": calculate_radial_layout(graph, root, effective, top_n, opened_funds),
        }
    for fund in sorted(opened_funds):
        layouts["drilldown"][fund] = {
            str(top_n): calculate_radial_layout(graph, fund, effective, top_n)
            for top_n in range(1, 41)
        }
    reports = _report_data(fixtures)
    root_total = sum(
        float(data.get("weight", 0.0)) for _, _, data in graph.out_edges(root, data=True)
    )
    unresolved_total = sum(result.unresolved.values())
    node_labels = {node["id"]: node["label"] for node in nodes}
    analytics = _analytics_data(graph, root, node_labels)
    lookthrough_exposures = []
    for exposure_id, weight in sorted(
        result.exposures.items(), key=lambda item: (-item[1], item[0])
    ):
        node_id = exposure_id.removeprefix("UNRESOLVED:")
        lookthrough_exposures.append(
            {
                "id": exposure_id,
                "node_id": node_id,
                "label": node_labels.get(node_id, node_id),
                "weight": weight,
                "unresolved": node_id in result.unresolved,
                "cut_off": node_id in result.cut_off,
                "contributions": [
                    {"path": path, "weight": contribution}
                    for path, contribution in result.contributions.get(exposure_id, [])
                ],
            }
        )
    after_by_node = {exposure["node_id"]: exposure for exposure in lookthrough_exposures}
    root_direct = {
        target: float(edge_data.get("weight", 0.0))
        for _, target, edge_data in graph.out_edges(root, data=True)
    }
    comparison = []
    for node_id in root_direct.keys() | after_by_node.keys():
        exposure = after_by_node.get(node_id)
        before = root_direct.get(node_id, 0.0)
        after = float(exposure["weight"]) if exposure else 0.0
        comparison.append(
            {
                "id": node_id,
                "label": node_labels.get(node_id, node_id),
                "before_weight": before,
                "after_weight": after,
                "change": after - before,
                "status": (
                    "Cutoff nedeniyle açılmadı"
                    if node_id in result.cut_off
                    else (
                        "Alt fon yapraklarına dağıtıldı"
                        if node_id in opened_funds and exposure is None
                        else "Etkin yaprak exposure"
                    )
                ),
                "contributions": exposure["contributions"] if exposure else [],
            }
        )
    comparison.sort(
        key=lambda item: (
            -max(item["before_weight"], item["after_weight"]),
            item["id"],
        )
    )
    return {
        "root": root,
        "nodes": nodes,
        "edges": edges,
        "layouts": layouts,
        "reports": reports,
        "analytics": analytics,
        "lookthrough": {
            "total": result.total,
            "coverage": result.coverage,
            "exposures": lookthrough_exposures,
            "comparison": comparison,
            "resolved_count": sum(
                not exposure["unresolved"] and not exposure["cut_off"]
                for exposure in lookthrough_exposures
            ),
            "cut_off": [exposure for exposure in lookthrough_exposures if exposure["cut_off"]],
            "unresolved": [
                exposure for exposure in lookthrough_exposures if exposure["unresolved"]
            ],
            "report_dates": result.report_dates,
            "reference_date": result.reference_date,
            "max_date_gap_days": result.max_date_gap_days,
            "cycles": result.cycles,
        },
        "summary": {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "root_total": root_total,
            "coverage": result.coverage,
            "cycles": result.cycles,
            "unresolved_total": unresolved_total,
            "cut_off_total": sum(result.cut_off.values()),
            "unresolved_top": [
                {"id": node["id"], "label": node["label"], "weight": node["effective_weight"]}
                for node in unresolved[:5]
            ],
            "date_mismatch": len({report["date"] for report in reports}) > 1,
        },
    }


def write_html(
    fixtures: list[dict[str, Any]],
    input_paths: list[Path],
    output_path: Path | None = None,
) -> Path:
    """Hazırlanan graf verisini ayrı HTML şablonuna gömüp tek dosya yaz."""
    data = prepare_graph_data(fixtures)
    names = "_".join(path.stem for path in input_paths)
    destination = output_path or RESULTS_DIR / f"{names}_graph.html"
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if "__GRAPH_DATA__" not in template:
        raise ValueError("HTML şablonunda __GRAPH_DATA__ yer tutucusu bulunamadı")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(template.replace("__GRAPH_DATA__", payload), encoding="utf-8")
    return destination.resolve()


def main() -> None:
    """Komut satırındaki fixture'ları etkileşimli tek HTML dosyasına aktar."""
    args = parse_args()
    fixtures = [load_fixture(path) for path in args.fixtures]
    output_path = write_html(fixtures, args.fixtures)
    print(f"HTML kaydedildi: {output_path}")
    if args.open_browser:
        webbrowser.open(output_path.as_uri())


if __name__ == "__main__":
    main()
