"""``gatherers.gather_audit`` — the default `"historico"` timeline kind.

Standalone (not the heavyweight `MockSupabaseClient`-backed `hub`
fixture in `conftest.py`): `gather_audit` queries `public.audit_logs`
through `cfg.get_core_client`, a DIFFERENT client/schema than every
other gatherer's product-scoped `db` — a minimal fake query-builder is
the right-sized double here.
"""
from __future__ import annotations

from noctusai_lib.domain.card_hub.config import CardHubConfig, MemberSource
from noctusai_lib.domain.card_hub.gatherers import gather_audit

ORG_ID = "5b0e8f7a-1c2d-4e3f-9a8b-7c6d5e4f3a2b"
ENTITY_ID = "c0ffee00-0000-0000-0000-000000000001"


class _FakeAuditQuery:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.calls: list[tuple] = []

    def select(self, *a):
        self.calls.append(("select", a))
        return self

    def eq(self, *a):
        self.calls.append(("eq", a))
        return self

    def contains(self, *a):
        self.calls.append(("contains", a))
        return self

    def order(self, *a, **kw):
        self.calls.append(("order", a, kw))
        return self

    def limit(self, *a):
        self.calls.append(("limit", a))
        return self

    def execute(self):
        return type("Resp", (), {"data": self._rows})()


class _FakeAuditTable:
    def __init__(self, query: _FakeAuditQuery) -> None:
        self._query = query
        self.table_name: str | None = None

    def table(self, name: str):
        self.table_name = name
        return self._query


class _FakeAdmin:
    def __init__(self, rows: list[dict]) -> None:
        self.schema_calls: list[str] = []
        self._table_iface = _FakeAuditTable(_FakeAuditQuery(rows))

    def schema(self, name: str):
        self.schema_calls.append(name)
        return self._table_iface


def _cfg(get_core_client, *, audit_trail_enabled: bool = True) -> CardHubConfig:
    return CardHubConfig(
        entity_kind="lead",
        entity_table="leads",
        entity_fk="lead_id",
        id_param="lead_id",
        table_prefix="lead",
        member_source=MemberSource(table="membros_equipe", fk="corretor_id"),
        bucket="lead-documentos",
        actor_resolver=lambda ids: {
            str(i): {"id": str(i), "nome": f"User {i}"} for i in ids
        },
        audit_trail_enabled=audit_trail_enabled,
        get_core_client=get_core_client,
    )


def test_config_wires_historico_gatherer_only_when_flag_and_client_are_both_set() -> None:
    enabled_cfg = _cfg(lambda: _FakeAdmin([]), audit_trail_enabled=True)
    assert enabled_cfg.timeline_gatherers["historico"] is gather_audit

    disabled_cfg = _cfg(lambda: _FakeAdmin([]), audit_trail_enabled=False)
    assert "historico" not in disabled_cfg.timeline_gatherers

    no_client_cfg = _cfg(None, audit_trail_enabled=True)
    assert "historico" not in no_client_cfg.timeline_gatherers


def test_gather_audit_maps_rows_to_timeline_entries() -> None:
    rows = [
        {
            "id": "row-1",
            "user_id": "u1",
            "created_at": "2026-09-20T10:00:00+00:00",
            "action": "POST",
            "details": {
                "route_template": "/api/leads/{lead_id}",
                "status": 201,
                "actor_kind": "user",
                "path_params": {"lead_id": ENTITY_ID},
            },
        },
    ]
    admin = _FakeAdmin(rows)
    cfg = _cfg(lambda: admin)

    entries = gather_audit(cfg, db=None, org_id=ORG_ID, entity_id=ENTITY_ID, entity={})

    assert admin.schema_calls == ["public"]
    assert admin._table_iface.table_name == "audit_logs"
    query_calls = dict((c[0], c) for c in admin._table_iface._query.calls)
    assert query_calls["eq"][1] == ("org_id", ORG_ID)
    assert query_calls["contains"][1] == ("details", {"path_params": {"lead_id": ENTITY_ID}})

    assert len(entries) == 1
    entry = entries[0]
    assert entry["kind"] == "historico"
    assert entry["id"] == "row-1"
    assert entry["ocorrido_em"] == "2026-09-20T10:00:00+00:00"
    assert entry["ator"] == {"id": "u1", "nome": "User u1"}
    assert entry["payload"] == {
        "method": "POST",
        "route_template": "/api/leads/{lead_id}",
        "status": 201,
        "actor_kind": "user",
    }


def test_gather_audit_handles_rows_with_no_actor() -> None:
    rows = [
        {
            "id": "row-2",
            "user_id": None,
            "created_at": "2026-09-20T11:00:00+00:00",
            "action": "DELETE",
            "details": {},
        },
    ]
    admin = _FakeAdmin(rows)
    cfg = _cfg(lambda: admin)

    entries = gather_audit(cfg, db=None, org_id=ORG_ID, entity_id=ENTITY_ID, entity={})

    assert entries[0]["ator"] is None
