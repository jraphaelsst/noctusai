import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from noctusai_lib.integrations.email import FakeEmailSender
from noctusai_lib.integrations.storage.fake import FakeStorageBackend

from app.services.assets import BUCKET, KIT_KEY, AssetService
from app.services.delivery_service import (
    DeliveryFailed,
    DeliveryService,
    DownloadRefused,
    build_delivery_email,
    download_state,
    mask_email,
)
from tests.support.fakes import FailingEmailSender, FakePedidoStore

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def _pedido(**over):
    base = {
        "id": "p1", "token": "tok", "nome": "João da Silva", "email": "joao@gmail.com", "status": "pago",
        "produto": "Kit <X>", "pago_em": NOW.isoformat(), "downloads": 0,
    }
    base.update(over)
    return base


def test_mask_email():
    assert mask_email("joao@gmail.com") == "j***@gmail.com"
    assert mask_email("nonsense") == "***"


@pytest.mark.parametrize(
    "over,expected",
    [
        ({}, "ok"),
        ({"status": "pendente"}, "not_paid"),
        ({"status": "falhou"}, "not_paid"),
        ({"status": "reembolsado"}, "refunded"),
        ({"pago_em": (NOW - timedelta(days=30)).isoformat()}, "ok"),  # day 30 still inside
        ({"pago_em": (NOW - timedelta(days=30, seconds=1)).isoformat()}, "expired"),
        ({"pago_em": None}, "expired"),
        ({"downloads": 19}, "ok"),
        ({"downloads": 20}, "exhausted"),
    ],
)
def test_download_state(over, expected):
    assert download_state(_pedido(**over), now=NOW) == expected


def test_email_content_escapes_html_and_states_terms():
    mail = build_delivery_email(_pedido(), public_url="https://store.example.com/")
    assert mail.subject == "Seu Kit <X> chegou"
    assert "https://store.example.com/api/public/download/tok" in mail.text
    assert "&lt;X&gt;" in mail.html and "<X>" not in mail.html
    assert "30 dias" in mail.text and "20 downloads" in mail.text
    assert mail.to == ["joao@gmail.com"]


def _svc(pedidos, sender=None, storage=None):
    return DeliveryService(
        pedidos=pedidos, email_sender=sender or FakeEmailSender(),
        assets=AssetService(storage or FakeStorageBackend()), public_url="https://s.test", now_fn=lambda: NOW,
    )


def test_send_once_is_idempotent():
    pedidos, sender = FakePedidoStore(), FakeEmailSender()
    row = pedidos.create({"token": "t", "email": "a@b.com", "nome": "A", "produto": "P", "status": "pago"})
    svc = _svc(pedidos, sender)
    assert run(svc.send_once(row)) is True
    assert run(svc.send_once(pedidos.get_by_id(row["id"]))) is False
    assert len(sender.sent) == 1


def test_send_failure_releases_claim_and_records_error():
    pedidos, sender = FakePedidoStore(), FailingEmailSender("boom")
    row = pedidos.create({"token": "t", "email": "a@b.com", "nome": "A", "produto": "P", "status": "pago"})
    svc = _svc(pedidos, sender)
    with pytest.raises(DeliveryFailed):
        run(svc.send_once(row))
    after = pedidos.get_by_id(row["id"])
    assert after["email_enviado_em"] is None and "boom" in after["email_erro"]
    # claim released => a retry attempts the send again
    with pytest.raises(DeliveryFailed):
        run(svc.send_once(after))
    assert sender.attempts == 2


def test_resend_failure_keeps_previous_sent_marker():
    pedidos = FakePedidoStore()
    row = pedidos.create({"token": "t", "email": "a@b.com", "nome": "A", "produto": "P", "status": "pago",
                          "email_enviado_em": "2026-10-01T00:00:00+00:00"})
    with pytest.raises(DeliveryFailed):
        run(_svc(pedidos, FailingEmailSender()).resend(row))
    after = pedidos.get_by_id(row["id"])
    assert after["email_enviado_em"] == "2026-10-01T00:00:00+00:00"
    assert after["email_erro"]


def test_take_download_exhaustion_is_atomic_at_the_store():
    storage = FakeStorageBackend()
    run(storage.put(bucket=BUCKET, key=KIT_KEY, data=b"PK\x03\x04"))
    pedidos = FakePedidoStore()
    row = pedidos.create({"token": "t", "email": "a@b.com", "nome": "A", "produto": "P", "status": "pago",
                          "pago_em": NOW.isoformat(), "downloads": 19})
    svc = _svc(pedidos, storage=storage)
    assert run(svc.take_download(row)).startswith("fake://")
    with pytest.raises(DownloadRefused) as exc:
        run(svc.take_download(pedidos.get_by_id(row["id"])))
    assert exc.value.status_code == 410
    assert pedidos.get_by_id(row["id"])["downloads"] == 20


def test_status_view_hides_download_when_expired():
    pedidos = FakePedidoStore()
    old = (NOW - timedelta(days=40)).isoformat()
    view = _svc(pedidos).status_view(_pedido(pago_em=old))
    assert view["status"] == "pago" and view["download_url"] is None
