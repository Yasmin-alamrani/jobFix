"""Database session and base.

Defaults to SQLite so the app runs with no external services; point
DATABASE_URL at Postgres for anything real. The schema is identical either way.
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_url = _settings.database_url
if _url.startswith("postgresql") and "DEV" not in _url:
    engine = create_engine(_url, pool_pre_ping=True)
else:
    engine = create_engine(_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import entities  # noqa: F401  -- register tables

    Base.metadata.create_all(bind=engine)
