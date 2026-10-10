"""Source-column to model-attribute maps.

These dicts are the contract between the CSV/spreadsheet headers and the ORM,
so they are written out literally rather than computed with ``.lower()``: a
reviewer has to be able to diff them against the real header, and
``tests/test_column_maps.py`` asserts they still match ``data/best_track.csv``
and the mapped columns.
"""

# ---------------------------------------------------------------------------
# data/best_track.csv -- BoM product IDCKMSTM0S, "Database of past tropical
# cyclone tracks". 4 metadata lines, header on line 5 (read with skiprows=4),
# 79 columns, 31,706 data rows, 1,133 disturbances.
#
# NAME and DISTURBANCE_ID are deliberately absent from the value map: NAME is
# constant per disturbance and lives on `disturbance`, and DISTURBANCE_ID is
# resolved to the `disturbance_pk` foreign key by the loader.
# ---------------------------------------------------------------------------
BEST_TRACK_KEY_COLUMNS: dict[str, str] = {
    "TM": "tm",
    "TYPE": "type_code",
    "COMMENT": "comment_text",
}

BEST_TRACK_VALUE_COLUMNS: dict[str, str] = {
    "DATA_SRC": "data_src",
    "SURFACE_CODE": "surface_code",
    "CYC_TYPE": "cyc_type",
    "LAT": "lat",
    "LON": "lon",
    "POSITION_METHOD": "position_method",
    "POSITION_UNCERTAINTY": "position_uncertainty",
    "DVORAK_DATA_T_NO": "dvorak_data_t_no",
    "DVORAK_MODEL_T_NO": "dvorak_model_t_no",
    "DVORAK_PATTERN_T_NO": "dvorak_pattern_t_no",
    "DVORAK_FINAL_T_NO": "dvorak_final_t_no",
    "DVORAK_CI_NO": "dvorak_ci_no",
    "CENTRAL_PRES": "central_pres",
    "CENTRAL_PRES_UNCERTAINTY": "central_pres_uncertainty",
    "CENTRAL_PRES_METHOD": "central_pres_method",
    "PRES_WIND_RELATION_USED": "pres_wind_relation_used",
    "ENV_PRES": "env_pres",
    "ENV_PRES_UNCERTAINTY": "env_pres_uncertainty",
    "MN_RADIUS_OUTER_ISOBAR": "mn_radius_outer_isobar",
    "MN_RAD_OUT_ISOBAR_UNCERTAINTY": "mn_rad_out_isobar_uncertainty",
    "MN_RADIUS_GF_WIND": "mn_radius_gf_wind",
    "MN_RADIUS_GF_SECNE": "mn_radius_gf_secne",
    "MN_RADIUS_GF_SECSE": "mn_radius_gf_secse",
    "MN_RADIUS_GF_SECSW": "mn_radius_gf_secsw",
    "MN_RADIUS_GF_SECNW": "mn_radius_gf_secnw",
    "MN_RADIUS_SF_WIND": "mn_radius_sf_wind",
    "MN_RADIUS_SF_SECNE": "mn_radius_sf_secne",
    "MN_RADIUS_SF_SECSE": "mn_radius_sf_secse",
    "MN_RADIUS_SF_SECSW": "mn_radius_sf_secsw",
    "MN_RADIUS_SF_SECNW": "mn_radius_sf_secnw",
    "MN_RADIUS_HF_WIND": "mn_radius_hf_wind",
    "MN_RADIUS_HF_SECNE": "mn_radius_hf_secne",
    "MN_RADIUS_HF_SECSE": "mn_radius_hf_secse",
    "MN_RADIUS_HF_SECSW": "mn_radius_hf_secsw",
    "MN_RADIUS_HF_SECNW": "mn_radius_hf_secnw",
    "MN_RADIUS_MAX_WIND": "mn_radius_max_wind",
    "MN_RADIUS_MAX_WIND_UNCERTAINTY": "mn_radius_max_wind_uncertainty",
    "MN_RADIUS_GF_WIND_UNCERTAINTY": "mn_radius_gf_wind_uncertainty",
    "MN_RADIUS_SF_WIND_UNCERTAINTY": "mn_radius_sf_wind_uncertainty",
    "MN_RADIUS_HF_WIND_UNCERTAINTY": "mn_radius_hf_wind_uncertainty",
    "MN_RADIUS_MAX_WIND_METHOD": "mn_radius_max_wind_method",
    "MN_RADIUS_GF_WIND_METHOD": "mn_radius_gf_wind_method",
    "MN_RADIUS_SF_WIND_METHOD": "mn_radius_sf_wind_method",
    "MN_RADIUS_HF_WIND_METHOD": "mn_radius_hf_wind_method",
    "WIND_SPD_PER": "wind_spd_per",
    "MAX_WIND_SPD": "max_wind_spd",
    "MAX_WIND_SPD_UNCERTAINTY": "max_wind_spd_uncertainty",
    "MAX_WIND_SPD_METHOD": "max_wind_spd_method",
    "MAX_WIND_GUST_PER": "max_wind_gust_per",
    "MAX_WIND_GUST": "max_wind_gust",
    "MAX_WIND_GUST_METHOD": "max_wind_gust_method",
    "MN_EYE_RAD": "mn_eye_rad",
    "MN_EYE_RAD_UNCERTAINTY": "mn_eye_rad_uncertainty",
    "MN_EYE_RAD_METHOD": "mn_eye_rad_method",
    "MAX_REP_WIND_SPD": "max_rep_wind_spd",
    "MAX_REP_WIND_DIR": "max_rep_wind_dir",
    "MAX_REP_WIND_METHOD": "max_rep_wind_method",
    "MAX_REP_WIND_LON": "max_rep_wind_lon",
    "MAX_REP_WIND_LAT": "max_rep_wind_lat",
    "MAX_REP_WAV_HT": "max_rep_wav_ht",
    "MAX_REP_WAV_METHOD": "max_rep_wav_method",
    "MAX_REP_WAV_LON": "max_rep_wav_lon",
    "MAX_REP_WAV_LAT": "max_rep_wav_lat",
    "MAX_REP_SWL_HT": "max_rep_swl_ht",
    "MAX_REP_SWL_DIR": "max_rep_swl_dir",
    "MAX_REP_SWL_PER": "max_rep_swl_per",
    "MAX_REP_SWL_METHOD": "max_rep_swl_method",
    "MAX_REP_SWL_LON": "max_rep_swl_lon",
    "MAX_REP_SWL_LAT": "max_rep_swl_lat",
    "MAX_REP_TIDE_ANOM": "max_rep_tide_anom",
    "MAX_REP_TIDE_ANOM_UNCERTAINTY": "max_rep_tide_anom_uncertainty",
    "MAX_REP_TIDE_ANOM_METHOD": "max_rep_tide_anom_method",
    "MAX_REP_TIDE_ANOM_LON": "max_rep_tide_anom_lon",
    "MAX_REP_TIDE_ANOM_LAT": "max_rep_tide_anom_lat",
}

