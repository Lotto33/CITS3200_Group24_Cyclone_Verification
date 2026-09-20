"""Disturbances, best track and interpolated track."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, PaginationDep
from app.models.best_track import BestTrackObservation
from app.models.disturbance import Disturbance
from app.models.enums import TrackDataset
from app.models.gml import Bulletin, BulletinArea, BulletinFix, BulletinTrack
from app.models.interpolation import InterpolatedPoint, InterpolationRun
from app.schemas.common import BBox, Page
from app.schemas.cyclone import (
    BestTrackObservationFull,
    BestTrackPoint,
    DisturbanceDetail,
    DisturbanceSummary,
    InterpolatedTrackPoint,
)
from app.schemas.gml import BulletinSummary
from app.services.loaders.codes_seed import CODE_COLUMN_BINDINGS, describe

router = APIRouter()


def _get_disturbance(db: DbSession, disturbance_id: str) -> Disturbance:
    row = db.execute(
        select(Disturbance).where(Disturbance.disturbance_id == disturbance_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no disturbance {disturbance_id}")
    return row


@router.get("", response_model=Page[DisturbanceSummary])
def list_disturbances(
    db: DbSession,
    page: PaginationDep,
    season: Annotated[str | None, Query(description="e.g. 2016-17")] = None,
    region: Annotated[str | None, Query(description="NT, QLD or WA")] = None,
    has_best_track: bool | None = None,
    has_bulletins: bool | None = None,
    has_watch_or_warning: bool | None = None,
    include_test: Annotated[
        bool, Query(description="Include BoM test products (97U/98U/99U, TEST-*)")
    ] = False,
) -> Page[DisturbanceSummary]:
    """List disturbances. Test products are excluded unless asked for."""
    filters = []
    if season:
        filters.append(Disturbance.season == season)
    if region:
        filters.append(Disturbance.region == region)
    if has_best_track is not None:
        filters.append(Disturbance.has_best_track.is_(has_best_track))
    if has_bulletins is not None:
        filters.append(
            Disturbance.bulletin_count > 0
            if has_bulletins
            else Disturbance.bulletin_count == 0
        )
    if has_watch_or_warning is not None:
        condition = Disturbance.has_watch | Disturbance.has_warning
        filters.append(condition if has_watch_or_warning else ~condition)
    if not include_test:
        filters.append(Disturbance.is_test.is_(False))

    total = db.execute(
        select(func.count()).select_from(Disturbance).where(*filters)
    ).scalar_one()
    rows = db.execute(
        select(Disturbance)
        .where(*filters)
        .order_by(Disturbance.disturbance_id)
        .limit(page.limit)
        .offset(page.offset)
    ).scalars()
    return Page(
        items=[DisturbanceSummary.model_validate(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{disturbance_id}", response_model=DisturbanceDetail)
def get_disturbance(db: DbSession, disturbance_id: str) -> DisturbanceDetail:
    row = _get_disturbance(db, disturbance_id)
    datasets = db.execute(
        select(BestTrackObservation.dataset)
        .where(BestTrackObservation.disturbance_pk == row.id)
        .distinct()
    ).scalars()
    detail = DisturbanceDetail.model_validate(row)
    detail.datasets = sorted(datasets)
    detail.type_description = describe(db, "type", row.type_code)
    return detail


@router.get("/{disturbance_id}/best-track", response_model=list[BestTrackPoint])
def get_best_track(
    db: DbSession,
    disturbance_id: str,
    dataset: TrackDataset = TrackDataset.BOM_BEST_TRACK,
) -> list[BestTrackPoint]:
    """The post-event reanalysed track, as the plottable subset."""
    row = _get_disturbance(db, disturbance_id)
    points = db.execute(
        select(BestTrackObservation)
        .where(
            BestTrackObservation.disturbance_pk == row.id,
            BestTrackObservation.dataset == dataset.value,
        )
        .order_by(BestTrackObservation.tm)
    ).scalars()
    return [BestTrackPoint.model_validate(p) for p in points]


@router.get(
    "/{disturbance_id}/observations/{tm}",
    response_model=BestTrackObservationFull,
)
def get_observation(
    db: DbSession,
    disturbance_id: str,
    tm: datetime,
    dataset: TrackDataset = TrackDataset.BOM_BEST_TRACK,
) -> BestTrackObservationFull:
    """Every BoM field for one observation, with code labels resolved."""
    row = _get_disturbance(db, disturbance_id)
    observation = db.execute(
        select(BestTrackObservation).where(
            BestTrackObservation.disturbance_pk == row.id,
            BestTrackObservation.dataset == dataset.value,
            BestTrackObservation.tm == tm,
        )
    ).scalar_one_or_none()
    if observation is None:
        raise HTTPException(
            status_code=404, detail=f"no observation at {tm.isoformat()}"
        )

    full = BestTrackObservationFull.model_validate(observation)
    labels = {}
    for attribute, domain in CODE_COLUMN_BINDINGS.items():
        value = getattr(observation, attribute, None)
        label = describe(db, domain, value)
        if label:
            labels[attribute] = label
    full.code_labels = labels
    return full


@router.get(
    "/{disturbance_id}/interpolated-track",
    response_model=list[InterpolatedTrackPoint],
)
def get_interpolated_track(
    db: DbSession,
    disturbance_id: str,
    run_id: Annotated[
        int | None, Query(description="Defaults to the most recent run")
    ] = None,
) -> list[InterpolatedTrackPoint]:
    row = _get_disturbance(db, disturbance_id)
    if run_id is None:
        run_id = db.execute(
            select(InterpolationRun.id).order_by(InterpolationRun.id.desc()).limit(1)
        ).scalar_one_or_none()
        if run_id is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "no interpolation run exists; create one with "
                    "`python -m app.cli interpolate`"
                ),
            )
    points = db.execute(
        select(InterpolatedPoint)
        .where(
            InterpolatedPoint.run_id == run_id,
            InterpolatedPoint.disturbance_pk == row.id,
        )
        .order_by(InterpolatedPoint.tm)
    ).scalars()
    return [InterpolatedTrackPoint.model_validate(p) for p in points]


@router.get("/{disturbance_id}/bulletins", response_model=list[BulletinSummary])
def list_bulletins(
    db: DbSession,
    disturbance_id: str,
) -> list[BulletinSummary]:
    """Bulletin metadata only.

    Deliberately carries no geometry: this cyclone's areas can run to
    thousands of polygons. Use ``/bulletins/{id}`` or
    ``/bulletins/{id}/geojson`` for one bulletin's shapes.
    """
    row = _get_disturbance(db, disturbance_id)
    counts = _child_counts(db, row.id)
    rows = db.execute(
        select(Bulletin)
        .where(Bulletin.disturbance_pk == row.id)
        .options(selectinload(Bulletin.disturbance))
        .order_by(Bulletin.fcast_time, Bulletin.issue_time)
    ).scalars()

    out = []
    for bulletin in rows:
        summary = BulletinSummary.model_validate(bulletin)
        summary.disturbance_id = disturbance_id
        summary.bbox = BBox.from_row(bulletin)
        tracks, fixes, areas, vertices = counts.get(bulletin.id, (0, 0, 0, 0))
        summary.track_count = tracks
        summary.fix_count = fixes
        summary.area_count = areas
        summary.vertex_count = vertices
        out.append(summary)
    return out


def _child_counts(
    db: DbSession, disturbance_pk: int
) -> dict[int, tuple[int, int, int, int]]:
    """Per-bulletin child counts, gathered in three queries rather than N."""
    ids = select(Bulletin.id).where(Bulletin.disturbance_pk == disturbance_pk)

    tracks = dict(
        db.execute(
            select(BulletinTrack.bulletin_id, func.count())
            .where(BulletinTrack.bulletin_id.in_(ids))
            .group_by(BulletinTrack.bulletin_id)
        ).all()
    )
    fixes = dict(
        db.execute(
            select(BulletinFix.bulletin_id, func.count())
            .where(BulletinFix.bulletin_id.in_(ids))
            .group_by(BulletinFix.bulletin_id)
        ).all()
    )
    areas = {
        bulletin_id: (count, vertices or 0)
        for bulletin_id, count, vertices in db.execute(
            select(
                BulletinArea.bulletin_id,
                func.count(),
                func.sum(BulletinArea.vertex_count),
            )
            .where(BulletinArea.bulletin_id.in_(ids))
            .group_by(BulletinArea.bulletin_id)
        ).all()
    }
    keys = set(tracks) | set(fixes) | set(areas)
    return {
        key: (
            tracks.get(key, 0),
            fixes.get(key, 0),
            areas.get(key, (0, 0))[0],
            areas.get(key, (0, 0))[1],
        )
        for key in keys
    }
