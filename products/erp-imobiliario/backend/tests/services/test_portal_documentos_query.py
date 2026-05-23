"""Tests for the single gated portal `documentos` read helper.

`fetch_shared_documentos` is the one place the LGPD `compartilhado_portal=True`
gate lives. Both public portal read paths (the bearer-token router and the
dashboard service) call it, so a regression here is caught once for both.

Result-based — the MockSupabaseClient evaluates `.eq` predicates against the
seeded rows; nothing is monkeypatched, so the gate is exercised for real.
"""
from tests.conftest import MockSupabaseClient


def _seed_docs(db):
    db.set_table_data("documentos", [
        {"id": "shared", "cliente_id": "client-1", "org_id": "org-1",
         "compartilhado_portal": True, "created_at": "2026-01-10T10:00:00Z"},
        {"id": "private", "cliente_id": "client-1", "org_id": "org-1",
         "compartilhado_portal": False, "created_at": "2026-01-11T10:00:00Z"},
        {"id": "unset", "cliente_id": "client-1", "org_id": "org-1",
         "created_at": "2026-01-12T10:00:00Z"},
    ])
    return db


class TestFetchSharedDocumentos:

    def test_excludes_unshared_documents(self):
        """The gate surfaces ONLY rows with compartilhado_portal=True.

        Rows that are explicitly False OR missing the flag entirely must be
        excluded — this is the leak class the helper exists to prevent.
        """
        from app.services.portal_documentos_query import fetch_shared_documentos
        db = _seed_docs(MockSupabaseClient())

        rows = fetch_shared_documentos(db, cliente_id="client-1")

        ids = {d["id"] for d in rows}
        assert ids == {"shared"}, (
            f"portal helper leaked unshared documents: {ids}"
        )

    def test_org_scoping_when_org_id_given(self):
        """When org_id is provided it scopes the read; cross-org rows excluded."""
        from app.services.portal_documentos_query import fetch_shared_documentos
        db = MockSupabaseClient()
        db.set_table_data("documentos", [
            {"id": "mine", "cliente_id": "client-1", "org_id": "org-1",
             "compartilhado_portal": True, "created_at": "2026-01-10T10:00:00Z"},
            {"id": "other-org", "cliente_id": "client-1", "org_id": "org-2",
             "compartilhado_portal": True, "created_at": "2026-01-11T10:00:00Z"},
        ])

        rows = fetch_shared_documentos(db, cliente_id="client-1", org_id="org-1")

        ids = {d["id"] for d in rows}
        assert ids == {"mine"}, f"org scoping failed: {ids}"

    def test_no_org_id_skips_org_filter(self):
        """org_id=None (or omitted) skips the org filter — gate still applies."""
        from app.services.portal_documentos_query import fetch_shared_documentos
        db = _seed_docs(MockSupabaseClient())

        rows = fetch_shared_documentos(db, cliente_id="client-1", org_id=None)

        ids = {d["id"] for d in rows}
        assert ids == {"shared"}, f"gate must hold even without org scoping: {ids}"

    def test_filters_by_cliente_id(self):
        """Only the requested cliente's shared docs are returned."""
        from app.services.portal_documentos_query import fetch_shared_documentos
        db = MockSupabaseClient()
        db.set_table_data("documentos", [
            {"id": "mine", "cliente_id": "client-1",
             "compartilhado_portal": True, "created_at": "2026-01-10T10:00:00Z"},
            {"id": "theirs", "cliente_id": "client-2",
             "compartilhado_portal": True, "created_at": "2026-01-11T10:00:00Z"},
        ])

        rows = fetch_shared_documentos(db, cliente_id="client-1")

        ids = {d["id"] for d in rows}
        assert ids == {"mine"}, f"cliente_id scoping failed: {ids}"

    def test_empty_table_returns_empty_list(self):
        from app.services.portal_documentos_query import fetch_shared_documentos
        db = MockSupabaseClient()
        db.set_table_data("documentos", [])

        rows = fetch_shared_documentos(db, cliente_id="client-1")

        assert rows == []

    def test_gate_is_mandatory_no_unshared_escape_hatch(self):
        """Contract guard: the helper exposes NO way to include unshared docs.

        If a future edit adds an `include_unshared=True` (or similar) escape
        hatch, this test fails — re-asserting that the gate can never be
        turned off, which is what reintroduced the original P0 leak class.
        """
        import inspect
        from app.services import portal_documentos_query

        sig = inspect.signature(portal_documentos_query.fetch_shared_documentos)
        params = set(sig.parameters)
        assert params == {"db", "cliente_id", "org_id", "limit"}, (
            "fetch_shared_documentos must not grow an unshared/all-docs escape "
            f"hatch; signature drifted to: {sorted(params)}"
        )
