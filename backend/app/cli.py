"""Command-line entry point for schema bootstrap and ingest.

Run from ``backend/``::

    python -m app.cli all              # seed + ingest everything
    python -m app.cli verify           # assert the expected row counts
    python -m app.cli --help

Plain argparse rather than a CLI framework: eight subcommands do not justify
another dependency.

Schema truth lives in ``alembic/versions/``. ``init-db`` is a dev convenience
that calls ``create_all`` and is deliberately not the production path.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.enums import IngestKind, TrackDataset
from app.services.loaders.common import Stats, ingest_run

log = logging.getLogger("app.cli")

#: Row counts measured from the shipped data files. `verify` checks against
#: these so a silently truncated ingest is caught rather than assumed fine.
EXPECTED = {
    "disturbance": None,  # depends on which sources were loaded
    "best_track_observation (bom_best_track)": 31_706,
    "town": 466,
    "town_group_membership": 472,
    "code_value": 116,
}


def _session() -> Session:
    return SessionLocal()


def cmd_init_db(args: argparse.Namespace) -> int:
    """create_all, for a quick dev database. Prefer `alembic upgrade head`."""
    Base.metadata.create_all(engine)
    print("created", len(Base.metadata.tables), "tables via create_all")
    print("note: schema truth is alembic/versions; prefer `alembic upgrade head`")
    return 0


def cmd_seed_codes(args: argparse.Namespace) -> int:
    from app.services.loaders.codes_seed import seed_code_tables

    with _session() as session:
        source = "TC_Database_Structure_Oct2011.pdf"
        with ingest_run(session, IngestKind.CODES, source=source) as run:
            domains, values = seed_code_tables(session)
            run.rows_read = values
            run.rows_written = values
        session.commit()
    print(f"seeded {domains} code domains, {values} code values")
    return 0


def cmd_towns(args: argparse.Namespace) -> int:
    from app.services.loaders.towns import load_towns, read_towns_sheet

    path = Path(args.xlsx) if args.xlsx else None
    with _session() as session:
        stats = Stats()
        frame = read_towns_sheet(path)
        source = str(path or "towns.xlsx")
        with ingest_run(session, IngestKind.TOWNS, source=source) as run:
            counts = load_towns(session, frame, stats=stats)
            run.rows_read = counts["rows_read"]
            run.rows_written = counts["towns"]
            run.rows_skipped = counts["skipped"]
            run.stats = stats.as_dict()
        session.commit()
    print(
        f"{counts['rows_read']} sheet rows -> {counts['towns']} towns, "
        f"{counts['memberships']} group memberships "
        f"({counts['skipped']} blank rows skipped)"
    )
    for conflict in stats.conflicts:
        print("  conflict:", conflict)
    return 0


def cmd_best_track(args: argparse.Namespace) -> int:
    from app.services.loaders.best_track import load_best_track, read_best_track_csv

    path = Path(args.csv) if args.csv else None
    with _session() as session:
        stats = Stats()
        frame = read_best_track_csv(path)
        with ingest_run(
            session, IngestKind.BEST_TRACK, source=str(path or "best_track.csv")
        ) as run:
            counts = load_best_track(
                session,
                frame,
                dataset=TrackDataset.BOM_BEST_TRACK,
                ingest_run_id=run.id,
                stats=stats,
            )
            run.rows_read = counts["rows_read"]
            run.rows_written = counts["rows_written"]
            run.stats = stats.as_dict()
        session.commit()
    print(f"{counts['rows_read']} rows -> {counts['rows_written']} observations")
    _report_codes(stats)
    return 0


def cmd_otcr(args: argparse.Namespace) -> int:
    from app.services.loaders.otcr import load_otcr, read_otcr_csv

    path = Path(args.csv) if args.csv else None
    with _session() as session:
        stats = Stats()
        frame = read_otcr_csv(path)
        with ingest_run(session, IngestKind.OTCR, source=str(path or "OTCR")) as run:
            counts = load_otcr(session, frame, ingest_run_id=run.id, stats=stats)
            run.rows_read = counts["rows_read"]
            run.rows_written = counts["rows_written"]
            run.stats = stats.as_dict()
        session.commit()
    print(
        f"{counts['rows_read']} rows -> {counts['rows_written']} observations "
        "(reference only; never the interpolation input)"
    )
    _report_codes(stats)
    return 0


def cmd_gml(args: argparse.Namespace) -> int:
    from app.services.loaders.gml import DEFAULT_BATCH_FILES, load_bulletins

    with _session() as session:
        stats = Stats()
        source = args.region or "all regions"
        with ingest_run(session, IngestKind.GML, source=source) as run:
            counts = load_bulletins(
                session,
                region=args.region,
                limit=args.limit,
                force=args.force,
                ingest_run_id=run.id,
                stats=stats,
                batch_size=args.batch_size or DEFAULT_BATCH_FILES,
            )
            run.rows_read = counts["rows_read"]
            run.rows_written = counts["rows_written"]
            run.rows_skipped = counts["rows_skipped"]
            run.stats = stats.as_dict()
        session.commit()
    print(
        f"{counts['rows_read']} files -> {counts['rows_written']} written, "
        f"{counts['rows_skipped']} unchanged, {counts['no_key']} unusable"
    )
    if stats.unknown_enum:
        print("  unexpected values (stored verbatim):")
        for field, values in stats.unknown_enum.items():
            print(f"    {field}: {dict(values)}")
    return 0


def cmd_interpolate(args: argparse.Namespace) -> int:
    from app.services.loaders.interpolation import load_interpolation

    with _session() as session:
        stats = Stats()
        with ingest_run(
            session, IngestKind.INTERPOLATION, source="best_track_observation"
        ) as run:
            counts = load_interpolation(
                session,
                step_minutes=args.step_minutes,
                watch_warning_only=not args.all_disturbances,
                label=args.label,
                replace=args.replace,
                stats=stats,
            )
            run.rows_read = counts["rows_read"]
            run.rows_written = counts["rows_written"]
            run.stats = stats.as_dict()
        session.commit()
    print(
        f"run {counts['run_id']}: {counts['rows_read']} observations -> "
        f"{counts['rows_written']} points at {args.step_minutes}-minute spacing"
    )
    if stats.notes.get("replaced_runs"):
        print(f"  replaced {stats.notes['replaced_runs']} earlier run(s)")
    return 0


def cmd_verification(args: argparse.Namespace) -> int:
    from app.services.loaders.interpolation import latest_run_id
    from app.services.loaders.verification import (
        compute_verification,
        load_verification,
    )

    directory = Path(args.dir) if args.dir else None
    with _session() as session:
        stats = Stats()
        source = str(directory) if directory else "database"
        with ingest_run(session, IngestKind.VERIFICATION, source=source) as run:
            if directory is None:
                # Scored from the server's own towns, bulletins and track, so
                # the result does not depend on who runs it.
                counts = compute_verification(
                    session,
                    interpolation_run_id=args.interpolation_run,
                    label=args.label,
                    replace=args.replace,
                    keep_table_b=args.keep_table_b,
                    stats=stats,
                )
            else:
                counts = load_verification(
                    session,
                    directory=directory,
                    interpolation_run_id=latest_run_id(session),
                    label=args.label,
                    replace=args.replace,
                    stats=stats,
                )
            run.rows_written = counts["rows_written"]
            run.stats = stats.as_dict()
        session.commit()
    print(f"run {counts['run_id']}: {counts['rows_written']} rows")
    if stats.notes.get("replaced_runs"):
        print(f"  replaced {stats.notes['replaced_runs']} earlier run(s)")
    keys = (
        "table_a",
        "table_b",
        "table_c",
        "table_d",
        "summaries",
        "skipped_disturbances",
    )
    for key in keys:
        if key in counts:
            print(f"  {key}: {counts[key]}")
    for conflict in stats.conflicts:
        print("  conflict:", conflict)
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    """Everything, in dependency order.

    Safe to re-run against a populated database: the reference loaders upsert,
    the GML loader skips unchanged files, and the interpolation and
    verification steps replace their previous "cli all" run.
    """
    steps = [
        ("code tables", cmd_seed_codes, argparse.Namespace()),
        ("towns", cmd_towns, argparse.Namespace(xlsx=None)),
        ("best track", cmd_best_track, argparse.Namespace(csv=None)),
        ("OTCR reference", cmd_otcr, argparse.Namespace(csv=None)),
        (
            "GML bulletins",
            cmd_gml,
            argparse.Namespace(region=None, limit=None, force=False, batch_size=None),
        ),
        (
            "interpolation",
            cmd_interpolate,
            argparse.Namespace(
                step_minutes=15,
                all_disturbances=False,
                label="cli all",
                replace=True,
            ),
        ),
        (
            "verification",
            cmd_verification,
            argparse.Namespace(
                dir=None,
                interpolation_run=None,
                label="cli all",
                replace=True,
                keep_table_b=False,
            ),
        ),
    ]
    for name, handler, namespace in steps:
        print(f"\n=== {name} ===")
        try:
            handler(namespace)
        except Exception as exc:  # noqa: BLE001 - report and continue
            # The GML bulletins must precede interpolation (its watch/warning
            # filter needs them), so one failure should not hide the rest.
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            if args.strict:
                return 1
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Assert the row counts measured from the shipped data files."""
    from app.models.best_track import BestTrackObservation
    from app.models.codes import CodeValue
    from app.models.disturbance import Disturbance
    from app.models.gml import Bulletin, BulletinArea, BulletinFix, BulletinTrack
    from app.models.interpolation import InterpolatedPoint
    from app.models.town import Town, TownGroupMembership
    from app.models.verification import VerificationPair

    checks: list[tuple[str, int, int | None]] = []
    with _session() as session:

        def count(model, *where) -> int:
            return session.execute(
                select(func.count()).select_from(model).where(*where)
            ).scalar_one()

        checks.append(("code_value", count(CodeValue), 116))
        checks.append(("town", count(Town), 466))
        checks.append(("town_group_membership", count(TownGroupMembership), 472))
        checks.append(
            (
                "best_track_observation (bom)",
                count(
                    BestTrackObservation,
                    BestTrackObservation.dataset == TrackDataset.BOM_BEST_TRACK.value,
                ),
                31_706,
            )
        )
        checks.append(
            (
                "best_track_observation (otcr)",
                count(
                    BestTrackObservation,
                    BestTrackObservation.dataset == TrackDataset.OTCR_REANALYSIS.value,
                ),
                13_743,
            )
        )
        checks.append(("bulletin", count(Bulletin), 3_448))
        checks.append(("bulletin_track", count(BulletinTrack), None))
        checks.append(("bulletin_fix", count(BulletinFix), None))
        checks.append(("bulletin_area", count(BulletinArea), None))
        checks.append(("interpolated_point", count(InterpolatedPoint), None))
        checks.append(("verification_pair", count(VerificationPair), None))
        checks.append(
            (
                "disturbance (with best track)",
                count(Disturbance, Disturbance.has_best_track.is_(True)),
                1_133,
            )
        )
        checks.append(
            (
                "disturbance (with bulletins)",
                count(Disturbance, Disturbance.bulletin_count > 0),
                136,
            )
        )
        checks.append(
            (
                "bulletins but no best track",
                count(
                    Disturbance,
                    Disturbance.bulletin_count > 0,
                    Disturbance.has_best_track.is_(False),
                ),
                30,
            )
        )

    failures = 0
    print(f"{'check':<34}{'actual':>10}{'expected':>10}  result")
    for name, actual, expected in checks:
        if expected is None:
            print(f"{name:<34}{actual:>10}{'-':>10}  ")
            continue
        ok = actual == expected
        failures += not ok
        print(f"{name:<34}{actual:>10}{expected:>10}  {'ok' if ok else 'MISMATCH'}")
    if failures:
        print(f"\n{failures} check(s) failed")
    return 1 if failures else 0


