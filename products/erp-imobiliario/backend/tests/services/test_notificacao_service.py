"""
Unit tests for notificacao_service — notification creation and team notification.
"""
import pytest

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# criar_notificacao
# ---------------------------------------------------------------------------

class TestCriarNotificacao:

    @pytest.mark.asyncio
    async def test_create_notification_returns_data(self):
        notif = {
            "id": "n-1",
            "org_id": "org-1",
            "user_id": "u-1",
            "tipo": "novo_lead",
            "titulo": "Novo lead recebido",
            "mensagem": "Cliente Joao interessado",
            "link": "/clientes/c-1",
        }
        db = MockSupabaseClient()
        db.set_sequential_responses("notificacoes", [MockSupabaseResponse(data=[notif])])

        from app.services.notificacao_service import criar_notificacao
        result = await criar_notificacao(
            supabase=db,
            org_id="org-1",
            user_id="u-1",
            tipo="novo_lead",
            titulo="Novo lead recebido",
            mensagem="Cliente Joao interessado",
            link="/clientes/c-1",
        )

        assert result["id"] == "n-1"
        assert result["tipo"] == "novo_lead"

    @pytest.mark.asyncio
    async def test_create_notification_without_optional_fields(self):
        notif = {"id": "n-2", "org_id": "org-1", "user_id": "u-1", "tipo": "meta_atingida", "titulo": "Meta atingida", "mensagem": None, "link": None}
        db = MockSupabaseClient()
        db.set_sequential_responses("notificacoes", [MockSupabaseResponse(data=[notif])])

        from app.services.notificacao_service import criar_notificacao
        result = await criar_notificacao(
            supabase=db,
            org_id="org-1",
            user_id="u-1",
            tipo="meta_atingida",
            titulo="Meta atingida",
        )

        assert result["id"] == "n-2"

    @pytest.mark.asyncio
    async def test_create_notification_fallback_on_empty_data(self):
        """When insert returns empty data, the function returns the input dict."""
        db = MockSupabaseClient(data=[])

        from app.services.notificacao_service import criar_notificacao
        result = await criar_notificacao(
            supabase=db,
            org_id="org-1",
            user_id="u-1",
            tipo="comissao_aprovada",
            titulo="Comissao aprovada",
        )

        assert result["tipo"] == "comissao_aprovada"
        assert result["titulo"] == "Comissao aprovada"


# ---------------------------------------------------------------------------
# notificar_equipe
# ---------------------------------------------------------------------------

class TestNotificarEquipe:

    @pytest.mark.asyncio
    async def test_notifies_multiple_users(self):
        rows = [
            {"id": "n-1", "user_id": "u-1"},
            {"id": "n-2", "user_id": "u-2"},
            {"id": "n-3", "user_id": "u-3"},
        ]
        db = MockSupabaseClient(data=rows)

        from app.services.notificacao_service import notificar_equipe
        count = await notificar_equipe(
            supabase=db,
            org_id="org-1",
            user_ids=["u-1", "u-2", "u-3"],
            tipo="proposta_recebida",
            titulo="Nova proposta",
            mensagem="Proposta de R$ 500k para Apto 302",
        )

        assert count == 3

    @pytest.mark.asyncio
    async def test_notifies_empty_list_returns_zero(self):
        db = MockSupabaseClient(data=[])

        from app.services.notificacao_service import notificar_equipe
        count = await notificar_equipe(
            supabase=db,
            org_id="org-1",
            user_ids=[],
            tipo="proposta_recebida",
            titulo="Nova proposta",
        )

        assert count == 0

    @pytest.mark.asyncio
    async def test_notificar_equipe_returns_zero_on_no_data(self):
        """When insert returns no data, count should be 0.

        2026-04-29: Migrated to `set_sequential_responses` after seed-lib mock
        upgrade. Previously relied on `data=[]` quirk to make insert return
        empty; now insert auto-returns inserted rows by default. Explicit
        empty-response queue simulates the failure path.
        """
        db = MockSupabaseClient(data=[])
        db.set_sequential_responses("notificacoes", [MockSupabaseResponse(data=[])])

        from app.services.notificacao_service import notificar_equipe
        count = await notificar_equipe(
            supabase=db,
            org_id="org-1",
            user_ids=["u-1"],
            tipo="vistoria_agendada",
            titulo="Vistoria marcada",
        )

        assert count == 0


# ---------------------------------------------------------------------------
# NOTIFICATION_TYPES constant
# ---------------------------------------------------------------------------

class TestNotificationTypes:

    def test_expected_types_exist(self):
        from app.services.notificacao_service import NOTIFICATION_TYPES

        expected = [
            "novo_lead", "proposta_recebida", "proposta_aceita",
            "contrato_assinado", "pagamento_atrasado", "vistoria_agendada",
        ]
        for tipo in expected:
            assert tipo in NOTIFICATION_TYPES