#: Every best-track CSV column that maps onto BestTrackObservation.
BEST_TRACK_COLUMNS: dict[str, str] = {
    **BEST_TRACK_KEY_COLUMNS,
    **BEST_TRACK_VALUE_COLUMNS,
}

#: Columns read into the `disturbance` table rather than the observation.
BEST_TRACK_DISTURBANCE_COLUMNS: dict[str, str] = {
    "NAME": "name",
    "DISTURBANCE_ID": "disturbance_id",
    "TYPE": "type_code",
}

#: The full CSV header, in file order. Asserted against the real file by
#: tests/test_column_maps.py, so a BoM schema change fails CI rather than
#: silently dropping a column.
BEST_TRACK_CSV_HEADER: tuple[str, ...] = (
    "NAME",
    "DISTURBANCE_ID",
    "TM",
    "TYPE",
    *BEST_TRACK_VALUE_COLUMNS,
    "COMMENT",
)

#: Where the 2011 spec and the shipped CSV disagree on a field name. The CSV
#: spelling wins -- it is what the existing interpolation code already uses --
#: but anyone reading the PDF alongside the code needs this to find the column
#: instead of concluding it is missing.
PDF_SPELLING_ALIASES: dict[str, str] = {
    "MN_RADIUS_GF_WND": "MN_RADIUS_GF_WIND",
    "MN_RADIUS_SF_WND": "MN_RADIUS_SF_WIND",
    "MN_RADIUS_HF_WND": "MN_RADIUS_HF_WIND",
    "MN_RADIUS_MAX_WND": "MN_RADIUS_MAX_WIND",
    "MN_RADIUS_MAX_WND_UNCERTAINTY": "MN_RADIUS_MAX_WIND_UNCERTAINTY",
    "MN_RADIUS_GF_WND_UNCERTAINTY": "MN_RADIUS_GF_WIND_UNCERTAINTY",
    "MN_RADIUS_SF_WND_UNCERTAINTY": "MN_RADIUS_SF_WIND_UNCERTAINTY",
    "MN_RADIUS_HF_WND_UNCERTAINTY": "MN_RADIUS_HF_WIND_UNCERTAINTY",
    "MN_RADIUS_MAX_WND_METHOD": "MN_RADIUS_MAX_WIND_METHOD",
    "MN_RADIUS_GF_METHOD": "MN_RADIUS_GF_WIND_METHOD",
    "MN_RADIUS_SF_METHOD": "MN_RADIUS_SF_WIND_METHOD",
    "MN_RADIUS_HF_METHOD": "MN_RADIUS_HF_WIND_METHOD",
    "MN_RADIUS_OUTER_ISOBAR_UNCERTAINTY": "MN_RAD_OUT_ISOBAR_UNCERTAINTY",
}

