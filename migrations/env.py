from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import MetaData, engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

db_url = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

# Empty target metadata: the project uses hand-written migrations and does not
# rely on autogenerate. An empty MetaData combined with the ``include_object``
# hook below keeps ``alembic check`` idempotent (no spurious diffs) once the
# DB is stamped at head.
target_metadata = MetaData()


def _include_object(object_, name, type_, reflected, compare_to):
    # We do not maintain SQLAlchemy models alongside the hand-written
    # migrations, so ``alembic check`` must not treat any reflected DB
    # object as a "removed" object. Skip anything that exists only in the
    # database (``compare_to is None``) to avoid false positives.
    if reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=_include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
