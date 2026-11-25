# CI proposal for Ahmet: Postgres tests + extraction smoke test

Hey Ahmet, `.github/` and the test setup are yours, so this is a draft for you to apply (or change) under your name, not a PR from me.
Patch: `docs/proposals/ci-postgres-e2e/ci-postgres-e2e.patch` (3 files, +81 −5). Apply from the repo root, then delete this folder in the same commit:

```bash
git apply docs/proposals/ci-postgres-e2e/ci-postgres-e2e.patch
```

## Why
The three bugs you found in #18/#19 were all at boundaries our CI never crossed:
- `pytest` only runs on SQLite. Postgres-only behaviour (NUMERIC scale, enums, constraints) is only tested by the migration round trip.
- The docker job uploads a fake PDF, but no real report ever goes through extraction → DB → API on the real stack.

## What it adds
1. **`tests/conftest.py`:** if `TEST_DATABASE_URL` is set, `session_factory` uses that database, with a fresh schema per test (`drop_all` + `create_all`). Without it, nothing changes: SQLite in memory, as now.
2. **New job `backend-postgres`:** the full backend suite against a `postgres:18.6-alpine` service, the same image as compose. pytest-socket already allows localhost, so nothing else changes.
3. **New step in the `docker` job, "Extraction smoke test":** runs after the upload smoke test, on the running stack.
   - `scripts.ingest_corpus IRF` runs the real IRF PDF through SeaweedFS → `documents` → baseline → validation → `holdings`.
   - It then checks `GET /documents/{id}/holdings`: 23 rows, run `ok`, all `weight_basis = total`, BGP at FTD `0.1059`.
   - A second run must print `skipped`, which checks that reprocessing creates no duplicates.
4. **Cache glob fix (from Yusuf's review on #21):** `setup-uv` resolves `cache-dependency-glob` relative to its `working-directory`, so `backend/uv.lock` becomes `backend/backend/uv.lock`. main's CI log already warns "No file matched … The cache will never get invalidated". The patch changes it to `uv.lock` in the existing `backend` job, in `evaluation.yml`, and in the two new `setup-uv` steps.

## How I checked it (locally, OrbStack)
- **Postgres suite:** the full suite with `TEST_DATABASE_URL` pointing at `postgres:18.6-alpine` gives 318 passed, 1 skipped (the IRF fixture test). The tables were really created in Postgres.
- **Smoke step:** with `docker compose up postgres seaweedfs api`, the step script passed: IRF saved as document 1, 23 rows, ok, API checks pass, second run skipped.
- **Your #18 scenario on the real stack:**
  - With SeaweedFS stopped, `ingest_corpus ICH` exits 1 and the `documents` count doesn't change.
  - After starting SeaweedFS again, the retry saves (82 rows, ok).
- **YAML:** parses and `check-yaml` passes. I couldn't run actionlint here.

## Before merging
- **The smoke step needs `scripts/ingest_corpus.py`, which is in #18.** Apply this after #18 is merged, or the step fails.
- **Add `backend-postgres` to the required status checks on `main`.** That's a branch protection setting; I can't see it.
- **Timing:** the new job takes about 30 s plus the Postgres service start. The smoke step adds `uv sync` plus a few seconds to the docker job.
