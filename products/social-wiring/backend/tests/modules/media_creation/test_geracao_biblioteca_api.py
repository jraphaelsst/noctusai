"""Biblioteca + Minha Biblioteca endpoints 7-19 (geracao-contract.md section 4.3), PLATFORM scope (estruturas-contract 4.2).

The library (profiles, videos) is platform-wide: reads are tier ``org`` (any member), profile writes are tier ``platform``
(``require_platform_admin``: strict 403 for a member). A brand's own selection (``/referencias*``) stays org-scoped."""
from __future__ import annotations

import ast
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anyio
import pytest

from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.integrations.apify import FakeActorRunner
from noctusai_lib.integrations.media.safe_fetch import FakeSafeFetcher, FetchResult
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.dependencies import get_platform_admin_check
from app.modules.media_creation.services import biblioteca_service as svc
from app.modules.media_creation.routers import biblioteca as router_mod
from app.modules.media_creation.routers.biblioteca import (
    get_biblioteca_fetcher,
    get_biblioteca_jobs,
    get_biblioteca_runner_factory,
    get_biblioteca_storage,
    get_ingestao_org,
    get_ingestao_switch,
)

BASE = "/api/media-creation/biblioteca"
ORG = "test-org-123"
MARCA = str(uuid.uuid4())
MARCA_B = str(uuid.uuid4())
FOREIGN_MARCA = str(uuid.uuid4())
P1 = str(uuid.uuid4())
P2 = str(uuid.uuid4())
FOREIGN_PERFIL = str(uuid.uuid4())
V1 = str(uuid.uuid4())
V2 = str(uuid.uuid4())
FOREIGN_VIRAL = str(uuid.uuid4())
ACC = str(uuid.uuid4())
NOW = datetime.now(timezone.utc)


class State:
    def __init__(self, client):
        self.client = client
        self.storage = FakeStorageBackend()
        self.jobs = FakeJobRepository()
        self.switch_on = True
        self.admin = False
        app = client._tc.app
        app.dependency_overrides[get_biblioteca_storage] = lambda: self.storage
        app.dependency_overrides[get_biblioteca_jobs] = lambda: self.jobs
        app.dependency_overrides[get_ingestao_switch] = lambda: (lambda: self.switch_on)
        app.dependency_overrides[get_platform_admin_check] = lambda: (lambda uid: self.admin)
        # the platform ingestion org (= the org that holds the Meta account); por-link / thumbnails are overridden per test
        app.dependency_overrides[get_ingestao_org] = lambda: (lambda: ORG)
        app.dependency_overrides[get_biblioteca_runner_factory] = lambda: (lambda org: self.runner)
        app.dependency_overrides[get_biblioteca_fetcher] = lambda: FakeSafeFetcher()
        self.runner = FakeActorRunner()

    @property
    def db(self):
        return self.client.mock_supabase

    def queued(self, type_=None):
        return [j for j in self.jobs._jobs.values() if type_ is None or j.type == type_]


@pytest.fixture
def bib(client):
    st = State(client)
    db = st.db
    db.rpc = _PurgeRpc(db)  # the 351 RPC doubles (profile create / purge / minimise / review)
    for mid, org in ((MARCA, ORG), (MARCA_B, ORG), (FOREIGN_MARCA, "other-org")):
        db.from_("marcas").insert({"id": mid, "org_id": org, "name": f"M {mid[:4]}"}).execute()
    db.from_("integration_accounts").insert({
        "id": ACC, "org_id": ORG, "provider": "meta", "status": "validated", "is_default": True,
        "account_label": "Conta Meta", "metadata": {"channel_title": "eu"},
    }).execute()
    db.from_("integration_accounts").insert({
        "id": str(uuid.uuid4()), "org_id": ORG, "provider": "instagram", "status": "validated",
        "account_label": "IG login", "metadata": {},
    }).execute()
    # platform rows (org_id NULL). FOREIGN_PERFIL is a LEGACY per-org row (written before 351): visible like any other
    for pid, handle, org, status in ((P1, "alvo1", None, "ativo"), (P2, "alvo2", None, "ativo"),
                                     (FOREIGN_PERFIL, "legado", "other-org", "ativo")):
        db.from_("cs_perfis_monitorados").insert({
            "id": pid, "org_id": org, "rede": "instagram", "handle": handle, "nome": handle.title(),
            "status": status, "metrica_base": "engajamento", "mediana_metrica": 100, "created_by": "u", "monitorar": True,
            "erro_mensagem": "Configure a chave do Apify" if pid == P2 else None,
        }).execute()
    db.from_("cs_virais").insert({
        "id": V1, "org_id": None, "perfil_id": P1, "codigo": 1, "ig_media_id": "a", "permalink": "https://i/1",
        "publicado_em": NOW.isoformat(), "likes": 400, "comments": 10, "score_viral": 4.1, "e_viral": True,
        "thumbnail_path": f"platform/{P1}/{V1}.jpg", "gancho": "Meu gancho de dor", "caption": "legenda longa",
        "transcricao_texto": "fala completa", "transcricao_status": "concluida", "classificacao_status": "concluida",
        "nicho_ids": [1], "profissao_ids": [2], "formato_ids": [8], "gatilho": "misterio",
        "blueprint": "SEGREDO-BLUEPRINT", "duracao_s": 31,
    }).execute()
    db.from_("cs_virais").insert({
        "id": V2, "org_id": None, "perfil_id": P2, "codigo": 2, "ig_media_id": "b", "permalink": "https://i/2",
        "publicado_em": (NOW - timedelta(days=3)).isoformat(), "likes": 50, "score_viral": 1.0, "e_viral": False,
        "transcricao_status": "nao_aplicavel", "classificacao_status": "pendente",
    }).execute()
    db.from_("cs_virais").insert({
        "id": FOREIGN_VIRAL, "org_id": "other-org", "perfil_id": FOREIGN_PERFIL, "codigo": 3, "ig_media_id": "c",
        "e_viral": True, "transcricao_status": "nao_aplicavel", "classificacao_status": "concluida",
        "gancho": "segredo de outro",
    }).execute()
    return st


def _refs(st):
    return st.db.from_("cs_biblioteca_referencias").select("*").execute().data


def _add_ref(st, marca, **kw):
    row = {"id": str(uuid.uuid4()), "org_id": ORG, "marca_id": marca, "auto_atualizar": True, **kw}
    st.db.from_("cs_biblioteca_referencias").insert(row).execute()
    return row


READ_ROUTES = [
    ("get", f"/virais?marca_id={MARCA}", {}),
    ("get", f"/virais/{V1}?marca_id={MARCA}", {}),
    ("get", "/perfis", {}),
    ("get", f"/perfis/{P1}", {}),
    ("get", f"/referencias?marca_id={MARCA}", {}),
    ("post", "/referencias", {"json": {"marca_id": MARCA, "modo": "perfil", "perfil_ids": [P1], "auto_atualizar": True}}),
    ("patch", f"/referencias/{uuid.uuid4()}", {"json": {"auto_atualizar": False}}),
    ("delete", f"/referencias/{uuid.uuid4()}", {}),
]
ADMIN_ROUTES = [
    ("get", "/perfis/verificar?handle=x", {}),
    ("post", "/perfis", {"json": {"handle": "x"}}),
    ("post", "/virais/por-link", {"json": {"url": "https://www.instagram.com/reel/ABCDE12345/"}}),
    ("post", f"/perfis/{P1}/sincronizar", {}),
    ("patch", f"/perfis/{P1}", {"json": {"status": "pausado"}}),
    ("delete", f"/perfis/{P1}", {}),
    ("get", "/contas-descoberta", {}),
    ("get", "/admin/optouts", {}),
    ("post", "/admin/optouts", {"json": {"handle": "x", "origem": "dpo"}}),
    ("delete", f"/admin/optouts/{uuid.uuid4()}", {}),
]


