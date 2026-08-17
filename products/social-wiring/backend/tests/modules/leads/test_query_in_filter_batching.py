"""Regression tests for the ``.in_()`` URL-length overflow class in the
Leads filter set (``query.apply_db_filters`` / ``fetch_filtered`` /
``leads_service.list_leads``).

Same failure shape as the one that took ``/clientes/revisao`` down in prod
on 2026-08-14 (see ``clientes_service._IN_FILTER_BATCH``): PostgREST puts
``.in_(col, values)`` values in the URL QUERY STRING, so a long enough
list becomes an over-long request line and the server answers a bare 400.
Flagged as the highest-signal finding by ``check_postgrest_unbounded_query``
for ``leads/services/query.py``'s ``apply_db_filters``.

The wrinkle here (vs. the ``clientes`` fix): ``.in_()`` is a filter on a
LARGER query that also carries other filters, ordering and pagination
(``leads_service._list_leads_db``'s count+page fast path). Naively batching
the ``.in_()`` call and concatenating page-by-page would silently change
ordering and break pagination/count semantics — see ``query.py``'s
``.in_()`` batching note and ``leads_service.list_leads``'s docstring for
the chosen approach: batch + union inside ``fetch_filtered`` (which already
has no server-side ordering/pagination commitment), and route the DB-pushed
fast path away from any oversized filter set entirely rather than teach it
to batch too.

Three tiers of coverage:

1. Pure unit tests on the batching primitives (partitioning, cartesian
   product across simultaneously-oversized fields, the pass-through
   no-op case).
2. Correctness (union/AND semantics) against a bespoke double that
   honours ``.in_()`` as real set membership but has no URL-length limit
   — proves the ROW SET math is right independent of the mock's budget
   check.
3. The real failure + the real fix, against
   ``noctusai_lib.testing.MockSupabaseClient`` — which now models
   PostgREST's URL-length budget and raises a genuine
   ``postgrest.exceptions.APIError`` past it (see ``mocks.py``'s
   ``_IN_FILTER_URL_BUDGET_BYTES``) — plus ordering/pagination/count
   assertions on the fallback path an oversized filter now routes
   through.
"""
from __future__ import annotations

import inspect
import uuid
from datetime import date

import pytest
from postgrest.exceptions import APIError
from noctusai_lib.testing import MockSupabaseClient

from app.modules.leads.services import leads_service
from app.modules.leads.services.query import (
    LeadFilters,
    _field_batches,
    _iter_batched_filters,
    fetch_filtered,
    needs_in_filter_batching,
)

ORG = uuid.UUID("6dd73140-74a4-41c6-aeff-bc94b5312b53")
OTHER_ORG = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _uuids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


# ─── 1. pure unit tests on the batching primitives ────────────────────────


class TestNeedsInFilterBatching:
    def test_false_for_default_filters(self):
        assert needs_in_filter_batching(LeadFilters()) is False

    def test_false_at_exactly_the_batch_size(self):
        assert needs_in_filter_batching(LeadFilters(corretor_id=_uuids(200))) is False

    def test_true_one_over_the_batch_size(self):
        assert needs_in_filter_batching(LeadFilters(corretor_id=_uuids(201))) is True

    def test_true_when_a_different_field_is_oversized(self):
        assert needs_in_filter_batching(LeadFilters(empreendimento=[f"e{i}" for i in range(201)])) is True

    def test_false_for_non_in_pushed_fields_no_matter_how_large(self):
        """`ano`/`mes`/`q` are never DB-pushed — see the module docstring —
        so an oversized `ano` list can never trigger this failure class."""
        assert needs_in_filter_batching(LeadFilters(ano=list(range(2000, 2500)))) is False


