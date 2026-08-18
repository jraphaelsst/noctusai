"""Fixtures for the `portal_leads` tests.

Reuses the leads module's `MockSupabaseClient` conventions (that client
under-filters nothing this module needs, and it is what
`leads_service.create_lead` is already proven against). No RPC simulator:
nothing in this module calls an RPC.
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

from tests.modules.leads.conftest import ORG_A, ORG_B  # noqa: F401 — re-exported

WEBHOOK_SECRET = "test-olx-secret"


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
        yield TestClient(app, raise_server_exceptions=True)


__all__ = ["ORG_A", "ORG_B", "WEBHOOK_SECRET", "http_client", "mock_db"]
