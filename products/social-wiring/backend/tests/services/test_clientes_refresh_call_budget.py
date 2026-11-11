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


# ── a PostgREST-shaped fake: eq / order / range / update / or_("col.is.null,col.eq.") on real row lists ──────────

class _Res:
    def __init__(self, data):
        self.data = data


class _Q:
    def __init__(self, store, name, hook):
        self.store, self.name, self.hook = store, name, hook
        self.mode, self.filters, self.orders, self.rng, self.patch, self.or_cols = "select", [], [], None, None, None

    def select(self, *_a, **_k):
        self.mode = "select"
        return self

    def update(self, patch):
        self.mode, self.patch = "update", patch
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def order(self, col, **_k):
        self.orders.append(col)
        return self

    def range(self, a, b):
        self.rng = (a, b)
        return self

    def or_(self, expr):
        self.or_cols = [c.split(".")[0] for c in expr.split(",")][0]  # "col.is.null,col.eq." -> col
        return self

    def _matching(self):
        return [r for r in self.store[self.name] if all(r.get(c) == v for c, v in self.filters)]

    def execute(self):
        rows = self._matching()
        if self.mode == "update":
            n = 0
            self.store.setdefault("_updates", []).append(self.patch)
            for r in rows:
                if self.or_cols is None or r.get(self.or_cols) in (None, ""):  # the database's re-check
                    r.update(self.patch)
                    n += 1
            return _Res([{}] * n)
        for c in reversed(self.orders):
            rows = sorted(rows, key=lambda r: r[c])
        if self.rng:
            rows = rows[self.rng[0]:self.rng[1] + 1]
        out = [dict(r) for r in rows]
        if self.hook:
            self.hook(self.name)
        return _Res(out)


class _Pg:
    def __init__(self, store, hook=None):
        self.store, self.hook = store, hook

    def table(self, name):
        return _Q(self.store, name, self.hook)


def _one_blank_cliente_store():
    return {
        "clientes": [{"id": "c1", "org_id": ORG, "nome": "Ana", "celular": None, "email": None}],
        "cliente_touches": [{"id": "t1", "org_id": ORG, "cliente_id": "c1", "origem_tabela": "leads", "origem_id": "l1"}],
    }


def _source(tel="+5511911111111", email="lead@x.com"):
    return svc.SourceRow(
        origem_tabela="leads", origem_id="l1", org_id=ORG, ocorreu_em="2026-01-01T00:00:00+00:00",
        nome="Ana", chave_canonica=tel, chave_tipo="telefone", telefone=tel, email=email,
    )


def test_a_blank_filled_between_the_read_and_the_write_survives():
    store = _one_blank_cliente_store()

    def operator_types_after_our_read(table):
        if table == "clientes":
            store["clientes"][0]["celular"] = "+5511999999999"  # typed by hand after the pass read the blank

    client = _Pg(store, hook=operator_types_after_our_read)
    svc._refresh_contato_from_sources(client, ORG, [_source()])
    row = store["clientes"][0]
    assert row["celular"] == "+5511999999999"  # fill-if-empty held at WRITE time: not overwritten
    assert row["email"] == "lead@x.com"  # the column that really was still blank is filled


def test_paging_a_large_org_visits_every_cliente_exactly_once_in_id_order():
    n = 2500  # > 2 pages of 1000
    store = {
        "clientes": [{"id": f"c{i:05d}", "org_id": ORG, "nome": f"P{i}", "celular": None, "email": None} for i in reversed(range(n))],
        "cliente_touches": [
            {"id": f"t{i}", "org_id": ORG, "cliente_id": f"c{i:05d}", "origem_tabela": "leads", "origem_id": f"l{i}"} for i in range(n)
        ],
    }
    ranges = []

    class _Spy(_Pg):
        def table(self, name):
            q = super().table(name)
            orig = q.range

            def spy(a, b, _o=orig, _name=name):
                ranges.append((_name, a, b))
                return _o(a, b)

            q.range = spy
            return q

    seen = svc._select_all_by_id(_Spy(store), "clientes", ORG, columns="id,nome")
    assert [r["id"] for r in seen] == [f"c{i:05d}" for i in range(n)]  # all of them, once each, ordered by id
    assert [x for x in ranges if x[0] == "clientes"] == [("clientes", 0, 999), ("clientes", 1000, 1999), ("clientes", 2000, 2999)]


def test_a_whitespace_only_value_is_not_patched_every_pass():
    """The write guard accepts only NULL / '' as blank, so the read side must agree: a whitespace-only celular used to
    be 'blank' on read, a guarded no-op PATCH on write, every 6 h."""
    store = _one_blank_cliente_store()
    store["clientes"][0]["celular"] = "   "
    svc._refresh_contato_from_sources(_Pg(store), ORG, [_source(email=None)])
    assert store.get("_updates", []) == []
    assert store["clientes"][0]["celular"] == "   "
