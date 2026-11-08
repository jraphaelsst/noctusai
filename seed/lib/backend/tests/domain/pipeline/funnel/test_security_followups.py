"""Funnel security follow-ups: F1 `board_fields` minimisation, F2 stage-editor
router tier, F6 generated touch trigger. Defaults must stay unchanged."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.pipeline import PipelineConfig, pipeline_migration

from .conftest import HEADERS, READ_ONLY, build_funnel, make_cfg

SID = "7a7a7a7a-1111-4222-8333-444444444444"
STAGE_ROUTES = [
    ("GET", "/etapas", None),
    ("GET", "/etapas/opcoes", None),
    ("POST", "/etapas", {"label": "Nova"}),
    ("PATCH", f"/etapas/{SID}", {"label": "Y"}),
    ("DELETE", f"/etapas/{SID}", None),
    ("POST", "/etapas/reordenar", {"ids": [SID]}),
]
STAGE_WRITES = [r for r in STAGE_ROUTES if r[0] != "GET"]


class TestBoardFields:
    def _funnel(self, funnel_schema_cache, **cfg_kw):
        f = build_funnel("org", cfg=make_cfg("org", editable_fields={"telefone": "telefone", "extra": "titulo"}, **cfg_kw))
        f.add_stage("entrada", posicao=0)
        return f

    def test_default_none_ships_every_campo(self, funnel_schema_cache):
        f = self._funnel(funnel_schema_cache)
        assert f.cfg.board_fields is None
        f.add_card(etapa="entrada", telefone="119")
        card = f.client.get(f.url("/board"), headers=HEADERS).json()["data"][0]["cards"][0]
        assert set(card["campos"]) == {"telefone", "extra"}

    def test_board_and_orphans_omit_unlisted_keys_detail_keeps_them(self, funnel_schema_cache):
        f = self._funnel(funnel_schema_cache, board_fields=("extra",))
        placed = f.add_card(etapa="entrada", telefone="119")
        orphan = f.add_card(etapa=None, telefone="118")
        board = f.client.get(f.url("/board"), headers=HEADERS).json()["data"]
        assert [set(c["campos"]) for col in board for c in col["cards"]] == [{"extra"}]
        orphans = f.client.get(f.url("/board/orfaos"), headers=HEADERS).json()["data"]
        assert [set(c["campos"]) for c in orphans] == [{"extra"}]
        for cid, phone in ((placed, "119"), (orphan, "118")):
            detail = f.client.get(f.url(f"/cards/{cid}"), headers=HEADERS).json()["data"]
            assert detail["campos"]["telefone"] == phone and "extra" in detail["campos"]

    def test_search_still_matches_an_unlisted_field(self, funnel_schema_cache):
        f = self._funnel(funnel_schema_cache, board_fields=())
        f.add_card(etapa="entrada", telefone="5511999")
        body = f.client.get(f.url("/board?busca=5511999"), headers=HEADERS).json()["data"]
        cards = [c for col in body for c in col["cards"]]
        assert len(cards) == 1 and cards[0]["campos"] == {}

    def test_bad_type_refused(self):
        with pytest.raises(ValueError):
            make_cfg("org", board_fields="telefone")


class TestStageRouterTier:
    @pytest.mark.parametrize("method,path,body", STAGE_ROUTES)
    def test_unauthenticated_is_401(self, fn, method, path, body):
        assert fn.client.request(method, fn.url(path), json=body).status_code == 401

    @pytest.mark.parametrize("method,path,body", STAGE_WRITES)
    def test_non_admin_write_is_403(self, fn, method, path, body):
        assert fn.client.request(method, fn.url(path), json=body, headers=READ_ONLY).status_code == 403

    @pytest.mark.parametrize("path", ["/etapas", "/etapas/opcoes"])
    def test_reads_stay_open_to_members(self, fn, path):
        assert fn.client.get(fn.url(path), headers=READ_ONLY).status_code == 200

    def test_platform_mount_keeps_etapas_out_of_openapi(self, funnel_schema_cache):
        f = build_funnel("platform")
        paths = f.app.openapi()["paths"]
        assert not [p for p in paths if "/etapas" in p]
        assert f.client.get(f.url("/etapas"), headers=HEADERS).status_code == 200

    def test_org_mount_still_documents_etapas(self, funnel_schema_cache):
        f = build_funnel("org")
        assert [p for p in f.app.openapi()["paths"] if "/etapas" in p]


class TestTouchTrigger:
    PIPE = PipelineConfig(pipeline="crm", card_table="leads", value_field="valor",
                          entity_label="lead", entity_kind="lead", cliente_field=None)

    @pytest.mark.parametrize("schema", ["public", "crm"])
    def test_function_is_invoker_with_locked_search_path(self, schema):
        sql = pipeline_migration(self.PIPE, schema)
        fn = sql[sql.index("CREATE OR REPLACE FUNCTION"):]
        fn = fn[: fn.index("$$;") + 3]
        # postgrest-qualified-ok: DDL text, not a PostgREST table name
        assert f"{schema}.pipeline_set_updated_at()" in fn
        assert "SECURITY INVOKER" in fn and "DEFINER" not in fn
        assert "SET search_path = ''" in fn
        assert "pg_catalog.now()" in fn
        assert "public, public" not in sql
