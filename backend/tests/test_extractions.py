"""save_extraction_run() and the read API for runs, holdings and summaries.

Records use real IRF values (weekly report 28.09–02.10.2026). Fixtures: tests/conftest.py.
"""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from schemas.holding import AssetType, Holding, ReportKind, ReportSummary, Status, WeightBasis
from storage import documents, extractions
from storage.models import ExtractionRun, HoldingRow, ReportSummaryRow

SCOPE = {
    "fund_code": "IRF",
    "period_start": date(2026, 9, 28),
    "period_end": date(2026, 10, 2),
    "report_kind": ReportKind.WEEKLY,
}


def holding(run_id: UUID, row_no: int, **overrides) -> Holding:
    fields = {
        **SCOPE,
        "page": 1,
        "quote": "BGP-AK PORTFÖY TL AK 5.884.985,00 6,796958 29/09/26 6,809489 40.073.740,62",
        "extraction_run_id": run_id,
        "row_no": row_no,
        "name": "BGP-AK PORTFÖY",
        "asset_type": AssetType.FUND,
        "isin": "TRYAKPO00625",
        "instrument_code": "BGP",
        "held_fund_code": "BGP",
        "value": Decimal("40073740.62"),
        "weight": Decimal("0.1202"),
        "weight_basis": WeightBasis.PORTFOLIO,
    }
    return Holding(**{**fields, **overrides})


def summary(run_id: UUID, **overrides) -> ReportSummary:
    fields = {
        **SCOPE,
        "page": 2,
        "quote": "FON TOPLAM DEĞERİ 378.395.976,36 100,00 %",
        "extraction_run_id": run_id,
        "portfolio_value": Decimal("332870561.22"),
        "cash_equivalents": Decimal("1085.71"),
        "receivables": Decimal("56572172.96"),
        "other_assets": Decimal("0.00"),
        "liabilities": Decimal("-11047843.53"),
        "total_value": Decimal("378395976.36"),
    }
    return ReportSummary(**{**fields, **overrides})


def two_holdings(run_id: UUID) -> list[Holding]:
    # Same ISIN twice (two purchase lots): must be stored as two rows.
    return [
        holding(run_id, 1),
        holding(run_id, 2, value=Decimal("-977400.00"), weight=Decimal("-0.0029")),
    ]


@pytest.fixture
def session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def document_id(session: Session) -> int:
    document, _ = documents.add_document(
        session,
        sha256="a" * 64,
        original_filename="IRF_2026-09.pdf",
        size_bytes=1,
        storage_key=f"pdfs/{'a' * 64}.pdf",
    )
    return document.id


def save(session: Session, document_id: int, run_id: UUID | None = None, **overrides):
    run_id = run_id or uuid4()
    fields = {
        "run_id": run_id,
        "document_id": document_id,
        "model": "baseline",
        "holdings": two_holdings(run_id),
        "summary": summary(run_id),
    }
    return extractions.save_extraction_run(session, **{**fields, **overrides})


def count(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


# --- save_extraction_run -------------------------------------------------------------------------


def test_save_writes_run_holdings_and_summary(session, document_id) -> None:
    run = save(session, document_id, prompt_version="2026-10-31.1", raw_output='{"rows": []}')

    assert run.status is Status.OK
    assert run.issues == []
    assert run.raw_output == '{"rows": []}'
    assert [h.row_no for h in run.holdings] == [1, 2]
    assert run.holdings[1].value == Decimal("-977400.00")
    assert run.summary.total_value == Decimal("378395976.36")


def test_records_round_trip_through_the_schema(session, document_id) -> None:
    run_id = uuid4()
    written = two_holdings(run_id)
    save(session, document_id, run_id, holdings=written)
    session.expire_all()

    read = [
        Holding.model_validate(row, from_attributes=True)
        for row in extractions.list_holdings(session, run_id)
    ]

    assert read == written


def test_issues_make_the_run_need_review(session, document_id) -> None:
    class Issue:  # shaped like extraction.validation.Issue
        code, message, row_no = "isin_check_digit", "TRYAKPO00626 fails the check digit", 1

    run = save(
        session,
        document_id,
        issues=[Issue(), {"code": "summary_missing", "message": "no table", "row_no": None}],
    )

    assert run.status is Status.NEEDS_REVIEW
    assert run.issues == [
        {"code": "isin_check_digit", "message": "TRYAKPO00626 fails the check digit", "row_no": 1},
        {"code": "summary_missing", "message": "no table", "row_no": None},
    ]


def test_a_record_needing_review_makes_the_run_need_review(session, document_id) -> None:
    run_id = uuid4()
    rows = [holding(run_id, 1, status=Status.NEEDS_REVIEW)]

    assert save(session, document_id, run_id, holdings=rows).status is Status.NEEDS_REVIEW


def test_run_without_summary(session, document_id) -> None:
    run = save(session, document_id, summary=None)

    assert run.summary is None
    assert count(session, ReportSummaryRow) == 0


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"holdings": [holding(uuid4(), 1)]}, ValueError),  # holding of another run
        ({"summary": summary(uuid4())}, ValueError),  # summary of another run
    ],
)
def test_invalid_input_writes_nothing(session, document_id, overrides, error) -> None:
    with pytest.raises(error):
        save(session, document_id, **overrides)

    assert count(session, ExtractionRun) == count(session, HoldingRow) == 0


