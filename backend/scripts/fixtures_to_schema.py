"""Exposure JSON fixture'larını ortak Holding/ReportSummary şemasına dönüştür."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from schemas.holding import Holding, ReportSummary  # noqa: E402

DEFAULT_FIXTURES = (
    "slide8.json",
    "unresolved.json",
    "deep.json",
    "cycle.json",
    "gtm_2026_09.json",
    "gal_2026_09.json",
    "gtm_gal_2026_09_expected.json",
)


def _period(value: str) -> tuple[str, str]:
    """Rapor bitiş tarihinden aylık fixture dönemini üret."""
    period_end = date.fromisoformat(value)
    return period_end.replace(day=1).isoformat(), period_end.isoformat()


def _run_id(fund_code: str, period_end: str) -> str:
    """Tekrarlanabilir ve okunur fixture çıkarım kimliği üret."""
    return f"fixture:{fund_code}:{period_end[:7]}"


def _instrument_code(quote: str) -> str | None:
    """Talep edilen geçici kuralla quote'un ilk kelimesini araç kodu yap."""
    words = quote.split()
    return words[0] if words else None


def _asset_type(row: dict[str, Any]) -> str:
    """Bilinen nakit/repo satırlarını ortak şema türlerine eşle."""
    name = str(row.get("name", "")).upper()
    current = str(row.get("asset_type", "other"))
    if current == "cash" and "VADELİ MEVDUAT" in name:
        return "deposit"
    if current == "other" and name == "TERS REPO":
        return "repo"
    # TBPP için kabul edilmiş bir tür bulunmadığından şimdilik other korunur.
    return current


def _fund_code(value: str) -> str:
    """Tek harfli sentetik kodları şemanın iki karakter alt sınırına taşı."""
    return f"F{value}" if len(value) == 1 else value


def _rewrite_node_ids(value: Any, code_map: dict[str, str], changes: set[str]) -> Any:
    """Expected alanlarındaki fon düğümü kimliklerini yeni kodlara taşı."""
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, nested in value.items():
            new_key = key
            for old, new in code_map.items():
                new_key = new_key.replace(f"FUND:{old}", f"FUND:{new}")
            if new_key != key:
                changes.add(f"{key} -> {new_key}")
            rewritten[new_key] = _rewrite_node_ids(nested, code_map, changes)
        return rewritten
    if isinstance(value, list):
        return [_rewrite_node_ids(item, code_map, changes) for item in value]
    if isinstance(value, str):
        rewritten = value
        for old, new in code_map.items():
            rewritten = rewritten.replace(f"FUND:{old}", f"FUND:{new}")
        if rewritten != value:
            changes.add(f"{value} -> {rewritten}")
        return rewritten
    return value


def _holding(row: dict[str, Any]) -> dict[str, Any]:
    """Eski holding sözlüğünü doğrulanabilir yeni şema sözlüğüne çevir."""
    converted = dict(row)
    report_date = str(converted.pop("report_date", converted.get("period_end")))
    period_start, period_end = _period(report_date)
    fund_code = str(converted["fund_code"])
    quote = str(converted["quote"])
    converted.update(
        {
            "period_start": converted.get("period_start", period_start),
            "period_end": period_end,
            "report_kind": converted.get("report_kind", "monthly"),
            "asset_type": _asset_type(converted),
            "instrument_code": converted.get("instrument_code") or _instrument_code(quote),
            "value": converted.pop("value_tl", converted.get("value", 0)),
            "extraction_run_id": converted.get("extraction_run_id")
            or _run_id(fund_code, period_end),
            "status": converted.get("status", "ok"),
        }
    )
    Holding.model_validate(converted)
    return converted


def _summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Eski rapor özetini yeni alan adlarına taşı ve doğrula."""
    converted = dict(summary)
    report_date = str(converted.pop("report_date", converted.get("period_end")))
    period_start, period_end = _period(report_date)
    fund_code = str(converted["fund_code"])
    portfolio_value = converted.pop("portfolio_value_tl", converted.get("portfolio_value", 1))
    liabilities = converted.pop("liabilities_tl", converted.get("liabilities", 0))
    converted.update(
        {
            "period_start": converted.get("period_start", period_start),
            "period_end": period_end,
            "report_kind": converted.get("report_kind", "monthly"),
            "page": converted.get("page", 1),
            "quote": converted.get("quote") or f"Fixture summary {fund_code} {period_end}",
            "extraction_run_id": converted.get("extraction_run_id")
            or _run_id(fund_code, period_end),
            "status": converted.get("status", "ok"),
            "portfolio_value": portfolio_value,
            "cash_equivalents": converted.pop(
                "ready_values_tl", converted.get("cash_equivalents", 0)
            ),
            "receivables": converted.pop("receivables_tl", converted.get("receivables", 0)),
            "other_assets": converted.pop("other_assets_tl", converted.get("other_assets", 0)),
            "liabilities": -abs(liabilities),
            "total_value": converted.pop("total_value_tl", converted.get("total_value", 1)),
        }
    )
    ReportSummary.model_validate(converted)
    return converted


def convert_fixture(path: Path) -> tuple[int, list[str]]:
    """Tek fixture'ı yerinde dönüştür ve değişen expected anahtarlarını döndür."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    holdings = payload.get("holdings")
    if holdings is None:
        return 0, []
    codes = {
        str(code)
        for code in [
            payload.get("root"),
            (payload.get("report_summary") or {}).get("fund_code"),
            *(row.get("fund_code") for row in holdings),
            *(row.get("held_fund_code") for row in holdings),
        ]
        if code
    }
    code_map = {code: _fund_code(code) for code in codes if _fund_code(code) != code}
    if payload.get("root") in code_map:
        payload["root"] = code_map[payload["root"]]
    if payload.get("report_summary", {}).get("fund_code") in code_map:
        payload["report_summary"]["fund_code"] = code_map[payload["report_summary"]["fund_code"]]
    for row in holdings:
        row["fund_code"] = code_map.get(row["fund_code"], row["fund_code"])
        if row.get("held_fund_code"):
            row["held_fund_code"] = code_map.get(row["held_fund_code"], row["held_fund_code"])
    payload["holdings"] = [_holding(row) for row in holdings]
    if payload.get("report_summary"):
        payload["report_summary"] = _summary(payload["report_summary"])

    # Bu dönüşüm node_key kimliklerini değiştirmiyor: cash/deposit aynı CASH:TRY,
    # repo/TBPP ise ISIN yoksa normalize edilmiş NAME anahtarını koruyor.
    changed_expected_keys: set[str] = set()
    for field in ("expected", "expected_cycles", "expected_paths"):
        if field in payload:
            payload[field] = _rewrite_node_ids(payload[field], code_map, changed_expected_keys)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(payload["holdings"]), sorted(changed_expected_keys)


def parse_args() -> argparse.Namespace:
    """İsteğe bağlı fixture dizinini komut satırından al."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "tests" / "fixtures",
    )
    return parser.parse_args()


def main() -> None:
    """Bütün Paket B fixture'larını dönüştür ve kısa rapor yazdır."""
    args = parse_args()
    total = 0
    changed_keys: list[str] = []
    for name in DEFAULT_FIXTURES:
        count, changed = convert_fixture(args.fixtures_dir / name)
        total += count
        changed_keys.extend(f"{name}: {key}" for key in changed)
        print(f"{name}: {count} holding doğrulandı")
    print(f"Toplam: {total} Holding; değişen expected anahtarı: {changed_keys or 'yok'}")


if __name__ == "__main__":
    main()
