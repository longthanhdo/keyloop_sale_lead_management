from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base


def _register_sqlite_pragmas(engine: Engine) -> None:
    """Enforce foreign key constraints on every SQLite connection (PostgreSQL parity)."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.close()


def create_db_engine(
    database_url: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_recycle: int = 1800,
) -> Engine:
    """Create a dialect-aware SQLAlchemy 2.0 engine."""
    if database_url.startswith("sqlite"):
        kwargs: dict[str, Any] = {
            "connect_args": {"check_same_thread": False},
            "future": True,
        }
        if database_url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        engine = create_engine(database_url, **kwargs)
        _register_sqlite_pragmas(engine)
        return engine

    return create_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=pool_recycle,
        future=True,
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def init_db(engine: Engine) -> None:
    """Ensure all ORM models are registered and create tables if missing."""
    import app.models.activity  # noqa: F401
    import app.models.lead  # noqa: F401

    Base.metadata.create_all(bind=engine)


class DatabaseManager:
    """Holds the active engine and session factory for the running application."""

    def __init__(self, settings: Settings | None = None) -> None:
        cfg = settings or get_settings()
        self.engine = create_db_engine(
            cfg.database_url,
            pool_size=cfg.db_pool_size,
            max_overflow=cfg.db_max_overflow,
            pool_recycle=cfg.db_pool_recycle,
        )
        self.session_factory = create_session_factory(self.engine)

    def get_session(self) -> Generator[Session, None, None]:
        session = self.session_factory()
        try:
            yield session
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()
