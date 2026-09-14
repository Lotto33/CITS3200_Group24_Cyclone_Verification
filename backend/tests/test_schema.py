"""Schema-level invariants that are easy to break and silent when broken."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.columns import UtcDateTime
from app.db.upsert import chunk_size_for
from app.models.best_track import BestTrackObservation
from app.models.codes import CodeValue
from app.models.disturbance import Disturbance
from app.models.enums import Outcome, TrackDataset
from app.models.gml import Bulletin, BulletinFix
from app.services.loaders.codes_seed import DOMAINS, TOTAL_CODE_VALUES

EXPECTED_TABLES = 19


def test_every_table_is_registered():
    import app.models  # noqa: F401

    assert len(Base.metadata.tables) == EXPECTED_TABLES


def test_every_constraint_is_named():
    """Unnamed constraints make SQLite batch migrations impossible.

    SQLite cannot ALTER a constraint, so Alembic recreates the whole table --
    and it can only recreate constraints it can name.
    """
    unnamed = [
        (table.name, type(constraint).__name__)
        for table in Base.metadata.sorted_tables
        for constraint in table.constraints
        if constraint.name is None
        and type(constraint).__name__ != "PrimaryKeyConstraint"
    ]
    assert not unnamed


def test_foreign_keys_are_enforced(db: Session):
    """SQLite disables FK enforcement by default.

    Without the PRAGMA in app.db.session every ForeignKey and ON DELETE
    CASCADE in the schema would be decorative, and integrity bugs would only
    appear on PostgreSQL.
    """
    assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_cascade_delete_removes_children(db: Session):
    disturbance = Disturbance(disturbance_id="AU209900_01U")
    db.add(disturbance)
    db.flush()
    bulletin = Bulletin(
        disturbance_pk=disturbance.id,
        region="NT",
        source_file="unit-test/one.gml",
    )
    db.add(bulletin)
    db.flush()
    db.add(BulletinFix(bulletin_id=bulletin.id, lon=130.0, lat=-12.0))
    db.flush()

    db.delete(disturbance)
    db.flush()
    assert db.execute(select(BulletinFix)).first() is None
    assert db.execute(select(Bulletin)).first() is None


def test_observation_natural_key_is_unique(db: Session):
    disturbance = Disturbance(disturbance_id="AU209900_02U")
    db.add(disturbance)
    db.flush()
    values = {
        "dataset": TrackDataset.BOM_BEST_TRACK.value,
        "disturbance_pk": disturbance.id,
        "tm": datetime(2020, 1, 1, tzinfo=UTC),
        "lat": -12.0,
        "lon": 130.0,
    }
    db.add(BestTrackObservation(**values))
    db.flush()
    db.add(BestTrackObservation(**values))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_the_two_datasets_can_share_a_time(db: Session):
    """The dataset discriminator is what lets BoM and OTCR coexist."""
    disturbance = Disturbance(disturbance_id="AU209900_03U")
    db.add(disturbance)
    db.flush()
    for dataset in TrackDataset:
        db.add(
            BestTrackObservation(
                dataset=dataset.value,
                disturbance_pk=disturbance.id,
                tm=datetime(2015, 1, 1, tzinfo=UTC),
                lat=-12.0,
                lon=130.0,
            )
        )
    db.flush()
    assert len(db.execute(select(BestTrackObservation)).scalars().all()) == 2


def test_utc_datetime_round_trips_as_aware(db: Session):
    disturbance = Disturbance(
        disturbance_id="AU209900_04U",
        first_obs_tm=datetime(2020, 6, 1, 12, 30, tzinfo=UTC),
    )
    db.add(disturbance)
    db.flush()
    db.expire(disturbance)
    assert disturbance.first_obs_tm.tzinfo is not None
    assert disturbance.first_obs_tm == datetime(
        2020, 6, 1, 12, 30, tzinfo=UTC
    )


def test_utc_datetime_rejects_nonsense():
    decorator = UtcDateTime()

    class Dialect:
        name = "sqlite"

    with pytest.raises(TypeError):
        decorator.process_bind_param(object(), Dialect())


def test_code_seed_row_count(seeded_db: Session):
    assert seeded_db.execute(select(CodeValue)).scalars().all().__len__() == (
        TOTAL_CODE_VALUES
    )
    assert len(DOMAINS) == 13


def test_chunk_size_respects_the_sqlite_parameter_limit():
    """SQLite's bound-parameter ceiling is 32766.

    A fixed row-based chunk is a trap: 500 rows of the 79-column observation
    table is about 39,500 parameters and fails outright.
    """
    for columns in (1, 9, 24, 79, 88):
        rows = chunk_size_for("sqlite", columns)
        assert rows >= 1
        assert rows * columns <= 32_766, columns


def test_geometry_columns_are_deferred():
    """An ordinary select() must not drag hundreds of MB through the ORM."""
    for model, column in (("BulletinArea", "geometry"), ("BulletinTrack", "geometry")):
        import app.models.gml as gml

        mapper = inspect(getattr(gml, model))
        assert mapper.attrs[column].deferred, f"{model}.{column} should be deferred"


def test_outcome_classification():
    assert Outcome.classify(True, True) is Outcome.HIT
    assert Outcome.classify(True, False) is Outcome.FALSE_ALARM
    assert Outcome.classify(False, True) is Outcome.MISS
    assert Outcome.classify(False, False) is Outcome.CORRECT_NEGATIVE