#: Columns whose values are fractional in the source data. Every other column
#: that maps to a numeric attribute is integral across all 31,706 rows, so the
#: loader raises on a fractional value there rather than truncating silently.
BEST_TRACK_FLOAT_COLUMNS: frozenset[str] = frozenset(
    {
        "LAT",
        "LON",
        "DVORAK_DATA_T_NO",
        "DVORAK_MODEL_T_NO",
        "DVORAK_PATTERN_T_NO",
        "DVORAK_FINAL_T_NO",
        "DVORAK_CI_NO",
        "MAX_WIND_SPD",
        "MAX_WIND_SPD_UNCERTAINTY",
        "MAX_WIND_GUST",
        "MN_EYE_RAD",
        "MAX_REP_WIND_SPD",
        "MAX_REP_WIND_LON",
        "MAX_REP_WIND_LAT",
        "MAX_REP_WAV_HT",
        "MAX_REP_WAV_LON",
        "MAX_REP_WAV_LAT",
        "MAX_REP_SWL_HT",
        "MAX_REP_SWL_LON",
        "MAX_REP_SWL_LAT",
        "MAX_REP_TIDE_ANOM",
        "MAX_REP_TIDE_ANOM_UNCERTAINTY",
        "MAX_REP_TIDE_ANOM_LON",
        "MAX_REP_TIDE_ANOM_LAT",
    }
)

#: BoM writes TM as "YYYY-MM-DD HH:MM".
BEST_TRACK_TM_FORMAT = "%Y-%m-%d %H:%M"
BEST_TRACK_HEADER_ROW = 4

# ---------------------------------------------------------------------------
# data/OTCR_alldata_final_external.csv -- Objective TC Reanalysis 1981-2016.
#
# 221 columns, header on line 1, 14,256 rows. Columns 0-83 are the best-track
# schema with five OTCR-derived columns interleaved; columns 84-220 are an
# analyst-workbook dump of per-method blocks whose headers repeat -- "Lat",
# "Lon", "Date" and "Vmax (kn)" each appear four to six times, so pandas
# mangles them into "Lat.1", "Lat.2" and so on. The loader therefore selects
# by POSITION, never by name, and stops after column 84.
#
# TM in this file is "DD/MM/YYYY H:MM", unlike best_track.csv. Parse with an
# explicit format: inference reads 03/11/2016 as 11 March.
# ---------------------------------------------------------------------------
OTCR_HEADER_ROW = 0
OTCR_TM_FORMAT = "%d/%m/%Y %H:%M"

#: Last column index the loader reads (exclusive upper bound is this + 1).
OTCR_LAST_MAPPED_INDEX = 84

#: OTCR column index -> model attribute, for the five interleaved extras plus
#: "Adjusted Vm" at index 84.
OTCR_EXTRA_COLUMNS: dict[int, str] = {
    11: "otcr_adj_adt_vm_kn",
    12: "otcr_cp_ckz_hpa",
    13: "otcr_poci_lok_hpa",
    53: "otcr_vmax_kn",
    58: "otcr_wind_gust_kn",
    84: "otcr_adjusted_vm",
}

