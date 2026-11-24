"""Fonlar arasındaki yönlü sahiplik döngülerini bulur."""

import networkx as nx


def find_cycles(graph: nx.DiGraph) -> list[list[str]]:
    """Yalnız fon alt grafındaki döngüleri kapalı ve deterministik yollar olarak döndür."""
    fund_nodes = sorted(node for node, data in graph.nodes(data=True) if data.get("kind") == "fund")
    fund_graph = graph.subgraph(fund_nodes)
    normalized: list[list[str]] = []
    for cycle in nx.simple_cycles(fund_graph):  # NetworkX başlangıç düğümünü tekrar yazmaz.
        start = min(range(len(cycle)), key=cycle.__getitem__)  # En küçük anahtardan başlat.
        ordered = [*cycle[start:], *cycle[:start]]
        normalized.append([*ordered, ordered[0]])  # Okunabilirlik için başa dönerek kapat.
    return sorted(normalized)
