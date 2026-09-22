"""The unified timeline — ported from social-wiring's
`tests/modules/card_hub/test_timeline.py`.

Social-wiring's own kinds (`touch`, `movimento`, `visita`, `sistema`) stay in
social-wiring; the ordering + paging properties they pinned are re-pinned here
on the seed kinds and on a product kind registered through the gatherer
registry (the seam social-wiring's kinds will plug into)."""
from __future__ import annotations

import base64
from dataclasses import replace
from uuid import uuid4

import pytest

from noctusai_lib.domain.card_hub import SEED_GATHERERS, decode_cursor, encode_cursor
from noctusai_lib.primitives.exceptions import ValidationError_
from tests.domain.card_hub.conftest import AUTH, ORG_ID, build_hub


def _backfilled_gatherer(cfg, db, org_id, entity_id, entity):
    """A product kind whose event time (`ocorreu_em`) differs from the time
    its row was RECORDED — the backfill shape."""
    return [
        {
            "id": f"bf-{i}",
            "kind": "backfill",
            "ocorrido_em": ocorreu,
            "ator": None,
            "payload": {"origem": "import", "n": i},
        }
        for i, ocorreu in enumerate(entity.get("_eventos", []))
    ]


@pytest.fixture(params=["lead", "sw"])
def product_hub(request, lead_schema_cache):
    """A hub with one extra, product-registered kind."""
    return build_hub(
        request.param,
        cfg_transform=lambda cfg: replace(
            cfg, timeline_gatherers={**SEED_GATHERERS, "backfill": _backfilled_gatherer}
        ),
    )


class TestTimelineOrdering:
    def test_seed_kinds_interleave_by_ocorrido_em(self, hub):
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.notas, [hub.nota_row(str(uuid4()), eid, created_at="2026-06-01T00:00:00+00:00")])
        hub.seed(hub.cfg.tables.documentos, [hub.documento_row(str(uuid4()), eid, created_at="2026-02-01T00:00:00+00:00")])
        cl = hub.checklist_row(str(uuid4()), eid)
        hub.seed(hub.cfg.tables.checklists, [cl])
        hub.seed(hub.cfg.tables.checklist_itens, [
            hub.checklist_item_row(str(uuid4()), cl["id"], concluido=True, concluido_em="2026-04-01T00:00:00+00:00"),
            hub.checklist_item_row(str(uuid4()), cl["id"], concluido=False),
        ])

        resp = hub.client.get(hub.url(eid, "/timeline"), headers=AUTH)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [e["kind"] for e in body["items"]] == ["nota", "checklist", "documento"]
        assert body["total"] == 3
        assert body["next_cursor"] is None

    def test_items_flatten_the_payload(self, hub):
        eid = hub.new_entity()
        nid = str(uuid4())
        hub.seed(hub.cfg.tables.notas, [hub.nota_row(nid, eid, corpo="olá")])
        item = hub.client.get(hub.url(eid, "/timeline"), headers=AUTH).json()["items"][0]
        assert item == {
            "id": nid, "kind": "nota", "ocorrido_em": "2026-01-05T00:00:00+00:00", "ator": None,
            "corpo": "olá", "autor": None, "editado_em": None, "deleted_at": None,
        }

    def test_backfilled_product_kind_sorts_by_event_time(self, product_hub):
        hub = product_hub
        eid = hub.new_entity(_eventos=["2026-03-01T10:00:00+00:00", "2026-08-01T10:00:00+00:00"])
        resp = hub.client.get(hub.url(eid, "/timeline?kinds=backfill"), headers=AUTH)
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert [i["ocorrido_em"] for i in items] == ["2026-08-01T10:00:00+00:00", "2026-03-01T10:00:00+00:00"]
        assert items[0]["origem"] == "import"

    def test_kinds_filter(self, hub):
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.notas, [hub.nota_row(str(uuid4()), eid)])
        hub.seed(hub.cfg.tables.documentos, [hub.documento_row(str(uuid4()), eid)])
        resp = hub.client.get(hub.url(eid, "/timeline?kinds=nota"), headers=AUTH)
        assert resp.status_code == 200
        assert {e["kind"] for e in resp.json()["items"]} == {"nota"}

    def test_a_filter_of_only_unknown_kinds_is_an_empty_page(self, hub):
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.notas, [hub.nota_row(str(uuid4()), eid)])
        resp = hub.client.get(hub.url(eid, "/timeline?kinds=touch"), headers=AUTH)
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "total": 0, "next_cursor": None}

    def test_deleted_documents_are_not_events(self, hub):
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.documentos, [hub.documento_row(str(uuid4()), eid, deleted_at="2026-01-02T00:00:00+00:00")])
        assert hub.client.get(hub.url(eid, "/timeline"), headers=AUTH).json()["items"] == []

    def test_unknown_entity_404s(self, hub):
        resp = hub.client.get(hub.url(str(uuid4()), "/timeline"), headers=AUTH)
        assert resp.status_code == 404

    def test_limit_is_bounded_1_to_200(self, hub):
        eid = hub.new_entity()
        assert hub.client.get(hub.url(eid, "/timeline?limit=0"), headers=AUTH).status_code == 422
        assert hub.client.get(hub.url(eid, "/timeline?limit=201"), headers=AUTH).status_code == 422


