"""Esteira de reels API (BE-1): auth, scoping, board, create, stage gate, binding, equipe, timeline.

Real seams only: the DB is the module ``client`` fixture's mock Supabase; stages are seeded by the
seed ``ensure_default_stages`` on the first read (never hand-inserted unless a test renames one).
"""
from __future__ import annotations

import uuid

import pytest

from app.dependencies import coerce_org_uuid

BASE = "/api/media-creation/esteira"
EQUIPE = "/api/media-creation/equipe"
ORG = str(coerce_org_uuid("test-org-123"))
OTHER_ORG = str(uuid.uuid4())
MARCA = str(uuid.uuid4())
MARCA_B = str(uuid.uuid4())
MARCA_FORA = str(uuid.uuid4())


def _id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def ec(client):
    sb = client.mock_supabase
    for mid, org, name in ((MARCA, ORG, "Marca A"), (MARCA_B, ORG, "Marca B"), (MARCA_FORA, OTHER_ORG, "Fora")):
        sb.from_("marcas").insert({"id": mid, "org_id": org, "name": name}).execute()
    return client


def _ins(ec, table, **row):
    row.setdefault("id", _id())
    ec.mock_supabase.from_(table).insert(row).execute()
    return row


def _headline(ec, marca=MARCA, org=ORG, texto="Como vender mais rápido"):
    return _ins(ec, "cs_headlines", org_id=org, marca_id=marca, texto=texto, favorita=False)


def _roteiro(ec, marca=MARCA, status="completo", headline_id=None, org=ORG):
    return _ins(ec, "cs_roteiros", org_id=org, marca_id=marca, nome="Roteiro 1", status=status, headline_id=headline_id)


def _stages(ec) -> dict:
    r = ec.get(f"{BASE}/etapas")
    assert r.status_code == 200, r.text
    return {s["slug"]: s for s in r.json()["data"]}


