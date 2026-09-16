"""Replays the pinned FE↔BE contract fixture against the real routes.

`seed/lib/frontend/src/photo-editing/contract.fixture.json` holds the wire
shapes the seed FE hooks are typed against. Every response entry must be
matched by the live route (same keys, same JSON types — `null` matches any
type, extra response keys are allowed); every request-body entry must be
accepted as-is. A shape change on either side fails here first.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .conftest import EDIT_MODEL

FIXTURE_REL = Path("seed/lib/frontend/src/photo-editing/contract.fixture.json")


def _fixture() -> dict[str, Any]:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / FIXTURE_REL
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"contract fixture not found: {FIXTURE_REL}")


FIXTURE = _fixture()


def _kind(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def assert_shape(expected: Any, actual: Any, path: str = "$") -> None:
    if expected is None or actual is None:
        return
    assert _kind(expected) == _kind(actual), f"{path}: {_kind(expected)} != {_kind(actual)}"
    if isinstance(expected, dict):
        missing = set(expected) - set(actual)
        assert not missing, f"{path}: missing keys {sorted(missing)}"
        for key, value in expected.items():
            assert_shape(value, actual[key], f"{path}.{key}")
    elif isinstance(expected, list) and expected and actual:
        for i, item in enumerate(actual):
            assert_shape(expected[0], item, f"{path}[{i}]")


def _ready_batch(edicao) -> str:
    """A submitted, processed batch with one photo awaiting a decision,
    created and filled through the routes with the fixture's bodies."""
    edicao.configure_org()
    edicao.activate_guide()
    edicao.as_user("corretor")
    created = edicao.http.post("/api/edicao-fotos/lotes", json=FIXTURE["novo_lote_body"])
    assert created.status_code == 201, created.text
    assert_shape(FIXTURE["lote_criado"], created.json())
    lote = created.json()["id"]
    upload = edicao.http.post(
        f"/api/edicao-fotos/lotes/{lote}/fotos",
        files=[(FIXTURE["upload_field"], ("sala.jpg", b"\xff\xd8jpeg", "image/jpeg"))],
    )
    assert upload.status_code == 201, upload.text
    assert edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/submeter", json={}).status_code == 200
    edicao.drain()
    return lote


def test_capacidades_shape(edicao) -> None:
    edicao.configure_org()
    resp = edicao.as_user("corretor").http.get("/api/edicao-fotos/capacidades")
    assert_shape(FIXTURE["capacidades"], resp.json())
    platform = edicao.as_user("plataforma").http.get("/api/edicao-fotos/capacidades").json()
    assert platform["dashboard"] in ("org", "platform")  # the FE's literal set


def test_lotes_list_and_detail_shapes(edicao) -> None:
    lote = _ready_batch(edicao)
    page = edicao.http.get("/api/edicao-fotos/lotes", params={"page": 1, "page_size": 50}).json()
    assert_shape(FIXTURE["lotes_page"], page)
    assert page["items"][0]["estado_agregado"] == "aguardando_revisao"
    detail = edicao.http.get(f"/api/edicao-fotos/lotes/{lote}").json()
    assert_shape(FIXTURE["lote_detalhe"], detail)
    assert "avaliacao" not in detail["fotos"][0]


def test_revisao_shapes_by_role(edicao) -> None:
    lote = _ready_batch(edicao)
    corretor = edicao.http.get(f"/api/edicao-fotos/revisao/{lote}").json()
    assert isinstance(corretor, list) and corretor
    assert_shape(FIXTURE["foto_revisao_corretor"], corretor[0])
    assert "avaliacao" not in corretor[0]
    admin = edicao.as_user("admin").http.get(f"/api/edicao-fotos/revisao/{lote}").json()
    assert_shape(FIXTURE["foto_revisao_admin"], admin[0])
    assert admin[0]["avaliacao"] is not None