class TestTimelineCursorPagination:
    def test_cursor_pages_forward_without_gaps_or_dupes(self, hub):
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.notas, [
            hub.nota_row(str(uuid4()), eid, created_at=f"2026-01-{i + 1:02d}T00:00:00+00:00") for i in range(10)
        ])
        seen: list[str] = []
        cursor = None
        for _ in range(6):
            url = hub.url(eid, "/timeline?kinds=nota&limit=2")
            if cursor:
                url += f"&cursor={cursor}"
            resp = hub.client.get(url, headers=AUTH)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["total"] == 10  # the whole thread, not what is left
            seen.extend(e["id"] for e in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break
        assert len(seen) == len(set(seen)) == 10

    def test_bad_cursor_400s(self, hub):
        eid = hub.new_entity()
        resp = hub.client.get(hub.url(eid, "/timeline?cursor=not-a-real-cursor!!"), headers=AUTH)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


class TestCursorCodec:
    def test_encoding_is_urlsafe_base64_of_time_pipe_id(self):
        """🔴 Clients hold these across releases — the encoding is contract."""
        cursor = encode_cursor("2026-01-01T00:00:00+00:00", "abc")
        assert cursor == base64.urlsafe_b64encode(b"2026-01-01T00:00:00+00:00|abc").decode("ascii")
        assert decode_cursor(cursor) == ("2026-01-01T00:00:00+00:00", "abc")

    def test_an_id_containing_a_pipe_survives(self):
        assert decode_cursor(encode_cursor("t", "a|b")) == ("t", "a|b")

    def test_garbage_is_a_typed_validation_error(self):
        with pytest.raises(ValidationError_):
            decode_cursor("!!!")


class TestTimelinePostgrestCap:
    def test_more_than_1000_events_are_not_silently_truncated(self, hub):
        """A bare `.execute()` caps at 1 000 rows. 1 200 comments must ALL be
        reachable across pages and `total` must be the true count."""
        eid = hub.new_entity()
        hub.seed(hub.cfg.tables.notas, [
            hub.nota_row(str(uuid4()), eid, created_at=f"2026-01-01T00:{i % 60:02d}:{i % 60:02d}.{i:06d}+00:00")
            for i in range(1200)
        ])
        seen: set[str] = set()
        cursor = None
        total = None
        for _ in range(10):
            url = hub.url(eid, "/timeline?kinds=nota&limit=200")
            if cursor:
                url += f"&cursor={cursor}"
            body = hub.client.get(url, headers=AUTH).json()
            total = body["total"]
            seen.update(e["id"] for e in body["items"])
            cursor = body["next_cursor"]
            if cursor is None:
                break
        assert total == 1200
        assert len(seen) == 1200


def test_org_id_is_the_harness_org(hub):
    """Guard: every row builder seeds the org the auth dependency resolves."""
    assert hub.entity_row()["org_id"] == ORG_ID
