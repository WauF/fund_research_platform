"""Score extractions against the gold set (success criterion 1): row F1 and weight error.

Run from backend/:
    uv run python -m scripts.evaluate_extraction baseline [FUND ...]
    uv run python -m scripts.evaluate_extraction recorded [FUND ...]   # tests/recorded/ LLM runs
Scores every fund that has a gold file in data/gold/. Writes the details to
evaluations/results/eval_<source>.json (git-ignored). Gold files with draft rows are marked
UNVERIFIED: until each row is checked against the PDF, their scores are not accuracy.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from extraction.baseline import UnsupportedTemplate, parse_report
from extraction.evaluate import Score, read_gold, score
from extraction.pdf_text import extract_pages
from schemas.holding import Holding
from scripts.ingest_corpus import _meta, read_corpus
from scripts.llm_manual import replay

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "gold"
RECORDED = ROOT / "backend" / "tests" / "recorded"
RESULTS = ROOT / "backend" / "evaluations" / "results"


def predicted(source: str, fund_code: str) -> tuple[list[Holding], str] | None:
    """The rows an extractor produced for this fund, and a label for the run; None if none."""
    if source == "baseline":
        [row] = read_corpus(ROOT / "data" / "corpus.csv", [fund_code])
        try:
            result = parse_report(extract_pages(ROOT / row["local_path"]), _meta(row))
        except UnsupportedTemplate:
            return None
        return result.holdings, "baseline"
    recordings = sorted(RECORDED.glob(f"{fund_code}_*.json"))
    if not recordings:
        return None
    recording = json.loads(recordings[-1].read_text(encoding="utf-8"))
    extraction, _ = replay(recording)
    return extraction.holdings, recording["model"]


def as_dict(fund_code: str, run: str, s: Score) -> dict:
    return {
        "fund": fund_code,
        "run": run,
        "gold_verified": s.gold_verified,
        "gold_rows": s.gold_rows,
        "predicted_rows": s.predicted_rows,
        "matched": s.matched,
        "correct": s.correct,
        "precision": round(s.precision, 4),
        "recall": round(s.recall, 4),
        "f1": round(s.f1, 4),
        "max_weight_error_pp": str(s.max_weight_error_pp),
        "mean_weight_error_pp": str(s.mean_weight_error_pp),
        "basis_mismatches": s.basis_mismatches,
        "mistakes": s.mistakes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", choices=["baseline", "recorded"])
    parser.add_argument("funds", nargs="*")
    args = parser.parse_args()

    funds = args.funds or sorted(
        p.name.split("_")[0] for p in GOLD.glob("*_2026-09.csv") if "summary" not in p.name
    )
    results = []
    for code in funds:
        gold_path = GOLD / f"{code}_2026-09.csv"
        run = predicted(args.source, code) if gold_path.exists() else None
        if run is None:
            print(f"{code:4} skipped: no gold file or no {args.source} run")
            continue
        s = score(run[0], read_gold(gold_path))
        results.append(as_dict(code, run[1], s))
        flag = "" if s.gold_verified else "  UNVERIFIED GOLD (draft rows): not an accuracy number"
        print(
            f"{code:4} {run[1]:16} F1={s.f1:.3f} P={s.precision:.3f} R={s.recall:.3f} "
            f"rows {s.correct}/{s.gold_rows} max weight err={s.max_weight_error_pp} pp{flag}"
        )
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"eval_{args.source}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"details: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
