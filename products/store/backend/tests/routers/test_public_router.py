"""Public storefront routes — status-pinned, no auth dependency."""
import asyncio
from datetime import datetime, timedelta, timezone

from app.services.assets import BUCKET, KIT_KEY
from app.services.settings_service import DEFAULT_SETTINGS

VALID_CPF = "529.982.247-25"  # public check-digit-valid sample CPF


def run(coro):
    return asyncio.run(coro)


def _seed_pedido(store, **overrides):
    row = {
        "token": "tok-abc",
        "nome": "Maria Souza",
        "email": "maria@gmail.com",
        "cpf": "52998224725",
        "valor_cents": 4700,
        "produto": "Contrato Blindado de Compra e Venda",
        "status": "pago",
        "gateway": "asaas",
        "pago_em": datetime.now(timezone.utc).isoformat(),
    }
    row.update(overrides)
    return store.pedidos.create(row)


def _put_kit(store):
    run(store.storage.put(bucket=BUCKET, key=KIT_KEY, data=b"PK\x03\x04zip"))


class TestPublicSettings:
    def test_returns_defaults_with_derived_total(self, store):
        resp = store.client.raw().get("/api/public/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["price_cents"] == 4700
        assert body["anchor_total_cents"] == 9700 + 9700 + 12700 + 4700
        assert body["author"]["photo_url"] is None
        assert body["author"]["has_photo"] is False

    def test_photo_url_when_photo_exists(self, store):
        run(store.storage.put(bucket=BUCKET, key="autor/foto.jpg", data=b"\xff\xd8\xffjpg"))
        resp = store.client.raw().get("/api/public/settings")
        assert resp.status_code == 200
        assert resp.json()["author"]["photo_url"] == "/api/public/autor/foto"
        assert resp.json()["author"]["has_photo"] is True

    def test_needs_no_auth(self, store):
        assert store.client.raw().get("/api/public/settings").status_code == 200


class TestAuthorPhoto:
    def test_404_when_none(self, store):
        assert store.client.raw().get("/api/public/autor/foto", follow_redirects=False).status_code == 404

    def test_redirects_to_signed_url(self, store):
        run(store.storage.put(bucket=BUCKET, key="autor/foto.png", data=b"\x89PNG\r\n\x1a\n"))
        resp = store.client.raw().get("/api/public/autor/foto", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].startswith("fake://storage/store-produtos/autor/foto.png")


class TestCheckout:
    def _post(self, store, **over):
        body = {"nome": "Maria Souza", "email": "Maria@Gmail.com", "cpf": VALID_CPF}
        body.update(over)
        return store.client.raw().post("/api/public/checkout", json=body)

    def test_creates_pedido_and_returns_url(self, store):
        resp = self._post(store)
        assert resp.status_code == 201
        body = resp.json()
        assert body["checkout_url"].startswith("https://checkout.fake.test/")
        pedido = store.pedidos.get_by_token(body["pedido_token"])
        assert pedido["status"] == "pendente"
        assert pedido["email"] == "maria@gmail.com"
        assert pedido["cpf"] == "52998224725"
        assert pedido["gateway_charge_id"].startswith("pay_")

    def test_price_comes_from_settings_not_the_client(self, store):
        resp = self._post(store, valor_cents=1)
        assert resp.status_code == 422  # extra field forbidden
        ok = self._post(store)
        assert ok.status_code == 201
        pedido = store.pedidos.get_by_token(ok.json()["pedido_token"])
        assert pedido["valor_cents"] == DEFAULT_SETTINGS["price_cents"]
        request = store.checkout.calls[-1][1]
        assert request.price.amount_cents == 4700
        assert request.billing_cycle is None
        assert request.success_url.endswith(f"/obrigado?pedido={ok.json()['pedido_token']}")

    def test_invalid_cpf_422(self, store):
        resp = self._post(store, cpf="111.111.111-11")
        assert resp.status_code == 422
        assert resp.json()["field"] == "cpf"
        assert store.pedidos.rows == {}

    def test_invalid_email_422(self, store):
        resp = self._post(store, email="not-an-email")
        assert resp.status_code == 422
        assert resp.json()["field"] == "email"

    def test_checkout_disabled_409(self, store):
        data = {**DEFAULT_SETTINGS, "checkout_enabled": False}
        store.settings.append(version=1, data=data, created_by=None)
        resp = self._post(store)
        assert resp.status_code == 409
        assert resp.json()["code"] == "checkout_disabled"
        assert store.pedidos.rows == {}

    def test_unconfigured_gateway_503(self, client):
        # No `store` fixture: the real `build_hosted_checkout` runs with no
        # ASAAS_API_KEY and no PAYMENTS_ALLOW_FAKE -> refuse, never a Fake.
        from app import store_deps
        from app.main import app

        from tests.support.fakes import FakePedidoStore, FakeSettingsStore

        pedidos = FakePedidoStore()
        overrides = {
            store_deps.get_settings_store: lambda: FakeSettingsStore(),
            store_deps.get_pedido_store: lambda: pedidos,
        }
        app.dependency_overrides.update(overrides)
        try:
            resp = client.raw().post(
                "/api/public/checkout", json={"nome": "Maria Souza", "email": "m@gmail.com", "cpf": VALID_CPF}
            )
        finally:
            for dep in overrides:
                app.dependency_overrides.pop(dep, None)
        assert resp.status_code == 503
        assert pedidos.rows == {}

    def test_gateway_failure_marks_pedido_falhou_502(self, store, caplog):
        from noctusai_lib.integrations.payments import PaymentGatewayError

        class _Boom:
            def create_checkout(self, request):
                raise PaymentGatewayError(
                    "asaas", "Não há nenhum domínio configurado em sua conta.",
                    status=400, code="invalid_object", retryable=False,
                )

        from app import store_deps
        from app.main import app

        app.dependency_overrides[store_deps.get_checkout_factory] = lambda: (lambda: _Boom())
        try:
            resp = self._post(store)
        finally:
            app.dependency_overrides[store_deps.get_checkout_factory] = lambda: (lambda: store.checkout)
        assert resp.status_code == 502
        (row,) = store.pedidos.rows.values()
        assert row["status"] == "falhou"
        # The gateway's own reason reaches the log — the status alone hid an
        # Asaas account-setup gap on the first sandbox run (2026-10-03).
        logged = " ".join(r.getMessage() for r in caplog.records if "gateway refused" in r.getMessage())
        assert "invalid_object" in logged and "domínio configurado" in logged
        # ...but never to the buyer.
        assert "domínio" not in resp.text

    def test_unknown_field_422(self, store):
        assert self._post(store, extra="x").status_code == 422


class TestPedidoStatus:
    def test_pending_has_no_download_url(self, store):
        _seed_pedido(store, status="pendente", pago_em=None)
        resp = store.client.raw().get("/api/public/pedidos/tok-abc")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "pendente"
        assert body["download_url"] is None
        assert body["email_mascarado"] == "m***@gmail.com"

    def test_paid_has_download_url(self, store):
        _seed_pedido(store)
        body = store.client.raw().get("/api/public/pedidos/tok-abc").json()
        assert body["status"] == "pago"
        assert body["download_url"] == "/api/public/download/tok-abc"

    def test_refunded_has_no_download_url(self, store):
        _seed_pedido(store, status="reembolsado")
        assert store.client.raw().get("/api/public/pedidos/tok-abc").json()["download_url"] is None

    def test_unknown_token_404(self, store):
        assert store.client.raw().get("/api/public/pedidos/nope").status_code == 404

    def test_response_never_leaks_cpf_or_full_email(self, store):
        _seed_pedido(store)
        text = store.client.raw().get("/api/public/pedidos/tok-abc").text
        assert "52998224725" not in text and "maria@gmail.com" not in text


class TestDownload:
    def test_paid_redirects_and_counts(self, store):
        _put_kit(store)
        _seed_pedido(store)
        resp = store.client.raw().get("/api/public/download/tok-abc", follow_redirects=False)
        assert resp.status_code == 302
        assert KIT_KEY in resp.headers["location"]
        assert store.pedidos.get_by_token("tok-abc")["downloads"] == 1

    def test_pending_404(self, store):
        _put_kit(store)
        _seed_pedido(store, status="pendente", pago_em=None)
        assert store.client.raw().get("/api/public/download/tok-abc", follow_redirects=False).status_code == 404

    def test_refunded_410(self, store):
        _put_kit(store)
        _seed_pedido(store, status="reembolsado")
        assert store.client.raw().get("/api/public/download/tok-abc", follow_redirects=False).status_code == 410
        assert store.pedidos.get_by_token("tok-abc")["downloads"] == 0

    def test_expired_after_30_days_410(self, store):
        _put_kit(store)
        old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        _seed_pedido(store, pago_em=old)
        assert store.client.raw().get("/api/public/download/tok-abc", follow_redirects=False).status_code == 410

    def test_limit_of_20_then_410(self, store):
        _put_kit(store)
        _seed_pedido(store)
        statuses = [
            store.client.raw().get("/api/public/download/tok-abc", follow_redirects=False).status_code
            for _ in range(21)
        ]
        assert statuses[:20] == [302] * 20
        assert statuses[20] == 410
        assert store.pedidos.get_by_token("tok-abc")["downloads"] == 20

    def test_missing_kit_503_does_not_consume_a_download(self, store):
        _seed_pedido(store)
        assert store.client.raw().get("/api/public/download/tok-abc", follow_redirects=False).status_code == 503
        assert store.pedidos.get_by_token("tok-abc")["downloads"] == 0

    def test_unknown_token_404(self, store):
        assert store.client.raw().get("/api/public/download/nope", follow_redirects=False).status_code == 404
