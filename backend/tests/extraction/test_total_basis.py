"""LLM output on the total basis (decision 0009), from the recorded IRF run to look-through.

The baseline already stored FTD weights; the LLM path did not, so its records could not be used by
package B. These tests run the recorded reply through validation, the conversion, the database and
the holding graph, and compare the result with the baseline's.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from exposure.graph import build_graph
from exposure.lookthrough import look_through
from extraction.baseline import parse_report
from extraction.baseline import to_total_basis as baseline_total
from extraction.ingest import ingest_llm
from extraction.weights import to_total_basis
from schemas.holding import AssetType, Holding, Status, WeightBasis
from scripts.llm_manual import replay
from storage.documents import add_document
from storage.extractions import list_holdings
from tests.extraction.test_baseline import IRF_META, IRF_PAGES
from tests.extraction.test_boundaries import _raw

RECORDING = Path(__file__).parents[1] / "recorded" / "IRF_2026-09__claude-opus-5-5.json"


def recording(**row_changes) -> dict:
    rec = json.loads(RECORDING.read_text(encoding="utf-8"))
    if row_changes:
        reply = json.loads(rec["reply"])
        for i, change in row_changes.items():
            reply["rows"][int(i)].update(change)
        rec["reply"] = json.dumps(reply, ensure_ascii=False)
    return rec


@pytest.fixture
def session(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def document(session):
    doc, _ = add_document(
        session, sha256="c" * 64, original_filename="IRF.pdf", size_bytes=1, storage_key="k"
    )
    return doc


def save(session, document, rec):
    extraction, _ = replay(rec)
    return ingest_llm(session, document_id=document.id, extraction=extraction, pages=rec["pages"])


def test_llm_run_saved_on_total_basis(session, document):
    run = save(session, document, recording())

    assert run.status is Status.OK, run.issues
    assert (run.model, run.prompt_version) == ("claude-opus-5-5", "2026-10-31.1")
    assert json.loads(run.raw_output)["number_format"] == "tr"
    rows = list_holdings(session, run.id)
    assert len(rows) == 23
    assert {r.weight_basis for r in rows} == {WeightBasis.TOTAL}
    bgp = next(r for r in rows if r.held_fund_code == "BGP")
    assert bgp.weight == Decimal("0.1059")  # FTD; the model read FPD 12,02


def test_llm_total_weights_match_the_printed_ftd():
    # The LLM path derives FTD as value / total value; the baseline uses the printed column.
    # They may differ only by the rounding of the printed percent.
    extraction, check = replay(recording())
    llm = to_total_basis(check.holdings, check.summary)
    base = parse_report(IRF_PAGES, IRF_META)
    printed = baseline_total(base)
    diffs = [abs(a.weight - b.weight) for a, b in zip(llm, printed, strict=True)]
    assert max(diffs) <= Decimal("0.0001")


def test_llm_and_baseline_give_the_same_look_through(session, document):
    run = save(session, document, recording())
    llm_graph = build_graph([_raw(r, Holding) for r in list_holdings(session, run.id)])
    base = parse_report(IRF_PAGES, IRF_META)
    base_graph = build_graph(baseline_total(base))

    llm, ref = look_through(llm_graph, "FUND:IRF"), look_through(base_graph, "FUND:IRF")
    assert llm.exposures.keys() == ref.exposures.keys()
    for key, weight in ref.exposures.items():
        assert llm.exposures[key] == pytest.approx(weight, abs=1e-4), key
    assert llm.unresolved.keys() == ref.unresolved.keys()


def test_mixed_bases_in_one_reply_end_up_total(session, document):
    # A model may read FTD on one row and FPD on the others: one graph needs one basis.
    rec = recording(**{"3": {"weight_text": "10,59", "weight_basis": "total"}})  # BGP, FTD column
    run = save(session, document, rec)
    rows = list_holdings(session, run.id)
    assert {r.weight_basis for r in rows} == {WeightBasis.TOTAL}
    assert next(r for r in rows if r.held_fund_code == "BGP").weight == Decimal("0.1059")
    build_graph([_raw(r, Holding) for r in rows])


def test_unknown_basis_is_saved_but_kept_out_of_look_through(session, document):
    rec = recording(**{"0": {"weight_basis": "unknown"}})
    run = save(session, document, rec)
    assert run.status is Status.NEEDS_REVIEW
    assert "weight_basis_unknown" in [i["code"] for i in run.issues]


def test_status_is_kept_and_printed_ftd_wins():
    _, check = replay(recording())
    flagged = [check.holdings[0].model_copy(update={"status": Status.NEEDS_REVIEW})]
    [row] = to_total_basis(flagged, check.summary, {1: Decimal("0.0026")})
    assert (row.status, row.weight, row.weight_basis) == (
        Status.NEEDS_REVIEW,
        Decimal("0.0026"),
        WeightBasis.TOTAL,
    )


def test_without_summary_nothing_changes():
    _, check = replay(recording())
    assert to_total_basis(check.holdings, None) == list(check.holdings)


def test_derivative_weight_is_scaled_not_derived_from_its_value():
    # A template that prints the notional amount: value / total value would be 4.11 here.
    _, check = replay(recording())
    future = check.holdings[0].model_copy(
        update={
            "asset_type": AssetType.DERIVATIVE,
            "isin": None,
            "value": Decimal("1555000000.00"),
            "weight": Decimal("0.0010"),
        }
    )
    [row] = to_total_basis([future], check.summary)
    assert row.weight == Decimal("0.0009")  # 0.0010 x 332.870.561,22 / 378.395.976,36
