"""Package A's output where it meets packages B and C.

Unit tests check extraction against data shaped the way extraction itself produces it. The bugs
found in review on #18 and #19 lived at the boundaries instead: values read back from the database
(NUMERIC(24,6)), the holding graph (no mixed weight bases), a failed upload. These tests cross
those boundaries with the real IRF report.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.extractions import _to_schema
from exposure.graph import build_graph
from exposure.lookthrough import look_through
from extraction.baseline import ReportMeta
from extraction.ingest import ingest_baseline
from extraction.pdf_text import extract_pages
from extraction.validation import validate_report
from schemas.holding import Holding, ReportKind, ReportSummary, WeightBasis
from scripts.llm_manual import replay
from storage.documents import add_document
from storage.extractions import get_summary, list_holdings
from tests.extraction.test_baseline import IRF_META, IRF_PAGES

RECORDED = Path(__file__).parents[1] / "recorded"
ROOT = Path(__file__).parents[3]


@pytest.fixture
def session(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def irf_run(session):
    doc, _ = add_document(
        session, sha256="b" * 64, original_filename="IRF.pdf", size_bytes=1, storage_key="k"
    )
    return ingest_baseline(session, document_id=doc.id, pages=IRF_PAGES, meta=IRF_META)


def _raw(row, model):
    """A database row as the schema record, with the column's scale kept (977400.000000)."""
    fields = {
        c.key: getattr(row, c.key) for c in row.__table__.columns if c.key in model.model_fields
    }
    return model.model_validate(fields)


@pytest.mark.parametrize("read", [_raw, _to_schema], ids=["raw_columns", "api_schema"])
def test_records_from_the_database_validate_again(session, irf_run, read):
    # Review on #19: re-validating records loaded from the database flagged all 23 rows. The review
    # and corrections flow (package C) will do exactly this.
    holdings = [read(r, Holding) for r in list_holdings(session, irf_run.id)]
    summary = read(get_summary(session, irf_run.id), ReportSummary)
    assert len(holdings) == 23
    assert any(h.value.as_tuple().exponent != -2 for h in holdings)  # the scale really changed

    check = validate_report(holdings, summary, IRF_PAGES)
    assert check.ok, check.issues


def test_saved_records_build_a_graph(session, irf_run):
    # What package B reads: one weight basis per graph, total value (decision 0009).
    holdings = [_raw(r, Holding) for r in list_holdings(session, irf_run.id)]
    graph = build_graph(holdings)
    assert graph.graph["weight_basis"] == WeightBasis.TOTAL.value
    result = look_through(graph, "FUND:IRF")
    assert len(result.unresolved) == 20  # IRF's sub-funds have no report in this graph


def _ftd_reply() -> dict:
    """The IRF recording as a model reading the FTD column would answer it.

    FTD is the last number of each quote; the VİOP collateral row prints no FTD, so its weight is
    empty, the case from the review.
    """
    recording = json.loads((RECORDED / "IRF_2026-09__claude-opus-5-5.json").read_text("utf-8"))
    reply = json.loads(recording["reply"])
    for row in reply["rows"]:
        row["weight_basis"] = "total"
        row["weight_text"] = (
            "" if row["name"] == "VIOP Nakit Teminatı" else row["quote"].split()[-1]
        )
    recording["reply"] = json.dumps(reply, ensure_ascii=False)
    return recording


def test_llm_output_with_a_missing_weight_still_builds_a_graph():
    # Review on #19: a missing weight derived on another basis made build_graph raise.
    # The replay checks the request hashes, not the reply, so the reply can be changed here.
    extraction, check = replay(_ftd_reply())

    assert [i.code for i in check.issues] == ["extraction_error"]
    viop = next(h for h in extraction.holdings if h.name == "VIOP Nakit Teminatı")
    assert viop.weight == Decimal("0.0315")  # 11.927.534,70 / 378.395.976,36 total value
    graph = build_graph(extraction.holdings)
    assert graph.graph["weight_basis"] == WeightBasis.TOTAL.value


def test_money_market_rows_from_the_database_are_one_leaf(session):
    # Item 4: TPP/BPP rows have no ISIN, so the graph keys them by name. With the whole printed
    # line as the name, PKV's 64 BPP/TPP placements were 64 leaves. Through the database (C) into
    # the graph (B) they must be one leaf per market, with the same total weight.
    pdf = ROOT / "data/raw/PKV/haftalik/PKV_2026-09-07_2026-09-11.pdf"
    meta = ReportMeta("PKV", date(2026, 9, 7), date(2026, 9, 11), ReportKind.WEEKLY)
    doc, _ = add_document(
        session, sha256="d" * 64, original_filename=pdf.name, size_bytes=1, storage_key="k"
    )
    run = ingest_baseline(session, document_id=doc.id, pages=extract_pages(pdf), meta=meta)
    rows = [_raw(r, Holding) for r in list_holdings(session, run.id)]
    money_market = [r for r in rows if r.name in {"TPP", "BPP"}]
    assert len(money_market) == 64

    graph = build_graph(rows)
    leaves = {key: w for _, key, w in graph.out_edges("FUND:PKV", data="weight")}
    assert len(leaves) == 9
    expected = sum(float(r.weight) for r in money_market)
    assert leaves["NAME:BPP"] + leaves["NAME:TPP"] == pytest.approx(expected)
