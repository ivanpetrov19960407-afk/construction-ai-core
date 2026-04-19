"""Security helpers for JWT and password hashing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import bcrypt


class JWTError(Exception):
    """JWT decoding/validation errors."""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("utf-8")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def encode_jwt(payload: dict[str, object], key: str, algorithm: str = "HS256") -> str:
    """Encode a JWT using HS256."""
    if algorithm != "HS256":
        raise JWTError("Unsupported algorithm")

    header = {"alg": "HS256", "typ": "JWT"}
    header_segment = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_segment = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_segment}.{payload_segment}".encode()
    signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_segment}.{payload_segment}.{_b64url_encode(signature)}"


def decode_jwt(token: str, key: str, algorithms: list[str] | None = None) -> dict[str, object]:
    """Decode and validate a JWT signed with HS256."""
    allowed_algorithms = algorithms or ["HS256"]
    if "HS256" not in allowed_algorithms:
        raise JWTError("Unsupported algorithm")

    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise JWTError("Malformed token") from exc

    signing_input = f"{header_segment}.{payload_segment}".encode()
    expected_signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_signature = _b64url_decode(signature_segment)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise JWTError("Invalid signature")

    payload_raw = _b64url_decode(payload_segment)
    payload = json.loads(payload_raw.decode("utf-8"))
    exp = payload.get("exp")
    if isinstance(exp, int | float) and exp < time.time():
        raise JWTError("Token expired")
    return payload


def hash_password(password: str) -> str:
    """Hash password using adaptive bcrypt with salt."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
