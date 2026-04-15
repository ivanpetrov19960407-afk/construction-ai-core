"""Shared API models."""

from pydantic import BaseModel


class UserCreate(BaseModel):
    """Payload for creating a new user."""

    username: str
    password: str
    invite_code: str


class UserLogin(BaseModel):
    """Payload for user login."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT response returned by login."""

    access_token: str
    token_type: str
    expires_in: int
    role: str
