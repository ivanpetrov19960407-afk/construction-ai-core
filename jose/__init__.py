"""Minimal local jose-compatible interface for offline environments."""

from .jwt import JWTError as JWTError
from .jwt import decode, encode

__all__ = ["JWTError", "jwt"]


class _JWTModule:
    encode = staticmethod(encode)
    decode = staticmethod(decode)


jwt = _JWTModule()
