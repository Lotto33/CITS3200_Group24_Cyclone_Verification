"""Shared FastAPI dependencies."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.db.session import SessionLocal

MAX_PAGE_LIMIT = 500


def get_db() -> Iterator[Session]:
    """Yield a request-scoped Session.

    Deliberately does not commit: every route here is read-only, and an
    implicit commit would hide write bugs in whatever is added later.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


PaginationDep = Annotated[Pagination, Depends(pagination)]
