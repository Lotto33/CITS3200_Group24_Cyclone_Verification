"""The CSV headers and the ORM must not drift apart.

This is the test that catches a typo'd column name: the maps in
``app.db.column_maps`` are the contract between the source files and the
models, and nothing else would notice if one entry pointed at an attribute
that does not exist.
"""

import csv
from pathlib import Path

import pytest

from app.db.column_maps import (
    BEST_TRACK_COLUMNS,
    BEST_TRACK_CSV_HEADER,
    BEST_TRACK_FLOAT_COLUMNS,
    BEST_TRACK_HEADER_ROW,
    INTERPOLATED_COLUMNS,
    OTCR_EXTRA_COLUMNS,
    OTCR_EXTRA_HEADERS,
    OTCR_HEADER_ROW,
    PDF_SPELLING_ALIASES,
    TOWN_COLUMNS,
)
from app.models.best_track import BestTrackObservation
from app.models.interpolation import InterpolatedPoint
from app.models.town import Town, TownGroupMembership

EXPECTED_CSV_COLUMNS = 79


def _header(path: Path, row: int) -> list[str]:
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        return list(csv.reader(handle))[row]


def test_best_track_header_has_79_columns():
    assert len(BEST_TRACK_CSV_HEADER) == EXPECTED_CSV_COLUMNS


def test_best_track_header_matches_the_shipped_csv(best_track_csv: Path):
    assert _header(best_track_csv, BEST_TRACK_HEADER_ROW) == list(BEST_TRACK_CSV_HEADER)


def test_every_mapped_column_exists_on_the_model():
    columns = set(BestTrackObservation.__table__.columns.keys())
    missing = {v for v in BEST_TRACK_COLUMNS.values() if v not in columns}
    assert not missing


def test_mapped_columns_account_for_the_whole_header():
    # NAME and DISTURBANCE_ID are the two that live elsewhere: NAME on
    # `disturbance`, DISTURBANCE_ID resolved to the foreign key.
    unmapped = set(BEST_TRACK_CSV_HEADER) - set(BEST_TRACK_COLUMNS)
    assert unmapped == {"NAME", "DISTURBANCE_ID"}


def test_float_columns_are_a_subset_of_the_header():
    assert BEST_TRACK_FLOAT_COLUMNS <= set(BEST_TRACK_CSV_HEADER)


def test_float_columns_map_to_float_model_columns():
    columns = BestTrackObservation.__table__.columns
    for csv_column in BEST_TRACK_FLOAT_COLUMNS:
        attribute = BEST_TRACK_COLUMNS[csv_column]
        assert "FLOAT" in str(columns[attribute].type).upper(), attribute


def test_pdf_aliases_point_at_real_csv_columns():
    """The PDF spells several fields differently; the CSV spelling wins."""
    for pdf_name, csv_name in PDF_SPELLING_ALIASES.items():
        assert csv_name in BEST_TRACK_COLUMNS, csv_name
        assert pdf_name not in BEST_TRACK_COLUMNS, (
            f"{pdf_name} is the PDF spelling and must not be a real column"
        )


def test_interpolated_columns_exist_on_the_model():
    columns = set(InterpolatedPoint.__table__.columns.keys())
    missing = {v for v in INTERPOLATED_COLUMNS.values() if v not in columns}
    assert not missing


def test_town_columns_exist_across_the_two_town_tables():
    columns = set(Town.__table__.columns.keys()) | set(
        TownGroupMembership.__table__.columns.keys()
    )
    missing = {v for v in TOWN_COLUMNS.values() if v not in columns}
    assert not missing


def test_otcr_extra_columns_and_headers_agree():
    assert set(OTCR_EXTRA_COLUMNS) == set(OTCR_EXTRA_HEADERS)


def test_otcr_extra_columns_exist_on_the_model():
    columns = set(BestTrackObservation.__table__.columns.keys())
    missing = {v for v in OTCR_EXTRA_COLUMNS.values() if v not in columns}
    assert not missing


@pytest.mark.requires_data
def test_otcr_extra_headers_are_at_the_expected_indices():
    """OTCR is read by position, so a shifted export must be detected.

    Its headers repeat -- ``Lat``, ``Lon``, ``Date`` and ``Vmax (kn)`` each
    appear four to six times -- so reading by name is not an option and a
    layout change would otherwise write wind speeds into pressure columns.
    """
    from app.services.loaders.otcr import default_otcr_path

    path = default_otcr_path()
    if not path.is_file():
        pytest.skip(f"{path} is not present")
    header = _header(path, OTCR_HEADER_ROW)
    for index, expected in OTCR_EXTRA_HEADERS.items():
        assert header[index].strip() == expected, index
