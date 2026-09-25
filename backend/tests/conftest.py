"""Shared test fixtures.

The engine is a **temp file**, not ``sqlite:///:memory:``. The PRAGMAs in
``app.db.session`` and the multi-connection behaviour they affect only
reproduce against a real file, and one of the things these tests assert is
that foreign-key enforcement is actually switched on.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_db
from app.db.base import Base
from app.main import app
from app.services.loaders.codes_seed import seed_code_tables

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
FIXTURES = Path(__file__).parent / "fixtures"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "requires_data: needs the git-ignored files under data/ to be present",
    )


@pytest.fixture(scope="session")
def engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Engine]:
    path = tmp_path_factory.mktemp("db") / "test.db"
    eng = create_engine(f"sqlite+pysqlite:///{path}", future=True)
    import app.models  # noqa: F401  # registers every table

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """An isolated session: every table is emptied afterwards.

    Wrapping each test in an outer transaction and rolling it back is the
    usual trick, but it does not hold here -- the GML loader commits once per
    file on purpose, so a failure part-way through a 3,448-file pass does not
    discard the work already done, and those commits escape the savepoint.
    Deleting the rows afterwards is unconditional and cheap at this scale.
    """
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        _truncate_all(engine)


def _truncate_all(engine: Engine) -> None:
    """Empty every table, children first so the foreign keys stay satisfied."""
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture
def seeded_db(db: Session) -> Session:
    """A session with the code lookup tables populated."""
    seed_code_tables(db)
    db.flush()
    return db


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """A TestClient whose requests share the test's rolled-back session."""

    def override() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session")
def best_track_csv() -> Path:
    """The real best-track CSV, or skip."""
    path = DATA_DIR / "best_track.csv"
    if not path.is_file():
        pytest.skip(f"{path} is not present (data/ is git-ignored)")
    return path


@pytest.fixture(scope="session")
def towns_xlsx() -> Path:
    path = DATA_DIR / "towns.xlsx"
    if not path.is_file():
        pytest.skip(f"{path} is not present (data/ is git-ignored)")
    return path


@pytest.fixture(scope="session")
def a_gml_file() -> Path:
    """Any real GML bulletin that has an area section, or skip."""
    for region in ("QLD", "NT", "WA"):
        directory = DATA_DIR / f"{region}_GMLs"
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.gml")):
            return path
    pytest.skip("no GML bulletins present (data/ is git-ignored)")