def _post(ec, **body):
    body.setdefault("marca_id", MARCA)
    body.setdefault("titulo", "Reel de teste")
    r = ec.post(f"{BASE}/posts", json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _mover(ec, post_id, etapa_id, **extra):
    return ec.post(f"{BASE}/posts/{post_id}/mover-etapa", json={"para_etapa_id": etapa_id, **extra})


def _detail(r):
    """The coded refusal. The app's HTTPException handler flattens ``detail={"code",...}`` into the
    top level of the body (``{code, detail, post_id}``), a shape the FE ApiError parses."""
    b = r.json()
    if isinstance(b.get("detail"), dict):  # FastAPI-native: {"detail": {...}}
        return b["detail"]
    if isinstance(b.get("error"), dict):  # platform envelope: {"error": {"code", "message", "details"}}
        e = b["error"]
        d = {"code": e.get("code"), **(e.get("details") or {})}
        d.setdefault("detail", e.get("message"))
        return d
    assert "code" in b, b
    return b


class TestAuth:
    @pytest.mark.parametrize(
        "method,path,kw",
        [
            ("get", f"{BASE}/board", {}),
            ("get", f"{BASE}/etapas", {}),
            ("post", f"{BASE}/posts", {"json": {"marca_id": MARCA, "titulo": "x"}}),
            ("get", f"{BASE}/posts/{uuid.uuid4()}", {}),
            ("patch", f"{BASE}/posts/{uuid.uuid4()}", {"json": {"titulo": "x"}}),
            ("delete", f"{BASE}/posts/{uuid.uuid4()}", {}),
            ("post", f"{BASE}/posts/{uuid.uuid4()}/mover-etapa", {"json": {"para_etapa_id": str(uuid.uuid4())}}),
            ("put", f"{BASE}/posts/{uuid.uuid4()}/headline", {"json": {"texto": "x"}}),
            ("delete", f"{BASE}/posts/{uuid.uuid4()}/headline", {}),
            ("put", f"{BASE}/posts/{uuid.uuid4()}/roteiro", {"json": {"roteiro_id": str(uuid.uuid4())}}),
            ("delete", f"{BASE}/posts/{uuid.uuid4()}/roteiro", {}),
            ("get", f"{BASE}/posts/tags", {}),
            ("get", f"{BASE}/posts/{uuid.uuid4()}/card", {}),
            ("get", f"{BASE}/posts/{uuid.uuid4()}/timeline", {}),
            ("get", EQUIPE, {}),
            ("post", EQUIPE, {"json": {"nome": "Ana"}}),
            ("patch", f"{EQUIPE}/{uuid.uuid4()}", {"json": {"ativo": False}}),
            ("delete", f"{EQUIPE}/{uuid.uuid4()}", {}),
        ],
    )
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(path, **kw)
        assert r.status_code == 401, (method, path, r.status_code, r.text)


class TestBoard:
    def test_default_stages_seeded_once_and_columns_emitted(self, ec):
        r = ec.get(f"{BASE}/board")
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert [c["stage"]["slug"] for c in data["colunas"]] == [
            "ideacao", "headline_roteiro", "gravacao", "edicao", "pronto", "postado", "bloqueado_cancelado",
        ]
        assert data["orfaos"] == 0
        n = len(ec.mock_supabase.from_("pipeline_stages").select("*").execute().data)
        ec.get(f"{BASE}/board")
        assert len(ec.mock_supabase.from_("pipeline_stages").select("*").execute().data) == n == 7

    def test_not_reseeded_once_the_org_configured_its_stages(self, ec):
        st = _stages(ec)
        assert ec.patch(f"{BASE}/etapas/{st['edicao']['id']}", json={"ativo": False}).status_code == 200
        cols = ec.get(f"{BASE}/board").json()["data"]["colunas"]
        assert "edicao" not in [c["stage"]["slug"] for c in cols] and len(cols) == 6
        assert len(ec.mock_supabase.from_("pipeline_stages").select("*").execute().data) == 7

    def test_groups_filters_and_search(self, ec):
        st = _stages(ec)
        a = _post(ec, titulo="Alpha")
        _post(ec, titulo="Beta", marca_id=MARCA_B)
        h = _headline(ec, texto="Segredo da conversão")
        c = _post(ec, titulo="Gamma", headline_id=h["id"])
        cols = {c["stage"]["slug"]: c for c in ec.get(f"{BASE}/board").json()["data"]["colunas"]}
        assert cols["ideacao"]["total"] == 2 and cols["headline_roteiro"]["total"] == 1
        card = cols["headline_roteiro"]["cards"][0]
        assert card["id"] == c["id"] and card["headline"]["texto"] == "Segredo da conversão"
        assert card["marca_nome"] == "Marca A" and isinstance(card["kanban_pos"], str)
        only_b = ec.get(f"{BASE}/board", params={"marca_id": MARCA_B}).json()["data"]["colunas"]
        assert sum(x["total"] for x in only_b) == 1
        found = ec.get(f"{BASE}/board", params={"busca": "conversão"}).json()["data"]["colunas"]
        assert [x["cards"][0]["id"] for x in found if x["cards"]] == [c["id"]]
        by_title = ec.get(f"{BASE}/board", params={"busca": "alph"}).json()["data"]["colunas"]
        assert [x["cards"][0]["id"] for x in by_title if x["cards"]] == [a["id"]]
        assert st["ideacao"]["id"] == a["etapa_id"]

    def test_archived_excluded_by_default_and_membro_filter(self, ec):
        p1 = _post(ec, titulo="Um")
        p2 = _post(ec, titulo="Dois")
        assert ec.patch(f"{BASE}/posts/{p2['id']}", json={"arquivado": True}).status_code == 200
        total = lambda params: sum(  # noqa: E731
            x["total"] for x in ec.get(f"{BASE}/board", params=params).json()["data"]["colunas"]
        )
        assert total({}) == 1 and total({"incluir_arquivados": True}) == 2
        m = ec.post(EQUIPE, json={"nome": "Vídeo"}).json()["data"]
        _ins(ec, "cs_post_membros", org_id=ORG, post_id=p1["id"], equipe_id=m["id"])
        assert total({"membro_id": m["id"]}) == 1
        card = [c for x in ec.get(f"{BASE}/board").json()["data"]["colunas"] for c in x["cards"]][0]
        assert card["membros"] == [{"id": m["id"], "nome": "Vídeo", "cor": None}]

    def test_cross_org_marca_filter_is_404(self, ec):
        assert ec.get(f"{BASE}/board", params={"marca_id": MARCA_FORA}).status_code == 404

    def test_orphans_counted(self, ec):
        _stages(ec)
        p = _post(ec)
        ec.mock_supabase.from_("cs_posts").update({"etapa_id": "stage-gone"}).eq("id", p["id"]).execute()
        data = ec.get(f"{BASE}/board").json()["data"]
        assert data["orfaos"] == 1 and sum(c["total"] for c in data["colunas"]) == 0


class TestCreate:
    def test_default_stage_and_on_top(self, ec):
        st = _stages(ec)
        a = _post(ec, titulo="A")
        b = _post(ec, titulo="B")
        assert a["etapa_id"] == st["ideacao"]["id"] == b["etapa_id"]
        assert float(b["kanban_pos"]) < float(a["kanban_pos"])

    def test_with_headline_goes_to_second_stage_and_titulo_defaults(self, ec):
        st = _stages(ec)
        h = _headline(ec, texto="Texto da headline")
        r = ec.post(f"{BASE}/posts", json={"marca_id": MARCA, "headline_id": h["id"]})
        assert r.status_code == 201, r.text
        d = r.json()["data"]
        assert d["etapa_id"] == st["headline_roteiro"]["id"] and d["titulo"] == "Texto da headline"
        assert d["headline"]["id"] == h["id"]

    def test_titulo_required_without_headline(self, ec):
        r = ec.post(f"{BASE}/posts", json={"marca_id": MARCA})
        assert r.status_code == 422 and _detail(r)["code"] == "titulo_obrigatorio"

    def test_headline_already_in_post_is_409_with_post_id(self, ec):
        h = _headline(ec)
        first = ec.post(f"{BASE}/posts", json={"marca_id": MARCA, "headline_id": h["id"]}).json()["data"]
        r = ec.post(f"{BASE}/posts", json={"marca_id": MARCA, "headline_id": h["id"]})
        assert r.status_code == 409
        d = _detail(r)
        assert d["code"] == "headline_ja_em_post" and d["post_id"] == first["id"] and d["detail"]

    def test_other_marca_headline_and_conta_are_422(self, ec):
        h = _headline(ec, marca=MARCA_B)
        r = ec.post(f"{BASE}/posts", json={"marca_id": MARCA, "headline_id": h["id"]})
        assert r.status_code == 422 and _detail(r)["code"] == "headline_de_outra_marca"
        conta = _ins(ec, "integration_accounts", org_id=ORG, marca_id=MARCA_B, account_label="@b")
        r = ec.post(f"{BASE}/posts", json={"marca_id": MARCA, "titulo": "x", "conta_id": conta["id"]})
        assert r.status_code == 422 and _detail(r)["code"] == "conta_de_outra_marca"

    def test_cross_org_references_are_404(self, ec):
        assert ec.post(f"{BASE}/posts", json={"marca_id": MARCA_FORA, "titulo": "x"}).status_code == 404
        h = _headline(ec, marca=MARCA_FORA, org=OTHER_ORG)
        assert ec.post(f"{BASE}/posts", json={"marca_id": MARCA, "headline_id": h["id"]}).status_code == 404

    def test_post_in_gated_stage_requires_pendencias(self, ec):
        st = _stages(ec)
        r = ec.post(f"{BASE}/posts", json={"marca_id": MARCA, "titulo": "x", "etapa_id": st["gravacao"]["id"]})
        assert r.status_code == 409 and _detail(r)["code"] == "pendencias"

    def test_unknown_field_rejected(self, ec):
        r = ec.post(f"{BASE}/posts", json={"marca_id": MARCA, "titulo": "x", "bogus": 1})
        assert r.status_code == 422


class TestReadUpdateDelete:
    def test_cross_org_post_is_404_everywhere(self, ec):
        row = _ins(ec, "cs_posts", org_id=OTHER_ORG, marca_id=MARCA_FORA, titulo="alheio", etapa_id=_id(), kanban_pos=0)
        pid = row["id"]
        st = _stages(ec)
        assert ec.get(f"{BASE}/posts/{pid}").status_code == 404
        assert ec.patch(f"{BASE}/posts/{pid}", json={"titulo": "x"}).status_code == 404
        assert ec.delete(f"{BASE}/posts/{pid}").status_code == 404
        assert _mover(ec, pid, st["pronto"]["id"]).status_code == 404
        assert ec.put(f"{BASE}/posts/{pid}/headline", json={"texto": "x"}).status_code == 404
        assert ec.get(f"{BASE}/posts/{pid}/card").status_code == 404

    def test_detail_shape(self, ec):
        d = ec.get(f"{BASE}/posts/{_post(ec)['id']}").json()["data"]
        for k in ("conta", "legenda", "hashtags", "primeiro_comentario", "links_producao", "permalink",
                  "ig_media_id", "lote_ativo", "created_at", "checklist", "comentarios", "membros"):
            assert k in d
        assert d["hashtags"] == [] and d["lote_ativo"] is None and d["formato"] == "reel"

    def test_lote_ativo_is_the_running_batch(self, ec):
        p = _post(ec)
        _ins(ec, "cs_headline_lotes", org_id=ORG, post_id=p["id"], status="completo", created_at="2026-01-01")
        run = _ins(ec, "cs_headline_lotes", org_id=ORG, post_id=p["id"], status="processando", etapa="x", created_at="2026-02-01")
        d = ec.get(f"{BASE}/posts/{p['id']}").json()["data"]
        assert d["lote_ativo"] == {"id": run["id"], "status": "processando", "etapa": "x"}

    def test_patch_updates_and_clears(self, ec):
        p = _post(ec)
        r = ec.patch(
            f"{BASE}/posts/{p['id']}",
            json={"legenda": "oi", "hashtags": ["a", "b"], "links_producao": [{"rotulo": "Drive", "url": "https://x.com/y"}]},
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["legenda"] == "oi" and d["hashtags"] == ["a", "b"] and d["links_producao"][0]["rotulo"] == "Drive"
        d = ec.patch(f"{BASE}/posts/{p['id']}", json={"legenda": None}).json()["data"]
        assert d["legenda"] is None and d["hashtags"] == ["a", "b"]

    @pytest.mark.parametrize("campo", ["etapa_id", "marca_id", "headline_id", "roteiro_id"])
    def test_patch_immutable_fields(self, ec, campo):
        r = ec.patch(f"{BASE}/posts/{_post(ec)['id']}", json={campo: _id()})
        assert r.status_code == 422 and _detail(r)["code"] == "campo_nao_editavel"

    def test_patch_datas(self, ec):
        pid = _post(ec)["id"]
        r = ec.patch(
            f"{BASE}/posts/{pid}",
            json={
                "data_entrega": "2026-11-01T12:00:00+00:00",
                "entrega_concluida": True,
                "lembrete_minutos_antes": 60,
                "recorrencia": "semanal",
                "data_inicio": "2026-10-30T09:00:00+00:00",
            },
        )
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["data_entrega"].startswith("2026-11-01") and d["entrega_concluida"] is True
        row = ec.mock_supabase.from_("cs_posts").select("*").eq("id", pid).execute().data[0]
        assert row["lembrete_minutos_antes"] == 60 and row["recorrencia"] == "semanal"
        assert row["data_inicio"].startswith("2026-10-30")
        # explicit null clears the nullable ones; entrega_concluida (NOT NULL) is not cleared by null
        r = ec.patch(f"{BASE}/posts/{pid}", json={"data_entrega": None, "recorrencia": None, "entrega_concluida": None})
        d = r.json()["data"]
        assert d["data_entrega"] is None and d["entrega_concluida"] is True

    def test_patch_datas_validation(self, ec):
        pid = _post(ec)["id"]
        for bad in ({"recorrencia": "quinzenal"}, {"lembrete_minutos_antes": -1}, {"data_entrega": "ontem"}):
            assert ec.patch(f"{BASE}/posts/{pid}", json=bad).status_code == 422, bad

    def test_hub_members_body_key_is_membro_ids(self, ec):
        pid = _post(ec)["id"]
        m = ec.post(EQUIPE, json={"nome": "Ana"}).json()["data"]
        ec.mock_supabase.from_("cs_equipe").update({"id": str(uuid.UUID(int=7))}).eq("id", m["id"]).execute()
        r = ec.put(f"{BASE}/posts/{pid}/membros", json={"equipe_ids": []})
        assert r.status_code == 422
        r = ec.put(f"{BASE}/posts/{pid}/membros", json={"membro_ids": []})
        assert r.status_code == 200, r.text

    def test_patch_validation(self, ec):
        pid = _post(ec)["id"]
        assert ec.patch(f"{BASE}/posts/{pid}", json={"permalink": "http://evil"}).status_code == 422
        assert ec.patch(f"{BASE}/posts/{pid}", json={"hashtags": ["x"] * 31}).status_code == 422
        assert ec.patch(f"{BASE}/posts/{pid}", json={"links_producao": [{"rotulo": "x", "url": "http://a.com"}]}).status_code == 422
        assert ec.patch(f"{BASE}/posts/{pid}", json={"titulo": "  "}).status_code == 422

    def test_delete_keeps_headline_and_roteiro(self, ec):
        h = _headline(ec)
        ro = _roteiro(ec)
        p = _post(ec)
        assert ec.put(f"{BASE}/posts/{p['id']}/headline", json={"headline_id": h["id"]}).status_code == 200
        assert ec.put(f"{BASE}/posts/{p['id']}/roteiro", json={"roteiro_id": ro["id"]}).status_code in (200, 409)
        assert ec.delete(f"{BASE}/posts/{p['id']}").status_code == 204
        assert ec.get(f"{BASE}/posts/{p['id']}").status_code == 404
        sb = ec.mock_supabase
        assert sb.from_("cs_headlines").select("*").eq("id", h["id"]).execute().data
        assert sb.from_("cs_roteiros").select("*").eq("id", ro["id"]).execute().data


class TestMove:
    def _ready(self, ec):
        h = _headline(ec)
        ro = _roteiro(ec, headline_id=h["id"])
        p = _post(ec, headline_id=h["id"])
        ec.mock_supabase.from_("cs_posts").update({"roteiro_id": ro["id"]}).eq("id", p["id"]).execute()
        return p

    def test_forward_skip_blocked_by_pendencias(self, ec):
        st = _stages(ec)
        p = _post(ec)
        r = _mover(ec, p["id"], st["edicao"]["id"])
        assert r.status_code == 409
        d = _detail(r)
        assert d["code"] == "pendencias" and d["faltando"] == ["headline", "roteiro"] and d["post_id"] == p["id"]

    def test_roteiro_incompleto(self, ec):
        st = _stages(ec)
        h = _headline(ec)
        ro = _roteiro(ec, status="processando")
        p = _post(ec, headline_id=h["id"])
        ec.mock_supabase.from_("cs_posts").update({"roteiro_id": ro["id"]}).eq("id", p["id"]).execute()
        r = _mover(ec, p["id"], st["gravacao"]["id"])
        assert r.status_code == 409 and _detail(r)["faltando"] == ["roteiro_incompleto"]

    def test_forward_skip_allowed_when_ready_and_history_written(self, ec):
        st = _stages(ec)
        p = self._ready(ec)
        r = _mover(ec, p["id"], st["pronto"]["id"])
        assert r.status_code == 200, r.text
        assert r.json()["data"]["etapa_id"] == st["pronto"]["id"] and "headline" in r.json()["data"]
        hist = ec.mock_supabase.from_("pipeline_movimentos").select("*").execute().data
        assert len(hist) == 1
        assert hist[0]["pipeline"] == "esteira" and hist[0]["entidade_id"] == p["id"] and hist[0]["org_id"] == ORG
        assert hist[0]["para_etapa_id"] == st["pronto"]["id"]

    def test_pre_gravacao_moves_need_nothing(self, ec):
        st = _stages(ec)
        p = _post(ec)
        assert _mover(ec, p["id"], st["headline_roteiro"]["id"]).status_code == 200

    def test_backward_needs_motivo(self, ec):
        st = _stages(ec)
        p = self._ready(ec)
        assert _mover(ec, p["id"], st["pronto"]["id"]).status_code == 200
        r = _mover(ec, p["id"], st["edicao"]["id"])
        assert r.status_code == 422 and _detail(r)["code"] == "motivo_obrigatorio"
        r = _mover(ec, p["id"], st["edicao"]["id"], motivo="refazer corte")
        assert r.status_code == 200
        hist = ec.mock_supabase.from_("pipeline_movimentos").select("*").execute().data
        assert hist[-1]["motivo"] == "refazer corte"

    def test_cancelado_needs_motivo_and_stores_it(self, ec):
        st = _stages(ec)
        p = _post(ec)
        r = _mover(ec, p["id"], st["bloqueado_cancelado"]["id"])
        assert r.status_code == 422 and _detail(r)["code"] == "motivo_obrigatorio"
        r = _mover(ec, p["id"], st["bloqueado_cancelado"]["id"], motivo="  sem verba ")
        assert r.status_code == 200 and r.json()["data"]["motivo_bloqueio"] == "sem verba"
        # leaving cancelado needs a motivo and hides the reason from the face
        assert _mover(ec, p["id"], st["ideacao"]["id"]).status_code == 422
        back = _mover(ec, p["id"], st["ideacao"]["id"], motivo="reativado")
        assert back.status_code == 200 and back.json()["data"]["motivo_bloqueio"] is None

    def test_postado_stamps_once_and_keeps_permalink(self, ec):
        st = _stages(ec)
        p = self._ready(ec)
        r = _mover(ec, p["id"], st["postado"]["id"], permalink="https://www.instagram.com/reel/abc/")
        assert r.status_code == 200
        stamp = r.json()["data"]["postado_em"]
        assert stamp
        assert _mover(ec, p["id"], st["pronto"]["id"], motivo="x").status_code == 200
        again = _mover(ec, p["id"], st["postado"]["id"])
        assert again.json()["data"]["postado_em"] == stamp
        assert ec.get(f"{BASE}/posts/{p['id']}").json()["data"]["permalink"] == "https://www.instagram.com/reel/abc/"

    def test_bad_permalink_rejected(self, ec):
        st = _stages(ec)
        r = _mover(ec, _post(ec)["id"], st["postado"]["id"], permalink="http://evil")
        assert r.status_code == 422

    def test_inactive_stage_is_409_and_foreign_stage_404(self, ec):
        st = _stages(ec)
        p = _post(ec)
        assert ec.patch(f"{BASE}/etapas/{st['edicao']['id']}", json={"ativo": False}).status_code == 200
        r = _mover(ec, p["id"], st["edicao"]["id"])
        assert r.status_code == 409 and _detail(r)["code"] == "etapa_invalida"
        assert _mover(ec, p["id"], _id()).status_code == 404

    def test_reorder_inside_column_midpoint_no_history(self, ec):
        a = _post(ec, titulo="A")
        b = _post(ec, titulo="B")
        c = _post(ec, titulo="C")  # column order: C, B, A
        r = _mover(ec, a["id"], a["etapa_id"], novo_indice=1)
        assert r.status_code == 200
        pos = {x["id"]: float(x["kanban_pos"]) for x in
               ec.mock_supabase.from_("cs_posts").select("id,kanban_pos").execute().data}
        assert pos[c["id"]] < pos[a["id"]] < pos[b["id"]]
        assert ec.mock_supabase.from_("pipeline_movimentos").select("*").execute().data == []

    def test_renamed_role_stage_keeps_the_gate(self, ec):
        st = _stages(ec)
        assert ec.patch(f"{BASE}/etapas/{st['gravacao']['id']}", json={"label": "Captação"}).status_code == 200
        r = _mover(ec, _post(ec)["id"], st["gravacao"]["id"])
        assert r.status_code == 409 and _detail(r)["code"] == "pendencias"

    def test_move_returns_full_card(self, ec):
        st = _stages(ec)
        r = _mover(ec, _post(ec)["id"], st["headline_roteiro"]["id"])
        for k in ("id", "marca_nome", "kanban_pos", "headline", "roteiro", "membros", "checklist", "comentarios"):
            assert k in r.json()["data"]


class TestBinding:
    def test_headline_by_id_and_by_text(self, ec):
        h = _headline(ec)
        p = _post(ec)
        r = ec.put(f"{BASE}/posts/{p['id']}/headline", json={"headline_id": h["id"]})
        assert r.status_code == 200 and r.json()["data"]["headline"]["id"] == h["id"]
        r = ec.put(f"{BASE}/posts/{p['id']}/headline", json={"texto": "  Nova headline  "})
        d = r.json()["data"]
        assert d["headline"]["texto"] == "Nova headline" and d["headline"]["id"] != h["id"]
        row = [x for x in ec.mock_supabase.from_("cs_headlines").select("*").execute().data if x["id"] == d["headline"]["id"]][0]
        assert row["lote_id"] is None and row["marca_id"] == MARCA and row["org_id"] == ORG

    def test_headline_body_needs_exactly_one(self, ec):
        pid = _post(ec)["id"]
        assert ec.put(f"{BASE}/posts/{pid}/headline", json={}).status_code == 422
        assert ec.put(f"{BASE}/posts/{pid}/headline", json={"headline_id": _id(), "texto": "x"}).status_code == 422

    def test_duplicate_headline_bind_409_shape(self, ec):
        h = _headline(ec)
        p1 = _post(ec)
        p2 = _post(ec)
        assert ec.put(f"{BASE}/posts/{p1['id']}/headline", json={"headline_id": h["id"]}).status_code == 200
        r = ec.put(f"{BASE}/posts/{p2['id']}/headline", json={"headline_id": h["id"]})
        assert r.status_code == 409
        assert _detail(r) == {"code": "headline_ja_em_post", "post_id": p1["id"], "detail": _detail(r)["detail"]}
        # rebinding the same headline to the same post is idempotent
        assert ec.put(f"{BASE}/posts/{p1['id']}/headline", json={"headline_id": h["id"]}).status_code == 200

    def test_headline_other_marca_422_foreign_org_404(self, ec):
        p = _post(ec)
        other = _headline(ec, marca=MARCA_B)
        r = ec.put(f"{BASE}/posts/{p['id']}/headline", json={"headline_id": other["id"]})
        assert r.status_code == 422 and _detail(r)["code"] == "headline_de_outra_marca"
        foreign = _headline(ec, marca=MARCA_FORA, org=OTHER_ORG)
        assert ec.put(f"{BASE}/posts/{p['id']}/headline", json={"headline_id": foreign["id"]}).status_code == 404

    def test_unbind_headline_keeps_row(self, ec):
        h = _headline(ec)
        p = _post(ec, headline_id=h["id"])
        assert ec.delete(f"{BASE}/posts/{p['id']}/headline").status_code == 204
        assert ec.get(f"{BASE}/posts/{p['id']}").json()["data"]["headline"] is None
        assert ec.mock_supabase.from_("cs_headlines").select("*").eq("id", h["id"]).execute().data

    def test_roteiro_bind_uses_the_rebind_rpc(self, ec):
        ro = _roteiro(ec)
        p = _post(ec)
        ec.mock_supabase._rpcs["cs_rebind_roteiro"] = True
        r = ec.put(f"{BASE}/posts/{p['id']}/roteiro", json={"roteiro_id": ro["id"]})
        assert r.status_code == 200, r.text
        assert ec.mock_supabase.rpc_calls[-1] == (
            "cs_rebind_roteiro",
            {"p_org": ORG, "p_post": p["id"], "p_old": None, "p_new": ro["id"]},
        )

    def test_roteiro_bind_race_is_409(self, ec):
        ro = _roteiro(ec)
        p = _post(ec)
        ec.mock_supabase._rpcs["cs_rebind_roteiro"] = False
        r = ec.put(f"{BASE}/posts/{p['id']}/roteiro", json={"roteiro_id": ro["id"]})
        assert r.status_code == 409 and _detail(r)["code"] == "post_mudou"

    def test_roteiro_other_marca_422_taken_409_foreign_404(self, ec):
        p = _post(ec)
        assert _detail(ec.put(f"{BASE}/posts/{p['id']}/roteiro", json={"roteiro_id": _roteiro(ec, marca=MARCA_B)["id"]}))[
            "code"
        ] == "roteiro_de_outra_marca"
        foreign = _roteiro(ec, marca=MARCA_FORA, org=OTHER_ORG)
        assert ec.put(f"{BASE}/posts/{p['id']}/roteiro", json={"roteiro_id": foreign["id"]}).status_code == 404
        taken = _roteiro(ec)
        holder = _post(ec)
        ec.mock_supabase.from_("cs_posts").update({"roteiro_id": taken["id"]}).eq("id", holder["id"]).execute()
        r = ec.put(f"{BASE}/posts/{p['id']}/roteiro", json={"roteiro_id": taken["id"]})
        assert r.status_code == 409
        assert _detail(r) == {"code": "roteiro_ja_em_post", "post_id": holder["id"], "detail": _detail(r)["detail"]}

    def test_headline_diferente_flag(self, ec):
        h1, h2 = _headline(ec), _headline(ec, texto="outra")
        ro = _roteiro(ec, headline_id=h2["id"])
        p = _post(ec, headline_id=h1["id"])
        ec.mock_supabase.from_("cs_posts").update({"roteiro_id": ro["id"]}).eq("id", p["id"]).execute()
        d = ec.get(f"{BASE}/posts/{p['id']}").json()["data"]
        assert d["roteiro"]["headline_diferente"] is True and d["roteiro"]["status"] == "completo"

    def test_unbind_roteiro_keeps_row(self, ec):
        ro = _roteiro(ec)
        p = _post(ec)
        ec.mock_supabase.from_("cs_posts").update({"roteiro_id": ro["id"]}).eq("id", p["id"]).execute()
        assert ec.delete(f"{BASE}/posts/{p['id']}/roteiro").status_code == 204
        assert ec.get(f"{BASE}/posts/{p['id']}").json()["data"]["roteiro"] is None
        assert ec.mock_supabase.from_("cs_roteiros").select("*").eq("id", ro["id"]).execute().data


class TestEquipe:
    def test_crud_and_shape(self, ec):
        r = ec.post(EQUIPE, json={"nome": " Ana ", "funcao": "Editora", "cor": "success"})
        assert r.status_code == 201, r.text
        m = r.json()["data"]
        assert m == {"id": m["id"], "nome": "Ana", "funcao": "Editora", "cor": "success", "user_id": None, "ativo": True}
        lst = ec.get(EQUIPE).json()
        assert [x["nome"] for x in lst["data"]] == ["Ana"]
        r = ec.patch(f"{EQUIPE}/{m['id']}", json={"funcao": "Chefe", "ativo": False})
        assert r.json()["data"]["funcao"] == "Chefe" and r.json()["data"]["ativo"] is False
        assert ec.get(EQUIPE).json()["data"] == []
        assert len(ec.get(EQUIPE, params={"incluir_inativos": True}).json()["data"]) == 1

    def test_duplicate_name_409(self, ec):
        ec.post(EQUIPE, json={"nome": "Bia"})
        r = ec.post(EQUIPE, json={"nome": "bia"})
        assert r.status_code == 409 and _detail(r)["code"] == "membro_duplicado"
        other = ec.post(EQUIPE, json={"nome": "Caio"}).json()["data"]
        r = ec.patch(f"{EQUIPE}/{other['id']}", json={"nome": "BIA"})
        assert r.status_code == 409

    def test_invalid_cor_and_nome(self, ec):
        assert ec.post(EQUIPE, json={"nome": "X", "cor": "pink"}).status_code == 422
        assert ec.post(EQUIPE, json={"nome": "   "}).status_code == 422

    def test_delete_hard_vs_soft(self, ec):
        free = ec.post(EQUIPE, json={"nome": "Livre"}).json()["data"]
        used = ec.post(EQUIPE, json={"nome": "Usada"}).json()["data"]
        p = _post(ec)
        _ins(ec, "cs_post_membros", org_id=ORG, post_id=p["id"], equipe_id=used["id"])
        assert ec.delete(f"{EQUIPE}/{free['id']}").status_code == 204
        assert ec.delete(f"{EQUIPE}/{used['id']}").status_code == 204
        rows = {r["id"]: r for r in ec.mock_supabase.from_("cs_equipe").select("*").execute().data}
        assert free["id"] not in rows and rows[used["id"]]["ativo"] is False

    def test_foreign_org_member_is_404(self, ec):
        row = _ins(ec, "cs_equipe", org_id=OTHER_ORG, nome="Alheio", ativo=True)
        assert ec.patch(f"{EQUIPE}/{row['id']}", json={"ativo": False}).status_code == 404
        assert ec.delete(f"{EQUIPE}/{row['id']}").status_code == 404
        assert ec.get(EQUIPE).json()["data"] == []


class TestTimelineGatherer:
    def test_movimento_kind_is_bound_and_renders_stage_labels(self, ec):
        from app.modules.media_creation.esteira_config import CS_POST_HUB
        from app.modules.media_creation.esteira_timeline import gather_movimentos_esteira

        assert CS_POST_HUB.timeline_gatherers["movimento"] is gather_movimentos_esteira
        assert "nota" in CS_POST_HUB.timeline_gatherers  # seed kinds survive
        st = _stages(ec)
        p = _post(ec)
        assert _mover(ec, p["id"], st["headline_roteiro"]["id"]).status_code == 200
        # `created_at` is a DB default the mock does not apply
        ec.mock_supabase.from_("pipeline_movimentos").update({"created_at": "2026-10-10T12:00:00+00:00"}).eq(
            "entidade_id", p["id"]
        ).execute()
        r = ec.get(f"{BASE}/posts/{p['id']}/timeline")
        assert r.status_code == 200, r.text
        items = [i for i in r.json()["items"] if i["kind"] == "movimento"]
        assert len(items) == 1
        assert items[0]["de_etapa"] == "Ideação" and items[0]["para_etapa"] == "Headline + roteiro"
        assert items[0]["ocorrido_em"]