class TestAuth:
    @pytest.mark.parametrize("method,path,kw", READ_ROUTES + ADMIN_ROUTES)
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (path, r.status_code, r.text)

    @pytest.mark.parametrize("method,path,kw", ADMIN_ROUTES)
    def test_an_org_member_who_is_not_a_platform_admin_is_403_on_every_write(self, bib, client, method, path, kw):
        r = getattr(client, method)(BASE + path, **kw)
        assert r.status_code == 403, (method, path, r.status_code, r.text)
        # the real wire shape of require_platform_admin's plain-string detail (the app's error envelope)
        assert r.json()["error"]["code"] == "FORBIDDEN"

    @pytest.mark.parametrize("method,path,kw", READ_ROUTES)
    def test_reads_and_the_brand_selection_are_open_to_any_member(self, bib, client, method, path, kw):
        r = getattr(client, method)(BASE + path, **kw)
        assert r.status_code not in (401, 403), (method, path, r.status_code, r.text)

    def test_the_admin_router_is_platform_tier_and_hidden_from_the_public_schema(self):
        assert router_mod.router_admin.access_tier == "platform" and router_mod.router.access_tier == "org"
        assert all(not r.include_in_schema for r in router_mod.router_admin.routes)
        # a read can never inherit a write gate: no route of the org router is a profile write / add-by-link / opt-out
        writes = {("POST", "/api/media-creation/biblioteca/perfis"), ("DELETE", "/api/media-creation/biblioteca/perfis/{perfil_id}"),
                  ("POST", "/api/media-creation/biblioteca/virais/por-link")}
        org_routes = {(m, r.path) for r in router_mod.router.routes for m in getattr(r, "methods", ())}
        assert not (writes & org_routes)

    def test_the_external_work_routes_carry_the_ai_rate_limit(self):
        tree = ast.parse(Path(router_mod.__file__).read_text())
        limited = set()
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)):
            for d in fn.decorator_list:
                if isinstance(d, ast.Call) and ast.unparse(d.func) == "limiter.limit" and ast.unparse(d.args[0]) == "DEFAULT_AI_RL":
                    limited.add(fn.name)
        assert {"criar_perfil", "sincronizar_perfil", "adicionar_viral_por_link"} <= limited


class TestListVirais:
    def test_card_shape_signed_thumbnail_and_switch_flag(self, bib, client):
        r = client.get(f"{BASE}/virais?marca_id={MARCA}")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["page"] == 1 and d["ingestao_ativa"] is True and d["filtro_automatico"] is False
        card = next(i for i in d["items"] if i["id"] == V1)
        assert card["perfil"] == {"id": P1, "handle": "alvo1"} and card["codigo"] == 1
        assert card["thumbnail_url"].startswith(f"fake://storage/sw-biblioteca/platform/{P1}/{V1}.jpg")
        assert card["trecho"] == "Meu gancho de dor" and card["score_viral"] == 4.1 and card["duracao_s"] == 31.0
        assert set(card) == {"id", "codigo", "perfil", "thumbnail_url", "permalink", "publicado_em", "views",
                             "likes", "comments", "duracao_s", "score_viral", "e_viral", "trecho"}

    def test_the_library_is_platform_wide_every_org_sees_the_same_videos(self, bib, client):
        ids = {i["id"] for i in client.get(f"{BASE}/virais?marca_id={MARCA}&somente_virais=false").json()["data"]["items"]}
        assert {V1, V2, FOREIGN_VIRAL} <= ids  # a legacy per-org row is just a library row now

    def test_foreign_marca_is_404(self, bib, client):
        assert client.get(f"{BASE}/virais?marca_id={FOREIGN_MARCA}").status_code == 404
        assert client.get(f"{BASE}/virais?marca_id={uuid.uuid4()}").status_code == 404

    def test_switch_off_is_reported(self, bib, client):
        bib.switch_on = False
        assert client.get(f"{BASE}/virais?marca_id={MARCA}").json()["data"]["ingestao_ativa"] is False

    def test_repeated_query_params_are_accepted(self, bib, client):
        r = client.get(f"{BASE}/virais?marca_id={MARCA}&nichos=1&nichos=2&profissoes=3&profissoes=4")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["filtro_automatico"] is False  # explicit filters win over the automatic one

    def test_automatic_filter_follows_the_marca_profile(self, bib, client):
        bib.db.from_("cs_marca_perfil").insert({"marca_id": MARCA, "org_id": ORG, "nichos": [1], "profissoes": []}).execute()
        assert client.get(f"{BASE}/virais?marca_id={MARCA}").json()["data"]["filtro_automatico"] is True
        assert client.get(f"{BASE}/virais?marca_id={MARCA}&ver_todos=true").json()["data"]["filtro_automatico"] is False
        assert client.get(f"{BASE}/virais?marca_id={MARCA}&perfil_id={P1}").json()["data"]["filtro_automatico"] is False
        assert client.get(f"{BASE}/virais?marca_id={MARCA}&codigo=1").json()["data"]["filtro_automatico"] is False
        # a marca with an empty profile has nothing to filter by
        assert client.get(f"{BASE}/virais?marca_id={MARCA_B}").json()["data"]["filtro_automatico"] is False

    def test_pool_with_an_empty_allow_list_is_empty(self, bib, client):
        d = client.get(f"{BASE}/virais?marca_id={MARCA}&pool=minha_biblioteca").json()["data"]
        assert d["items"] == [] and d["total"] == 0 and d["ingestao_ativa"] is True

    def test_pool_with_references_serves_the_allow_list_route(self, bib, client):
        _add_ref(bib, MARCA, modo="perfil", perfil_id=P1)
        r = client.get(f"{BASE}/virais?marca_id={MARCA}&pool=minha_biblioteca")
        assert r.status_code == 200 and r.json()["data"]["filtro_automatico"] is False

    @pytest.mark.parametrize("qs", [
        "ordem=aleatoria", "buscar_em=tudo", "page=0", "data_de=ontem", "views_min=-1", "pool=outra",
    ])
    def test_bad_params_are_422(self, bib, client, qs):
        assert client.get(f"{BASE}/virais?marca_id={MARCA}&{qs}").status_code == 422

    def test_transcript_search_returns_a_snippet_around_the_match(self, bib, client):
        d = client.get(f"{BASE}/virais?marca_id={MARCA}&q=completa&buscar_em=transcricao").json()["data"]
        card = next(i for i in d["items"] if i["id"] == V1)
        assert "completa" in card["trecho"]


class TestDetalhe:
    def test_detail_hides_the_blueprint_by_default(self, bib, client):
        d = client.get(f"{BASE}/virais/{V1}?marca_id={MARCA}").json()["data"]
        assert "blueprint" not in d
        assert d["gancho"] == "Meu gancho de dor" and d["transcricao_texto"] == "fala completa"
        assert d["nichos"][0]["id"] == 1 and d["profissoes"][0]["id"] == 2 and d["formatos"][0]["id"] == 8
        assert d["gatilho"] == "misterio" and d["estrutura_utilizavel"] is True
        assert d["transcricao_status"] == "concluida" and d["caption"] == "legenda longa"
        assert "origem_inclusao" not in d and d["estruturas"] == []  # how a video entered the library is an admin fact (F9)

    def test_detail_lists_the_estruturas_of_the_video_active_only_for_a_member(self, bib, client):
        for eid, codigo, status in (("e1", 5, "ativa"), ("e2", 6, "rascunho")):
            bib.db.from_("cs_estruturas").insert({"id": eid, "codigo": codigo, "perfil_id": P1, "viral_id": V1, "status": status,
                                                  "formula_headline": "Como [x] faz " + "y" * 200}).execute()
        d = client.get(f"{BASE}/virais/{V1}?marca_id={MARCA}").json()["data"]
        assert [e["id"] for e in d["estruturas"]] == ["e1"]
        ref = d["estruturas"][0]
        assert set(ref) == {"id", "codigo", "perfil", "formula_trecho"} and ref["perfil"]["handle"] == "alvo1"
        assert len(ref["formula_trecho"]) <= 120
        bib.admin = True
        assert [e["id"] for e in client.get(f"{BASE}/virais/{V1}?marca_id={MARCA}").json()["data"]["estruturas"]] == ["e1", "e2"]

    def test_debug_blueprint_is_platform_admin_only(self, bib, client):
        assert "blueprint" not in client.get(f"{BASE}/virais/{V1}?marca_id={MARCA}&debug=1").json()["data"]
        bib.admin = True
        assert client.get(f"{BASE}/virais/{V1}?marca_id={MARCA}&debug=1").json()["data"]["blueprint"] == "SEGREDO-BLUEPRINT"
        assert "blueprint" not in client.get(f"{BASE}/virais/{V1}?marca_id={MARCA}").json()["data"]

    def test_unknown_ids_and_foreign_marca_are_404(self, bib, client):
        assert client.get(f"{BASE}/virais/{FOREIGN_VIRAL}?marca_id={MARCA}").status_code == 200  # library-wide
        assert client.get(f"{BASE}/virais/{uuid.uuid4()}?marca_id={MARCA}").status_code == 404
        assert client.get(f"{BASE}/virais/{V1}?marca_id={FOREIGN_MARCA}").status_code == 404
        assert client.get(f"{BASE}/virais/{V1}").status_code == 422


