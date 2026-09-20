"""Shared response envelopes."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """A slice of a collection, with the total so a client can paginate."""

    items: list[T]
    total: int
    limit: int
    offset: int


class BBox(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    @classmethod
    def from_row(cls, row: object, prefix: str = "bbox_") -> "BBox | None":
        """Build from an object carrying ``bbox_min_lon`` and friends."""
        values = {
            field: getattr(row, f"{prefix}{field}", None)
            for field in ("min_lon", "min_lat", "max_lon", "max_lat")
        }
        if any(v is None for v in values.values()):
            return None
        return cls(**values)


class CodedValue(BaseModel):
    """A BoM numeric code alongside its label from ``code_value``."""

    code: str
    description: str | None = None
