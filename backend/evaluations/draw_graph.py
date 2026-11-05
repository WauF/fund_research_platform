"""Bir veya daha fazla holding fixture'ından exposure grafiği çiz ve PNG kaydet."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT_DIR / "evaluations" / "results"
sys.path.insert(0, str(ROOT_DIR))

from evaluations.pdf_fixture import load_pdf_fixture  # noqa: E402
from exposure.graph import build_graph, node_key  # noqa: E402
from schemas.holding import Holding  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Fixture yollarını ve isteğe bağlı hedef sınırını komut satırından al."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fixtures",
        nargs="+",
        type=Path,
        help="Bir veya daha fazla fixture JSON ya da data/corpus.csv içindeki PDF",
    )
    parser.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="Her fonun en büyük N yaprağını göster; kalanları 'Diğer' olarak topla",
    )
    args = parser.parse_args()
    if args.top is not None and args.top < 1:
        parser.error("--top pozitif bir tam sayı olmalı")
    return args


def load_fixture(path: Path) -> dict[str, Any]:
    """Bir fixture JSON'u veya corpus PDF'ini çizime hazır sözlüğe dönüştür."""
    resolved_path = path if path.is_absolute() else Path.cwd() / path
    resolved_path = resolved_path.resolve()
    if resolved_path.suffix.casefold() == ".pdf":
        return load_pdf_fixture(resolved_path)

    with resolved_path.open(encoding="utf-8") as fixture_file:
        data = json.load(fixture_file)

    missing = {"root", "holdings"} - data.keys()
    if missing:
        raise ValueError(f"Fixture alanları eksik: {', '.join(sorted(missing))}")
    if not isinstance(data["holdings"], list):
        raise TypeError("Fixture içindeki 'holdings' alanı bir liste olmalı")
    data["_path"] = resolved_path
    return data


def reachable_graph(graph: nx.DiGraph, root: str) -> nx.DiGraph:
    """Yalnızca seçilen kökten ulaşılabilen graf bölümünü döndür."""
    reachable = {root, *nx.descendants(graph, root)}
    return graph.subgraph(reachable).copy()


def top_view(graph: nx.DiGraph, root: str, top: int | None) -> nx.DiGraph:
    """Her açık fonun büyük yapraklarını koru, kalanlarını ayrı 'Diğer' düğümünde topla."""
    graph = reachable_graph(graph, root)
    if top is None:
        return graph

    fund_sources = [
        node
        for node, data in graph.nodes(data=True)
        if data.get("kind") == "fund" and graph.out_degree(node) > 0
    ]
    selected_targets: set[str] = set()
    for source in fund_sources:
        edges = sorted(
            graph.out_edges(source, data=True),
            key=lambda edge: float(edge[2].get("weight", 0.0)),
            reverse=True,
        )
        fund_targets = [edge[1] for edge in edges if graph.nodes[edge[1]].get("kind") == "fund"]
        leaf_targets = [edge[1] for edge in edges if graph.nodes[edge[1]].get("kind") != "fund"]
        selected_targets.update(fund_targets)
        selected_targets.update(leaf_targets[:top])

    view = nx.DiGraph()
    for source in fund_sources:
        view.add_node(source, **graph.nodes[source])
        hidden_edges: list[tuple[str, str, dict[str, Any]]] = []
        for edge_source, target, edge_data in graph.out_edges(source, data=True):
            if target in selected_targets:
                view.add_node(target, **graph.nodes[target])
                view.add_edge(edge_source, target, **edge_data)
            else:
                hidden_edges.append((edge_source, target, edge_data))

        if hidden_edges:
            code = source.removeprefix("FUND:")
            other_key = f"NAME:DİĞER:{code}"
            hidden_weight = sum(float(edge[2].get("weight", 0.0)) for edge in hidden_edges)
            view.add_node(
                other_key,
                kind="leaf",
                label=f"Diğer ({len(hidden_edges)} pozisyon)",
                unresolved=False,
            )
            view.add_edge(source, other_key, weight=hidden_weight)

    return reachable_graph(view, root)


def bfs_levels(graph: nx.DiGraph, root: str) -> dict[str, int]:
    """Kökten erişilebilen düğümlerin en kısa BFS seviyelerini döndür."""
    return dict(nx.single_source_shortest_path_length(graph, root))


def node_exposures(graph: nx.DiGraph, root: str, levels: dict[str, int]) -> dict[str, float]:
    """Kök ağırlığını tüm ileri yollar boyunca taşıyarak etkin maruziyetleri hesapla."""
    exposures: defaultdict[str, float] = defaultdict(float)
    exposures[root] = 1.0
    is_acyclic = nx.is_directed_acyclic_graph(graph)
    order = list(nx.topological_sort(graph)) if is_acyclic else sorted(levels, key=levels.get)
    for source in order:
        for _, target, edge_data in graph.out_edges(source, data=True):
            if is_acyclic or levels.get(target, 0) > levels.get(source, 0):
                exposures[target] += exposures[source] * float(edge_data.get("weight", 0.0))
    return dict(exposures)


def ring_layout(
    graph: nx.DiGraph,
    root: str,
    levels: dict[str, int],
    exposures: dict[str, float],
) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
    """Kök hedeflerini halkaya, açılan fon yapraklarını fonun arkasındaki yaya yerleştir."""
    positions: dict[str, tuple[float, float]] = {root: (0.0, 0.0)}
    angles: dict[str, float] = {root: 0.0}
    label_directions: dict[str, tuple[float, float]] = {}
    child_groups: dict[str, list[str]] = {}
    direct_targets = sorted(
        graph.successors(root),
        key=lambda node: float(graph[root][node].get("weight", 0.0)),
        reverse=True,
    )
    for index, node in enumerate(direct_targets):
        angle = (math.pi / 2) - (2 * math.pi * index / len(direct_targets))
        angles[node] = angle
        positions[node] = (math.cos(angle), math.sin(angle))
        label_directions[node] = positions[node]

    opened_funds = [
        node
        for node in direct_targets
        if graph.nodes[node].get("kind") == "fund" and graph.out_degree(node) > 0
    ]
    for fund in opened_funds:
        fund_angle = angles[fund]
        outward = (math.cos(fund_angle), math.sin(fund_angle))
        tangent = (-math.sin(fund_angle), math.cos(fund_angle))
        center = (
            positions[fund][0] + 1.05 * outward[0],
            positions[fund][1] + 1.05 * outward[1],
        )
        children = [
            node
            for node in graph.successors(fund)
            if node not in positions and graph.in_degree(node) == 1
        ]
        children.sort(key=lambda node: exposures.get(node, 0.0), reverse=True)
        child_groups[fund] = children
        for index, node in enumerate(children):
            fraction = 0.5 if len(children) == 1 else index / (len(children) - 1)
            arc_angle = (-math.pi / 2) + (math.pi * fraction)
            arc_radius = 0.78
            positions[node] = (
                center[0]
                + arc_radius
                * (math.cos(arc_angle) * outward[0] + math.sin(arc_angle) * tangent[0]),
                center[1]
                + arc_radius
                * (math.cos(arc_angle) * outward[1] + math.sin(arc_angle) * tangent[1]),
            )
            angles[node] = math.atan2(positions[node][1], positions[node][0])
            label_directions[node] = (
                math.cos(arc_angle) * outward[0] + math.sin(arc_angle) * tangent[0],
                math.cos(arc_angle) * outward[1] + math.sin(arc_angle) * tangent[1],
            )

    shared_direct = [
        node
        for node in direct_targets
        if graph.nodes[node].get("kind") != "fund" and graph.in_degree(node) > 1
    ]
    grouped_shared: defaultdict[str, list[str]] = defaultdict(list)
    for node in shared_direct:
        opened_parents = [parent for parent in graph.predecessors(node) if parent != root]
        if opened_parents:
            grouped_shared[opened_parents[0]].append(node)
    for fund, nodes in grouped_shared.items():
        fund_x, fund_y = positions[fund]
        tangent = (-fund_y, fund_x)
        center = (len(nodes) - 1) / 2
        for index, node in enumerate(nodes):
            offset = (index - center) * 0.30
            positions[node] = (
                0.52 * fund_x + offset * tangent[0],
                0.52 * fund_y + offset * tangent[1],
            )
            angles[node] = math.atan2(positions[node][1], positions[node][0])
            distance = math.hypot(*positions[node])
            label_directions[node] = (
                positions[node][0] / distance,
                positions[node][1] / distance,
            )

    unplaced = [node for node in graph if node not in positions]
    for index, node in enumerate(unplaced):
        level = levels.get(node, 2)
        angle = (math.pi / 2) - (2 * math.pi * index / max(len(unplaced), 1))
        radius = 1.0 + 0.85 * level
        positions[node] = (radius * math.cos(angle), radius * math.sin(angle))
        angles[node] = angle
        label_directions[node] = (math.cos(angle), math.sin(angle))

    label_positions: dict[str, tuple[float, float]] = {root: positions[root]}
    for node in (item for item in graph if item != root):
        direction = label_directions[node]
        label_positions[node] = (
            positions[node][0] + 0.16 * direction[0],
            positions[node][1] + 0.16 * direction[1],
        )

    # Yayın tepesindeki yatay etiketleri, üst sınırı koruyarak az miktarda ayır.
    for children in child_groups.values():
        ordered = sorted(children, key=lambda node: label_positions[node][1])
        if len(ordered) < 2:
            continue
        original_y = [label_positions[node][1] for node in ordered]
        adjusted_y: list[float] = []
        for y_position in original_y:
            minimum_y = adjusted_y[-1] + 0.11 if adjusted_y else -math.inf
            adjusted_y.append(max(y_position, minimum_y))
        center_shift = adjusted_y[-1] - original_y[-1]
        for node, y_position in zip(ordered, adjusted_y, strict=True):
            x_position, _ = label_positions[node]
            label_positions[node] = (x_position, y_position - center_shift)

    # Ortak düğüm etiketlerini komşu doğrudan hedeflerden küçük bir açıyla uzaklaştır.
    for nodes in grouped_shared.values():
        ordered = sorted(nodes, key=lambda node: positions[node][1], reverse=True)
        for index, node in enumerate(ordered):
            x_position, y_position = label_positions[node]
            label_positions[node] = (x_position, y_position - 0.13 * index)
    return positions, label_positions


def percent(value: float, decimals: int | None = None) -> str:
    """Ondalık oranı büyüklüğüne göre bir veya iki haneli Türkçe yüzdeye çevir."""
    percentage = value * 100
    digits = decimals if decimals is not None else (2 if percentage < 1 else 1)
    return f"%{percentage:.{digits}f}".replace(".", ",")


def node_metadata(holdings: list[dict[str, Any]]) -> dict[str, dict[str, set[str]]]:
    """Holding satırlarından her düğümün bütün adlarını ve varlık türlerini topla."""
    metadata: defaultdict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"names": set(), "asset_types": set()}
    )
    for holding in holdings:
        key = node_key(holding)
        metadata[key]["names"].add(str(holding["name"]).strip())
        metadata[key]["asset_types"].add(str(holding["asset_type"]))
    return dict(metadata)


def display_name(
    graph: nx.DiGraph,
    node: str,
    root: str,
    metadata: dict[str, dict[str, set[str]]],
) -> str:
    """Düğüm türü ve bütün kaynak adlarını kullanarak yanıltıcı olmayan kısa adı seç."""
    if node == root or node.startswith("FUND:"):
        return node.removeprefix("FUND:")
    if node == "CASH:TRY":
        return "Mevduat (tüm bankalar)"
    if node.startswith("NAME:DİĞER:"):
        return str(graph.nodes[node]["label"])

    details = metadata.get(node, {"names": set(), "asset_types": set()})
    if node.startswith("ISIN:") and "bond" in details["asset_types"]:
        return node.removeprefix("ISIN:")
    names = details["names"]
    if names:
        name = min(names, key=lambda item: (len(item), item.casefold()))
    else:
        name = str(graph.nodes[node].get("label") or node.split(":", 1)[-1])
    return name if len(name) <= 18 else f"{name[:17]}…"


def short_label(
    graph: nx.DiGraph,
    node: str,
    weight: float,
    root: str,
    metadata: dict[str, dict[str, set[str]]],
) -> str:
    """Adı etkin yüzdeyle, açılan fon yaprağını ayrıca fon içi payla etiketle."""
    label = f"{display_name(graph, node, root, metadata)} {percent(weight)}"
    opened_parents = [
        parent
        for parent in graph.predecessors(node)
        if parent != root
        and graph.nodes[parent].get("kind") == "fund"
        and graph.out_degree(parent) > 0
    ]
    if opened_parents:
        parent = max(
            opened_parents,
            key=lambda item: float(graph[item][node].get("weight", 0.0)),
        )
        inside_weight = float(graph[parent][node].get("weight", 0.0))
        label += f" ({parent.removeprefix('FUND:')} içinde {percent(inside_weight)})"
    return label


def node_color(graph: nx.DiGraph, node: str, root: str) -> str:
    """Bir düğümün türüne göre dolgu rengini seç."""
    data = graph.nodes[node]
    if node == root:
        return "#102A43"
    if data.get("unresolved"):
        return "#D64545"
    if data.get("kind") == "fund" or node.startswith("FUND:"):
        return "#8CC8E8"
    if node.startswith("ISIN:"):
        return "#5BAE75"
    return "#A7ADB4"


def unresolved_summary(graph: nx.DiGraph, root: str, exposures: dict[str, float]) -> str:
    """Unresolved fonları ve kökten etkin yüzdelerini başlık için biçimlendir."""
    unresolved = sorted(
        [
            node
            for node, data in graph.nodes(data=True)
            if node != root and data.get("unresolved") and node.startswith("FUND:")
        ],
        key=lambda node: exposures.get(node, 0.0),
        reverse=True,
    )
    if not unresolved:
        return "Yok"
    visible = unresolved[:5]
    details = ", ".join(
        f"{node.removeprefix('FUND:')} {percent(exposures.get(node, 0.0), 2)}" for node in visible
    )
    if len(unresolved) > len(visible):
        total = sum(exposures.get(node, 0.0) for node in unresolved)
        details += f" +{len(unresolved) - len(visible)} fon (toplam {percent(total, 2)})"
    return details


def report_details(fixtures: list[dict[str, Any]]) -> tuple[str, bool]:
    """Başlık için fon kodu/tarih metni ile tarih uyuşmazlığı bilgisini üret."""
    reports: list[str] = []
    dates: set[str] = set()
    for fixture in fixtures:
        summary = fixture.get("report_summary") or {}
        code = str(summary.get("fund_code") or fixture["root"])
        date = str(summary.get("period_end") or "tarih yok")
        reports.append(f"{code} {date}")
        dates.add(date)
    return " + ".join(reports), len(dates) > 1


def maximize_window() -> None:
    """Matplotlib penceresini desteklenen arayüzlerde en büyük boyuta getir."""
    manager = plt.get_current_fig_manager()
    window = getattr(manager, "window", None)
    if window is None:
        return
    try:
        if hasattr(window, "showMaximized"):
            window.showMaximized()
        elif hasattr(window, "state"):
            window.state("zoomed")
        elif hasattr(window, "wm_state"):
            window.wm_state("zoomed")
    except (AttributeError, TypeError):
        pass


def draw_node_groups(
    graph: nx.DiGraph,
    positions: dict[str, tuple[float, float]],
    sizes: dict[str, float],
    root: str,
    axis: Any,
) -> None:
    """Normal, ortak ve unresolved düğümleri farklı çerçevelerle çiz."""
    unresolved = [node for node in graph if graph.nodes[node].get("unresolved")]
    shared = [
        node
        for node in graph
        if graph.in_degree(node) > 1 and node not in unresolved and node != root
    ]
    regular = [node for node in graph if node not in unresolved and node not in shared]

    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=regular,
        node_size=[sizes[node] for node in regular],
        node_color=[node_color(graph, node, root) for node in regular],
        edgecolors="#243B53",
        linewidths=1.2,
        ax=axis,
    )
    if shared:
        nx.draw_networkx_nodes(
            graph,
            positions,
            nodelist=shared,
            node_size=[sizes[node] for node in shared],
            node_color=[node_color(graph, node, root) for node in shared],
            edgecolors="#F28C28",
            linewidths=3.2,
            ax=axis,
        )
    if unresolved:
        unresolved_nodes = nx.draw_networkx_nodes(
            graph,
            positions,
            nodelist=unresolved,
            node_size=[sizes[node] for node in unresolved],
            node_color=[node_color(graph, node, root) for node in unresolved],
            edgecolors="#8B1E1E",
            linewidths=2.8,
            ax=axis,
        )
        unresolved_nodes.set_linestyle("--")


def draw_fixtures(
    fixtures: list[dict[str, Any]],
    top: int | None = None,
    output_dir: Path = RESULTS_DIR,
    *,
    show: bool = True,
) -> Path:
    """Fixture'ları tek grafta birleştir, çiz, PNG kaydet ve ekranda göster."""
    root = f"FUND:{str(fixtures[0]['root']).upper()}"
    holdings = [holding for fixture in fixtures for holding in fixture["holdings"]]
    validated = [Holding.model_validate(holding) for holding in holdings]
    metadata = node_metadata(holdings)
    full_graph = build_graph(validated)
    if root not in full_graph:
        raise ValueError(f"Kök düğüm grafta bulunamadı: {root}")

    graph = top_view(full_graph, root, top)
    levels = bfs_levels(graph, root)
    exposures = node_exposures(graph, root, levels)
    positions, label_positions = ring_layout(graph, root, levels, exposures)

    non_root = [weight for node, weight in exposures.items() if node != root]
    largest_exposure = max(non_root, default=1.0)
    sizes = {
        node: 2800 if node == root else max(300, 4200 * exposures.get(node, 0.0) / largest_exposure)
        for node in graph
    }
    root_edges = list(graph.out_edges(root))
    root_weights = [
        float(graph[source][target].get("weight", 0.0)) for source, target in root_edges
    ]
    largest_root_edge = max(root_weights, default=1.0)
    root_widths = [0.8 + 7.0 * weight / largest_root_edge for weight in root_weights]
    fund_edges = [(source, target) for source, target in graph.edges if source != root]
    fund_widths = [
        0.35
        + 2.0
        * (
            exposures.get(source, 0.0)
            * float(graph[source][target].get("weight", 0.0))
            / largest_root_edge
        )
        for source, target in fund_edges
    ]

    figure, axis = plt.subplots(figsize=(18, 11))
    figure.patch.set_facecolor("#F7F9FC")
    axis.set_facecolor("#F7F9FC")
    nx.draw_networkx_edges(
        graph,
        positions,
        edgelist=root_edges,
        ax=axis,
        width=root_widths,
        edge_color="#627D98",
        alpha=0.68,
        arrows=True,
        arrowsize=18,
        connectionstyle="arc3,rad=0.03",
    )
    if fund_edges:
        nx.draw_networkx_edges(
            graph,
            positions,
            edgelist=fund_edges,
            ax=axis,
            width=fund_widths,
            edge_color="#829AB1",
            alpha=0.38,
            arrows=True,
            arrowsize=12,
            connectionstyle="arc3,rad=0.03",
        )
    draw_node_groups(graph, positions, sizes, root, axis)

    labels = {
        node: short_label(graph, node, exposures.get(node, 0.0), root, metadata) for node in graph
    }
    for node, label in labels.items():
        x_position, y_position = label_positions[node]
        alignment = "center" if node == root else ("left" if x_position >= 0 else "right")
        axis.text(
            x_position,
            y_position,
            label,
            fontsize=8.3,
            fontweight="bold",
            color="#102A43",
            horizontalalignment=alignment,
            verticalalignment="center",
            bbox={
                "boxstyle": "round,pad=0.20",
                "facecolor": "white",
                "alpha": 0.84,
                "lw": 0,
            },
        )

    root_weight = sum(
        float(edge_data.get("weight", 0.0)) for _, _, edge_data in graph.out_edges(root, data=True)
    )
    reports, date_mismatch = report_details(fixtures)
    title_line_1 = f"{fixtures[0]['root']} · Raporlar: {reports} · {len(holdings)} satır"
    title_line_2 = (
        f"Graf: {full_graph.number_of_nodes()} düğüm / {full_graph.number_of_edges()} kenar · "
        f"Çizilen: {graph.number_of_nodes()} düğüm · Kök toplamı: {percent(root_weight, 2)} · "
        f"Unresolved: {unresolved_summary(graph, root, exposures)}"
    )
    figure.suptitle(
        f"{title_line_1}\n{title_line_2}",
        fontsize=14,
        fontweight="bold",
        color="#102A43",
        y=0.99,
        linespacing=1.35,
    )
    if date_mismatch:
        figure.text(
            0.5,
            0.92,
            "UYARI: Rapor tarihleri farklı; look-through karşılaştırması dönem uyumsuz olabilir.",
            ha="center",
            color="#C62828",
            fontsize=11,
            fontweight="bold",
        )

    legend_items = [
        Patch(facecolor="#102A43", edgecolor="#243B53", label="Kök fon"),
        Patch(facecolor="#8CC8E8", edgecolor="#243B53", label="Alt fon"),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor="#D64545",
            markeredgecolor="#8B1E1E",
            markeredgewidth=2,
            linestyle="--",
            label="Unresolved fon",
        ),
        Patch(facecolor="#5BAE75", edgecolor="#243B53", label="ISIN"),
        Patch(facecolor="#A7ADB4", edgecolor="#243B53", label="NAME / CASH"),
        Patch(
            facecolor="white",
            edgecolor="#F28C28",
            linewidth=3,
            label="İki yoldan ulaşılan",
        ),
    ]
    figure.legend(
        handles=legend_items,
        loc="lower right",
        bbox_to_anchor=(0.985, 0.04),
        frameon=True,
        framealpha=0.95,
    )
    axis.margins(0.20)
    axis.set_axis_off()
    figure.tight_layout(rect=(0, 0, 1, 0.90))

    names = "_".join(Path(fixture["_path"]).stem for fixture in fixtures)
    suffix = f"_top{top}" if top is not None else ""
    output_path = output_dir / f"{names}{suffix}_graph.png"
    output_dir.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=figure.get_facecolor())
    print(f"PNG kaydedildi: {output_path}")

    if show:
        maximize_window()
        plt.show()
    else:
        plt.close(figure)
    return output_path


def main() -> None:
    """Fixture'ları yükle ve komut satırı seçenekleriyle grafiği çiz."""
    args = parse_args()
    fixtures = [load_fixture(path) for path in args.fixtures]
    draw_fixtures(fixtures, args.top)


if __name__ == "__main__":
    main()