def test_unknown_document_writes_nothing(session, document_id) -> None:
    with pytest.raises(LookupError):
        save(session, 999)

    assert count(session, ExtractionRun) == count(session, HoldingRow) == 0


def test_duplicate_row_no_writes_nothing(session, document_id) -> None:
    run_id = uuid4()
    with pytest.raises(ValueError, match="row_no"):
        save(session, document_id, run_id, holdings=[holding(run_id, 1), holding(run_id, 1)])

    assert count(session, ExtractionRun) == 0


def test_same_run_id_twice_is_rejected(session, document_id) -> None:
    run_id = uuid4()
    save(session, document_id, run_id)

    with pytest.raises(IntegrityError):
        save(session, document_id, run_id)

    assert count(session, ExtractionRun) == 1
    assert count(session, HoldingRow) == 2


# --- latest_run (decision 0008) ------------------------------------------------------------------


def test_latest_run_is_the_newest(session, document_id) -> None:
    save(session, document_id)
    newest = save(session, document_id)

    assert extractions.latest_run(session, document_id).id == newest.id


def test_latest_ok_run_skips_runs_that_need_review(session, document_id) -> None:
    ok = save(session, document_id)
    flagged = save(session, document_id, issues=[{"code": "x", "message": "y"}])

    assert extractions.latest_run(session, document_id).id == flagged.id
    assert extractions.latest_run(session, document_id, only_ok=True).id == ok.id


def test_latest_run_of_document_without_runs(session, document_id) -> None:
    assert extractions.latest_run(session, document_id) is None


# --- API -----------------------------------------------------------------------------------------


def test_get_holdings_serves_the_latest_run(client, session, document_id) -> None:
    save(session, document_id)
    run = save(session, document_id)

    response = client.get(f"/documents/{document_id}/holdings")

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["id"] == str(run.id)
    assert body["run"]["status"] == "ok"
    assert body["run"]["holding_count"] == 2
    assert [h["row_no"] for h in body["holdings"]] == [1, 2]
    first = body["holdings"][0]
    assert first["extraction_run_id"] == str(run.id)
    assert first["held_fund_code"] == "BGP"
    # Decimals keep their printed precision, without the column's padding.
    assert first["value"] == "40073740.62"
    assert first["weight"] == "0.1202"
    assert body["summary"]["liabilities"] == "-11047843.53"
    assert "raw_output" not in body["run"]


def test_get_holdings_of_a_given_run(client, session, document_id) -> None:
    older = save(session, document_id)
    save(session, document_id)

    response = client.get(f"/documents/{document_id}/holdings", params={"run_id": str(older.id)})

    assert response.json()["run"]["id"] == str(older.id)


def test_get_holdings_filters_by_status(client, session, document_id) -> None:
    run_id = uuid4()
    rows = [holding(run_id, 1), holding(run_id, 2, status=Status.NEEDS_REVIEW)]
    save(session, document_id, run_id, holdings=rows)

    response = client.get(f"/documents/{document_id}/holdings", params={"status": "needs_review"})

    body = response.json()
    assert [h["row_no"] for h in body["holdings"]] == [2]
    assert body["run"]["holding_count"] == 2  # the count is of the whole run


def test_get_holdings_only_ok(client, session, document_id) -> None:
    ok = save(session, document_id)
    save(session, document_id, issues=[{"code": "x", "message": "y"}])

    latest = client.get(f"/documents/{document_id}/holdings").json()
    latest_ok = client.get(f"/documents/{document_id}/holdings", params={"only_ok": True}).json()

    assert latest["run"]["status"] == "needs_review"
    assert latest["run"]["issues"] == [{"code": "x", "message": "y", "row_no": None}]
    assert latest_ok["run"]["id"] == str(ok.id)


def test_get_holdings_not_found(client, session, document_id) -> None:
    other_document, _ = documents.add_document(
        session, sha256="b" * 64, original_filename="b.pdf", size_bytes=1, storage_key="b"
    )
    run_of_other = save(session, other_document.id)
    base = f"/documents/{document_id}/holdings"

    assert client.get("/documents/999/holdings").status_code == 404
    assert client.get(base).status_code == 404  # no run yet
    assert client.get(base, params={"run_id": str(uuid4())}).status_code == 404
    # A run of another document is not served under this one.
    assert client.get(base, params={"run_id": str(run_of_other.id)}).status_code == 404
    assert client.get(base, params={"run_id": "not-a-uuid"}).status_code == 422


def test_list_runs(client, session, document_id) -> None:
    first = save(session, document_id)
    second = save(
        session, document_id, summary=None, holdings=[], issues=[{"code": "x", "message": "y"}]
    )

    response = client.get(f"/documents/{document_id}/runs")

    assert response.status_code == 200
    runs = response.json()
    assert [r["id"] for r in runs] == [str(second.id), str(first.id)]
    assert [r["holding_count"] for r in runs] == [0, 2]
    assert runs[0]["status"] == "needs_review"
    assert client.get("/documents/999/runs").status_code == 404
