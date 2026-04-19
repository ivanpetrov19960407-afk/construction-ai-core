"""Linking between Telegram and desktop sessions + notification storage."""

from __future__ import annotations

from datetime import datetime, timezone

from api.security import JWTError, decode_jwt, encode_jwt
from config.settings import settings
from core.database import get_db

UTC = getattr(datetime, "UTC", timezone.utc)


class InvalidTelegramLinkTokenError(ValueError):
    """Raised when telegram link token cannot be validated."""


def issue_telegram_link_token(telegram_user_id: int, session_id: str) -> str:
    """Create a short-lived token that desktop can exchange via /api/link/telegram."""
    payload: dict[str, object] = {
        "kind": "telegram_link",
        "telegram_user_id": str(telegram_user_id),
        "session_id": session_id,
    }
    return encode_jwt(payload, settings.jwt_secret)


def parse_telegram_link_token(token: str) -> tuple[str, str]:
    """Validate and decode telegram link token."""
    try:
        payload = decode_jwt(token, settings.jwt_secret)
    except JWTError as exc:
        raise InvalidTelegramLinkTokenError("invalid token") from exc

    if payload.get("kind") != "telegram_link":
        raise InvalidTelegramLinkTokenError("unexpected token kind")

    telegram_user_id = str(payload.get("telegram_user_id", "")).strip()
    session_id = str(payload.get("session_id", "")).strip()
    if not telegram_user_id or not session_id:
        raise InvalidTelegramLinkTokenError("token missing required fields")
    return telegram_user_id, session_id


async def upsert_telegram_link(telegram_user_id: str, user_id: str, session_id: str) -> None:
    """Persist mapping telegram_user_id ↔ desktop user_id ↔ session_id."""
    now = datetime.now(UTC).isoformat()
    async with get_db(settings.sqlite_db_path) as db:
        await db.execute(
            """
            INSERT INTO telegram_session_links (
                telegram_user_id, user_id, session_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id)
            DO UPDATE SET
                user_id = excluded.user_id,
                session_id = excluded.session_id,
                updated_at = excluded.updated_at
            """,
            (telegram_user_id, user_id, session_id, now, now),
        )
        await db.commit()


async def create_notification(
    *,
    user_id: str,
    telegram_user_id: str | None,
    session_id: str,
    event_type: str,
    title: str,
    body: str,
) -> None:
    """Store a notification for desktop polling."""
    now = datetime.now(UTC).isoformat()
    async with get_db(settings.sqlite_db_path) as db:
        await db.execute(
            """
            INSERT INTO notifications (
                user_id, telegram_user_id, session_id, event_type, title, body, created_at, is_read
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (user_id, telegram_user_id, session_id, event_type, title, body, now),
        )
        await db.commit()


async def create_document_ready_notification_for_session(*, session_id: str, doc_type: str) -> None:
    """Create desktop notification when bot-generated document is ready."""
    async with get_db(settings.sqlite_db_path) as db:
        cursor = await db.execute(
            """
            SELECT telegram_user_id, user_id, session_id
            FROM telegram_session_links
            WHERE telegram_user_id = ? OR session_id = ?
            LIMIT 1
            """,
            (session_id, session_id),
        )
        row = await cursor.fetchone()

    if row is None:
        return

    user_id = str(row["user_id"])
    telegram_user_id = str(row["telegram_user_id"])
    mapped_session_id = str(row["session_id"])
    await create_notification(
        user_id=user_id,
        telegram_user_id=telegram_user_id,
        session_id=mapped_session_id,
        event_type="document_ready",
        title="Документ готов в Telegram-боте",
        body=f"Сформирован документ типа '{doc_type}' для связанной сессии.",
    )


async def fetch_and_mark_notifications(user_id: str, limit: int = 20) -> list[dict[str, str]]:
    """Fetch unread notifications and mark them as read."""
    async with get_db(settings.sqlite_db_path) as db:
        cursor = await db.execute(
            """
            SELECT id, user_id, telegram_user_id, session_id, event_type, title, body, created_at
            FROM notifications
            WHERE user_id = ? AND is_read = 0
            ORDER BY id ASC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = await cursor.fetchall()

        if rows:
            notification_ids = [str(int(row["id"])) for row in rows]
            placeholders = ",".join("?" for _ in notification_ids)
            await db.execute(
                f"UPDATE notifications SET is_read = 1 WHERE id IN ({placeholders})",
                notification_ids,
            )
            await db.commit()

    return [
        {
            "id": str(int(row["id"])),
            "user_id": str(row["user_id"]),
            "telegram_user_id": str(row["telegram_user_id"] or ""),
            "session_id": str(row["session_id"]),
            "event_type": str(row["event_type"]),
            "title": str(row["title"]),
            "body": str(row["body"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]
