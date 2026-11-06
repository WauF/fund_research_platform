"""Baseline extraction written to the database (SQLite in memory, moto S3: tests/conftest.py)."""

import re
from decimal import Decimal

import pytest

from extraction import ingest as ingest_module
from extraction.baseline import UnsupportedTemplate
from extraction.ingest import BASELINE_MODEL, ingest_baseline
from schemas.holding import Status, WeightBasis
from scripts import ingest_corpus as script
from storage.documents import add_document, get_by_sha256
from storage.extractions import latest_run, list_holdings, list_runs
from storage.objects import ObjectStore
from tests.conftest import BUCKET
from tests.extraction.test_baseline import IRF_META, IRF_PAGES


@pytest.fixture
def session(session_factory):
    with session_factory() as session:
        yield session


@pytest.fixture
def document(session):
    doc, _ = add_document(
        session, sha256="a" * 64, original_filename="IRF.pdf", size_bytes=1, storage_key="k"
    )
    return doc


def test_irf_saved_on_total_basis(session, document):
    run = ingest_baseline(session, document_id=document.id, pages=IRF_PAGES, meta=IRF_META)

    assert run.model == BASELINE_MODEL
    assert run.status is Status.OK
    assert run.issues == []
    rows = list_holdings(session, run.id)
    assert len(rows) == 23
    assert {r.weight_basis for r in rows} == {WeightBasis.TOTAL}
    bgp = next(r for r in rows if r.held_fund_code == "BGP")
    assert bgp.weight == Decimal("0.1059")  # FTD; the FPD weight is 0.1202
    assert run.summary.total_value == Decimal("378395976.36")
    assert latest_run(session, document.id, only_ok=True).id == run.id


def test_faulty_report_saved_for_review(session, document):
    # A misread fund total value: the summary no longer adds up.
    pages = [
        re.sub(r"^(FON TOPLAM DEĞERİ\s+)378", r"\g<1>388", p, flags=re.MULTILINE) for p in IRF_PAGES
    ]
    assert pages != IRF_PAGES

    run = ingest_baseline(session, document_id=document.id, pages=pages, meta=IRF_META)

    assert run.status is Status.NEEDS_REVIEW
    assert run.issues
    assert all(r.status is Status.NEEDS_REVIEW for r in list_holdings(session, run.id))
    assert latest_run(session, document.id, only_ok=True) is None


def test_baseline_warnings_become_issues(session, document, monkeypatch):
    real = ingest_module.parse_report

    def with_warning(*args, **kwargs):
        result = real(*args, **kwargs)
        result.warnings.append("row 99 on page 2 skipped: no plausible reading")
        return result

    monkeypatch.setattr(ingest_module, "parse_report", with_warning)
    run = ingest_baseline(session, document_id=document.id, pages=IRF_PAGES, meta=IRF_META)

    assert run.status is Status.NEEDS_REVIEW
    assert [i["code"] for i in run.issues] == ["baseline_warning"]


def test_unsupported_template_writes_nothing(session, document):
    with pytest.raises(UnsupportedTemplate):
        ingest_baseline(session, document_id=document.id, pages=["", ""], meta=IRF_META)
    assert list_runs(session, document.id) == []


# --- scripts/ingest_corpus.py ---------------------------------------------------------------

PDF_BYTES = b"%PDF-1.7 IRF stand-in"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """One IRF row whose 'PDF' is a stand-in; its text is the IRF fixture."""
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "raw" / "IRF.pdf").write_bytes(PDF_BYTES)
    monkeypatch.setattr(script, "extract_pages", lambda _path: IRF_PAGES)
    row = {
        "fund_code": "IRF",
        "primary": "yes",
        "period_start": "2026-09-28",
        "period_end": "2026-10-02",
        "report_kind": "weekly",
        "local_path": "data/raw/IRF.pdf",
    }
    return tmp_path, [row]


def test_corpus_uploads_and_saves(session, s3, corpus):
    root, rows = corpus
    store = ObjectStore(s3, BUCKET)

    [outcome] = script.ingest_corpus(session, store, rows, root)

    assert outcome.result == "saved", outcome
    doc = get_by_sha256(session, script.hashlib.sha256(PDF_BYTES).hexdigest())
    assert doc.storage_key == f"pdfs/{doc.sha256}.pdf"
    assert s3.get_object(Bucket=BUCKET, Key=doc.storage_key)["Body"].read() == PDF_BYTES
    assert len(list_runs(session, doc.id)) == 1


def test_corpus_skips_extracted_documents_unless_forced(session, s3, corpus):
    root, rows = corpus
    store = ObjectStore(s3, BUCKET)
    script.ingest_corpus(session, store, rows, root)

    [again] = script.ingest_corpus(session, store, rows, root)
    [forced] = script.ingest_corpus(session, store, rows, root, force=True)

    assert again.result == "skipped"
    assert forced.result == "saved"
    doc = get_by_sha256(session, script.hashlib.sha256(PDF_BYTES).hexdigest())
    assert len(list_runs(session, doc.id)) == 2


def test_corpus_dry_run_and_missing_file(corpus):
    root, rows = corpus
    missing = {**rows[0], "fund_code": "XXX", "local_path": "data/raw/none.pdf"}

    checked, absent = script.ingest_corpus(None, None, [*rows, missing], root)

    assert (checked.result, checked.detail) == ("checked", "23 rows, ok")
    assert absent.result == "missing"


def test_corpus_unsupported_uploads_nothing(session, s3, corpus, monkeypatch):
    root, rows = corpus
    monkeypatch.setattr(script, "extract_pages", lambda _path: ["", ""])

    [outcome] = script.ingest_corpus(session, ObjectStore(s3, BUCKET), rows, root)

    assert outcome.result == "unsupported"
    assert "Contents" not in s3.list_objects_v2(Bucket=BUCKET)
    assert get_by_sha256(session, script.hashlib.sha256(PDF_BYTES).hexdigest()) is None
