"""Persistence-seam tests — Protocol conformance + Fake/Real parity.

The parity suite is the load-bearing part. Every behavioural test runs
against BOTH :class:`InMemoryRecordStore` and :class:`SqliteRecordStore`
through the same parametrised fixture, so a divergence between the Fake
and the backend the app actually runs on fails here rather than in
production. That is the specific failure the Fake+Real pattern exists to
prevent (``KB § PATTERNS/backend/seed-fake-real-adapter.md``).
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.persistence import (
    InMemoryRecordStore,
    Op,
    PersistenceError,
    QuerySpec,
    RecordNotFound,
    RecordStore,
    SqliteRecordStore,
    SupabaseRecordStore,
    get_record_store,
)

ORG_A = "org-aaa"
ORG_B = "org-bbb"

_SCHEMA = """
CREATE TABLE cliente (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    nome        TEXT,
    nicho       TEXT,
    mrr         REAL,
    encerrado_em TEXT,
    metadados   TEXT,
    created_at  TEXT,
    updated_at  TEXT
);
"""


@pytest.fixture(params=["fake", "sqlite"])
def store(request) -> RecordStore:
    """Both implementations, same assertions."""
    if request.param == "fake":
        return InMemoryRecordStore()
    sqlite_store = SqliteRecordStore(":memory:")
    sqlite_store.executescript(_SCHEMA)
    return sqlite_store


# ── Protocol conformance ────────────────────────────────────────────
def test_every_implementation_satisfies_the_protocol():
    assert isinstance(InMemoryRecordStore(), RecordStore)
    assert isinstance(SqliteRecordStore(":memory:"), RecordStore)
    assert isinstance(SupabaseRecordStore(client=object()), RecordStore)


# ── factory ─────────────────────────────────────────────────────────
def test_factory_returns_in_memory_without_signals():
    assert isinstance(get_record_store(), InMemoryRecordStore)


def test_factory_returns_sqlite_for_a_path(tmp_path):
    store = get_record_store(sqlite_path=tmp_path / "igig.db")
    assert isinstance(store, SqliteRecordStore)


def test_factory_prefers_supabase_over_a_stale_sqlite_path(tmp_path):
    """A configured production backend must never be shadowed by a local file."""
    store = get_record_store(supabase_client=object(), sqlite_path=tmp_path / "igig.db")
    assert isinstance(store, SupabaseRecordStore)


# ── CRUD parity ─────────────────────────────────────────────────────
def test_insert_returns_the_persisted_row_with_generated_columns(store):
    row = store.insert("cliente", ORG_A, {"nome": "Padaria Sol"})
    assert row["nome"] == "Padaria Sol"
    assert row["org_id"] == ORG_A
    assert row["id"], "insert must return a generated id"
    assert row["created_at"], "insert must return a generated created_at"


def test_get_round_trips_an_inserted_row(store):
    created = store.insert("cliente", ORG_A, {"nome": "Padaria Sol"})
    assert store.get("cliente", ORG_A, created["id"])["nome"] == "Padaria Sol"


def test_update_patches_and_stamps_updated_at(store):
    created = store.insert("cliente", ORG_A, {"nome": "Padaria Sol", "nicho": "food"})
    updated = store.update("cliente", ORG_A, created["id"], {"nicho": "alimentacao"})
    assert updated["nicho"] == "alimentacao"
    assert updated["nome"] == "Padaria Sol", "patch must not clear untouched columns"
    assert updated["updated_at"]


def test_update_cannot_move_a_row_between_orgs(store):
    """id/org_id are structural — a patch may not rewrite tenancy."""
    created = store.insert("cliente", ORG_A, {"nome": "Padaria Sol"})
    store.update("cliente", ORG_A, created["id"], {"org_id": ORG_B, "id": "hijacked"})
    assert store.get("cliente", ORG_A, created["id"])["org_id"] == ORG_A
    with pytest.raises(RecordNotFound):
        store.get("cliente", ORG_B, created["id"])


def test_delete_reports_whether_a_row_went(store):
    created = store.insert("cliente", ORG_A, {"nome": "Padaria Sol"})
    assert store.delete("cliente", ORG_A, created["id"]) is True
    assert store.delete("cliente", ORG_A, created["id"]) is False


# ── tenant isolation (the RLS substitute) ───────────────────────────
def test_get_across_orgs_is_indistinguishable_from_absent(store):
    """A cross-tenant read must not leak that the id exists."""
    created = store.insert("cliente", ORG_A, {"nome": "Padaria Sol"})
    with pytest.raises(RecordNotFound):
        store.get("cliente", ORG_B, created["id"])


def test_list_never_crosses_orgs(store):
    store.insert("cliente", ORG_A, {"nome": "A-um"})
    store.insert("cliente", ORG_A, {"nome": "A-dois"})
    store.insert("cliente", ORG_B, {"nome": "B-um"})
    assert {r["nome"] for r in store.list("cliente", ORG_A)} == {"A-um", "A-dois"}
    assert {r["nome"] for r in store.list("cliente", ORG_B)} == {"B-um"}


def test_delete_cannot_reach_another_org(store):
    created = store.insert("cliente", ORG_A, {"nome": "Padaria Sol"})
    assert store.delete("cliente", ORG_B, created["id"]) is False
    assert store.get("cliente", ORG_A, created["id"])["nome"] == "Padaria Sol"


def test_count_is_org_scoped(store):
    store.insert("cliente", ORG_A, {"nome": "A-um"})
    store.insert("cliente", ORG_B, {"nome": "B-um"})
    assert store.count("cliente", ORG_A) == 1


# ── QuerySpec semantics ─────────────────────────────────────────────
def test_eq_and_neq_filters(store):
    store.insert("cliente", ORG_A, {"nome": "A", "nicho": "food"})
    store.insert("cliente", ORG_A, {"nome": "B", "nicho": "moda"})
    eq = store.list("cliente", ORG_A, QuerySpec().with_filter("nicho", Op.EQ, "food"))
    assert [r["nome"] for r in eq] == ["A"]
    neq = store.list("cliente", ORG_A, QuerySpec().with_filter("nicho", Op.NEQ, "food"))
    assert [r["nome"] for r in neq] == ["B"]


def test_numeric_comparisons(store):
    store.insert("cliente", ORG_A, {"nome": "A", "mrr": 1000.0})
    store.insert("cliente", ORG_A, {"nome": "B", "mrr": 5000.0})
    got = store.list("cliente", ORG_A, QuerySpec().with_filter("mrr", Op.GTE, 5000.0))
    assert [r["nome"] for r in got] == ["B"]


def test_in_filter(store):
    store.insert("cliente", ORG_A, {"nome": "A", "nicho": "food"})
    store.insert("cliente", ORG_A, {"nome": "B", "nicho": "moda"})
    store.insert("cliente", ORG_A, {"nome": "C", "nicho": "tech"})
    got = store.list("cliente", ORG_A, QuerySpec().with_filter("nicho", Op.IN, ["food", "tech"]))
    assert {r["nome"] for r in got} == {"A", "C"}


def test_empty_in_filter_matches_nothing_rather_than_erroring(store):
    """`IN ()` is a SQL syntax error — the seam must encode it as false."""
    store.insert("cliente", ORG_A, {"nome": "A", "nicho": "food"})
    assert store.list("cliente", ORG_A, QuerySpec().with_filter("nicho", Op.IN, [])) == []


def test_contains_is_case_insensitive(store):
    store.insert("cliente", ORG_A, {"nome": "Padaria Sol"})
    got = store.list("cliente", ORG_A, QuerySpec().with_filter("nome", Op.CONTAINS, "sol"))
    assert len(got) == 1


def test_is_null_both_directions(store):
    store.insert("cliente", ORG_A, {"nome": "ativo", "encerrado_em": None})
    store.insert("cliente", ORG_A, {"nome": "encerrado", "encerrado_em": "2026-01-01"})
    ativos = store.list("cliente", ORG_A, QuerySpec().with_filter("encerrado_em", Op.IS_NULL, True))
    assert [r["nome"] for r in ativos] == ["ativo"]
    encerrados = store.list("cliente", ORG_A, QuerySpec().with_filter("encerrado_em", Op.IS_NULL, False))
    assert [r["nome"] for r in encerrados] == ["encerrado"]


def test_null_columns_compare_false_to_value_predicates(store):
    """SQL three-valued logic: NULL matches nothing except IS NULL."""
    store.insert("cliente", ORG_A, {"nome": "sem-mrr", "mrr": None})
    assert store.list("cliente", ORG_A, QuerySpec().with_filter("mrr", Op.GTE, 0)) == []


def test_order_limit_and_offset(store):
    for nome, mrr in (("A", 300.0), ("B", 100.0), ("C", 200.0)):
        store.insert("cliente", ORG_A, {"nome": nome, "mrr": mrr})
    from noctusai_lib.integrations.persistence import Order

    spec = QuerySpec(order_by=(Order("mrr", descending=True),), limit=2)
    assert [r["nome"] for r in store.list("cliente", ORG_A, spec)] == ["A", "C"]

    paged = QuerySpec(order_by=(Order("mrr", descending=True),), limit=2, offset=1)
    assert [r["nome"] for r in store.list("cliente", ORG_A, paged)] == ["C", "B"]


def test_offset_without_limit_is_supported(store):
    """SQLite needs a LIMIT before OFFSET — the adapter must supply one."""
    for nome in ("A", "B", "C"):
        store.insert("cliente", ORG_A, {"nome": nome})
    from noctusai_lib.integrations.persistence import Order

    spec = QuerySpec(order_by=(Order("nome"),), offset=1)
    assert [r["nome"] for r in store.list("cliente", ORG_A, spec)] == ["B", "C"]


def test_column_projection(store):
    store.insert("cliente", ORG_A, {"nome": "Padaria Sol", "nicho": "food"})
    got = store.list("cliente", ORG_A, QuerySpec(columns=("nome",)))
    assert got == [{"nome": "Padaria Sol"}]


def test_json_columns_round_trip(store):
    """dict/list survive the SQLite text encoding — the jsonb stand-in."""
    palette = {"primaria": "#f97316", "tons": ["#fff", "#000"]}
    created = store.insert("cliente", ORG_A, {"nome": "Padaria Sol", "metadados": palette})
    assert store.get("cliente", ORG_A, created["id"])["metadados"] == palette


# ── error contract ──────────────────────────────────────────────────
def test_update_on_a_missing_row_raises_not_found(store):
    with pytest.raises(RecordNotFound):
        store.update("cliente", ORG_A, "does-not-exist", {"nome": "x"})


def test_get_on_a_missing_row_raises_not_found(store):
    with pytest.raises(RecordNotFound):
        store.get("cliente", ORG_A, "does-not-exist")


# ── SQLite-specific hardening ───────────────────────────────────────
def test_sqlite_rejects_unsafe_identifiers():
    """Identifiers cannot be bound parameters, so they get an allowlist."""
    store = SqliteRecordStore(":memory:")
    store.executescript(_SCHEMA)
    with pytest.raises(PersistenceError):
        store.list("cliente; DROP TABLE cliente", ORG_A)
    with pytest.raises(PersistenceError):
        store.list("cliente", ORG_A, QuerySpec().with_filter("nome; DROP TABLE cliente", Op.EQ, "x"))


def test_sqlite_values_are_bound_not_interpolated():
    store = SqliteRecordStore(":memory:")
    store.executescript(_SCHEMA)
    hostile = "'; DROP TABLE cliente; --"
    store.insert("cliente", ORG_A, {"nome": hostile})
    assert store.list("cliente", ORG_A, QuerySpec().with_filter("nome", Op.EQ, hostile))


def test_sqlite_persists_to_disk(tmp_path):
    path = tmp_path / "igig.db"
    first = SqliteRecordStore(path)
    first.executescript(_SCHEMA)
    created = first.insert("cliente", ORG_A, {"nome": "Padaria Sol"})
    first.close()

    second = SqliteRecordStore(path)
    assert second.get("cliente", ORG_A, created["id"])["nome"] == "Padaria Sol"
    second.close()


# ── filter validation ───────────────────────────────────────────────
def test_in_filter_rejects_a_scalar():
    from noctusai_lib.integrations.persistence import Filter

    with pytest.raises(ValueError, match="needs a sequence"):
        Filter("nicho", Op.IN, "food")


def test_is_null_filter_rejects_a_non_bool():
    from noctusai_lib.integrations.persistence import Filter

    with pytest.raises(ValueError, match="needs a bool"):
        Filter("encerrado_em", Op.IS_NULL, "yes")
