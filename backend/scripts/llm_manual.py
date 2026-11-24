"""Run LLM extraction with a model not behind an API: write the request, record the reply.

Until the LLM provider is decided (advisor's GPU or an API), the model is used by hand: it gets the
exact request the pipeline would send, and its reply is recorded with its provenance. The recorded
file is then replayed through the same code as a live run (extract_with_llm, validate_extraction),
and by tests/extraction/test_recorded_llm.py in every CI run.

Run from backend/:
    uv run python -m scripts.llm_manual request IRF
        -> evaluations/results/manual/IRF/{system.txt, user.txt, schema.json}
    uv run python -m scripts.llm_manual record IRF reply.json --model claude-opus-5-5 --note "..."
        -> tests/recorded/IRF_2026-09__claude-opus-5-5.json, then prints the validation result
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from extraction.baseline import ReportMeta
from extraction.llm import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    LLMExtraction,
    LLMReport,
    extract_with_llm,
    render_pages,
    validate_extraction,
)
from extraction.llm_client import RecordedClient, request_hashes
from extraction.pdf_text import extract_pages
from extraction.validation import ValidationResult
from schemas.holding import ReportKind
from scripts.ingest_corpus import read_corpus

ROOT = Path(__file__).resolve().parents[2]
RECORDED = ROOT / "backend" / "tests" / "recorded"
REQUESTS = ROOT / "backend" / "evaluations" / "results" / "manual"  # git-ignored


def corpus_row(fund_code: str) -> dict[str, str]:
    [row] = read_corpus(ROOT / "data" / "corpus.csv", [fund_code])
    if not row["period_start"]:
        raise SystemExit(f"{fund_code}: period unknown in corpus.csv")
    return row


def write_request(fund_code: str) -> Path:
    row = corpus_row(fund_code)
    pages = extract_pages(ROOT / row["local_path"])
    out = REQUESTS / fund_code
    out.mkdir(parents=True, exist_ok=True)
    (out / "system.txt").write_text(SYSTEM_PROMPT, encoding="utf-8")
    (out / "user.txt").write_text(render_pages(pages), encoding="utf-8")
    schema = LLMReport.model_json_schema()
    (out / "schema.json").write_text(json.dumps(schema, indent=1), encoding="utf-8")
    return out


def make_recording(
    row: dict[str, str], pages: list[str], reply: str, model: str, note: str
) -> dict:
    """The recorded run: the reply with everything needed to replay and audit it."""
    return {
        "fund_code": row["fund_code"],
        "period_start": row["period_start"],
        "period_end": row["period_end"],
        "report_kind": row["report_kind"],
        "pdf_sha256": row["sha256"],
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "produced_by": note,
        "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "request_sha256": request_hashes(
            SYSTEM_PROMPT, render_pages(pages), LLMReport.model_json_schema()
        ),
        "pages": pages,  # the input text, so the run replays without the PDF
        "reply": reply,
    }


def replay(recording: dict) -> tuple[LLMExtraction, ValidationResult]:
    """Run a recorded reply through the same code as a live run."""
    meta = ReportMeta(
        recording["fund_code"],
        date.fromisoformat(recording["period_start"]),
        date.fromisoformat(recording["period_end"]),
        ReportKind(recording["report_kind"]),
    )
    pages = recording["pages"]
    extraction = extract_with_llm(pages, meta, RecordedClient(recording))
    return extraction, validate_extraction(extraction, pages)


def record(fund_code: str, reply_path: Path, model: str, note: str) -> Path:
    row = corpus_row(fund_code)
    pages = extract_pages(ROOT / row["local_path"])
    reply = reply_path.read_text(encoding="utf-8")
    recording = make_recording(row, pages, reply, model, note)
    out = RECORDED / f"{fund_code}_{row['period_start'][:7]}__{model.replace('/', '_')}.json"
    out.write_text(json.dumps(recording, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    req = sub.add_parser("request", help="write the request for one fund")
    req.add_argument("fund")
    rec = sub.add_parser("record", help="record a reply and replay it")
    rec.add_argument("fund")
    rec.add_argument("reply", type=Path)
    rec.add_argument("--model", required=True)
    rec.add_argument("--note", required=True, help="who produced the reply, and how")
    args = parser.parse_args()

    if args.command == "request":
        print(f"request written to {write_request(args.fund)}")
        return
    path = record(args.fund, args.reply, args.model, args.note)
    extraction, check = replay(json.loads(path.read_text(encoding="utf-8")))
    print(f"recorded {path.relative_to(ROOT)}")
    print(f"rows: {len(extraction.holdings)}, summary: {extraction.summary is not None}")
    for e in extraction.errors:
        print(f"  error: {e}")
    for i in check.issues:
        print(f"  issue: {i.code} row={i.row_no} {i.message}")
    print("validation: ok" if check.ok else f"validation: {len(check.issues)} issue(s)")


if __name__ == "__main__":
    main()
