"""Load the primary reports of data/corpus.csv into the database with the rule-based baseline.

Run from backend/ with the stack up (DATABASE_URL and S3_* as in .env):
    uv run python -m scripts.ingest_corpus [--dry-run] [--force] [FUND ...]

For each report: the PDF is uploaded and registered like POST /documents (same sha256 -> same
document), then extracted and saved as a new extraction run. Reports outside the standard template
are skipped. A document that already has a baseline run is skipped unless --force.
--dry-run extracts and validates without touching the database or object storage.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from extraction.baseline import ReportMeta, UnsupportedTemplate, parse_report
from extraction.ingest import BASELINE_MODEL, ingest_baseline
from extraction.pdf_text import extract_pages
from extraction.validation import validate_report
from schemas.holding import ReportKind
from storage.documents import add_document
from storage.extractions import list_runs
from storage.objects import ObjectStore

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Outcome:
    fund_code: str
    result: str  # saved | skipped | unsupported | missing
    detail: str = ""


def read_corpus(path: Path, only: Iterable[str] = ()) -> list[dict[str, str]]:
    only = set(only)
    with open(path, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["primary"] == "yes"]
    return [r for r in rows if not only or r["fund_code"] in only]


def _meta(row: dict[str, str]) -> ReportMeta | None:
    if not row["period_start"]:
        return None  # detected from the report header, or UnsupportedTemplate
    return ReportMeta(
        row["fund_code"],
        date.fromisoformat(row["period_start"]),
        date.fromisoformat(row["period_end"]),
        ReportKind(row["report_kind"]),
    )


def ingest_corpus(
    session: Session | None,
    store: ObjectStore | None,
    rows: Iterable[dict[str, str]],
    root: Path = ROOT,
    *,
    force: bool = False,
) -> list[Outcome]:
    """Ingest corpus rows. session=None is a dry run: extract and validate only."""
    outcomes = []
    for row in rows:
        code = row["fund_code"]
        pdf = root / row["local_path"]
        if not pdf.is_file():
            outcomes.append(Outcome(code, "missing", str(pdf)))
            continue
        body = pdf.read_bytes()
        pages = extract_pages(pdf)
        meta = _meta(row)
        try:
            if session is None:
                result = parse_report(pages, meta)
                check = validate_report(result.holdings, result.summary, pages)
                status = "ok" if check.ok and not result.warnings else "needs_review"
                outcomes.append(Outcome(code, "checked", f"{len(result.holdings)} rows, {status}"))
                continue
            parse_report(pages, meta)  # reject other templates before uploading anything
        except UnsupportedTemplate as exc:
            outcomes.append(Outcome(code, "unsupported", str(exc)))
            continue

        sha256 = hashlib.sha256(body).hexdigest()
        document, created = add_document(
            session,
            sha256=sha256,
            original_filename=pdf.name,
            size_bytes=len(body),
            storage_key=f"pdfs/{sha256}.pdf",
        )
        if created:
            with open(pdf, "rb") as f:
                store.put(document.storage_key, f, "application/pdf")
        elif not force and any(r.model == BASELINE_MODEL for r in list_runs(session, document.id)):
            outcomes.append(Outcome(code, "skipped", f"document {document.id} already extracted"))
            continue
        run = ingest_baseline(session, document_id=document.id, pages=pages, meta=meta)
        detail = f"document {document.id}, {len(run.holdings)} rows, {run.status.value}"
        outcomes.append(Outcome(code, "saved", detail))
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("funds", nargs="*", help="only these fund codes")
    parser.add_argument("--dry-run", action="store_true", help="no database or object storage")
    parser.add_argument("--force", action="store_true", help="re-extract documents with a run")
    args = parser.parse_args()
    rows = read_corpus(ROOT / "data" / "corpus.csv", args.funds)

    if args.dry_run:
        outcomes = ingest_corpus(None, None, rows)
    else:
        from sqlalchemy.orm import sessionmaker

        from storage.db import get_engine
        from storage.objects import get_object_store

        with sessionmaker(get_engine())() as session:
            outcomes = ingest_corpus(session, get_object_store(), rows, force=args.force)

    for o in outcomes:
        print(f"{o.fund_code:4} {o.result:11} {o.detail}")
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o.result] = counts.get(o.result, 0) + 1
    print("\n" + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
