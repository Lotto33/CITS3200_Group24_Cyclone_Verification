"""Towns loader: the sheet has 472 rows but only 466 places.

Six QLD entries appear twice at identical coordinates, once in ``qld_towns``
and once in ``qld_coastal_threat_area_locations``. Treating the group as a
membership rather than a column is what makes ``(name, state)`` a usable key --
and contingency tables B and C identify a location by name alone, so it has to
be one.
"""

import pandas as pd
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.column_maps import TOWN_COLUMNS
from app.models.town import Town, TownGroupMembership
from app.services.loaders.common import Stats
from app.services.loaders.towns import load_towns, resolve_town_ids

DUPLICATED_IN_TWO_GROUPS = [
    "Bamaga",
    "Carmila",
    "Hayman Is",
    "QLD/NSW Border",
    "Sandy Cape",
    "Thursday Is",
]


def sheet(rows: list[dict]) -> pd.DataFrame:
    """A frame with the real sheet's columns, as strings."""
    return pd.DataFrame(
        [{column: row.get(column, "") for column in TOWN_COLUMNS} for row in rows],
        dtype=str,
    )


@pytest.fixture
def duplicate_sheet() -> pd.DataFrame:
    return sheet(
        [
            {
                "Name": "Bamaga",
                "State": "QLD",
                "Latitude": "-10.9",
                "Longitude": "142.4",
                "Town Group": "qld_towns",
                "Coastal Order": "81",
            },
            {
                "Name": "Bamaga",
                "State": "QLD",
                "Latitude": "-10.9",
                "Longitude": "142.4",
                "Town Group": "qld_coastal_threat_area_locations",
                "Coastal Order": "",
            },
            {
                "Name": "Darwin",
                "State": "NT",
                "Latitude": "-12.4",
                "Longitude": "130.87",
                "Town Group": "nt_towns",
                "Coastal Order": "57",
                "Major Town": "1",
            },
            # Formatted-but-empty trailing row, of which the real sheet has
            # hundreds.
            {"Name": "", "State": "", "Latitude": "", "Longitude": ""},
        ]
    )


def test_duplicate_rows_collapse_to_one_town(db: Session, duplicate_sheet):
    counts = load_towns(db, duplicate_sheet)
    db.flush()
    assert counts["rows_read"] == 4
    assert counts["skipped"] == 1
    assert db.execute(select(func.count()).select_from(Town)).scalar_one() == 2


def test_a_town_can_belong_to_two_groups(db: Session, duplicate_sheet):
    load_towns(db, duplicate_sheet)
    db.flush()
    groups = dict(
        db.execute(
            select(TownGroupMembership.town_group, TownGroupMembership.coastal_order)
            .join(Town)
            .where(Town.name == "Bamaga")
        ).all()
    )
    assert groups == {
        "qld_towns": 81.0,
        "qld_coastal_threat_area_locations": None,
    }


def test_coastal_order_keeps_fractions(db: Session):
    """The sheet uses 20.1 and 20.2 to insert places between integers.

    ``int(float(v))`` would collapse both onto 20 and destroy the very
    ordering the column exists to express.
    """
    load_towns(
        db,
        sheet(
            [
                {
                    "Name": "Between A",
                    "State": "QLD",
                    "Latitude": "-20",
                    "Longitude": "148",
                    "Town Group": "qld_towns",
                    "Coastal Order": "20.1",
                },
                {
                    "Name": "Between B",
                    "State": "QLD",
                    "Latitude": "-20.5",
                    "Longitude": "148.5",
                    "Town Group": "qld_towns",
                    "Coastal Order": "20.2",
                },
            ]
        ),
    )
    db.flush()
    orders = sorted(
        db.execute(select(TownGroupMembership.coastal_order)).scalars()
    )
    assert orders == [20.1, 20.2]


def test_flags_are_ored_and_the_disagreement_is_recorded(db: Session):
    """Sandy Cape is island=True in one group and False in the other."""
    stats = Stats()
    load_towns(
        db,
        sheet(
            [
                {
                    "Name": "Sandy Cape",
                    "State": "QLD",
                    "Latitude": "-24.7",
                    "Longitude": "153.27",
                    "Town Group": "qld_coastal_threat_area_locations",
                    "Island Town": "1",
                },
                {
                    "Name": "Sandy Cape",
                    "State": "QLD",
                    "Latitude": "-24.7",
                    "Longitude": "153.27",
                    "Town Group": "qld_towns",
                    "Island Town": "",
                },
            ]
        ),
        stats=stats,
    )
    db.flush()
    town = db.execute(select(Town).where(Town.name == "Sandy Cape")).scalar_one()
    assert town.is_island is True
    assert any("Island Town differs" in c for c in stats.conflicts)


def test_a_single_row_is_not_reported_as_a_conflict(db: Session, duplicate_sheet):
    """Filling in a default for the first row is not a disagreement."""
    stats = Stats()
    load_towns(db, duplicate_sheet, stats=stats)
    db.flush()
    assert not [c for c in stats.conflicts if "Darwin" in c]


def test_reload_is_idempotent(db: Session, duplicate_sheet):
    load_towns(db, duplicate_sheet)
    db.flush()
    load_towns(db, duplicate_sheet)
    db.flush()
    assert db.execute(select(func.count()).select_from(Town)).scalar_one() == 2
    assert (
        db.execute(select(func.count()).select_from(TownGroupMembership)).scalar_one()
        == 3
    )


def test_ambiguous_name_lookup_raises(db: Session):
    """Tables B and C have no State column, so a collision must not be guessed."""
    load_towns(
        db,
        sheet(
            [
                {
                    "Name": "Springfield",
                    "State": "QLD",
                    "Latitude": "-27",
                    "Longitude": "152",
                    "Town Group": "qld_towns",
                },
                {
                    "Name": "Springfield",
                    "State": "NSW",
                    "Latitude": "-33",
                    "Longitude": "151",
                    "Town Group": "nsw_towns",
                },
            ]
        ),
    )
    db.flush()
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_town_ids(db)


@pytest.mark.requires_data
def test_real_sheet_gives_466_towns_and_472_memberships(db: Session, towns_xlsx):
    from app.services.loaders.towns import read_towns_sheet

    stats = Stats()
    counts = load_towns(db, read_towns_sheet(towns_xlsx), stats=stats)
    db.flush()
    assert counts["towns"] == 466
    assert counts["memberships"] == 472

    names = dict(db.execute(select(Town.name, Town.id)).all())
    for name in DUPLICATED_IN_TWO_GROUPS:
        assert name in names, name
        memberships = db.execute(
            select(func.count())
            .select_from(TownGroupMembership)
            .where(TownGroupMembership.town_id == names[name])
        ).scalar_one()
        assert memberships == 2, name

    # Every location resolves by name alone, which tables B and C rely on.
    assert len(resolve_town_ids(db)) == 466
