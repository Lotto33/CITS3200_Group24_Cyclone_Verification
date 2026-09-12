"""Database engine and session factory.

The SQLite ``connect`` hook is required, not an optimisation: SQLite disables
foreign-key enforcement by default, so without ``PRAGMA foreign_keys=ON`` every
``ForeignKey`` and ``ON DELETE CASCADE`` in ``app.models`` would be decorative
and integrity bugs would only surface on PostgreSQL.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def create_db_engine(url: str | None = None, *, echo: bool | None = None) -> Engine:
    """Build an Engine for ``url`` (default: ``settings.DATABASE_URL``)."""
    url = url or settings.DATABASE_URL
    connect_args = {"check_same_thread": False} if _is_sqlite(url) else {}
    return create_engine(
        url,
        echo=settings.SQL_ECHO if echo is None else echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Enable FK enforcement and WAL on every new SQLite connection."""
    # Identify SQLite without importing the driver: only sqlite3 connections
    # expose `isolation_level` alongside a usable cursor for PRAGMAs.
    module = type(dbapi_connection).__module__ or ""
    if "sqlite3" not in module:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
    finally:
        cursor.close()


engine = create_db_engine()

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)
