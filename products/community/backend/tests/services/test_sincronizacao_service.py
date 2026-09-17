"""Tests for `SincronizacaoService` — contract §Sincronização, the
manager-confirmed state machine (proposto -> confirmado -> aplicado /
aplicado_parcial; cancelar; expira_em). Ban-risk posture (§5): only
`aplicar` mutates WhatsApp membership, chunked + rate-limited, never
auto-retries `invite_required`.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from noctusai_lib.integrations.whatsapp.fake_adapter import FakeWahaClient
from noctusai_lib.integrations.whatsapp.client import WahaGroupError
from noctusai_lib.testing import MockSupabaseClient

from app.services.sincronizacao_service import SincronizacaoService, SincronizacaoServiceError

ORG = UUID("00000000-0000-0000-0000-000000000123")
GRUPO_ID = "11111111-1111-1111-1111-111111111111"
CHAT_ID = "5511999990000@g.us"
PLANO_ID = "22222222-2222-2222-2222-222222222222"
MEMBRO_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
MEMBRO_2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _grupo_row(**over) -> dict:
    base = {"id": GRUPO_ID, "org_id": str(ORG), "chat_id": CHAT_ID, "ativo": True}
    base.update(over)
    return base


def _plano_row(**over) -> dict:
    base = {
        "id": PLANO_ID, "org_id": str(ORG),
        "entitlements": {"grupos_whatsapp": [GRUPO_ID]},
    }
    base.update(over)
    return base


def _membro_row(**over) -> dict:
    base = {
        "id": MEMBRO_1, "org_id": str(ORG), "nome": "Ana",
        "telefone": "+5511974693365", "status": "ativo", "plano_id": PLANO_ID,
    }
    base.update(over)
    return base


def _svc(*, grupos=None, membros=None, planos=None, lotes=None, lote_itens=None, **kwargs):
    mock = MockSupabaseClient()
    mock.set_table_data("grupos", grupos or [])
    mock.set_table_data("membros", membros or [])
    mock.set_table_data("planos", planos or [])
    mock.set_table_data("grupo_membros", [])
    mock.set_table_data("lotes_sincronizacao", lotes or [])
    mock.set_table_data("lote_itens", lote_itens or [])
    svc = SincronizacaoService(
        mock, org_id=ORG,
        lote_max_itens=kwargs.get("lote_max_itens", 20),
        lote_chunk=kwargs.get("lote_chunk", 5),
        lotes_aplicados_max_dia=kwargs.get("lotes_aplicados_max_dia", 5),
        lote_expira_horas=kwargs.get("lote_expira_horas", 24),
    )
    return svc, mock


class TestCriarLote:
    def test_adicionar_diff_includes_eligible_members(self):
        svc, _ = _svc(grupos=[_grupo_row()], membros=[_membro_row()], planos=[_plano_row()])
        lote = asyncio.run(svc.criar_lote(grupo_id=GRUPO_ID, acao="adicionar", proposto_por=None))
        assert lote["estado"] == "proposto"
        assert lote["total_itens"] == 1
        assert lote["itens"][0]["participante_jid"] == "5511974693365@c.us"

    def test_member_without_telefone_is_ignored_not_dropped(self):
        svc, _ = _svc(
            grupos=[_grupo_row()],
            membros=[_membro_row(telefone=None)],
            planos=[_plano_row()],
        )
        lote = asyncio.run(svc.criar_lote(grupo_id=GRUPO_ID, acao="adicionar", proposto_por=None))
        assert lote["total_itens"] == 0
        assert lote["ignorados"][0]["motivo"] == "Sem telefone cadastrado."

    def test_empty_diff_is_201_not_error(self):
        svc, _ = _svc(grupos=[_grupo_row()], membros=[], planos=[])
        lote = asyncio.run(svc.criar_lote(grupo_id=GRUPO_ID, acao="adicionar", proposto_por=None))
        assert lote["total_itens"] == 0

    def test_grupo_not_found_404(self):
        svc, _ = _svc(grupos=[])
        try:
            asyncio.run(svc.criar_lote(grupo_id="unknown", acao="adicionar", proposto_por=None))
            assert False, "expected error"
        except SincronizacaoServiceError as exc:
            assert exc.status_code == 404

    def test_open_lote_already_exists_409(self):
        svc, _ = _svc(
            grupos=[_grupo_row()],
            lotes=[{"id": "x", "org_id": str(ORG), "grupo_id": GRUPO_ID, "estado": "proposto"}],
        )
        try:
            asyncio.run(svc.criar_lote(grupo_id=GRUPO_ID, acao="adicionar", proposto_por=None))
            assert False, "expected error"
        except SincronizacaoServiceError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Já existe um lote em aberto para esse grupo."

    def test_exceeds_max_itens_409(self):
        membros = [
            _membro_row(id=f"m{i}", telefone=f"+551197469{i:04d}") for i in range(3)
        ]
        svc, _ = _svc(
            grupos=[_grupo_row()], membros=membros, planos=[_plano_row()], lote_max_itens=2,
        )
        try:
            asyncio.run(svc.criar_lote(grupo_id=GRUPO_ID, acao="adicionar", proposto_por=None))
            assert False, "expected error"
        except SincronizacaoServiceError as exc:
            assert exc.status_code == 409
            assert "excede o limite de 2 participantes" in exc.detail

    def test_remover_diff_includes_ineligible_observed_participants(self):
        svc, mock = _svc(
            grupos=[_grupo_row()],
            membros=[_membro_row(status="cancelado")],
            planos=[_plano_row()],
        )
        mock.set_table_data("grupo_membros", [{
            "id": "gm1", "org_id": str(ORG), "grupo_id": GRUPO_ID,
            "participante_jid": "5511974693365@c.us", "membro_id": MEMBRO_1,
            "papel": "participante", "visto_em": "2026-01-01T00:00:00+00:00",
        }])
        lote = asyncio.run(svc.criar_lote(grupo_id=GRUPO_ID, acao="remover", proposto_por=None))
        assert lote["total_itens"] == 1
        assert lote["itens"][0]["membro_id"] == MEMBRO_1


class TestConfirmar:
    def _lote(self, **over):
        base = {
            "id": "lote-1", "org_id": str(ORG), "grupo_id": GRUPO_ID, "acao": "adicionar",
            "estado": "proposto", "total_itens": 0,
            "proposto_em": datetime.now(timezone.utc).isoformat(),
            "expira_em": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        }
        base.update(over)
        return base

    def test_confirmar_200(self):
        svc, _ = _svc(lotes=[self._lote()])
        row = asyncio.run(svc.confirmar(lote_id="lote-1", confirmado_por=None))
        assert row["estado"] == "confirmado"

    def test_confirmar_not_proposto_409(self):
        svc, _ = _svc(lotes=[self._lote(estado="confirmado")])
        try:
            asyncio.run(svc.confirmar(lote_id="lote-1", confirmado_por=None))
            assert False, "expected error"
        except SincronizacaoServiceError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Esse lote não está aguardando confirmação."

    def test_confirmar_expired_flips_to_expirado_409(self):
        expirado = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        svc, mock = _svc(lotes=[self._lote(expira_em=expirado)])
        try:
            asyncio.run(svc.confirmar(lote_id="lote-1", confirmado_por=None))
            assert False, "expected error"
        except SincronizacaoServiceError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Esse lote expirou. Gere um novo."
        row = mock.table("lotes_sincronizacao").select("*").eq("id", "lote-1").execute().data[0]
        assert row["estado"] == "expirado"

    def test_confirmar_missing_404(self):
        svc, _ = _svc(lotes=[])
        try:
            asyncio.run(svc.confirmar(lote_id="unknown", confirmado_por=None))
            assert False, "expected error"
        except SincronizacaoServiceError as exc:
            assert exc.status_code == 404


class TestAplicar:
    def _seed(self, *, itens: list[dict], estado="confirmado", lote_over=None):
        lote = {
            "id": "lote-1", "org_id": str(ORG), "grupo_id": GRUPO_ID, "acao": "adicionar",
            "estado": estado, "total_itens": len(itens),
            "proposto_em": "2026-01-01T00:00:00+00:00",
            "expira_em": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        }
        if lote_over:
            lote.update(lote_over)
        svc, mock = _svc(grupos=[_grupo_row()], lotes=[lote], lote_itens=itens)
        return svc, mock

    def test_aplicar_requires_confirmado_409(self):
        svc, _ = self._seed(itens=[], estado="proposto")
        try:
            asyncio.run(svc.aplicar(lote_id="lote-1", waha_client=FakeWahaClient()))
            assert False, "expected error"
        except SincronizacaoServiceError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Confirme o lote antes de aplicar."

    def test_aplicar_missing_404(self):
        svc, _ = _svc(grupos=[_grupo_row()])
        try:
            asyncio.run(svc.aplicar(lote_id="unknown", waha_client=FakeWahaClient()))
            assert False, "expected error"
        except SincronizacaoServiceError as exc:
            assert exc.status_code == 404

    def test_all_succeed_estado_aplicado(self):
        item = {
            "id": "item-1", "org_id": str(ORG), "lote_id": "lote-1",
            "membro_id": MEMBRO_1, "participante_jid": "5511974693365@c.us",
            "resultado": "pendente",
        }
        svc, mock = self._seed(itens=[item])
        waha = FakeWahaClient()
        waha.fake_groups[CHAT_ID] = asyncio.run(waha.create_group("Grupo", []))

        result = asyncio.run(svc.aplicar(lote_id="lote-1", waha_client=waha))
        assert result["estado"] == "aplicado"
        assert result["itens"][0]["resultado"] == "adicionado"
        assert result["aplicado_em"] is not None

    def test_privacy_refused_becomes_convite_necessario_and_partial(self):
        item = {
            "id": "item-1", "org_id": str(ORG), "lote_id": "lote-1",
            "membro_id": MEMBRO_1, "participante_jid": "5511900000001@c.us",
            "resultado": "pendente",
        }
        svc, mock = self._seed(itens=[item])
        waha = FakeWahaClient()
        waha.fake_groups[CHAT_ID] = asyncio.run(waha.create_group("Grupo", []))
        waha.privacy_restricted_ids.add("5511900000001@c.us")

        result = asyncio.run(svc.aplicar(lote_id="lote-1", waha_client=waha))
        assert result["estado"] == "aplicado_parcial"
        assert result["itens"][0]["resultado"] == "convite_necessario"

    def test_idempotent_reapply_returns_unchanged(self):
        item = {
            "id": "item-1", "org_id": str(ORG), "lote_id": "lote-1",
            "membro_id": MEMBRO_1, "participante_jid": "5511974693365@c.us",
            "resultado": "adicionado",
        }
        svc, mock = self._seed(itens=[item], estado="aplicado")
        waha = FakeWahaClient()
        result = asyncio.run(svc.aplicar(lote_id="lote-1", waha_client=waha))
        assert result["estado"] == "aplicado"
        # No WAHA call made — nothing was sent (idempotent no-op).
        assert waha.fake_groups == {}

    def test_daily_cap_429(self):
        item = {
            "id": "item-1", "org_id": str(ORG), "lote_id": "lote-2",
            "membro_id": MEMBRO_1, "participante_jid": "5511974693365@c.us",
            "resultado": "pendente",
        }
        applied_today = datetime.now(timezone.utc).isoformat()
        lotes = [
            {
                "id": f"applied-{i}", "org_id": str(ORG), "grupo_id": GRUPO_ID,
                "acao": "adicionar", "estado": "aplicado", "total_itens": 0,
                "proposto_em": applied_today, "aplicado_em": applied_today,
                "expira_em": applied_today,
            }
            for i in range(5)
        ]
        lotes.append({
            "id": "lote-2", "org_id": str(ORG), "grupo_id": GRUPO_ID, "acao": "adicionar",
            "estado": "confirmado", "total_itens": 1, "proposto_em": applied_today,
            "expira_em": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        })
        svc, mock = _svc(grupos=[_grupo_row()], lotes=lotes, lote_itens=[item])
        try:
            asyncio.run(svc.aplicar(lote_id="lote-2", waha_client=FakeWahaClient()))
            assert False, "expected error"
        except SincronizacaoServiceError as exc:
            assert exc.status_code == 429
            assert exc.detail == (
                "Limite diário de lotes aplicados atingido. Tente novamente amanhã."
            )

    def test_waha_hard_failure_marks_chunk_falhou_never_5xx(self):
        item = {
            "id": "item-1", "org_id": str(ORG), "lote_id": "lote-1",
            "membro_id": MEMBRO_1, "participante_jid": "5511974693365@c.us",
            "resultado": "pendente",
        }
        svc, mock = self._seed(itens=[item])

        class _BrokenWaha(FakeWahaClient):
            async def add_participants(self, group_id, participant_ids):
                raise WahaGroupError(op="add_participants", status=500, detail="boom")

        waha = _BrokenWaha()
        result = asyncio.run(svc.aplicar(lote_id="lote-1", waha_client=waha))
        assert result["estado"] == "aplicado_parcial"
        assert result["itens"][0]["resultado"] == "falhou"


class TestCancelar:
    def test_cancelar_from_proposto_200(self):
        svc, _ = _svc(lotes=[{
            "id": "lote-1", "org_id": str(ORG), "grupo_id": GRUPO_ID,
            "estado": "proposto",
        }])
        row = asyncio.run(svc.cancelar(lote_id="lote-1"))
        assert row["estado"] == "cancelado"

    def test_cancelar_terminal_409(self):
        svc, _ = _svc(lotes=[{
            "id": "lote-1", "org_id": str(ORG), "grupo_id": GRUPO_ID,
            "estado": "aplicado",
        }])
        try:
            asyncio.run(svc.cancelar(lote_id="lote-1"))
            assert False, "expected error"
        except SincronizacaoServiceError as exc:
            assert exc.status_code == 409


class TestConvitesPendentes:
    def test_lists_only_convite_necessario_items_with_link(self):
        itens = [
            {
                "id": "i1", "org_id": str(ORG), "lote_id": "lote-1",
                "membro_id": MEMBRO_1, "participante_jid": "5511900000001@c.us",
                "resultado": "convite_necessario",
            },
            {
                "id": "i2", "org_id": str(ORG), "lote_id": "lote-1",
                "membro_id": MEMBRO_2, "participante_jid": "5511900000002@c.us",
                "resultado": "adicionado",
            },
        ]
        svc, mock = _svc(
            grupos=[_grupo_row()],
            lotes=[{"id": "lote-1", "org_id": str(ORG), "grupo_id": GRUPO_ID, "estado": "aplicado_parcial"}],
            lote_itens=itens,
        )
        waha = FakeWahaClient()
        waha.fake_groups[CHAT_ID] = asyncio.run(waha.create_group("Grupo", []))
        result = asyncio.run(svc.convites_pendentes(lote_id="lote-1", waha_client=waha))
        assert result["total"] == 1
        assert result["items"][0]["participante_jid"] == "5511900000001@c.us"
        assert result["link"] is not None
