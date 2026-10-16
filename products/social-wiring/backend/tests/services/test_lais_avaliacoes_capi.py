"""Lais wave 13 -- the Google review ask (90-day rule, negative-feedback skip, 24 h window, deterministic copy) and the
Meta CAPI signals (Meta-ads leads only, SHA-256 per Meta's normalisation, gated by config + token, not-configured
paths, idempotent). Seams are the Fakes the product ships (mock DB, `FakeJobRepository`, `FakeCapiProvider`,
`FakeReviewsProvider`); nothing of ours is patched. No personal data: synthetic phones / emails only."""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest
from noctusai_lib.domain.jobs import FakeJobRepository
from noctusai_lib.primitives.exceptions import AppException

from app.clients.agents import FakeAgentsClient, LaisAction, ResumoResult, TurnResult
from app.services import lais_acoes_service as acoes
from app.services import lais_avaliacoes_service as av
from app.services import lais_capi_service as capi
from app.services import lais_contatos_service as contatos
from app.services.lais_reviews_provider import (
    FakeReviewsProvider, NaoConfiguradoReviews, RealGbpReviewsProvider, Review, ReviewsNaoConfigurado, make_reviews_provider,
    review_de_api,
)

from tests.support.lais_world import CONNECTION_ID, LEAD_CHAT, ORG_ID as ORG, OTHER_ORG_ID, World

AGORA = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
LINK = "https://g.page/r/exemplo/review"
FONE = "+5511988887777"
PIXEL = "123456789012345"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def world() -> World:
    w = World()
    w.seed_connection()
    for t in (av.T_CONFIG, av.T_PEDIDOS, av.T_CACHE, av.T_FEEDBACK, capi.T_CAPI, capi.T_LEADS, capi.T_META_LEADS):
        w.sw.set_table_data(t, [])
    return w


@pytest.fixture
def repo():
    r = FakeJobRepository()
    av.registrar_repo(r)
    capi.registrar_repo(r)
    yield r
    av.registrar_repo(None)
    capi.registrar_repo(None)


@pytest.fixture
def token():
    capi.registrar_token_resolver(lambda: "tok-fake")
    yield
    capi.registrar_token_resolver(None)


def contato(w: World, *, inbound_ago_h: float = 1, lead_id: str | None = None, **over) -> dict[str, Any]:
    c = contatos.obter_ou_criar_contato(w.sw, org_id=ORG, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT, telefone_e164=FONE, nome="Ana Maria")
    patch = {"ultimo_inbound_at": (AGORA - timedelta(hours=inbound_ago_h)).isoformat(), "lead_id": lead_id, **over}
    contatos.atualizar_contato(w.sw, c["id"], patch)
    return w.rows("lais_contatos")[0]


def interacao(w: World, c: dict[str, Any], desfecho: str = "qualificado") -> dict[str, Any]:
    row = {"id": str(uuid4()), "org_id": ORG, "contato_id": c["id"], "iniciada_at": AGORA.isoformat(), "encerrada_at": AGORA.isoformat(),
           "desfecho": desfecho, "tipo": "comercial", "slots": {}, "intencoes": []}
    return w.sw.table("lais_interacoes").insert(row).execute().data[0]


def config(w: World, **over):
    w.sw.table(av.T_CONFIG).insert({"org_id": ORG, "google_review_url": LINK, "gbp_location_id": None, "capi_ativo": False, "capi_pixel_id": None, **over}).execute()


class Saida:
    def __init__(self, erro: Exception | None = None):
        self.enviados: list[tuple[dict, str]] = []
        self.erro = erro

    async def __call__(self, c, texto):
        if self.erro:
            raise self.erro
        self.enviados.append((c, texto))


def job(c, inter, gen=None):
    from types import SimpleNamespace

    return SimpleNamespace(id="j1", type=av.JOB_PEDIR, payload={"org_id": ORG, "contato_id": c["id"], "interacao_id": inter["id"],
                                                    "gen": c["gen"] if gen is None else gen, "chat_key": "k"})


