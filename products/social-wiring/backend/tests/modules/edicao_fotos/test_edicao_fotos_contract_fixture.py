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
