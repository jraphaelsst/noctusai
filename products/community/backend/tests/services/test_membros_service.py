"""Tests for `MembrosService` — contract §Membros business rules.

Exercises the service directly (no HTTP) against a data-seeded
`MockSupabaseClient` — no monkeypatching of our own code.
"""
import asyncio
from uuid import UUID

from noctusai_lib.testing import MockSupabaseClient

from app.services.membros_service import MembrosService, MembrosServiceError

ORG = UUID("00000000-0000-0000-0000-000000000123")
MEMBRO_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PLANO_ID = "11111111-1111-1111-1111-111111111111"


def _row(**over) -> dict:
    base = {
        "id": MEMBRO_ID,
        "org_id": str(ORG),
        "nome": "Ana",
        "email": "ana@x.com",
        "telefone": None,
        "status": "pendente",
        "plano_id": None,
        "origem": "checkout",
        "tags": [],
        "user_id": None,
        "observacoes": None,
        "entrou_em": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _svc(rows=None) -> tuple[MembrosService, MockSupabaseClient]:
    mock = MockSupabaseClient()
    if rows is not None:
        mock.set_table_data("membros", rows)
    return MembrosService(mock, org_id=ORG), mock


class TestSetStatus:
    def test_idempotent_same_status_is_unchanged_200(self):
        svc, _ = _svc([_row(status="ativo", plano_id=PLANO_ID)])
        result = asyncio.run(svc.set_status(membro_id=MEMBRO_ID, novo_status="ativo"))
        assert result["status"] == "ativo"

    def test_activate_without_plano_raises_409(self):
        svc, _ = _svc([_row(status="pendente", plano_id=None)])
        try:
            asyncio.run(svc.set_status(membro_id=MEMBRO_ID, novo_status="ativo"))
            assert False, "expected MembrosServiceError"
        except MembrosServiceError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Defina um plano antes de ativar o membro."

    def test_activate_with_plano_succeeds(self):
        svc, _ = _svc([_row(status="pendente", plano_id=PLANO_ID)])
        result = asyncio.run(svc.set_status(membro_id=MEMBRO_ID, novo_status="ativo"))
        assert result["status"] == "ativo"

    def test_transition_to_atrasado_pausado_cancelado(self):
        for target in ("atrasado", "pausado", "cancelado"):
            svc, _ = _svc([_row(status="ativo", plano_id=PLANO_ID)])
            result = asyncio.run(svc.set_status(membro_id=MEMBRO_ID, novo_status=target))
            assert result["status"] == target

    def test_unknown_membro_returns_none(self):
        svc, _ = _svc([])
        result = asyncio.run(svc.set_status(membro_id=MEMBRO_ID, novo_status="ativo"))
        assert result is None


class TestSoftDelete:
    def test_sets_cancelado_never_hard_deletes(self):
        svc, mock = _svc([_row(status="ativo")])
        ok = asyncio.run(svc.soft_delete(membro_id=MEMBRO_ID))
        assert ok is True
        row = mock.table("membros").select("*").execute().data[0]
        assert row["status"] == "cancelado"
        assert row["id"] == MEMBRO_ID  # the row itself still exists


class TestCreate:
    def test_duplicate_email_raises_409(self):
        svc, _ = _svc([_row(email="dup@x.com")])
        try:
            asyncio.run(svc.create(payload={
                "nome": "Outra", "email": "dup@x.com", "origem": "checkout",
                "status": "pendente", "plano_id": None, "tags": [], "observacoes": None,
                "telefone": None,
            }))
            assert False, "expected MembrosServiceError"
        except MembrosServiceError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Já existe um membro com esse e-mail."

    def test_create_stamps_entrou_em(self):
        svc, _ = _svc([])
        result = asyncio.run(svc.create(payload={
            "nome": "Nova", "email": "nova@x.com", "origem": "checkout",
            "status": "pendente", "plano_id": None, "tags": [], "observacoes": None,
            "telefone": None,
        }))
        assert result["entrou_em"] is not None
