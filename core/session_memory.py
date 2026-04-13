"""SQLite-хранилище истории сообщений сессии и документов."""

from __future__ import annotations

from datetime import datetime, timezone

from config.settings import settings
from core.database import get_db


class SessionMemory:
    """Хранилище истории по session_id в SQLite."""

    def __init__(self, max_messages: int = 50, db_path: str | None = None) -> None:
        self.max_messages = max_messages
        self.db_path = db_path or settings.sqlite_db_path

    async def _ensure_session(self, session_id: str, role: str, timestamp: str) -> None:
        async with get_db(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions (id, role, created_at, last_active)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    role = excluded.role,
                    last_active = excluded.last_active
                """,
                (session_id, role, timestamp, timestamp),
            )
            await db.commit()

    async def add(self, session_id: str, role: str, content: str) -> None:
        """Добавить сообщение в историю сессии."""
        timestamp = datetime.now(timezone.utc).isoformat()  # noqa: UP017
        await self._ensure_session(session_id=session_id, role=role, timestamp=timestamp)

        async with get_db(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO messages (session_id, role, content, agent_id, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, role, content, None, timestamp),
            )
            await db.execute(
                """
                DELETE FROM messages
                WHERE id IN (
                    SELECT id FROM messages
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (session_id, self.max_messages),
            )
            await db.execute(
                "UPDATE sessions SET last_active = ? WHERE id = ?",
                (timestamp, session_id),
            )
            await db.commit()

    async def get(self, session_id: str, last_n: int = 10) -> list[dict[str, str]]:
        """Вернуть последние N сообщений сессии."""
        if last_n <= 0:
            return []

        async with get_db(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT role, content, timestamp
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, last_n),
            )
            rows = await cursor.fetchall()

        rows_list = list(rows)
        return [dict(row) for row in reversed(rows_list)]

    async def clear(self, session_id: str) -> None:
        """Очистить историю и документы конкретной сессии."""
        async with get_db(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM documents WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await db.commit()

    async def get_session_documents(self, session_id: str) -> list[dict]:
        """Получить список документов сессии (новые первыми)."""
        async with get_db(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT id, session_id, doc_type, filename, docx_bytes, sha256, created_at
                FROM documents
                WHERE session_id = ?
                ORDER BY id DESC
                """,
                (session_id,),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def save_document(
        self,
        session_id: str,
        doc_type: str,
        filename: str,
        docx_bytes: bytes,
        sha256: str | None,
    ) -> None:
        """Сохранить сгенерированный документ в SQLite."""
        timestamp = datetime.now(timezone.utc).isoformat()  # noqa: UP017
        await self._ensure_session(session_id=session_id, role="assistant", timestamp=timestamp)

        async with get_db(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO documents (
                    session_id, doc_type, filename, docx_bytes, sha256, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, doc_type, filename, docx_bytes, sha256, timestamp),
            )
            await db.execute(
                "UPDATE sessions SET last_active = ? WHERE id = ?",
                (timestamp, session_id),
            )
            await db.commit()
