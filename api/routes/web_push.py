"""Web Push subscription and delivery endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import create_engine, text

from config.settings import settings

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - validated in runtime/tests by monkeypatch
    WebPushException = RuntimeError
    webpush = None

router = APIRouter(prefix="/api/push", tags=["push"])


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionBody(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys


class PushSubscribeRequest(BaseModel):
    subscription: PushSubscriptionBody
    org_id: str = "default"


class PushSendRequest(BaseModel):
    org_id: str
    title: str = "Construction AI"
    body: str
    url: str = "/"


@dataclass(slots=True)
class PushSubscriptionRecord:
    endpoint: str
    p256dh: str
    auth: str


def _ensure_push_subscriptions_table() -> None:
    engine = create_engine(settings.database_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id TEXT PRIMARY KEY,
                    org_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL UNIQUE,
                    p256dh TEXT NOT NULL,
                    auth TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """,
            ),
        )


def _require_admin(request: Request) -> None:
    if getattr(request.state, "user_role", None) == "admin":
        return
    api_key = request.headers.get("X-API-Key", "")
    if api_key and api_key in settings.admin_api_keys:
        return
    raise HTTPException(status_code=403, detail="Admin role required")


def _load_org_subscriptions(org_id: str) -> list[PushSubscriptionRecord]:
    _ensure_push_subscriptions_table()
    engine = create_engine(settings.database_url, future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT endpoint, p256dh, auth
                FROM push_subscriptions
                WHERE org_id = :org_id
                ORDER BY created_at DESC
                """,
            ),
            {"org_id": org_id},
        ).mappings()
        return [PushSubscriptionRecord(**row) for row in rows]


async def send_push_to_org(org_id: str, payload: dict[str, str]) -> int:
    """Send web push payload to all subscriptions of an org."""
    if webpush is None:
        raise HTTPException(status_code=503, detail="pywebpush is not installed")

    subs = _load_org_subscriptions(org_id)
    if not subs:
        return 0

    vapid_private_key = settings.vapid_private_key.strip()
    vapid_public_key = settings.vapid_public_key.strip()
    if not vapid_private_key or not vapid_public_key:
        raise HTTPException(status_code=503, detail="VAPID keys are not configured")

    sent = 0
    engine = create_engine(settings.database_url, future=True)
    for sub in subs:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {
                "p256dh": sub.p256dh,
                "auth": sub.auth,
            },
        }
        try:
            push_data = PushSendRequest.model_validate({"org_id": org_id, **payload})
            webpush(
                subscription_info=subscription_info,
                data=push_data.model_dump_json(),
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": f"mailto:{settings.vapid_claims_email}"},
            )
            sent += 1
        except WebPushException:
            with engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM push_subscriptions WHERE endpoint = :endpoint"),
                    {"endpoint": sub.endpoint},
                )
    return sent


@router.post("/subscribe")
async def subscribe_push(payload: PushSubscribeRequest) -> dict[str, bool]:
    _ensure_push_subscriptions_table()
    engine = create_engine(settings.database_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO push_subscriptions (id, org_id, endpoint, p256dh, auth, created_at)
                VALUES (:id, :org_id, :endpoint, :p256dh, :auth, CURRENT_TIMESTAMP)
                ON CONFLICT(endpoint) DO UPDATE SET
                    org_id = excluded.org_id,
                    p256dh = excluded.p256dh,
                    auth = excluded.auth
                """,
            ),
            {
                "id": str(uuid4()),
                "org_id": payload.org_id,
                "endpoint": payload.subscription.endpoint,
                "p256dh": payload.subscription.keys.p256dh,
                "auth": payload.subscription.keys.auth,
            },
        )
    return {"ok": True}


@router.post("/send")
async def send_push(payload: PushSendRequest, request: Request) -> dict[str, Any]:
    _require_admin(request)
    sent = await send_push_to_org(
        payload.org_id,
        {
            "title": payload.title,
            "body": payload.body,
            "url": payload.url,
        },
    )
    return {"ok": True, "sent": sent}
