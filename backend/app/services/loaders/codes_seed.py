"""BoM code lookup tables, transcribed from TC_Database_Structure_Oct2011.pdf.

``NULL`` always means "unknown or not applicable" and is therefore not listed
as a code -- a missing value in the CSV stays NULL rather than mapping to a
sentinel row here.

A domain appears once even where several columns share it:
``radius_method`` serves all four ``MN_RADIUS_*_METHOD`` columns,
``wind_method`` serves ``MAX_WIND_SPD_METHOD`` and ``MAX_REP_WIND_METHOD``, and
``wave_swell_method`` serves ``MAX_REP_WAV_METHOD`` and
``MAX_REP_SWL_METHOD``.

Note what is deliberately *not* here: any foreign key. The shipped CSV carries
``PRES_WIND_RELATION_USED = 40`` on 71 rows, a code the 2011 spec does not
list, so these tables are reference data for labelling and validation
reporting -- never a constraint that could abort an ingest.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.codes import CodeDomain, CodeValue


@dataclass(frozen=True)
class Domain:
    code: str
    label: str
    description: str
    values: tuple[tuple[str, str], ...]


DOMAINS: tuple[Domain, ...] = (
    Domain(
        code="type",
        label="System type",
        description=(
            "BoM TYPE: the system's classification as a whole. Where a system "
            "evolves, its overall type is the highest on this list."
        ),
        values=(
            ("D", "DRAFT - operational track provided awaiting Best Track"),
            ("T", "Tropical cyclone"),
            ("E", "Extra-tropical cyclone or East Coast Low"),
            ("L", "Tropical low, failed to attain TC strength"),
            ("O", "Other type of system"),
            ("U", "Unknown"),
        ),
    ),
    Domain(
        code="data_src",
        label="Data source",
        description=(
            "Originating office; generally the region that performed the "
            "original best-track analysis."
        ),
        values=(
            ("1", "La Reunion"),
            ("2", "Perth"),
            ("3", "Darwin"),
            ("4", "Brisbane"),
            ("5", "Papua New Guinea"),
            ("6", "Fiji"),
            ("7", "New Zealand"),
            ("10", "Mauritius"),
            ("11", "New Caledonia"),
            ("12", "Central Pacific Hurricane Center, Honolulu"),
            ("13", "Joint Typhoon Warning Center, Honolulu"),
            ("19", "Indonesia"),
            ("20", "Australia - generic"),
            ("21", "Australia - generic, Woodside Study 05"),
            ("30", "S Hemisphere database"),
        ),
    ),
    Domain(
        code="surface_code",
        label="Surface beneath the centre",
        description="Type of surface the cyclone centre is located above.",
        values=(
            ("1", "Over water"),
            ("2", "Over land"),
            ("3", "Moving from water to land"),
            ("4", "Moving from land to water"),
            ("5", "Moving over island of length < 60 nautical miles"),
        ),
    ),
    Domain(
        code="cyc_type",
        label="Cyclone type at this observation",
        description=(
            "Type of system at the time of the observation. Systems can "
            "evolve and change type mid-track, e.g. extra-tropical transition."
        ),
        values=(
            ("10", "Tropics; disturbance (no closed isobars)"),
            ("20", "Winds < 34 knots (17 m/s), at least one closed isobar"),
            ("21", "34-63 knots (17-32 m/s), two or fewer quadrants"),
            ("30", "34-63 knots (17-32 m/s), more than two quadrants"),
            ("40", "Greater than 63 knots (> 32 m/s)"),
            ("50", "Extra-tropical (no gales)"),
            ("51", "Extra-tropical (with gales)"),
            ("52", "Extra-tropical (max wind unknown)"),
            ("60", "Dissipating (no gales)"),
            ("70", "Subtropical cyclone (no gales)"),
            ("71", "Subtropical cyclone (with gales)"),
            ("72", "Subtropical cyclone (max wind unknown)"),
            ("80", "Overland (no gales)"),
            ("81", "Overland (gales)"),
            (
                "91",
                "Tropical cold-cored monsoon low (gales away from the centre)",
            ),
        ),
    ),
    Domain(
        code="position_method",
        label="Method used to derive the centre position",
        description="Tools used to derive the centre location of the system.",
        values=(
            ("1", "No satellite, no radar, no observations"),
            ("2", "No satellite, no radar, observations only"),
            ("3", "Satellite IR/Vis; no clear eye"),
            ("4", "Satellite IR/Vis; clearly defined eye"),
            ("5", "Aircraft radar report"),
            ("6", "Land-based radar report"),
            ("7", "Satellite IR/Vis and radar and observations"),
            ("8", "Report from inside the eye"),
            ("10", "Satellite - scatterometer"),
            ("11", "Satellite - microwave"),
            ("12", "Manned aircraft reconnaissance"),
            ("13", "UAV aircraft reconnaissance"),
        ),
    ),
    Domain(
        code="central_pres_method",
        label="Method used to derive central pressure",
        description="How the central pressure value was obtained.",
        values=(
            ("1", "Aircraft or dropsonde observation"),
            ("2", "Over-water observation (e.g. buoy)"),
            ("3", "Over-land observation"),
            ("4", "Instrument - unknown type"),
            ("5", "Derived directly from Dvorak"),
            ("6", "Derived from wind via a pressure-wind equation"),
            ("7", "Estimate from surrounding observations"),
            ("8", "Extrapolation from radar"),
            ("9", "Other"),
        ),
    ),
    Domain(
        code="pres_wind_relation_used",
        label="Pressure-wind relation",
        description=(
            "Relation used to derive the estimated central pressure and winds "
            "from Dvorak analysis or observations. The shipped CSV also "
            "carries code 40 on 71 rows, which this 2011 lookup does not "
            "define -- which is why no foreign key constrains the column."
        ),
        values=(
            ("1", "Crane (Qld small)"),
            ("2", "Crane (Qld system)"),
            ("3", "Atkinson & Holliday (1977)"),
            ("4", "Love & Murphy (1985)"),
            ("5", "Dvorak (1975)"),
            ("6", "Dvorak Atlantic (1984)"),
            ("7", "Dvorak NWP (1984)"),
            ("8", "Courtney & Knaff Aust. (2009)"),
            ("49", "Other"),
        ),
    ),
    Domain(
        code="radius_method",
        label="Method used to estimate a mean radius",
        description=(
            "Shared by MN_RADIUS_MAX_WIND_METHOD, MN_RADIUS_GF_WIND_METHOD, "
            "MN_RADIUS_SF_WIND_METHOD and MN_RADIUS_HF_WIND_METHOD."
        ),
        values=(
            ("1", "Aircraft observation"),
            ("2", "Surface observation"),
            ("3", "Radar: defined circulation (no eye)"),
            ("4", "Radar: well defined eye"),
            ("5", "Radar: poorly defined eye"),
            ("6", "Radar: Doppler wind"),
            ("7", "Satellite: defined circulation (no eye)"),
            ("8", "Satellite: well defined eye"),
            ("9", "Satellite: poorly defined eye"),
            ("10", "Satellite: scatterometer data"),
            ("11", "Estimate from outer closed isobar"),
            ("20", "Other"),
        ),
    ),
    Domain(
        code="wind_method",
        label="Method used to obtain a wind speed",
        description=(
            "Shared by MAX_WIND_SPD_METHOD and MAX_REP_WIND_METHOD. Code 12 "
            "applies only to MAX_WIND_SPD_METHOD."
        ),
        values=(
            ("1", "Aircraft reconnaissance"),
            ("2", "Dropsonde"),
            ("3", "Ship estimate"),
            ("4", "Ship instrument"),
            ("5", "Other marine instrument (e.g. buoy)"),
            ("6", "Land estimate"),
            ("7", "Land instrument (other)"),
            ("8", "Land instrument (Dynes)"),
            ("9", "Land instrument (propeller)"),
            ("10", "Land instrument (not stated)"),
            ("11", "Satellite radar/scatterometer"),
            ("12", "Derived from pressure measurement"),
            ("13", "Dvorak estimate"),
            ("20", "Other"),
        ),
    ),
    Domain(
        code="max_wind_gust_method",
        label="Method used to estimate the maximum gust",
        description="How the maximum wind gust was obtained.",
        values=(
            ("1", "Estimate from mean wind"),
            ("2", "Direct observation"),
            ("3", "Impact analysis"),
            ("20", "Other"),
        ),
    ),
    Domain(
        code="mn_eye_rad_method",
        label="Method used to determine the eye radius",
        description="How the mean eye radius was estimated.",
        values=(
            ("1", "Satellite image with clear eye"),
            ("2", "Aircraft radar"),
            ("3", "Land-based radar"),
            ("4", "Direct observation"),
            ("20", "Other"),
        ),
    ),
    Domain(
        code="wave_swell_method",
        label="Method used to obtain wave or swell",
        description="Shared by MAX_REP_WAV_METHOD and MAX_REP_SWL_METHOD.",
        values=(
            ("1", "Ship estimate"),
            ("2", "Land estimate"),
            ("3", "Ocean instrument"),
            ("4", "Satellite radar/scatterometer"),
            ("5", "Aircraft"),
            ("6", "Other"),
        ),
    ),
    Domain(
        code="tide_anom_method",
        label="Method used to obtain the tidal anomaly",
        description="How the maximum reported tidal anomaly was obtained.",
        values=(
            ("1", "Subjective estimate"),
            ("2", "Post-analysis of debris"),
            ("3", "Instrument"),
            ("9", "Other"),
        ),
    ),
)

#: Which observation column resolves against which domain. Used to label coded
#: values in API responses and to report codes absent from the spec.
CODE_COLUMN_BINDINGS: dict[str, str] = {
    "type_code": "type",
    "data_src": "data_src",
    "surface_code": "surface_code",
    "cyc_type": "cyc_type",
    "position_method": "position_method",
    "central_pres_method": "central_pres_method",
    "pres_wind_relation_used": "pres_wind_relation_used",
    "mn_radius_max_wind_method": "radius_method",
    "mn_radius_gf_wind_method": "radius_method",
    "mn_radius_sf_wind_method": "radius_method",
    "mn_radius_hf_wind_method": "radius_method",
    "max_wind_spd_method": "wind_method",
    "max_rep_wind_method": "wind_method",
    "max_wind_gust_method": "max_wind_gust_method",
    "mn_eye_rad_method": "mn_eye_rad_method",
    "max_rep_wav_method": "wave_swell_method",
    "max_rep_swl_method": "wave_swell_method",
    "max_rep_tide_anom_method": "tide_anom_method",
}

#: Total seeded code values, asserted by the tests so an accidental edit to the
#: transcription above is visible.
TOTAL_CODE_VALUES = sum(len(d.values) for d in DOMAINS)


def seed_code_tables(session: Session) -> tuple[int, int]:
    """Insert or update every domain and code value. Idempotent.

    Returns ``(domains, values)`` written.
    """
    existing_domains = {
        d.code: d for d in session.execute(select(CodeDomain)).scalars()
    }
    domain_count = 0
    value_count = 0

    for spec in DOMAINS:
        domain = existing_domains.get(spec.code)
        if domain is None:
            domain = CodeDomain(code=spec.code)
            session.add(domain)
        domain.label = spec.label
        domain.description = spec.description
        session.flush()
        domain_count += 1

        existing_values = {
            v.code: v
            for v in session.execute(
                select(CodeValue).where(CodeValue.domain_id == domain.id)
            ).scalars()
        }
        for order, (code, description) in enumerate(spec.values):
            value = existing_values.get(code)
            if value is None:
                value = CodeValue(domain_id=domain.id, code=code)
                session.add(value)
            value.description = description
            value.sort_order = order
            value_count += 1

    session.flush()
    return domain_count, value_count


def describe(session: Session, domain_code: str, code: object) -> str | None:
    """Label for ``code`` in ``domain_code``, or None if unknown."""
    if code is None:
        return None
    text = str(code).strip()
    if not text:
        return None
    if text.endswith(".0"):
        text = text[:-2]
    return session.execute(
        select(CodeValue.description)
        .join(CodeDomain)
        .where(CodeDomain.code == domain_code, CodeValue.code == text)
    ).scalar_one_or_none()
