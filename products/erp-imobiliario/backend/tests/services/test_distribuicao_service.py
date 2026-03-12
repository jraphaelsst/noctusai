"""
Unit tests for distribuicao_service — round-robin, region-based, and specialty-based
lead distribution.
"""
import pytest

from tests.conftest import MockSupabaseClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config(**overrides):
    """Return a base distribution config dict."""
    base = {
        "id": "cfg-1",
        "org_id": "org-1",
        "modo": "round_robin",
        "corretores_ativos": ["agent-a", "agent-b", "agent-c"],
        "proximo_corretor_idx": 0,
        "regras": {},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# get_next_agent
# ---------------------------------------------------------------------------

class TestGetNextAgent:

    def test_returns_first_agent(self):
        db = MockSupabaseClient()
        config = _config(proximo_corretor_idx=0)

        from app.services.distribuicao_service import get_next_agent
        result = get_next_agent(config, db)

        assert result == "agent-a"

    def test_wraps_around(self):
        db = MockSupabaseClient()
        config = _config(proximo_corretor_idx=2)

        from app.services.distribuicao_service import get_next_agent
        result = get_next_agent(config, db)

        assert result == "agent-c"

    def test_empty_corretores_returns_none(self):
        db = MockSupabaseClient()
        config = _config(corretores_ativos=[])

        from app.services.distribuicao_service import get_next_agent
        result = get_next_agent(config, db)

        assert result is None

    def test_index_beyond_list_wraps(self):
        db = MockSupabaseClient()
        config = _config(proximo_corretor_idx=5, corretores_ativos=["x", "y"])

        from app.services.distribuicao_service import get_next_agent
        result = get_next_agent(config, db)

        # 5 % 2 = 1 -> "y"
        assert result == "y"


# ---------------------------------------------------------------------------
# auto_assign — manual mode
# ---------------------------------------------------------------------------

class TestAutoAssignManual:

    def test_manual_mode_not_assigned(self):
        db = MockSupabaseClient()
        db.set_table_data("distribuicao_config", [_config(modo="manual")])

        from app.services.distribuicao_service import auto_assign
        result = auto_assign("cli-1", "org-1", db)

        assert result["atribuido"] is False
        assert result["modo"] == "manual"


# ---------------------------------------------------------------------------
# auto_assign — no config
# ---------------------------------------------------------------------------

class TestAutoAssignNoConfig:

    def test_missing_config(self):
        db = MockSupabaseClient(data=[])

        from app.services.distribuicao_service import auto_assign
        result = auto_assign("cli-1", "org-1", db)

        assert result["atribuido"] is False
        assert "não encontrada" in result["motivo"]


# ---------------------------------------------------------------------------
# auto_assign — round_robin
# ---------------------------------------------------------------------------

class TestAutoAssignRoundRobin:

    def test_assigns_next_agent(self):
        db = MockSupabaseClient()
        db.set_table_data("distribuicao_config", [_config(modo="round_robin")])

        from app.services.distribuicao_service import auto_assign
        result = auto_assign("cli-1", "org-1", db)

        assert result["atribuido"] is True
        assert result["corretor_id"] == "agent-a"
        assert result["modo"] == "round_robin"

    def test_no_active_agents(self):
        db = MockSupabaseClient()
        db.set_table_data("distribuicao_config", [
            _config(modo="round_robin", corretores_ativos=[]),
        ])

        from app.services.distribuicao_service import auto_assign
        result = auto_assign("cli-1", "org-1", db)

        assert result["atribuido"] is False


# ---------------------------------------------------------------------------
# auto_assign — por_regiao
# ---------------------------------------------------------------------------

class TestAutoAssignPorRegiao:

    def test_region_match(self):
        db = MockSupabaseClient()
        cfg = _config(
            modo="por_regiao",
            regras={"regioes": {"zona_sul": "agent-sul", "zona_norte": "agent-norte"}},
        )
        db.set_table_data("distribuicao_config", [cfg])
        db.set_table_data("clientes", {"id": "cli-1", "interesse": "zona_sul apartamento", "observacoes": ""})

        from app.services.distribuicao_service import auto_assign
        result = auto_assign("cli-1", "org-1", db)

        assert result["atribuido"] is True
        assert result["corretor_id"] == "agent-sul"
        assert result["regiao"] == "zona_sul"

    def test_region_no_match_fallback_round_robin(self):
        db = MockSupabaseClient()
        cfg = _config(
            modo="por_regiao",
            regras={"regioes": {"zona_sul": "agent-sul"}},
        )
        db.set_table_data("distribuicao_config", [cfg])
        db.set_table_data("clientes", {"id": "cli-1", "interesse": "zona_leste apartamento", "observacoes": ""})

        from app.services.distribuicao_service import auto_assign
        result = auto_assign("cli-1", "org-1", db)

        assert result["atribuido"] is True
        assert result["regiao"] == "fallback_round_robin"

    def test_client_not_found(self):
        db = MockSupabaseClient()
        cfg = _config(modo="por_regiao", regras={"regioes": {"zona_sul": "agent-1"}})
        db.set_table_data("distribuicao_config", [cfg])
        db.set_table_data("clientes", None)

        from app.services.distribuicao_service import auto_assign
        result = auto_assign("cli-missing", "org-1", db)

        assert result["atribuido"] is False


# ---------------------------------------------------------------------------
# auto_assign — por_especialidade
# ---------------------------------------------------------------------------

class TestAutoAssignPorEspecialidade:

    def test_specialty_match(self):
        db = MockSupabaseClient()
        cfg = _config(
            modo="por_especialidade",
            regras={"especialidades": {"comercial": "agent-com", "residencial": "agent-res"}},
        )
        db.set_table_data("distribuicao_config", [cfg])
        db.set_table_data("clientes", {"id": "cli-1", "interesse": "comercial galpao"})

        from app.services.distribuicao_service import auto_assign
        result = auto_assign("cli-1", "org-1", db)

        assert result["atribuido"] is True
        assert result["corretor_id"] == "agent-com"
        assert result["especialidade"] == "comercial"

    def test_specialty_no_match_fallback(self):
        db = MockSupabaseClient()
        cfg = _config(
            modo="por_especialidade",
            regras={"especialidades": {"comercial": "agent-com"}},
        )
        db.set_table_data("distribuicao_config", [cfg])
        db.set_table_data("clientes", {"id": "cli-1", "interesse": "terreno rural"})

        from app.services.distribuicao_service import auto_assign
        result = auto_assign("cli-1", "org-1", db)

        assert result["atribuido"] is True
        assert result["especialidade"] == "fallback_round_robin"


# ---------------------------------------------------------------------------
# auto_assign — unknown mode
# ---------------------------------------------------------------------------

class TestAutoAssignUnknownMode:

    def test_unknown_mode(self):
        db = MockSupabaseClient()
        db.set_table_data("distribuicao_config", [_config(modo="custom_xyz")])

        from app.services.distribuicao_service import auto_assign
        result = auto_assign("cli-1", "org-1", db)

        assert result["atribuido"] is False
        assert "desconhecido" in result["motivo"]


# ---------------------------------------------------------------------------
# get_queue_info
# ---------------------------------------------------------------------------

class TestGetQueueInfo:

    def test_empty_corretores(self):
        db = MockSupabaseClient()
        config = _config(corretores_ativos=[])

        from app.services.distribuicao_service import get_queue_info
        result = get_queue_info(config, db)

        assert result["corretores_ativos"] == []
        assert result["proximo_corretor_id"] is None

    def test_returns_agent_info(self):
        db = MockSupabaseClient()
        db.set_table_data("profiles", [
            {"id": "agent-a", "nome": "Alice", "email": "a@test.com"},
            {"id": "agent-b", "nome": "Bob", "email": "b@test.com"},
        ])
        config = _config(corretores_ativos=["agent-a", "agent-b"], proximo_corretor_idx=1)

        from app.services.distribuicao_service import get_queue_info
        result = get_queue_info(config, db)

        assert result["proximo_corretor_id"] == "agent-b"
        assert result["proximo_corretor_idx"] == 1
        assert len(result["corretores_ativos"]) == 2
        # agent-b should be marked as next
        next_agents = [a for a in result["corretores_ativos"] if a["is_next"]]
        assert len(next_agents) == 1
        assert next_agents[0]["id"] == "agent-b"