def _perfil_row(st, pid):
    return next(r for r in st.db.from_("cs_perfis_monitorados").select("*").execute().data if r["id"] == pid)


def _eventos(st, tipo=None):
    rows = st.db.from_("cs_perfil_eventos").select("*").execute().data
    return [r for r in rows if tipo is None or r["tipo"] == tipo]


class FakeApiError(Exception):
    """A PostgREST ``APIError`` double (the attributes the service reads)."""

    def __init__(self, message: str, details: str = "", code: str = "P0001"):
        super().__init__({"message": message, "details": details, "code": code})
        self.message, self.details, self.code = message, details, code


class _Exec:
    count = None

    def __init__(self, data=None, exc=None):
        self.data, self._exc = data, exc

    def execute(self):
        if self._exc:
            raise self._exc
        return self


class _PurgeRpc:
    """A double of the 351 library RPCs (their real behaviour is proven on PGlite by the 351 probes): same arguments, same
    refusals, same cascades over the mock tables. ``calls`` = the ``cs_perfil_purgar`` calls; the other RPCs log into
    ``criar_calls`` / ``minimizar_calls`` / ``revisao_calls``. NO event row carries a handle (owner decision 2026-11-15)."""

    def __init__(self, db):
        self.db, self.calls, self.criar_calls, self.minimizar_calls, self.revisao_calls, self.rascunhos_calls = db, [], [], [], [], []
        self.revisao_resposta = {"sinalizadas": 0, "liberadas": 0}

    def _perfil(self, pid):
        return next((r for r in self.db.from_("cs_perfis_monitorados").select("*").execute().data if r["id"] == pid), None)

    def __call__(self, name, params=None):
        if name == "cs_perfil_plataforma_criar":
            return self._criar(dict(params))
        if name == "cs_perfil_minimizar":
            return self._minimizar(dict(params))
        if name == "cs_estruturas_rascunhos_expirar":
            self.rascunhos_calls.append(dict(params))
            corte = (datetime.now(timezone.utc) - timedelta(days=params["p_dias"])).isoformat()
            vel = [e for e in self.db.from_("cs_estruturas").select("*").execute().data
                   if e.get("status") == "rascunho" and e.get("origem") == "viral_auto"
                   and (e.get("updated_at") or e.get("created_at") or "9") < corte]
            for e in vel:
                self.db.from_("cs_estrutura_eventos").insert({"estrutura_id": e["id"], "perfil_id": e["perfil_id"],
                                                              "tipo": "rascunho_expirado", "ator_tipo": "sistema_retencao"}).execute()
                self.db.from_("cs_estruturas").delete().eq("id", e["id"]).execute()
            return _Exec(data={"expiradas": len(vel)})
        if name == "cs_estruturas_revisao_desuso":
            self.revisao_calls.append(dict(params))
            return _Exec(data=dict(self.revisao_resposta))
        assert name == "cs_perfil_purgar", name
        p = dict(params)
        self.calls.append(p)
        pid = p["p_perfil"]
        ests = [e for e in self.db.from_("cs_estruturas").select("*").execute().data if e["perfil_id"] == pid]
        if ests and not p["p_apagar_estruturas"]:
            return _Exec(exc=FakeApiError("perfil_com_estruturas", str(len(ests))))
        perfil = next((r for r in self.db.from_("cs_perfis_monitorados").select("*").execute().data if r["id"] == pid), None)
        if perfil is None:
            return _Exec(data={"perfil": False, "estruturas": 0, "virais": 0})
        for e in ests:
            self.db.from_("cs_estrutura_eventos").insert({"estrutura_id": e["id"], "perfil_id": pid, "tipo": "excluida",
                                                          "ator_tipo": "admin" if p["p_ator_tipo"] == "admin" else "sistema_retencao"}).execute()
            self.db.from_("cs_estruturas").delete().eq("id", e["id"]).execute()
        self.db.from_("cs_perfil_eventos").insert({"perfil_id": pid, "tipo": p["p_tipo"],
                                                   "ator_id": p["p_ator"], "ator_tipo": p["p_ator_tipo"]}).execute()
        # the FK cascades of the real table: videos, and every brand selection of the profile or of one of its videos
        virais = [v["id"] for v in self.db.from_("cs_virais").select("id").eq("perfil_id", pid).execute().data]
        for vid in virais:
            self.db.from_("cs_biblioteca_referencias").delete().eq("viral_id", vid).execute()
        self.db.from_("cs_virais").delete().eq("perfil_id", pid).execute()
        self.db.from_("cs_biblioteca_referencias").delete().eq("perfil_id", pid).execute()
        self.db.from_("cs_perfis_monitorados").delete().eq("id", pid).execute()
        return _Exec(data={"perfil": True, "estruturas": len(ests), "virais": len(virais)})

    def _criar(self, p):
        self.criar_calls.append(p)
        h = p["p_handle"]
        if any(o["handle"] == h for o in self.db.from_("cs_biblioteca_optouts").select("*").execute().data):
            return _Exec(exc=FakeApiError("perfil_optout"))
        ja = next((r for r in self.db.from_("cs_perfis_monitorados").select("*").execute().data
                   if r.get("org_id") is None and r["handle"] == h), None)
        if ja is not None:
            return _Exec(data={"id": ja["id"], "handle": h, "criado": False})
        pid = str(uuid.uuid4())
        self.db.from_("cs_perfis_monitorados").insert({
            "id": pid, "org_id": None, "rede": "instagram", "handle": h, "nome": p["p_nome"], "status": p["p_status"],
            "monitorar": p["p_monitorar"], "conta_descoberta_id": p["p_conta"], "erro_codigo": p["p_erro_codigo"],
            "erro_mensagem": p["p_erro_mensagem"], "created_by": p["p_ator"], "metrica_base": "engajamento",
        }).execute()
        for tipo in ("criado",) + (("importado",) if p["p_origem"] == "import" else ()):
            self.db.from_("cs_perfil_eventos").insert({"perfil_id": pid, "tipo": tipo, "ator_id": p["p_ator"],
                                                       "ator_tipo": p["p_ator_tipo"], "importacao_id": p["p_importacao"]}).execute()
        return _Exec(data={"id": pid, "handle": h, "criado": True})

    def _minimizar(self, p):
        self.minimizar_calls.append(p)
        perfil = self._perfil(p["p_perfil"])
        if perfil is None or (not perfil.get("foto_path") and perfil.get("seguidores") is None):
            return _Exec(data={"minimizado": False, "foto_path": None})
        foto = perfil.get("foto_path")  # read BEFORE the update (the mock hands out live row dicts)
        self.db.from_("cs_perfis_monitorados").update({"foto_path": None, "seguidores": None}).eq("id", p["p_perfil"]).execute()
        self.db.from_("cs_perfil_eventos").insert({"perfil_id": p["p_perfil"], "tipo": "minimizado", "ator_id": p["p_ator"],
                                                   "ator_tipo": p["p_ator_tipo"]}).execute()
        return _Exec(data={"minimizado": True, "foto_path": foto})


