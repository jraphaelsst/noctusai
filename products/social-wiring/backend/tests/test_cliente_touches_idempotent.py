"""`_insert_touches` is idempotent on the GLOBAL (origem_tabela, origem_id) unique.

THE INCIDENT (2026-10-09): fixture rows leaked into prod under a ghost org and
took the touch for a real lead. The correct org's backfill then failed every
run with 23505 on the bulk insert. A touch owned elsewhere is skipped + logged.
"""
from __future__ import annotations

import logging
from uuid import UUID, uuid4

import pytest

from noctusai_lib.testing import MockSupabaseClient

from app.services import clientes_service as svc

ORG = UUID("11111111-1111-4111-8111-111111111111")
GHOST = "00000000-0000-4000-8000-0000000000aa"


def _members(*ids):
    return [
        svc.SourceRow(
            origem_tabela="meta_ads_leads", origem_id=i, org_id=str(ORG), ocorreu_em="2026-01-01T00:00:00+00:00",
            nome="Ana", chave_canonica="+5511900000001", chave_tipo="telefone",
            origem_label="Meta",
        )
        for i in ids
    ]


def _client(existing):
    c = MockSupabaseClient()
    c.set_table_data("cliente_touches", existing)
    return c


def _ghost_touch(origem_id):
    return {
        "id": str(uuid4()), "org_id": GHOST, "cliente_id": str(uuid4()),
        "origem_tabela": "meta_ads_leads", "origem_id": origem_id,
    }


def test_touch_owned_by_another_org_is_skipped_with_warning(caplog):
    c = _client([_ghost_touch("X")])
    report = svc.BackfillReport(org_id=str(ORG), dry_run=False)
    cliente = str(uuid4())
    with caplog.at_level(logging.WARNING):
        svc._insert_touches(
            c, ORG, cliente, _members("X", "Y"), "+5511900000001", report, dry_run=False
        )
    rows = c.table("cliente_touches").select("*").execute().data
    mine = [r for r in rows if r["org_id"] == str(ORG)]
    assert [r["origem_id"] for r in mine] == ["Y"]
    assert report.touches_created == 1
    assert GHOST in caplog.text and cliente in caplog.text


def test_rerun_is_idempotent_for_own_touches():
    c = _client([])
    cliente = str(uuid4())
    for _ in range(2):
        svc._insert_touches(
            c, ORG, cliente, _members("A"), None, svc.BackfillReport(org_id=str(ORG), dry_run=False), dry_run=False
        )
    assert len(c.table("cliente_touches").select("*").execute().data) == 1


def test_race_on_unique_falls_back_row_by_row(monkeypatch):
    """A 23505 on the bulk insert (lost race after the pre-check) skips only the
    colliding rows; any other error still propagates."""
    c = MockSupabaseClient()
    c.set_table_data("cliente_touches", [])
    calls = {"n": 0}
    real_table = c.table

    def table(name):
        b = real_table(name)
        if name != "cliente_touches":
            return b
        real_insert = b.insert

        def insert(payload, *a, **k):
            calls["n"] += 1
            if isinstance(payload, list) and len(payload) > 1:
                raise Exception("duplicate key value violates unique constraint (23505)")
            if not isinstance(payload, list) and payload["origem_id"] == "X":
                raise Exception("duplicate key value violates unique constraint (23505)")
            return real_insert(payload, *a, **k)

        b.insert = insert
        return b

    c.table = table  # type: ignore[method-assign]  # test double wiring, not product code
    report = svc.BackfillReport(org_id=str(ORG), dry_run=False)
    svc._insert_touches(c, ORG, str(uuid4()), _members("X", "Y"), None, report, dry_run=False)
    assert report.touches_created == 1
    assert [r["origem_id"] for r in real_table("cliente_touches").select("*").execute().data] == ["Y"]


def test_non_unique_error_propagates():
    c = MockSupabaseClient()
    c.set_table_data("cliente_touches", [])
    real_table = c.table

    def table(name):
        b = real_table(name)
        if name == "cliente_touches":
            def boom(*a, **k):
                raise RuntimeError("connection reset")
            b.insert = boom
        return b

    c.table = table  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        svc._insert_touches(c, ORG, str(uuid4()), _members("Z"), None, svc.BackfillReport(org_id=str(ORG), dry_run=False), dry_run=False)
