"""FastAPI entry point. Run locally with `uv run uvicorn app.main:app --reload`."""

from fastapi import FastAPI

from app import documents

app = FastAPI(title="Fund Research & Exposure Platform")
app.include_router(documents.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe for Docker, CI smoke tests and the deploy check."""
    return {"status": "ok"}
