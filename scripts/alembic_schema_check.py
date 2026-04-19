"""Fail if SQLAlchemy models diverge from Alembic-managed schema."""

from __future__ import annotations

import os
import sys

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from core.projects import Base


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required for Alembic schema check.", file=sys.stderr)
        return 2

    engine = create_engine(database_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diffs = compare_metadata(context, Base.metadata)

    if diffs:
        print("Detected schema drift between models and migrations:", file=sys.stderr)
        for diff in diffs:
            print(f" - {diff!r}", file=sys.stderr)
        return 1

    print("No schema drift detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
