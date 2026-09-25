from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from app.core.config import settings
from app.schemas.contigency import (
    ContingencyRequest,
    ContingencyResponse,
)
from app.services import contigency_service as contingency_service
router = APIRouter()


@router.post("/", response_model=ContingencyResponse)
def generate_contingency_tables(request: ContingencyRequest):
    try:
        return contingency_service.generate_tables(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/files/{filename}")
def download_contingency_file(filename: str):
    output_dir = (settings.DATA_DIR / "contingency_tables").resolve()
    path = (output_dir / filename).resolve()
    if path.parent != output_dir or path.suffix.lower() != ".csv" or not path.is_file():
        raise HTTPException(status_code=404, detail="CSV file not found")
    return FileResponse(path, filename=path.name, media_type="text/csv")