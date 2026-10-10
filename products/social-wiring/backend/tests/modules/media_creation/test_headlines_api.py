"""Headlines API (BE-4): auth, isolation, caps, lifecycle, lists, edits, daily suggestions.

Real seams only: the queue is a ``FakeJobRepository`` and the settings a ``model_copy`` of the real
ones (both through the router's DI seams), the IA-configured check and the thumbnail storage are the
router's own DI seams, the DB the module ``client`` fixture's mock Supabase.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.integrations.llm import LLMNotConfigured
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.config import settings
from app.modules.media_creation.routers import headlines as hr
from app.modules.media_creation.services import headline_pipeline as hp
from app.rate_limit import limiter

BASE = "/api/media-creation/headlines"
ORG = "test-org-123"
MARCA = str(uuid.uuid4())
OTHER_MARCA = str(uuid.uuid4())
BIO = "Eu sou Gilson Tangerino, especialista em negócios imobiliários."
NOW = datetime.now(timezone.utc)
DORES = "DORES-TANGIVEIS-DO-AVATAR"


def _cfg(**over):
    return settings.model_copy(update=over)


class FakeJobsBroken:
    async def enqueue(self, **_kw):
        raise RuntimeError("queue down")


@pytest.fixture
def hc(client):
    sb = client.mock_supabase
    sb.from_("marcas").insert({"id": MARCA, "org_id": ORG, "name": "Marca A"}).execute()
    sb.from_("marcas").insert({"id": OTHER_MARCA, "org_id": "other-org", "name": "B"}).execute()
    sb.from_("cs_marca_perfil").insert({"marca_id": MARCA, "org_id": ORG, "bio": BIO, "nichos": [3]}).execute()
    client.jobs = FakeJobRepository()
    client.storage = FakeStorageBackend()
    ov = client._tc.app.dependency_overrides
    ov[hr.get_headline_jobs] = lambda: client.jobs
    ov[hr.get_headline_settings] = lambda: _cfg()
    ov[hr.get_ia_check] = lambda: (lambda org_id: None)
    ov[hr.get_headline_storage] = lambda: client.storage
    return client


def _use_cfg(hc, **over):
    hc._tc.app.dependency_overrides[hr.get_headline_settings] = lambda: _cfg(**over)


def _lotes(hc):
    return hc.mock_supabase.from_("cs_headline_lotes").select("*").execute().data


def _hls(hc):
    return hc.mock_supabase.from_("cs_headlines").select("*").execute().data


def _viral(hc, *, status="concluida", blueprint="BP", perfil=None, score=5.0, e_viral=True, **extra):
    vid = str(uuid.uuid4())
    perfil = perfil or str(uuid.uuid4())
    hc.mock_supabase.from_("cs_perfis_monitorados").insert(
        {"id": perfil, "org_id": ORG, "handle": "perfil_x"}
    ).execute() if not hc.mock_supabase.from_("cs_perfis_monitorados").select("id").eq("id", perfil).execute().data else None
    hc.mock_supabase.from_("cs_virais").insert({
        "id": vid, "org_id": ORG, "perfil_id": perfil, "codigo": len(hc.mock_supabase.from_("cs_virais").select("id").execute().data) + 1,
        "classificacao_status": status, "blueprint": blueprint, "blueprint_slots": [DORES], "nicho_ids": [3],
        "formato_ids": [], "score_viral": score, "e_viral": e_viral, "permalink": "https://ig/p/x",
        "publicado_em": (NOW - timedelta(days=3)).isoformat(), "views": None, "likes": 10, "comments": 5, **extra,
    }).execute()
    return vid, perfil


def _lote_row(hc, *, status="completo", origem="form_me", marca=MARCA, org=ORG, user=None, params=None, age_h=0.0):
    lid = str(uuid.uuid4())
    hc.mock_supabase.from_("cs_headline_lotes").insert({
        "id": lid, "org_id": org, "marca_id": marca, "created_by": user or "someone", "origem": origem,
        "parametros": params or {"origem": origem, "marca_id": marca, "variaveis": ["*"], "assunto": "juros"},
        "status": status, "estruturas_total": 1, "estruturas_processadas": 1, "estruturas_com_erro": 0,
        "created_at": (NOW - timedelta(hours=age_h)).isoformat(),
    }).execute()
    return lid


def _hl(hc, *, lote=None, marca=MARCA, org=ORG, texto="Uma headline.", viral=None, favorita=False, modo=None,
        age_min=0, angulo=1, original=None):
    hid = str(uuid.uuid4())
    hc.mock_supabase.from_("cs_headlines").insert({
        "id": hid, "org_id": org, "marca_id": marca, "lote_id": lote, "viral_id": viral, "texto": texto,
        "texto_original": original, "angulo": angulo, "itens_usados": [], "favorita": favorita,
        "favoritada_em": NOW.isoformat() if favorita else None, "modo": modo,
        "created_at": (NOW - timedelta(minutes=age_min)).isoformat(),
    }).execute()
    return hid


def _form(**over):
    return {"marca_id": MARCA, "origem": "form_me", "variaveis": [DORES], "criatividade": "equilibrado", **over}


def _create(hc, body=None):
    return hc.post(f"{BASE}/lotes", json=body or _form())


LOTE_KEYS = {
    "id", "marca_id", "origem", "status", "etapa", "estruturas_total", "estruturas_processadas",
    "estruturas_com_erro", "aviso_poucas_estruturas", "fallback_metodo", "erro", "resumo", "created_at",
    "finished_at",
}
HEADLINE_KEYS = {
    "id", "marca_id", "lote_id", "texto", "texto_original", "angulo", "viral", "template_metodo",
    "itens_usados", "favorita", "modo", "roteiro_id", "post", "created_at",
}


class TestAuthAndLimits:
    @pytest.mark.parametrize("fn", [hr.create_lote, hr.reprocessar_lote, hr.gerar_sugestoes_agora])
    def test_default_ai_rl_is_applied_to_every_llm_route(self, fn):
        from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL

        key = f"{fn.__module__}.{fn.__name__}"
        limits = limiter._route_limits.get(key) or []
        assert limits, f"{key} carries no @limiter.limit"
        assert DEFAULT_AI_RL.split("/")[0] in {str(lim.limit.amount) for lim in limits}

    @pytest.mark.parametrize("method,path,kw", [
        ("post", "/lotes", {"json": {"marca_id": MARCA, "origem": "form_me", "variaveis": ["*"]}}),
        ("get", "/lotes", {"params": {"marca_id": MARCA}}),
        ("get", f"/lotes/{uuid.uuid4()}", {}),
        ("post", f"/lotes/{uuid.uuid4()}/reprocessar", {}),
        ("post", "/lotes/excluir", {"json": {"ids": [str(uuid.uuid4())]}}),
        ("get", "", {"params": {"marca_id": MARCA, "lista": "favoritas"}}),
        ("get", f"/{uuid.uuid4()}", {}),
        ("patch", f"/{uuid.uuid4()}", {"json": {"texto": "x"}}),
        ("post", f"/{uuid.uuid4()}/favoritar", {}),
        ("post", f"/{uuid.uuid4()}/desfavoritar", {}),
        ("post", "", {"json": {"marca_id": MARCA, "texto": "x", "favoritar": True}}),
        ("post", "/excluir", {"json": {"ids": [str(uuid.uuid4())]}}),
        ("post", "/sugestoes/gerar-agora", {"json": {"marca_id": MARCA}}),
        ("get", "/estruturas/contagem", {"params": {"marca_id": MARCA, "variaveis": ["*"]}}),
    ])
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (method, path, r.status_code, r.text)


class TestCreateLote:
    def test_202_queues_the_batch_and_the_job(self, hc):
        r = _create(hc)
        assert r.status_code == 202, r.text
        data = r.json()["data"]
        assert set(data) == LOTE_KEYS
        assert data["status"] == "criando" and data["origem"] == "form_me" and data["resumo"] == "Headlines para mim"
        row = _lotes(hc)[0]
        assert row["parametros"]["variaveis"] == [DORES] and row["created_by"]
        job = next(iter(hc.jobs._jobs.values()))
        assert job.type == "headline.gerar" and job.payload == {"lote_id": data["id"]}
        assert job.dedupe_key == f"headline.gerar:{data['id']}" and job.max_retries == 2
        assert row["queue_job_id"] == job.id

    def test_the_four_origins_are_accepted(self, hc):
        vid, _ = _viral(hc)
        t1 = str(uuid.uuid4())
        hc.mock_supabase.from_("cs_viral_topics").insert(
            {"id": t1, "org_id": ORG, "marca_id": MARCA, "topic": "juros", "status": "approved"}
        ).execute()
        bodies = [
            _form(origem="form_public", assunto="x", somente_pesquisa=True),
            {"marca_id": MARCA, "origem": "form_viral", "assunto_livre": "juros", "tom": 12, "criatividade": "explorador"},
            {"marca_id": MARCA, "origem": "form_viral", "assunto_ids": [t1]},
            {"marca_id": MARCA, "origem": "biblioteca", "viral_id": vid, "assunto_livre": "x"},
        ]
        for b in bodies:
            assert _create(hc, b).status_code == 202, b
            for row in _lotes(hc):  # free the user's single active slot between runs
                hc.mock_supabase.from_("cs_headline_lotes").update({"status": "completo"}).eq("id", row["id"]).execute()
        assert [r["origem"] for r in _lotes(hc)] == ["form_public", "form_viral", "form_viral", "biblioteca"]

    @pytest.mark.parametrize("body", [
        {"marca_id": MARCA, "origem": "form_viral"},  # needs a subject
        {"marca_id": MARCA, "origem": "form_viral", "assunto_livre": "x", "tom": 9},
        {"marca_id": MARCA, "origem": "form_viral", "assunto_livre": "x", "referencia": {"tipo": "gatilho", "gatilhos": ["misterio"]}},
        {"marca_id": MARCA, "origem": "form_me", "variaveis": []},
        {"marca_id": MARCA, "origem": "nada", "variaveis": ["*"]},
        {"marca_id": MARCA, "origem": "form_me", "variaveis": ["*"], "criatividade": "louca"},
        {"marca_id": MARCA, "origem": "form_me", "variaveis": ["*"], "extra": 1},
        {"marca_id": MARCA, "origem": "form_me", "variaveis": ["*"], "assunto": "x" * 301},
        {"marca_id": MARCA, "origem": "form_me", "variaveis": ["*"], "referencia": {"tipo": "perfil", "perfil_ids": []}},
        {"marca_id": MARCA, "origem": "biblioteca"},
    ])
    def test_invalid_bodies_are_422(self, hc, body):
        assert _create(hc, body).status_code == 422
        assert _lotes(hc) == [] and hc.jobs._jobs == {}

    def test_empty_bio_is_422_with_the_contract_message(self, hc):
        hc.mock_supabase.from_("cs_marca_perfil").update({"bio": ""}).eq("marca_id", MARCA).execute()
        r = _create(hc)
        assert r.status_code == 422 and r.json()["error"]["message"] == "Preencha a bio em Meu Perfil antes de gerar headlines"
        assert _lotes(hc) == []

    def test_unknown_variable_is_422(self, hc):
        r = _create(hc, _form(variaveis=["NAO-EXISTE"]))
        assert r.status_code == 422 and "NAO-EXISTE" in r.json()["error"]["message"]

    def test_valores_must_be_approved_items_of_this_marca(self, hc):
        ok = str(uuid.uuid4())
        hc.mock_supabase.from_("cs_research_items").insert({
            "id": ok, "org_id": ORG, "marca_id": MARCA, "variable_slug": DORES, "content": "x", "status": "approved",
        }).execute()
        pend = str(uuid.uuid4())
        hc.mock_supabase.from_("cs_research_items").insert({
            "id": pend, "org_id": ORG, "marca_id": MARCA, "variable_slug": DORES, "content": "y", "status": "pending",
        }).execute()
        assert _create(hc, _form(valores={DORES: [pend]})).status_code == 422
        assert _create(hc, _form(valores={DORES: [str(uuid.uuid4())]})).status_code == 422
        assert _create(hc, _form(valores={DORES: [ok]})).status_code == 202

    def test_foreign_or_unknown_marca_is_404(self, hc):
        assert _create(hc, _form(marca_id=OTHER_MARCA)).status_code == 404
        assert _create(hc, _form(marca_id=str(uuid.uuid4()))).status_code == 404

    def test_unknown_profile_reference_is_404_and_bad_format_422(self, hc):
        assert _create(hc, _form(referencia={"tipo": "perfil", "perfil_ids": [str(uuid.uuid4())]})).status_code == 404
        assert _create(hc, _form(referencia={"tipo": "formato", "formato_ids": [99999]})).status_code == 422

    def test_biblioteca_viral_without_structure_is_409_unknown_or_foreign_404(self, hc):
        pend, _ = _viral(hc, status="pendente", blueprint=None)
        r = _create(hc, {"marca_id": MARCA, "origem": "biblioteca", "viral_id": pend})
        assert r.status_code == 409 and "ainda não tem estrutura" in r.json()["error"]["message"]
        assert _create(hc, {"marca_id": MARCA, "origem": "biblioteca", "viral_id": str(uuid.uuid4())}).status_code == 404

    def test_unknown_viral_topic_is_404(self, hc):
        r = _create(hc, {"marca_id": MARCA, "origem": "form_viral", "assunto_ids": [str(uuid.uuid4())]})
        assert r.status_code == 404

    def test_second_active_batch_is_409(self, hc):
        assert _create(hc).status_code == 202
        r = _create(hc)
        assert r.status_code == 409 and r.json()["error"]["message"] == "Já existe uma geração em andamento"

    def test_a_finished_batch_frees_the_slot(self, hc):
        assert _create(hc).status_code == 202
        hc.mock_supabase.from_("cs_headline_lotes").update({"status": "falha"}).execute()
        assert _create(hc).status_code == 202

    def test_a_suggestion_batch_does_not_hold_the_manual_slot(self, hc):
        _lote_row(hc, status="processando", origem="sugestao_auto", user="whoever")
        assert _create(hc).status_code == 202

    def test_daily_cap_is_429_with_retry_after(self, hc):
        _use_cfg(hc, headline_lotes_dia_usuario=1)
        assert _create(hc).status_code == 202
        hc.mock_supabase.from_("cs_headline_lotes").update({"status": "completo"}).execute()
        r = _create(hc)
        assert r.status_code == 429 and r.headers["Retry-After"] == "3600"

    def test_cap_counts_a_rolling_24_hours_only(self, hc):
        _use_cfg(hc, headline_lotes_dia_usuario=1)
        assert _create(hc).status_code == 202
        hc.mock_supabase.from_("cs_headline_lotes").update(
            {"status": "completo", "created_at": (NOW - timedelta(hours=25)).isoformat()}
        ).execute()
        assert _create(hc).status_code == 202

    def test_worker_disabled_is_503(self, hc):
        _use_cfg(hc, geracao_worker_enabled=False)
        r = _create(hc)
        assert r.status_code == 503 and "geracao_indisponivel" in r.text and _lotes(hc) == []

    def test_unconfigured_ia_is_503_before_anything_is_written(self, hc):
        def check(org_id):
            raise LLMNotConfigured("anthropic")

        hc._tc.app.dependency_overrides[hr.get_ia_check] = lambda: check
        r = _create(hc)
        assert r.status_code == 503 and "ia_nao_configurada" in r.text
        assert _lotes(hc) == [] and hc.jobs._jobs == {}

    def test_enqueue_failure_is_503_and_the_row_is_settled_falha(self, hc):
        hc._tc.app.dependency_overrides[hr.get_headline_jobs] = lambda: FakeJobsBroken()
        r = _create(hc)
        assert r.status_code == 503
        row = _lotes(hc)[0]
        assert row["status"] == "falha" and row["erro"] == "Falha ao iniciar a geração"
        hc._tc.app.dependency_overrides[hr.get_headline_jobs] = lambda: hc.jobs
        assert _create(hc).status_code == 202  # the failed row freed the slot


class TestLotes:
    # NOTE: MockSupabaseClient ignores .order(); the DB-side ordering (created_at DESC) is asserted
    # only as a SET here -- the real ordering is Postgres'.
    def test_list_defaults_to_the_three_form_origins(self, hc):
        a = _lote_row(hc, age_h=3)
        b = _lote_row(hc, origem="form_viral", age_h=1)
        _lote_row(hc, origem="biblioteca")
        _lote_row(hc, origem="sugestao_auto")
        _lote_row(hc, marca=OTHER_MARCA, org="other-org")
        d = hc.get(f"{BASE}/lotes", params={"marca_id": MARCA}).json()["data"]
        assert {i["id"] for i in d["items"]} == {b, a} and d["total"] == 2 and set(d["items"][0]) == LOTE_KEYS

    def test_origem_in_and_pagination(self, hc):
        ids = [_lote_row(hc, origem="biblioteca", age_h=i) for i in range(3)]
        p1 = hc.get(f"{BASE}/lotes", params={"marca_id": MARCA, "origem_in": ["biblioteca"], "limit": 2}).json()["data"]
        p2 = hc.get(f"{BASE}/lotes", params={"marca_id": MARCA, "origem_in": ["biblioteca"], "limit": 2, "offset": 2}).json()["data"]
        assert (len(p1["items"]), p1["total"], len(p2["items"]), p2["total"]) == (2, 3, 1, 3)
        assert {i["id"] for i in p1["items"] + p2["items"]} == set(ids)

    def test_invalid_origem_is_422_foreign_marca_404(self, hc):
        assert hc.get(f"{BASE}/lotes", params={"marca_id": MARCA, "origem_in": ["x"]}).status_code == 422
        assert hc.get(f"{BASE}/lotes", params={"marca_id": OTHER_MARCA}).status_code == 404

    def test_search_matches_the_subject(self, hc):
        a = _lote_row(hc, params={"origem": "form_me", "assunto": "juros altos"})
        _lote_row(hc, params={"origem": "form_me", "assunto": "reforma"})
        d = hc.get(f"{BASE}/lotes", params={"marca_id": MARCA, "q": "JUROS"}).json()["data"]
        assert [i["id"] for i in d["items"]] == [a] and d["total"] == 1
        assert d["items"][0]["resumo"] == "Headlines para mim · juros altos"

    def test_detail_carries_the_params_and_headlines_with_their_viral(self, hc):
        vid, perfil = _viral(hc, thumbnail_path="t/1.jpg", gancho="Um gancho forte")
        lid = _lote_row(hc)
        h2 = _hl(hc, lote=lid, viral=vid, angulo=2, age_min=0)
        h1 = _hl(hc, lote=lid, viral=vid, angulo=1, age_min=0)
        d = hc.get(f"{BASE}/lotes/{lid}").json()["data"]
        assert d["parametros"]["assunto"] == "juros" and {h["id"] for h in d["headlines"]} == {h1, h2}
        h = d["headlines"][0]
        assert set(h) == HEADLINE_KEYS
        assert h["viral"]["perfil"] == {"id": perfil, "handle": "perfil_x"} and h["viral"]["trecho"] == "Um gancho forte"
        assert h["viral"]["thumbnail_url"].startswith("fake://storage/sw-biblioteca/t/1.jpg")
        assert h["viral"]["views"] is None and h["viral"]["e_viral"] is True

    def test_foreign_batch_is_404(self, hc):
        other = _lote_row(hc, marca=OTHER_MARCA, org="other-org")
        assert hc.get(f"{BASE}/lotes/{other}").status_code == 404
        assert hc.get(f"{BASE}/lotes/{uuid.uuid4()}").status_code == 404

    def test_reprocess_creates_a_new_batch_with_the_same_params_and_keeps_the_old(self, hc):
        _viral(hc)
        first = _create(hc, _form(assunto="juros")).json()["data"]["id"]
        hc.mock_supabase.from_("cs_headline_lotes").update({"status": "falha"}).eq("id", first).execute()
        r = hc.post(f"{BASE}/lotes/{first}/reprocessar")
        assert r.status_code == 202, r.text
        new = r.json()["data"]["id"]
        rows = {x["id"]: x for x in _lotes(hc)}
        assert set(rows) == {first, new} and rows[new]["parametros"] == rows[first]["parametros"]
        assert len(hc.jobs._jobs) == 2

    def test_reprocess_while_one_is_active_is_409_foreign_404(self, hc):
        first = _create(hc).json()["data"]["id"]
        assert hc.post(f"{BASE}/lotes/{first}/reprocessar").status_code == 409
        other = _lote_row(hc, marca=OTHER_MARCA, org="other-org")
        assert hc.post(f"{BASE}/lotes/{other}/reprocessar").status_code == 404

    def test_delete_cascades_to_headlines_favorites_included(self, hc):
        lid, keep = _lote_row(hc), _lote_row(hc)
        _hl(hc, lote=lid, favorita=True)
        survivor = _hl(hc, lote=keep)
        r = hc.post(f"{BASE}/lotes/excluir", json={"ids": [lid]})
        assert r.status_code == 200 and r.json()["data"] == {"excluidos": 1}
        assert [h["id"] for h in _hls(hc)] == [survivor] and [x["id"] for x in _lotes(hc)] == [keep]

    def test_delete_is_all_or_nothing_for_foreign_ids_and_refuses_active_batches(self, hc):
        mine = _lote_row(hc)
        foreign = _lote_row(hc, marca=OTHER_MARCA, org="other-org")
        assert hc.post(f"{BASE}/lotes/excluir", json={"ids": [mine, foreign]}).status_code == 404
        assert len(_lotes(hc)) == 2
        active = _lote_row(hc, status="processando")
        assert hc.post(f"{BASE}/lotes/excluir", json={"ids": [active]}).status_code == 409


class TestHeadlines:
    def test_favoritas_list_orders_by_favorited_at_and_is_marca_scoped(self, hc):
        a = _hl(hc, favorita=True, age_min=30)
        b = _hl(hc, favorita=True, age_min=1)
        _hl(hc, favorita=False)
        _hl(hc, favorita=True, marca=OTHER_MARCA, org="other-org")
        hc.mock_supabase.from_("cs_headlines").update({"favoritada_em": (NOW - timedelta(minutes=30)).isoformat()}).eq("id", a).execute()
        d = hc.get(BASE, params={"marca_id": MARCA, "lista": "favoritas"}).json()["data"]
        assert {h["id"] for h in d["items"]} == {b, a} and d["total"] == 2 and set(d["items"][0]) == HEADLINE_KEYS

    def test_sugeridas_sorted_by_viral_metric_then_recency_and_modo_filter(self, hc):
        weak, _ = _viral(hc, likes=1, comments=1)
        strong, _ = _viral(hc, likes=500, comments=100)
        viewed, _ = _viral(hc, views=9000, likes=0, comments=0)
        a = _hl(hc, viral=weak, modo="manual", age_min=1)
        b = _hl(hc, viral=strong, modo="automatico", age_min=50)
        c = _hl(hc, viral=viewed, modo="manual", age_min=100)
        d_old = _hl(hc, viral=None, modo="manual", age_min=2)
        _hl(hc, modo=None, favorita=True)  # a form headline is not a suggestion
        d = hc.get(BASE, params={"marca_id": MARCA, "lista": "sugeridas"}).json()["data"]
        assert [h["id"] for h in d["items"]] == [c, b, a, d_old] and d["total"] == 4
        d = hc.get(BASE, params={"marca_id": MARCA, "lista": "sugeridas", "modo": "automatico"}).json()["data"]
        assert [h["id"] for h in d["items"]] == [b]
        d = hc.get(BASE, params={"marca_id": MARCA, "lista": "sugeridas", "limit": 1, "offset": 1}).json()["data"]
        assert [h["id"] for h in d["items"]] == [b] and d["total"] == 4

    def test_search_text(self, hc):
        a = _hl(hc, texto="O aluguel que nunca acaba", favorita=True)
        _hl(hc, texto="Outra coisa", favorita=True)
        d = hc.get(BASE, params={"marca_id": MARCA, "lista": "favoritas", "q": "ALUGUEL"}).json()["data"]
        assert [h["id"] for h in d["items"]] == [a]

    def test_bad_list_params(self, hc):
        assert hc.get(BASE, params={"marca_id": MARCA, "lista": "todas"}).status_code == 422
        assert hc.get(BASE, params={"marca_id": MARCA, "lista": "sugeridas", "modo": "x"}).status_code == 422
        assert hc.get(BASE, params={"marca_id": OTHER_MARCA, "lista": "favoritas"}).status_code == 404

    def test_get_one_and_derived_roteiro_id(self, hc):
        h = _hl(hc)
        hc.mock_supabase.from_("cs_roteiros").insert(
            {"id": "r1", "org_id": ORG, "marca_id": MARCA, "headline_id": h, "created_at": NOW.isoformat()}
        ).execute()
        d = hc.get(f"{BASE}/{h}").json()["data"]
        assert d["id"] == h and d["roteiro_id"] == "r1" and d["viral"] is None

    def test_edit_keeps_the_original_text_once(self, hc):
        h = _hl(hc, texto="Texto da IA")
        r = hc.patch(f"{BASE}/{h}", json={"texto": "  Texto editado  "})
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["texto"] == "Texto editado" and d["texto_original"] == "Texto da IA"
        d = hc.patch(f"{BASE}/{h}", json={"texto": "Segunda edição"}).json()["data"]
        assert d["texto"] == "Segunda edição" and d["texto_original"] == "Texto da IA"

    @pytest.mark.parametrize("texto", ["", "   ", "x" * 1001])
    def test_edit_validation(self, hc, texto):
        h = _hl(hc)
        assert hc.patch(f"{BASE}/{h}", json={"texto": texto}).status_code == 422

    def test_favoritar_and_desfavoritar_are_idempotent(self, hc):
        h = _hl(hc)
        for _ in range(2):
            d = hc.post(f"{BASE}/{h}/favoritar").json()["data"]
            assert d["favorita"] is True
        assert _hls(hc)[0]["favoritada_em"]
        for _ in range(2):
            assert hc.post(f"{BASE}/{h}/desfavoritar").json()["data"]["favorita"] is False
        assert _hls(hc)[0]["favoritada_em"] is None

    def test_save_from_chat_has_no_batch_and_is_a_favorite(self, hc):
        r = hc.post(BASE, json={"marca_id": MARCA, "texto": " Minha headline ", "favoritar": True})
        assert r.status_code == 201, r.text
        d = r.json()["data"]
        assert d["lote_id"] is None and d["favorita"] is True and d["texto"] == "Minha headline"
        assert d["texto_original"] == "Minha headline" and d["modo"] is None and d["viral"] is None

    def test_save_validation(self, hc):
        assert hc.post(BASE, json={"marca_id": MARCA, "texto": "x", "favoritar": False}).status_code == 422
        assert hc.post(BASE, json={"marca_id": MARCA, "texto": "   ", "favoritar": True}).status_code == 422
        assert hc.post(BASE, json={"marca_id": OTHER_MARCA, "texto": "x", "favoritar": True}).status_code == 404

    def test_cross_org_headline_is_404_on_every_id_route(self, hc):
        foreign = _hl(hc, marca=OTHER_MARCA, org="other-org")
        assert hc.get(f"{BASE}/{foreign}").status_code == 404
        assert hc.patch(f"{BASE}/{foreign}", json={"texto": "x"}).status_code == 404
        assert hc.post(f"{BASE}/{foreign}/favoritar").status_code == 404
        assert hc.post(f"{BASE}/{foreign}/desfavoritar").status_code == 404
        assert hc.post(f"{BASE}/excluir", json={"ids": [foreign]}).status_code == 404
        assert _hls(hc)[0]["texto"] == "Uma headline."  # untouched

    def test_bulk_delete(self, hc):
        a, b, keep = _hl(hc), _hl(hc), _hl(hc)
        r = hc.post(f"{BASE}/excluir", json={"ids": [a, b, a]})
        assert r.status_code == 200 and r.json()["data"] == {"excluidos": 2}
        assert [h["id"] for h in _hls(hc)] == [keep]
        assert hc.post(f"{BASE}/excluir", json={"ids": []}).status_code == 422
        assert hc.post(f"{BASE}/excluir", json={"ids": [str(uuid.uuid4())] * 101}).status_code == 422


class TestContagem:
    def test_counts_compatible_structures_per_profile(self, hc):
        _, p1 = _viral(hc)
        _viral(hc, perfil=p1)
        _, p2 = _viral(hc, blueprint="X")
        d = hc.get(f"{BASE}/estruturas/contagem", params={"marca_id": MARCA, "variaveis": [DORES]}).json()["data"]
        assert d["compativeis"] == 3 and {x["perfil_id"]: x["n"] for x in d["por_perfil"]} == {p1: 2, p2: 1}
        d = hc.get(f"{BASE}/estruturas/contagem", params={"marca_id": MARCA, "variaveis": ["MEDOS-DO-AVATAR"]}).json()["data"]
        assert d["compativeis"] == 0 and {x["n"] for x in d["por_perfil"]} == {0}

    def test_validation_and_scoping(self, hc):
        assert hc.get(f"{BASE}/estruturas/contagem", params={"marca_id": MARCA, "variaveis": ["NOPE"]}).status_code == 422
        assert hc.get(f"{BASE}/estruturas/contagem", params={"marca_id": OTHER_MARCA, "variaveis": ["*"]}).status_code == 404
        assert hc.get(f"{BASE}/estruturas/contagem", params={"marca_id": MARCA}).status_code == 422


class TestGerarAgora:
    def _now(self, hc):
        return hc.post(f"{BASE}/sugestoes/gerar-agora", json={"marca_id": MARCA})

    def test_202_creates_one_automatic_batch_with_the_top_virals(self, hc):
        best, _ = _viral(hc, score=90.0)
        mid, _ = _viral(hc, score=50.0)
        _viral(hc, score=99.0, e_viral=False)  # not viral -> never suggested
        _viral(hc, score=98.0, status="pendente", blueprint=None)
        r = self._now(hc)
        assert r.status_code == 202, r.text
        row = _lotes(hc)[0]
        assert r.json()["data"]["origem"] == "sugestao_auto" and row["parametros"]["viral_ids"] == [best, mid]
        assert next(iter(hc.jobs._jobs.values())).payload == {"lote_id": row["id"]}

    def test_capped_at_the_daily_structure_count(self, hc):
        _use_cfg(hc, headlines_sugeridas_por_dia_marca=2)
        for i in range(4):
            _viral(hc, score=float(i))
        self._now(hc)
        assert len(_lotes(hc)[0]["parametros"]["viral_ids"]) == 2

    def test_virals_used_in_the_last_30_days_are_excluded(self, hc):
        used, _ = _viral(hc, score=99.0)
        fresh, _ = _viral(hc, score=1.0)
        _hl(hc, viral=used, age_min=60)
        self._now(hc)
        assert _lotes(hc)[0]["parametros"]["viral_ids"] == [fresh]

    def test_once_per_marca_per_day_is_429_but_a_failed_one_does_not_count(self, hc):
        _viral(hc)
        assert self._now(hc).status_code == 202
        r = self._now(hc)
        assert r.status_code == 429 and r.headers["Retry-After"] == "3600"
        hc.mock_supabase.from_("cs_headline_lotes").update({"status": "falha"}).execute()
        assert self._now(hc).status_code == 202

    def test_needs_bio_and_a_niche(self, hc):
        _viral(hc)
        hc.mock_supabase.from_("cs_marca_perfil").update({"nichos": []}).eq("marca_id", MARCA).execute()
        assert self._now(hc).status_code == 422
        hc.mock_supabase.from_("cs_marca_perfil").update({"nichos": [3], "bio": " "}).eq("marca_id", MARCA).execute()
        assert self._now(hc).status_code == 422

    def test_no_structure_is_409_and_creates_nothing(self, hc):
        r = self._now(hc)
        assert r.status_code == 409 and _lotes(hc) == []

    def test_foreign_marca_404(self, hc):
        assert hc.post(f"{BASE}/sugestoes/gerar-agora", json={"marca_id": OTHER_MARCA}).status_code == 404


class TestGeracaoWorkerSwitchOnlyGatesGeneration:
    def test_reads_and_edits_still_work_with_the_worker_off(self, hc):
        _use_cfg(hc, geracao_worker_enabled=False)
        h = _hl(hc, favorita=True)
        assert hc.get(BASE, params={"marca_id": MARCA, "lista": "favoritas"}).status_code == 200
        assert hc.patch(f"{BASE}/{h}", json={"texto": "x"}).status_code == 200
        assert hp.JOB_TYPE == "headline.gerar"
