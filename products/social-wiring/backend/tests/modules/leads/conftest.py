"""Shared fixtures for the Leads module test suite.

Backed by ``noctusai_lib.testing.MockSupabaseClient`` (NOT the SQLite dev
client) — the leads services use ``gte``/``lte``/``in_``/``ilike``,
which the mock's ``_FilterMixin`` evaluates literally (confirmed against
``noctusai_lib/testing/mocks.py``); the SQLite dev adapter only
implements ``eq``/``lt``/``in_``/``or_``(cursor-only) and would silently
under-filter. Per ``KB § PATTERNS/di-test-seam.md``.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import (
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

ORG_A = "00000000-0000-4000-8000-0000000000a1"
ORG_B = "00000000-0000-4000-8000-0000000000b2"


@pytest.fixture
def mock_db():
    return MockSupabaseClient()


@pytest.fixture
def http_client(mock_db):
    mock_db.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id=ORG_A))
    )
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_db),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_db),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_db),
    ):
        from app.main import app

        bind_consent_module_to_mock(mock_db)
        tc = TestClient(app, raise_server_exceptions=True)
        yield tc


def auth_headers() -> dict:
    return {"Authorization": "Bearer test-token"}


__all__ = ["ORG_A", "ORG_B", "auth_headers"]
