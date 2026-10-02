"""Admin routes — strict 401 without a token, 403 for a signed-in non-admin,
200 for the allow-listed owner (case-insensitive)."""
import asyncio
import io

from app.services.assets import BUCKET, KIT_KEY
from app.services.settings_service import DEFAULT_SETTINGS
from tests.conftest import as_admin, as_other_user

ADMIN_ROUTES = [
    ("get", "/api/admin/settings", None),
    ("put", "/api/admin/settings", {"data": DEFAULT_SETTINGS, "expected_version": 0}),
    ("get", "/api/admin/produto/arquivo", None),
    ("get", "/api/admin/pedidos", None),
    ("post", "/api/admin/pedidos/x/reenviar", None),
]


def _call(c, method, path, body=None):
    return getattr(c, method)(path, json=body) if body is not None else getattr(c, method)(path)


class TestGate:
    def test_every_admin_route_requires_a_token_401(self, store):
        raw = store.client.raw()
        for method, path, body in ADMIN_ROUTES:
            assert _call(raw, method, path, body).status_code == 401, (method, path)
        assert raw.post("/api/admin/autor/foto", files={"file": ("a.png", b"x", "image/png")}).status_code == 401
        assert raw.post("/api/admin/produto/arquivo", files={"file": ("k.zip", b"x", "application/zip")}).status_code == 401

    def test_signed_in_non_admin_gets_403_everywhere(self, store):
        as_other_user(store.client)
        for method, path, body in ADMIN_ROUTES:
            assert _call(store.client, method, path, body).status_code == 403, (method, path)
        assert store.client.post("/api/admin/autor/foto", files={"file": ("a.png", b"x", "image/png")}).status_code == 403
        assert store.client.post("/api/admin/produto/arquivo", files={"file": ("k.zip", b"x", "application/zip")}).status_code == 403

    def test_admin_email_match_is_case_insensitive(self, store):
        from noctusai_lib.testing import bind_user_metadata

        bind_user_metadata(store.client, email=store.admin_email.upper(), org_id="test-org-123")
        assert store.client.get("/api/admin/settings").status_code == 200

    def test_empty_allowlist_means_nobody(self, store):
        from app.dependencies import get_store_admin_emails
        from app.main import app

        as_admin(store.client)
        app.dependency_overrides[get_store_admin_emails] = lambda: frozenset()
        try:
            assert store.client.get("/api/admin/settings").status_code == 403
        finally:
            app.dependency_overrides[get_store_admin_emails] = lambda: frozenset({store.admin_email})


