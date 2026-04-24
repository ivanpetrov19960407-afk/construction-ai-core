"""Deprecation-warning tests for legacy scope/role keys in ResearcherAgent."""

from __future__ import annotations

import warnings

import pytest

from agents.researcher import ResearcherAgent
from agents.researcher.errors import ResearchScopeError


def test_legacy_scope_triggers_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with pytest.raises(ResearchScopeError):
            ResearcherAgent._resolve_access_scope({"scope": "pto_engineer"})
    assert any(issubclass(w.category, DeprecationWarning) for w in recorded)


def test_legacy_role_triggers_deprecation_warning() -> None:
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with pytest.raises(ResearchScopeError):
            ResearcherAgent._resolve_access_scope({"role": "foreman"})
    assert any(issubclass(w.category, DeprecationWarning) for w in recorded)


def test_explicit_access_scope_emits_no_warning() -> None:
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        scope = ResearcherAgent._resolve_access_scope({"access_scope": "public"})
    assert scope == "public"
    assert not any(issubclass(w.category, DeprecationWarning) for w in recorded)