def test_decision_bodies_are_accepted(edicao) -> None:
    lote = _ready_batch(edicao)
    foto = edicao.http.get(f"/api/edicao-fotos/revisao/{lote}").json()[0]["id"]
    url = f"/api/edicao-fotos/revisao/{lote}/fotos/{foto}/decisao"
    rejected = edicao.http.post(url, json=FIXTURE["decisao_body_rejeitar"])
    assert rejected.status_code == 200, rejected.text
    assert_shape(FIXTURE["foto_revisao_corretor"], rejected.json())
    assert rejected.json()["decisao"] == "rejeitar"
    approved = edicao.http.post(url, json=FIXTURE["decisao_body_aprovar"])
    assert approved.status_code == 200 and approved.json()["comentario"] is None


def test_vista_body_is_accepted(edicao) -> None:
    from noctusai_lib.domain.real_estate.imovel import ImovelFoto

    edicao.configure_org()
    lote = edicao.make_batch("corretor")
    edicao.vista.galleries[FIXTURE["vista_body"]["codigo"]] = [
        ImovelFoto(codigo="1", url="https://cdn/1.jpg")
    ]
    resp = edicao.as_user("corretor").http.post(
        f"/api/edicao-fotos/lotes/{lote}/vista", json=FIXTURE["vista_body"]
    )
    assert resp.status_code == 200, resp.text


def test_configuracoes_round_trip(edicao) -> None:
    edicao.configure_org()
    got = edicao.as_user("corretor").http.get("/api/edicao-fotos/configuracoes").json()
    assert_shape(FIXTURE["configuracoes"], got)
    assert got["modelo_editor_imagem"] == EDIT_MODEL
    put = edicao.as_user("admin").http.put(
        "/api/edicao-fotos/configuracoes", json=FIXTURE["configuracoes_body"]
    )
    assert put.status_code == 200, put.text
    assert_shape(FIXTURE["configuracoes"], put.json())
    assert put.json()["modelo_editor_imagem"] == FIXTURE["configuracoes_body"]["modelo_editor_imagem"]


def test_modelos_shape(edicao) -> None:
    resp = edicao.as_user("admin").http.get("/api/edicao-fotos/modelos")
    assert resp.status_code == 200
    models = resp.json()
    assert isinstance(models, list) and models
    for item in models:
        assert_shape(FIXTURE["modelo"], item)
    assert {m["id"] for m in models} >= {FIXTURE["modelo"]["id"]}


def test_error_envelope_shape(edicao) -> None:
    resp = edicao.as_user("corretor").http.post(
        "/api/edicao-fotos/lotes", json=FIXTURE["novo_lote_body"]
    )
    assert resp.status_code == 422
    assert_shape(FIXTURE["erro"], resp.json())
    assert resp.json()["code"] == FIXTURE["erro"]["code"]


def test_zip_is_a_binary_get(edicao) -> None:
    lote = _ready_batch(edicao)
    foto = edicao.http.get(f"/api/edicao-fotos/revisao/{lote}").json()[0]["id"]
    edicao.http.post(
        f"/api/edicao-fotos/revisao/{lote}/fotos/{foto}/decisao", json=FIXTURE["decisao_body_aprovar"]
    )
    resp = edicao.http.get(f"/api/edicao-fotos/lotes/{lote}/zip")
    assert resp.status_code == 200 and resp.headers["content-type"] == "application/zip"
    assert resp.content[:2] == b"PK"


# --- W6: reference pool + guides + platform settings -----------------------


def _upload_fixture_pair(edicao):
    spec = FIXTURE["referencia_upload"]
    form = spec["form"]
    return edicao.http.post(
        "/api/edicao-fotos/referencias",
        data={"comodo": form["comodo"], "tipos_edicao": form["tipos_edicao"], "nota": form["nota"]},
        files=[(name, (f"{name}.jpg", b"\xff\xd8jpeg", "image/jpeg")) for name in spec["file_fields"]],
    )


def test_referencias_shapes(edicao) -> None:
    edicao.as_user("curador")
    created = _upload_fixture_pair(edicao)
    assert created.status_code == 201, created.text
    assert_shape(FIXTURE["referencia"], created.json())
    assert created.json()["tipos_edicao"] == FIXTURE["referencia_upload"]["form"]["tipos_edicao"]
    page = edicao.http.get("/api/edicao-fotos/referencias", params={"page": 1, "page_size": 50})
    assert_shape(FIXTURE["referencias_page"], page.json())
    archived = edicao.http.delete(f"/api/edicao-fotos/referencias/{created.json()['id']}")
    assert_shape(FIXTURE["referencia"], archived.json())
    assert isinstance(archived.json()["arquivada_em"], str)


