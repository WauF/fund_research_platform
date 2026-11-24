"""PDF extraction sonuçlarını exposure görselleri için FTD ağırlıklarına dönüştür."""

from __future__ import annotations

import csv
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from schemas.holding import Holding, ReportKind, ReportSummary, WeightBasis

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
CORPUS_PATH = PROJECT_ROOT / "data" / "corpus.csv"
_TR_NUMBER = re.compile(r"^-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d+$")


def _tr_decimal(value: str) -> Decimal:
    """Türkçe biçimli sayıyı Decimal değerine dönüştür."""
    return Decimal(value.replace(".", "").replace(",", "."))


def _printed_total_weight(holding: Holding) -> Decimal | None:
    """Satırda ayrı FTD sütunu varsa basılı yüzdeyi kesir olarak döndür."""
    trailing: list[Decimal] = []
    for token in reversed(holding.quote.split()):
        if not _TR_NUMBER.fullmatch(token):
            break
        trailing.append(_tr_decimal(token))
    trailing.reverse()
    if len(trailing) < 4:
        return None

    value, portfolio_percent, total_percent = trailing[-4], trailing[-2], trailing[-1]
    value_tolerance = max(Decimal("0.01"), abs(holding.value) * Decimal("1e-9"))
    if abs(value - holding.value) > value_tolerance:
        return None
    if abs(portfolio_percent / 100 - holding.weight) > Decimal("0.00011"):
        return None
    return total_percent / 100


def normalize_holdings_to_total(
    holdings: list[Holding],
    summary: ReportSummary | None,
) -> list[Holding]:
    """FPD ağırlıklarını basılı FTD veya raporun FPD/FTD oranıyla total tabana çevir."""
    if summary is None:
        return holdings
    portfolio_share = summary.portfolio_share()
    normalized: list[Holding] = []
    for holding in holdings:
        if holding.weight_basis is not WeightBasis.PORTFOLIO:
            normalized.append(holding)
            continue
        total_weight = _printed_total_weight(holding)
        if total_weight is None:
            total_weight = holding.weight * portfolio_share
        normalized.append(
            holding.model_copy(update={"weight": total_weight, "weight_basis": WeightBasis.TOTAL})
        )
    return normalized


def load_pdf_fixture(path: Path, corpus_path: Path = CORPUS_PATH) -> dict[str, Any]:
    """Corpus dönem bilgisiyle PDF'i ayrıştırıp total ağırlıklı fixture döndür."""
    try:
        from extraction.baseline import ReportMeta, parse_report
        from extraction.pdf_text import extract_pages
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PDF çizimi Akif'in extraction-baseline dalı merge edildikten sonra kullanılabilir"
        ) from exc

    path = path.resolve()
    with corpus_path.open(encoding="utf-8", newline="") as corpus_file:
        rows = list(csv.DictReader(corpus_file))
    corpus_row = next(
        (row for row in rows if (PROJECT_ROOT / row.get("local_path", "")).resolve() == path),
        None,
    )
    if corpus_row is None:
        raise ValueError(f"PDF data/corpus.csv içinde bulunamadı: {path}")
    if not corpus_row.get("period_start") or not corpus_row.get("period_end"):
        raise ValueError(f"PDF dönem bilgisi eksik: {path}")

    meta = ReportMeta(
        fund_code=corpus_row["fund_code"],
        period_start=date.fromisoformat(corpus_row["period_start"]),
        period_end=date.fromisoformat(corpus_row["period_end"]),
        report_kind=ReportKind(corpus_row["report_kind"]),
    )
    result = parse_report(extract_pages(path), meta)
    for warning in result.warnings:
        print(f"{meta.fund_code} uyarı: {warning}")
    holdings = normalize_holdings_to_total(result.holdings, result.summary)
    summary = (
        result.summary.model_dump(mode="json")
        if result.summary
        else {"fund_code": meta.fund_code, "period_end": meta.period_end.isoformat()}
    )
    return {
        "root": meta.fund_code,
        "holdings": [holding.model_dump(mode="json") for holding in holdings],
        "report_summary": summary,
        "_path": path,
    }