class TestPerfisLeitura:
    """GET /perfis (paged, library-wide) and GET /perfis/{id}: tier org."""

    def test_list_is_paged_library_wide_with_counts_and_no_org_filter(self, bib, client):
        d = client.get(f"{BASE}/perfis").json()["data"]
        assert set(d) == {"items", "total"} and d["total"] == 3
        assert [p["handle"] for p in d["items"]] == ["alvo1", "alvo2", "legado"]
        p1 = d["items"][0]
        assert (p1["virais"], p1["posts"]) == (1, 1) and p1["ingestao_ativa"] is True and p1["optout_contato"]
        # a client org sees handle + name ONLY (owner decision 2026-11-15; security review F9)
        assert set(p1) == {"id", "handle", "nome", "virais", "posts", "ingestao_ativa", "optout_contato"}
        assert "selecionado_pela_marca" not in p1  # only when marca_id is given
        assert [p["handle"] for p in client.get(f"{BASE}/perfis?q=ALVO2").json()["data"]["items"]] == ["alvo2"]

    def test_paging_and_the_page_cap(self, bib, client):
        d = client.get(f"{BASE}/perfis?limit=1&offset=1").json()["data"]
        assert d["total"] == 3 and [p["handle"] for p in d["items"]] == ["alvo2"]
        assert client.get(f"{BASE}/perfis?limit=51").status_code == 422
        assert client.get(f"{BASE}/perfis?limit=0").status_code == 422
        assert client.get(f"{BASE}/perfis?offset=-1").status_code == 422

    def test_marca_id_adds_the_brands_own_selection(self, bib, client):
        _add_ref(bib, MARCA, modo="perfil", perfil_id=P1)
        items = client.get(f"{BASE}/perfis?marca_id={MARCA}").json()["data"]["items"]
        assert {p["handle"]: p["selecionado_pela_marca"] for p in items} == {"alvo1": True, "alvo2": False, "legado": False}
        assert client.get(f"{BASE}/perfis?marca_id={FOREIGN_MARCA}").status_code == 404

    def test_a_member_never_sees_an_ingestion_error_an_admin_does(self, bib, client):
        item = lambda: next(p for p in client.get(f"{BASE}/perfis").json()["data"]["items"] if p["id"] == P2)
        assert "erro_mensagem" not in item()
        bib.admin = True
        assert item()["erro_mensagem"] == "Configure a chave do Apify"

    def test_get_one_has_estruturas_total_active_only_for_a_member(self, bib, client):
        for eid, status in (("e1", "ativa"), ("e2", "rascunho"), ("e3", "arquivada")):
            bib.db.from_("cs_estruturas").insert({"id": eid, "perfil_id": P1, "status": status}).execute()
        assert client.get(f"{BASE}/perfis/{P1}").json()["data"]["estruturas_total"] == 1
        bib.admin = True
        assert client.get(f"{BASE}/perfis/{P1}").json()["data"]["estruturas_total"] == 3
        assert client.get(f"{BASE}/perfis/{uuid.uuid4()}").status_code == 404

    def test_the_perfil_payload_carries_no_internal_columns(self, bib, client):
        body = client.get(f"{BASE}/perfis/{P1}").text
        for forbidden in ("created_by", "conta_descoberta_id", "org_id", "nome_editado", "ig_user_id"):
            assert forbidden not in body


    def test_a_member_response_carries_handle_and_name_only_serialise_and_grep(self, bib, client):
        """Owner decision 2026-11-15 + security review F9: no photo, follower count, status, monitoring flag, sync metrics
        or inclusion origin reaches a client org, on ANY route that embeds a creator."""
        bib.db.from_("cs_perfis_monitorados").update({"foto_path": f"platform/{P1}/foto.jpg", "seguidores": 98765}).eq("id", P1).execute()
        _add_ref(bib, MARCA, modo="perfil", perfil_id=P1)
        _add_ref(bib, MARCA, modo="video", viral_id=V1)
        bodies = [
            client.get(f"{BASE}/perfis").text, client.get(f"{BASE}/perfis/{P1}").text,
            client.get(f"{BASE}/perfis?marca_id={MARCA}").text, client.get(f"{BASE}/referencias?marca_id={MARCA}").text,
            client.get(f"{BASE}/virais/{V1}?marca_id={MARCA}").text, client.get(f"{BASE}/virais?marca_id={MARCA}").text,
        ]
        for body in bodies:
            for forbidden in ("foto_url", "foto_path", "seguidores", "98765", "monitorar", "metrica_base", "mediana_metrica",
                              "ultima_sync_em", "origem_inclusao", "erro_mensagem", "\"status\""):
                assert forbidden not in body, forbidden
            assert "alvo1" in body  # the handle IS what a member gets
        bib.admin = True  # an admin keeps everything
        d = client.get(f"{BASE}/perfis/{P1}").json()["data"]
        assert d["seguidores"] == 98765 and d["monitorar"] is True and d["status"] == "ativo" and "foto_url" in d
        assert client.get(f"{BASE}/virais/{V1}?marca_id={MARCA}").json()["data"]["origem_inclusao"] == "sync"


