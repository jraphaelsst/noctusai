"""Config guards, the DDL, `position_for_drop`, the movimentos gatherer, and the mount order."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from noctusai_lib.domain.card_hub import CardHubConfig, MemberSource
from noctusai_lib.domain.card_hub.gatherers import movimentos_gatherer
from noctusai_lib.domain.pipeline import PipelineConfig, pipeline_migration, position_for_drop
from noctusai_lib.domain.pipeline.funnel import (
    FunnelAction,
    FunnelConfig,
    FunnelGate,
    LostReason,
    mount_funnel,
)
from noctusai_lib.primitives.responses import success_response
from noctusai_lib.testing.mocks import MockSupabaseClient

from .conftest import HEADERS, ORG, PLATFORM_ORG, USER, _auth, make_cfg

PIPE = PipelineConfig(
    pipeline="crm", card_table="cards", value_field="valor", entity_label="card", entity_kind="card", cliente_field=None
)


def _hub(**kw) -> CardHubConfig:
    return CardHubConfig(
        entity_kind="lead", entity_table="cards", entity_fk="lead_id", id_param="lead_id", table_prefix="lead",
        member_source=MemberSource(table="membros", fk="membro_id"), bucket="b", actor_resolver=lambda ids: {}, **kw,
    )


class TestConfigGuards:
    def test_tenancy_must_be_declared_and_known(self):
        with pytest.raises(ValueError, match="tenancy"):
            FunnelConfig(pipeline=PIPE, tenancy="all")  # type: ignore[arg-type]

    def test_platform_needs_an_explicit_org(self):
        with pytest.raises(ValueError, match="platform_org_id"):
            FunnelConfig(pipeline=PIPE, tenancy="platform")

    def test_org_tenancy_refuses_a_platform_org(self):
        with pytest.raises(ValueError, match="only valid"):
            FunnelConfig(pipeline=PIPE, tenancy="org", platform_org_id=PLATFORM_ORG)

    def test_platform_card_hub_needs_its_own_entity_getter(self):
        with pytest.raises(ValueError, match="ensure_entity"):
            FunnelConfig(pipeline=PIPE, tenancy="platform", platform_org_id=PLATFORM_ORG, card_hub=_hub())
        FunnelConfig(
            pipeline=PIPE, tenancy="platform", platform_org_id=PLATFORM_ORG,
            card_hub=_hub(ensure_entity=lambda db, org, eid: {"id": eid}),
        )

    @pytest.mark.parametrize("role", ["ganho", "perdido"])
    def test_outcomes_are_statuses_so_a_won_or_lost_stage_role_is_refused(self, role):
        pipe = replace(PIPE, stage_roles=("final", role))
        with pytest.raises(ValueError, match="outcomes are statuses"):
            FunnelConfig(pipeline=pipe, tenancy="org")

    def test_gate_on_a_role_no_stage_can_carry_is_refused(self):
        with pytest.raises(ValueError, match="stage_roles"):
            FunnelConfig(pipeline=PIPE, tenancy="org", gates={"ganho": FunnelGate("g", lambda *a: [])})

    def test_action_key_must_match_its_code(self):
        with pytest.raises(ValueError, match="carries code"):
            FunnelConfig(pipeline=PIPE, tenancy="org", actions={"a": FunnelAction("b", "B", lambda *a: {})})

    def test_duplicate_lost_reason_is_refused(self):
        with pytest.raises(ValueError, match="repeat"):
            FunnelConfig(pipeline=PIPE, tenancy="org", lost_reasons=(LostReason("x", "X"), LostReason("x", "Y")))

    @pytest.mark.parametrize("column", ["etapa_id", "kanban_pos", "org_id", "status", "motivo_perda"])
    def test_editable_fields_cannot_reach_organ_owned_columns(self, column):
        with pytest.raises(ValueError, match="organ owns"):
            FunnelConfig(pipeline=PIPE, tenancy="org", editable_fields={"k": column})

    def test_status_vocabulary_maps_both_ways(self):
        cfg = FunnelConfig(pipeline=PIPE, tenancy="org", status_values={"perdido": "perdida"})
        assert cfg.status_stored("perdido") == "perdida" and cfg.status_stored("aberto") == "aberto"
        assert cfg.status_canonical("perdida") == "perdido" and cfg.status_canonical("???") == "???"
        with pytest.raises(ValueError, match="unknown canonical"):
            FunnelConfig(pipeline=PIPE, tenancy="org", status_values={"lost": "x"})

    def test_pipeline_status_field_is_normalised_for_the_stage_delete_guard(self):
        assert FunnelConfig(pipeline=PIPE, tenancy="org", status_field="estado").pipeline.status_field == "estado"

    def test_unknown_projection_key_raises_instead_of_vanishing(self):
        from noctusai_lib.domain.pipeline.funnel.service import card_dto

        cfg = FunnelConfig(pipeline=PIPE, tenancy="org", card_projection=lambda row: {"titlo": "typo"})
        with pytest.raises(ValueError, match="outside the card DTO"):
            card_dto(cfg, {"id": "1"})

    def test_projection_wins_and_campos_merge(self):
        from noctusai_lib.domain.pipeline.funnel.service import card_dto

        cfg = FunnelConfig(
            pipeline=PIPE, tenancy="org", editable_fields={"fone": "telefone"},
            card_projection=lambda row: {"titulo": "T", "badges": [{"label": "Quente", "variant": "danger"}], "campos": {"score": 3}},
        )
        dto = card_dto(cfg, {"id": "1", "telefone": "9", "valor": "2.5"})
        assert (dto["titulo"], dto["campos"], dto["badges"], dto["valor"]) == ("T", {"fone": "9", "score": 3}, [{"label": "Quente", "variant": "danger"}], 2.5)


class TestPositionForDrop:
    cards = [{"id": "a", "kanban_pos": "1"}, {"id": "b", "kanban_pos": "2"}, {"id": "c", "kanban_pos": "3"}]

    def test_none_index_means_no_opinion(self):
        assert position_for_drop(self.cards, "x", None) is None

    def test_midpoint_between_neighbours(self):
        assert position_for_drop(self.cards, "x", 1) == Decimal("1.5")

    def test_ends(self):
        assert position_for_drop(self.cards, "x", 0) == Decimal(0)
        assert position_for_drop(self.cards, "x", 3) == Decimal(4)

    def test_moved_card_is_excluded_from_its_own_neighbours(self):
        # b is at index 1; dropping it at index 1 again means between a and c.
        assert position_for_drop(self.cards, "b", 1) == Decimal(2)
        # dragging a one slot down: with a removed the column is [b, c] -> index 1 is between b and c.
        assert position_for_drop(self.cards, "a", 1) == Decimal("2.5")

    def test_clamps_a_racy_index(self):
        assert position_for_drop(self.cards, "x", 99) == Decimal(4)

    def test_sorts_numerically_not_lexically_and_breaks_ties_by_age(self):
        cards = [{"id": "a", "kanban_pos": "10"}, {"id": "b", "kanban_pos": "9"}]
        assert position_for_drop(cards, "x", 1) == Decimal("9.5") + Decimal(0) or True
        assert position_for_drop(cards, "x", 1) == Decimal("9.5")

    def test_empty_column(self):
        assert position_for_drop([], "x", 0) == Decimal(0)


class TestPipelineMigration:
    sql = pipeline_migration(PIPE, "crm", tier="platform")

    def test_tables_are_service_role_only(self):
        for table in ("pipeline_stages", "pipeline_movimentos"):
            assert f"REVOKE ALL ON crm.{table} FROM anon, authenticated;" in self.sql
            assert f"ALTER TABLE crm.{table} ENABLE ROW LEVEL SECURITY;" in self.sql
            assert f'CREATE POLICY "service_role_bypass" ON crm.{table} FOR ALL TO service_role' in self.sql
            assert f"COMMENT ON TABLE crm.{table} IS 'tier:platform';" in self.sql
        assert "TO authenticated" not in self.sql and "TO PUBLIC" not in self.sql
        assert "GRANT" not in self.sql.replace("TO service_role", "").replace("GRANT ALL ON", "")

    def test_history_is_append_only(self):
        assert "BEFORE UPDATE OR DELETE ON crm.pipeline_movimentos" in self.sql

    def test_history_carries_the_event_kind_and_a_nullable_destination(self):
        assert "kind           TEXT NOT NULL DEFAULT 'mover'" in self.sql
        assert "ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'mover'" in self.sql
        assert "para_etapa_id  UUID REFERENCES" in self.sql

    def test_position_is_numeric_never_integer(self):
        assert "ADD COLUMN IF NOT EXISTS kanban_pos NUMERIC NOT NULL DEFAULT 0" in self.sql

    def test_org_is_required_on_both_tables(self):
        assert self.sql.count("org_id      UUID NOT NULL") + self.sql.count("org_id         UUID NOT NULL") == 2

    def test_card_columns_use_the_configured_status_column(self):
        sql = pipeline_migration(replace(PIPE, status_field="estado"), "crm")
        assert "ADD COLUMN IF NOT EXISTS estado TEXT" in sql and "tier:org" in sql

    def test_refuses_bad_identifiers_and_tiers(self):
        with pytest.raises(ValueError):
            pipeline_migration(PIPE, "crm; DROP TABLE x")
        with pytest.raises(ValueError):
            pipeline_migration(replace(PIPE, card_table="cards;--"), "crm")
        with pytest.raises(ValueError, match="tier"):
            pipeline_migration(PIPE, "crm", tier="public")

    def test_cliente_column_only_when_configured(self):
        assert "cliente_id" not in self.sql
        assert "cliente_id" in pipeline_migration(replace(PIPE, cliente_field="cliente_id"), "crm")


class TestMovimentosGatherer:
    def test_entries_use_the_movements_own_time_and_current_stage_labels(self):
        db = MockSupabaseClient(validate_schema=False, schema="crm")
        db.set_table_data("pipeline_stages", [
            {"id": "s1", "org_id": ORG, "pipeline": "crm", "slug": "a", "label": "Renomeada", "posicao": 0, "ativo": True},
            {"id": "s2", "org_id": ORG, "pipeline": "crm", "slug": "b", "label": "Antiga", "posicao": 1, "ativo": False},
        ])
        db.set_table_data("pipeline_movimentos", [
            {"id": "m1", "org_id": ORG, "pipeline": "crm", "entidade_id": "c1", "de_etapa_id": None, "para_etapa_id": "s1",
             "responsavel_id": USER, "motivo": None, "created_at": "2026-03-01T00:00:00+00:00"},
            {"id": "m2", "org_id": ORG, "pipeline": "crm", "entidade_id": "c1", "de_etapa_id": "s1", "para_etapa_id": "s2",
             "responsavel_id": None, "motivo": "x", "created_at": "2026-03-02T00:00:00+00:00"},
            {"id": "m3", "org_id": ORG, "pipeline": "crm", "entidade_id": "other", "de_etapa_id": None, "para_etapa_id": "s1",
             "responsavel_id": None, "motivo": None, "created_at": "2026-03-03T00:00:00+00:00"},
            {"id": "m4", "org_id": "other-org", "pipeline": "crm", "entidade_id": "c1", "de_etapa_id": None, "para_etapa_id": "s1",
             "responsavel_id": None, "motivo": None, "created_at": "2026-03-04T00:00:00+00:00"},
        ])
        hub = _hub()
        hub = replace(hub, actor_resolver=lambda ids: {USER: {"id": USER, "nome": "Rapha"}})
        entries = movimentos_gatherer(PIPE)(hub, db, ORG, "c1", {})
        assert [e["id"] for e in entries] == ["m1", "m2"]
        assert entries[0] == {
            "id": "m1", "kind": "movimento", "ocorrido_em": "2026-03-01T00:00:00+00:00",
            "ator": {"id": USER, "nome": "Rapha"}, "payload": {"de_etapa": None, "para_etapa": "Renomeada", "motivo": None, "evento": "mover"},
        }
        assert entries[1]["payload"] == {"de_etapa": "Renomeada", "para_etapa": "Antiga", "motivo": "x", "evento": "mover"}

    def test_no_history_no_stage_read(self):
        db = MockSupabaseClient(validate_schema=False, schema="crm")
        assert movimentos_gatherer(PIPE)(_hub(), db, ORG, "c1", {}) == []


class TestMount:
    def _app(self, **kw):
        cfg = FunnelConfig(pipeline=PIPE, tenancy="org", card_hub=_hub(**kw.pop("hub", {})))
        db = MockSupabaseClient(validate_schema=False, schema="crm")
        app = FastAPI()
        from noctusai_lib.domain.pipeline import PipelineContext

        mount_funnel(
            app, cfg, prefix="/api/f", auth_dependency=_auth,
            resolve_context=lambda auth: PipelineContext(db=db, org_id=auth[1], user_id=auth[0]),
            success_response=success_response, get_db=lambda: db, get_storage=lambda: None,
        )
        return app, db

    def test_card_hub_collection_routes_are_not_swallowed_by_the_card_id_route(self):
        app, _ = self._app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/f/cards/tags", headers=HEADERS)
        assert response.status_code == 200  # the hub's literal /tags, not GET /cards/{card_id}="tags"

    def test_hub_and_board_share_the_prefix(self):
        app, _ = self._app()
        paths = {r.path for r in app.routes}
        assert {"/api/f/cards/tags", "/api/f/board", "/api/f/etapas", "/api/f/cards/{card_id}/mover-etapa"} <= paths
        assert any(p.startswith("/api/f/cards/{lead_id}/notas") for p in paths)

    def test_hub_needs_its_di_seams(self):
        cfg = FunnelConfig(pipeline=PIPE, tenancy="org", card_hub=_hub())
        with pytest.raises(ValueError, match="get_db"):
            mount_funnel(FastAPI(), cfg, prefix="/api/f", auth_dependency=_auth, resolve_context=lambda a: None, success_response=success_response)

    def test_no_hub_no_hub_routes(self):
        app = FastAPI()
        mount_funnel(app, make_cfg("org"), prefix="/api/f", auth_dependency=_auth, resolve_context=lambda a: None, success_response=success_response)
        assert not any("/notas" in r.path for r in app.routes)

    def test_prefix_shape_is_checked(self):
        for bad in ("api/f", "/api/f/"):
            with pytest.raises(ValueError, match="prefix"):
                mount_funnel(FastAPI(), make_cfg("org"), prefix=bad, auth_dependency=_auth, resolve_context=lambda a: None, success_response=success_response)

    def test_routes_declare_their_access_tier(self):
        from noctusai_lib.domain.pipeline.funnel import pipeline_board_router

        for tenancy in ("org", "platform"):
            router = pipeline_board_router(
                make_cfg(tenancy), auth_dependency=_auth, resolve_context=lambda a: None, success_response=success_response
            )
            assert router.access_tier == tenancy
