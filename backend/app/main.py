"""FastAPI entrypoint."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import export, jobs, resumes, scout, tailor
from app.core.config import get_settings
from app.models.db import init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Resume Checker & Job Hunt", version="0.1.0", lifespan=lifespan)

# Single-user mode runs the Vite dev server on 5173 against this API on 8000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The browser downloads exports with fetch, and needs to read the filename.
    expose_headers=["Content-Disposition"],
)

app.include_router(resumes.router)
app.include_router(scout.router)
app.include_router(tailor.router)
app.include_router(export.router)
app.include_router(jobs.router)


@app.get("/api/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "model": settings.claude_model,
        "claude_key_configured": bool(settings.anthropic_api_key),
        "openrouter_key_configured": bool(settings.openrouter_api_key),
    }