# ── the ask: rule ────────────────────────────────────────────────────────────────
class TestPedido:
    def test_sends_once_with_the_deterministic_text_and_records_it(self, world):
        config(world)
        c = contato(world)
        i = interacao(world, c)
        out = Saida()
        assert run(av.executar_pedido(job(c, i), client=world.sw, enviar=out, agora=AGORA)) == "enviado"
        (_, texto), = out.enviados
        assert texto == av.montar_texto("Ana Maria", LINK) and LINK in texto and texto.startswith("Oi, Ana!")
        (p,) = world.rows(av.T_PEDIDOS)
        assert p["status"] == "enviado" and p["contato_id"] == c["id"] and p["interacao_id"] == i["id"]
        assert world.rows("lais_contatos")[0]["ultimo_outbound_at"]

    def test_text_without_a_name(self):
        assert av.montar_texto(None, LINK).startswith("Oi! ") and av.montar_texto("  ", LINK).startswith("Oi! ")

    def test_at_most_once_per_contato_in_90_days(self, world):
        config(world)
        c = contato(world)
        i = interacao(world, c)
        out = Saida()
        assert run(av.executar_pedido(job(c, i), client=world.sw, enviar=out, agora=AGORA)) == "enviado"
        i2 = interacao(world, c)
        r = run(av.executar_pedido(job(c, i2), client=world.sw, enviar=out, agora=AGORA + timedelta(days=89)))
        assert r == "ignorado:ja_pediu_90_dias" and len(out.enviados) == 1
        # day 91: the window reopened (use a fresh in-window inbound)
        c2 = contato(world, inbound_ago_h=0)
        contatos.atualizar_contato(world.sw, c["id"], {"ultimo_inbound_at": (AGORA + timedelta(days=91)).isoformat()})
        r = run(av.executar_pedido(job(c2, i2), client=world.sw, enviar=out, agora=AGORA + timedelta(days=91, minutes=5)))
        assert r == "enviado" and len(out.enviados) == 2

    def test_a_failed_ask_does_not_count_toward_the_90_days(self, world):
        config(world)
        c = contato(world)
        i = interacao(world, c)
        assert run(av.executar_pedido(job(c, i), client=world.sw, enviar=Saida(RuntimeError("x")), agora=AGORA)) == "erro:RuntimeError"
        assert world.rows(av.T_PEDIDOS)[0]["status"] == "erro" and world.rows(av.T_PEDIDOS)[0]["erro"] == "RuntimeError"
        assert run(av.executar_pedido(job(c, i), client=world.sw, enviar=Saida(), agora=AGORA)) == "enviado"

    def test_negative_feedback_skips(self, world):
        config(world)
        c = contato(world)
        i = interacao(world, c)
        world.sw.table(av.T_FEEDBACK).insert({"org_id": ORG, "contato_id": c["id"], "nota": "like", "created_at": "2026-10-14T10:00:00+00:00"}).execute()
        world.sw.table(av.T_FEEDBACK).insert({"org_id": ORG, "contato_id": c["id"], "nota": "dislike", "created_at": "2026-10-15T10:00:00+00:00"}).execute()
        out = Saida()
        assert run(av.executar_pedido(job(c, i), client=world.sw, enviar=out, agora=AGORA)) == "ignorado:feedback_negativo"
        assert not out.enviados and not world.rows(av.T_PEDIDOS)

    def test_a_later_like_overrides_an_old_dislike(self, world):
        config(world)
        c = contato(world)
        i = interacao(world, c)
        world.sw.table(av.T_FEEDBACK).insert({"org_id": ORG, "contato_id": c["id"], "nota": "dislike", "created_at": "2026-10-10T10:00:00+00:00"}).execute()
        world.sw.table(av.T_FEEDBACK).insert({"org_id": ORG, "contato_id": c["id"], "nota": "like", "created_at": "2026-10-14T10:00:00+00:00"}).execute()
        assert run(av.executar_pedido(job(c, i), client=world.sw, enviar=Saida(), agora=AGORA)) == "enviado"

    def test_outside_the_24h_window_skips(self, world):
        config(world)
        c = contato(world, inbound_ago_h=25)
        i = interacao(world, c)
        out = Saida()
        assert run(av.executar_pedido(job(c, i), client=world.sw, enviar=out, agora=AGORA)) == "ignorado:fora_da_janela_24h"
        assert not out.enviados

    def test_never_inbound_is_outside_the_window(self, world):
        config(world)
        c = contato(world, ultimo_inbound_at=None)
        assert av.dentro_da_janela(world.rows("lais_contatos")[0], AGORA) is False

    @pytest.mark.parametrize("desfecho", ["em_andamento", "desqualificado", None])
    def test_only_a_qualificado_outcome_asks(self, world, desfecho):
        config(world)
        c = contato(world)
        i = interacao(world, c, desfecho)
        assert run(av.executar_pedido(job(c, i), client=world.sw, enviar=Saida(), agora=AGORA)) == "ignorado:desfecho_nao_qualificado"

    def test_no_review_link_skips(self, world):
        c = contato(world)
        i = interacao(world, c)
        assert run(av.executar_pedido(job(c, i), client=world.sw, enviar=Saida(), agora=AGORA)) == "ignorado:sem_link"

    def test_stale_gen_is_obsolete_and_sends_nothing(self, world):
        config(world)
        c = contato(world)
        i = interacao(world, c)
        out = Saida()
        assert run(av.executar_pedido(job(c, i, gen=c["gen"] + 1), client=world.sw, enviar=out, agora=AGORA)) == "obsoleto"
        assert not out.enviados

    def test_other_org_contato_is_obsolete(self, world):
        config(world)
        c = contato(world)
        i = interacao(world, c)
        j = job(c, i)
        j.payload["org_id"] = OTHER_ORG_ID
        assert run(av.executar_pedido(j, client=world.sw, enviar=Saida(), agora=AGORA)) == "obsoleto"


