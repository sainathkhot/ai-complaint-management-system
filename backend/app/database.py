"""Database engine and session handling.

Postgres is the intended target (and what docker-compose brings up). A SQLite
fallback is wired in purely so the app still boots on a machine with no
database running — useful when recording a demo on a laptop. The ORM layer is
identical either way; only the URL changes.
"""

import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import Base

logger = logging.getLogger(__name__)

SQLITE_FALLBACK = "sqlite:///./aivoa_cms.db"


def _build_engine():
    url = settings.database_url
    try:
        engine = create_engine(url, pool_pre_ping=True, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Connected to database: %s", url.split("@")[-1])
        return engine
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not connect to %s (%s). Falling back to SQLite at %s. "
            "Start Postgres with `docker compose up -d db` for the intended setup.",
            url.split("@")[-1],
            type(exc).__name__,
            SQLITE_FALLBACK,
        )
        return create_engine(
            SQLITE_FALLBACK, connect_args={"check_same_thread": False}, future=True
        )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("Schema ready")


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """For use outside the request cycle (scripts, graph nodes)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
