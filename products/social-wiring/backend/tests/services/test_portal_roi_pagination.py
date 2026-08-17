"""PostgREST row-cap regression for portal_roi_service.

🔴 Found LIVE on 2026-08-14 by loading /portal-roi in a browser after the
deploy: the KPI read **1.000 leads** against a true 13 255. `_count_leads_by_origem`
fetched every `leads` row with a bare `.execute()`, which PostgREST silently
caps at 1 000 — so the platform total, every per-portal lead count, and every
CPL derived from one were wrong, with no error raised anywhere.

`_aggregate_vendas_by_origem` had the identical shape and was harmless only
because `lead_vendas` is still empty — a latent instance of the same bug.

The shared `MockSupabaseClient` cannot catch this class: its `.range()` is a
no-op and it enforces no ceiling, so a capped query and a paginated one are
indistinguishable under it. These tests therefore use a local double that
models the real ceiling — an unpaginated select truncates, a `.range()`d one
pages through.
"""
from __future__ import annotations

from uuid import uuid4

from app.services import portal_roi_service as svc

CAP = svc._PAGE  # the real PostgREST ceiling — no patching of production internals


class _CappedQuery:
    """Models PostgREST: a bare execute() truncates at CAP; range() pages."""

    def __init__(self, rows: list[dict], cap: int = CAP):
        self._rows = rows
        self._cap = cap
        self._lo: int | None = None
        self._hi: int | None = None

    def range(self, lo: int, hi: int):
        self._lo, self._hi = lo, hi
        return self

    def execute(self):
        if self._lo is None:
            window = self._rows[: self._cap]   # the silent cap
        else:
            window = self._rows[self._lo : self._hi + 1][: self._cap]
        return type("Resp", (), {"data": window})()


def test_paginate_drains_past_the_row_cap():
    rows = [{"origem_id": f"o{i}"} for i in range(10)]
    assert len(_CappedQuery(rows[:], cap=3).execute().data) == 3, "double must cap"
    drained = svc._paginate(_CappedQuery(rows[:], cap=3), page_size=3)
    assert len(drained) == len(rows), (
        f"drained {len(drained)} of {len(rows)} — an unpaginated select was "
        "capped and reported success anyway"
    )


def test_paginate_counts_every_lead_not_just_the_first_page():
    """The live shape: many leads across a few origens. A capped read
    under-counts the busiest portal, which is exactly what shipped."""
    busy, quiet = str(uuid4()), str(uuid4())
    rows = [{"origem_id": busy} for _ in range(8)] + [{"origem_id": quiet} for _ in range(2)]
    drained = svc._paginate(_CappedQuery(rows[:], cap=3), page_size=3)
    counts: dict[str, int] = {}
    for r in drained:
        counts[r["origem_id"]] = counts.get(r["origem_id"], 0) + 1
    assert counts == {busy: 8, quiet: 2}, f"under-counted: {counts}"


# ── The real pin: does _count_leads_by_origem actually USE the paginator? ──
# The two tests above prove `_paginate` works. They would still pass if the
# caller never called it — which was precisely the shipped bug. This one
# drives the real method through a capping client and FAILS against the
# pre-fix `list(query.execute().data or [])`.

class _CappedTable:
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return _CappedQuery(self._rows)


class _Chainable(_CappedQuery):
    """_CappedQuery plus the filter methods the service chains on."""
    def eq(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def lte(self, *a, **k): return self
    @property
    def not_(self): return self
    def is_(self, *a, **k): return self


class _CappedClient:
    def __init__(self, rows): self._rows = rows
    def table(self, name):
        rows = self._rows if name == "leads" else []
        t = _CappedTable(rows)
        t.select = lambda *a, **k: _Chainable(rows)  # type: ignore[method-assign]
        return t


def test_count_leads_by_origem_sees_every_lead():
    """🔴 Exceeds the REAL 1 000-row ceiling rather than shrinking it by
    patching `svc._PAGE`. An earlier draft monkeypatched that constant and was
    correctly rejected by the compliance keeper — CLAUDE.md §1, "no
    monkey-patching (incl. tests)": a test that reaches into production
    internals stops exercising the thing it claims to guard."""
    busy, quiet = str(uuid4()), str(uuid4())
    rows = [{"origem_id": busy} for _ in range(CAP + 50)] + [{"origem_id": quiet} for _ in range(2)]
    service = svc.PortalRoiService(_CappedClient(rows))
    counts = service._count_leads_by_origem(uuid4(), None, None)
    assert counts == {busy: CAP + 50, quiet: 2}, (
        f"got {counts} — expected {CAP + 50}/2. A capped read under-counts the "
        "busiest portal, which is what shipped on 2026-08-14 (1 000 vs 13 255)."
    )
