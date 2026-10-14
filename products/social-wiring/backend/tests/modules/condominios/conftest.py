"""Fixtures for the condominios module.

The role-bearing TestClients (`admin_client` / `member_client`) are the
imovel_hub ones -- same DI seam (`get_imovel_hub_client`). `scoped` here does
NOT depend on `client` (imovel_hub's does): it resolves the scoped mock inside
whichever client fixture the test requested FIRST, so seeding is visible to the
routes. List the client fixture before `scoped`/`com_imoveis`.
"""
from __future__ import annotations

import pytest

from app.modules.imovel_hub.deps import get_imovel_hub_client
from tests.modules.imovel_hub.conftest import (  # noqa: F401
    ORG_ID,
    admin_client,
    anon_client,
    auth,
    member_client,
)


@pytest.fixture
def scoped():
    return get_imovel_hub_client()
