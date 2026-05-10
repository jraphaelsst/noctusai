"""
Pure-function tests for the orders state machine (Phase 3).

Lifecycle (per `migrations/001_adconnect.sql` § 5):
  rascunho → enviado → confirmado → enviado_para_entrega → entregue
                    └→ cancelado (from anywhere except entregue)

Tests focus on the state-machine itself (`is_valid_transition`) and the
`transition_status` orchestrator; the create_pedido_from_cart path is
covered end-to-end by the router tests.
"""
from __future__ import annotations

from typing import Any

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.services import orders_service


# ---------------------------------------------------------------------------
# is_valid_transition — pure check
# ---------------------------------------------------------------------------


class TestIsValidTransition:
    def test_rascunho_to_enviado_is_valid(self):
        assert orders_service.is_valid_transition("rascunho", "enviado") is True

    def test_enviado_to_confirmado_is_valid(self):
        assert orders_service.is_valid_transition("enviado", "confirmado") is True

    def test_confirmado_to_enviado_para_entrega_is_valid(self):
        assert (
            orders_service.is_valid_transition(
                "confirmado", "enviado_para_entrega"
            )
            is True
        )

    def test_enviado_para_entrega_to_entregue_is_valid(self):
        assert (
            orders_service.is_valid_transition(
                "enviado_para_entrega", "entregue"
            )
            is True
        )

    def test_cancelado_from_rascunho_is_valid(self):
        assert orders_service.is_valid_transition("rascunho", "cancelado") is True

    def test_cancelado_from_enviado_para_entrega_is_valid(self):
        assert (
            orders_service.is_valid_transition(
                "enviado_para_entrega", "cancelado"
            )
            is True
        )

    def test_entregue_is_terminal(self):
        for target in (
            "rascunho",
            "enviado",
            "confirmado",
            "enviado_para_entrega",
            "cancelado",
        ):
            assert (
                orders_service.is_valid_transition("entregue", target) is False
            ), f"entregue → {target} must be invalid"

    def test_cancelado_is_terminal(self):
        for target in (
            "rascunho",
            "enviado",
            "confirmado",
            "enviado_para_entrega",
            "entregue",
        ):
            assert (
                orders_service.is_valid_transition("cancelado", target) is False
            ), f"cancelado → {target} must be invalid"

    def test_cannot_skip_states(self):
        # rascunho → confirmado would skip 'enviado' — invalid.
        assert (
            orders_service.is_valid_transition("rascunho", "confirmado") is False
        )
        # enviado → entregue would skip 'confirmado' + 'enviado_para_entrega'.
        assert orders_service.is_valid_transition("enviado", "entregue") is False

    def test_unknown_status_is_invalid(self):
        assert orders_service.is_valid_transition("inexistente", "enviado") is False
        assert orders_service.is_valid_transition("rascunho", "inventado") is False


# ---------------------------------------------------------------------------
# transition_status — DB orchestrator
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db() -> MockSupabaseClient:
    return MockSupabaseClient(schema="adconnect")


def _seed_pedido(db: MockSupabaseClient, *, status: str, pedido_id: str = "ped-1"):
    db.set_table_data(
        "pedidos",
        [{"id": pedido_id, "distributor_id": "dist-1", "status": status, "total": 100.0}],
    )


class TestTransitionStatus:
    def test_admin_can_advance_enviado_to_confirmado(self, mock_db):
        _seed_pedido(mock_db, status="enviado")
        result = orders_service.transition_status(
            mock_db,
            pedido_id="ped-1",
            new_status="confirmado",
            actor_role="admin",
        )
        assert result["status"] == "confirmado"
        assert "confirmed_at" in result
        # Insert side: capture the update payload.
        updates = mock_db.table("pedidos").updated_payloads
        assert len(updates) == 1
        assert updates[0]["status"] == "confirmado"
        assert "confirmed_at" in updates[0]

    def test_distributor_cannot_advance_to_confirmado(self, mock_db):
        _seed_pedido(mock_db, status="enviado")
        with pytest.raises(orders_service.OrderError):
            orders_service.transition_status(
                mock_db,
                pedido_id="ped-1",
                new_status="confirmado",
                actor_role="customer",
            )

    def test_distributor_can_cancel_from_enviado(self, mock_db):
        _seed_pedido(mock_db, status="enviado")
        result = orders_service.transition_status(
            mock_db,
            pedido_id="ped-1",
            new_status="cancelado",
            actor_role="customer",
        )
        assert result["status"] == "cancelado"
        updates = mock_db.table("pedidos").updated_payloads
        assert updates[0]["status"] == "cancelado"
        assert "canceled_at" in updates[0]

    def test_invalid_transition_raises(self, mock_db):
        _seed_pedido(mock_db, status="rascunho")
        with pytest.raises(orders_service.OrderError) as excinfo:
            orders_service.transition_status(
                mock_db,
                pedido_id="ped-1",
                new_status="entregue",
                actor_role="admin",
            )
        assert "transição inválida" in str(excinfo.value).lower()

    def test_terminal_entregue_rejects_any_transition(self, mock_db):
        _seed_pedido(mock_db, status="entregue")
        with pytest.raises(orders_service.OrderError):
            orders_service.transition_status(
                mock_db,
                pedido_id="ped-1",
                new_status="cancelado",
                actor_role="admin",
            )

    def test_pedido_not_found_raises(self, mock_db):
        # No seed — empty table.
        with pytest.raises(orders_service.OrderError) as excinfo:
            orders_service.transition_status(
                mock_db,
                pedido_id="nope",
                new_status="enviado",
                actor_role="admin",
            )
        assert "não encontrado" in str(excinfo.value).lower()

    def test_delivered_stamp_is_written(self, mock_db):
        _seed_pedido(mock_db, status="enviado_para_entrega")
        orders_service.transition_status(
            mock_db,
            pedido_id="ped-1",
            new_status="entregue",
            actor_role="admin",
        )
        updates = mock_db.table("pedidos").updated_payloads
        assert "delivered_at" in updates[0]
