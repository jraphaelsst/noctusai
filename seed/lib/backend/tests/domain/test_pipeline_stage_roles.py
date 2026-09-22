"""Tests for the OPEN stage-role set (`PipelineConfig.stage_roles`) and the
optional `require_stage_admin` write gate on `pipeline_stages_router`.

What these protect:

* **Backwards compatibility.** Every existing consumer builds a
  `PipelineConfig` without `stage_roles`; it must keep accepting exactly
  `proposta_aceite` / `final` and refusing anything else.
* **A declared set is the set.** A CRM-shaped board declaring
  `("ganho", "perdido")` must accept those and refuse the ERP's defaults — the
  validation reads the CONFIG, not a module constant.
* **The write gate gates writes only.** Reads stay open so every member can
  render the board; create / edit / delete / reorder answer to the admin
  dependency. Strict status codes (`== 403` / `== 200`), never a tuple.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from noctusai_lib.domain.pipeline import (
    DEFAULT_STAGE_ROLES,
    STAGE_ROLE_ACCEPT,
    STAGE_ROLE_FINAL,
    STAGE_ROLES,
    PipelineConfig,
    PipelineContext,
    create_stage,
    pipeline_stages_router,
    update_stage,
)
from noctusai_lib.primitives.exceptions import AppException
from noctusai_lib.testing.mocks import MockSupabaseClient

ORG = "org-1"

ERP_LIKE = PipelineConfig(
    pipeline="funil",
    card_table="negociacoes_venda",
    value_field="valor_estimado",
    entity_label="negociação",
    entity_kind="negociacao_venda",
)

CRM_LIKE = PipelineConfig(
    pipeline="crm",
    card_table="leads",
    value_field="valor",
    entity_label="lead",
    entity_kind="lead",
    stage_roles=("ganho", "perdido"),
)


def _db():
    client = MockSupabaseClient(validate_schema=False, schema="erp")
    client.set_table_data(
        "pipeline_stages",
        [
            {"id": "s1", "org_id": ORG, "pipeline": "funil", "slug": "novo",
             "label": "Novo", "cor": "secondary", "posicao": 0, "papel": None,
             "ativo": True},
            {"id": "c1", "org_id": ORG, "pipeline": "crm", "slug": "novo",
             "label": "Novo", "cor": "secondary", "posicao": 0, "papel": None,
             "ativo": True},
        ],
    )
    client.set_table_data("negociacoes_venda", [])
    client.set_table_data("leads", [])
    return client


# ---------------------------------------------------------------------------
# PipelineConfig.stage_roles
# ---------------------------------------------------------------------------

def test_default_roles_are_the_historical_two():
    assert DEFAULT_STAGE_ROLES == (STAGE_ROLE_ACCEPT, STAGE_ROLE_FINAL)
    assert STAGE_ROLES == DEFAULT_STAGE_ROLES
    assert ERP_LIKE.stage_roles == ("proposta_aceite", "final")


def test_a_list_is_normalised_to_a_tuple_so_the_config_stays_hashable():
    cfg = PipelineConfig(
        pipeline="x", card_table="t", value_field="v", entity_label="item",
        entity_kind="item", stage_roles=["a", "b"],  # type: ignore[arg-type]
    )
    assert cfg.stage_roles == ("a", "b")
    hash(cfg)


@pytest.mark.parametrize("roles", [("a", "a"), ("",), ("  ",)])
def test_a_degenerate_role_set_is_refused_at_construction(roles):
    with pytest.raises(ValueError):
        PipelineConfig(
            pipeline="x", card_table="t", value_field="v", entity_label="item",
            entity_kind="item", stage_roles=roles,
        )


def test_default_config_still_accepts_the_default_roles():
    db = _db()
    stage = create_stage(db, ERP_LIKE, {"label": "Fechado", "papel": "final"}, org_id=ORG)
    assert stage["papel"] == "final"


def test_default_config_refuses_a_role_it_did_not_declare():
    with pytest.raises(AppException) as exc:
        create_stage(_db(), ERP_LIKE, {"label": "Ganho", "papel": "ganho"}, org_id=ORG)
    assert "Papel inválido" in exc.value.message


def test_a_declared_role_set_is_accepted_on_create_and_update():
    db = _db()
    stage = create_stage(db, CRM_LIKE, {"label": "Ganho", "papel": "ganho"}, org_id=ORG)
    assert stage["papel"] == "ganho"
    updated = update_stage(db, CRM_LIKE, "c1", {"papel": "perdido"}, org_id=ORG)
    assert updated["papel"] == "perdido"


def test_a_declared_role_set_replaces_the_defaults():
    with pytest.raises(AppException) as exc:
        create_stage(_db(), CRM_LIKE, {"label": "Fechado", "papel": "final"}, org_id=ORG)
    assert "ganho" in exc.value.message and "perdido" in exc.value.message


# ---------------------------------------------------------------------------
# Router: /opcoes reflects the config; require_stage_admin gates writes only
# ---------------------------------------------------------------------------

def _app(cfg: PipelineConfig, *, admin: bool | None):
    db = _db()

    def auth():
        return {"user_id": "u1"}

    def require_admin():
        if not admin:
            raise HTTPException(status_code=403, detail="stage admin only")

    router = pipeline_stages_router(
        cfg,
        auth_dependency=auth,
        resolve_context=lambda _auth: PipelineContext(db=db, org_id=ORG, user_id="u1"),
        success_response=lambda data: {"data": data},
        prefix="/etapas",
        require_stage_admin=require_admin if admin is not None else None,
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_opcoes_serves_the_configured_roles():
    client = _app(CRM_LIKE, admin=None)
    resp = client.get("/etapas/opcoes")
    assert resp.status_code == 200
    assert resp.json()["data"]["papeis"] == ["ganho", "perdido"]


def test_without_the_gate_any_authenticated_caller_may_write():
    client = _app(ERP_LIKE, admin=None)
    resp = client.post("/etapas", json={"label": "Visitas"})
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/etapas", {"label": "Visitas"}),
        ("patch", "/etapas/s1", {"label": "Renomeada"}),
        ("delete", "/etapas/s1", None),
        ("post", "/etapas/reordenar", {"ordem": ["s1"]}),
    ],
)
def test_the_gate_refuses_every_write_for_a_non_admin(method, path, body):
    client = _app(ERP_LIKE, admin=False)
    kwargs = {"json": body} if body is not None else {}
    resp = getattr(client, method)(path, **kwargs)
    assert resp.status_code == 403


def test_the_gate_leaves_reads_open_for_a_non_admin():
    client = _app(ERP_LIKE, admin=False)
    assert client.get("/etapas").status_code == 200
    assert client.get("/etapas/opcoes").status_code == 200


def test_the_gate_lets_an_admin_write():
    client = _app(ERP_LIKE, admin=True)
    resp = client.patch("/etapas/s1", json={"label": "Renomeada"})
    assert resp.status_code == 200
    assert resp.json()["data"]["label"] == "Renomeada"
