"""Verification runs, contingency summaries and the 2x2 matrix."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import DbSession, PaginationDep
from app.models.disturbance import Disturbance
from app.models.enums import SummaryScope
from app.models.town import Town
from app.models.verification import (
    VerificationPair,
    VerificationRun,
    VerificationSummary,
)
from app.schemas.common import Page
from app.schemas.verification import (
    ContingencySummary,
    VerificationPairRead,
    VerificationRunRead,
)

router = APIRouter()


NO_RUNS_HINT = (
    "no verification run exists yet; load one with `python -m app.cli verification`"
)


def _resolve_run(db: DbSession, run_id: int | None) -> int:
    """Validate ``run_id``, or fall back to the most recent run.

    An empty database and a wrong run id are different problems, so they get
    different messages: asking for run 1 before anything is loaded should say
    how to load it, not just that run 1 is missing.
    """
    latest = db.execute(
        select(VerificationRun.id).order_by(VerificationRun.id.desc()).limit(1)
    ).scalar_one_or_none()
    if latest is None:
        raise HTTPException(status_code=404, detail=NO_RUNS_HINT)
    if run_id is None:
        return latest
    if db.get(VerificationRun, run_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"no verification run {run_id}; the latest is {latest}",
        )
    return run_id


@router.get("", response_model=list[VerificationRunRead])
def list_runs(db: DbSession) -> list[VerificationRunRead]:
    rows = db.execute(
        select(VerificationRun).order_by(VerificationRun.id.desc())
    ).scalars()
    return [VerificationRunRead.model_validate(r) for r in rows]


@router.get("/{run_id}/summary", response_model=list[ContingencySummary])
def get_summary(
    db: DbSession,
    run_id: int,
    scope: SummaryScope = SummaryScope.ALL,
    scope_key: Annotated[
        str | None, Query(description="Disturbance id or season, for a scoped row")
    ] = None,
) -> list[ContingencySummary]:
    """Contingency counts, with POD/FAR/CSI/bias and the 2x2 computed."""
    resolved = _resolve_run(db, run_id)
    query = select(VerificationSummary).where(
        VerificationSummary.run_id == resolved,
        VerificationSummary.scope == scope.value,
    )
    if scope_key is not None:
        query = query.where(VerificationSummary.scope_key == scope_key)
    rows = db.execute(query.order_by(VerificationSummary.scope_key)).scalars()
    out = [ContingencySummary.model_validate(r) for r in rows]
    if not out:
        raise HTTPException(
            status_code=404,
            detail=f"no {scope.value} summary for run {resolved}",
        )
    return out


@router.get("/{run_id}/pairs", response_model=Page[VerificationPairRead])
def list_pairs(
    db: DbSession,
    run_id: int,
    page: PaginationDep,
    disturbance_id: str | None = None,
    outcome: str | None = None,
) -> Page[VerificationPairRead]:
    """The individual forecast/observed pairs behind the counts."""
    resolved = _resolve_run(db, run_id)
    filters = [VerificationPair.run_id == resolved]
    if disturbance_id:
        filters.append(Disturbance.disturbance_id == disturbance_id)
    if outcome:
        filters.append(VerificationPair.outcome == outcome)

    base = (
        select(VerificationPair, Disturbance.disturbance_id, Town.name, Town.state)
        .join(Disturbance, VerificationPair.disturbance_pk == Disturbance.id)
        .join(Town, VerificationPair.town_id == Town.id)
        .where(*filters)
    )
    total = db.execute(
        select(func.count())
        .select_from(VerificationPair)
        .join(Disturbance, VerificationPair.disturbance_pk == Disturbance.id)
        .join(Town, VerificationPair.town_id == Town.id)
        .where(*filters)
    ).scalar_one()

    rows = db.execute(
        base.order_by(VerificationPair.base_time, Town.name)
        .limit(page.limit)
        .offset(page.offset)
    ).all()

    items = []
    for pair, ident, town_name, town_state in rows:
        read = VerificationPairRead.model_validate(pair)
        read.disturbance_id = ident
        read.town_name = town_name
        read.town_state = town_state
        items.append(read)
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)