class TestFieldBatches:
    def test_a_small_list_is_a_single_untouched_batch(self):
        ids = _uuids(5)
        assert _field_batches(LeadFilters(corretor_id=ids), "corretor_id") == [ids]

    def test_an_oversized_list_splits_at_the_configured_size(self):
        ids = _uuids(450)
        batches = _field_batches(LeadFilters(corretor_id=ids), "corretor_id")
        assert [len(b) for b in batches] == [200, 200, 50]

    def test_batching_loses_and_reorders_nothing(self):
        ids = _uuids(450)
        batches = _field_batches(LeadFilters(corretor_id=ids), "corretor_id")
        assert [x for b in batches for x in b] == ids


class TestIterBatchedFilters:
    def test_no_oversized_field_yields_exactly_one_equivalent_filters(self):
        filters = LeadFilters(tipo=["novo"], corretor_id=_uuids(3))
        cells = list(_iter_batched_filters(filters))
        assert len(cells) == 1
        assert cells[0] == filters

    def test_one_oversized_field_partitions_only_that_field(self):
        ids = _uuids(250)
        filters = LeadFilters(corretor_id=ids, tipo=["novo"])
        cells = list(_iter_batched_filters(filters))
        assert len(cells) == 2  # ceil(250 / 200)
        # every other filter is identical across cells
        assert all(c.tipo == ["novo"] for c in cells)
        # the corretor_id batches partition the original list exactly
        union = [v for c in cells for v in c.corretor_id]
        assert union == ids
        assert len(cells[0].corretor_id) == 200
        assert len(cells[1].corretor_id) == 50

    def test_two_simultaneously_oversized_fields_cartesian_product(self):
        """corretor_id AND empreendimento both oversized at once: every
        cell must carry a batch of EACH, so no cell's request line can
        still overflow on the field the naive 'batch just one' fix would
        have left untouched."""
        corretor_ids = _uuids(250)  # -> 2 batches (200, 50)
        empreendimentos = [f"Emp {i}" for i in range(300)]  # -> 2 batches (200, 100)
        filters = LeadFilters(corretor_id=corretor_ids, empreendimento=empreendimentos)
        cells = list(_iter_batched_filters(filters))
        assert len(cells) == 4  # 2 x 2
        for cell in cells:
            assert len(cell.corretor_id) <= 200
            assert len(cell.empreendimento) <= 200
        # every (corretor batch, empreendimento batch) combination appears
        corretor_sizes = sorted(len(c.corretor_id) for c in cells)
        assert corretor_sizes == [50, 50, 200, 200]


# ─── 2. correctness against an honest-but-URL-length-agnostic double ─────


class _SetMembershipBuilder:
    """Applies `eq`/`in_`/`gte`/`lte` as real predicates (unlike
    `noctusai_lib.testing`'s no-URL-limit-but-also-correct semantics) with
    NO url-length limit of its own — isolates "is the batched UNION+AND
    math right" from "does the mock model PostgREST's 400", which tier 3
    below covers separately."""

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self._start = 0
        self._end: int | None = None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self._rows = [r for r in self._rows if str(r.get(col)) == str(val)]
        return self

    def in_(self, col, vals):
        wanted = {str(v) for v in vals}
        self._rows = [r for r in self._rows if str(r.get(col)) in wanted]
        return self

    def gte(self, col, val):
        self._rows = [r for r in self._rows if str(r.get(col)) >= str(val)]
        return self

    def lte(self, col, val):
        self._rows = [r for r in self._rows if str(r.get(col)) <= str(val)]
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, start, end):
        self._start, self._end = start, end
        return self

    def execute(self):
        end = len(self._rows) - 1 if self._end is None else self._end
        window = self._rows[self._start : end + 1]
        return type("Resp", (), {"data": window})()


class _FakeClient:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def table(self, _name):
        return _SetMembershipBuilder(list(self._rows))


def _lead_row(*, corretor_id: str, tipo: str = "novo", org_id=ORG) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "org_id": str(org_id),
        "data_entrada": "2026-01-15",
        "corretor_id": corretor_id,
        "tipo_lead": tipo,
    }


