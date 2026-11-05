"""Look-through sonucunu bağımsız yöntemler ve yoğunlaşma ölçüleriyle doğrular."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

import networkx as nx
import numpy as np

from exposure.cycles import find_cycles
from exposure.lookthrough import look_through


@dataclass(frozen=True)
class MethodComparison:
    """Recursive ve matris çözümlerinin sayısal karşılaştırmasıdır."""

    recursive: dict[str, float]
    matrix: dict[str, float]
    differences: dict[str, float]
    max_abs_difference: float
    tolerance: float
    matches: bool


@dataclass(frozen=True)
class OverlapResult:
    """İki portföyün ortak pozisyonlarını ve toplam örtüşme oranını taşır."""

    score: float
    shared: dict[str, float]
    first_total: float
    second_total: float


def _clean_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Ağırlıkları doğrula ve sıfır değerleri hesap dışında bırak."""
    cleaned: dict[str, float] = {}
    for key, raw_weight in weights.items():
        weight = float(raw_weight)
        if not isfinite(weight):
            raise ValueError(f"Ağırlık sonlu bir sayı olmalı: {key}")
        if weight:
            cleaned[key] = weight
    return cleaned


def direct_exposures(graph: nx.DiGraph, root: str) -> dict[str, float]:
    """Bir fonun raporunda görünen, henüz açılmamış doğrudan dağılımını döndür."""
    if root not in graph:
        raise ValueError(f"Kök düğüm grafta bulunamadı: {root}")
    return {
        target: float(data.get("weight", 0.0))
        for _, target, data in sorted(graph.out_edges(root, data=True), key=lambda edge: edge[1])
    }


def matrix_look_through(graph: nx.DiGraph, root: str) -> dict[str, float]:
    """Etkin yaprak ağırlıklarını ``(I-F)`` doğrusal sistemini çözerek hesapla.

    Ters matrisi açıkça üretmek yerine ``solve`` kullanılır; bu hem daha hızlı hem de sayısal olarak
    daha kararlıdır. Raporu bulunmayan fonlar recursive yöntemdeki gibi unresolved yaprak kalır.
    """
    if root not in graph:
        raise ValueError(f"Kök düğüm grafta bulunamadı: {root}")
    cycles = find_cycles(graph)
    if cycles:
        raise ValueError("Döngülü grafta matris look-through hesaplanamaz")

    reachable = {root, *nx.descendants(graph, root)}
    resolved_funds = sorted(
        node
        for node in reachable
        if graph.nodes[node].get("kind") == "fund" and graph.out_degree(node) > 0
    )
    if root not in resolved_funds:
        return {f"UNRESOLVED:{root}": 1.0}

    fund_index = {node: index for index, node in enumerate(resolved_funds)}
    leaf_keys = sorted(
        {
            f"UNRESOLVED:{target}" if graph.nodes[target].get("kind") == "fund" else target
            for source in resolved_funds
            for target in graph.successors(source)
            if target not in fund_index
        }
    )
    leaf_index = {node: index for index, node in enumerate(leaf_keys)}
    fund_matrix = np.zeros((len(resolved_funds), len(resolved_funds)), dtype=np.float64)
    leaf_matrix = np.zeros((len(resolved_funds), len(leaf_keys)), dtype=np.float64)

    for source in resolved_funds:
        source_index = fund_index[source]
        for target, edge_data in graph[source].items():
            weight = float(edge_data.get("weight", 0.0))
            if target in fund_index:
                fund_matrix[source_index, fund_index[target]] += weight
            else:
                leaf = (
                    f"UNRESOLVED:{target}" if graph.nodes[target].get("kind") == "fund" else target
                )
                leaf_matrix[source_index, leaf_index[leaf]] += weight

    root_vector = np.zeros(len(resolved_funds), dtype=np.float64)
    root_vector[fund_index[root]] = 1.0
    fund_visits = np.linalg.solve(np.eye(len(resolved_funds)) - fund_matrix.T, root_vector)
    exposures = fund_visits @ leaf_matrix
    return {
        leaf: float(weight)
        for leaf, weight in zip(leaf_keys, exposures, strict=True)
        if abs(float(weight)) > 1e-15
    }


def compare_methods(
    graph: nx.DiGraph,
    root: str,
    tolerance: float = 1e-9,
) -> MethodComparison:
    """Recursive ve matris sonuçlarını aynı yapraklarda, verilen toleransla karşılaştır."""
    if tolerance < 0:
        raise ValueError("Tolerans negatif olamaz")
    recursive = look_through(graph, root, cutoff=0).exposures
    matrix = matrix_look_through(graph, root)
    keys = sorted(recursive.keys() | matrix.keys())
    differences = {key: matrix.get(key, 0.0) - recursive.get(key, 0.0) for key in keys}
    max_difference = max((abs(value) for value in differences.values()), default=0.0)
    return MethodComparison(
        recursive=recursive,
        matrix=matrix,
        differences=differences,
        max_abs_difference=max_difference,
        tolerance=tolerance,
        matches=max_difference <= tolerance,
    )


def herfindahl_hirschman(
    weights: Mapping[str, float],
    *,
    normalize: bool = True,
) -> float:
    """Brüt mutlak paylarla HHI hesapla; 1'e yaklaştıkça portföy daha yoğunlaşmıştır."""
    cleaned = _clean_weights(weights)
    total = sum(abs(weight) for weight in cleaned.values())
    if not total:
        return 0.0
    scale = total if normalize else 1.0
    return sum((abs(weight) / scale) ** 2 for weight in cleaned.values())


def fund_overlap(
    first: Mapping[str, float],
    second: Mapping[str, float],
    *,
    normalize: bool = True,
) -> OverlapResult:
    """İki fonun ortak maruziyetini ``sum(min(w1, w2))`` yöntemiyle hesapla."""
    first_clean = _clean_weights(first)
    second_clean = _clean_weights(second)
    first_total = sum(abs(weight) for weight in first_clean.values())
    second_total = sum(abs(weight) for weight in second_clean.values())
    if not first_total or not second_total:
        return OverlapResult(0.0, {}, first_total, second_total)

    first_scale = first_total if normalize else 1.0
    second_scale = second_total if normalize else 1.0
    shared = {}
    for key in sorted(first_clean.keys() & second_clean.keys()):
        first_weight = first_clean[key]
        second_weight = second_clean[key]
        if first_weight * second_weight > 0:  # Zıt yönlü long/short pozisyonlar ortak sayılmaz.
            shared[key] = min(abs(first_weight) / first_scale, abs(second_weight) / second_scale)
    shared = {key: weight for key, weight in shared.items() if weight}
    return OverlapResult(sum(shared.values()), shared, first_total, second_total)