class TestPerfisAdmin:
    """The platform-admin profile writes: every one writes a content-free cs_perfil_eventos row."""

    @pytest.fixture(autouse=True)
    def _admin(self, bib):
        bib.admin = True
        bib.client.mock_supabase.rpc = _PurgeRpc(bib.db)

    def test_contas_descoberta_lists_the_ingestion_orgs_meta_connections(self, bib, client):
        d = client.get(f"{BASE}/contas-descoberta").json()["data"]
        assert d == [{"id": ACC, "nome": "Conta Meta", "ig_username": "eu"}]

    def test_verificar_states(self, bib, client):
        g = lambda h, extra="": client.get(f"{BASE}/perfis/verificar?handle={h}{extra}")
        assert g("novo").json()["data"] == {"status": "disponivel"}
        assert g("alvo1").json()["data"]["status"] == "ja_monitorado"
        _add_ref(bib, MARCA, modo="perfil", perfil_id=P1)
        assert g("alvo1", f"&marca_id={MARCA}").json()["data"]["status"] == "na_minha_biblioteca"
        assert g("alvo1", f"&marca_id={MARCA_B}").json()["data"]["status"] == "ja_monitorado"
        assert g("https%3A%2F%2Finstagram.com%2F%40alvo1").json()["data"]["status"] == "ja_monitorado"
        assert g("p%2Fabc").status_code == 422
        bib.db.from_("integration_accounts").delete().eq("provider", "meta").execute()
        assert g("novo").json()["data"] == {"status": "sem_conta_descoberta"}

    def test_criar_writes_a_platform_row_a_sync_job_and_the_criado_event(self, bib, client):
        r = client.post(f"{BASE}/perfis", json={"handle": "@Novo.Perfil"})
        assert r.status_code == 201, r.text
        d = r.json()["data"]
        assert d["handle"] == "novo.perfil" and d["status"] == "aguardando" and d["monitorar"] is True
        assert [j.payload["perfil_id"] for j in bib.queued("biblioteca.sync_perfil")] == [d["id"]]
        row = _perfil_row(bib, d["id"])
        assert row["org_id"] is None and row["conta_descoberta_id"] == ACC and row["monitorar"] is True
        assert [(e["tipo"], e["ator_tipo"], e["perfil_id"]) for e in _eventos(bib, "criado")] == [("criado", "admin", d["id"])]
        assert all("handle" not in e for e in _eventos(bib))  # the event row keeps no handle (owner decision 2026-11-15)
        assert _refs(bib) == []  # a library profile is not a brand's selection

    def test_criar_library_only_is_never_synced(self, bib, client):
        d = client.post(f"{BASE}/perfis", json={"handle": "so.biblioteca", "monitorar": False}).json()["data"]
        assert d["monitorar"] is False and d["status"] == "ativo"
        assert bib.queued() == []

    def test_marca_id_is_accepted_and_ignored_for_one_release(self, bib, client):
        r = client.post(f"{BASE}/perfis", json={"marca_id": MARCA, "handle": "legado.cliente"})
        assert r.status_code == 201 and _refs(bib) == []

    def test_duplicate_handle_is_409_perfil_ja_existe(self, bib, client):
        r = client.post(f"{BASE}/perfis", json={"handle": "alvo1"})
        assert r.status_code == 409 and r.json()["code"] == "perfil_ja_existe" and r.json()["perfil_id"] == P1
        assert bib.queued() == [] and _eventos(bib) == []

    def test_opted_out_handle_is_409_perfil_optout(self, bib, client):
        bib.db.from_("cs_biblioteca_optouts").insert({"id": str(uuid.uuid4()), "handle": "pediu.saida", "origem": "email"}).execute()
        r = client.post(f"{BASE}/perfis", json={"handle": "pediu.saida"})
        assert r.status_code == 409 and r.json()["code"] == "perfil_optout"
        assert client.get(f"{BASE}/perfis/verificar?handle=pediu.saida").status_code == 409

    def test_platform_cap_is_409_limite_perfis(self, bib, client):
        from app.config import settings

        for i in range(settings.biblioteca_max_perfis_plataforma - 3):
            bib.db.from_("cs_perfis_monitorados").insert(
                {"id": str(uuid.uuid4()), "org_id": None, "rede": "instagram", "handle": f"fill{i}", "status": "ativo"}).execute()
        r = client.post(f"{BASE}/perfis", json={"handle": "excedente"})
        assert r.status_code == 409 and r.json()["code"] == "limite_perfis"

    def test_without_a_meta_account_a_monitored_profile_is_sem_conta_and_nothing_is_queued(self, bib, client):
        bib.db.from_("integration_accounts").delete().eq("provider", "meta").execute()
        d = client.post(f"{BASE}/perfis", json={"handle": "novo"}).json()["data"]
        assert d["status"] == "sem_conta" and "Meta" in d["erro_mensagem"]
        assert bib.queued() == []

    @pytest.mark.parametrize("handle", ["", "p/abc", "instagram.com/reel/xyz", "a b", "x" * 31])
    def test_invalid_handles_are_422(self, bib, client, handle):
        assert client.post(f"{BASE}/perfis", json={"handle": handle}).status_code == 422

    def test_unknown_fields_are_422(self, bib, client):
        assert client.post(f"{BASE}/perfis", json={"handle": "x", "org_id": "o"}).status_code == 422

    def test_foreign_account_is_422(self, bib, client):
        r = client.post(f"{BASE}/perfis", json={"handle": "x", "conta_descoberta_id": str(uuid.uuid4())})
        assert r.status_code == 422

    def test_sincronizar_enqueues_once_per_hour_and_records_the_event(self, bib, client):
        r = client.post(f"{BASE}/perfis/{P1}/sincronizar")
        assert r.status_code == 202, r.text
        assert r.json()["data"]["enfileirado"] is True and r.json()["data"]["ingestao_ativa"] is True
        assert len(bib.queued("biblioteca.sync_perfil")) == 1
        assert [e["perfil_id"] for e in _eventos(bib, "sincronizacao_solicitada")] == [P1]
        again = client.post(f"{BASE}/perfis/{P1}/sincronizar")
        assert again.status_code == 429 and int(again.headers["Retry-After"]) > 0
        assert len(bib.queued("biblioteca.sync_perfil")) == 1 and len(_eventos(bib, "sincronizacao_solicitada")) == 1

    def test_sincronizar_has_a_daily_cap_per_admin_org(self, bib, client):
        from app.config import settings

        hoje = datetime.now(timezone.utc).strftime("%Y%m%d")
        for i in range(settings.biblioteca_sync_manual_dia_org):
            bib.db.from_("jobs").insert({
                "id": str(uuid.uuid4()), "type": "biblioteca.sync_perfil", "status": "completed",
                "dedupe_key": f"sync:{P2}:{hoje}:manual:{i:02d}:{ORG}",
            }).execute()
        r = client.post(f"{BASE}/perfis/{P1}/sincronizar")
        assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
        assert bib.queued("biblioteca.sync_perfil") == []

    def test_sincronizar_refused_right_after_a_sync(self, bib, client):
        bib.db.from_("cs_perfis_monitorados").update({"ultima_sync_em": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()}).eq("id", P2).execute()
        r = client.post(f"{BASE}/perfis/{P2}/sincronizar")
        assert r.status_code == 429 and int(r.headers["Retry-After"]) <= 3600
        assert bib.queued() == []

    def test_sincronizar_after_an_hour_and_for_error_states_resets_them(self, bib, client):
        bib.db.from_("cs_perfis_monitorados").update(
            {"ultima_sync_em": (NOW - timedelta(hours=2)).isoformat(), "status": "erro", "erro_mensagem": "x"}
        ).eq("id", P2).execute()
        assert client.post(f"{BASE}/perfis/{P2}/sincronizar").status_code == 202
        row = _perfil_row(bib, P2)
        assert row["status"] == "aguardando" and row["erro_mensagem"] is None

    def test_sincronizar_paused_is_409_and_unknown_is_404(self, bib, client):
        bib.db.from_("cs_perfis_monitorados").update({"status": "pausado"}).eq("id", P2).execute()
        assert client.post(f"{BASE}/perfis/{P2}/sincronizar").status_code == 409
        assert client.post(f"{BASE}/perfis/{uuid.uuid4()}/sincronizar").status_code == 404

    def test_patch_pause_reactivate_and_their_events(self, bib, client):
        d = client.patch(f"{BASE}/perfis/{P1}", json={"status": "pausado"}).json()["data"]
        assert d["status"] == "pausado" and bib.queued() == []
        d = client.patch(f"{BASE}/perfis/{P1}", json={"status": "ativo"}).json()["data"]
        assert d["status"] == "aguardando" and len(bib.queued("biblioteca.sync_perfil")) == 1
        assert [e["tipo"] for e in _eventos(bib)] == ["pausado", "retomado"]

    def test_patch_monitorar_and_nome_override_are_recorded(self, bib, client):
        d = client.patch(f"{BASE}/perfis/{P1}", json={"monitorar": False, "nome": "  Nome Novo "}).json()["data"]
        assert d["monitorar"] is False and d["nome"] == "Nome Novo"
        row = _perfil_row(bib, P1)
        assert row["monitorar"] is False and row["nome_editado"] is True
        assert sorted(e["tipo"] for e in _eventos(bib)) == ["editado", "monitorar_desligado"]
        client.patch(f"{BASE}/perfis/{P1}", json={"monitorar": True})
        assert "monitorar_ligado" in {e["tipo"] for e in _eventos(bib)}
        n = len(_eventos(bib))
        client.patch(f"{BASE}/perfis/{P1}", json={"monitorar": True})  # no change: no event
        assert len(_eventos(bib)) == n

    def test_patch_account_validation_and_404(self, bib, client):
        assert client.patch(f"{BASE}/perfis/{P1}", json={"conta_descoberta_id": str(uuid.uuid4())}).status_code == 422
        assert client.patch(f"{BASE}/perfis/{P1}", json={"conta_descoberta_id": ACC}).status_code == 200
        assert client.patch(f"{BASE}/perfis/{uuid.uuid4()}", json={"status": "pausado"}).status_code == 404
        assert client.patch(f"{BASE}/perfis/{P1}", json={"status": "erro"}).status_code == 422

    def test_delete_without_estruturas_removes_blobs_transcripts_and_the_profile(self, bib, client):
        anyio.run(lambda: bib.storage.put(bucket="sw-biblioteca", key=f"platform/{P1}/{V1}.jpg", data=b"x"))
        anyio.run(lambda: bib.storage.put(bucket="sw-biblioteca", key=f"platform/{P1}/foto.jpg", data=b"x"))
        bib.db.from_("cs_perfis_monitorados").update({"foto_path": f"platform/{P1}/foto.jpg"}).eq("id", P1).execute()
        bib.db.from_("transcricoes").insert({"id": "t1", "org_id": ORG, "contexto_tipo": "biblioteca_viral", "contexto_ref": V1,
                                             "status": "processando", "storage_path": "o/u/t1.mp3", "texto": "fala"}).execute()
        bib.db.from_("transcricoes").insert({"id": "t2", "org_id": ORG, "contexto_tipo": "cerebro_resposta", "contexto_ref": V1, "status": "concluida"}).execute()
        anyio.run(lambda: bib.storage.put(bucket="sw-transcricoes", key="o/u/t1.mp3", data=b"audio"))
        assert client.delete(f"{BASE}/perfis/{P1}").status_code == 204
        assert anyio.run(lambda: bib.storage.list_keys(bucket="sw-biblioteca")) == []
        ids = {r["id"] for r in bib.db.from_("transcricoes").select("*").execute().data}
        assert ids == {"t2"}  # the library's transcript went, even a job still `processando` (F2); another context's stays
        assert anyio.run(lambda: bib.storage.list_keys(bucket="sw-transcricoes")) == []  # ... and its recording with it
        assert P1 not in {r["id"] for r in bib.db.from_("cs_perfis_monitorados").select("*").execute().data}
        assert [e["tipo"] for e in _eventos(bib)] == ["excluido"] and all("handle" not in e for e in _eventos(bib))

    def test_delete_with_estruturas_is_409_with_the_count_and_destroys_nothing(self, bib, client):
        anyio.run(lambda: bib.storage.put(bucket="sw-biblioteca", key=f"platform/{P1}/{V1}.jpg", data=b"x"))
        for eid, status in (("e1", "ativa"), ("e2", "arquivada")):
            bib.db.from_("cs_estruturas").insert({"id": eid, "perfil_id": P1, "status": status}).execute()
        r = client.delete(f"{BASE}/perfis/{P1}")
        assert r.status_code == 409
        assert r.json()["code"] == "perfil_com_estruturas" and r.json()["estruturas_total"] == 2
        assert P1 in {x["id"] for x in bib.db.from_("cs_perfis_monitorados").select("*").execute().data}
        assert anyio.run(lambda: bib.storage.list_keys(bucket="sw-biblioteca")) != []  # the refusal came BEFORE any erasure
        assert bib.client.mock_supabase.rpc.calls == []

    def test_delete_with_apagar_estruturas_cascades_and_leaves_content_free_events(self, bib, client):
        bib.db.from_("cs_estruturas").insert({"id": "e1", "perfil_id": P1, "status": "ativa", "formula_headline": "SEGREDO"}).execute()
        assert client.delete(f"{BASE}/perfis/{P1}?apagar_estruturas=true").status_code == 204
        assert bib.db.from_("cs_estruturas").select("*").execute().data == []
        ev = bib.db.from_("cs_estrutura_eventos").select("*").execute().data
        assert [(e["estrutura_id"], e["tipo"]) for e in ev] == [("e1", "excluida")]
        assert "SEGREDO" not in str(ev) + str(_eventos(bib))  # events carry no content
        assert bib.client.mock_supabase.rpc.calls[0]["p_apagar_estruturas"] is True

    def test_delete_unknown_is_404(self, bib, client):
        assert client.delete(f"{BASE}/perfis/{uuid.uuid4()}").status_code == 404


