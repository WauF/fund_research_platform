"""Fon-içinde-fon yapılarını yaprak maruziyetlerine kadar açar."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import networkx as nx

from exposure.cycles import find_cycles

PathContribution = tuple[list[str], float]
CYCLIC_PATH_FLOOR = 1e-12
MAX_PATH_STEPS = 1_000_000


@dataclass
class LookThroughResult:
    """Look-through hesabı, açıklama yolları ve veri kalitesi özetidir."""

    root: str
    exposures: dict[str, float]
    contributions: dict[str, list[PathContribution]]
    unresolved: dict[str, float]
    cut_off: dict[str, float]
    coverage: float
    report_dates: dict[str, str | None]
    reference_date: str | None
    max_date_gap_days: int | None
    cycles: list[list[str]]
    total: float


def _report_dates(
    graph: nx.DiGraph, root: str
) -> tuple[dict[str, str | None], str | None, int | None]:
    """Fon dönemlerini, kök referans tarihini ve ona en büyük uzaklığı çıkar."""
    reachable = {root, *nx.descendants(graph, root)}
    fund_nodes = sorted(
        node
        for node in reachable
        if graph.nodes[node].get("kind") == "fund" or node.startswith("FUND:")
    )
    dates = {node.removeprefix("FUND:"): graph.nodes[node].get("period_end") for node in fund_nodes}
    reference_date = graph.nodes[root].get("period_end")
    if not dates or reference_date is None:
        return dates, reference_date, None
    try:
        reference = date.fromisoformat(str(reference_date))
        parsed = [date.fromisoformat(str(value)) for value in dates.values() if value is not None]
    except ValueError:
        return dates, reference_date, None
    max_gap = max((abs((value - reference).days) for value in parsed), default=0)
    return dates, reference_date, max_gap


def look_through(
    graph: nx.DiGraph,
    root: str,
    top_k_paths: int = 5,
    cutoff: float = 0.0005,
) -> LookThroughResult:
    """Kök fondan yapraklara etkin ağırlıkları ve en büyük katkı yollarını hesapla."""
    if root not in graph:
        raise ValueError(f"Kök düğüm grafta bulunamadı: {root}")
    if top_k_paths < 1:
        raise ValueError("top_k_paths pozitif bir tam sayı olmalı")
    if cutoff < 0:
        raise ValueError("cutoff negatif olamaz")

    report_dates, reference_date, max_date_gap_days = _report_dates(graph, root)
    reachable = {root, *nx.descendants(graph, root)}
    cycles = find_cycles(graph.subgraph(reachable))

    exposures: defaultdict[str, float] = defaultdict(float)
    paths: defaultdict[str, list[PathContribution]] = defaultdict(list)
    unresolved: defaultdict[str, float] = defaultdict(float)
    cut_off: defaultdict[str, float] = defaultdict(float)

    def record(leaf: str, path: list[str], path_weight: float) -> None:
        """Exposure toplamını güncelle ve yalnız en büyük açıklama yollarını bellekte tut."""
        exposures[leaf] += path_weight
        paths[leaf].append((path, path_weight))
        if len(paths[leaf]) > top_k_paths * 4:
            paths[leaf].sort(key=lambda item: (-abs(item[1]), -item[1], tuple(item[0])))
            del paths[leaf][top_k_paths * 2 :]

    def visit(node: str, path_weight: float, path: list[str]) -> list[tuple[str, float, list[str]]]:
        """Bir yol adımını çöz ve sıradaki fon/varlık adımlarını döndür."""
        data = graph.nodes[node]
        if cycles and len(path) > 1 and abs(path_weight) < CYCLIC_PATH_FLOOR:
            return []  # Cutoff sıfırken bile yakınsayan döngünün sayısal kuyruğunu sonlandır.
        if data.get("kind") == "fund" and data.get("unresolved"):
            leaf = f"UNRESOLVED:{node}"  # Raporu olmayan fon hesapta görünür bir yapraktır.
            record(leaf, path, path_weight)
            unresolved[node] += path_weight
            return []
        if node != root and data.get("kind") == "fund" and abs(path_weight) < cutoff:
            leaf = f"UNRESOLVED:{node}"  # Eşik altındaki fon kaybolmaz, ayrı kalite alanına gider.
            record(leaf, path, path_weight)
            cut_off[node] += path_weight
            return []
        if graph.out_degree(node) == 0:
            record(node, path, path_weight)
            return []

        following = []
        for _, child, edge_data in sorted(graph.out_edges(node, data=True), reverse=True):
            edge_weight = float(edge_data.get("weight", 0.0))
            following.append((child, path_weight * edge_weight, [*path, child]))
        return following

    stack = [(root, 1.0, [root])]
    steps = 0
    while stack:
        node, path_weight, path = stack.pop()
        stack.extend(visit(node, path_weight, path))
        steps += 1
        if steps > MAX_PATH_STEPS:
            raise ValueError("Look-through yolları yakınsamıyor; cycle ağırlıklarını kontrol edin")

    ordered_exposures = {leaf: exposures[leaf] for leaf in sorted(exposures)}
    contributions = {
        leaf: sorted(paths[leaf], key=lambda item: (-abs(item[1]), -item[1], tuple(item[0])))[
            :top_k_paths
        ]
        for leaf in sorted(paths)
    }
    total = sum(ordered_exposures.values())
    gross_total = sum(abs(weight) for weight in ordered_exposures.values())
    unavailable_total = sum(abs(weight) for weight in unresolved.values()) + sum(
        abs(weight) for weight in cut_off.values()
    )
    coverage = 1.0 - unavailable_total / gross_total if gross_total else 0.0
    return LookThroughResult(
        root=root,
        exposures=ordered_exposures,
        contributions=contributions,
        unresolved=dict(sorted(unresolved.items())),
        cut_off=dict(sorted(cut_off.items())),
        coverage=coverage,
        report_dates=report_dates,
        reference_date=reference_date,
        max_date_gap_days=max_date_gap_days,
        cycles=cycles,
        total=total,
    )
