"""Утилиты работы с SQLite для хранения сессий и документов."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

_SHARED_MEMORY_URI = "file:construction_ai_core_memdb?mode=memory&cache=shared"
_memory_keepalive: aiosqlite.Connection | None = None


def _is_sqlite_uri(db_path: str) -> bool:
    return db_path.startswith("file:")


def _normalize_db_path(db_path: str) -> tuple[str, bool]:
    if db_path == ":memory:":
        return _SHARED_MEMORY_URI, True
    return db_path, _is_sqlite_uri(db_path)


@asynccontextmanager
async def get_db(db_path: str) -> AsyncIterator[aiosqlite.Connection]:
    """Вернуть контекстный менеджер подключения к SQLite."""
    resolved_path, use_uri = _normalize_db_path(db_path)
    if not use_uri:
        Path(resolved_path).parent.mkdir(parents=True, exist_ok=True)

    connection = await aiosqlite.connect(resolved_path, uri=use_uri)
    connection.row_factory = aiosqlite.Row
    await connection.execute("PRAGMA foreign_keys = ON;")
    try:
        yield connection
    finally:
        await connection.close()


async def init_db(db_path: str) -> None:
    """Инициализировать таблицы хранилища сессий."""
    global _memory_keepalive
    resolved_path, use_uri = _normalize_db_path(db_path)
    if db_path == ":memory:" and _memory_keepalive is None:
        _memory_keepalive = await aiosqlite.connect(resolved_path, uri=use_uri)
        _memory_keepalive.row_factory = aiosqlite.Row
        await _memory_keepalive.execute("PRAGMA foreign_keys = ON;")

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
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_session_links (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              telegram_user_id TEXT NOT NULL UNIQUE,
              user_id TEXT NOT NULL,
              session_id TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id TEXT NOT NULL,
              telegram_user_id TEXT,
              session_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              title TEXT NOT NULL,
              body TEXT NOT NULL,
              created_at TEXT NOT NULL,
              is_read INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        await db.commit()
