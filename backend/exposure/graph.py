"""Holding kayıtlarından ağırlık bazı ve para birimi güvenli fon-varlık grafı kurar."""

import logging
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import networkx as nx

from schemas.holding import FUND_LIKE, AssetType, Holding, Status, WeightBasis


class HoldingAttributes(Protocol):
    """Pydantic'in ``from_attributes`` ile okuyabildiği ORM benzeri holding girdisi."""

    fund_code: str


type HoldingInput = Holding | Mapping[str, Any] | HoldingAttributes
type ReviewRow = tuple[str, str, int]

LOGGER = logging.getLogger(__name__)


def _validated(value: HoldingInput) -> Holding:
    """Sözlük girdilerini ortak Pydantic Holding şemasından geçir."""
    if isinstance(value, Holding):
        return value
    # DB'deki HoldingRow gibi ORM nesnelerini de aynı veri sözleşmesiyle doğrula.
    return Holding.model_validate(value, from_attributes=not isinstance(value, Mapping))


def node_key(value: HoldingInput) -> str:
    """Bir holding satırını kurallı ve benzersiz düğüm anahtarına çevir."""
    holding = _validated(value)  # Graf kimliği yalnız şemadan geçmiş kayıttan üretilir.
    if holding.asset_type in FUND_LIKE and holding.held_fund_code:  # Fon ve ETF kodla bağlanır.
        return f"FUND:{holding.held_fund_code}"
    if holding.asset_type in {AssetType.CASH, AssetType.DEPOSIT}:  # Nakdi para birimine göre topla.
        return f"CASH:{holding.currency}"
    if holding.isin:  # ISIN bulunan varlık değişmeyen uluslararası kimliği kullanır.
        return f"ISIN:{holding.isin}"
    name = " ".join(
        holding.name.upper().split()
    )  # Adsız kimlikte boşlukları ve harfi normalize et.
    return f"NAME:{name}"


def build_graph(holdings: Sequence[HoldingInput]) -> nx.DiGraph:
    """Holding satırlarını doğrula ve kaynak fonlardan hedeflere ağırlıklı graf kur."""
    # Bütün girdileri graf mutasyonundan önce doğrula.
    validated = [_validated(value) for value in holdings]
    review_rows = [
        (holding.fund_code, holding.period_end.isoformat(), holding.row_no)
        for holding in validated
        if holding.status is not Status.OK
    ]

    weight_bases = {holding.weight_basis for holding in validated}  # FPD ve FTD karışımını bul.
    if len(weight_bases) > 1:
        bases = ", ".join(sorted(basis.value for basis in weight_bases))
        raise ValueError(f"Tek grafta farklı weight_basis değerleri karıştırılamaz: {bases}")

    weight_basis = next(iter(weight_bases), None)
    basis_warning = None
    if weight_basis is WeightBasis.PORTFOLIO:
        basis_warning = (
            "Portfolio (FPD) ağırlıkları tanılama için çizilebilir; üretim look-through "
            "hesabında total (FTD) ağırlıkları kullanılmalıdır."
        )
        LOGGER.warning(basis_warning)
    elif weight_basis is WeightBasis.UNKNOWN:
        basis_warning = (
            "Tabanı bilinmeyen ağırlıklar tanılama için çizilebilir; look-through hesabında "
            "kullanılamaz."
        )
        LOGGER.warning(basis_warning)

    review_warning = None
    if review_rows:
        review_warning = (
            "needs_review satırları tanılama için grafa eklendi; doğrulanmadan look-through "
            "hesabında kullanılmamalıdır."
        )
        LOGGER.warning(review_warning)

    lookthrough_ready = weight_basis is WeightBasis.TOTAL and not review_rows

    graph = nx.DiGraph()  # Yönlü graf fonlardan tuttukları varlıklara doğru ilerler.
    graph.graph["weight_basis"] = weight_basis.value if weight_basis else None
    graph.graph["lookthrough_ready"] = lookthrough_ready
    graph.graph["weight_basis_warning"] = basis_warning
    graph.graph["review_rows"] = review_rows
    graph.graph["review_warning"] = review_warning
    for holding in validated:
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
