"""Verification loader and contingency arithmetic.

The load-bearing test here is
:func:`test_recomputed_counts_reproduce_the_committed_summary`: grouping the
loaded pairs by outcome must give back exactly the numbers BoM's own generator
wrote to ``_contingency_summary.csv``. If that holds, the chain from town
sheet, through the GML watch/warning areas, to the 2x2 table is intact.
"""

import csv
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import Outcome, SummaryScope
from app.models.verification import (
    ForecastAdviceDistance,
    ObservedWindDistance,
    VerificationPair,
    VerificationSummary,
)
from app.schemas.verification import ContingencySummary
from app.services.loaders.verification import (
    default_contingency_dir,
    discover,
    load_verification,
)

#: From the committed CSVs, verified by reading them.
COMMITTED = {
    "AU202526_02U": (277, 565, 23, 1890, 2755),
    "AU202526_03U": (10, 9, 0, 0, 19),
    "AU202526_05U": (0, 0, 0, 0, 0),
}


def test_contingency_summary_computes_the_documented_scores():
    """POD/FAR/CSI/bias and the 2x2 are derived, never stored."""
    summary = ContingencySummary(
        scope="disturbance",
        scope_key="AU202526_02U",
        hit=277,
        false_alarm=565,
        miss=23,
        correct_negative=1890,
        total=2755,
    )
    assert summary.pod == pytest.approx(277 / 300)
    assert summary.far == pytest.approx(565 / 842)
    assert summary.csi == pytest.approx(277 / 865)
    assert summary.bias == pytest.approx(842 / 300)

    # This must match the committed contingency_matrix.csv exactly.
    matrix = summary.matrix
    assert (matrix.forecast_yes.observed_yes, matrix.forecast_yes.observed_no) == (
        277,
        565,
    )
    assert matrix.forecast_yes.total == 842
    assert (matrix.forecast_no.observed_yes, matrix.forecast_no.observed_no) == (
        23,
        1890,
    )
    assert matrix.forecast_no.total == 1913
    assert (matrix.total.observed_yes, matrix.total.observed_no) == (300, 2455)
    assert matrix.total.total == 2755


def test_scores_are_none_rather_than_dividing_by_zero():
    empty = ContingencySummary(
        scope="disturbance",
        scope_key="AU202526_05U",
        hit=0,
        false_alarm=0,
        miss=0,
        correct_negative=0,
        total=0,
    )
    assert empty.pod is None
    assert empty.far is None
    assert empty.csi is None
    assert empty.bias is None


