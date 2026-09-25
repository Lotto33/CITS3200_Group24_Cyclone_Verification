from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.gen_cont_tables import find_pre_cutoff_near_polygon_distances

router = APIRouter()


@router.post("/near-polygon-distances")
def near_polygon_distances():
    output = settings.DATA_DIR / "near_polygon_distances.csv"
    try:
        result = find_pre_cutoff_near_polygon_distances(output_csv=output)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "success",
        "rows": len(result),
        "file": str(output),
    }
