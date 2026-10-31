"""Run the rule-based baseline and validation on every primary report in data/corpus.csv.

Run from backend/:  uv run python scripts/evaluate_baseline.py [FUND ...]
The PDFs must be under data/raw/ (links in data/corpus.csv). Reports outside the standard template
are listed as unsupported. Prints, per report: rows extracted, validation issues and warnings.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from extraction.baseline import ReportMeta, UnsupportedTemplate, parse_report
from extraction.pdf_text import extract_pages
from extraction.validation import validate_report
from schemas.holding import ReportKind

ROOT = Path(__file__).resolve().parents[2]


def main(only: list[str]) -> None:
    with open(ROOT / "data" / "corpus.csv", encoding="utf-8") as f:
        reports = [r for r in csv.DictReader(f) if r["primary"] == "yes"]
    totals: Counter[str] = Counter()
    for r in reports:
        code = r["fund_code"]
        if only and code not in only:
            continue
        if not r["period_start"]:
            print(f"{code:4} skipped: period unknown in corpus.csv")
            continue
        meta = ReportMeta(
            code,
            date.fromisoformat(r["period_start"]),
            date.fromisoformat(r["period_end"]),
            ReportKind(r["report_kind"]),
        )
        pages = extract_pages(ROOT / r["local_path"])
        try:
            result = parse_report(pages, meta)
        except UnsupportedTemplate as exc:
            totals["unsupported"] += 1
            print(f"{code:4} unsupported: {exc}")
            continue
        check = validate_report(result.holdings, result.summary, pages)
        totals["reports"] += 1
        totals["clean"] += check.ok
        totals["rows"] += len(result.holdings)
        issues = Counter(i.code for i in check.issues)
        print(f"{code:4} rows={len(result.holdings):4} issues={dict(issues) or '-'}")
        for w in result.warnings:
            print(f"     warning: {w}")
    print(
        f"\nstandard template: {totals['reports']} reports, {totals['clean']} pass validation, "
        f"{totals['rows']} rows; unsupported: {totals['unsupported']}"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