# ── the ask: hook through the REAL close paths ──────────────────────────────────────
class TestHookNosFechamentos:
    def _fechar(self, world, repo, *, desfecho, via):
        av.registrar()
        config(world)
        c = contato(world, inbound_ago_h=0)
        agents = FakeAgentsClient(resumo_script=[ResumoResult(resumo="ok", desfecho=desfecho)])
        i = contatos.abrir_interacao(world.sw, ORG, c)
        if via == "encerrar":
            res = TurnResult(conversation_id=str(uuid4()), partes=(), status="respondido", actions=(LaisAction("encerrar", 1, {"motivo": "lead_encerrou"}),))
            run(acoes.aplicar(world.sw, org_id=ORG, contato=c, result=res, lote_hash="l-" + via, agents_client=agents))
        else:
            run(acoes.fechar_interacao(world.sw, org_id=ORG, contato=c, interacao=i, agents_client=agents, conversation_id=str(uuid4())))
        return c

    def test_encerrar_with_qualificado_enqueues_the_ask(self, world, repo):
        self._fechar(world, repo, desfecho="qualificado", via="encerrar")
        jobs = [j for j in repo._jobs.values()] if hasattr(repo, "_jobs") else []
        assert len(jobs) == 1 and jobs[0].type == av.JOB_PEDIR and jobs[0].payload["gen"] == world.rows("lais_contatos")[0]["gen"]

    def test_encerrar_without_qualificado_enqueues_nothing(self, world, repo):
        self._fechar(world, repo, desfecho="em_andamento", via="encerrar")
        assert not list(getattr(repo, "_jobs", {}).values())

    def test_the_silence_close_never_asks(self, world, repo):
        self._fechar(world, repo, desfecho="qualificado", via="silencio")
        assert not list(getattr(repo, "_jobs", {}).values())

    def test_a_failing_hook_never_undoes_the_close(self, world, repo):
        av.registrar_repo(None)  # no repo: logged, not raised
        self._fechar(world, repo, desfecho="qualificado", via="encerrar")
        assert world.rows("lais_interacoes")[0]["encerrada_at"]


