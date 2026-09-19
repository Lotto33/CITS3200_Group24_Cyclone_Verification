from fastapi import APIRouter, HTTPException

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
