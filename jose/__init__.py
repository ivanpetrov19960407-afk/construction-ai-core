"""Minimal local jose-compatible interface for offline environments."""

from .jwt import JWTError, decode, encode

class _JWTModule:
    encode = staticmethod(encode)
    decode = staticmethod(decode)

jwt = _JWTModule()
