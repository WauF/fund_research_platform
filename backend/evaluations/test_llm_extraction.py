"""Live LLM extraction of the IRF report, scored against the hand-built reference.

Run by hand only (see README.md):
    LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
    uv run pytest evaluations --force-enable-socket -m extraction
Writes the raw output, model, prompt version and scores to evaluations/results/.
"""

from __future__ import annotations

import csv
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from extraction.llm import extract_with_llm, validate_extraction
from extraction.llm_client import OpenAICompatibleClient
from tests.extraction.test_baseline import IRF_META, IRF_PAGES

ROOT = Path(__file__).resolve().parents[2]
RESULTS = Path(__file__).parent / "results"


def reference() -> dict[str, tuple[str, Decimal, Decimal]]:
    """KAP code -> (ISIN, value, FPD weight) of IRF's sub-funds."""
    with open(ROOT / "data" / "irf_look_through_elle.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["level"] == "2"]
    return {
        r["fund_code"]: (
            r["isin"],
            Decimal(r["value_tl"]),
            Decimal(r["weight_portfolio_in_parent"]),
        )
        for r in rows
    }


@pytest.mark.extraction
@pytest.mark.skipif(not os.environ.get("LLM_MODEL"), reason="LLM_MODEL is not set")
def test_irf_extraction() -> None:
    client = OpenAICompatibleClient.from_env()
    extraction = extract_with_llm(IRF_PAGES, IRF_META, client, run_id="eval-irf")
    check = validate_extraction(extraction, IRF_PAGES)

    expected = reference()
    got = {
        h.held_fund_code: (h.isin, h.value, h.weight)
        for h in extraction.holdings
        if h.held_fund_code
    }
    exact = sum(1 for code, row in expected.items() if got.get(code) == row)
    weight_error_pp = max(
        (abs(got[c][2] - expected[c][2]) * 100 for c in expected if c in got), default=None
    )
    precision = exact / len(got) if got else 0.0
    recall = exact / len(expected)
    f1 = 2 * precision * recall / (precision + recall) if exact else 0.0

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"llm_irf_{client.model.replace('/', '_')}.json"
    out.write_text(
        json.dumps(
            {
                "model": extraction.model,
                "prompt_version": extraction.prompt_version,
                "sub_funds_exact": exact,
                "sub_funds_expected": len(expected),
                "f1": f1,
                "max_weight_error_pp": str(weight_error_pp),
                "validation_issues": [i.__dict__ for i in check.issues],
                "errors": extraction.errors,
                "raw_output": extraction.raw_output,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    # Draft target from the presentation (criterion 1); fixed after the November pilot.
    assert f1 >= 0.95, f"F1 {f1:.3f}, see {out.name}"
