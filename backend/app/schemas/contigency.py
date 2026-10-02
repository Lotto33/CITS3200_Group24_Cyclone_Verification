from pydantic import BaseModel, Field, field_validator

VALID_BASE_TIME_HOURS = (0, 6, 12, 18)

class ContingencyRequest(BaseModel):
    disturbance_ids: list[str] = Field(default_factory=list)
    season: str | None = None
    state: str | None = None
    x_hours: int = Field(default=0, ge=0)
    y_hours: int = Field(default=24, gt=0)
    base_time_hours: list[int] = Field(
        default_factory=lambda: list(VALID_BASE_TIME_HOURS)
    )
    coastal_buffer_km: float = Field(default=20.0, gt=0)
    relevance_km: float = Field(default=300.0, gt=0)

    @field_validator("base_time_hours")
    @classmethod
    def validate_base_time_hours(cls, values: list[int]) -> list[int]:
        if not values:
            raise ValueError("Select at least one base time.")
        if len(values) != len(set(values)):
            raise ValueError("Base-time hours must not contain duplicates.")
        invalid = sorted(set(values) - set(VALID_BASE_TIME_HOURS))
        if invalid:
            raise ValueError(
                f"Invalid base-time hour(s) {invalid}; "
                f"choose from {list(VALID_BASE_TIME_HOURS)}."
            )
        return sorted(values)

class ContingencyStats(BaseModel):
    hit: int
    false_alarm: int
    miss: int
    correct_negative: int
    total: int

class ContingencyResponse(BaseModel):
    status: str
    disturbance_ids: list[str]
    stats: ContingencyStats
    files: dict[str, str] = Field(default_factory=dict)
