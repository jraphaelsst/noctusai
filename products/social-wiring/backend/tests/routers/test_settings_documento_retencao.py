"""GET/PUT/DELETE /api/settings/documento-retencao — the retention screen (079).

Mirrors `test_settings_clientes_inactivity.py`'s shape: same admin-gate +
read/write split, same `get_scoped_admin_client("social_wiring")` seam, same
per-scenario `MockSupabaseClient` reused across a PUT-then-GET round trip.

**Strict `== 401` / `== 403`, never `in (...)`** per
`KB § PATTERNS/compliance/auth-boundary-false-green.md`.

🔴 WHY THE WRITE GATE GETS ITS OWN TEST RATHER THAN RIDING ON THE ROUTER'S
--------------------------------------------------------------------------
Shortening a retention period DELETES FILES on the next sweep. That makes an
accidentally-ungated PUT here materially worse than an ungated config write
elsewhere on this router — the damage is irreversible and silent. The
403-for-a-member assertion is the one this file exists for.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import (
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

_URL = "/api/settings/documento-retencao"
TABLE = "documento_retencao_politicas"


def _politica(superficie, tipo, dias, *, org_id=None, motivo=None) -> dict:
    return {
        "id": str(uuid4()),
        "org_id": org_id,
        "superficie": superficie,
        "tipo_documento": tipo,
        "retencao_dias": dias,
        "motivo": motivo,
        "atualizado_em": None,
        "atualizado_por": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


_SEED = [
    _politica("atendimento", "extratos_fgts", 730, motivo="finalidade encerra na decisão do banco"),
    _politica("atendimento", "certidao_casamento", 3650),
    _politica("cliente", "contrato", 1825),
]


def _mock_client(*, org_role: str | None = None) -> MockSupabaseClient:
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(
        return_value=MockUserResponse(MockUser(org_id="test-org-123", org_role=org_role))
    )
    return mock_sb


def _client_for(org_role):
    """🔴 Seeds through `get_scoped_admin_client`, NOT `mock_sb.schema(...)`.

    `MockSupabaseClient.schema(name)` hands back a brand-new wrapper with an
    empty per-table store on every call, so seeding via a fresh `.schema()`
    puts the rows somewhere the endpoint never looks — the read comes back
    empty and the test fails for a reason that has nothing to do with the
    code. `get_scoped_admin_client` is cached by admin-client object, so
    seeding through it hits the exact instance the route resolves.
    """
    mock_sb = _mock_client(org_role=org_role)
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.dependencies import get_scoped_admin_client
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        get_scoped_admin_client("social_wiring").set_table_data(
            TABLE, [dict(r) for r in _SEED]
        )
        yield TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def admin_client():
    yield from _client_for("owner")


@pytest.fixture
def member_client():
    yield from _client_for(None)


@pytest.fixture
def anon_client():
    """A TestClient sending NO Authorization header — the only shape that can
    produce a genuine 401 here."""
    yield from _client_for("owner")


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


# ─── auth boundary ────────────────────────────────────────────────────


class TestAuth:
    def test_get_without_a_token_is_401(self, anon_client):
        assert anon_client.get(_URL).status_code == 401

    def test_put_without_a_token_is_401(self, anon_client):
        resp = anon_client.put(
            _URL,
            json={
                "superficie": "atendimento",
                "tipo_documento": "extratos_fgts",
                "retencao_dias": 365,
            },
        )
        assert resp.status_code == 401

    def test_delete_without_a_token_is_401(self, anon_client):
        resp = anon_client.delete(
            f"{_URL}?superficie=atendimento&tipo_documento=extratos_fgts"
        )
        assert resp.status_code == 401

    def test_a_member_can_READ_the_policy(self, member_client):
        """Open on purpose: a corretor should be able to look up how long the
        agency keeps a buyer's income tax return. That is the kind of question
        LGPD art. 9 says a data subject can ask, and an answer nobody in the
        office can find is not an answer."""
        assert member_client.get(_URL, headers=_auth()).status_code == 200

    def test_a_member_cannot_WRITE_the_policy(self, member_client):
        """🔴 The assertion this file exists for — a shortened period deletes
        files on the next sweep."""
        resp = member_client.put(
            _URL,
            json={
                "superficie": "atendimento",
                "tipo_documento": "extratos_fgts",
                "retencao_dias": 1,
            },
            headers=_auth(),
        )
        assert resp.status_code == 403

    def test_a_member_cannot_RESTORE_the_default(self, member_client):
        resp = member_client.delete(
            f"{_URL}?superficie=atendimento&tipo_documento=extratos_fgts",
            headers=_auth(),
        )
        assert resp.status_code == 403


# ─── the read ─────────────────────────────────────────────────────────


class TestLeitura:
    def test_lists_every_type_with_its_anchor(self, admin_client):
        body = admin_client.get(_URL, headers=_auth()).json()

        assert body["total"] == len(_SEED)
        por_tipo = {i["tipo_documento"]: i for i in body["items"]}
        assert por_tipo["extratos_fgts"]["retencao_dias"] == 730
        assert por_tipo["extratos_fgts"]["ancora"] == "encerramento"
        assert por_tipo["contrato"]["ancora"] == "envio"
        # A duration with no anchor on screen is a duration that gets misread.
        assert all(i["ancora_rotulo"] for i in body["items"])

    def test_nothing_is_personalizado_before_anyone_edits(self, admin_client):
        body = admin_client.get(_URL, headers=_auth()).json()
        assert all(i["personalizado"] is False for i in body["items"])


# ─── the write ────────────────────────────────────────────────────────


class TestEscrita:
    def test_admin_put_overrides_and_returns_the_whole_list(self, admin_client):
        resp = admin_client.put(
            _URL,
            json={
                "superficie": "atendimento",
                "tipo_documento": "extratos_fgts",
                "retencao_dias": 365,
                "motivo": "política interna revista",
            },
            headers=_auth(),
        )

        assert resp.status_code == 200
        body = resp.json()
        # The WHOLE list, not the single row — the screen renders them
        # together and a partial response is where an optimistic-update bug
        # would live.
        assert body["total"] == len(_SEED)
        alvo = [i for i in body["items"] if i["tipo_documento"] == "extratos_fgts"][0]
        assert alvo["retencao_dias"] == 365
        assert alvo["padrao_dias"] == 730, "the default must survive the override"
        assert alvo["personalizado"] is True

    def test_the_override_survives_a_reread(self, admin_client):
        admin_client.put(
            _URL,
            json={
                "superficie": "atendimento",
                "tipo_documento": "extratos_fgts",
                "retencao_dias": 365,
            },
            headers=_auth(),
        )

        body = admin_client.get(_URL, headers=_auth()).json()
        alvo = [i for i in body["items"] if i["tipo_documento"] == "extratos_fgts"][0]
        assert alvo["retencao_dias"] == 365

    def test_null_is_accepted_as_keep_indefinitely(self, admin_client):
        resp = admin_client.put(
            _URL,
            json={
                "superficie": "atendimento",
                "tipo_documento": "extratos_fgts",
                "retencao_dias": None,
            },
            headers=_auth(),
        )

        assert resp.status_code == 200
        alvo = [
            i for i in resp.json()["items"] if i["tipo_documento"] == "extratos_fgts"
        ][0]
        assert alvo["retencao_dias"] is None
        assert alvo["personalizado"] is True, (
            "keeping forever DELIBERATELY is a decision, not an absence"
        )

    def test_zero_days_is_rejected_by_the_schema(self, admin_client):
        resp = admin_client.put(
            _URL,
            json={
                "superficie": "atendimento",
                "tipo_documento": "extratos_fgts",
                "retencao_dias": 0,
            },
            headers=_auth(),
        )
        assert resp.status_code == 422

    def test_an_unknown_surface_is_rejected_by_the_schema(self, admin_client):
        resp = admin_client.put(
            _URL,
            json={
                "superficie": "imovel",
                "tipo_documento": "matricula",
                "retencao_dias": 365,
            },
            headers=_auth(),
        )
        assert resp.status_code == 422

    def test_an_unknown_tipo_is_rejected_by_the_service(self, admin_client):
        """The platform tier is the allow-list; the schema cannot enumerate a
        table, so this one lands as a 400 from the service."""
        resp = admin_client.put(
            _URL,
            json={
                "superficie": "atendimento",
                "tipo_documento": "nao_existe",
                "retencao_dias": 365,
            },
            headers=_auth(),
        )
        assert resp.status_code == 400

    def test_delete_restores_the_platform_default(self, admin_client):
        admin_client.put(
            _URL,
            json={
                "superficie": "atendimento",
                "tipo_documento": "extratos_fgts",
                "retencao_dias": 365,
            },
            headers=_auth(),
        )

        resp = admin_client.delete(
            f"{_URL}?superficie=atendimento&tipo_documento=extratos_fgts",
            headers=_auth(),
        )

        assert resp.status_code == 200
        alvo = [
            i for i in resp.json()["items"] if i["tipo_documento"] == "extratos_fgts"
        ][0]
        assert alvo["retencao_dias"] == 730
        assert alvo["personalizado"] is False
