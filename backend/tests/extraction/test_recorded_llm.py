"""Recorded LLM runs (tests/recorded/), replayed through the same code as a live run, offline.

Each recording carries its own input text, the request hashes and the raw reply
(scripts/llm_manual.py). A changed prompt, schema or PDF text makes the recording stale: it fails
here and must be recorded again, instead of an old answer passing silently.
"""

import hashlib
import json
from pathlib import Path

import pytest

from extraction.baseline import parse_report
from extraction.llm_client import RecordedClient, StaleRecording
from extraction.pdf_text import extract_pages
from scripts.llm_manual import replay
from tests.extraction.test_baseline import IRF_META, IRF_PAGES

ROOT = Path(__file__).parents[3]
RECORDED = Path(__file__).parents[1] / "recorded"
RECORDINGS = sorted(RECORDED.glob("*.json"))


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_there_is_a_recorded_run():
    assert RECORDINGS, "no recorded LLM run in tests/recorded/"


@pytest.mark.parametrize("path", RECORDINGS, ids=lambda p: p.stem)
def test_recording_replays_and_validates(path):
    recording = load(path)
    assert recording["produced_by"] and recording["model"] and recording["pdf_sha256"]
    extraction, check = replay(recording)
    assert extraction.errors == []
    assert extraction.holdings, "the reply converted to no rows"
    assert check.ok, check.issues


@pytest.mark.parametrize("path", RECORDINGS, ids=lambda p: p.stem)
def test_recorded_input_is_the_pdf_text_today(path):
    """The replay hashes the pages stored in the recording; this ties them to the real PDF.

    If the PDF or the text extraction (extraction/pdf_text.py) changes, the recording is stale.
    """
    recording = load(path)
    pdf = ROOT / recording["pdf_path"]
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == recording["pdf_sha256"]
    assert extract_pages(pdf) == recording["pages"], f"{path.name} is stale: record it again"


def test_irf_recording_matches_the_baseline():
    """Same rows as the rule-based baseline: quote, value, FPD weight, ISIN, fund code."""
    extraction, _ = replay(load(RECORDED / "IRF_2026-09__claude-opus-5-5.json"))
    baseline = parse_report(IRF_PAGES, IRF_META)

    def key(h):
        return (h.quote, h.value, h.weight, h.weight_basis, h.isin, h.held_fund_code, h.asset_type)

    assert [key(h) for h in extraction.holdings] == [key(h) for h in baseline.holdings]
    s, b = extraction.summary, baseline.summary
    assert (s.portfolio_value, s.total_value, s.liabilities) == (
        b.portfolio_value,
        b.total_value,
        b.liabilities,
    )


def test_recording_is_stale_when_the_prompt_changes():
    recording = load(RECORDED / "IRF_2026-09__claude-opus-5-5.json")
    client = RecordedClient(recording)
    with pytest.raises(StaleRecording, match="system"):
        client.complete_json("a different prompt", "=== PAGE 1 ===\n", {})
