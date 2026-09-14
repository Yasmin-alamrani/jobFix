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


app = FastAPI(title="Resume Analyzer", version="0.1.0", lifespan=lifespan)

# Single-user mode runs the Vite dev server against this API on 8000. Any local
# port is accepted, not just 5173: Vite quietly moves to 5174, 5175... when 5173
# is taken, and a hard-coded port turns that into "Cannot reach the API" while
# the backend is running fine. Local only either way -- no remote origin matches.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
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
        "model": settings.gemini_model,
        "gemini_key_configured": bool(settings.gemini_api_key),
    }
