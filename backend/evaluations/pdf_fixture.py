"""PDF extraction sonuçlarını exposure görselleri için FTD ağırlıklarına dönüştür."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from extraction import baseline
from extraction.pdf_text import extract_pages
from extraction.weights import to_total_basis
from schemas.holding import Holding, ReportKind, ReportSummary

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
CORPUS_PATH = PROJECT_ROOT / "data" / "corpus.csv"


def normalize_holdings_to_total(
    holdings: list[Holding],
    summary: ReportSummary | None,
) -> list[Holding]:
    """Eski değerlendirme çağrılarını ortak FTD dönüşümüne yönlendir."""
    return to_total_basis(holdings, summary)


def load_pdf_fixture(path: Path, corpus_path: Path = CORPUS_PATH) -> dict[str, Any]:
    """Corpus dönem bilgisiyle PDF'i ayrıştırıp total ağırlıklı fixture döndür."""
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

    meta = baseline.ReportMeta(
        fund_code=corpus_row["fund_code"],
        period_start=date.fromisoformat(corpus_row["period_start"]),
        period_end=date.fromisoformat(corpus_row["period_end"]),
        report_kind=ReportKind(corpus_row["report_kind"]),
    )
    result = baseline.parse_report(extract_pages(path), meta)
    for warning in result.warnings:
        print(f"{meta.fund_code} uyarı: {warning}")
    holdings = baseline.to_total_basis(result)
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
