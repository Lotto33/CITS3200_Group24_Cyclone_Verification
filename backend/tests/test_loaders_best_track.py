"""Best-track loader behaviour, especially the NULL-vs-zero rule.

The whole point of reading these CSVs as raw strings is that ``0`` and blank
mean different things -- "no gales in that quadrant" versus "not analysed" --
and :mod:`app.services.interpolation.interpolate_best_track` branches on the
difference. If this file ever goes green with a ``fillna(0)`` in the loader,
the science silently changes.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.best_track import BestTrackObservation
from app.models.disturbance import Disturbance
from app.models.enums import TrackDataset
from app.services.loaders.best_track import load_best_track, read_best_track_csv
from app.services.loaders.common import Stats

FIXTURE = Path(__file__).parent / "fixtures" / "best_track_sample.csv"


@pytest.fixture
def loaded(seeded_db: Session) -> tuple[Session, Stats]:
    stats = Stats()
    load_best_track(seeded_db, read_best_track_csv(FIXTURE), stats=stats)
    seeded_db.flush()
    return seeded_db, stats


def _observation(db: Session, disturbance_id: str, tm: str) -> BestTrackObservation:
    return db.execute(
        select(BestTrackObservation)
        .join(Disturbance)
        .where(
            Disturbance.disturbance_id == disturbance_id,
            BestTrackObservation.tm == tm,
        )
    ).scalar_one()


def test_fixture_header_is_the_real_79_columns():
    frame = read_best_track_csv(FIXTURE)
    assert len(frame.columns) == 79


def test_loads_every_row(loaded):
    db, _ = loaded
    assert (
        db.execute(select(func.count()).select_from(BestTrackObservation)).scalar_one()
        == 4
    )


def test_single_space_becomes_null(loaded):
    """BoM writes a missing value as ' ', which must land as NULL."""
    db, _ = loaded
    row = _observation(db, "AU190607_01U", "1907-01-17 23:00")
    assert row.cyc_type is None
    assert row.data_src is None
    assert row.max_wind_spd is None
    assert row.mn_radius_gf_secne is None


def test_explicit_zero_stays_zero(loaded):
    """0 means 'known to be zero' and must not become NULL."""
    db, _ = loaded
    row = _observation(db, "AU201617_19U", "2017-02-17 00:00")
    assert row.mn_radius_gf_secne == 0
    assert row.mn_radius_gf_secse == 0  # written as "0.0" in the CSV
    assert row.mn_radius_gf_secsw == 120
    assert row.mn_eye_rad == 0.0  # 0 means NO EYE, per the spec


def test_zero_and_null_coexist_on_the_same_disturbance(loaded):
    """The distinction has to survive across rows, not just within one."""
    db, _ = loaded
    zero_row = _observation(db, "AU201617_19U", "2017-02-17 00:00")
    null_row = _observation(db, "AU201617_19U", "2017-02-17 06:00")
    assert zero_row.mn_radius_gf_secne == 0
    assert null_row.mn_radius_gf_secne is None


def test_tm_parses_as_utc(loaded):
    db, _ = loaded
    row = _observation(db, "AU190607_01U", "1907-01-17 23:00")
    assert row.tm == datetime(1907, 1, 17, 23, 0, tzinfo=UTC)
    assert row.tm.tzinfo is not None


def test_name_is_stripped_and_stored_on_the_disturbance(loaded):
    db, _ = loaded
    disturbance = db.execute(
        select(Disturbance).where(Disturbance.disturbance_id == "AU190607_01U")
    ).scalar_one()
    assert disturbance.name == "unnamed"
    assert "name" not in BestTrackObservation.__table__.columns


def test_season_is_derived_from_the_id(loaded):
    db, _ = loaded
    seasons = dict(
        db.execute(select(Disturbance.disturbance_id, Disturbance.season)).all()
    )
    assert seasons["AU190607_01U"] == "1906-07"
    assert seasons["AU201617_19U"] == "2016-17"


def test_test_products_are_flagged(loaded):
    db, _ = loaded
    disturbance = db.execute(
        select(Disturbance).where(Disturbance.disturbance_id == "AU201617_99U")
    ).scalar_one()
    assert disturbance.is_test is True


def test_out_of_spec_code_is_stored_and_reported(loaded):
    """PRES_WIND_RELATION_USED=40 is real data the 2011 spec omits.

    It must be kept and reported, never rejected -- a foreign key here would
    abort the 31,706-row production ingest.
    """
    db, stats = loaded
    row = _observation(db, "AU201617_19U", "2017-02-17 06:00")
    assert row.pres_wind_relation_used == 40
    assert stats.unknown_code["pres_wind_relation_used"]["40"] == 1


def test_blank_and_zero_counts_are_recorded(loaded):
    _, stats = loaded
    assert stats.blank_counts["CYC_TYPE"] >= 1
    assert stats.zero_counts["MN_RADIUS_GF_SECNE"] == 1


def test_reload_is_idempotent(seeded_db: Session):
    frame = read_best_track_csv(FIXTURE)
    load_best_track(seeded_db, frame)
    seeded_db.flush()
    first = set(seeded_db.execute(select(BestTrackObservation.id)).scalars())

    load_best_track(seeded_db, frame)
    seeded_db.flush()
    second = set(seeded_db.execute(select(BestTrackObservation.id)).scalars())

    assert first == second, "re-running must update in place, not insert again"


def test_changed_value_updates_in_place(seeded_db: Session):
    frame = read_best_track_csv(FIXTURE)
    load_best_track(seeded_db, frame)
    seeded_db.flush()

    frame.loc[frame["TM"] == "2017-02-17 00:00", "MAX_WIND_SPD"] = "31.4"
    load_best_track(seeded_db, frame)
    seeded_db.flush()

    row = _observation(seeded_db, "AU201617_19U", "2017-02-17 00:00")
    assert row.max_wind_spd == 31.4
    assert (
        seeded_db.execute(
            select(func.count()).select_from(BestTrackObservation)
        ).scalar_one()
        == 4
    )


def test_has_best_track_is_derived_not_asserted(seeded_db: Session):
    """It must mean 'has BoM observations', not 'appears in some source'.

    OTCR covers one system the BoM best track does not, so setting the flag
    from whichever loader created the row would over-count by exactly that
    one.
    """
    load_best_track(seeded_db, read_best_track_csv(FIXTURE))
    seeded_db.flush()
    flags = dict(
        seeded_db.execute(
            select(Disturbance.disturbance_id, Disturbance.has_best_track)
        ).all()
    )
    assert all(flags.values())

    orphan = Disturbance(disturbance_id="AU209900_01U", has_best_track=True)
    seeded_db.add(orphan)
    seeded_db.flush()

    from app.services.loaders.best_track import (
        refresh_disturbance_observation_stats,
    )

    refresh_disturbance_observation_stats(
        seeded_db, dataset=TrackDataset.BOM_BEST_TRACK
    )
    seeded_db.flush()
    seeded_db.refresh(orphan)
    assert orphan.has_best_track is False
    assert orphan.observation_count == 0


def test_header_mismatch_is_rejected(tmp_path: Path):
    """A BoM schema change must fail loudly, not drop a column silently."""
    broken = tmp_path / "broken.csv"
    text = FIXTURE.read_text(encoding="utf-8").replace("MN_RADIUS_GF_WIND", "GF_WIND")
    broken.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="header does not match"):
        read_best_track_csv(broken)