def test_pool_cheio_error_shape(edicao) -> None:
    edicao.as_user("plataforma")
    edicao.http.put(
        "/api/edicao-fotos/configuracoes/plataforma",
        json={**FIXTURE["configuracoes_plataforma_body"], "limite_pares_referencia": 1},
    )
    assert _upload_fixture_pair(edicao).status_code == 201
    full = _upload_fixture_pair(edicao)
    assert full.status_code == 409
    assert full.json() == FIXTURE["erro_pool_cheio"]


def test_guias_shapes(edicao) -> None:
    edicao.as_user("plataforma")
    created = edicao.http.post("/api/edicao-fotos/guias", json=FIXTURE["guia_body"])
    assert created.status_code == 201, created.text
    assert_shape(FIXTURE["guia"], created.json())
    assert created.json()["origem"] == FIXTURE["guia"]["origem"]
    for action, status in (("ativar", 200), ("restaurar", 201)):
        resp = edicao.http.post(f"/api/edicao-fotos/guias/1/{action}", json={})
        assert resp.status_code == status, resp.text
        assert_shape(FIXTURE["guia"], resp.json())
    page = edicao.http.get("/api/edicao-fotos/guias", params={"page": 1, "page_size": 20}).json()
    assert_shape(FIXTURE["guias_page"], page)
    assert page["versao_ativa"] == 1
    _upload_fixture_pair(edicao)
    regen = edicao.http.post("/api/edicao-fotos/guias/regenerar", json={})
    assert regen.status_code == 202
    assert_shape(FIXTURE["guia_regenerar"], regen.json())


def test_regras_shapes(edicao) -> None:
    edicao.as_user("admin")
    created = edicao.http.post("/api/edicao-fotos/regras", json=FIXTURE["regra_body"])
    assert created.status_code == 201, created.text
    assert_shape(FIXTURE["regra"], created.json())
    assert created.json()["texto"] == FIXTURE["regra_body"]["texto"]

    page = edicao.http.get("/api/edicao-fotos/regras").json()
    assert_shape(FIXTURE["regras_page"], page)

    approved = edicao.http.post(f"/api/edicao-fotos/regras/{created.json()['id']}/aprovar")
    assert_shape(FIXTURE["regra"], approved.json())


def test_guia_efetivo_shape(edicao) -> None:
    edicao.as_user("admin")
    edicao.activate_guide()
    view = edicao.http.get("/api/edicao-fotos/regras/guia-efetivo").json()
    assert_shape(FIXTURE["guia_efetivo_view"], view)
    assert_shape(FIXTURE["guia_efetivo"], view["atual"])


def test_painel_shape(edicao) -> None:
    edicao.configure_org()
    edicao.activate_guide()
    edicao.as_user("corretor")
    lote = edicao.make_batch("corretor")
    edicao.upload(lote)
    edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/submeter", json={})
    edicao.drain()
    foto = edicao.http.get(f"/api/edicao-fotos/revisao/{lote}").json()[0]["id"]
    edicao.http.post(
        f"/api/edicao-fotos/revisao/{lote}/fotos/{foto}/decisao", json=FIXTURE["decisao_body_aprovar"]
    )
    resp = edicao.as_user("admin").http.get("/api/edicao-fotos/painel")
    assert resp.status_code == 200, resp.text
    assert_shape(FIXTURE["painel"], resp.json())


def test_configuracoes_plataforma_round_trip(edicao) -> None:
    edicao.as_user("plataforma")
    got = edicao.http.get("/api/edicao-fotos/configuracoes/plataforma").json()
    assert_shape(FIXTURE["configuracoes_plataforma"], got)
    put = edicao.http.put(
        "/api/edicao-fotos/configuracoes/plataforma", json=FIXTURE["configuracoes_plataforma_body"]
    )
    assert put.status_code == 200, put.text
    assert put.json() == FIXTURE["configuracoes_plataforma_body"]


