"""`_refresh_contato_from_sources` ran in every 6 h clientes backfill pass AND on every startup catch-up, and read
`clientes` ONCE PER CLIENTE (~10k reads per pass): the `GET clientes?id=eq.?&select=nome,celular,email` N+1
(2026-11-09 egress incident, ~16.6k/22h for that one shape; KB § PATTERNS/backend/polling-request-budget.md).
A fake client makes the N+1 free, so these tests COUNT the reads."""
from __future__ import annotations

from app.services import clientes_service as svc
from noctusai_lib.testing import MockSupabaseClient

ORG = "00000000-0000-4000-8000-000000000001"
N = 30


class _Counting:
    """Delegates to the scoped mock and counts `.select(...)` calls per table."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.selects: dict[str, int] = {}

    def table(self, name):
        outer = self
        builder = self._inner.table(name)

        class _P:
            def select(self, *a, **k):
                outer.selects[name] = outer.selects.get(name, 0) + 1
                return builder.select(*a, **k)

            def __getattr__(self, attr):
                return getattr(builder, attr)

        return _P()


def _setup(blank=True):
    inner = MockSupabaseClient().schema("social_wiring")
    inner.set_table_data("clientes", [
        {"id": f"c{i}", "org_id": ORG, "nome": f"Pessoa {i}", "celular": None if blank else "+5511900000000", "email": None}
        for i in range(N)
    ])
    inner.set_table_data("cliente_touches", [
        {"id": f"t{i}", "org_id": ORG, "cliente_id": f"c{i}", "origem_tabela": "leads", "origem_id": f"l{i}"}
        for i in range(N)
    ])
    sources = [
        svc.SourceRow(
            origem_tabela="leads", origem_id=f"l{i}", org_id=ORG, ocorreu_em="2026-01-01T00:00:00+00:00",
            nome=f"Pessoa {i}", chave_canonica=f"+55119000000{i:02d}", chave_tipo="telefone",
            telefone=f"+55119000000{i:02d}",
        )
        for i in range(N)
    ]
    return inner, _Counting(inner), sources


def test_refresh_reads_clientes_once_for_all_clusters_not_once_per_cliente():
    inner, client, sources = _setup()
    svc._refresh_contato_from_sources(client, ORG, sources)
    assert client.selects.get("clientes", 0) <= 2  # was N (one per cliente)
    rows = {r["id"]: r for r in inner.table("clientes").select("*").execute().data}
    assert all(rows[f"c{i}"]["celular"] for i in range(N))  # the fill-if-empty behaviour is unchanged


def test_a_steady_state_pass_writes_nothing_and_reads_once():
    inner, client, sources = _setup(blank=False)
    for r in inner.table("clientes").select("*").execute().data:
        r["email"] = "x@y.com"
    svc._refresh_contato_from_sources(client, ORG, sources)
    assert client.selects.get("clientes", 0) <= 2
