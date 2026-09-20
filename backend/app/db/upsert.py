"""Dialect-dispatching bulk upsert.

Every loader writes through :func:`upsert_many` so that re-running an ingest
over unchanged input is a no-op on row count. SQLite and PostgreSQL both
support ``INSERT ... ON CONFLICT`` with the same API shape, which is the main
reason this pair of backends is comfortable to support together.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

# SQLite's compile-time bound-parameter ceiling is 32766 on modern builds (999
# on very old ones). A fixed row-based chunk size is a trap: 500 rows of the
# 79-column best_track_observation is ~39,500 parameters and fails outright.
# Derive the chunk size from the column count instead. The conservative budget
# leaves room for the ON CONFLICT ... SET clause, which re-binds nothing but
# still counts toward statement complexity.
SQLITE_PARAM_BUDGET = 20_000

# PostgreSQL's limit is 65535; keep chunks large but bounded so a single
# statement does not balloon in memory.
DEFAULT_PARAM_BUDGET = 60_000

MAX_CHUNK_ROWS = 5_000


def chunk_size_for(dialect_name: str, column_count: int) -> int:
    """Largest safe number of rows per INSERT for ``column_count`` columns."""
    if column_count <= 0:
        raise ValueError("column_count must be positive")
    budget = SQLITE_PARAM_BUDGET if dialect_name == "sqlite" else DEFAULT_PARAM_BUDGET
    return max(1, min(MAX_CHUNK_ROWS, budget // column_count))


def upsert_many(
    session: Session,
    model: Any,
    rows: Sequence[dict[str, Any]],
    *,
    conflict_cols: Sequence[str],
    update_cols: Sequence[str] | None = None,
) -> int:
    """Insert ``rows``, updating on conflict against ``conflict_cols``.

    Returns the number of rows sent. ``update_cols`` defaults to every mapped
    column present in the payload except the conflict columns and ``id``.
    Pass an empty sequence for insert-or-ignore semantics.
    """
    if not rows:
        return 0

    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        insert = sqlite_insert
    elif dialect == "postgresql":
        insert = pg_insert
    else:  # pragma: no cover - guarded so a silent partial write is impossible
        raise NotImplementedError(f"upsert_many does not support dialect {dialect!r}")

    table = model.__table__
    payload_cols = [c for c in table.columns.keys() if c in rows[0]]
    if update_cols is None:
        update_cols = [
            c for c in payload_cols if c not in set(conflict_cols) and c != "id"
        ]

    size = chunk_size_for(dialect, max(1, len(payload_cols)))
    sent = 0
    for start in range(0, len(rows), size):
        batch = rows[start : start + size]
        stmt = insert(table).values(batch)
        if update_cols:
            stmt = stmt.on_conflict_do_update(
                index_elements=list(conflict_cols),
                set_={c: getattr(stmt.excluded, c) for c in update_cols},
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=list(conflict_cols))
        session.execute(stmt)
        sent += len(batch)
    return sent
