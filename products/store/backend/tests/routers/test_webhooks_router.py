"""Asaas webhook — the 5-pin contract: verify first (401), fail closed,
per-request secret, rate-limited, status-pinned assertions."""
import json
from datetime import datetime, timedelta, timezone

from tests.conftest import WEBHOOK_TOKEN

PATH = "/api/webhooks/asaas"


def _pedido(store, **over):
    row = {
        "token": "tok-w",
        "nome": "Maria Souza",
        "email": "maria@gmail.com",
        "cpf": "52998224725",
        "valor_cents": 4700,
        "produto": "Contrato Blindado de Compra e Venda",
        "status": "pendente",
        "gateway": "asaas",
    }
    row.update(over)
    return store.pedidos.create(row)


def _event(pedido, event="PAYMENT_RECEIVED", payment_id="pay_1", event_id=None):
    body = {
        "id": event_id or f"evt_{event}_{payment_id}",
        "event": event,
        "payment": {"id": payment_id, "externalReference": pedido["id"], "status": "RECEIVED"},
    }
    return json.dumps(body).encode()


def _post(store, body, token=WEBHOOK_TOKEN):
    headers = {"content-type": "application/json"}
    if token is not None:
        headers["asaas-access-token"] = token
    return store.client.raw().post(PATH, content=body, headers=headers)


class TestVerification:
    def test_wrong_token_401(self, store):
        pedido = _pedido(store)
        assert _post(store, _event(pedido), token="nope").status_code == 401
        assert store.pedidos.get_by_id(pedido["id"])["status"] == "pendente"
        assert store.email.sent == []

    def test_missing_token_401(self, store):
        pedido = _pedido(store)
        assert _post(store, _event(pedido), token=None).status_code == 401

    def test_unset_secret_fails_closed_401(self, store):
        from app import store_deps
        from app.main import app

        pedido = _pedido(store)
        app.dependency_overrides[store_deps.get_asaas_webhook_token] = lambda: ""
        try:
            resp = _post(store, _event(pedido), token="anything")
        finally:
            app.dependency_overrides[store_deps.get_asaas_webhook_token] = lambda: store.webhook_token
        assert resp.status_code == 401
        assert store.pedidos.get_by_id(pedido["id"])["status"] == "pendente"

    def test_garbage_body_401(self, store):
        assert _post(store, b"not json").status_code == 401


class TestPaid:
    def test_paid_marks_pago_and_sends_one_email(self, store):
        pedido = _pedido(store)
        resp = _post(store, _event(pedido))
        assert resp.status_code == 200
        row = store.pedidos.get_by_id(pedido["id"])
        assert row["status"] == "pago"
        assert row["pago_em"] is not None
        assert row["email_enviado_em"] is not None
        assert len(store.email.sent) == 1
        mail = store.email.sent[0]
        assert mail.to == ["maria@gmail.com"]
        assert mail.subject == "Seu Contrato Blindado de Compra e Venda chegou"
        assert "/api/public/download/tok-w" in mail.text
        assert "30 dias" in mail.text and "20 downloads" in mail.text

    def test_same_event_twice_sends_one_email(self, store):
        pedido = _pedido(store)
        body = _event(pedido)
        assert _post(store, body).status_code == 200
        second = _post(store, body)
        assert second.status_code == 200
        assert second.json()["outcome"] == "duplicate"
        assert len(store.email.sent) == 1

    def test_received_plus_confirmed_pair_sends_one_email(self, store):
        pedido = _pedido(store)
        assert _post(store, _event(pedido, "PAYMENT_CONFIRMED")).status_code == 200
        assert _post(store, _event(pedido, "PAYMENT_RECEIVED")).status_code == 200
        assert len(store.email.sent) == 1

    def test_email_failure_is_recorded_and_still_200(self, store):
        from app import store_deps
        from app.main import app

        from tests.support.fakes import FailingEmailSender

        failing = FailingEmailSender("smtp down")
        app.dependency_overrides[store_deps.get_email_sender] = lambda: failing
        pedido = _pedido(store)
        try:
            resp = _post(store, _event(pedido))
        finally:
            app.dependency_overrides[store_deps.get_email_sender] = lambda: store.email
        assert resp.status_code == 200
        row = store.pedidos.get_by_id(pedido["id"])
        assert row["status"] == "pago"  # the payment IS confirmed
        assert row["email_enviado_em"] is None  # claim released: a resend can succeed
        assert "ConnectionError" in row["email_erro"]
        assert failing.attempts == 1

    def test_unknown_pedido_ignored_200(self, store):
        ghost = {"id": "00000000-0000-0000-0000-00000000dead"}
        resp = _post(store, _event(ghost))
        assert resp.status_code == 200
        assert resp.json()["outcome"] == "ignored"
        assert store.email.sent == []

    def test_unhandled_event_ignored_200(self, store):
        pedido = _pedido(store)
        body = json.dumps({"id": "evt_x", "event": "PAYMENT_CREATED", "payment": {"id": "pay_1", "externalReference": pedido["id"]}}).encode()
        resp = _post(store, body)
        assert resp.status_code == 200
        assert store.pedidos.get_by_id(pedido["id"])["status"] == "pendente"

    def test_late_paid_event_does_not_resurrect_a_refund(self, store):
        pedido = _pedido(store, status="reembolsado")
        assert _post(store, _event(pedido)).status_code == 200
        assert store.pedidos.get_by_id(pedido["id"])["status"] == "reembolsado"
        assert store.email.sent == []


class TestRefund:
    def test_refund_marks_reembolsado_and_stops_downloads(self, store):
        from noctusai_lib.integrations.storage.fake import FakeStorageBackend  # noqa: F401
        import asyncio

        from app.services.assets import BUCKET, KIT_KEY

        asyncio.run(store.storage.put(bucket=BUCKET, key=KIT_KEY, data=b"PK\x03\x04z"))
        pedido = _pedido(store)
        assert _post(store, _event(pedido)).status_code == 200
        ok = store.client.raw().get("/api/public/download/tok-w", follow_redirects=False)
        assert ok.status_code == 302

        assert _post(store, _event(pedido, "PAYMENT_REFUNDED", event_id="evt_refund")).status_code == 200
        assert store.pedidos.get_by_id(pedido["id"])["status"] == "reembolsado"
        gone = store.client.raw().get("/api/public/download/tok-w", follow_redirects=False)
        assert gone.status_code == 410

    def test_overdue_marks_pending_as_falhou(self, store):
        pedido = _pedido(store)
        assert _post(store, _event(pedido, "PAYMENT_OVERDUE")).status_code == 200
        assert store.pedidos.get_by_id(pedido["id"])["status"] == "falhou"