class TestSettings:
    def test_get_returns_version_and_data(self, store):
        as_admin(store.client)
        body = store.client.get("/api/admin/settings").json()
        assert body["version"] == 0
        assert body["data"]["price_cents"] == 4700
        assert body["data"]["author"]["has_photo"] is False

    def test_put_creates_new_version(self, store):
        as_admin(store.client)
        data = {**DEFAULT_SETTINGS, "price_cents": 5900}
        resp = store.client.put("/api/admin/settings", json={"data": data, "expected_version": 0})
        assert resp.status_code == 200
        assert resp.json() == {"version": 1}
        got = store.client.get("/api/admin/settings").json()
        assert got["version"] == 1 and got["data"]["price_cents"] == 5900
        # the ledger is append-only
        assert len(store.settings.rows) == 1

    def test_stale_version_409(self, store):
        as_admin(store.client)
        store.client.put("/api/admin/settings", json={"data": DEFAULT_SETTINGS, "expected_version": 0})
        stale = store.client.put("/api/admin/settings", json={"data": DEFAULT_SETTINGS, "expected_version": 0})
        assert stale.status_code == 409
        assert stale.json()["code"] == "version_conflict"
        assert len(store.settings.rows) == 1

    def test_public_reflects_the_new_price_for_checkout(self, store):
        as_admin(store.client)
        store.client.put(
            "/api/admin/settings", json={"data": {**DEFAULT_SETTINGS, "price_cents": 5900}, "expected_version": 0}
        )
        assert store.client.raw().get("/api/public/settings").json()["price_cents"] == 5900
        resp = store.client.raw().post(
            "/api/public/checkout", json={"nome": "Maria Souza", "email": "m@gmail.com", "cpf": "52998224725"}
        )
        assert resp.status_code == 201
        assert store.checkout.calls[-1][1].price.amount_cents == 5900

    def test_validation_422(self, store):
        as_admin(store.client)
        bad_cases = [
            {**DEFAULT_SETTINGS, "price_cents": 99},
            {**DEFAULT_SETTINGS, "price_cents": 1_000_001},
            {**DEFAULT_SETTINGS, "items": []},
            {**DEFAULT_SETTINGS, "items": [{"label": "x", "anchor_cents": 1}] * 9},
            {**DEFAULT_SETTINGS, "guarantee_days": 31},
            {**DEFAULT_SETTINGS, "guarantee_days": -1},
            {**DEFAULT_SETTINGS, "author": {**DEFAULT_SETTINGS["author"], "bio": "x" * 601}},
            {**DEFAULT_SETTINGS, "unknown": 1},
        ]
        for data in bad_cases:
            resp = store.client.put("/api/admin/settings", json={"data": data, "expected_version": 0})
            assert resp.status_code == 422, data.get("price_cents")
        assert store.settings.rows == []

    def test_boundary_values_accepted(self, store):
        as_admin(store.client)
        data = {
            **DEFAULT_SETTINGS,
            "price_cents": 100,
            "guarantee_days": 0,
            "items": [{"label": "x", "anchor_cents": 0}] * 8,
            "author": {**DEFAULT_SETTINGS["author"], "bio": "x" * 600},
        }
        assert store.client.put("/api/admin/settings", json={"data": data, "expected_version": 0}).status_code == 200

    def test_client_cannot_forge_has_photo(self, store):
        as_admin(store.client)
        data = {**DEFAULT_SETTINGS, "author": {**DEFAULT_SETTINGS["author"], "has_photo": True}}
        store.client.put("/api/admin/settings", json={"data": data, "expected_version": 0})
        assert store.settings.current()["data"]["author"]["has_photo"] is False
        assert store.client.get("/api/admin/settings").json()["data"]["author"]["has_photo"] is False


class TestUploads:
    def test_photo_upload_takes_effect_immediately(self, store):
        as_admin(store.client)
        resp = store.client.post(
            "/api/admin/autor/foto", files={"file": ("me.png", b"\x89PNG\r\n\x1a\nrest", "image/png")}
        )
        assert resp.status_code == 200
        assert store.client.get("/api/admin/settings").json()["data"]["author"]["has_photo"] is True
        pub = store.client.raw().get("/api/public/settings").json()
        assert pub["author"]["photo_url"] == "/api/public/autor/foto"

    def test_photo_replaces_previous_even_with_other_extension(self, store):
        as_admin(store.client)
        store.client.post("/api/admin/autor/foto", files={"file": ("a.png", b"\x89PNG\r\n\x1a\n1", "image/png")})
        store.client.post("/api/admin/autor/foto", files={"file": ("a.jpg", b"\xff\xd8\xff2", "image/jpeg")})
        keys = asyncio.run(store.storage.list_keys(bucket=BUCKET, prefix="autor/"))
        assert keys == ["autor/foto.jpg"]

    def test_photo_wrong_type_422(self, store):
        as_admin(store.client)
        resp = store.client.post("/api/admin/autor/foto", files={"file": ("a.gif", b"GIF89a", "image/gif")})
        assert resp.status_code == 422

    def test_photo_content_not_matching_type_422(self, store):
        as_admin(store.client)
        resp = store.client.post("/api/admin/autor/foto", files={"file": ("a.png", b"<html>", "image/png")})
        assert resp.status_code == 422

    def test_photo_over_5mb_413(self, store):
        as_admin(store.client)
        big = b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024)
        resp = store.client.post("/api/admin/autor/foto", files={"file": ("a.png", io.BytesIO(big), "image/png")})
        assert resp.status_code == 413

    def test_kit_upload_and_info(self, store):
        as_admin(store.client)
        assert store.client.get("/api/admin/produto/arquivo").json() == {"exists": False, "size": None, "updated_at": None}
        resp = store.client.post(
            "/api/admin/produto/arquivo", files={"file": ("kit.zip", b"PK\x03\x04" + b"0" * 100, "application/zip")}
        )
        assert resp.status_code == 200
        info = store.client.get("/api/admin/produto/arquivo").json()
        assert info["exists"] is True and info["size"] == 104 and info["updated_at"]
        assert asyncio.run(store.storage.exists(bucket=BUCKET, key=KIT_KEY))

    def test_kit_not_a_zip_422(self, store):
        as_admin(store.client)
        resp = store.client.post("/api/admin/produto/arquivo", files={"file": ("kit.zip", b"hello", "application/zip")})
        assert resp.status_code == 422

    def test_kit_replaces_previous(self, store):
        as_admin(store.client)
        store.client.post("/api/admin/produto/arquivo", files={"file": ("k.zip", b"PK\x03\x04v1", "application/zip")})
        store.client.post("/api/admin/produto/arquivo", files={"file": ("k.zip", b"PK\x03\x04version2", "application/zip")})
        assert store.client.get("/api/admin/produto/arquivo").json()["size"] == 12