class TestBatchedUnionCorrectness:
    def test_union_finds_matches_scattered_across_every_batch(self):
        """Only 3 of 260 candidate corretor_ids actually have a matching
        row; those 3 are deliberately spread so at least one lands in
        each batch (positions 0, 199, 259 -> batches 0 and 1)."""
        candidates = [str(uuid.uuid4()) for _ in range(260)]
        matching_positions = [0, 199, 259]
        rows = [_lead_row(corretor_id=candidates[i]) for i in matching_positions]
        client = _FakeClient(rows)

        result = fetch_filtered(client, ORG, LeadFilters(corretor_id=[uuid.UUID(c) for c in candidates]))

        assert {r["corretor_id"] for r in result} == {candidates[i] for i in matching_positions}

    def test_non_matching_ids_in_the_batch_contribute_nothing(self):
        real = str(uuid.uuid4())
        padding = [str(uuid.uuid4()) for _ in range(259)]
        rows = [_lead_row(corretor_id=real)]
        client = _FakeClient(rows)

        result = fetch_filtered(
            client, ORG, LeadFilters(corretor_id=[uuid.UUID(c) for c in [real] + padding])
        )
        assert len(result) == 1
        assert result[0]["corretor_id"] == real

    def test_other_filters_still_apply_and_across_every_batch(self):
        """`tipo` (in-budget) must still AND against the oversized
        `corretor_id` batches — a row matching the corretor id but not
        `tipo` must not appear."""
        candidates = [str(uuid.uuid4()) for _ in range(210)]
        rows = [
            _lead_row(corretor_id=candidates[0], tipo="novo"),
            _lead_row(corretor_id=candidates[0], tipo="retorno"),
            _lead_row(corretor_id=candidates[209], tipo="novo"),
        ]
        client = _FakeClient(rows)

        result = fetch_filtered(
            client,
            ORG,
            LeadFilters(corretor_id=[uuid.UUID(c) for c in candidates], tipo=["novo"]),
        )
        assert len(result) == 2
        assert all(r["tipo_lead"] == "novo" for r in result)

    def test_a_batched_result_carries_no_duplicates(self):
        """A row can only satisfy one batch (the batches partition the
        id list disjointly) — concatenation must never double-count."""
        candidates = [str(uuid.uuid4()) for _ in range(400)]
        rows = [_lead_row(corretor_id=c) for c in candidates]
        client = _FakeClient(rows)

        result = fetch_filtered(client, ORG, LeadFilters(corretor_id=[uuid.UUID(c) for c in candidates]))
        ids = [r["id"] for r in result]
        assert len(ids) == len(set(ids)) == 400


# ─── 3. the real failure + the real fix (MockSupabaseClient) ─────────────


def _scoped_mock() -> object:
    return MockSupabaseClient().schema("social_wiring")


def _create_leads_with_corretores(client, org_id, corretor_ids: list[str]) -> list[dict]:
    return [
        leads_service.create_lead(
            client,
            org_id,
            {
                "data_entrada": date(2026, 1, (i % 27) + 1).isoformat(),
                "corretor_id": cid,
                "cliente_nome": f"Cliente {i:04d}",
            },
        )
        for i, cid in enumerate(corretor_ids)
    ]