# --- W8: model catalog admin + processing ------------------------------------


def _w8_seams(edicao):
    """The W8 routes' own seams (store, probe, worker control, probe memory)."""
    from noctusai_lib.integrations.llm import (
        FakeCreditProbe,
        InMemoryModelCatalogStore,
        clear_model_overrides,
    )

    from app.modules.edicao_fotos.deps import (
        get_catalog_store,
        get_credit_probe,
        get_platform_openai_key,
        get_worker_control,
    )
    from app.modules.edicao_fotos.routers.processamento import ProbeMemory, get_probe_memory
    from app.modules.edicao_fotos.services import worker as worker_service

    clear_model_overrides()
    store, memory = InMemoryModelCatalogStore(), ProbeMemory()
    edicao.app.dependency_overrides.update({
        get_catalog_store: lambda: store,
        get_credit_probe: lambda: FakeCreditProbe("sem_credito"),
        get_worker_control: lambda: worker_service,
        get_probe_memory: lambda: memory,
        get_platform_openai_key: lambda: (lambda: "sk-test"),
    })
    return [get_catalog_store, get_credit_probe, get_worker_control, get_probe_memory, get_platform_openai_key]


def _drop(edicao, keys) -> None:
    from noctusai_lib.integrations.llm import clear_model_overrides

    for key in keys:
        edicao.app.dependency_overrides.pop(key, None)
    clear_model_overrides()


def test_modelos_admin_view_shape(edicao) -> None:
    resp = edicao.as_user("admin").http.get("/api/edicao-fotos/modelos")
    item = next(m for m in resp.json() if m["id"] == FIXTURE["modelo_admin_visao"]["id"])
    assert_shape(FIXTURE["modelo_admin_visao"], item)
    assert isinstance(item["metricas"], dict)


def test_modelos_catalogo_shapes(edicao) -> None:
    keys = _w8_seams(edicao)
    try:
        http = edicao.as_user("plataforma").http
        page = http.get("/api/edicao-fotos/modelos/catalogo").json()
        assert_shape(FIXTURE["modelos_catalogo_page"], page)
        saved = http.put("/api/edicao-fotos/modelos/catalogo/gpt-image-2", json=FIXTURE["modelo_catalogo_body"])
        assert saved.status_code == 200, saved.text
        assert_shape(FIXTURE["modelo_catalogo_salvo"], saved.json())
        versions = http.get("/api/edicao-fotos/modelos/catalogo/gpt-image-2/versoes", params={"kind": "image_edit"})
        assert_shape(FIXTURE["modelo_versoes_page"], versions.json())
    finally:
        _drop(edicao, keys)


def test_modelos_etapas_and_notas_shapes(edicao) -> None:
    http = edicao.as_user("plataforma").http
    assert_shape(FIXTURE["modelos_etapas"], http.get("/api/edicao-fotos/modelos/etapas").json())
    put = http.put("/api/edicao-fotos/modelos/etapas", json=FIXTURE["modelos_etapas_body"])
    assert put.status_code == 200, put.text
    assert_shape(FIXTURE["modelos_etapas"], put.json())
    queued = http.post("/api/edicao-fotos/modelos/notas/gerar")
    assert queued.status_code == 202
    assert_shape(FIXTURE["notas_gerar"], queued.json())


def test_processamento_shapes(edicao) -> None:
    keys = _w8_seams(edicao)
    try:
        http = edicao.as_user("plataforma").http
        assert_shape(FIXTURE["processamento"], http.get("/api/edicao-fotos/processamento").json())
        put = http.put("/api/edicao-fotos/processamento", json=FIXTURE["processamento_body"])
        assert put.status_code == 200, put.text
        assert_shape(FIXTURE["processamento"], put.json())
        sonda = http.post("/api/edicao-fotos/processamento/sonda")
        assert_shape(FIXTURE["sonda"], sonda.json())
    finally:
        _drop(edicao, keys)