# ── config ────────────────────────────────────────────────────────────────────────
class TestConfig:
    def test_defaults_and_partial_save(self, world):
        assert av.obter_config(world.sw, ORG) == av.CONFIG_PADRAO
        av.salvar_config(world.sw, ORG, {"google_review_url": LINK})
        novo = av.salvar_config(world.sw, ORG, {"capi_ativo": True, "capi_pixel_id": PIXEL})
        assert novo["google_review_url"] == LINK and novo["capi_ativo"] is True and novo["capi_pixel_id"] == PIXEL
        assert av.salvar_config(world.sw, ORG, {"google_review_url": None})["google_review_url"] is None

    @pytest.mark.parametrize("valores", [{"google_review_url": "http://x.com/r"}, {"google_review_url": "javascript:alert(1)"},
                                         {"capi_pixel_id": "abc"}, {"capi_pixel_id": "123"}])
    def test_invalid_values_are_422(self, world, valores):
        with pytest.raises(AppException) as exc:
            av.salvar_config(world.sw, ORG, valores)
        assert exc.value.status_code == 422 and exc.value.code == "config_invalida"


# ── reviews: provider + sync + painel ────────────────────────────────────────────────
def reviews(n=3):
    return [Review(f"r{i}", f"Autor {i}", 5 - i % 3, f"texto {i}", datetime(2026, 10, 1 + i, 12, tzinfo=timezone.utc), f"https://g.co/{i}") for i in range(n)]


class TestAvaliacoes:
    def test_sync_is_idempotent_and_counts_new(self, world):
        config(world, gbp_location_id="accounts/1/locations/2")
        prov = FakeReviewsProvider(reviews(3))
        assert run(av.sincronizar(world.sw, ORG, prov, agora=AGORA)) == {"estado": "sincronizada", "novas": 3}
        assert len(world.rows(av.T_CACHE)) == 3
        prov.reviews = reviews(4)
        assert run(av.sincronizar(world.sw, ORG, prov, agora=AGORA + timedelta(hours=1))) == {"estado": "sincronizada", "novas": 1}
        assert len(world.rows(av.T_CACHE)) == 4

    def test_sync_is_throttled(self, world):
        config(world, gbp_location_id="accounts/1/locations/2")
        prov = FakeReviewsProvider(reviews(1))
        run(av.sincronizar(world.sw, ORG, prov, agora=AGORA))
        assert run(av.sincronizar(world.sw, ORG, prov, agora=AGORA + timedelta(minutes=5)))["estado"] == "recente"
        assert len(prov.chamadas) == 1

    def test_sync_states_without_location_or_credentials_or_on_error(self, world):
        config(world)
        assert run(av.sincronizar(world.sw, ORG, FakeReviewsProvider()))["estado"] == "sem_local"
        world.sw.set_table_data(av.T_CONFIG, [])
        config(world, gbp_location_id="accounts/1/locations/2")
        assert run(av.sincronizar(world.sw, ORG, NaoConfiguradoReviews()))["estado"] == "nao_configurado"
        assert run(av.sincronizar(world.sw, ORG, FakeReviewsProvider(erro=RuntimeError("boom"))))["estado"] == "erro"

    def test_factory_is_not_configured_without_a_token_resolver(self):
        assert isinstance(make_reviews_provider(ORG), NaoConfiguradoReviews)
        with pytest.raises(ReviewsNaoConfigurado):
            run(make_reviews_provider(ORG).listar("accounts/1/locations/2"))
        assert isinstance(make_reviews_provider(ORG, use_fake=True), FakeReviewsProvider)
        assert isinstance(make_reviews_provider(ORG, access_token_resolver=lambda o: "t"), RealGbpReviewsProvider)

    def test_real_provider_maps_the_gbp_v4_payload_and_pages(self):
        paginas = [
            {"reviews": [{"reviewId": "a", "starRating": "FIVE", "comment": "ótimo", "createTime": "2026-10-02T10:00:00Z",
                          "reviewer": {"displayName": "Fulano"}}], "nextPageToken": "p2"},
            {"reviews": [{"name": "accounts/1/locations/2/reviews/b", "starRating": "ONE"}, {"reviewId": "c", "starRating": "ZERO"}]},
        ]
        chamadas = []

        class Resp:
            status_code = 200

            def __init__(self, body):
                self._b = body

            def json(self):
                return self._b

        def http_get(url, headers, params, timeout):
            chamadas.append((url, headers["Authorization"], params.get("pageToken")))
            return Resp(paginas[len(chamadas) - 1])

        prov = RealGbpReviewsProvider(org_id=ORG, access_token_resolver=lambda o: "tok", http_get=http_get)
        out = run(prov.listar("accounts/1/locations/2"))
        assert [(r.external_id, r.nota) for r in out] == [("a", 5), ("b", 1)]  # ZERO has no usable rating
        assert chamadas[0][0].endswith("accounts/1/locations/2/reviews") and chamadas[0][1] == "Bearer tok" and chamadas[1][2] == "p2"
        assert review_de_api({"starRating": "FIVE"}, "x") is None

    def test_real_provider_without_a_token_is_not_configured(self):
        with pytest.raises(ReviewsNaoConfigurado):
            run(RealGbpReviewsProvider(org_id=ORG, access_token_resolver=lambda o: None).listar("accounts/1/locations/2"))


