"""Best-track observations: BoM's post-event reanalysed track.

All 79 columns of ``data/best_track.csv`` (BoM product IDCKMSTM0S, "Database of
past tropical cyclone tracks"), typed from
``data/TC_Database_Structure_Oct2011.pdf``. ``NAME`` is constant per
disturbance and lives on :class:`~app.models.disturbance.Disturbance`;
``DISTURBANCE_ID`` becomes ``disturbance_pk``.

Attribute names are a mechanical lowercase of the CSV header, which in three
places differs from the PDF -- the CSV says ``MN_RADIUS_GF_WIND`` and
``MN_RADIUS_GF_WIND_METHOD`` where the PDF says ``MN_RADIUS_GF_WND`` and
``MN_RADIUS_GF_METHOD``, and abbreviates ``MN_RAD_OUT_ISOBAR_UNCERTAINTY``.
**The CSV spelling wins**; see ``app.db.column_maps.PDF_SPELLING_ALIASES``.

Two things about missing values that the rest of the codebase depends on:

* Every measurement column is nullable and **none defaults to 0**. In this data
  ``0`` means "known to be zero" (no gales in that quadrant, no eye) while
  ``NULL`` means "not analysed", and
  :mod:`app.services.interpolation.interpolate_best_track` branches on exactly
  that difference.
* The CSV writes missing values as a single space, not an empty field, so the
  loader strips before testing for blank.

The ``dataset`` discriminator lets the BoM best track and the OTCR reanalysis
share this table: OTCR columns 0-83 *are* this schema. OTCR is reference data
only -- it ends 2016-12-25 and contributes 58 rows inside the project period
against best track's 4,383 -- so it is never the interpolation input.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.columns import UtcDateTime
from app.models.disturbance import Disturbance
from app.models.enums import TrackDataset, sql_in_clause


class BestTrackObservation(Base):
    __tablename__ = "best_track_observation"
    __table_args__ = (
        UniqueConstraint("dataset", "disturbance_pk", "tm"),
        CheckConstraint(sql_in_clause("dataset", TrackDataset), name="dataset_valid"),
        CheckConstraint(
            "lat BETWEEN -90 AND 90 AND lon BETWEEN -180 AND 180",
            name="coords_in_range",
        ),
        Index("ix_best_track_observation_disturbance_pk_tm", "disturbance_pk", "tm"),
        Index("ix_best_track_observation_tm", "tm"),
        Index("ix_best_track_observation_dataset", "dataset"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        doc="Which CSV this row came from. See app.models.enums.TrackDataset.",
    )
    disturbance_pk: Mapped[int] = mapped_column(
        ForeignKey("disturbance.id", ondelete="CASCADE"),
        nullable=False,
    )
    tm: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        doc="BoM TM: the time this row describes, UTC to the nearest minute.",
    )

    # --- Provenance ---
    ingest_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingest_run.id", ondelete="SET NULL")
    )
    source_row_number: Mapped[int | None] = mapped_column(
        Integer,
        doc="1-based line number in the source CSV, for tracing a value back.",
    )

    # --- Free text ---
    type_code: Mapped[str | None] = mapped_column(
        String(1),
        doc="BoM TYPE at this observation. Domain type.",
    )
    comment_text: Mapped[str | None] = mapped_column(
        String(240),
        doc="BoM COMMENT. Named comment_text because COMMENT is reserved in "
        "MySQL and a statement in PostgreSQL.",
    )

    # --- Classification codes (PDF pp. 4-6) ---
    data_src: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Source of the analysis; generally the originating BoM region. Domain "
            "data_src."
        ),
    )
    surface_code: Mapped[int | None] = mapped_column(
        Integer,
        doc="Surface beneath the cyclone centre (land or water). Domain surface_code.",
    )
    cyc_type: Mapped[int | None] = mapped_column(
        Integer,
        doc="System type at this observation. Domain cyc_type.",
    )

    # --- Centre position (PDF pp. 6-7) ---
    lat: Mapped[float | None] = mapped_column(
        Float,
        doc="Centre latitude, decimal degrees, north positive.",
    )
    lon: Mapped[float | None] = mapped_column(
        Float,
        doc="Centre longitude, decimal degrees, east positive.",
    )
    position_method: Mapped[int | None] = mapped_column(
        Integer,
        doc="Tools used to derive the centre. Domain position_method.",
    )
    position_uncertainty: Mapped[int | None] = mapped_column(
        Integer,
        doc="Position-fix uncertainty, km.",
    )

    # --- Dvorak pattern analysis (PDF p. 7) ---
    dvorak_data_t_no: Mapped[float | None] = mapped_column(
        Float,
        doc="Dvorak pattern-analysis parameter (T-number / CI number).",
    )
    dvorak_model_t_no: Mapped[float | None] = mapped_column(
        Float,
        doc="Dvorak pattern-analysis parameter (T-number / CI number).",
    )
    dvorak_pattern_t_no: Mapped[float | None] = mapped_column(
        Float,
        doc="Dvorak pattern-analysis parameter (T-number / CI number).",
    )
    dvorak_final_t_no: Mapped[float | None] = mapped_column(
        Float,
        doc="Dvorak pattern-analysis parameter (T-number / CI number).",
    )
    dvorak_ci_no: Mapped[float | None] = mapped_column(
        Float,
        doc="Dvorak pattern-analysis parameter (T-number / CI number).",
    )

    # --- Pressure (PDF pp. 8-9) ---
    central_pres: Mapped[int | None] = mapped_column(
        Integer,
        doc="Central pressure, hPa.",
    )
    central_pres_uncertainty: Mapped[int | None] = mapped_column(
        Integer,
        doc="Estimated central-pressure uncertainty, hPa.",
    )
    central_pres_method: Mapped[int | None] = mapped_column(
        Integer,
        doc="Domain central_pres_method.",
    )
    pres_wind_relation_used: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Pressure-wind relation used. Domain pres_wind_relation_used. NOTE: the "
            "data carries code 40 on 71 rows, which the 2011 spec does not list -- "
            "which is why no foreign key constrains this column."
        ),
    )
    env_pres: Mapped[int | None] = mapped_column(
        Integer,
        doc="Environmental pressure the cyclone is embedded in, hPa.",
    )
    env_pres_uncertainty: Mapped[int | None] = mapped_column(
        Integer,
        doc="hPa. Empty in every row of the current CSV.",
    )
    mn_radius_outer_isobar: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of the outermost closed isobar, km. 0 if there is no closed "
            "isobar."
        ),
    )
    mn_rad_out_isobar_uncertainty: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "km. Empty in every row of the current CSV. The attribute name follows the "
            "CSV abbreviation; the PDF spells it MN_RADIUS_OUTER_ISOBAR_UNCERTAINTY."
        ),
    )

    # --- Gale-force wind radii, 17 m/s and above (PDF p. 10) ---
    mn_radius_gf_wind: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of gale-force (17 m/s and above) winds, km. 0 means none "
            "present; NULL means not analysed. Almost always empty post-2016 (22 "
            "non-blank of 4,383 rows for GF): the quadrant columns carry the data, "
            "which is why the interpolator uses this only as a fallback when all four "
            "quadrants are missing."
        ),
    )
    mn_radius_gf_secne: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of gale-force (17 m/s and above) winds in the NE quadrant, "
            "km. 0 means none present; NULL means not analysed."
        ),
    )
    mn_radius_gf_secse: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of gale-force (17 m/s and above) winds in the SE quadrant, "
            "km. 0 means none present; NULL means not analysed."
        ),
    )
    mn_radius_gf_secsw: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of gale-force (17 m/s and above) winds in the SW quadrant, "
            "km. 0 means none present; NULL means not analysed."
        ),
    )
    mn_radius_gf_secnw: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of gale-force (17 m/s and above) winds in the NW quadrant, "
            "km. 0 means none present; NULL means not analysed."
        ),
    )

    # --- Storm-force wind radii, 25 m/s and above (PDF p. 10) ---
    mn_radius_sf_wind: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of storm-force (25 m/s and above) winds, km. 0 means none "
            "present; NULL means not analysed. Almost always empty post-2016 (22 "
            "non-blank of 4,383 rows for GF): the quadrant columns carry the data, "
            "which is why the interpolator uses this only as a fallback when all four "
            "quadrants are missing."
        ),
    )
    mn_radius_sf_secne: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of storm-force (25 m/s and above) winds in the NE quadrant, "
            "km. 0 means none present; NULL means not analysed."
        ),
    )
    mn_radius_sf_secse: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of storm-force (25 m/s and above) winds in the SE quadrant, "
            "km. 0 means none present; NULL means not analysed."
        ),
    )
    mn_radius_sf_secsw: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of storm-force (25 m/s and above) winds in the SW quadrant, "
            "km. 0 means none present; NULL means not analysed."
        ),
    )
    mn_radius_sf_secnw: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of storm-force (25 m/s and above) winds in the NW quadrant, "
            "km. 0 means none present; NULL means not analysed."
        ),
    )

    # --- Hurricane-force wind radii, 33 m/s and above (PDF p. 10) ---
    mn_radius_hf_wind: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of hurricane-force (33 m/s and above) winds, km. 0 means none "
            "present; NULL means not analysed. Almost always empty post-2016 (22 "
            "non-blank of 4,383 rows for GF): the quadrant columns carry the data, "
            "which is why the interpolator uses this only as a fallback when all four "
            "quadrants are missing."
        ),
    )
    mn_radius_hf_secne: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of hurricane-force (33 m/s and above) winds in the NE "
            "quadrant, km. 0 means none present; NULL means not analysed."
        ),
    )
    mn_radius_hf_secse: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of hurricane-force (33 m/s and above) winds in the SE "
            "quadrant, km. 0 means none present; NULL means not analysed."
        ),
    )
    mn_radius_hf_secsw: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of hurricane-force (33 m/s and above) winds in the SW "
            "quadrant, km. 0 means none present; NULL means not analysed."
        ),
    )
    mn_radius_hf_secnw: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Mean radius of hurricane-force (33 m/s and above) winds in the NW "
            "quadrant, km. 0 means none present; NULL means not analysed."
        ),
    )

    # --- Radius of maximum wind; radius uncertainties and methods (PDF p. 11) ---
    mn_radius_max_wind: Mapped[int | None] = mapped_column(
        Integer,
        doc="Mean radius of the maximum mean wind, km.",
    )
    mn_radius_max_wind_uncertainty: Mapped[int | None] = mapped_column(
        Integer,
        doc="km. 99 means 99 km or greater. Empty in every row of the current CSV.",
    )
    mn_radius_gf_wind_uncertainty: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Uncertainty in the gale-force (17 m/s and above) mean radius, km. 99 "
            "means 99 km or greater -- a sentinel, not a measurement, so exclude it "
            "from any average. Empty in every row of the current CSV."
        ),
    )
    mn_radius_sf_wind_uncertainty: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Uncertainty in the storm-force (25 m/s and above) mean radius, km. 99 "
            "means 99 km or greater -- a sentinel, not a measurement, so exclude it "
            "from any average. Empty in every row of the current CSV."
        ),
    )
    mn_radius_hf_wind_uncertainty: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Uncertainty in the hurricane-force (33 m/s and above) mean radius, km. 99 "
            "means 99 km or greater -- a sentinel, not a measurement, so exclude it "
            "from any average. Empty in every row of the current CSV."
        ),
    )
    mn_radius_max_wind_method: Mapped[int | None] = mapped_column(
        Integer,
        doc="Domain radius_method.",
    )
    mn_radius_gf_wind_method: Mapped[int | None] = mapped_column(
        Integer,
        doc="Method for the gale-force (17 m/s and above) radii. Domain radius_method.",
    )
    mn_radius_sf_wind_method: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Method for the storm-force (25 m/s and above) radii. Domain radius_method."
        ),
    )
    mn_radius_hf_wind_method: Mapped[int | None] = mapped_column(
        Integer,
        doc=(
            "Method for the hurricane-force (33 m/s and above) radii. Domain "
            "radius_method."
        ),
    )

    # --- Winds and gusts (PDF pp. 11-13) ---
    wind_spd_per: Mapped[int | None] = mapped_column(
        Integer,
        doc="Averaging period for all mean winds, minutes. Australian data is 10.",
    )
    max_wind_spd: Mapped[float | None] = mapped_column(
        Float,
        doc="Estimated maximum mean wind near the centre, m/s.",
    )
    max_wind_spd_uncertainty: Mapped[float | None] = mapped_column(
        Float,
        doc="Estimated accuracy of the maximum mean wind, m/s.",
    )
    max_wind_spd_method: Mapped[int | None] = mapped_column(
        Integer,
        doc="Domain wind_method.",
    )
    max_wind_gust_per: Mapped[int | None] = mapped_column(
        Integer,
        doc="Gust period, seconds. Australian data is 3.",
    )
    max_wind_gust: Mapped[float | None] = mapped_column(
        Float,
        doc="Estimated maximum gust near the centre, m/s, open-terrain basis.",
    )
    max_wind_gust_method: Mapped[int | None] = mapped_column(
        Integer,
        doc="Domain max_wind_gust_method.",
    )

    # --- Eye (PDF p. 14) ---
    mn_eye_rad: Mapped[float | None] = mapped_column(
        Float,
        doc="Mean eye radius, km. 0 means NO EYE; NULL means unknown.",
    )
    mn_eye_rad_uncertainty: Mapped[int | None] = mapped_column(
        Integer,
        doc="Accuracy of the eye-radius estimate, km.",
    )
    mn_eye_rad_method: Mapped[int | None] = mapped_column(
        Integer,
        doc="Domain mn_eye_rad_method.",
    )

    # --- Maximum reported wind (PDF p. 15) ---
    max_rep_wind_spd: Mapped[float | None] = mapped_column(
        Float,
        doc=(
            "Maximum reported wind, m/s. Not recorded unless winds above 17 m/s were "
            "observed, and normally lower than MAX_WIND_SPD."
        ),
    )
    max_rep_wind_dir: Mapped[int | None] = mapped_column(
        Integer,
        doc="Direction of the maximum reported wind, degrees.",
    )
    max_rep_wind_method: Mapped[int | None] = mapped_column(
        Integer,
        doc="Domain wind_method (code 12 is not applicable here).",
    )
    max_rep_wind_lon: Mapped[float | None] = mapped_column(
        Float,
        doc="Longitude of the observation, decimal degrees, east positive.",
    )
    max_rep_wind_lat: Mapped[float | None] = mapped_column(
        Float,
        doc="Latitude of the observation, decimal degrees, north positive.",
    )

    # --- Maximum reported wave height (PDF p. 16) ---
    max_rep_wav_ht: Mapped[float | None] = mapped_column(
        Float,
        doc=(
            "Maximum reported sea wave height, m. Reported only within 556 km of the "
            "centre."
        ),
    )
    max_rep_wav_method: Mapped[int | None] = mapped_column(
        Integer,
        doc="Domain wave_swell_method.",
    )
    max_rep_wav_lon: Mapped[float | None] = mapped_column(
        Float,
        doc="Longitude of the observation, decimal degrees, east positive.",
    )
    max_rep_wav_lat: Mapped[float | None] = mapped_column(
        Float,
        doc="Latitude of the observation, decimal degrees, north positive.",
    )

    # --- Maximum reported swell (PDF p. 17) ---
    max_rep_swl_ht: Mapped[float | None] = mapped_column(
        Float,
        doc=(
            "Maximum reported sea swell height, m. Reported only within 56 km of the "
            "centre."
        ),
    )
    max_rep_swl_dir: Mapped[int | None] = mapped_column(
        Integer,
        doc="Direction of the maximum reported swell, degrees.",
    )
    max_rep_swl_per: Mapped[int | None] = mapped_column(
        Integer,
        doc="Period of the maximum reported swell, seconds.",
    )
    max_rep_swl_method: Mapped[int | None] = mapped_column(
        Integer,
        doc="Domain wave_swell_method.",
    )
    max_rep_swl_lon: Mapped[float | None] = mapped_column(
        Float,
        doc="Longitude of the observation, decimal degrees, east positive.",
    )
    max_rep_swl_lat: Mapped[float | None] = mapped_column(
        Float,
        doc="Latitude of the observation, decimal degrees, north positive.",
    )

    # --- Maximum reported tidal anomaly (PDF p. 18) ---
    max_rep_tide_anom: Mapped[float | None] = mapped_column(
        Float,
        doc=(
            "Maximum reported positive tidal anomaly above the predicted astronomical "
            "tide, m."
        ),
    )
    max_rep_tide_anom_uncertainty: Mapped[float | None] = mapped_column(
        Float,
        doc="m.",
    )
    max_rep_tide_anom_method: Mapped[int | None] = mapped_column(
        Integer,
        doc="Domain tide_anom_method.",
    )
    max_rep_tide_anom_lon: Mapped[float | None] = mapped_column(
        Float,
        doc="Longitude of the observation, decimal degrees, east positive.",
    )
    max_rep_tide_anom_lat: Mapped[float | None] = mapped_column(
        Float,
        doc="Latitude of the observation, decimal degrees, north positive.",
    )

    # --- OTCR-derived columns (null for dataset='bom_best_track') ---
    otcr_adj_adt_vm_kn: Mapped[float | None] = mapped_column(
        Float, doc="OTCR 'adj. ADT Vm (kn)'."
    )
    otcr_cp_ckz_hpa: Mapped[float | None] = mapped_column(
        Float, doc="OTCR 'CP(CKZ(Lok R34,LokPOCI, adj. Vm),hPa)'."
    )
    otcr_poci_lok_hpa: Mapped[float | None] = mapped_column(
        Float, doc="OTCR 'POCI (Lok, hPa)'."
    )
    otcr_vmax_kn: Mapped[float | None] = mapped_column(Float, doc="OTCR 'Vmax (kn)'.")
    otcr_wind_gust_kn: Mapped[float | None] = mapped_column(
        Float, doc="OTCR 'Wind Gust (kn)'."
    )
    otcr_adjusted_vm: Mapped[float | None] = mapped_column(
        Float, doc="OTCR 'Adjusted Vm'."
    )

    disturbance: Mapped[Disturbance] = relationship(back_populates="observations")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BestTrackObservation {self.disturbance_pk} {self.tm} {self.dataset}>"