class TestRealMockRegressionAndFix:
    def test_guard_a_raw_oversized_in_call_really_does_raise(self):
        """Proves the double really does enforce PostgREST's URL budget —
        a regression back to an unbatched `.in_()` call fails THIS test's
        premise (or, downstream, the fix tests below) instead of passing
        by accident."""
        client = _scoped_mock()
        oversized = [str(uuid.uuid4()) for _ in range(250)]
        with pytest.raises(APIError):
            # postgrest-unbounded-ok: deliberately unbatched — this IS the
            # raw failure this test module exists to prove is real.
            client.table("leads").select("*").eq("org_id", str(ORG)).in_(
                "corretor_id", oversized
            ).execute()

    def test_fetch_filtered_does_not_raise_past_the_url_budget(self):
        client = _scoped_mock()
        real_ids = _uuids(5)
        padding_ids = _uuids(245)  # -> 250 total, well past the 200 batch size
        _create_leads_with_corretores(client, ORG, [str(v) for v in real_ids])

        result = fetch_filtered(
            client, ORG, LeadFilters(corretor_id=list(real_ids) + list(padding_ids))
        )
        assert {r["corretor_id"] for r in result} == {str(v) for v in real_ids}

    def test_list_leads_does_not_raise_and_routes_to_the_fallback(self):
        """`list_leads` must ITSELF avoid the DB-pushed fast path
        (`_list_leads_db`) for an oversized filter set — that path's count
        + page queries are not batched (see the module docstring) and
        would hit the same APIError if ever invoked with one."""
        client = _scoped_mock()
        real_ids = _uuids(5)
        padding_ids = _uuids(245)
        _create_leads_with_corretores(client, ORG, [str(v) for v in real_ids])

        rows, total = leads_service.list_leads(
            client, ORG, LeadFilters(corretor_id=list(real_ids) + list(padding_ids)),
            page=1, page_size=50,
        )
        assert total == 5
        assert len(rows) == 5
        assert {r["corretor_id"] for r in rows} == {str(v) for v in real_ids}

    def test_ordering_is_preserved_through_the_batched_fallback(self):
        client = _scoped_mock()
        real_ids = _uuids(4)
        padding_ids = _uuids(210)
        rows_created = [
            leads_service.create_lead(
                client, ORG,
                {"data_entrada": d, "corretor_id": str(cid)},
            )
            for cid, d in zip(
                real_ids,
                ["2026-01-01", "2026-03-15", "2026-02-10", "2026-04-20"],
            )
        ]
        rows, total = leads_service.list_leads(
            client, ORG, LeadFilters(corretor_id=list(real_ids) + list(padding_ids)),
            page=1, page_size=50, sort="data_entrada", order="desc",
        )
        assert total == 4
        dates = [r["data_entrada"] for r in rows]
        assert dates == sorted(dates, reverse=True)

    def test_pagination_slices_correctly_through_the_batched_fallback(self):
        client = _scoped_mock()
        real_ids = _uuids(5)
        padding_ids = _uuids(210)
        _create_leads_with_corretores(client, ORG, [str(v) for v in real_ids])
        filters = LeadFilters(corretor_id=list(real_ids) + list(padding_ids))

        page1, total1 = leads_service.list_leads(client, ORG, filters, page=1, page_size=2)
        page2, total2 = leads_service.list_leads(client, ORG, filters, page=2, page_size=2)
        page3, total3 = leads_service.list_leads(client, ORG, filters, page=3, page_size=2)

        assert total1 == total2 == total3 == 5
        assert len(page1) == len(page2) == 2
        assert len(page3) == 1
        seen_ids = {r["id"] for r in page1 + page2 + page3}
        assert len(seen_ids) == 5  # disjoint pages, complete coverage

    def test_org_scoping_still_applies_through_the_batched_fallback(self):
        client = _scoped_mock()
        real_ids = _uuids(3)
        other_ids = _uuids(3)
        padding_ids = _uuids(210)
        _create_leads_with_corretores(client, ORG, [str(v) for v in real_ids])
        _create_leads_with_corretores(client, OTHER_ORG, [str(v) for v in other_ids])

        rows, total = leads_service.list_leads(
            client, ORG, LeadFilters(corretor_id=list(real_ids) + list(other_ids) + list(padding_ids)),
            page=1, page_size=50,
        )
        assert total == 3
        assert {r["org_id"] for r in rows} == {str(ORG)}


# ─── structural guard ──────────────────────────────────────────────────


class TestStructuralGuard:
    def test_list_leads_routes_oversized_filters_away_from_the_db_fast_path(self):
        """A future edit that drops this condition silently reintroduces
        the `_list_leads_db` APIError for large filter lists."""
        src = inspect.getsource(leads_service.list_leads)
        assert "needs_in_filter_batching(filters)" in src

    def test_fetch_filtered_batches_before_paging(self):
        src = inspect.getsource(fetch_filtered)
        assert "needs_in_filter_batching(filters)" in src
        assert "_iter_batched_filters(filters)" in src
