

from app.core.config import settings
from app.gen_cont_tables import (
    generate_all_tables_for_disturbance,
    generate_all_tables_for_disturbances,
    list_disturbance_ids_for_season,
)
from app.schemas.contigency import ContingencyRequest


def generate_tables(request: ContingencyRequest):
    if not request.disturbance_ids and not request.season:
        raise ValueError(
            "Provide at least one disturbance ID or a season."
        )
    if request.disturbance_ids:
        disturbance_ids = request.disturbance_ids
    else:
        disturbance_ids = list_disturbance_ids_for_season(request.season)

    if not disturbance_ids:
        raise ValueError("No disturbances found")

    output_dir = settings.DATA_DIR / "contingency_tables"

    if len(disturbance_ids) == 1:
        result = generate_all_tables_for_disturbance(
            disturbance_ids[0],
            output_dir=output_dir,
            x_hours=request.x_hours,
            y_hours=request.y_hours,
            coastal_buffer_km=request.coastal_buffer_km,
            relevance_km=request.relevance_km,
            state=request.state,
            season=request.season,
        )
        stats = result["stats"]
    else:
        result = generate_all_tables_for_disturbances(
            disturbance_ids,
            output_dir=output_dir,
            x_hours=request.x_hours,
            y_hours=request.y_hours,
            coastal_buffer_km=request.coastal_buffer_km,
            relevance_km=request.relevance_km,
            state=request.state,
            season=request.season,
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

    files = {
        path.name: str(path)
        for path in output_dir.glob("*.csv")
        if path.is_file()
    }

    return {
        "status": "success",
        "disturbance_ids": disturbance_ids,
        "stats": api_stats,
        "files": files,
    }

