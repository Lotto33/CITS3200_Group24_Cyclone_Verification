from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import settings
from app.services import dataset_service

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
def upload_gml_archive(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip archive containing *_GMLs folders")
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = settings.UPLOAD_DIR / file.filename
    with archive_path.open("wb") as output:
        output.write(file.file.read())
    try:
        return dataset_service.process_uploaded_gml_archive(archive_path, settings.DATA_DIR)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        archive_path.unlink(missing_ok=True)


@router.post("/interpolate-best-track")
def interpolate_best_track():
    try:
        return dataset_service.interpolate_and_process_dataset(settings.DATA_DIR)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/upload-best-track")
def upload_best_track(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a best-track .csv file")
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    upload_path = settings.UPLOAD_DIR / file.filename
    with upload_path.open("wb") as output:
        output.write(file.file.read())
    try:
        return dataset_service.process_uploaded_best_track(upload_path, settings.DATA_DIR)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        upload_path.unlink(missing_ok=True)
