from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI()

class ContingencyRequest(BaseModel):
    disturbance_ids: list[str] = Field(default_factory=list)
    season: str | None = None
    state: str | None = None
    x_hours: int = Field(default=0, ge=0)
    y_hours: int = Field(default=24, gt=0)
    coastal_buffer_km: float = Field(default=20.0, gt=0)
    relevance_km: float = Field(default=300.0, gt=0)

class ContigencyStats(BaseModel):
    hit: int
    false_alarm: int
    miss: int
    correct_negative: int

class ContigencyResponse(BaseModel):
    status:str
    disturbance_ids: list[str]
    stats: ContigencyStats
    file: dict[str, str] = Field(default_factory=dict)
