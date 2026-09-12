"""Database engine and session plumbing.

We use *synchronous* SQLAlchemy. FastAPI runs non-async path operations in a
worker thread pool, so a blocking query here does not block the event loop.
For this workload -- a few indexed reads per request -- that is simpler to
reason about than async SQLAlchemy and costs nothing measurable.
"""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,  # survives Postgres restarts and failovers
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
