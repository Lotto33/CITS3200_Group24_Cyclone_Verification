import pandas as pd
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.gen_cont_tables import (
    derive_season,
    generate_all_tables_for_disturbance,
    generate_all_tables_for_disturbances,
)
from app.models.disturbance import Disturbance
from app.models.enums import TrackDataset
from app.schemas.contigency import ContingencyRequest
from app.services.loaders.interpolation import latest_run_id
from app.services.loaders.verification import (
    _db_forecasts,
    _db_locations,
    _db_tracks,
)


def generate_tables(request: ContingencyRequest):
    if not request.disturbance_ids and not request.season:
        raise ValueError("Provide at least one disturbance ID or a season.")
    with SessionLocal() as session:
        locations = _db_locations(session)
        forecasts_by_pk = _db_forecasts(session)

        disturbances_by_id = {row.disturbance_id: row for row in session.execute(select(Disturbance)).scalars()}

        if request.disturbance_ids:
            disturbance_ids = request.disturbance_ids
        else:
            disturbance_ids = sorted(
                ident
                for ident, disturbance in disturbances_by_id.items()
                if any(derive_season(timestamp) == request.season for timestamp in forecasts_by_pk.get(disturbance.id, {}))
            )

        if not disturbance_ids:
            raise ValueError("No disturbances found")

        if locations.empty:
            raise ValueError("No database towns available")

        if request.state is not None and not locations["state"].eq(request.state).any():
            raise ValueError(f"No database towns for state {request.state!r}")

        for ident in disturbance_ids:
            if ident not in disturbances_by_id:
                raise ValueError(f"Unknown disturbance ID: {ident}")

            disturbance = disturbances_by_id[ident]

            if not forecasts_by_pk.get(disturbance.id):
                raise ValueError(f"No database forecasts available for {ident}")

        run_id = latest_run_id(
            session,
            dataset=TrackDataset.BOM_BEST_TRACK,
        )

        if run_id is None:
            raise ValueError("No BOM best-track interpolation run available; run python -m app.cli interpolate")

        tracks_by_pk = _db_tracks(session, run_id)
        forecasts_by_id = {}
        tracks_by_id = {}

        for ident in disturbance_ids:
            disturbance = disturbances_by_id[ident]

            forecasts_by_id[ident] = forecasts_by_pk[disturbance.id]

            track = tracks_by_pk.get(disturbance.id)

            if track is None:
                if not disturbance.has_best_track and disturbance.observation_count == 0:
                    track = pd.DataFrame(columns=["LAT", "LON"])
                else:
                    raise ValueError(f"{ident}: no interpolated points in run {run_id}")

            tracks_by_id[ident] = track

        print(f"[verification] Using database interpolation run {run_id}")

    output_dir = settings.DATA_DIR / "contingency_tables"

    if len(disturbance_ids) == 1:
        result = generate_all_tables_for_disturbance(
            disturbance_ids[0],
            output_dir=output_dir,
            x_hours=request.x_hours,
            y_hours=request.y_hours,
            forecast_level=request.forecast_level,
            coastal_buffer_km=request.coastal_buffer_km,
            relevance_km=request.relevance_km,
            state=request.state,
            season=request.season,
            base_time_hours=request.base_time_hours,
            locations=locations,
            forecasts=forecasts_by_id[disturbance_ids[0]],
            track=tracks_by_id[disturbance_ids[0]],
        )
        stats = result["stats"]
    else:
        result = generate_all_tables_for_disturbances(
            disturbance_ids,
            output_dir=output_dir,
            x_hours=request.x_hours,
            y_hours=request.y_hours,
            forecast_level=request.forecast_level,
            coastal_buffer_km=request.coastal_buffer_km,
            relevance_km=request.relevance_km,
            state=request.state,
            season=request.season,
            base_time_hours=request.base_time_hours,
            locations=locations,
            forecasts_by_id=forecasts_by_id,
            tracks_by_id=tracks_by_id,
        )
        stats = result["combined_stats"]

    # gen_cont_tables.py uses human-readable keys, while the API schema uses
    # Python-friendly names. Convert them at the service boundary.
    api_stats = {
        "hit": stats["hit"],
        "false_alarm": stats["false alarm"],
        "miss": stats["miss"],
        "correct_negative": stats["correct negative"],
        "total": stats["total"],
    }

    files = {path.name: str(path) for path in result.get("files", [])}

    return {
        "status": "success",
        "disturbance_ids": disturbance_ids,
        "stats": api_stats,
        "files": files,
    }
