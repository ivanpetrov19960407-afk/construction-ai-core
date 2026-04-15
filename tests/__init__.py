"""Test package setup."""

from config.settings import settings

# Ensure app startup validation passes in tests.
settings.jwt_secret = "test-jwt-secret-for-ci-0123456789abcdef"
