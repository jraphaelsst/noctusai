"""Shape tests for the Real stores against `MockSupabaseClient` (schema
validation ON — the mock cross-checks columns against the migration files)."""
import pytest

from noctusai_lib.testing import MockSupabaseClient

from app.stores import SupabasePedidoStore, SupabaseSettingsStore, VersionConflict


def _client(**tables):
    c = MockSupabaseClient(schema="store")
    for name, rows in tables.items():
        c.set_table_data(name, rows)
    return c


def test_settings_current_none_when_empty():
    assert SupabaseSettingsStore(lambda: _client(landing_settings=[])).current() is None


def test_settings_current_returns_row():
    row = {"version": 3, "data": {"price_cents": 1}, "created_by": None, "created_at": "x"}
    assert SupabaseSettingsStore(lambda: _client(landing_settings=[row])).current() == row


def test_settings_append_inserts_the_version_row():
    c = _client(landing_settings=[])
    SupabaseSettingsStore(lambda: c).append(version=2, data={"a": 1}, created_by="u")
    assert c.table("landing_settings").inserted_payloads == [{"version": 2, "data": {"a": 1}, "created_by": "u"}]


def test_settings_append_unique_violation_is_a_version_conflict():
    class _Dup(Exception):
        code = "23505"

    class _Builder:
        def insert(self, *_a, **_k):
            return self

        def execute(self):
            raise _Dup()

    class _Client:
        def table(self, _n):
            return _Builder()

    with pytest.raises(VersionConflict):
        SupabaseSettingsStore(lambda: _Client()).append(version=2, data={}, created_by=None)


def test_pedido_create_and_lookups_use_bare_table_names():
    row = {"id": "i1", "token": "t1", "status": "pendente", "gateway_charge_id": "pay_1"}
    c = _client(pedidos=[row])
    store = SupabasePedidoStore(lambda: c)
    assert store.get_by_token("t1")["id"] == "i1"
    assert store.get_by_id("i1")["token"] == "t1"
    assert store.get_by_charge_id("pay_1")["id"] == "i1"
    store.create({"token": "t2", "nome": "n", "email": "e@x.com", "cpf": "1", "valor_cents": 100, "produto": "p"})
    assert c.table("pedidos").inserted_payloads[-1]["token"] == "t2"


def test_claim_email_is_a_conditional_update_on_null():
    c = _client(pedidos=[{"id": "i1", "email_enviado_em": None}])
    store = SupabasePedidoStore(lambda: c)
    assert store.claim_email("i1", at_iso="2026-10-02T00:00:00+00:00") is True
    assert c.table("pedidos").updated_payloads[-1]["email_enviado_em"] == "2026-10-02T00:00:00+00:00"


def test_release_email_clears_marker_and_records_error():
    c = _client(pedidos=[{"id": "i1"}])
    SupabasePedidoStore(lambda: c).release_email("i1", error="boom")
    assert c.table("pedidos").updated_payloads[-1] == {"email_enviado_em": None, "email_erro": "boom"}


def test_take_download_refuses_at_the_cap_without_writing():
    c = _client(pedidos=[{"id": "i1", "token": "t1", "downloads": 20}])
    assert SupabasePedidoStore(lambda: c).take_download("t1", max_downloads=20) is False
    assert c.table("pedidos").updated_payloads == []


def test_take_download_unknown_token_false():
    assert SupabasePedidoStore(lambda: _client(pedidos=[])).take_download("nope", max_downloads=20) is False
