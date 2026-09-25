"""Response models for the verification products.

The 2x2 matrix and every skill score are **computed**, never stored: they are
functions of the same four counts, and a stored copy is a second source of
truth that can drift.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field


class VerificationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    label: str | None
    interpolation_run_id: int | None
    forecast_source: str | None
    truth_dataset: str | None
    town_count: int | None
    disturbance_count: int | None
    code_version: str | None
    notes: str | None


class ContingencyCell(BaseModel):
    observed_yes: int
    observed_no: int
    total: int


class ContingencyMatrix(BaseModel):
    """The 2x2 table as ``contingency_matrix.csv`` renders it."""

    forecast_yes: ContingencyCell
    forecast_no: ContingencyCell
    total: ContingencyCell


class ContingencySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scope: str
    scope_key: str | None
    hit: int
    false_alarm: int
    miss: int
    correct_negative: int
    total: int

    @computed_field
    @property
    def pod(self) -> float | None:
        """Probability of detection (hit rate): hits / observed yes."""
        denominator = self.hit + self.miss
        return self.hit / denominator if denominator else None

    @computed_field
    @property
    def far(self) -> float | None:
        """False alarm ratio: false alarms / forecast yes."""
        denominator = self.hit + self.false_alarm
        return self.false_alarm / denominator if denominator else None

    @computed_field
    @property
    def csi(self) -> float | None:
        """Critical success index (threat score)."""
        denominator = self.hit + self.false_alarm + self.miss
        return self.hit / denominator if denominator else None

    @computed_field
    @property
    def bias(self) -> float | None:
        """Frequency bias: forecast yes / observed yes."""
        denominator = self.hit + self.miss
        return (self.hit + self.false_alarm) / denominator if denominator else None

    @computed_field
    @property
    def matrix(self) -> ContingencyMatrix:
        return ContingencyMatrix(
            forecast_yes=ContingencyCell(
                observed_yes=self.hit,
                observed_no=self.false_alarm,
                total=self.hit + self.false_alarm,
            ),
            forecast_no=ContingencyCell(
                observed_yes=self.miss,
                observed_no=self.correct_negative,
                total=self.miss + self.correct_negative,
            ),
            total=ContingencyCell(
                observed_yes=self.hit + self.miss,
                observed_no=self.false_alarm + self.correct_negative,
                total=self.total,
            ),
        )


class VerificationPairRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_time: datetime
    season: str | None
    forecast: bool
    observed: bool
    outcome: str
    town_name: str | None = None
    town_state: str | None = None
    disturbance_id: str | None = None
