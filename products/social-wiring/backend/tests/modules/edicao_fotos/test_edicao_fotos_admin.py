"""Capabilities, org + platform settings, and curator grants."""
from __future__ import annotations

from decimal import Decimal

import pytest

from noctusai_lib.domain.photo_editing import EditType, Speed

from .conftest import EDIT_MODEL, ORG, USERS

# --- capacidades ----------------------------------------------------------


def test_corretor_capabilities_never_expose_the_verdict(edicao) -> None:
    edicao.configure_org()
    caps = edicao.as_user("corretor").http.get("/api/edicao-fotos/capacidades").json()
    assert caps["pode_criar_lote"] is True
    assert caps["pode_ver_veredito"] is False
    assert caps["pode_gerir_pool"] is False and caps["dashboard"] is None
    assert caps["economico_disponivel"] is False
    assert caps["economico_bloqueado_motivo"] == "modelo_sem_batch"
    assert caps["tipos_edicao_ativos"] == ["cor_luz", "ceu"]
    assert caps["limites"] == {"fotos_por_lote": 100, "bytes_por_foto": 26214400}


def test_admin_and_platform_capabilities(edicao) -> None:
    edicao.configure_org()
    admin = edicao.as_user("admin").http.get("/api/edicao-fotos/capacidades").json()
    assert admin["pode_ver_veredito"] and admin["pode_aprovar_regras"] and admin["dashboard"] == "org"
    platform = edicao.as_user("plataforma").http.get("/api/edicao-fotos/capacidades").json()
    assert platform["dashboard"] == "platform" and platform["pode_ativar_guia"] is True


def test_curator_without_org_role_gets_capabilities_but_no_batches(edicao) -> None:
    caps = edicao.as_user("curador").http.get("/api/edicao-fotos/capacidades")
    assert caps.status_code == 200
    assert caps.json()["pode_gerir_pool"] is True and caps.json()["pode_criar_lote"] is False
    assert edicao.http.get("/api/edicao-fotos/lotes").status_code == 403


def test_no_model_reports_sem_modelo(edicao) -> None:
    caps = edicao.as_user("admin").http.get("/api/edicao-fotos/capacidades").json()
    assert caps["modelo_configurado"] is False
    assert caps["economico_bloqueado_motivo"] == "sem_modelo"


# --- org settings -----------------------------------------------------------


def test_org_settings_default_readable_by_members(edicao) -> None:
    for user in ("gerente", "corretor"):
        body = edicao.as_user(user).http.get("/api/edicao-fotos/configuracoes").json()
        assert body["org_id"] == ORG and body["modelo_editor_imagem"] is None
        assert body["tipos_edicao_ativos"] == []
        assert body["velocidade_padrao"] == "urgente" and body["segue_padrao_plataforma"] is True


def test_modelos_catalog(edicao) -> None:
    models = edicao.as_user("corretor").http.get("/api/edicao-fotos/modelos").json()
    by_id = {m["id"]: m for m in models}
    assert EDIT_MODEL in by_id
    assert by_id[EDIT_MODEL]["suporta_batch"] is False
    assert by_id[EDIT_MODEL]["versao"] == f"{EDIT_MODEL}-2026-09-08"
    assert by_id[EDIT_MODEL]["metricas"] is None


def test_org_settings_update_persists(edicao) -> None:
    resp = edicao.as_user("admin").http.put(
        "/api/edicao-fotos/configuracoes",
        json={
            "tipos_edicao_ativos": ["staging_virtual", "ceu", "ceu"],
            "modelo_editor_imagem": EDIT_MODEL,
            "velocidade_padrao": "urgente",
            "notificacoes_ativas": False,
        },
    )
    assert resp.status_code == 200, resp.text
    saved = edicao.run(edicao.repo.get_org_settings(ORG))
    assert saved.tipos_edicao_ativos == (EditType.STAGING_VIRTUAL, EditType.CEU)
    assert saved.modelo_editor_id == EDIT_MODEL
    # "urgente" IS the platform default → the org follows the platform.
    assert saved.velocidade_override is None and saved.notificacoes_ativas is False
    assert resp.json()["velocidade_padrao"] == "urgente"


