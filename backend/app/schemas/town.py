"""Response models for tropical-cyclone locations."""

from pydantic import BaseModel, ConfigDict


class TownGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    town_group: str
    coastal_order: float | None


class TownRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    state: str
    lat: float
    lon: float
    is_major: bool
    is_island: bool
    groups: list[TownGroupRead] = []