def _report_codes(stats: Stats) -> None:
    reported = {k: dict(v) for k, v in stats.unknown_code.items() if v}
    if reported:
        print("  codes absent from the 2011 spec (stored anyway):")
        for field, values in reported.items():
            print(f"    {field}: {values}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Bootstrap and populate the cyclone verification database.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="log progress at INFO"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser(
        "init-db", help="create_all (dev only; prefer alembic upgrade head)"
    )
    init.set_defaults(handler=cmd_init_db)
    sub.add_parser("seed-codes", help="seed the BoM code lookup tables").set_defaults(
        handler=cmd_seed_codes
    )

    towns = sub.add_parser("towns", help="load data/towns.xlsx")
    towns.add_argument("--xlsx")
    towns.set_defaults(handler=cmd_towns)

    best = sub.add_parser("best-track", help="load data/best_track.csv")
    best.add_argument("--csv")
    best.set_defaults(handler=cmd_best_track)

    otcr = sub.add_parser("otcr", help="load the OTCR reanalysis (reference only)")
    otcr.add_argument("--csv")
    otcr.set_defaults(handler=cmd_otcr)

    gml = sub.add_parser("gml", help="load the GML bulletins")
    gml.add_argument("--region", choices=["NT", "QLD", "WA"])
    gml.add_argument("--limit", type=int)
    gml.add_argument(
        "--force", action="store_true", help="re-parse even if the hash matches"
    )
    gml.add_argument(
        "--batch-size",
        type=int,
        help="files written per transaction (default: 200)",
    )
    gml.set_defaults(handler=cmd_gml)

    interp = sub.add_parser("interpolate", help="run and store an interpolation")
    interp.add_argument("--step-minutes", type=int, default=15)
    interp.add_argument("--label")
    interp.add_argument(
        "--all-disturbances",
        action="store_true",
        help="do not restrict to watch/warning systems",
    )
    interp.add_argument(
        "--replace",
        action="store_true",
        help="delete earlier runs with the same --label first",
    )
    interp.set_defaults(handler=cmd_interpolate)

    verif = sub.add_parser(
        "verification", help="score the forecasts from the database contents"
    )
    verif.add_argument(
        "--dir",
        help="import precomputed contingency CSVs from here instead of computing",
    )
    verif.add_argument(
        "--interpolation-run",
        type=int,
        help="interpolation run to score against (default: the latest)",
    )
    verif.add_argument(
        "--keep-table-b",
        action="store_true",
        help="also store Table B, the per-timestep wind-radii distances "
        "(~93%% of the rows; not needed for the scores)",
    )
    verif.add_argument("--label")
    verif.add_argument(
        "--replace",
        action="store_true",
        help="delete earlier runs with the same label first",
    )
    verif.set_defaults(handler=cmd_verification)

    everything = sub.add_parser("all", help="seed and ingest everything, in order")
    everything.add_argument(
        "--strict", action="store_true", help="stop at the first failing step"
    )
    everything.set_defaults(handler=cmd_all)

    sub.add_parser("verify", help="assert the expected row counts").set_defaults(
        handler=cmd_verify
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
