from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.core.config import settings
from app.services import dataset_service, upload_jobs

router = APIRouter()

@router.post("/")
def create_dataset():
    try:
        return dataset_service.process_gml_dataset(
            input_dir=settings.GML_DIR,
            data_dir=settings.DATA_DIR,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/status")
def dataset_status():
    return dataset_service.get_status(settings.DATA_DIR)


@router.post("/upload")
def upload_gml_archive(file: Annotated[UploadFile, File()]):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=400,
            detail="Upload a .zip archive containing *_GMLs folders",
        )
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        suffix=".zip", dir=settings.UPLOAD_DIR, delete=False
    ) as output:
        archive_path = Path(output.name)
        output.write(file.file.read())

    def process() -> dict:
        try:
            return dataset_service.process_uploaded_gml_archive(
                archive_path, settings.DATA_DIR
            )
        finally:
            archive_path.unlink(missing_ok=True)

    try:
        job = upload_jobs.start_upload_job("GML archive", process)
        return {"job_id": job.job_id, "status": job.status}
    except Exception:
        archive_path.unlink(missing_ok=True)
        raise


@router.post("/interpolate-best-track")
def interpolate_best_track():
    try:
        return dataset_service.interpolate_and_process_dataset(settings.DATA_DIR)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/upload-best-track")
def upload_best_track(file: Annotated[UploadFile, File()]):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a best-track .csv file")
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        suffix=".csv", dir=settings.UPLOAD_DIR, delete=False
    ) as output:
        upload_path = Path(output.name)
        output.write(file.file.read())

    def process() -> dict:
        try:
            return dataset_service.process_uploaded_best_track(
                upload_path, settings.DATA_DIR
            )
        finally:
            upload_path.unlink(missing_ok=True)

    try:
        job = upload_jobs.start_upload_job("Best-track CSV", process)
        return {"job_id": job.job_id, "status": job.status}
    except Exception:
        upload_path.unlink(missing_ok=True)
        raise


@router.get("/jobs/{job_id}")
def upload_job_status(
    job_id: str,
    since: Annotated[int, Query(ge=0)] = 0,
):
    job = upload_jobs.get_upload_job(job_id, since)
    if job is None:
        raise HTTPException(status_code=404, detail="Upload job not found or expired")
    return job
