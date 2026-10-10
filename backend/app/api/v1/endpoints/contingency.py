
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import settings
from app.schemas.contigency import ContingencyRequest
from app.services import contigency_service as contingency_service
from app.services import upload_jobs

router = APIRouter()


@router.post("/", status_code=202)
def generate_contingency_tables(request: ContingencyRequest):
    if not request.disturbance_ids and not request.season:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one disturbance ID or a season.",
        )

    try:
        job = upload_jobs.start_upload_job(
            "Contingency tables",
            lambda: contingency_service.generate_tables(request),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"job_id": job.job_id, "status": job.status}


@router.get("/jobs/{job_id}")
def contingency_job_status(
    job_id: str,
    since: Annotated[int, Query(ge=0)] = 0,
):
    job = upload_jobs.get_upload_job(job_id, since)
    if job is None:
        raise HTTPException(
            status_code=404, detail="Contingency job not found or expired"
        )
    return job


@router.get("/files/{filename}")
def download_contingency_file(filename: str):
    output_dir = (settings.DATA_DIR / "contingency_tables").resolve()
    path = (output_dir / filename).resolve()
    if path.parent != output_dir or path.suffix.lower() != ".csv" or not path.is_file():
        raise HTTPException(status_code=404, detail="CSV file not found")
    return FileResponse(path, filename=path.name, media_type="text/csv")