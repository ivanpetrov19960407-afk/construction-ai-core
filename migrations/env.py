"""Alembic environment for Construction AI Core migrations."""

from __future__ import annotations

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from core.projects import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Track SQLAlchemy models from the project.
target_metadata = Base.metadata


def _get_database_url() -> str:
    return os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")


def _include_object(object_, name, type_, reflected, compare_to):
    """Compare only tables represented in SQLAlchemy metadata.

    The project still has legacy/raw-SQL tables not tracked by ORM models; those
    should not trigger Alembic drift failures.
    """
    if type_ == "table":
        return name in target_metadata.tables

    if type_ in {"column", "index", "unique_constraint", "foreign_key_constraint"}:
        table_name = None
        if getattr(object_, "table", None) is not None:
            table_name = object_.table.name
        elif getattr(compare_to, "table", None) is not None:
            table_name = compare_to.table.name
        return table_name in target_metadata.tables

    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=_get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _get_database_url()

    connectable = engine_from_config(
        section,
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