class TestReferencias:
    def test_create_profiles_idempotent(self, bib, client):
        body = {"marca_id": MARCA, "modo": "perfil", "perfil_ids": [P1, P2], "auto_atualizar": False}
        r = client.post(f"{BASE}/referencias", json=body)
        assert r.status_code == 201 and r.json()["data"] == {"criadas": 2, "ja_existentes": 0}
        assert all(r["auto_atualizar"] is False for r in _refs(bib))
        assert client.post(f"{BASE}/referencias", json=body).json()["data"] == {"criadas": 0, "ja_existentes": 2}

    def test_create_videos(self, bib, client):
        body = {"marca_id": MARCA, "modo": "video", "viral_ids": [V1, V2]}
        assert client.post(f"{BASE}/referencias", json=body).json()["data"] == {"criadas": 2, "ja_existentes": 0}
        assert client.post(f"{BASE}/referencias", json=body).json()["data"] == {"criadas": 0, "ja_existentes": 2}

    def test_unknown_ids_and_foreign_marca_are_404_and_nothing_is_created(self, bib, client):
        post = lambda b: client.post(f"{BASE}/referencias", json=b)
        ghost = str(uuid.uuid4())
        assert post({"marca_id": MARCA, "modo": "perfil", "perfil_ids": [P1, ghost], "auto_atualizar": True}).status_code == 404
        assert post({"marca_id": MARCA, "modo": "video", "viral_ids": [V1, ghost]}).status_code == 404
        assert post({"marca_id": FOREIGN_MARCA, "modo": "video", "viral_ids": [V1]}).status_code == 404
        assert _refs(bib) == []

    def test_a_brand_selects_from_the_platform_library_including_a_legacy_row(self, bib, client):
        body = {"marca_id": MARCA, "modo": "perfil", "perfil_ids": [P1, FOREIGN_PERFIL], "auto_atualizar": True}
        assert client.post(f"{BASE}/referencias", json=body).json()["data"] == {"criadas": 2, "ja_existentes": 0}
        assert {r["org_id"] for r in _refs(bib)} == {ORG}  # the SELECTION is the caller's org's

    def test_the_selected_profiles_per_brand_are_capped_by_biblioteca_max_perfis_org(self, bib, client):
        from app.config import settings

        for i in range(settings.biblioteca_max_perfis_org):
            pid = str(uuid.uuid4())
            bib.db.from_("cs_perfis_monitorados").insert({"id": pid, "org_id": None, "rede": "instagram", "handle": f"sel{i}", "status": "ativo"}).execute()
            _add_ref(bib, MARCA, modo="perfil", perfil_id=pid)
        r = client.post(f"{BASE}/referencias", json={"marca_id": MARCA, "modo": "perfil", "perfil_ids": [P1], "auto_atualizar": True})
        assert r.status_code == 409 and "limite" in r.json()["error"]["message"]
        # another brand of the same org starts from zero
        assert client.post(f"{BASE}/referencias", json={"marca_id": MARCA_B, "modo": "perfil", "perfil_ids": [P1], "auto_atualizar": True}).status_code == 201

    @pytest.mark.parametrize("body", [
        {"modo": "perfil", "perfil_ids": [], "auto_atualizar": True},
        {"modo": "video", "viral_ids": []},
        {"modo": "outro", "perfil_ids": [P1]},
        {"modo": "perfil", "viral_ids": [V1]},
    ])
    def test_bad_bodies_are_422(self, bib, client, body):
        assert client.post(f"{BASE}/referencias", json={"marca_id": MARCA, **body}).status_code == 422

    def test_request_caps(self, bib, client):
        many = [str(uuid.uuid4()) for _ in range(21)]
        assert client.post(f"{BASE}/referencias", json={"marca_id": MARCA, "modo": "perfil", "perfil_ids": many, "auto_atualizar": True}).status_code == 422
        many = [str(uuid.uuid4()) for _ in range(51)]
        assert client.post(f"{BASE}/referencias", json={"marca_id": MARCA, "modo": "video", "viral_ids": many}).status_code == 422

    def test_marca_allow_list_ceiling_is_409(self, bib, client):
        from app.modules.media_creation.schemas.biblioteca import MAX_REFERENCIAS_MARCA

        for _ in range(MAX_REFERENCIAS_MARCA):
            _add_ref(bib, MARCA, modo="video", viral_id=str(uuid.uuid4()))
        r = client.post(f"{BASE}/referencias", json={"marca_id": MARCA, "modo": "video", "viral_ids": [V1]})
        assert r.status_code == 409

    def test_list_shapes_and_filtering(self, bib, client):
        _add_ref(bib, MARCA, modo="perfil", perfil_id=P1, posts_ate="2026-05-01")
        _add_ref(bib, MARCA, modo="video", viral_id=V1, auto_atualizar=False)
        _add_ref(bib, MARCA_B, modo="perfil", perfil_id=P2)
        d = client.get(f"{BASE}/referencias?marca_id={MARCA}").json()["data"]
        assert {x["modo"] for x in d} == {"perfil", "video"} and len(d) == 2
        perfil = next(x for x in d if x["modo"] == "perfil")
        assert perfil["perfil"]["handle"] == "alvo1" and perfil["viral"] is None and perfil["posts_ate"] == "2026-05-01"
        video = next(x for x in d if x["modo"] == "video")
        assert video["viral"]["id"] == V1 and video["perfil"] is None and video["auto_atualizar"] is False
        # the repo lists by id (keyset pagination), so the order of the two refs is the order of two random uuids
        assert sorted(x["modo"] for x in client.get(f"{BASE}/referencias?marca_id={MARCA}&q=alvo1").json()["data"]) == ["perfil", "video"]
        assert client.get(f"{BASE}/referencias?marca_id={MARCA}&q=zzz").json()["data"] == []
        assert client.get(f"{BASE}/referencias?marca_id={FOREIGN_MARCA}").status_code == 404

    def test_patch(self, bib, client):
        ref = _add_ref(bib, MARCA, modo="perfil", perfil_id=P1)
        vref = _add_ref(bib, MARCA, modo="video", viral_id=V1, auto_atualizar=False)
        d = client.patch(f"{BASE}/referencias/{ref['id']}", json={"auto_atualizar": False, "posts_ate": "2026-06-30"}).json()["data"]
        assert d["auto_atualizar"] is False and d["posts_ate"] == "2026-06-30"
        assert client.patch(f"{BASE}/referencias/{vref['id']}", json={"posts_ate": "2026-06-30"}).status_code == 422
        assert client.patch(f"{BASE}/referencias/{ref['id']}", json={"posts_ate": "2026-13-45"}).status_code == 422
        assert client.patch(f"{BASE}/referencias/{ref['id']}", json={"posts_ate": "30/06/2026"}).status_code == 422
        assert client.patch(f"{BASE}/referencias/{uuid.uuid4()}", json={"auto_atualizar": True}).status_code == 404

    def test_delete_and_cross_org(self, bib, client):
        ref = _add_ref(bib, MARCA, modo="perfil", perfil_id=P1)
        foreign = {"id": str(uuid.uuid4()), "org_id": "other-org", "marca_id": FOREIGN_MARCA, "modo": "perfil",
                   "perfil_id": FOREIGN_PERFIL, "auto_atualizar": True}
        bib.db.from_("cs_biblioteca_referencias").insert(foreign).execute()
        assert client.delete(f"{BASE}/referencias/{foreign['id']}").status_code == 404
        assert client.patch(f"{BASE}/referencias/{foreign['id']}", json={"auto_atualizar": False}).status_code == 404
        assert client.delete(f"{BASE}/referencias/{ref['id']}").status_code == 204
        assert [r["id"] for r in _refs(bib)] == [foreign["id"]]


