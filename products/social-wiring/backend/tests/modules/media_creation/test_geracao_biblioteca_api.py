"""Biblioteca + Minha Biblioteca endpoints 7-19 (geracao-contract.md section 4.3)."""
from __future__ import annotations

import ast
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import anyio
import pytest

from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.dependencies import get_platform_admin_check
from app.modules.media_creation.routers import biblioteca as router_mod
from app.modules.media_creation.routers.biblioteca import (
    get_biblioteca_jobs,
    get_biblioteca_storage,
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

    @property
    def db(self):
        return self.client.mock_supabase

    def queued(self, type_=None):
        return [j for j in self.jobs._jobs.values() if type_ is None or j.type == type_]


@pytest.fixture
def bib(client):
    st = State(client)
    db = st.db
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
    for pid, handle, org, status in ((P1, "alvo1", ORG, "ativo"), (P2, "alvo2", ORG, "ativo"),
                                     (FOREIGN_PERFIL, "alheio", "other-org", "ativo")):
        db.from_("cs_perfis_monitorados").insert({
            "id": pid, "org_id": org, "rede": "instagram", "handle": handle, "nome": handle.title(),
            "status": status, "metrica_base": "engajamento", "mediana_metrica": 100, "created_by": "u",
        }).execute()
    db.from_("cs_virais").insert({
        "id": V1, "org_id": ORG, "perfil_id": P1, "codigo": 1, "ig_media_id": "a", "permalink": "https://i/1",
        "publicado_em": NOW.isoformat(), "likes": 400, "comments": 10, "score_viral": 4.1, "e_viral": True,
        "thumbnail_path": f"{ORG}/{P1}/{V1}.jpg", "gancho": "Meu gancho de dor", "caption": "legenda longa",
        "transcricao_texto": "fala completa", "transcricao_status": "concluida", "classificacao_status": "concluida",
        "nicho_ids": [1], "profissao_ids": [2], "formato_ids": [8], "gatilho": "misterio",
        "blueprint": "SEGREDO-BLUEPRINT", "duracao_s": 31,
    }).execute()
    db.from_("cs_virais").insert({
        "id": V2, "org_id": ORG, "perfil_id": P2, "codigo": 2, "ig_media_id": "b", "permalink": "https://i/2",
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


class TestAuth:
    @pytest.mark.parametrize("method,path,kw", [
        ("get", f"/virais?marca_id={MARCA}", {}),
        ("get", f"/virais/{V1}?marca_id={MARCA}", {}),
        ("get", "/perfis", {}),
        ("get", "/perfis/verificar?handle=x", {}),
        ("post", "/perfis", {"json": {"marca_id": MARCA, "handle": "x"}}),
        ("post", f"/perfis/{P1}/sincronizar", {}),
        ("patch", f"/perfis/{P1}", {"json": {"status": "pausado"}}),
        ("delete", f"/perfis/{P1}", {}),
        ("get", "/contas-descoberta", {}),
        ("get", f"/referencias?marca_id={MARCA}", {}),
        ("post", "/referencias", {"json": {"marca_id": MARCA, "modo": "perfil", "perfil_ids": [P1], "auto_atualizar": True}}),
        ("patch", f"/referencias/{uuid.uuid4()}", {"json": {"auto_atualizar": False}}),
        ("delete", f"/referencias/{uuid.uuid4()}", {}),
    ])
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (path, r.status_code, r.text)

    def test_the_two_external_work_routes_carry_the_ai_rate_limit(self):
        tree = ast.parse(Path(router_mod.__file__).read_text())
        limited = set()
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)):
            for d in fn.decorator_list:
                if isinstance(d, ast.Call) and ast.unparse(d.func) == "limiter.limit" and ast.unparse(d.args[0]) == "DEFAULT_AI_RL":
                    limited.add(fn.name)
        assert {"solicitar_perfil", "sincronizar_perfil"} <= limited


class TestListVirais:
    def test_card_shape_signed_thumbnail_and_switch_flag(self, bib, client):
        r = client.get(f"{BASE}/virais?marca_id={MARCA}")
        assert r.status_code == 200, r.text
        d = r.json()["data"]
        assert d["page"] == 1 and d["ingestao_ativa"] is True and d["filtro_automatico"] is False
        card = next(i for i in d["items"] if i["id"] == V1)
        assert card["perfil"] == {"id": P1, "handle": "alvo1"} and card["codigo"] == 1
        assert card["thumbnail_url"].startswith(f"fake://storage/sw-biblioteca/{ORG}/{P1}/{V1}.jpg")
        assert card["trecho"] == "Meu gancho de dor" and card["score_viral"] == 4.1 and card["duracao_s"] == 31.0
        assert set(card) == {"id", "codigo", "perfil", "thumbnail_url", "permalink", "publicado_em", "views",
                             "likes", "comments", "duracao_s", "score_viral", "e_viral", "trecho"}

    def test_org_isolation(self, bib, client):
        ids = {i["id"] for i in client.get(f"{BASE}/virais?marca_id={MARCA}&somente_virais=false").json()["data"]["items"]}
        assert FOREIGN_VIRAL not in ids and V1 in ids

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

    def test_debug_blueprint_is_platform_admin_only(self, bib, client):
        assert "blueprint" not in client.get(f"{BASE}/virais/{V1}?marca_id={MARCA}&debug=1").json()["data"]
        bib.admin = True
        assert client.get(f"{BASE}/virais/{V1}?marca_id={MARCA}&debug=1").json()["data"]["blueprint"] == "SEGREDO-BLUEPRINT"
        assert "blueprint" not in client.get(f"{BASE}/virais/{V1}?marca_id={MARCA}").json()["data"]

    def test_foreign_ids_are_404(self, bib, client):
        assert client.get(f"{BASE}/virais/{FOREIGN_VIRAL}?marca_id={MARCA}").status_code == 404
        assert client.get(f"{BASE}/virais/{uuid.uuid4()}?marca_id={MARCA}").status_code == 404
        assert client.get(f"{BASE}/virais/{V1}?marca_id={FOREIGN_MARCA}").status_code == 404
        assert client.get(f"{BASE}/virais/{V1}").status_code == 422


class TestPerfis:
    def test_list_has_counts_and_switch_flag_and_no_foreign_rows(self, bib, client):
        d = client.get(f"{BASE}/perfis").json()["data"]
        assert [p["handle"] for p in d] == ["alvo1", "alvo2"]
        p1 = d[0]
        assert (p1["virais"], p1["posts"]) == (1, 1) and p1["ingestao_ativa"] is True
        assert p1["metrica_base"] == "engajamento" and p1["mediana_metrica"] == 100.0
        assert [p["handle"] for p in client.get(f"{BASE}/perfis?q=ALVO2").json()["data"]] == ["alvo2"]

    def test_contas_descoberta_lists_only_meta_connections(self, bib, client):
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
        assert g("alheio").json()["data"]["status"] == "disponivel"  # another org's profile is invisible
        assert g("p%2Fabc").status_code == 422
        bib.db.from_("integration_accounts").delete().eq("provider", "meta").execute()
        assert g("novo").json()["data"] == {"status": "sem_conta_descoberta"}

    def test_solicitar_creates_profile_reference_and_sync_job(self, bib, client):
        r = client.post(f"{BASE}/perfis", json={"marca_id": MARCA, "handle": "@Novo.Perfil"})
        assert r.status_code == 201, r.text
        d = r.json()["data"]
        assert d["handle"] == "novo.perfil" and d["status"] == "aguardando" and d["ingestao_ativa"] is True
        jobs = bib.queued("biblioteca.sync_perfil")
        assert [j.payload["perfil_id"] for j in jobs] == [d["id"]]
        refs = _refs(bib)
        assert any(r["modo"] == "perfil" and r["perfil_id"] == d["id"] and r["marca_id"] == MARCA and r["auto_atualizar"] for r in refs)
        row = next(r for r in bib.db.from_("cs_perfis_monitorados").select("*").execute().data if r["id"] == d["id"])
        assert row["conta_descoberta_id"] == ACC and row["org_id"] == ORG

    def test_switch_off_still_201_aguardando_with_the_banner_flag(self, bib, client):
        bib.switch_on = False
        r = client.post(f"{BASE}/perfis", json={"marca_id": MARCA, "handle": "novo"})
        assert r.status_code == 201
        d = r.json()["data"]
        assert d["status"] == "aguardando" and d["ingestao_ativa"] is False
        assert len(bib.queued("biblioteca.sync_perfil")) == 1  # waits in the queue, claim-gated

    def test_without_a_meta_account_the_profile_is_sem_conta_and_nothing_is_queued(self, bib, client):
        bib.db.from_("integration_accounts").delete().eq("provider", "meta").execute()
        d = client.post(f"{BASE}/perfis", json={"marca_id": MARCA, "handle": "novo"}).json()["data"]
        assert d["status"] == "sem_conta" and "Meta" in d["erro_mensagem"]
        assert bib.queued() == []

    def test_existing_handle_is_reused_and_referenced(self, bib, client):
        r = client.post(f"{BASE}/perfis", json={"marca_id": MARCA_B, "handle": "alvo1"})
        assert r.status_code == 201 and r.json()["data"]["id"] == P1
        assert bib.queued() == []
        assert len(client.get(f"{BASE}/perfis").json()["data"]) == 2

    @pytest.mark.parametrize("handle", ["", "p/abc", "instagram.com/reel/xyz", "a b", "x" * 31])
    def test_invalid_handles_are_422(self, bib, client, handle):
        assert client.post(f"{BASE}/perfis", json={"marca_id": MARCA, "handle": handle}).status_code == 422

    def test_unknown_fields_are_422(self, bib, client):
        assert client.post(f"{BASE}/perfis", json={"marca_id": MARCA, "handle": "x", "org_id": "o"}).status_code == 422

    def test_foreign_marca_and_foreign_account(self, bib, client):
        assert client.post(f"{BASE}/perfis", json={"marca_id": FOREIGN_MARCA, "handle": "x"}).status_code == 404
        r = client.post(f"{BASE}/perfis", json={"marca_id": MARCA, "handle": "x", "conta_descoberta_id": str(uuid.uuid4())})
        assert r.status_code == 422

    def test_org_profile_cap_is_409(self, bib, client):
        from app.config import settings

        for i in range(settings.biblioteca_max_perfis_org):
            bib.db.from_("cs_perfis_monitorados").insert(
                {"id": str(uuid.uuid4()), "org_id": ORG, "rede": "instagram", "handle": f"fill{i}", "status": "ativo"}
            ).execute()
        assert client.post(f"{BASE}/perfis", json={"marca_id": MARCA, "handle": "excedente"}).status_code == 409

    def test_sincronizar_enqueues_once_per_hour(self, bib, client):
        r = client.post(f"{BASE}/perfis/{P1}/sincronizar")
        assert r.status_code == 202, r.text
        assert r.json()["data"]["enfileirado"] is True and r.json()["data"]["ingestao_ativa"] is True
        assert len(bib.queued("biblioteca.sync_perfil")) == 1
        again = client.post(f"{BASE}/perfis/{P1}/sincronizar")
        assert again.status_code == 429 and int(again.headers["Retry-After"]) > 0
        assert len(bib.queued("biblioteca.sync_perfil")) == 1

    def test_sincronizar_refused_right_after_a_sync(self, bib, client):
        bib.db.from_("cs_perfis_monitorados").update({"ultima_sync_em": (NOW - timedelta(minutes=10)).isoformat()}).eq("id", P2).execute()
        r = client.post(f"{BASE}/perfis/{P2}/sincronizar")
        assert r.status_code == 429 and int(r.headers["Retry-After"]) <= 3600
        assert bib.queued() == []

    def test_sincronizar_after_an_hour_and_for_error_states_resets_them(self, bib, client):
        bib.db.from_("cs_perfis_monitorados").update(
            {"ultima_sync_em": (NOW - timedelta(hours=2)).isoformat(), "status": "erro", "erro_mensagem": "x"}
        ).eq("id", P2).execute()
        assert client.post(f"{BASE}/perfis/{P2}/sincronizar").status_code == 202
        row = next(r for r in bib.db.from_("cs_perfis_monitorados").select("*").execute().data if r["id"] == P2)
        assert row["status"] == "aguardando" and row["erro_mensagem"] is None

    def test_sincronizar_paused_is_409_and_foreign_is_404(self, bib, client):
        bib.db.from_("cs_perfis_monitorados").update({"status": "pausado"}).eq("id", P2).execute()
        assert client.post(f"{BASE}/perfis/{P2}/sincronizar").status_code == 409
        assert client.post(f"{BASE}/perfis/{FOREIGN_PERFIL}/sincronizar").status_code == 404

    def test_patch_pause_and_reactivate(self, bib, client):
        d = client.patch(f"{BASE}/perfis/{P1}", json={"status": "pausado"}).json()["data"]
        assert d["status"] == "pausado" and bib.queued() == []
        d = client.patch(f"{BASE}/perfis/{P1}", json={"status": "ativo"}).json()["data"]
        assert d["status"] == "aguardando" and len(bib.queued("biblioteca.sync_perfil")) == 1

    def test_patch_account_validation_and_404(self, bib, client):
        assert client.patch(f"{BASE}/perfis/{P1}", json={"conta_descoberta_id": str(uuid.uuid4())}).status_code == 422
        assert client.patch(f"{BASE}/perfis/{P1}", json={"conta_descoberta_id": ACC}).status_code == 200
        assert client.patch(f"{BASE}/perfis/{FOREIGN_PERFIL}", json={"status": "pausado"}).status_code == 404
        assert client.patch(f"{BASE}/perfis/{P1}", json={"status": "erro"}).status_code == 422

    def test_delete_removes_blobs_transcripts_and_the_profile(self, bib, client):
        anyio.run(lambda: bib.storage.put(bucket="sw-biblioteca", key=f"{ORG}/{P1}/{V1}.jpg", data=b"x"))
        anyio.run(lambda: bib.storage.put(bucket="sw-biblioteca", key=f"{ORG}/{P1}/foto.jpg", data=b"x"))
        bib.db.from_("cs_perfis_monitorados").update({"foto_path": f"{ORG}/{P1}/foto.jpg"}).eq("id", P1).execute()
        bib.db.from_("transcricoes").insert({"id": "t1", "org_id": ORG, "contexto_tipo": "biblioteca_viral", "contexto_ref": V1, "status": "concluida"}).execute()
        bib.db.from_("transcricoes").insert({"id": "t2", "org_id": ORG, "contexto_tipo": "cerebro_resposta", "contexto_ref": V1, "status": "concluida"}).execute()
        _add_ref(bib, MARCA, modo="perfil", perfil_id=P1)
        assert client.delete(f"{BASE}/perfis/{P1}?marca_id={MARCA}").status_code == 204
        assert anyio.run(lambda: bib.storage.list_keys(bucket="sw-biblioteca")) == []
        ids = {r["id"] for r in bib.db.from_("transcricoes").select("*").execute().data}
        assert ids == {"t2"}  # only the library's transcript went; another context's stays
        assert P1 not in {r["id"] for r in bib.db.from_("cs_perfis_monitorados").select("*").execute().data}

    def test_delete_is_409_while_another_marca_references_it(self, bib, client):
        _add_ref(bib, MARCA, modo="perfil", perfil_id=P1)
        _add_ref(bib, MARCA_B, modo="perfil", perfil_id=P1)
        assert client.delete(f"{BASE}/perfis/{P1}?marca_id={MARCA}").status_code == 409
        assert client.delete(f"{BASE}/perfis/{P1}").status_code == 409
        assert P1 in {r["id"] for r in bib.db.from_("cs_perfis_monitorados").select("*").execute().data}

    def test_delete_is_409_when_another_marca_references_one_of_its_videos(self, bib, client):
        _add_ref(bib, MARCA_B, modo="video", viral_id=V1)
        assert client.delete(f"{BASE}/perfis/{P1}?marca_id={MARCA}").status_code == 409

    def test_delete_foreign_is_404(self, bib, client):
        assert client.delete(f"{BASE}/perfis/{FOREIGN_PERFIL}").status_code == 404


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

    def test_foreign_ids_and_marca_are_404_and_nothing_is_created(self, bib, client):
        post = lambda b: client.post(f"{BASE}/referencias", json=b)
        assert post({"marca_id": MARCA, "modo": "perfil", "perfil_ids": [P1, FOREIGN_PERFIL], "auto_atualizar": True}).status_code == 404
        assert post({"marca_id": MARCA, "modo": "video", "viral_ids": [V1, FOREIGN_VIRAL]}).status_code == 404
        assert post({"marca_id": FOREIGN_MARCA, "modo": "video", "viral_ids": [V1]}).status_code == 404
        assert _refs(bib) == []

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
        assert [x["modo"] for x in client.get(f"{BASE}/referencias?marca_id={MARCA}&q=alvo1").json()["data"]] == ["perfil", "video"]
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
