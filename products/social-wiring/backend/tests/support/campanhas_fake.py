"""In-memory PostgREST stand-in for the campanhas CRUD tests.

`MockSupabaseClient` answers canned responses; CRUD needs state (a soft-deleted
campanha must stop resolving, a freed Meta id must be reusable). Emulates only
the builder surface the service uses, plus mig 218's unique index
`campanha_veiculacoes_meta_ref_unico` so the 409 path is exercised.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4


class _Query:
    def __init__(self, store, table):
        self._s, self._t = store, table
        self._f: list = []
        self._op, self._payload = "select", None
        self._order: list[str] = []
        self._rng = None
        self._lim = None

    def select(self, *_a, **_k):
        return self

    def eq(self, c, v):
        self._f.append(lambda r: str(r.get(c)) == str(v))
        return self

    def in_(self, c, vs):
        vs = {str(v) for v in vs}
        self._f.append(lambda r: str(r.get(c)) in vs)
        return self

    def is_(self, c, v):
        self._f.append((lambda r: r.get(c) is None) if v == "null" else (lambda r: r.get(c) is not None))
        return self

    def order(self, c, **_k):
        self._order.append(c)
        return self

    def range(self, a, b):
        self._rng = (a, b)
        return self

    def limit(self, n):
        self._lim = n
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def _match(self):
        return [r for r in self._s.tables.setdefault(self._t, []) if all(f(r) for f in self._f)]

    def execute(self):
        rows = self._s.tables.setdefault(self._t, [])
        if self._op == "insert":
            new = [dict(p) for p in (self._payload if isinstance(self._payload, list) else [self._payload])]
            for r in new:
                r.setdefault("id", str(uuid4()))
                if self._t == "campanhas":
                    r.setdefault("created_at", f"2026-10-09T10:00:{len(rows):02d}+00:00")
                    r.setdefault("deleted_at", None)
                if self._t == "campanha_veiculacoes" and r.get("canal") == "meta_ads":
                    if any(
                        x["org_id"] == r["org_id"] and x["nivel"] == r["nivel"]
                        and x["ref_codigo"] == r["ref_codigo"] and x["canal"] == "meta_ads"
                        for x in rows
                    ):
                        raise RuntimeError(
                            'duplicate key value violates unique constraint '
                            '"campanha_veiculacoes_meta_ref_unico"'
                        )
                rows.append(r)
            return SimpleNamespace(data=new)
        hit = self._match()
        if self._op == "update":
            for r in hit:
                r.update(self._payload)
            return SimpleNamespace(data=hit)
        if self._op == "delete":
            self._s.tables[self._t] = [r for r in rows if r not in hit]
            return SimpleNamespace(data=hit)
        for c in reversed(self._order):
            hit = sorted(hit, key=lambda r, c=c: str(r.get(c)))
        if self._rng:
            hit = hit[self._rng[0]: self._rng[1] + 1]
        if self._lim is not None:
            hit = hit[: self._lim]
        return SimpleNamespace(data=[dict(r) for r in hit])


class FakeCampanhasClient:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}

    def schema(self, _name):
        return self

    def table(self, name):
        return _Query(self, name)

    def add_imovel(self, org_id, codigo, titulo=None):
        rid = str(uuid4())
        self.tables.setdefault("imovel_registry", []).append({
            "id": rid, "org_id": str(org_id), "codigo_canonical": codigo.upper(),
            "codigo_display": codigo.upper(), "snap_titulo": titulo,
        })
        return rid
