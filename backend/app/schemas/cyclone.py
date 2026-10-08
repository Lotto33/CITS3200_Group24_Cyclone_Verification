"""Response models for disturbances, best track and interpolated track.

No model here mirrors a table one-to-one. In particular
:class:`BestTrackPoint` is the small subset anyone actually plots, and the full
79-field row is served only from the single-observation route -- a list of
31,706 full rows is not a useful response.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DisturbanceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    disturbance_id: str
    name: str | None
    region: str | None
    season: str | None
    type_code: str | None
    is_test: bool
    has_watch: bool
    has_warning: bool
    has_best_track: bool
    bulletin_count: int
    observation_count: int
    first_obs_tm: datetime | None
    last_obs_tm: datetime | None


class DisturbanceDetail(DisturbanceSummary):
    first_issue: datetime | None = None
    last_issue: datetime | None = None
    datasets: list[str] = []
    type_description: str | None = None


class BestTrackPoint(BaseModel):
    """The plottable subset, matching what ``data/best_track/<id>.json`` holds."""

    model_config = ConfigDict(from_attributes=True)

    tm: datetime
    lat: float | None
    lon: float | None
    central_pres: int | None
    max_wind_spd: float | None
    cyc_type: int | None
    position_uncertainty: int | None
    mn_radius_gf_wind: int | None
    mn_radius_sf_wind: int | None
    mn_radius_hf_wind: int | None


class InterpolatedTrackPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tm: datetime
    is_interpolated: bool
    lat: float | None
    lon: float | None
    max_wind_spd: float | None
    position_uncertainty: float | None

    # Wind radii in km for the gale / storm / hurricane force thresholds. The
    # map builds its wind-area polygons from these, so the quadrant and mean
    # values for every threshold are served, not just gale force.
    mn_radius_gf_wind: float | None
    mn_radius_gf_secne: float | None
    mn_radius_gf_secse: float | None
    mn_radius_gf_secsw: float | None
    mn_radius_gf_secnw: float | None
    mn_radius_sf_wind: float | None
    mn_radius_sf_secne: float | None
    mn_radius_sf_secse: float | None
    mn_radius_sf_secsw: float | None
    mn_radius_sf_secnw: float | None
    mn_radius_hf_wind: float | None
    mn_radius_hf_secne: float | None
    mn_radius_hf_secse: float | None
    mn_radius_hf_secsw: float | None
    mn_radius_hf_secnw: float | None


class InterpolationRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    label: str | None
    source_dataset: str
    step_minutes: int
    project_start: datetime | None
    gf_threshold_kn: float
    sf_threshold_kn: float
    hf_threshold_kn: float
    restricted_to_watch_warning: bool
    input_row_count: int | None
    output_row_count: int | None
    disturbance_count: int | None
    code_version: str | None


class BestTrackObservationFull(BaseModel):
    """Every BoM field for one observation.

    Served only from ``/observations/{tm}``; see the module docstring.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset: str
    tm: datetime
    type_code: str | None = None
    comment_text: str | None = None

    data_src: int | None = None
    surface_code: int | None = None
    cyc_type: int | None = None
    lat: float | None = None
    lon: float | None = None
    position_method: int | None = None
    position_uncertainty: int | None = None

    dvorak_data_t_no: float | None = None
    dvorak_model_t_no: float | None = None
    dvorak_pattern_t_no: float | None = None
    dvorak_final_t_no: float | None = None
    dvorak_ci_no: float | None = None

    central_pres: int | None = None
    central_pres_uncertainty: int | None = None
    central_pres_method: int | None = None
    pres_wind_relation_used: int | None = None
    env_pres: int | None = None
    env_pres_uncertainty: int | None = None
    mn_radius_outer_isobar: int | None = None
    mn_rad_out_isobar_uncertainty: int | None = None

    mn_radius_gf_wind: int | None = None
    mn_radius_gf_secne: int | None = None
    mn_radius_gf_secse: int | None = None
    mn_radius_gf_secsw: int | None = None
    mn_radius_gf_secnw: int | None = None
    mn_radius_sf_wind: int | None = None
    mn_radius_sf_secne: int | None = None
    mn_radius_sf_secse: int | None = None
    mn_radius_sf_secsw: int | None = None
    mn_radius_sf_secnw: int | None = None
    mn_radius_hf_wind: int | None = None
    mn_radius_hf_secne: int | None = None
    mn_radius_hf_secse: int | None = None
    mn_radius_hf_secsw: int | None = None
    mn_radius_hf_secnw: int | None = None

    mn_radius_max_wind: int | None = None
    mn_radius_max_wind_uncertainty: int | None = None
    mn_radius_gf_wind_uncertainty: int | None = None
    mn_radius_sf_wind_uncertainty: int | None = None
    mn_radius_hf_wind_uncertainty: int | None = None
    mn_radius_max_wind_method: int | None = None
    mn_radius_gf_wind_method: int | None = None
    mn_radius_sf_wind_method: int | None = None
    mn_radius_hf_wind_method: int | None = None

    wind_spd_per: int | None = None
    max_wind_spd: float | None = None
    max_wind_spd_uncertainty: float | None = None
    max_wind_spd_method: int | None = None
    max_wind_gust_per: int | None = None
    max_wind_gust: float | None = None
    max_wind_gust_method: int | None = None

    mn_eye_rad: float | None = None
    mn_eye_rad_uncertainty: int | None = None
    mn_eye_rad_method: int | None = None

    max_rep_wind_spd: float | None = None
    max_rep_wind_dir: int | None = None
    max_rep_wind_method: int | None = None
    max_rep_wind_lon: float | None = None
    max_rep_wind_lat: float | None = None

    max_rep_wav_ht: float | None = None
    max_rep_wav_method: int | None = None
    max_rep_wav_lon: float | None = None
    max_rep_wav_lat: float | None = None

    max_rep_swl_ht: float | None = None
    max_rep_swl_dir: int | None = None
    max_rep_swl_per: int | None = None
    max_rep_swl_method: int | None = None
    max_rep_swl_lon: float | None = None
    max_rep_swl_lat: float | None = None

    max_rep_tide_anom: float | None = None
    max_rep_tide_anom_uncertainty: float | None = None
    max_rep_tide_anom_method: int | None = None
    max_rep_tide_anom_lon: float | None = None
    max_rep_tide_anom_lat: float | None = None

    otcr_adj_adt_vm_kn: float | None = None
    otcr_cp_ckz_hpa: float | None = None
    otcr_poci_lok_hpa: float | None = None
    otcr_vmax_kn: float | None = None
    otcr_wind_gust_kn: float | None = None
    otcr_adjusted_vm: float | None = None

    #: Code labels resolved from ``code_value``, keyed by attribute name.
    code_labels: dict[str, str] = {}