@pytest.mark.requires_data
class TestAgainstCommittedCsvs:
    @pytest.fixture(autouse=True)
    def _require_files(self):
        if not discover():
            pytest.skip(f"no contingency CSVs under {default_contingency_dir()}")

    @pytest.fixture(scope="class")
    @classmethod
    def source_frames(cls, towns_xlsx: Path, best_track_csv: Path):
        """Read the two big source files once for the whole class.

        The best-track frame is narrowed to the disturbances the contingency
        tables actually reference: loading all 31,706 rows per test made this
        class take five minutes for no extra coverage.
        """
        from app.services.loaders.best_track import read_best_track_csv
        from app.services.loaders.towns import read_towns_sheet

        wanted = set(discover())
        best_track = read_best_track_csv(best_track_csv)
        narrowed = best_track[
            best_track["DISTURBANCE_ID"].str.strip().isin(wanted)
        ].copy()
        return read_towns_sheet(towns_xlsx), narrowed

    @pytest.fixture
    def loaded(self, seeded_db: Session, source_frames):
        from app.services.loaders.best_track import load_best_track
        from app.services.loaders.towns import load_towns

        towns_frame, best_track_frame = source_frames
        load_towns(seeded_db, towns_frame)
        load_best_track(seeded_db, best_track_frame)
        seeded_db.flush()
        counts = load_verification(seeded_db)
        seeded_db.flush()
        return seeded_db, counts

    def test_every_table_is_populated(self, loaded):
        _, counts = loaded
        assert counts["table_a"] > 0
        assert counts["table_b"] > 0
        assert counts["table_c"] > 0
        assert counts["table_d"] > 0

    def test_recomputed_counts_reproduce_the_committed_summary(self, loaded):
        db, counts = loaded
        for ident, expected in COMMITTED.items():
            row = db.execute(
                select(VerificationSummary).where(
                    VerificationSummary.run_id == counts["run_id"],
                    VerificationSummary.scope == SummaryScope.DISTURBANCE.value,
                    VerificationSummary.scope_key == ident,
                )
            ).scalar_one()
            got = (
                row.hit,
                row.false_alarm,
                row.miss,
                row.correct_negative,
                row.total,
            )
            assert got == expected, ident

    def test_summary_matches_the_csv_on_disk(self, loaded):
        """Read the CSVs here too, so the constants above cannot drift."""
        db, counts = loaded
        for ident, files in discover().items():
            path = files.get("contingency_summary")
            if path is None:
                continue
            with path.open(newline="", encoding="utf-8") as handle:
                reported = next(csv.DictReader(handle))
            row = db.execute(
                select(VerificationSummary).where(
                    VerificationSummary.run_id == counts["run_id"],
                    VerificationSummary.scope == SummaryScope.DISTURBANCE.value,
                    VerificationSummary.scope_key == ident,
                )
            ).scalar_one()
            assert row.hit == int(reported["hit"]), ident
            assert row.false_alarm == int(reported["false alarm"]), ident
            assert row.miss == int(reported["miss"]), ident
            assert row.correct_negative == int(reported["correct negative"]), ident
            assert row.total == int(reported["total"]), ident

    def test_overall_scope_is_the_sum_of_the_disturbances(self, loaded):
        db, counts = loaded
        overall = db.execute(
            select(VerificationSummary).where(
                VerificationSummary.run_id == counts["run_id"],
                VerificationSummary.scope == SummaryScope.ALL.value,
            )
        ).scalar_one()
        assert overall.total == sum(v[4] for v in COMMITTED.values())

    def test_outcome_agrees_with_forecast_and_observed(self, loaded):
        db, counts = loaded
        mismatched = 0
        for pair in db.execute(
            select(VerificationPair).where(
                VerificationPair.run_id == counts["run_id"]
            )
        ).scalars():
            expected = Outcome.classify(pair.forecast, pair.observed).value
            mismatched += pair.outcome != expected
        assert mismatched == 0

    def test_negative_distances_are_preserved(self, loaded):
        """A negative distance means the town is inside the area."""
        db, counts = loaded
        inside = db.execute(
            select(func.count())
            .select_from(ForecastAdviceDistance)
            .where(
                ForecastAdviceDistance.run_id == counts["run_id"],
                ForecastAdviceDistance.distance_to_watch_km < 0,
            )
        ).scalar_one()
        assert inside > 0

    def test_blank_warning_distance_stays_null(self, loaded):
        """Blank means the bulletin had no warning area at all."""
        db, counts = loaded
        nulls = db.execute(
            select(func.count())
            .select_from(ForecastAdviceDistance)
            .where(
                ForecastAdviceDistance.run_id == counts["run_id"],
                ForecastAdviceDistance.distance_to_warning_km.is_(None),
            )
        ).scalar_one()
        assert nulls > 0

    def test_table_b_is_keyed_on_time_not_base_time(self, loaded):
        db, counts = loaded
        row = db.execute(
            select(ObservedWindDistance).where(
                ObservedWindDistance.run_id == counts["run_id"]
            )
        ).scalars().first()
        assert row.tm is not None
        assert row.analysis_uncertainty_km is not None

    def test_an_empty_disturbance_still_gets_a_zero_row(self, loaded):
        """AU202526_05U has header-only tables but was still scored."""
        db, counts = loaded
        row = db.execute(
            select(VerificationSummary).where(
                VerificationSummary.run_id == counts["run_id"],
                VerificationSummary.scope == SummaryScope.DISTURBANCE.value,
                VerificationSummary.scope_key == "AU202526_05U",
            )
        ).scalar_one()
        assert row.total == 0
