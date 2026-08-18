"""The unified timeline — D9, contract §3.

`ocorrido_em` is the sort key and it is the event's OWN time, never
`created_at` of the recording row — a backfilled touch from March must
sort in March. This file's most important test
(`test_backfilled_touch_sorts_by_ocorreu_em_not_created_at`) asserts
exactly that with a touch whose `created_at` (today) and `ocorreu_em`
(March) diverge."""
from __future__ import annotations

from uuid import uuid4

from tests.modules.card_hub.conftest import cliente_row, nota_row, touch_row


def _auth() -> dict:
    return {"Authorization": "Bearer test-token"}


class TestTimelineOrdering:
    def test_backfilled_touch_sorts_by_ocorreu_em_not_created_at(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, created_at="2025-01-01T00:00:00+00:00")])
        # A touch backfilled TODAY for an event that happened in MARCH.
        old_touch = touch_row(
            str(uuid4()), cid, origem_id="lead-1", ocorreu_em="2026-03-01T10:00:00+00:00"
        )
        recent_touch = touch_row(
            str(uuid4()), cid, origem_id="lead-2", ocorreu_em="2026-08-01T10:00:00+00:00"
        )
        scoped.set_table_data("cliente_touches", [old_touch, recent_touch])

        resp = client.get(f"/api/clientes/{cid}/timeline?kinds=touch", headers=_auth())
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert len(items) == 2
        # Newest-first: the August touch (recent ocorrido_em) comes BEFORE
        # the March one, regardless of both being recorded "today".
        assert items[0]["id"] == recent_touch["id"]
        assert items[1]["id"] == old_touch["id"]
        assert items[0]["ocorrido_em"] == "2026-08-01T10:00:00+00:00"
        assert items[1]["ocorrido_em"] == "2026-03-01T10:00:00+00:00"

    def test_mixed_kinds_interleave_by_ocorrido_em(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "cliente_touches",
            [touch_row(str(uuid4()), cid, origem_id="l1", ocorreu_em="2026-02-01T00:00:00+00:00")],
        )
        scoped.set_table_data(
            "cliente_notas",
            [nota_row(str(uuid4()), cid, corpo="x", created_at="2026-06-01T00:00:00+00:00")],
        )

        resp = client.get(f"/api/clientes/{cid}/timeline", headers=_auth())
        assert resp.status_code == 200
        kinds_in_order = [e["kind"] for e in resp.json()["items"]]
        assert kinds_in_order.index("nota") < kinds_in_order.index("touch")

    def test_kinds_filter(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        scoped.set_table_data(
            "cliente_touches",
            [touch_row(str(uuid4()), cid, origem_id="l1", ocorreu_em="2026-02-01T00:00:00+00:00")],
        )
        scoped.set_table_data("cliente_notas", [nota_row(str(uuid4()), cid)])

        resp = client.get(f"/api/clientes/{cid}/timeline?kinds=nota", headers=_auth())
        assert resp.status_code == 200
        assert {e["kind"] for e in resp.json()["items"]} == {"nota"}

    def test_sistema_criado_event_present(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid, created_at="2026-01-01T00:00:00+00:00")])
        resp = client.get(f"/api/clientes/{cid}/timeline?kinds=sistema", headers=_auth())
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert any(i["evento"] == "criado" for i in items)

    def test_unknown_cliente_404s(self, client, scoped):
        resp = client.get(f"/api/clientes/{uuid4()}/timeline", headers=_auth())
        assert resp.status_code == 404


class TestTimelineCursorPagination:
    def test_cursor_pages_forward_without_gaps_or_dupes(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        touches = [
            touch_row(str(uuid4()), cid, origem_id=f"lead-{i}", ocorreu_em=f"2026-01-{i + 1:02d}T00:00:00+00:00")
            for i in range(10)
        ]
        scoped.set_table_data("cliente_touches", touches)

        seen_ids: list[str] = []
        cursor = None
        for _ in range(6):  # more than enough pages at limit=2
            url = f"/api/clientes/{cid}/timeline?kinds=touch&limit=2"
            if cursor:
                url += f"&cursor={cursor}"
            resp = client.get(url, headers=_auth())
            assert resp.status_code == 200, resp.text
            body = resp.json()
            seen_ids.extend(e["id"] for e in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break

        assert len(seen_ids) == len(set(seen_ids)) == 10

    def test_bad_cursor_400s(self, client, scoped):
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        resp = client.get(f"/api/clientes/{cid}/timeline?cursor=not-a-real-cursor!!", headers=_auth())
        assert resp.status_code == 400


class TestTimelinePostgrestCap:
    def test_more_than_1000_touches_are_not_silently_truncated(self, client, scoped):
        """The exact bug class named in the brief (`71bb2e4c`, `98377d26`,
        ...): a bare `.execute()` silently caps at 1 000 rows. 1 200
        touches for one cliente must ALL be reachable across pages —
        `total` must report the true count, not the capped one, proving
        the underlying gather composed the seed's pager rather than a
        bare `.execute()`."""
        cid = str(uuid4())
        scoped.set_table_data("clientes", [cliente_row(cid)])
        touches = [
            touch_row(
                str(uuid4()),
                cid,
                origem_id=f"lead-{i}",
                ocorreu_em=f"2026-01-01T00:{i % 60:02d}:{i % 60:02d}.{i:06d}+00:00",
            )
            for i in range(1200)
        ]
        scoped.set_table_data("cliente_touches", touches)

        # `limit` is capped at 200 per request (the endpoint's own
        # `le=200`) — page through with the max page size and count.
        seen_ids: set[str] = set()
        cursor = None
        reported_total = None
        for _ in range(10):  # 1200 / 200 = 6 pages; generous ceiling
            url = f"/api/clientes/{cid}/timeline?kinds=touch&limit=200"
            if cursor:
                url += f"&cursor={cursor}"
            resp = client.get(url, headers=_auth())
            assert resp.status_code == 200, resp.text
            body = resp.json()
            reported_total = body["total"]
            seen_ids.update(e["id"] for e in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break

        assert reported_total == 1200
        assert len(seen_ids) == 1200
