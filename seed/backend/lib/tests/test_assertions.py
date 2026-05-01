"""Tests for `noctusai_lib.testing.assert_error_contains`.

Pins the platform-or-FastAPI error-shape extraction across the two
shapes products encounter: the platform exception-handler wrapper
(`{"error": {"code": ..., "message": ...}}`) and FastAPI's default
(`{"detail": ...}`).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from noctusai_lib.testing import assert_error_contains


class _FakeResponse:
    """Minimal stand-in for `httpx.Response` / `TestClient` response."""

    def __init__(self, body: dict):
        self._body = body

    def json(self) -> dict:
        return self._body


class TestAssertErrorContains:
    def test_matches_platform_error_shape(self):
        resp = _FakeResponse({"error": {"code": "BLOCKED", "message": "Usuário bloqueado. Não é possível enviar"}})
        assert_error_contains(resp, "bloqueado")

    def test_matches_fastapi_default_shape(self):
        resp = _FakeResponse({"detail": "Convite não encontrado"})
        assert_error_contains(resp, "não encontrado")

    def test_substring_match_not_exact(self):
        resp = _FakeResponse({"error": {"message": "Não é possível bloquear a si mesmo"}})
        assert_error_contains(resp, "si mesmo")

    def test_raises_on_missing_substring(self):
        resp = _FakeResponse({"error": {"message": "different reason"}})
        with pytest.raises(AssertionError) as exc:
            assert_error_contains(resp, "expected text")
        # Failure message must include the actual body for debugging.
        assert "expected text" in str(exc.value)
        assert "different reason" in str(exc.value)

    def test_raises_on_empty_body(self):
        resp = _FakeResponse({})
        with pytest.raises(AssertionError):
            assert_error_contains(resp, "anything")

    def test_platform_shape_takes_precedence_over_detail(self):
        """When BOTH shapes are present, the platform wrapper wins —
        FastAPI's default is the fallback for tests that bypass the
        platform exception handler."""
        resp = _FakeResponse({
            "error": {"message": "platform message"},
            "detail": "fastapi message",
        })
        assert_error_contains(resp, "platform")
        # Confirms `detail` is NOT consulted when `error` is present.
        with pytest.raises(AssertionError):
            assert_error_contains(resp, "fastapi")
