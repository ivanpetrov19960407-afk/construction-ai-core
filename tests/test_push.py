"""Tests for web push subscription and delivery."""

from __future__ import annotations

import shutil
import subprocess

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.main import app
from config.settings import settings


def test_subscribe_stores_subscription(tmp_path):
    old_database_url = settings.database_url
    old_api_keys = settings.api_keys
    settings.database_url = f"sqlite:///{tmp_path / 'push.db'}"
    settings.api_keys = ["push-key"]

    payload = {
        "org_id": "org-1",
        "subscription": {
            "endpoint": "https://example.test/sub/1",
            "keys": {
                "p256dh": "p256dh-key",
                "auth": "auth-key",
            },
        },
    }

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/push/subscribe",
                json=payload,
                headers={"X-API-Key": "push-key"},
            )

        engine = create_engine(settings.database_url, future=True)
        with engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT org_id, endpoint, p256dh, auth FROM push_subscriptions "
                        "WHERE endpoint = :endpoint"
                    ),
                    {"endpoint": payload["subscription"]["endpoint"]},
                )
                .mappings()
                .one()
            )
    finally:
        settings.database_url = old_database_url
        settings.api_keys = old_api_keys

    assert response.status_code == 200
    assert row["org_id"] == "org-1"
    assert row["p256dh"] == "p256dh-key"
    assert row["auth"] == "auth-key"


def test_send_push_calls_pywebpush(monkeypatch, tmp_path):
    from api.routes import web_push

    old_database_url = settings.database_url
    old_api_keys = settings.api_keys
    old_admin_api_keys = settings.admin_api_keys
    old_vapid_public = settings.vapid_public_key
    old_vapid_private = settings.vapid_private_key

    settings.database_url = f"sqlite:///{tmp_path / 'push-send.db'}"
    settings.api_keys = ["push-key"]
    settings.admin_api_keys = ["push-key"]
    settings.vapid_public_key = "public"
    settings.vapid_private_key = "private"

    calls: list[dict] = []

    def _fake_webpush(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(web_push, "webpush", _fake_webpush)

    subscribe_payload = {
        "org_id": "org-2",
        "subscription": {
            "endpoint": "https://example.test/sub/2",
            "keys": {
                "p256dh": "p256dh-key-2",
                "auth": "auth-key-2",
            },
        },
    }
    send_payload = {
        "org_id": "org-2",
        "title": "Alert",
        "body": "Delayed section",
        "url": "/web/projects/1",
    }

    try:
        with TestClient(app) as client:
            sub_resp = client.post(
                "/api/push/subscribe",
                json=subscribe_payload,
                headers={"X-API-Key": "push-key"},
            )
            send_resp = client.post(
                "/api/push/send",
                json=send_payload,
                headers={"X-API-Key": "push-key"},
            )
    finally:
        settings.database_url = old_database_url
        settings.api_keys = old_api_keys
        settings.admin_api_keys = old_admin_api_keys
        settings.vapid_public_key = old_vapid_public
        settings.vapid_private_key = old_vapid_private

    assert sub_resp.status_code == 200
    assert send_resp.status_code == 200
    assert send_resp.json()["sent"] == 1
    assert len(calls) == 1
    assert calls[0]["subscription_info"]["endpoint"] == "https://example.test/sub/2"


def test_sw_cache_strategy():
    sw_path = "web/sw.js"
    source = open(sw_path, encoding="utf-8").read()

    assert 'const CACHE_NAME = "construction-ai-v2"' in source
    assert "fetch(event.request).catch(() => caches.match(event.request))" in source
    assert 'self.addEventListener("push"' in source

    node_bin = shutil.which("node")
    if node_bin is None:
        return

    result = subprocess.run(
        [node_bin, "--check", sw_path],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
