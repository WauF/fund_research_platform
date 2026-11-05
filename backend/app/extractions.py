"""Read API for extraction results: a document's runs, holdings and report summary.

Which run is served by default: decision 0008 (docs/decisions/0008-extraction-run-secimi.md).
Records are returned in the shared schemas.holding contract, so clients see the same fields as
package A writes and package B reads.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from schemas.holding import Holding, ReportSummary, Status
from storage import documents, extractions
from storage.db import Base, get_session
from storage.models import ExtractionRun

router = APIRouter(prefix="/documents", tags=["extractions"])

SessionDep = Annotated[Session, Depends(get_session)]


class IssueOut(BaseModel):
    code: str
    message: str
    row_no: int | None = None  # None: the issue concerns the whole report


class RunOut(BaseModel):
    id: UUID
    document_id: int
    model: str
    prompt_version: str | None
    status: Status
    issues: list[IssueOut]
    holding_count: int
    created_at: datetime


class HoldingsOut(BaseModel):
    run: RunOut
    summary: ReportSummary | None
    holdings: list[Holding]


def _clean(value: Any) -> Any:
    """Numeric columns come back with the column's scale (0.1202000000): drop the padding."""
    if not isinstance(value, Decimal):
        return value
    return value.quantize(Decimal(1)) if value == value.to_integral() else value.normalize()


def _to_schema[T: BaseModel](row: Base, model: type[T]) -> T:
    fields = {
        column.key: _clean(getattr(row, column.key))
        for column in row.__table__.columns
        if column.key in model.model_fields
    }
    return model.model_validate(fields)


def _run_out(run: ExtractionRun, holding_count: int) -> RunOut:
    return RunOut(
        id=run.id,
        document_id=run.document_id,
        model=run.model,
        prompt_version=run.prompt_version,
        status=run.status,
        issues=[IssueOut(**issue) for issue in run.issues],
        holding_count=holding_count,
        created_at=run.created_at,
    )


def _require_document(session: Session, document_id: int) -> None:
    if documents.get_document(session, document_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"document {document_id} not found")


@router.get("/{document_id}/runs")
def list_runs(document_id: int, session: SessionDep) -> list[RunOut]:
    """All extraction runs of a document, newest first. raw_output is not included."""
    _require_document(session, document_id)
    runs = extractions.list_runs(session, document_id)
    counts = extractions.count_holdings(session, [run.id for run in runs])
    return [_run_out(run, counts[run.id]) for run in runs]


@router.get(
    "/{document_id}/holdings",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No such document or run"}},
)
def get_holdings(
    document_id: int,
    session: SessionDep,
    run_id: Annotated[UUID | None, Query(description="A specific run; default: latest")] = None,
    only_ok: Annotated[bool, Query(description="Default run: skip runs that need review")] = False,
    record_status: Annotated[
        Status | None, Query(alias="status", description="Only holdings with this status")
    ] = None,
) -> HoldingsOut:
    """Holdings and report summary of one extraction run of a document.

    Without run_id the latest run is served, also when it needs review: the response's run.status
    and each record's status say so. Pass only_ok=true to get the latest run that passed
    validation instead.
    """
    _require_document(session, document_id)
    if run_id is not None:
        run = extractions.get_run(session, run_id)
        if run is None or run.document_id != document_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, f"run {run_id} not found for document {document_id}"
            )
    else:
        run = extractions.latest_run(session, document_id, only_ok=only_ok)
        if run is None:
            detail = "no extraction run" + (" that passed validation" if only_ok else "")
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"{detail} for document {document_id}")

    rows = extractions.list_holdings(session, run.id, status=record_status)
    summary = extractions.get_summary(session, run.id)
    holding_count = extractions.count_holdings(session, [run.id])[run.id]
    return HoldingsOut(
        run=_run_out(run, holding_count),
        summary=_to_schema(summary, ReportSummary) if summary else None,
        holdings=[_to_schema(row, Holding) for row in rows],
    )