def test_org_settings_keep_owner_limits_and_omitted_switches(edicao) -> None:
    edicao.configure_org(limite_fotos_por_lote=40, notificacoes_ativas=False)
    edicao.as_user("admin").http.put(
        "/api/edicao-fotos/configuracoes", json={"tipos_edicao_ativos": ["ceu"]}
    )
    saved = edicao.run(edicao.repo.get_org_settings(ORG))
    assert saved.limite_fotos_por_lote == 40
    assert saved.notificacoes_ativas is False  # the FE body omits it


@pytest.mark.parametrize(
    "body,code",
    [
        ({"modelo_editor_imagem": "gpt-inventado"}, "modelo_desconhecido"),
        ({"modelo_editor_imagem": EDIT_MODEL, "velocidade_padrao": "economico"}, "economico_indisponivel"),
        ({"velocidade_padrao": "economico"}, "economico_indisponivel"),
    ],
)
def test_org_settings_refusals(edicao, body, code) -> None:
    resp = edicao.as_user("admin").http.put("/api/edicao-fotos/configuracoes", json=body)
    assert resp.status_code == 422 and resp.json()["code"] == code
    assert edicao.run(edicao.repo.get_org_settings(ORG)) is None


def test_org_settings_reject_unknown_edit_type_and_fields(edicao) -> None:
    edicao.as_user("admin")
    assert edicao.http.put(
        "/api/edicao-fotos/configuracoes", json={"tipos_edicao_ativos": ["pintura"]}
    ).status_code == 422
    assert edicao.http.put(
        "/api/edicao-fotos/configuracoes", json={"limite_fotos_por_lote": 1000}
    ).status_code == 422


# --- platform settings -------------------------------------------------------


def test_platform_settings_round_trip(edicao) -> None:
    edicao.as_user("plataforma")
    assert edicao.http.get("/api/edicao-fotos/configuracoes/plataforma").json() == {
        "velocidade_default": "urgente",
        "notificacoes_globais_ativas": True,
        "preco_storage_gb_mes_usd": None,
    }
    resp = edicao.http.put(
        "/api/edicao-fotos/configuracoes/plataforma",
        json={"notificacoes_globais_ativas": False, "preco_storage_gb_mes_usd": "0.021"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["preco_storage_gb_mes_usd"] == "0.021"
    stored = edicao.repo.platform_settings
    assert stored.notificacoes_globais_ativas is False
    assert stored.preco_storage_gb_mes_usd == Decimal("0.021")


def test_platform_default_economico_is_refused(edicao) -> None:
    resp = edicao.as_user("plataforma").http.put(
        "/api/edicao-fotos/configuracoes/plataforma", json={"velocidade_default": "economico"}
    )
    assert resp.status_code == 422 and resp.json()["code"] == "economico_indisponivel"
    assert edicao.repo.platform_settings.velocidade_default is Speed.URGENTE


# --- curadores ---------------------------------------------------------------


def test_curator_grant_lifecycle(edicao) -> None:
    edicao.as_user("plataforma")
    listed = edicao.http.get("/api/edicao-fotos/curadores").json()
    assert [i["user_id"] for i in listed["items"]] == [USERS["curador"].id]
    assert listed["items"][0]["nome"] == "Cris Curadora"

    target = USERS["corretor"].id
    added = edicao.http.post("/api/edicao-fotos/curadores", json={"user_id": target})
    assert added.status_code == 201, added.text
    assert added.json()["concedido_por"] == USERS["plataforma"].id
    assert edicao.run(edicao.grants.has_permission(user_id=target, permission="photo_curator"))
    # idempotent
    assert edicao.http.post("/api/edicao-fotos/curadores", json={"user_id": target}).status_code == 201
    assert edicao.http.get("/api/edicao-fotos/curadores").json()["total"] == 2

    removed = edicao.http.delete(f"/api/edicao-fotos/curadores/{target}")
    assert removed.status_code == 204
    assert not edicao.run(edicao.grants.has_permission(user_id=target, permission="photo_curator"))


def test_new_curator_gains_pool_capability(edicao) -> None:
    edicao.as_user("plataforma").http.post(
        "/api/edicao-fotos/curadores", json={"user_id": USERS["viewer"].id}
    )
    caps = edicao.as_user("viewer").http.get("/api/edicao-fotos/capacidades")
    assert caps.status_code == 200 and caps.json()["pode_gerir_pool"] is True
