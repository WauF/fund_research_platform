"""Holding kayıtlarından fon-varlık grafı kurar.

Nakit ve mevduat şimdilik aynı ``CASH:TRY`` düğümünde birleşir. Bu kimlik kararı kalıcı veri
sözleşmesi kesinleştiğinde yeniden değerlendirilecektir.
"""

from collections.abc import Mapping
from typing import Any

import networkx as nx

from schemas.holding import FUND_LIKE, AssetType, Holding

type HoldingInput = Holding | Mapping[str, Any]


def _validated(value: HoldingInput) -> Holding:
    """Sözlük girdilerini ortak Pydantic Holding şemasından geçir."""
    return value if isinstance(value, Holding) else Holding.model_validate(value)


def node_key(value: HoldingInput) -> str:
    """Bir holding satırını kurallı ve benzersiz düğüm anahtarına çevir."""
    holding = _validated(value)  # Graf kimliği yalnız şemadan geçmiş kayıttan üretilir.
    if holding.asset_type in FUND_LIKE and holding.held_fund_code:  # Fon ve ETF kodla bağlanır.
        return f"FUND:{holding.held_fund_code}"
    if holding.asset_type in {AssetType.CASH, AssetType.DEPOSIT}:  # TRY nakdi tek düğümde topla.
        return "CASH:TRY"
    if holding.isin:  # ISIN bulunan varlık değişmeyen uluslararası kimliği kullanır.
        return f"ISIN:{holding.isin}"
    name = " ".join(
        holding.name.upper().split()
    )  # Adsız kimlikte boşlukları ve harfi normalize et.
    return f"NAME:{name}"


def build_graph(holdings: list[Holding]) -> nx.DiGraph:
    """Holding satırlarını doğrula ve kaynak fonlardan hedeflere ağırlıklı graf kur."""
    graph = nx.DiGraph()  # Yönlü graf fonlardan tuttukları varlıklara doğru ilerler.
    for value in holdings:
        holding = _validated(value)  # Çalışma zamanında gelen sözlük de şemadan geçirilir.
        source = f"FUND:{holding.fund_code}"  # Raporu yayımlayan fon kaynak düğümdür.
        target = node_key(holding)  # Hedef anahtarı ortak kimlik kuralıyla belirlenir.
        period_end = holding.period_end.isoformat()  # Fon tarihi rapor döneminin bitişidir.
        is_linked_fund = holding.asset_type in FUND_LIKE and holding.held_fund_code is not None
        target_kind = "fund" if is_linked_fund else "leaf"  # Bağlı ETF de alt fon gibi açılır.

        current_period = graph.nodes.get(source, {}).get("period_end")
        latest_period = max(filter(None, (current_period, period_end)), default=None)
        graph.add_node(source, kind="fund", period_end=latest_period)  # En yeni dönemi sakla.
        graph.add_node(
            target,
            kind=target_kind,
            label=holding.name,
        )  # Hedef bilgisini ekle.

        old_weight = graph.get_edge_data(source, target, {}).get("weight", 0.0)
        new_weight = old_weight + float(holding.weight)  # Decimal lot ağırlıklarını float topla.
        graph.add_edge(source, target, weight=new_weight)  # Güncel toplam ağırlığı kaydet.

    for node, data in graph.nodes(data=True):  # Raporu olmayan alt fonları son adımda işaretle.
        data["unresolved"] = data.get("kind") == "fund" and graph.out_degree(node) == 0
        if data.get("kind") == "fund":  # Raporu bulunmayan fonlarda tarih açıkça None kalır.
            data.setdefault("period_end", None)
    return graph