# ── CAPI ──────────────────────────────────────────────────────────────────────────────
def lead_meta(w: World, *, meta_id="9000000000000001", phone="(11) 98888-7777", email=" Ana@Exemplo.COM "):
    lead = w.sw.table("leads").insert({"id": str(uuid4()), "org_id": ORG, "meta_lead_id": meta_id}).execute().data[0]
    w.sw.table(capi.T_META_LEADS).insert({"id": meta_id, "org_id": ORG, "phone": phone, "email": email}).execute()
    return lead


def lead_comum(w: World):
    return w.sw.table("leads").insert({"id": str(uuid4()), "org_id": ORG, "meta_lead_id": None}).execute().data[0]


class TestHashing:
    def test_email_is_trimmed_lowercased_then_sha256(self):
        assert capi.hash_email("  Ana@Exemplo.COM ") == hashlib.sha256(b"ana@exemplo.com").hexdigest()
        assert capi.hash_email("sem-arroba") is None and capi.hash_email(None) is None

    @pytest.mark.parametrize("entrada", ["+55 (11) 98888-7777", "5511988887777", "(11) 98888-7777", "011988887777"])
    def test_phone_is_digits_with_country_code_then_sha256(self, entrada):
        assert capi.hash_telefone(entrada) == hashlib.sha256(b"5511988887777").hexdigest()

    def test_short_phone_is_not_hashed(self):
        assert capi.hash_telefone("123") is None and capi.hash_telefone(None) is None

    def test_the_payload_carries_only_hashes_and_the_lead_id(self, world):
        c = contato(world)
        ev = capi.montar_evento("lead_qualificado", "k1", AGORA, c, {"id": "9000000000000001", "phone": "11988887777", "email": "a@b.co"})
        ud = ev.user_data
        assert ud["lead_id"] == "9000000000000001" and len(ud["ph"][0]) == 64 and len(ud["em"][0]) == 64
        blob = repr(ev.como_payload())
        assert "11988887777" not in blob and "a@b.co" not in blob and ev.nome == "QualifiedLead"
        assert ev.como_payload()["action_source"] == "system_generated" and ev.event_time == int(AGORA.timestamp())


