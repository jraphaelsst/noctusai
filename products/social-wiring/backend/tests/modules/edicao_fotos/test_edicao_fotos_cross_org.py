"""Org isolation. The engine runs on a service-role client, so every one of
these is enforced by the module (`deps.load_visible_batch`), not by RLS.

- Routes addressing a batch: a batch of ANOTHER org is a `404`, even for
  that caller's agency admin — and so is a colleague's batch for a corretor.
- Routes without an id (`/lotes`, `/configuracoes`, `/capacidades`) read and
  write only the caller's own org.
- `/curadores` is platform-scope by contract (grants carry no org); its
  "other tenant" case is the unknown-user / unknown-grant `404`.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from .conftest import ORG, OTHER_ORG, USERS

_BATCH_ROUTES = [
    ("get", "/api/edicao-fotos/lotes/{lote_id}", None),
    ("post", "/api/edicao-fotos/lotes/{lote_id}/fotos", "files"),
    ("post", "/api/edicao-fotos/lotes/{lote_id}/vista", {"codigo": "CA1"}),
    ("post", "/api/edicao-fotos/lotes/{lote_id}/submeter", None),
    ("post", "/api/edicao-fotos/lotes/{lote_id}/fotos/{foto_id}/retentar", None),
    ("get", "/api/edicao-fotos/lotes/{lote_id}/zip", None),
    ("get", "/api/edicao-fotos/revisao/{lote_id}", None),
    ("post", "/api/edicao-fotos/revisao/{lote_id}/fotos/{foto_id}/decisao", {"decisao": "aprovar"}),
]


def _call(edicao, method, path, body, lote_id, foto_id):
    url = path.replace("{lote_id}", lote_id).replace("{foto_id}", foto_id)
    kwargs = {}
    if body == "files":
        kwargs["files"] = [("fotos", ("a.jpg", b"x", "image/jpeg"))]
    elif body is not None:
        kwargs["json"] = body
    return getattr(edicao.http, method)(url, **kwargs)


@pytest.mark.parametrize("method,path,body", _BATCH_ROUTES, ids=lambda v: str(v))
def test_other_org_batch_is_404_even_for_platform_admin(edicao, method, path, body) -> None:
    lote = edicao.make_batch("outra_admin")
    foto = edicao.add_photo(lote)
    for user in ("admin", "plataforma"):
        resp = _call(edicao.as_user(user), method, path, body, lote, foto)
        assert resp.status_code == 404, f"{user}: {method} {path} -> {resp.status_code}"
        assert resp.json()["code"] == "lote_nao_encontrado"


@pytest.mark.parametrize("method,path,body", _BATCH_ROUTES, ids=lambda v: str(v))
def test_colleagues_batch_is_404_for_a_corretor(edicao, method, path, body) -> None:
    lote = edicao.make_batch("corretor2")
    foto = edicao.add_photo(lote)
    resp = _call(edicao.as_user("corretor"), method, path, body, lote, foto)
    assert resp.status_code == 404
    assert resp.json()["code"] == "lote_nao_encontrado"


def test_photo_of_another_batch_is_404(edicao) -> None:
    mine = edicao.make_batch("corretor")
    theirs = edicao.make_batch("outra_admin")
    foreign_photo = edicao.add_photo(theirs)
    edicao.as_user("corretor")
    retry = edicao.http.post(f"/api/edicao-fotos/lotes/{mine}/fotos/{foreign_photo}/retentar")
    decide = edicao.http.post(
        f"/api/edicao-fotos/revisao/{mine}/fotos/{foreign_photo}/decisao", json={"decisao": "aprovar"}
    )
    assert retry.status_code == 404 and retry.json()["code"] == "foto_nao_encontrada"
    assert decide.status_code == 404 and decide.json()["code"] == "foto_nao_encontrada"


def test_unknown_batch_is_404(edicao) -> None:
    resp = edicao.as_user("admin").http.get(f"/api/edicao-fotos/lotes/{uuid4()}")
    assert resp.status_code == 404


def test_list_never_shows_another_orgs_batches(edicao) -> None:
    edicao.make_batch("outra_admin", nome="alheio")
    own = edicao.make_batch("corretor", nome="meu")
    for user in ("admin", "plataforma", "corretor"):
        items = edicao.as_user(user).http.get("/api/edicao-fotos/lotes").json()["items"]
        assert [i["id"] for i in items] == [own], user


def test_settings_read_and_write_only_the_callers_org(edicao) -> None:
    edicao.configure_org(OTHER_ORG, modelo_editor_id=None)
    edicao.as_user("admin")
    resp = edicao.http.put(
        "/api/edicao-fotos/configuracoes",
        json={"tipos_edicao_ativos": ["ceu"], "modelo_editor_imagem": "gpt-image-2.5-flare"},
    )
    assert resp.status_code == 200 and resp.json()["org_id"] == ORG
    assert edicao.run(edicao.repo.get_org_settings(OTHER_ORG)).modelo_editor_id is None
    assert edicao.http.get("/api/edicao-fotos/configuracoes").json()["org_id"] == ORG


def test_capabilities_read_the_callers_org_settings(edicao) -> None:
    edicao.configure_org(OTHER_ORG)  # configured elsewhere only
    caps = edicao.as_user("corretor").http.get("/api/edicao-fotos/capacidades").json()
    assert caps["modelo_configurado"] is False and caps["pode_criar_lote"] is False


_REGRA_ROUTES = [
    ("put", "/api/edicao-fotos/regras/{regra_id}", {"texto": "x"}),
    ("post", "/api/edicao-fotos/regras/{regra_id}/aprovar", None),
    ("post", "/api/edicao-fotos/regras/{regra_id}/rejeitar", None),
]


@pytest.mark.parametrize("method,path,body", _REGRA_ROUTES, ids=lambda v: str(v))
def test_other_org_rule_is_404_even_for_platform_admin(edicao, method, path, body) -> None:
    """W7 — same shape as `_BATCH_ROUTES` above: `deps.load_visible_rule`
    404s a rule from another org for EVERY caller, including the platform
    admin (R1 keeps every caller inside their own org)."""
    regra = edicao.run(
        edicao.repo.add_rule(org_id=OTHER_ORG, texto="Regra alheia", origem_comentarios=())
    )
    url = path.replace("{regra_id}", regra.id)
    kwargs = {"json": body} if body is not None else {}
    for user in ("admin", "plataforma"):
        resp = getattr(edicao.as_user(user).http, method)(url, **kwargs)
        assert resp.status_code == 404, f"{user}: {method} {path} -> {resp.status_code}"
        assert resp.json()["code"] == "regra_nao_encontrada"


def test_regras_list_and_effective_guide_never_leak_another_org(edicao) -> None:
    edicao.run(edicao.repo.add_rule(org_id=OTHER_ORG, texto="Regra alheia", origem_comentarios=()))
    mine = edicao.as_user("admin").http.post("/api/edicao-fotos/regras", json={"texto": "Minha regra"})
    assert mine.status_code == 201
    items = edicao.http.get("/api/edicao-fotos/regras").json()["items"]
    assert [r["texto"] for r in items] == ["Minha regra"]
    guia = edicao.http.get("/api/edicao-fotos/regras/guia-efetivo").json()
    assert guia["atual"] is None  # no active company guide yet — never raises


def test_curator_routes_404_for_unknown_user_and_grant(edicao) -> None:
    edicao.as_user("plataforma")
    add = edicao.http.post("/api/edicao-fotos/curadores", json={"user_id": str(uuid4())})
    remove = edicao.http.delete(f"/api/edicao-fotos/curadores/{USERS['corretor'].id}")
    assert add.status_code == 404 and add.json()["code"] == "usuario_nao_encontrado"
    assert remove.status_code == 404 and remove.json()["code"] == "curador_nao_encontrado"