class TestPedidos:
    def _seed(self, store):
        a = store.pedidos.create({"token": "t1", "nome": "A", "email": "a@x.com", "cpf": "52998224725",
                                  "valor_cents": 4700, "produto": "P", "status": "pago", "gateway": "asaas"})
        b = store.pedidos.create({"token": "t2", "nome": "B", "email": "b@x.com", "cpf": "52998224725",
                                  "valor_cents": 4700, "produto": "P", "status": "pendente", "gateway": "asaas"})
        return a, b

    def test_list_items_newest_first_and_no_secrets(self, store):
        as_admin(store.client)
        a, b = self._seed(store)
        resp = store.client.get("/api/admin/pedidos")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert [i["id"] for i in items] == [b["id"], a["id"]]
        first = items[0]
        for key in ("id", "nome", "email", "valor_cents", "status", "created_at", "email_enviado_em", "downloads"):
            assert key in first
        assert first["cpf_mascarado"] == "***.***.***-25"
        assert "token" not in first and "cpf" not in first
        assert "52998224725" not in resp.text

    def test_filter_by_status(self, store):
        as_admin(store.client)
        a, _b = self._seed(store)
        items = store.client.get("/api/admin/pedidos?status=pago").json()["items"]
        assert [i["id"] for i in items] == [a["id"]]

    def test_invalid_status_filter_422(self, store):
        as_admin(store.client)
        assert store.client.get("/api/admin/pedidos?status=bogus").status_code == 422

    def test_resend_paid_sends_email_again(self, store):
        as_admin(store.client)
        a, _b = self._seed(store)
        resp = store.client.post(f"/api/admin/pedidos/{a['id']}/reenviar")
        assert resp.status_code == 200
        assert len(store.email.sent) == 1
        assert store.pedidos.get_by_id(a["id"])["email_enviado_em"] is not None

    def test_resend_unpaid_409(self, store):
        as_admin(store.client)
        _a, b = self._seed(store)
        assert store.client.post(f"/api/admin/pedidos/{b['id']}/reenviar").status_code == 409
        assert store.email.sent == []

    def test_resend_unknown_404(self, store):
        as_admin(store.client)
        assert store.client.post("/api/admin/pedidos/nope/reenviar").status_code == 404

    def test_resend_email_failure_502_and_recorded(self, store):
        from app import store_deps
        from app.main import app

        from tests.support.fakes import FailingEmailSender

        as_admin(store.client)
        a, _b = self._seed(store)
        app.dependency_overrides[store_deps.get_email_sender] = lambda: FailingEmailSender()
        try:
            resp = store.client.post(f"/api/admin/pedidos/{a['id']}/reenviar")
        finally:
            app.dependency_overrides[store_deps.get_email_sender] = lambda: store.email
        assert resp.status_code == 502
        assert "ConnectionError" in store.pedidos.get_by_id(a["id"])["email_erro"]