class TestCapi:
    def test_non_meta_contato_records_nothing_and_never_calls(self, world, repo, token):
        config(world, capi_ativo=True, capi_pixel_id=PIXEL)
        c = contato(world, lead_id=lead_comum(world)["id"])
        assert run(capi.registrar_evento(world.sw, ORG, c["id"], "lead_qualificado")) == {"estado": "nao_meta"}
        sem_lead = contato(world, lead_id=None)
        assert run(capi.registrar_evento(world.sw, ORG, sem_lead["id"], "lead_qualificado"))["estado"] == "nao_meta"
        assert not world.rows(capi.T_CAPI) and not repo._jobs

    def test_meta_lead_configured_is_queued_then_sent_hashed(self, world, repo, token):
        config(world, capi_ativo=True, capi_pixel_id=PIXEL)
        c = contato(world, lead_id=lead_meta(world)["id"])
        r = run(capi.registrar_evento(world.sw, ORG, c["id"], "lead_qualificado"))
        assert r["estado"] == "pendente" and len(repo._jobs) == 1
        (j,) = repo._jobs.values()
        fake = capi.FakeCapiProvider()
        assert run(capi.executar_envio(j, client=world.sw, provider_factory=lambda t: fake, agora=AGORA)) == "enviado"
        (pixel, ev), = fake.enviados
        assert pixel == PIXEL and ev.nome == "QualifiedLead" and ev.user_data["lead_id"] == "9000000000000001"
        assert ev.user_data["ph"] == [hashlib.sha256(b"5511988887777").hexdigest()]
        assert ev.user_data["em"] == [hashlib.sha256(b"ana@exemplo.com").hexdigest()]
        (row,) = world.rows(capi.T_CAPI)
        assert row["status"] == "enviado" and row["enviado_at"] and row["evento"] == "lead_qualificado"
        assert run(capi.executar_envio(j, client=world.sw, provider_factory=lambda t: fake)) == "ja_tratado" and len(fake.enviados) == 1

    @pytest.mark.parametrize("cfg,tem_token", [({}, True), ({"capi_ativo": True}, True), ({"capi_ativo": True, "capi_pixel_id": PIXEL}, False),
                                                ({"capi_ativo": False, "capi_pixel_id": PIXEL}, True)])
    def test_not_configured_is_stored_and_meta_is_never_called(self, world, repo, cfg, tem_token):
        config(world, **cfg)
        capi.registrar_token_resolver((lambda: "tok") if tem_token else (lambda: None))
        try:
            c = contato(world, lead_id=lead_meta(world)["id"])
            assert run(capi.registrar_evento(world.sw, ORG, c["id"], "visita_agendada", referencia="v1"))["estado"] == "nao_configurado"
        finally:
            capi.registrar_token_resolver(None)
        assert world.rows(capi.T_CAPI)[0]["status"] == "nao_configurado" and not repo._jobs

    def test_replay_is_idempotent(self, world, repo, token):
        config(world, capi_ativo=True, capi_pixel_id=PIXEL)
        c = contato(world, lead_id=lead_meta(world)["id"])
        run(capi.registrar_evento(world.sw, ORG, c["id"], "lead_qualificado"))
        assert run(capi.registrar_evento(world.sw, ORG, c["id"], "lead_qualificado"))["estado"] == "repetido"
        assert len(world.rows(capi.T_CAPI)) == 1 and len(repo._jobs) == 1

    def test_provider_failure_is_stored(self, world, repo, token):
        config(world, capi_ativo=True, capi_pixel_id=PIXEL)
        c = contato(world, lead_id=lead_meta(world)["id"])
        run(capi.registrar_evento(world.sw, ORG, c["id"], "lead_qualificado"))
        (j,) = repo._jobs.values()
        assert run(capi.executar_envio(j, client=world.sw, provider_factory=lambda t: capi.FakeCapiProvider(erro=RuntimeError("x")))) == "erro:RuntimeError"
        assert world.rows(capi.T_CAPI)[0]["status"] == "erro" and world.rows(capi.T_CAPI)[0]["erro"] == "RuntimeError"

    def test_config_turned_off_before_the_job_fires_never_calls_meta(self, world, repo, token):
        config(world, capi_ativo=True, capi_pixel_id=PIXEL)
        c = contato(world, lead_id=lead_meta(world)["id"])
        run(capi.registrar_evento(world.sw, ORG, c["id"], "lead_qualificado"))
        av.salvar_config(world.sw, ORG, {"capi_ativo": False})
        (j,) = repo._jobs.values()
        fake = capi.FakeCapiProvider()
        assert run(capi.executar_envio(j, client=world.sw, provider_factory=lambda t: fake)) == "nao_configurado" and not fake.enviados

    def test_no_queue_marks_the_row_instead_of_losing_it(self, world, token):
        capi.registrar_repo(None)
        config(world, capi_ativo=True, capi_pixel_id=PIXEL)
        c = contato(world, lead_id=lead_meta(world)["id"])
        assert run(capi.registrar_evento(world.sw, ORG, c["id"], "lead_qualificado"))["estado"] == "erro"
        assert world.rows(capi.T_CAPI)[0]["erro"] == "sem_fila"

    def test_unknown_event_never_raises(self, world, repo, token):
        c = contato(world)
        assert run(capi.registrar_evento(world.sw, ORG, c["id"], "bogus"))["estado"] == "erro"

    def test_resposta_cliente_needs_a_recent_reengajamento_and_is_once_per_reengajamento(self, world, repo, token):
        config(world, capi_ativo=True, capi_pixel_id=PIXEL)
        c = contato(world, lead_id=lead_meta(world)["id"])
        assert run(capi.registrar_resposta(world.sw, ORG, c, agora=AGORA))["estado"] == "sem_reengajamento"
        ev = world.sw.table("lais_eventos").insert({"id": str(uuid4()), "org_id": ORG, "tipo": "reengajamento", "contato_id": c["id"],
                                                    "created_at": (AGORA - timedelta(days=1)).isoformat()}).execute().data[0]
        assert run(capi.registrar_resposta(world.sw, ORG, c, agora=AGORA))["estado"] == "pendente"
        assert run(capi.registrar_resposta(world.sw, ORG, c, agora=AGORA))["estado"] == "repetido"
        assert world.rows(capi.T_CAPI)[0]["dedupe_key"].endswith(ev["id"])

    def test_resposta_cliente_older_than_7_days_is_skipped(self, world, repo, token):
        config(world, capi_ativo=True, capi_pixel_id=PIXEL)
        c = contato(world, lead_id=lead_meta(world)["id"])
        world.sw.table("lais_eventos").insert({"id": str(uuid4()), "org_id": ORG, "tipo": "reengajamento", "contato_id": c["id"],
                                               "created_at": (AGORA - timedelta(days=8)).isoformat()}).execute()
        assert run(capi.registrar_resposta(world.sw, ORG, c, agora=AGORA))["estado"] == "sem_reengajamento"

    def test_real_provider_posts_one_hashed_event_to_the_pixel(self, world):
        postadas = []

        def post(path, *, access_token, data, **kw):
            postadas.append((path, access_token, data))
            return {"events_received": 1}

        c = contato(world)
        ev = capi.montar_evento("visita_agendada", "k", AGORA, c, {"id": "9000000000000001", "phone": FONE, "email": None})
        assert run(capi.RealMetaCapiProvider(access_token="tok", post=post).enviar(PIXEL, ev)) == {"events_received": 1}
        (path, tok, data), = postadas
        assert path == f"{PIXEL}/events" and tok == "tok" and '"event_name": "Schedule"' in data["data"] and FONE not in data["data"]

    def test_factory_returns_none_without_a_token(self):
        assert capi.make_capi_provider(access_token=None) is None
        assert isinstance(capi.make_capi_provider(access_token="t"), capi.RealMetaCapiProvider)
        assert isinstance(capi.make_capi_provider(access_token=None, use_fake=True), capi.FakeCapiProvider)


class TestQualificarLeadDispara:
    def test_qualificar_lead_handler_records_the_signal_for_a_meta_lead(self, world, repo, token):
        from app.services import lais_envio_service as envio

        config(world, capi_ativo=True, capi_pixel_id=PIXEL)
        c = contato(world, lead_id=lead_meta(world)["id"], status_envio="enviado")
        res = TurnResult(conversation_id=str(uuid4()), partes=(), status="respondido", actions=(LaisAction("qualificar_lead", 1, {}),))
        h = dict(acoes.HANDLERS)
        acoes.registrar_handler("qualificar_lead", envio._h_qualificar_lead, registro=h)  # noqa: SLF001
        run(acoes.aplicar(world.sw, org_id=ORG, contato=c, result=res, lote_hash="q1", handlers=h))
        assert [r["evento"] for r in world.rows(capi.T_CAPI)] == ["lead_qualificado"]
