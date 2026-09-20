"""Tropical-cyclone locations."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession
from app.models.town import Town, TownGroupMembership
from app.schemas.town import TownRead

router = APIRouter()


@router.get("", response_model=list[TownRead])
def list_towns(
    db: DbSession,
    state: Annotated[str | None, Query(description="NSW, NT, QLD or WA")] = None,
    town_group: Annotated[
        str | None, Query(description="e.g. qld_towns, wa_minor_northern_towns")
    ] = None,
    major_only: bool = False,
) -> list[TownRead]:
    """All 466 locations.

    Intentionally unpaginated: the whole set is about 60 KB, and both map
    viewers want it in one request to draw the Towns layer at startup.
    """
    query = (
        select(Town).options(selectinload(Town.groups)).order_by(Town.state, Town.name)
    )
    if state:
        query = query.where(Town.state == state)
    if major_only:
        query = query.where(Town.is_major.is_(True))
    if town_group:
        query = query.where(
            Town.id.in_(
                select(TownGroupMembership.town_id).where(
                    TownGroupMembership.town_group == town_group
                )
            )
        )
    return [TownRead.model_validate(t) for t in db.execute(query).scalars()]


@router.get("/groups", response_model=dict[str, int])
def list_town_groups(db: DbSession) -> dict[str, int]:
    """Town group -> member count.

    A location can belong to more than one group, so these sum to more than
    the number of towns: the sheet lists six QLD places in two groups each.
    """
    from sqlalchemy import func

    rows = db.execute(
        select(TownGroupMembership.town_group, func.count())
        .group_by(TownGroupMembership.town_group)
        .order_by(TownGroupMembership.town_group)
    ).all()
    return dict(rows)


@router.get("/{town_id}", response_model=TownRead)
def get_town(db: DbSession, town_id: int) -> TownRead:
    row = db.execute(
        select(Town).options(selectinload(Town.groups)).where(Town.id == town_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no town {town_id}")
    return TownRead.model_validate(row)
