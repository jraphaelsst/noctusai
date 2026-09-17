"""Tests for `GruposService` — contract §Grupos business rules.

Exercises the service directly (no HTTP) against a data-seeded
`MockSupabaseClient` + a `FakeWahaClient` — no monkeypatching of our
own code.
"""
import asyncio
from uuid import UUID

from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient
from noctusai_lib.integrations.whatsapp.client import WahaGroupError
from noctusai_lib.testing import MockSupabaseClient

from app.services.grupos_service import GruposService, GruposServiceError, get_sessao

ORG = UUID("00000000-0000-0000-0000-000000000123")
GRUPO_ID = "11111111-1111-1111-1111-111111111111"
CHAT_ID = "5511999990000@g.us"
MEMBRO_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _grupo_row(**over) -> dict:
    base = {
        "id": GRUPO_ID, "org_id": str(ORG), "nome": "Grupo Oficial",
        "chat_id": CHAT_ID, "descricao": None, "ativo": True,
        "somente_admin": False, "participantes_observados": 0,
        "sincronizado_em": None,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


def _svc(grupos=None, membros=None) -> tuple[GruposService, MockSupabaseClient]:
    mock = MockSupabaseClient()
    if grupos is not None:
        mock.set_table_data("grupos", grupos)
    if membros is not None:
        mock.set_table_data("membros", membros)
    return GruposService(mock, org_id=ORG), mock


class TestList:
    def test_list_and_filter_by_ativo(self):
        svc, _ = _svc(grupos=[
            _grupo_row(id="a", chat_id="a@g.us", ativo=True, nome="A"),
            _grupo_row(id="b", chat_id="b@g.us", ativo=False, nome="B"),
        ])
        result = asyncio.run(svc.list(ativo=True))
        assert result["total"] == 1
        assert result["items"][0]["id"] == "a"


class TestCreate:
    def test_register_existing_group_by_chat_id(self):
        svc, mock = _svc(grupos=[])
        waha = FakeWahaClient()
        row = asyncio.run(svc.create(
            payload={"chat_id": CHAT_ID, "nome": "Grupo X", "criar": False}, waha_client=waha,
        ))
        assert row["chat_id"] == CHAT_ID
        assert row["nome"] == "Grupo X"

    def test_duplicate_chat_id_409(self):
        svc, _ = _svc(grupos=[_grupo_row()])
        waha = FakeWahaClient()
        try:
            asyncio.run(svc.create(
                payload={"chat_id": CHAT_ID, "nome": "Outro", "criar": False}, waha_client=waha,
            ))
            assert False, "expected GruposServiceError"
        except GruposServiceError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Esse grupo já está cadastrado."

    def test_criar_calls_waha_create_group(self):
        svc, _ = _svc(grupos=[])
        waha = FakeWahaClient()
        row = asyncio.run(svc.create(
            payload={"criar": True, "nome": "Novo Grupo"}, waha_client=waha,
        ))
        assert row["nome"] == "Novo Grupo"
        assert row["chat_id"] in waha.fake_groups

    def test_criar_without_nome_422(self):
        svc, _ = _svc(grupos=[])
        waha = FakeWahaClient()
        try:
            asyncio.run(svc.create(payload={"criar": True}, waha_client=waha))
            assert False, "expected GruposServiceError"
        except GruposServiceError as exc:
            assert exc.status_code == 422

    def test_register_without_chat_id_422(self):
        svc, _ = _svc(grupos=[])
        waha = FakeWahaClient()
        try:
            asyncio.run(svc.create(payload={"criar": False}, waha_client=waha))
            assert False, "expected GruposServiceError"
        except GruposServiceError as exc:
            assert exc.status_code == 422


class TestUpdate:
    def test_update_200(self):
        svc, _ = _svc(grupos=[_grupo_row()])
        row = asyncio.run(svc.update(grupo_id=GRUPO_ID, payload={"nome": "Renomeado"}))
        assert row["nome"] == "Renomeado"

    def test_update_missing_returns_none(self):
        svc, _ = _svc(grupos=[])
        row = asyncio.run(svc.update(grupo_id="unknown", payload={"nome": "X"}))
        assert row is None


class TestSincronizarRoster:
    def test_matches_participant_by_phone_and_updates_counts(self):
        svc, mock = _svc(
            grupos=[_grupo_row()],
            membros=[{"id": MEMBRO_ID, "telefone": "+5511974693365"}],
        )
        waha = FakeWahaClient()
        waha.fake_groups[CHAT_ID] = asyncio.run(waha.create_group("Grupo Oficial", ["5511974693365@c.us"]))
        waha.fake_contacts["5511974693365@c.us"] = {"name": "Ana"}

        count = asyncio.run(svc.sincronizar_roster(grupo_id=GRUPO_ID, waha_client=waha))
        assert count == 1
        roster = asyncio.run(svc.get_roster(grupo_id=GRUPO_ID))
        assert roster[0]["membro_id"] == MEMBRO_ID
        assert roster[0]["membro_nome"] == "Ana"

        grupo_atualizado = asyncio.run(svc.get(grupo_id=GRUPO_ID))
        assert grupo_atualizado["participantes_observados"] == 1
        assert grupo_atualizado["sincronizado_em"] is not None

    def test_unmatched_participant_has_no_membro_id(self):
        svc, mock = _svc(grupos=[_grupo_row()], membros=[])
        waha = FakeWahaClient()
        waha.fake_groups[CHAT_ID] = asyncio.run(waha.create_group("Grupo Oficial", ["5511900000000@c.us"]))

        asyncio.run(svc.sincronizar_roster(grupo_id=GRUPO_ID, waha_client=waha))
        roster = asyncio.run(svc.get_roster(grupo_id=GRUPO_ID))
        assert roster[0]["membro_id"] is None

    def test_grupo_not_found_404(self):
        svc, _ = _svc(grupos=[])
        waha = FakeWahaClient()
        try:
            asyncio.run(svc.sincronizar_roster(grupo_id="unknown", waha_client=waha))
            assert False, "expected GruposServiceError"
        except GruposServiceError as exc:
            assert exc.status_code == 404

    def test_waha_unreachable_502(self):
        svc, _ = _svc(grupos=[_grupo_row()])

        class _BrokenWaha(FakeWahaClient):
            async def list_participants(self, group_id):
                raise WahaGroupError(op="list_participants", status=500, detail="boom")

        waha = _BrokenWaha()
        try:
            asyncio.run(svc.sincronizar_roster(grupo_id=GRUPO_ID, waha_client=waha))
            assert False, "expected GruposServiceError"
        except GruposServiceError as exc:
            assert exc.status_code == 502
            assert exc.detail == "O WhatsApp não respondeu. Tente novamente em alguns minutos."


class TestConvite:
    def test_get_convite_returns_link(self):
        svc, _ = _svc(grupos=[_grupo_row()])
        waha = FakeWahaClient()
        waha.fake_groups[CHAT_ID] = asyncio.run(waha.create_group("Grupo Oficial", []))
        link = asyncio.run(svc.get_convite(grupo_id=GRUPO_ID, waha_client=waha))
        assert link.startswith("https://chat.whatsapp.com/")

    def test_get_convite_grupo_not_found_404(self):
        svc, _ = _svc(grupos=[])
        waha = FakeWahaClient()
        try:
            asyncio.run(svc.get_convite(grupo_id="unknown", waha_client=waha))
            assert False, "expected GruposServiceError"
        except GruposServiceError as exc:
            assert exc.status_code == 404

    def test_revogar_convite_changes_link(self):
        svc, _ = _svc(grupos=[_grupo_row()])
        waha = FakeWahaClient()
        waha.fake_groups[CHAT_ID] = asyncio.run(waha.create_group("Grupo Oficial", []))
        first = asyncio.run(svc.get_convite(grupo_id=GRUPO_ID, waha_client=waha))
        revoked = asyncio.run(svc.revogar_convite(grupo_id=GRUPO_ID, waha_client=waha))
        assert revoked != first


class TestSessao:
    def test_get_sessao_reads_through(self):
        waha = FakeWahaClient()
        waha.simulate_pair()
        info = asyncio.run(get_sessao(waha_client=waha))
        assert info["estado"] == "WORKING"
        assert info["sessao"] == "default"
