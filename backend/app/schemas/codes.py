"""Response models for the BoM code lookup tables."""

from pydantic import BaseModel, ConfigDict


class CodeValueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    description: str
    sort_order: int


class CodeDomainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    label: str | None
    description: str | None
    values: list[CodeValueRead] = []
