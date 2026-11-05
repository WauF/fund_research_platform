"""Repository functions for extraction runs and their records (decision 0008)."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from schemas.holding import Holding, ReportSummary, Status
from storage.models import Document, ExtractionRun, HoldingRow, ReportSummaryRow


class IssueLike(Protocol):
    """extraction.validation.Issue, without importing package A here."""

    code: str
    message: str
    row_no: int | None


def _issue_dict(issue: IssueLike | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(issue, Mapping):
        return {"code": issue["code"], "message": issue["message"], "row_no": issue.get("row_no")}
    return {"code": issue.code, "message": issue.message, "row_no": issue.row_no}


def save_extraction_run(
    session: Session,
    *,
    run_id: UUID,
    document_id: int,
    model: str,
    holdings: Sequence[Holding],
    summary: ReportSummary | None,
    issues: Sequence[IssueLike | Mapping[str, Any]] = (),
    prompt_version: str | None = None,
    raw_output: str | None = None,
) -> ExtractionRun:
    """Write one extraction run and all its records in a single transaction.

    Pass the records after validation (extraction.validation), so their status is final. Nothing is
    written if any check fails:
    - LookupError: the document does not exist.
    - ValueError: a record belongs to another run, or two holdings share a row_no.
    - sqlalchemy.exc.IntegrityError: a run with this id was already saved.

    The run is needs_review if there are issues or any record needs review.
    """
    if session.get(Document, document_id) is None:
        raise LookupError(f"document {document_id} does not exist")
    records: list[Holding | ReportSummary] = [*holdings, *([summary] if summary else [])]
    if foreign := {r.extraction_run_id for r in records} - {run_id}:
        raise ValueError(f"records belong to other runs: {sorted(map(str, foreign))}")
    row_nos = [h.row_no for h in holdings]
    if len(row_nos) != len(set(row_nos)):
        raise ValueError("two holdings share a row_no")

    issue_dicts = [_issue_dict(i) for i in issues]
    flagged = any(r.status is Status.NEEDS_REVIEW for r in records)
    run = ExtractionRun(
        id=run_id,
        document_id=document_id,
        model=model,
        prompt_version=prompt_version,
        raw_output=raw_output,
        status=Status.NEEDS_REVIEW if issue_dicts or flagged else Status.OK,
        issues=issue_dicts,
        holdings=[HoldingRow(**h.model_dump()) for h in holdings],
        summary=ReportSummaryRow(**summary.model_dump()) if summary else None,
    )
    session.add(run)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(run)
    return run


def get_run(session: Session, run_id: UUID) -> ExtractionRun | None:
    return session.get(ExtractionRun, run_id)


def list_runs(session: Session, document_id: int) -> list[ExtractionRun]:
    """All runs of a document, newest first."""
    query = (
        select(ExtractionRun)
        .where(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id)
    )
    return list(session.scalars(query))


def latest_run(
    session: Session, document_id: int, *, only_ok: bool = False
) -> ExtractionRun | None:
    """The run served for a document by default (decision 0008).

    only_ok=True skips runs that need review: use it for anything computed from the data (e.g.
    look-through), where a faulty run must not be used.
    """
    query = (
        select(ExtractionRun)
        .where(ExtractionRun.document_id == document_id)
        .order_by(ExtractionRun.created_at.desc(), ExtractionRun.id)
        .limit(1)
    )
    if only_ok:
        query = query.where(ExtractionRun.status == Status.OK)
    return session.scalars(query).first()


def list_holdings(
    session: Session, run_id: UUID, *, status: Status | None = None
) -> list[HoldingRow]:
    query = (
        select(HoldingRow).where(HoldingRow.extraction_run_id == run_id).order_by(HoldingRow.row_no)
    )
    if status is not None:
        query = query.where(HoldingRow.status == status)
    return list(session.scalars(query))


def get_summary(session: Session, run_id: UUID) -> ReportSummaryRow | None:
    query = select(ReportSummaryRow).where(ReportSummaryRow.extraction_run_id == run_id)
    return session.scalars(query).one_or_none()


def count_holdings(session: Session, run_ids: Sequence[UUID]) -> dict[UUID, int]:
    """Number of holdings per run, in one query."""
    if not run_ids:
        return {}
    query = (
        select(HoldingRow.extraction_run_id, func.count())
        .where(HoldingRow.extraction_run_id.in_(run_ids))
        .group_by(HoldingRow.extraction_run_id)
    )
    counts = {run_id: n for run_id, n in session.execute(query)}
    return {run_id: counts.get(run_id, 0) for run_id in run_ids}
