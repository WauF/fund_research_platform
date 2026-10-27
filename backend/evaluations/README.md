# Evaluations (live calls)

Routine tests (`tests/`) must be repeatable: fixtures, recorded LLM outputs, fixed seeds, and
no internet (pytest-socket blocks it). Anything that calls a **real** LLM or market-data API goes
here instead.

- Write evaluations as pytest tests and mark each one `@pytest.mark.extraction` or
  `@pytest.mark.market_data`.
- Write results (accuracy, cost, failures, raw outputs) under `evaluations/results/`.
  That folder is git-ignored and uploaded as a workflow artifact.
- Never run on PRs. Run them by hand:
  - **Locally:** `uv run pytest evaluations --force-enable-socket -m extraction`
    (reads `LLM_API_KEY` / `LLM_MODEL` from your environment).
  - **GitHub:** Actions → *Evaluation* → *Run workflow*. Secrets come from the `evaluation`
    environment.
- Mind the agreed LLM cost limit (`docs/decisions/`) before running the whole suite.
