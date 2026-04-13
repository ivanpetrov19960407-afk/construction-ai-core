"""Утилиты работы с SQLite для хранения сессий и документов."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


def _is_sqlite_uri(db_path: str) -> bool:
    return db_path.startswith("file:")


@asynccontextmanager
async def get_db(db_path: str) -> AsyncIterator[aiosqlite.Connection]:
    """Вернуть контекстный менеджер подключения к SQLite."""
    if not _is_sqlite_uri(db_path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    connection = await aiosqlite.connect(db_path, uri=_is_sqlite_uri(db_path))
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys = ON;")
    try:
        yield connection
    finally:
        await connection.close()


async def init_db(db_path: str) -> None:
    """Инициализировать таблицы хранилища сессий."""
    async with get_db(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY,
              role TEXT NOT NULL,
              created_at TEXT NOT NULL,
              last_active TEXT NOT NULL
            );
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL,
              role TEXT NOT NULL,
              content TEXT NOT NULL,
              agent_id TEXT,
              timestamp TEXT NOT NULL,
              FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL,
              doc_type TEXT NOT NULL,
              filename TEXT NOT NULL,
              docx_bytes BLOB,
              sha256 TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            """
        )
        await db.commit()
