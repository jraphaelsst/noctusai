"""S3 — POST /api/public/ask/{app_slug}: pipeline, hardening and the no-log proof.

Every dependency is injected through the route's own seams (service +
config dependency overrides, constructor DI) — no monkeypatching. The S4
post-filter is a test-owned stand-in with the FIXED interface
(`ResultadoPosfiltro`, `aplicar_posfiltro(...)`); the real one lands in S4.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from noctusai_lib.api.audit import AuditMiddleware, FakeAuditSink
from noctusai_lib.api.middleware import (
    CorrelationIdMiddleware,
    MaxBodySizeMiddleware,
    RequestLoggingMiddleware,
)
from noctusai_lib.integrations.risk_classifier import FakeRiskClassifier

from app.public_ask import limiar
from app.public_ask.breaker import DailyCostBreaker
from app.public_ask.router import (
    BODY_LIMIT_PATTERN,
    MAX_BODY_BYTES,
    PublicAskConfig,
    get_public_ask_config_dep,
    get_public_ask_service_dep,
    router,
)
from app.public_ask.safety_pack import load_engine
from app.public_ask.service import PublicAskService, Snippet
from app.rate_limit import limiter

SENTINEL = "xqzsentinelfrase"
URL = "/api/public/ask/limiar"
ENGINE = load_engine()


# -- test-owned stand-in for the S4 post-filter (fixed interface) ----------
@dataclass(frozen=True)
class ResultadoPosfiltro:
    ok: bool
    texto: str
    caminhos: tuple[str, ...]
    motivos: tuple[str, ...]


def stand_in_posfiltro(resposta, caminhos, *, fonte_ids, fonte_ids_recuperadas, pacote):
    if "REJEITAR" in resposta or not set(fonte_ids) <= set(fonte_ids_recuperadas):
        return ResultadoPosfiltro(False, "TEXTO-FALLBACK", ("quero_pensar_mais",), ("teste",))
    return ResultadoPosfiltro(True, resposta, tuple(caminhos), ())


class Gen:
    """Scripted generator seam; records kwargs (never asserts on text)."""

    def __init__(self, reply="Uma reflexao calma.\nFONTES: doc-1", exc=None):
        self.reply, self.exc, self.calls = reply, exc, []

    async def __call__(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if self.exc:
            raise self.exc
        return self.reply


async def _retrieve(tema):
    return [Snippet("doc-1", "Titulo", "trecho editorial")]


async def _retrieve_empty(tema):
    return []


def make_service(*, classifier, gen=None, retrieve=_retrieve, on_outage="amarelo_editorial", cap=100):
    return PublicAskService(
        engine=ENGINE,
        classifier=classifier,
        retrieve=retrieve,
        generate=gen or Gen(),
        posfiltro=stand_in_posfiltro,
        pacote=object(),
        breaker=DailyCostBreaker(cap),
        on_outage=on_outage,
    )


def build_app(service, *, enabled=True, sink=None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.dependency_overrides[get_public_ask_service_dep] = lambda: service
    app.dependency_overrides[get_public_ask_config_dep] = lambda: PublicAskConfig(enabled=enabled)
    # the seed middleware stack, same order as create_product_app
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(AuditMiddleware, sink=sink or FakeAuditSink(), product_slug="agents", enabled=True)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=1_000_000, path_overrides={BODY_LIMIT_PATTERN: MAX_BODY_BYTES})
    return app


def body(texto, tema="relacionamento", versao="triagem-app-1"):
    return {"tema": tema, "texto": texto, "versao_triagem": versao}


def clf(**scripted):
    c = FakeRiskClassifier()
    for text, (nivel, sinais) in scripted.items():
        c.add(text, nivel, sinais)
    return c


# ------------------------------------------------------------------ branches
def test_verde_generates_with_cache_off_and_returns_server_version():
    texto = f"{SENTINEL} quero pensar sobre domingos"
    gen = Gen()
    svc = make_service(classifier=clf(**{texto: ("verde", ())}), gen=gen)
    r = TestClient(build_app(svc)).post(URL, json=body(texto))
    assert r.status_code == 200
    j = r.json()
    assert j["nivel"] == "verde" and j["resposta"] == "Uma reflexao calma."
    assert j["fonte_ids"] == ["doc-1"] and j["caminhos"] == list(limiar.CAMINHOS_GERACAO)
    assert j["versao_triagem"] == ENGINE.versao != "triagem-app-1"
    assert j["versao_prompt"] == limiar.PROMPT_VERSION
    (messages, kwargs), = gen.calls
    assert kwargs["cache"] is False and 0 < kwargs["max_tokens"] <= 400
    assert "<<<TEXTO-" in messages[1]["content"] and texto in messages[1]["content"]
    assert texto not in messages[0]["content"]


def test_rules_vermelho_no_classifier_no_generation():
    c, gen = clf(), Gen()
    r = TestClient(build_app(make_service(classifier=c, gen=gen))).post(
        URL, json=body(f"{SENTINEL} quero me matar")
    )
    j = r.json()
    assert j["nivel"] == "vermelho" and j["rota"] == "seguranca" and j["tipo"] == "vida"
    assert "resposta" not in j and not gen.calls and not c.calls


def test_classifier_vermelho_overrides_rules_verde():
    texto = f"{SENTINEL} frase sutil"
    gen = Gen()
    svc = make_service(classifier=clf(**{texto: ("vermelho", ("autolesao",))}), gen=gen)
    j = TestClient(build_app(svc)).post(URL, json=body(texto)).json()
    assert (j["nivel"], j["rota"]) == ("vermelho", "seguranca") and not gen.calls


def test_classifier_violencia_route_type():
    texto = f"{SENTINEL} situacao em casa"
    svc = make_service(classifier=clf(**{texto: ("violencia", ("agressao",))}))
    j = TestClient(build_app(svc)).post(URL, json=body(texto)).json()
    assert (j["nivel"], j["rota"], j["tipo"]) == ("violencia", "seguranca", "violencia")


def test_amarelo_is_editorial_without_generation():
    texto = f"{SENTINEL} ando sem vontade de nada"
    gen = Gen()
    svc = make_service(classifier=clf(**{texto: ("amarelo", ("sofrimento_persistente",))}), gen=gen)
    j = TestClient(build_app(svc)).post(URL, json=body(texto)).json()
    assert j["nivel"] == "amarelo" and j["resposta"] == limiar.TEXTO_EDITORIAL
    assert j["caminhos"] == [] and j["rota"] == "editorial" and not gen.calls


@pytest.mark.parametrize(
    "on_outage, nivel, rota", [("amarelo_editorial", "amarelo", "editorial"), ("seguranca", "vermelho", "seguranca")]
)
def test_classifier_outage_follows_config_and_never_generates(on_outage, nivel, rota):
    gen = Gen()
    svc = make_service(classifier=clf(), gen=gen, on_outage=on_outage)  # unknown text => indeterminado
    j = TestClient(build_app(svc)).post(URL, json=body(f"{SENTINEL} nao classificado")).json()
    assert (j["nivel"], j["rota"]) == (nivel, rota) and not gen.calls


def test_outage_never_beats_rules_red():
    svc = make_service(classifier=clf(), on_outage="amarelo_editorial")
    j = TestClient(build_app(svc)).post(URL, json=body("quero morrer")).json()
    assert j["nivel"] == "vermelho"


def test_invalid_outage_config_refused():
    with pytest.raises(ValueError):
        make_service(classifier=clf(), on_outage="whatever")  # type: ignore[arg-type]


def test_no_retrieval_means_editorial_not_improvisation():
    texto = f"{SENTINEL} verde sem base"
    gen = Gen()
    svc = make_service(classifier=clf(**{texto: ("verde", ())}), gen=gen, retrieve=_retrieve_empty)
    j = TestClient(build_app(svc)).post(URL, json=body(texto)).json()
    assert j["resposta"] == limiar.TEXTO_EDITORIAL and not gen.calls


def test_postfilter_rejection_returns_its_fallback_without_sources():
    texto = f"{SENTINEL} verde rejeitado"
    svc = make_service(classifier=clf(**{texto: ("verde", ())}), gen=Gen(reply="REJEITAR isto"))
    j = TestClient(build_app(svc)).post(URL, json=body(texto)).json()
    assert j["resposta"] == "TEXTO-FALLBACK" and j["fonte_ids"] == []


def test_cited_source_outside_retrieved_set_is_rejected():
    texto = f"{SENTINEL} verde fonte falsa"
    svc = make_service(classifier=clf(**{texto: ("verde", ())}), gen=Gen(reply="ok\nFONTES: inventada"))
    j = TestClient(build_app(svc)).post(URL, json=body(texto)).json()
    assert j["resposta"] == "TEXTO-FALLBACK"


def test_breaker_tripped_gives_editorial_not_an_error():
    c = clf(**{f"{SENTINEL} um": ("verde", ()), f"{SENTINEL} dois": ("verde", ())})
    svc = make_service(classifier=c, cap=1)
    tc = TestClient(build_app(svc))
    assert tc.post(URL, json=body(f"{SENTINEL} um")).json()["nivel"] == "verde"
    r = tc.post(URL, json=body(f"{SENTINEL} dois"))
    assert r.status_code == 200 and r.json()["resposta"] == limiar.TEXTO_EDITORIAL
    # rules-red still answers when the breaker is spent (free, safety-critical)
    assert tc.post(URL, json=body("quero me matar")).json()["rota"] == "seguranca"


def test_breaker_resets_next_day():
    day = [date(2026, 10, 4)]
    b = DailyCostBreaker(1, today=lambda: day[0])
    assert b.try_acquire() and not b.try_acquire()
    day[0] += timedelta(days=1)
    assert b.try_acquire()


def test_levels_are_pinned_to_the_pack_order():
    assert {n: i for i, n in enumerate(limiar.LABELS.niveis)} == ENGINE_ORDEM()


def ENGINE_ORDEM():
    import json

    from app.public_ask.safety_pack.engine import PACK_DIR

    return json.loads((PACK_DIR / "regras.json").read_text())["triagem"]["ordem_nivel"]


# ---------------------------------------------------------------- hardening
def test_disabled_flag_is_404_and_unknown_slug_is_404():
    svc = make_service(classifier=clf())
    assert TestClient(build_app(svc, enabled=False)).post(URL, json=body("oi")).status_code == 404
    assert TestClient(build_app(svc)).post("/api/public/ask/outro", json=body("oi")).status_code == 404


def test_anonymous_access_works_only_when_enabled():
    texto = f"{SENTINEL} anon"
    svc = make_service(classifier=clf(**{texto: ("verde", ())}))
    assert TestClient(build_app(svc)).post(URL, json=body(texto)).status_code == 200  # no auth header
    assert TestClient(build_app(svc, enabled=False)).post(URL, json=body(texto)).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"tema": "nada", "texto": "oi", "versao_triagem": "v"},
        {"tema": "amizades", "texto": "", "versao_triagem": "v"},
        {"tema": "amizades", "texto": "x" * 601, "versao_triagem": "v"},
        {"tema": "amizades", "texto": "oi", "versao_triagem": "v", "extra": 1},
        {"tema": "amizades", "texto": 12, "versao_triagem": "v"},
        {"tema": "amizades", "texto": "   ", "versao_triagem": "v"},
        {"texto": "oi"},
        [1, 2],
    ],
)
def test_validation_failure_is_custom_400_without_echo(payload):
    r = TestClient(build_app(make_service(classifier=clf()))).post(URL, json=payload)
    assert r.status_code == 400 and r.json() == {"code": "entrada_invalida"}


def test_malformed_json_is_400():
    r = TestClient(build_app(make_service(classifier=clf()))).post(
        URL, content=b"{not json " + SENTINEL.encode(), headers={"content-type": "application/json"}
    )
    assert r.status_code == 400 and SENTINEL not in r.text


def test_body_over_2kb_rejected_before_parsing():
    gen = Gen()
    r = TestClient(build_app(make_service(classifier=clf(), gen=gen))).post(
        URL, content=b"x" * (MAX_BODY_BYTES + 1), headers={"content-type": "application/json"}
    )
    assert r.status_code == 413 and not gen.calls


def test_rate_limit_5_per_minute_per_ip():
    texto = f"{SENTINEL} rl"
    tc = TestClient(build_app(make_service(classifier=clf(**{texto: ("verde", ())}))))
    codes = [tc.post(URL, json=body(texto)).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]
    other = tc.post(URL, json=body(texto), headers={"cf-connecting-ip": "203.0.113.9"})
    assert other.status_code == 200  # a different visitor has its own bucket


def test_router_declares_no_admin_surface():
    assert [r.path for r in router.routes] == ["/api/public/ask/{app_slug}"]
    assert all(r.methods == {"POST"} for r in router.routes)


# -------------------------------------------------------------- main app wiring
def test_main_app_mounts_route_default_off_and_registers_2kb_cap():
    from app.config import settings
    from app.main import app

    assert settings.public_ask_enabled is False
    assert any(getattr(r, "path", "") == "/api/public/ask/{app_slug}" for r in app.routes)
    r = TestClient(app).post(URL, json=body("oi"))
    assert r.status_code == 404  # flag off in the suite env: unreachable
    big = TestClient(app).post(URL, content=b"x" * 3000, headers={"content-type": "application/json"})
    assert big.status_code == 413  # the real app carries the 2 KB override (default would be 1 MB)


# ----------------------------------------------------------- no-log proof
class SpyGen(Gen):
    pass


def _all_log_text(caplog) -> str:
    parts = []
    for rec in caplog.records:
        parts.append(rec.getMessage())
        parts.append(repr(rec.__dict__))
        if rec.exc_text:
            parts.append(rec.exc_text)
    return "\n".join(parts) + "\n" + caplog.text


class ExplodingClassifier:
    async def classify(self, text, *, labels, context=None):
        raise RuntimeError(f"provider echoed: {text}")


def test_sentinel_appears_nowhere_on_any_branch(caplog):
    caplog.set_level(logging.DEBUG)
    sink = FakeAuditSink()
    bodies: list[str] = []

    def run(svc, payload, *, enabled=True, n=1):
        tc = TestClient(build_app(svc, enabled=enabled, sink=sink))
        for _ in range(n):
            r = tc.post(URL, json=payload) if not isinstance(payload, bytes) else tc.post(
                URL, content=payload, headers={"content-type": "application/json"}
            )
            bodies.append(r.text)
        return r

    verde = f"{SENTINEL} verde"
    amarelo = f"{SENTINEL} amarelo"
    sc = clf(**{verde: ("verde", ()), amarelo: ("amarelo", ())})
    run(make_service(classifier=sc), body(verde))                                   # verde
    run(make_service(classifier=sc), body(amarelo))                                 # amarelo
    run(make_service(classifier=sc), body(f"{SENTINEL} quero me matar"))            # vermelho (rules)
    run(make_service(classifier=clf()), body(f"{SENTINEL} sem rotulo"))             # outage -> editorial
    run(make_service(classifier=clf(), on_outage="seguranca"), body(f"{SENTINEL} sem rotulo 2"))  # outage -> seguranca
    run(make_service(classifier=ExplodingClassifier()), body(f"{SENTINEL} classifier crash"))
    run(make_service(classifier=sc, gen=Gen(exc=RuntimeError(f"llm echoed {verde}"))), body(verde))  # LLM error
    run(make_service(classifier=sc, retrieve=_retrieve_empty), body(verde))         # no base
    run(make_service(classifier=sc, cap=0), body(verde))                            # breaker
    run(make_service(classifier=sc), {"tema": SENTINEL, "texto": SENTINEL, "versao_triagem": "v", SENTINEL: 1})  # 422-style
    run(make_service(classifier=sc), (b"{" + SENTINEL.encode()))                    # malformed JSON
    run(make_service(classifier=sc), body(verde), enabled=False)                    # disabled
    run(make_service(classifier=sc), body(verde), n=6)                              # rate limited (429s)
    run(make_service(classifier=sc), b'{"texto":"' + SENTINEL.encode() * 300 + b'"}')  # oversize (413)

    assert any("429" in b or "Rate limit" in b for b in bodies)  # the limited branch was really hit
    for b in bodies:
        assert SENTINEL not in b.lower()
    assert SENTINEL not in _all_log_text(caplog).lower()
    assert SENTINEL not in repr(sink.entries).lower()
    assert sink.entries  # the audit sink was live, and still never saw text


def test_llm_cache_and_usage_sink_never_see_the_text():
    """Through the REAL seed `chat_completion`: cache enabled platform-wide, a
    spy backend + usage sink — `cache=False` must keep the text out of both."""
    import asyncio

    from noctusai_lib.integrations.llm import chat_completion
    from noctusai_lib.integrations.llm.client import _provider_cache, _reset_for_testing, configure_llm
    from noctusai_lib.integrations.llm.config import LLMConfig
    from noctusai_lib.integrations.llm.providers import FakeProvider

    class SpyCache:
        def __init__(self):
            self.ops: list[tuple] = []

        async def get(self, key):
            self.ops.append(("get", key))

        async def setex(self, key, ttl, value):
            self.ops.append(("setex", key, value))

        async def delete(self, *keys):
            self.ops.append(("delete", keys))
            return 0

    class SpySink:
        def __init__(self):
            self.events = []

        async def record(self, event):
            self.events.append(event)

    cache, sink = SpyCache(), SpySink()
    texto = f"{SENTINEL} verde cache"
    provider = FakeProvider(chat_responses=["Reflexao.\nFONTES: doc-1"])
    configure_llm(
        LLMConfig(
            key_provider=lambda provider, org_id=None: "k",
            default_provider="fake",
            cache_enabled=True,
            cache_backend=cache,
            usage_sink=sink,
        )
    )
    _provider_cache["fake"] = provider
    try:
        svc = PublicAskService(
            engine=ENGINE,
            classifier=clf(**{texto: ("verde", ())}),
            retrieve=_retrieve,
            generate=chat_completion,
            posfiltro=stand_in_posfiltro,
            pacote=object(),
            breaker=DailyCostBreaker(10),
            model="m",
            provider="fake",
        )
        j = TestClient(build_app(svc)).post(URL, json=body(texto)).json()
    finally:
        _reset_for_testing()
    assert j["resposta"] == "Reflexao."
    assert provider.calls  # the model WAS called ...
    assert cache.ops == []  # ... and the cache was neither read nor written
    assert SENTINEL not in repr(sink.events).lower()


# ------------------------------------------- integration: the REAL post-filter
def _real_service(reply, texto):
    from app.public_ask.postfilter import aplicar_posfiltro, pacote_posfiltro_padrao

    return PublicAskService(
        engine=ENGINE,
        classifier=clf(**{texto: ("verde", ())}),
        retrieve=_retrieve,
        generate=Gen(reply=reply),
        posfiltro=aplicar_posfiltro,
        pacote=pacote_posfiltro_padrao(),
        breaker=DailyCostBreaker(10),
    )


def _good_answer() -> str:
    from tests.public_ask.test_postfilter import BONS

    return BONS[0]


def test_real_postfilter_passes_a_good_verde_answer():
    texto = f"{SENTINEL} real bom"
    j = TestClient(build_app(_real_service(_good_answer() + "\nFONTES: doc-1", texto))).post(
        URL, json=body(texto)
    ).json()
    assert j["nivel"] == "verde" and j["resposta"] == _good_answer()
    assert j["caminhos"] == ["quero_pensar_mais", "prefiro_fazer_algo_agora"]
    assert j["fonte_ids"] == ["doc-1"] and "rota" not in j


def test_real_postfilter_falls_back_on_a_bonding_phrase():
    texto = f"{SENTINEL} real vinculo"
    reply = _good_answer() + " Estou aqui com você.\nFONTES: doc-1"
    j = TestClient(build_app(_real_service(reply, texto))).post(URL, json=body(texto)).json()
    assert j["rota"] == "fallback" and j["fonte_ids"] == []
    assert "Estou aqui" not in j["resposta"]
