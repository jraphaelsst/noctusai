"""`GET /{id}/card` — the badge row. Ported from social-wiring's
`tests/modules/card_hub/test_card_resumo.py` (its `temperatura`/`touches`
badges and `atendimentos` key are product extensions — pinned here through
the extension seams instead)."""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from tests.domain.card_hub.conftest import AUTH, ORG_ID, build_hub


class TestCardResumo:
    def test_shape_and_empty_badges(self, hub):
        eid = hub.new_entity()
        resp = hub.client.get(hub.url(eid, "/card"), headers=AUTH)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        expected_keys = [hub.cfg.entity_kind, "tags", "membros", "descricao"]
        if hub.cfg.entity_datas:
            expected_keys.append("datas")
        expected_keys.append("badges")
        assert list(body) == expected_keys
        assert body[hub.cfg.entity_kind]["id"] == eid
        assert body["tags"] == []
        assert body["membros"] == []
        assert body["descricao"] is None
        assert body["badges"] == {
            "notas": 0, "documentos": 0, "checklist_total": 0, "checklist_concluidos": 0, "tem_descricao": False,
        }

    def test_datas_block_follows_the_entity_columns(self, lead_schema_cache):
        hub = build_hub("sw")
        eid = hub.new_entity(data_entrega="2026-09-30T12:00:00+00:00", entrega_concluida=True, recorrencia="mensal")
        datas = hub.client.get(hub.url(eid, "/card"), headers=AUTH).json()["datas"]
        assert datas == {
            "data_inicio": None,
            "data_entrega": "2026-09-30T12:00:00+00:00",
            "entrega_concluida": True,
            "lembrete_minutos_antes": None,
            "recorrencia": "mensal",
        }

    def test_badges_are_computed_correctly(self, hub):
        eid = hub.new_entity()
        t1, c1 = str(uuid4()), str(uuid4())
        fk = hub.cfg.entity_fk
        hub.seed(hub.cfg.tables.notas, [
            hub.nota_row(str(uuid4()), eid, tipo="descricao"),
            hub.nota_row(str(uuid4()), eid, tipo="comentario"),
            hub.nota_row(str(uuid4()), eid, tipo="comentario"),
        ])
        hub.seed(hub.cfg.tables.documentos, [hub.documento_row(str(uuid4()), eid)])
        hub.seed(hub.cfg.tables.tags, [hub.tag_row(t1)])
        hub.seed(hub.cfg.tables.tag_links, [
            {fk: eid, "tag_id": t1, "org_id": ORG_ID, "criado_por": None, "created_at": "2026-01-01T00:00:00+00:00"}
        ])
        hub.seed(hub.cfg.member_source.table, [hub.member_row(c1)])
        hub.seed(hub.cfg.tables.membros, [
            {fk: eid, hub.cfg.member_source.fk: c1, "org_id": ORG_ID, "created_at": "2026-01-01T00:00:00+00:00"}
        ])
        cl = hub.checklist_row(str(uuid4()), eid)
        hub.seed(hub.cfg.tables.checklists, [cl])
        hub.seed(hub.cfg.tables.checklist_itens, [
            hub.checklist_item_row(str(uuid4()), cl["id"], concluido=True, concluido_em="2026-01-02T00:00:00+00:00"),
            hub.checklist_item_row(str(uuid4()), cl["id"], concluido=False),
        ])

        body = hub.client.get(hub.url(eid, "/card"), headers=AUTH).json()
        # `notas` counts COMMENTS only — the description is `tem_descricao`.
        assert body["badges"]["notas"] == 2
        assert body["badges"]["tem_descricao"] is True
        assert body["descricao"]["corpo"]
        assert set(body["descricao"]) == {"id", "corpo", "editado_em"}
        assert body["badges"]["documentos"] == 1
        assert body["badges"]["checklist_total"] == 2
        assert body["badges"]["checklist_concluidos"] == 1
        assert len(body["tags"]) == 1
        assert len(body["membros"]) == 1

    def test_unknown_entity_404s(self, hub):
        assert hub.client.get(hub.url(str(uuid4()), "/card"), headers=AUTH).status_code == 404


def _sw_badges(cfg, db, org_id, entity_id, entity, current):
    """Social-wiring's shape: its own badges spliced into ITS key order."""
    return {
        "notas": current["notas"],
        "documentos": current["documentos"],
        "touches": 7,
        "checklist_total": current["checklist_total"],
        "checklist_concluidos": current["checklist_concluidos"],
        "tem_descricao": current["tem_descricao"],
        "temperatura": {"valor": 90, "rotulo": "quente", "provisoria": True},
    }


def _sw_resumo(cfg, db, org_id, entity_id, entity, current):
    return {**current, "atendimentos": []}


@pytest.fixture(params=["lead", "sw"])
def extended_hub(request, lead_schema_cache):
    return build_hub(
        request.param,
        cfg_transform=lambda cfg: replace(cfg, badge_extensions=(_sw_badges,), resumo_extensions=(_sw_resumo,)),
    )


class TestExtensions:
    def test_a_badge_extension_owns_keys_and_their_order(self, extended_hub):
        hub = extended_hub
        eid = hub.new_entity()
        body = hub.client.get(hub.url(eid, "/card"), headers=AUTH).json()
        assert list(body["badges"]) == [
            "notas", "documentos", "touches", "checklist_total", "checklist_concluidos", "tem_descricao", "temperatura",
        ]
        assert body["badges"]["touches"] == 7

    def test_a_resumo_extension_appends_after_the_seed_keys(self, extended_hub):
        hub = extended_hub
        eid = hub.new_entity()
        body = hub.client.get(hub.url(eid, "/card"), headers=AUTH).json()
        assert list(body)[-2:] == ["badges", "atendimentos"]
        if hub.name == "sw":
            # Exactly social-wiring's served order.
            assert list(body) == ["cliente", "tags", "membros", "descricao", "datas", "badges", "atendimentos"]