#: Expected OTCR header text at each index above, asserted by the loader so a
#: re-exported workbook with shifted columns fails loudly instead of writing
#: wind speeds into pressure columns.
OTCR_EXTRA_HEADERS: dict[int, str] = {
    11: "adj. ADT Vm (kn)",
    12: "CP(CKZ(Lok R34,LokPOCI, adj. Vm),hPa)",
    13: "POCI (Lok, hPa)",
    53: "Vmax (kn)",
    58: "Wind Gust (kn)",
    84: "Adjusted Vm",
}

# ---------------------------------------------------------------------------
# app/resources/towns.xlsx, sheet "TC Locations" -- 472 rows, 466 distinct locations.
# ---------------------------------------------------------------------------
TOWN_SHEET_NAME = "TC Locations"

TOWN_COLUMNS: dict[str, str] = {
    "Name": "name",
    "State": "state",
    "Latitude": "lat",
    "Longitude": "lon",
    "Town Group": "town_group",
    "Coastal Order": "coastal_order",
    "Major Town": "is_major",
    "Island Town": "is_island",
}

# ---------------------------------------------------------------------------
# data/processed/best_track_interpolated.csv (produced by
# app.services.interpolation.interpolate_best_track)
# ---------------------------------------------------------------------------
INTERPOLATED_COLUMNS: dict[str, str] = {
    "TM": "tm",
    "LAT": "lat",
    "LON": "lon",
    "POSITION_UNCERTAINTY": "position_uncertainty",
    "MAX_WIND_SPD": "max_wind_spd",
    "IS_INTERPOLATED": "is_interpolated",
    "MN_RADIUS_GF_WIND": "mn_radius_gf_wind",
    "MN_RADIUS_GF_SECNE": "mn_radius_gf_secne",
    "MN_RADIUS_GF_SECSE": "mn_radius_gf_secse",
    "MN_RADIUS_GF_SECSW": "mn_radius_gf_secsw",
    "MN_RADIUS_GF_SECNW": "mn_radius_gf_secnw",
    "MN_RADIUS_SF_WIND": "mn_radius_sf_wind",
    "MN_RADIUS_SF_SECNE": "mn_radius_sf_secne",
    "MN_RADIUS_SF_SECSE": "mn_radius_sf_secse",
    "MN_RADIUS_SF_SECSW": "mn_radius_sf_secsw",
    "MN_RADIUS_SF_SECNW": "mn_radius_sf_secnw",
    "MN_RADIUS_HF_WIND": "mn_radius_hf_wind",
    "MN_RADIUS_HF_SECNE": "mn_radius_hf_secne",
    "MN_RADIUS_HF_SECSE": "mn_radius_hf_secse",
    "MN_RADIUS_HF_SECSW": "mn_radius_hf_secsw",
    "MN_RADIUS_HF_SECNW": "mn_radius_hf_secnw",
}

# ---------------------------------------------------------------------------
# data/contingency_tables/<distId>_*.csv
# ---------------------------------------------------------------------------
TABLE_A_COLUMNS: dict[str, str] = {
    "Disturbance ID": "disturbance_id",
    "Base time": "base_time",
    "Location": "location",
    "Distance to watch": "distance_to_watch_km",
    "Distance to warning": "distance_to_warning_km",
    "Watch": "watch",
    "Warning": "warning",
}

TABLE_B_COLUMNS: dict[str, str] = {
    "Disturbance ID": "disturbance_id",
    "Location": "location",
    "Time": "tm",
    "Analysis Uncertainty": "analysis_uncertainty_km",
    "Distance to gale": "distance_to_gale_km",
    "Distance to storm": "distance_to_storm_km",
    "Distance to hurricane": "distance_to_hurricane_km",
}

TABLE_C_COLUMNS: dict[str, str] = {
    "Disturbance ID": "disturbance_id",
    "Base time": "base_time",
    "Location": "location",
    "Observed": "observed",
}

TABLE_D_COLUMNS: dict[str, str] = {
    "Disturbance ID": "disturbance_id",
    "Base time": "base_time",
    "Location": "location",
    "Season": "season",
    "Forecast": "forecast",
    "Observed": "observed",
}

CONTINGENCY_SUMMARY_COLUMNS: dict[str, str] = {
    "hit": "hit",
    "false alarm": "false_alarm",
    "miss": "miss",
    "correct negative": "correct_negative",
    "total": "total",
}

#: The contingency CSVs write timestamps as "YYYY-MM-DD HH:MM:SS".
CONTINGENCY_TM_FORMAT = "%Y-%m-%d %H:%M:%S"
