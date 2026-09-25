"""Alembic environment.

The database URL comes from ``app.core.config.settings`` rather than
``alembic.ini`` so that one environment variable drives the application, the
tests and the migrations alike.

``render_as_batch=True`` is set here from the start rather than being
discovered on the second migration: SQLite cannot ``ALTER`` a constraint, so
Alembic has to recreate whole tables, and that only works because
``app.db.base`` gives every constraint an explicit name.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.db.base import Base

# Importing the package (not individual modules) registers every table on
# Base.metadata and resolves the cross-module relationships. Without it
# autogenerate would cheerfully emit a migration that drops everything.
import app.models  # noqa: F401  # isort: skip

config = context.config

# ConfigParser interpolates "%", which appears in URL-encoded passwords.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

COMMON_OPTS = {
    "target_metadata": target_metadata,
    "compare_type": True,
    "compare_server_default": True,
    "render_as_batch": True,
}


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **COMMON_OPTS,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, **COMMON_OPTS)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