# ── admin add-by-link: POST /virais/por-link ────────────────────────────────

ACTOR = "apify/instagram-scraper"
CDN = "https://scontent.cdninstagram.com"
POST_URL = "https://www.instagram.com/reel/CODE12345/"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64


def _apify_item(shortcode="CODE12345", owner="criador.novo", reel=True, **over):
    item = {
        "id": "9001", "shortCode": shortcode, "url": f"https://www.instagram.com/reel/{shortcode}/",
        "type": "Video" if reel else "Image", "productType": "clips" if reel else None, "caption": "Meu gancho",
        "timestamp": "2026-10-01T12:00:00.000Z", "likesCount": 10, "commentsCount": 2,
        "videoPlayCount": 500, "videoDuration": 20.5, "ownerUsername": owner,
        "displayUrl": f"{CDN}/t.jpg", **({"videoUrl": f"{CDN}/v.mp4"} if reel else {}),
    }
    item.update(over)
    return item


class TestPorLink:
    @pytest.fixture(autouse=True)
    def _apify(self, bib, monkeypatch):
        monkeypatch.setenv("BIBLIOTECA_FONTE", "apify")  # the source switch is read through its env leg
        bib.admin = True
        bib.runner = FakeActorRunner({ACTOR: [_apify_item()]})
        bib.client._tc.app.dependency_overrides[get_biblioteca_fetcher] = lambda: FakeSafeFetcher({
            f"{CDN}/t.jpg": FetchResult(f"{CDN}/t.jpg", 200, "image/jpeg", JPEG)})
        bib.client._tc.app.dependency_overrides[get_biblioteca_runner_factory] = lambda: (lambda org: bib.runner)

    def _post(self, client, url=POST_URL):
        return client.post(f"{BASE}/virais/por-link", json={"url": url})

    def _virais(self, bib):
        return bib.db.from_("cs_virais").select("*").execute().data

    def test_creates_the_profile_library_only_the_video_and_the_same_analysis_jobs_as_a_synced_one(self, bib, client):
        r = self._post(client)
        assert r.status_code == 201, r.text
        d = r.json()["data"]
        assert d["perfil_criado"] is True and d["ja_existia"] is False
        assert d["viral"]["perfil"]["handle"] == "criador.novo" and d["viral"]["permalink"].endswith("CODE12345/")
        perfil = next(p for p in bib.db.from_("cs_perfis_monitorados").select("*").execute().data if p["handle"] == "criador.novo")
        assert perfil["org_id"] is None and perfil["monitorar"] is False and perfil["created_by"]
        v = next(x for x in self._virais(bib) if x.get("ig_shortcode") == "CODE12345")
        assert v["org_id"] is None and v["origem_inclusao"] == "link_manual" and v["incluido_por"]
        assert v["ig_media_id"] == "9001" and v["views"] == 500 and v["e_viral"] is False  # below any viral threshold
        assert v["video_url"] == f"{CDN}/v.mp4" and v["media_product_type"] == "REELS" and v["duracao_s"] == 20.5
        assert v["thumbnail_path"].startswith(f"platform/{perfil['id']}/9001")  # mirrored under the platform prefix
        assert v["transcricao_status"] == "pendente" and v["classificacao_status"] == "pendente"
        # analysed regardless of the viral threshold: the reel goes to transcription (then classify), like a synced viral reel
        t = bib.queued("biblioteca.transcrever")
        assert [j.payload for j in t] == [{"viral_id": v["id"], "media_url": f"{CDN}/v.mp4"}]
        assert bib.queued("biblioteca.sync_perfil") == []  # library-only: never scraped
        assert [(e["tipo"], e["ator_tipo"]) for e in _eventos(bib)] == [("criado", "admin"), ("video_adicionado_por_link", "admin")]
        assert _eventos(bib, "video_adicionado_por_link")[0]["viral_id"] == v["id"]

    def test_the_stored_permalink_is_the_canonical_one_never_what_the_scraper_returned(self, bib, client):
        """F10: the scraper's own ``url`` is untrusted; the stored permalink is re-composed from the validated shortcode."""
        bib.runner = FakeActorRunner({ACTOR: [_apify_item(url="javascript:alert(1)")]})
        assert self._post(client, "https://instagram.com/reels/CODE12345/?igsh=abc").status_code == 201
        v = next(x for x in self._virais(bib) if x.get("ig_shortcode") == "CODE12345")
        assert v["permalink"] == "https://www.instagram.com/reel/CODE12345/"
        assert v["permalink"].startswith(svc.PERMALINK_PREFIXO)

    def test_the_creation_door_maps_the_rpcs_opt_out_refusal_to_a_409(self, bib):
        """F3: the registry is read INSIDE ``cs_perfil_plataforma_criar`` (proven on PGlite by probe
        ``sw351_perfil_plataforma_criar_recusa_optout``); the service maps that refusal, whatever its own pre-check saw."""
        bib.db.from_("cs_biblioteca_optouts").insert({"id": str(uuid.uuid4()), "handle": "criador.novo", "origem": "dpo"}).execute()
        with pytest.raises(svc.BibliotecaError) as exc:
            svc.criar_perfil_plataforma(bib.db, handle="criador.novo", ator_id="u")
        assert exc.value.status == 409 and exc.value.code == "perfil_optout"
        assert [p for p in bib.db.from_("cs_perfis_monitorados").select("*").execute().data if p["handle"] == "criador.novo"] == []

    def test_a_post_that_is_not_a_video_goes_straight_to_classification(self, bib, client):
        bib.runner = FakeActorRunner({ACTOR: [_apify_item(reel=False)]})
        assert self._post(client).status_code == 201
        v = self._virais(bib)[-1]
        assert v["transcricao_status"] == "nao_aplicavel"
        assert [j.payload["viral_id"] for j in bib.queued("biblioteca.classificar")] == [v["id"]]
        assert bib.queued("biblioteca.transcrever") == []

    def test_the_actor_is_asked_for_the_recomposed_url_never_the_pasted_string(self, bib, client):
        pasted = "https://www.instagram.com/criador.novo/reels/CODE12345/?utm_source=ig&igsh=SEGREDO#frag"
        assert self._post(client, pasted).status_code == 201
        call = bib.runner.calls[0]
        assert call["actor_id"] == ACTOR and call["max_items"] == 1
        assert call["input"]["directUrls"] == [POST_URL]  # /reels/ -> /reel/, query + fragment gone
        assert "SEGREDO" not in str(call)

    def test_the_second_paste_is_200_ja_existia_with_no_new_job_no_fetch_no_event(self, bib, client):
        assert self._post(client).status_code == 201
        jobs_before, n_calls, n_events = len(bib.queued()), len(bib.runner.calls), len(_eventos(bib))
        r = self._post(client, "https://instagram.com/p/CODE12345/")  # same shortcode, other path shape
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["ja_existia"] is True and d["perfil_criado"] is False and d["viral"]["id"]
        assert len(bib.queued()) == jobs_before and len(bib.runner.calls) == n_calls and len(_eventos(bib)) == n_events
        assert len(self._virais(bib)) == 4  # V1, V2, FOREIGN_VIRAL + the ONE added
        assert sum(1 for v in self._virais(bib) if v.get("ig_shortcode") == "CODE12345") == 1

    def test_a_synced_video_without_a_shortcode_is_found_by_profile_and_media_id_and_backfilled(self, bib, client):
        bib.runner = FakeActorRunner({ACTOR: [_apify_item(shortcode="CODE12345", owner="alvo2", id="b")]})
        r = self._post(client)
        assert r.status_code == 200 and r.json()["data"]["ja_existia"] is True
        assert next(v for v in self._virais(bib) if v["id"] == V2)["ig_shortcode"] == "CODE12345"
        assert bib.queued() == []

    def test_an_existing_profile_is_reused_not_recreated(self, bib, client):
        bib.runner = FakeActorRunner({ACTOR: [_apify_item(owner="Alvo1")]})
        d = self._post(client).json()["data"]
        assert d["perfil_criado"] is False and d["viral"]["perfil"]["id"] == P1
        assert _eventos(bib, "criado") == [] and len(_eventos(bib, "video_adicionado_por_link")) == 1
        assert _perfil_row(bib, P1)["monitorar"] is True  # untouched

    def test_an_opted_out_owner_is_409_perfil_optout_and_nothing_is_stored(self, bib, client):
        bib.db.from_("cs_biblioteca_optouts").insert({"id": str(uuid.uuid4()), "handle": "criador.novo", "origem": "dpo"}).execute()
        r = self._post(client)
        assert r.status_code == 409 and r.json()["code"] == "perfil_optout"
        assert [v for v in self._virais(bib) if v.get("ig_shortcode")] == [] and bib.queued() == []
        assert all(p["handle"] != "criador.novo" for p in bib.db.from_("cs_perfis_monitorados").select("*").execute().data)

    @pytest.mark.parametrize("url", [
        "", "x", "http://www.instagram.com/p/ABCDE12345/", "https://evil.example/p/ABCDE12345/",
        "https://instagram.com.evil.example/p/ABCDE12345/", "https://www.instagram.com@evil.example/p/ABCDE12345/",
        "https://www.instagram.com:8080/p/ABCDE12345/", "https://www.instagram.com/alvo1/", "https://www.instagram.com/stories/alvo1/123/",
        "https://www.instagram.com/p/", "https://www.instagram.com/p/ab/", "https://www.instagram.com/p/ABCDE12345/extra/more/",
        "https://169.254.169.254/p/ABCDE12345/", "file:///etc/passwd", "javascript:alert(1)", "https://www.instagram.com/p/A B C D E/",
    ])
    def test_host_allowlist_and_shape_only_instagram_post_links_pass(self, bib, client, url):
        r = self._post(client, url)
        assert r.status_code == 422, (url, r.status_code, r.text)
        assert bib.runner.calls == []  # nothing was fetched

    def test_bad_link_through_the_service_is_coded_link_invalido(self, bib):
        from app.modules.media_creation.schemas.biblioteca import LinkInvalido, extrair_shortcode

        with pytest.raises(LinkInvalido):
            extrair_shortcode("https://evil.example/p/ABCDE12345/")
        assert extrair_shortcode("https://www.instagram.com/tv/AbC_d-12345/") == ("AbC_d-12345", "https://www.instagram.com/tv/AbC_d-12345/")
        assert extrair_shortcode("https://instagram.com/criador/reel/ABCDE12345/")[1] == "https://www.instagram.com/reel/ABCDE12345/"

    def test_post_not_found_is_404_coded(self, bib, client):
        bib.runner = FakeActorRunner({ACTOR: [{"error": "not_found", "errorDescription": "x"}]})
        r = self._post(client)
        assert r.status_code == 404 and r.json()["code"] == "post_nao_encontrado"
        # an item answering for ANOTHER post is not accepted either
        bib.runner = FakeActorRunner({ACTOR: [_apify_item(shortcode="OUTRO99999")]})
        assert self._post(client).status_code == 404

    def test_a_source_that_cannot_fetch_a_post_is_409_fonte_nao_suporta_link(self, bib, client, monkeypatch):
        monkeypatch.setenv("BIBLIOTECA_FONTE", "business_discovery")
        r = self._post(client)
        assert r.status_code == 409 and r.json()["code"] == "fonte_nao_suporta_link"
        assert bib.runner.calls == []

    def test_no_ingestion_org_is_503_and_visible_never_silent(self, bib, client):
        bib.client._tc.app.dependency_overrides[get_ingestao_org] = lambda: (lambda: None)
        r = self._post(client)
        assert r.status_code == 503 and r.json()["code"] == "ingestao_sem_org_plataforma"
        assert bib.runner.calls == []

    def test_the_kill_switch_off_is_503_before_any_spend(self, bib, client):
        bib.switch_on = False
        r = self._post(client)
        assert r.status_code == 503 and r.json()["code"] == "ingestao_desligada" and bib.runner.calls == []

    def test_the_daily_apify_cap_is_429_before_the_fetch(self, bib, client):
        from app.config import settings

        bib.db.from_("cs_apify_uso").insert({"org_id": ORG, "resultados": settings.biblioteca_apify_resultados_dia_org,
                                             "criado_em": datetime.now(timezone.utc).isoformat()}).execute()
        r = self._post(client)
        assert r.status_code == 429 and r.json()["code"] == "sem_orcamento" and int(r.headers["Retry-After"]) > 0
        assert bib.runner.calls == []

    def test_the_fetch_is_booked_on_the_ingestion_org(self, bib, client):
        assert self._post(client).status_code == 201
        uso = bib.db.from_("cs_apify_uso").select("*").execute().data
        assert len(uso) == 1 and uso[0]["org_id"] == ORG and uso[0]["resultados"] == 1

    @pytest.mark.parametrize("err,status,code", [
        ("not_configured", 503, "sem_credencial"), ("rate", 429, "fonte_ocupada"), ("failed", 503, "fonte_indisponivel"),
    ])
    def test_source_errors_are_coded_and_leak_no_vendor_text(self, bib, client, err, status, code):
        from noctusai_lib.integrations.apify import ApifyNotConfigured, ApifyRateLimited, ApifyRunFailed

        exc = {"not_configured": ApifyNotConfigured("token SEGREDO-TOKEN"), "rate": ApifyRateLimited(retry_after_s=30),
               "failed": ApifyRunFailed("apify body SEGREDO-CORPO")}[err]
        bib.runner = FakeActorRunner(raises=exc)
        r = self._post(client)
        assert r.status_code == status and r.json()["code"] == code
        assert "SEGREDO" not in r.text

    def test_the_platform_profile_cap_applies_to_a_new_profile(self, bib, client):
        from app.config import settings

        for i in range(settings.biblioteca_max_perfis_plataforma - 3):
            bib.db.from_("cs_perfis_monitorados").insert(
                {"id": str(uuid.uuid4()), "org_id": None, "rede": "instagram", "handle": f"fill{i}", "status": "ativo"}).execute()
        r = self._post(client)
        assert r.status_code == 409 and r.json()["code"] == "limite_perfis"
        assert [v for v in self._virais(bib) if v.get("ig_shortcode")] == []

    def test_a_broken_thumbnail_never_fails_the_add(self, bib, client):
        bib.client._tc.app.dependency_overrides[get_biblioteca_fetcher] = lambda: FakeSafeFetcher()  # nothing allowed
        r = self._post(client)
        assert r.status_code == 201 and r.json()["data"]["viral"]["thumbnail_url"] is None

    def test_an_added_video_is_listed_and_a_member_can_open_it(self, bib, client):
        d = self._post(client).json()["data"]
        bib.admin = False
        items = client.get(f"{BASE}/virais?marca_id={MARCA}").json()["data"]["items"]
        assert d["viral"]["id"] in {i["id"] for i in items}  # (the viral-or-manual `or` is match-all on the mock; its predicate is pinned in the pure tests)
        row = next(v for v in self._virais(bib) if v["id"] == d["viral"]["id"])  # (the mock mints non-UUID ids: no GET by id here)
        assert row["origem_inclusao"] == "link_manual"
