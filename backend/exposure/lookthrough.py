"""Fon-içinde-fon yapılarını yaprak maruziyetlerine kadar açar."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import networkx as nx

from exposure.cycles import find_cycles

PathContribution = tuple[list[str], float]


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
    cycles = find_cycles(graph)
    if cycles:  # Döngülü grafta sonlu ve anlamlı bir look-through sonucu üretme.
        return LookThroughResult(
            root=root,
            exposures={},
            contributions={},
            unresolved={},
            cut_off={},
            coverage=0.0,
            report_dates=report_dates,
            reference_date=reference_date,
            max_date_gap_days=max_date_gap_days,
            cycles=cycles,
            total=0.0,
        )

    exposures: defaultdict[str, float] = defaultdict(float)
    paths: defaultdict[str, list[PathContribution]] = defaultdict(list)
    unresolved: defaultdict[str, float] = defaultdict(float)
    cut_off: defaultdict[str, float] = defaultdict(float)

    def solve(node: str, path_weight: float, path: list[str]) -> None:
        """Mutlak yol ağırlığını yaprağa taşı; küçük fon yollarını görünür biçimde kes."""
        data = graph.nodes[node]
        if data.get("kind") == "fund" and data.get("unresolved"):
            leaf = f"UNRESOLVED:{node}"  # Raporu olmayan fon hesapta görünür bir yapraktır.
            exposures[leaf] += path_weight
            paths[leaf].append((path, path_weight))
            unresolved[node] += path_weight
            return
        if node != root and data.get("kind") == "fund" and path_weight < cutoff:
            leaf = f"UNRESOLVED:{node}"  # Eşik altındaki fon kaybolmaz, ayrı kalite alanına gider.
            exposures[leaf] += path_weight
            paths[leaf].append((path, path_weight))
            cut_off[node] += path_weight
            return
        if graph.out_degree(node) == 0:
            exposures[node] += path_weight
            paths[node].append((path, path_weight))
            return

        for _, child, edge_data in sorted(
            graph.out_edges(node, data=True), key=lambda edge: edge[1]
        ):
            edge_weight = float(edge_data.get("weight", 0.0))
            solve(child, path_weight * edge_weight, [*path, child])

    solve(root, 1.0, [root])
    ordered_exposures = {leaf: exposures[leaf] for leaf in sorted(exposures)}
    contributions = {
        leaf: sorted(paths[leaf], key=lambda item: (-item[1], tuple(item[0])))[:top_k_paths]
        for leaf in sorted(paths)
    }
    total = sum(ordered_exposures.values())
    unresolved_total = sum(unresolved.values())
    cut_off_total = sum(cut_off.values())
    coverage = 1.0 - (unresolved_total + cut_off_total) / total if total else 0.0
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
        cycles=[],
        total=total,
    )
