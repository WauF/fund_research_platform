"""Write an extraction to the database (decisions 0008 and 0009).

PDF text -> extraction (rule-based baseline or LLM) -> validation (FPD) -> total-value weights
(FTD) -> one extraction run with all its records, in a single transaction
(storage.extractions.save_extraction_run).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from uuid import uuid4

from sqlalchemy.orm import Session

from extraction.baseline import ReportMeta, parse_report, to_total_basis
from extraction.llm import LLMExtraction, validate_extraction
from extraction.validation import Issue, validate_report
from extraction.weights import to_total_basis as weights_to_total
from schemas.holding import WeightBasis
from storage.extractions import save_extraction_run
from storage.models import ExtractionRun

BASELINE_MODEL = "baseline"  # data contract, docs/veri-sozlesmesi.md §3.5


def ingest_baseline(
    session: Session,
    *,
    document_id: int,
    pages: Sequence[str],
    meta: ReportMeta | None = None,
    known_isins: set[str] | None = None,
) -> ExtractionRun:
    """Extract one standard-template report and save it as a new extraction run.

    Raises UnsupportedTemplate for other report layouts (nothing is written). A faulty report is
    still saved: its records and the run are needs_review, with the reasons in run.issues.
    Baseline warnings (e.g. a row it could not read) become issues too, so the run is never ok when
    a row may be missing.
    """
    run_id = uuid4()
    result = parse_report(list(pages), meta, run_id)
    check = validate_report(result.holdings, result.summary, pages, known_isins)
    validated = replace(result, holdings=check.holdings, summary=check.summary)
    issues = [*check.issues, *(Issue("baseline_warning", w) for w in result.warnings)]
    return save_extraction_run(
        session,
        run_id=run_id,
        document_id=document_id,
        model=BASELINE_MODEL,
        holdings=to_total_basis(validated),
        summary=validated.summary,
        issues=issues,
    )


def ingest_llm(
    session: Session,
    *,
    document_id: int,
    extraction: LLMExtraction,
    pages: Sequence[str],
    known_isins: set[str] | None = None,
) -> ExtractionRun:
    """Save an LLM extraction (live or recorded) as a new extraction run, on the total basis.

    Same order as the baseline: validate on the weights the model read, then convert to FTD.
    Model, prompt version and raw output are stored with the run (reproducibility). A faulty
    extraction is still saved, as needs_review. Rows whose basis the report does not state
    (unknown) cannot be converted; the run then gets an issue, so it never reaches look-through.
    """
    check = validate_extraction(extraction, list(pages), known_isins)
    holdings = weights_to_total(check.holdings, check.summary)
    issues = list(check.issues)
    if any(h.weight_basis is WeightBasis.UNKNOWN for h in holdings):
        issues.append(Issue("weight_basis_unknown", "weights not converted to the total basis"))
    return save_extraction_run(
        session,
        run_id=extraction.run_id,
        document_id=document_id,
        model=extraction.model,
        holdings=holdings,
        summary=check.summary,
        issues=issues,
        prompt_version=extraction.prompt_version,
        raw_output=extraction.raw_output,
    )
