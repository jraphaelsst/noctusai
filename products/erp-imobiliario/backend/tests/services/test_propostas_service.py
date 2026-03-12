"""
Unit tests for propostas_service — proposal status transitions, stats, and history.
"""
import pytest

from tests.conftest import MockSupabaseClient


# ---------------------------------------------------------------------------
# validate_status_transition
# ---------------------------------------------------------------------------

class TestValidateStatusTransition:

    def test_enviada_to_em_analise(self):
        from app.services.propostas_service import PropostasService

        assert PropostasService.validate_status_transition("enviada", "em_analise") is True

    def test_enviada_to_recusada(self):
        from app.services.propostas_service import PropostasService

        assert PropostasService.validate_status_transition("enviada", "recusada") is True

    def test_em_analise_to_aceita(self):
        from app.services.propostas_service import PropostasService

        assert PropostasService.validate_status_transition("em_analise", "aceita") is True

    def test_em_analise_to_recusada(self):
        from app.services.propostas_service import PropostasService

        assert PropostasService.validate_status_transition("em_analise", "recusada") is True

    def test_em_analise_to_contraproposta(self):
        from app.services.propostas_service import PropostasService

        assert PropostasService.validate_status_transition("em_analise", "contraproposta") is True

    def test_aceita_is_terminal(self):
        from app.services.propostas_service import PropostasService

        assert PropostasService.validate_status_transition("aceita", "em_analise") is False
        assert PropostasService.validate_status_transition("aceita", "recusada") is False

    def test_recusada_is_terminal(self):
        from app.services.propostas_service import PropostasService

        assert PropostasService.validate_status_transition("recusada", "aceita") is False

    def test_invalid_current_status(self):
        from app.services.propostas_service import PropostasService

        assert PropostasService.validate_status_transition("desconhecido", "aceita") is False

    def test_enviada_to_aceita_not_allowed(self):
        """Cannot skip em_analise when going from enviada to aceita."""
        from app.services.propostas_service import PropostasService

        assert PropostasService.validate_status_transition("enviada", "aceita") is False


# ---------------------------------------------------------------------------
# get_valid_transitions
# ---------------------------------------------------------------------------

class TestGetValidTransitions:

    def test_transitions_from_enviada(self):
        from app.services.propostas_service import PropostasService

        transitions = PropostasService.get_valid_transitions("enviada")

        assert "em_analise" in transitions
        assert "recusada" in transitions
        assert "expirada" in transitions
        assert "aceita" not in transitions

    def test_transitions_from_terminal_state(self):
        from app.services.propostas_service import PropostasService

        assert PropostasService.get_valid_transitions("aceita") == set()
        assert PropostasService.get_valid_transitions("recusada") == set()
        assert PropostasService.get_valid_transitions("expirada") == set()

    def test_unknown_status_returns_empty(self):
        from app.services.propostas_service import PropostasService

        assert PropostasService.get_valid_transitions("inexistente") == set()


# ---------------------------------------------------------------------------
# build_history_entry
# ---------------------------------------------------------------------------

class TestBuildHistoryEntry:

    def test_basic_entry(self):
        from app.services.propostas_service import PropostasService

        entry = PropostasService.build_history_entry("Status atualizado para aceita")

        assert entry["action"] == "Status atualizado para aceita"
        assert "timestamp" in entry
        assert "user_id" not in entry

    def test_entry_with_user(self):
        from app.services.propostas_service import PropostasService

        entry = PropostasService.build_history_entry(
            "Proposta enviada",
            user_id="u-1",
        )

        assert entry["user_id"] == "u-1"

    def test_entry_with_details(self):
        from app.services.propostas_service import PropostasService

        details = {"valor_anterior": 500000, "valor_novo": 480000}
        entry = PropostasService.build_history_entry(
            "Contraproposta registrada",
            details=details,
        )

        assert entry["details"]["valor_anterior"] == 500000
        assert entry["details"]["valor_novo"] == 480000


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:

    def test_stats_with_mixed_statuses(self):
        db = MockSupabaseClient()
        from app.services.propostas_service import PropostasService
        svc = PropostasService(db, "u-1")

        propostas = [
            {"id": "p-1", "status": "enviada"},
            {"id": "p-2", "status": "enviada"},
            {"id": "p-3", "status": "em_analise"},
            {"id": "p-4", "status": "aceita"},
            {"id": "p-5", "status": "recusada"},
        ]

        stats = svc.get_stats(propostas)

        assert stats["total"] == 5
        assert stats["enviada"] == 2
        assert stats["em_analise"] == 1
        assert stats["aceita"] == 1
        assert stats["recusada"] == 1
        assert stats["contraproposta"] == 0
        assert stats["expirada"] == 0

    def test_stats_empty_list(self):
        db = MockSupabaseClient()
        from app.services.propostas_service import PropostasService
        svc = PropostasService(db, "u-1")

        stats = svc.get_stats([])

        assert stats["total"] == 0
        for status in ["enviada", "em_analise", "contraproposta", "aceita", "recusada", "expirada"]:
            assert stats[status] == 0

    def test_stats_ignores_unknown_status(self):
        db = MockSupabaseClient()
        from app.services.propostas_service import PropostasService
        svc = PropostasService(db, "u-1")

        propostas = [
            {"id": "p-1", "status": "aceita"},
            {"id": "p-2", "status": "desconhecido"},
        ]

        stats = svc.get_stats(propostas)

        assert stats["total"] == 2
        assert stats["aceita"] == 1
        # Unknown status is counted in total but not in any bucket
