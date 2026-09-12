"""ORM models.

Every model module is imported here, which is load-bearing in two ways:
Alembic autogenerate only sees tables registered on ``Base.metadata``, and
SQLAlchemy resolves the string-named relationships between modules at
configure time. Import this package, not individual modules, when you need the
mappings complete.
"""

from app.models.best_track import BestTrackObservation
from app.models.codes import CodeDomain, CodeValue
from app.models.disturbance import Disturbance
from app.models.enums import (
    AreaKind,
    AreaType,
    DisturbanceType,
    FixSymbol,
    FixType,
    IngestKind,
    IngestStatus,
    MarineType,
    Outcome,
    Region,
    SummaryScope,
    TrackDataset,
    TrackType,
    WindType,
)
from app.models.gml import (
    Bulletin,
    BulletinArea,
    BulletinFix,
    BulletinTrack,
)
from app.models.ingest import IngestRun
from app.models.interpolation import InterpolatedPoint, InterpolationRun
from app.models.town import Town, TownGroupMembership
from app.models.verification import (
    ForecastAdviceDistance,
    ObservedTownImpact,
    ObservedWindDistance,
    VerificationPair,
    VerificationRun,
    VerificationSummary,
)

__all__ = [
    # Reference
    "CodeDomain",
    "CodeValue",
    "Town",
    "TownGroupMembership",
    "IngestRun",
    # Best track
    "Disturbance",
    "BestTrackObservation",
    # Interpolation
    "InterpolationRun",
    "InterpolatedPoint",
    # GML bulletins
    "Bulletin",
    "BulletinTrack",
    "BulletinFix",
    "BulletinArea",
    # Verification
    "VerificationRun",
    "ForecastAdviceDistance",
    "ObservedWindDistance",
    "ObservedTownImpact",
    "VerificationPair",
    "VerificationSummary",
    # Enums
    "AreaKind",
    "AreaType",
    "DisturbanceType",
    "FixSymbol",
    "FixType",
    "IngestKind",
    "IngestStatus",
    "MarineType",
    "Outcome",
    "Region",
    "SummaryScope",
    "TrackDataset",
    "TrackType",
    "WindType",
]
