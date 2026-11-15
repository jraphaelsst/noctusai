"""Platform prompt registry: the reader, the call helpers (chat / vision / transcription) routed through the seed LLM
seam with FakeProviders for BOTH vendors, the measurement, and the Real adapter against a mock PostgREST client."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.llm import registry as llm_registry
from noctusai_lib.integrations.llm.client import _reset_for_testing, configure_llm
from noctusai_lib.integrations.llm.config import LLMConfig
from noctusai_lib.integrations.llm.providers.fake_provider import FakeProvider
from noctusai_lib.integrations.prompt_registry import (
    FakePromptRegistry,
    PromptEntry,
    RegistroIAIndisponivel,
    SupabasePromptRegistry,
    calcular_estatisticas,
    chamar_ia,
    chamar_ia_visao,
    configure_prompt_registry,
    get_prompt_registry,
    invalidar_cache,
    make_prompt_registry,
    modelos_permitidos,
    prompt_e_modelo,
    transcrever_ia,
)
from noctusai_lib.integrations.prompt_registry.api import TTL_S

CHAVE = "agents.eval_improver"


def _row(**kw) -> PromptEntry:
    base = dict(chave=CHAVE, nome="n", descricao="d", vendor="anthropic", modelo="claude-opus-5-5", prompt="PROMPT")
    return PromptEntry(**{**base, **kw})


class _Fakes:
    """Both vendors registered in the seed provider registry as FakeProviders (the real seam, Fake adapters)."""

    def __enter__(self):
        self._old = dict(llm_registry._PROVIDERS)
        _reset_for_testing()
        configure_llm(LLMConfig(key_provider=lambda provider, org: "k"))
        self.anthropic = FakeProvider(chat_responses=["resposta-anthropic"], chat_usage=[(1000, 200)],
                                      usage_provider="anthropic")
        self.openai = FakeProvider(chat_responses=["resposta-openai"], chat_usage=[(500, 100)],
                                   usage_provider="openai", transcription_responses=["transcrito"],
                                   vision_responses=["vista"])
        llm_registry.register("anthropic", lambda: self.anthropic)
        llm_registry.register("openai", lambda: self.openai)
        return self

    def __exit__(self, *exc):
        _reset_for_testing()
        llm_registry._PROVIDERS.clear()
        llm_registry._PROVIDERS.update(self._old)


@pytest.fixture(autouse=True)
def _limpo():
    invalidar_cache()
    configure_prompt_registry(None)
    yield
    invalidar_cache()
    configure_prompt_registry(None)


class TestReader:
    def test_reads_prompt_model_vendor(self):
        assert prompt_e_modelo(CHAVE, registry=FakePromptRegistry([_row()])) == ("PROMPT", "claude-opus-5-5", "anthropic")

    def test_missing_key_raises(self):
        with pytest.raises(RegistroIAIndisponivel, match="not registered"):
            prompt_e_modelo("nao.existe", registry=FakePromptRegistry())

    def test_inactive_row_raises(self):
        with pytest.raises(RegistroIAIndisponivel, match="inactive"):
            prompt_e_modelo(CHAVE, registry=FakePromptRegistry([_row(ativo=False)]))

    def test_unreadable_registry_raises_not_falls_back(self):
        r = FakePromptRegistry([_row()])
        r.falha = ConnectionError("db down")
        with pytest.raises(RegistroIAIndisponivel, match="could not be read"):
            prompt_e_modelo(CHAVE, registry=r)

    def test_unconfigured_registry_is_a_loud_error(self):
        with pytest.raises(RegistroIAIndisponivel, match="no prompt registry configured"):
            get_prompt_registry()
        with pytest.raises(RegistroIAIndisponivel):
            prompt_e_modelo(CHAVE)

    def test_configured_registry_is_cached_briefly_and_invalidated(self):
        r = FakePromptRegistry([_row()])
        configure_prompt_registry(r)
        t = 100.0
        prompt_e_modelo(CHAVE, agora=lambda: t)
        prompt_e_modelo(CHAVE, agora=lambda: t + 5)
        assert r.leituras == 1
        prompt_e_modelo(CHAVE, agora=lambda: t + TTL_S + 1)
        assert r.leituras == 2
        invalidar_cache(CHAVE)
        prompt_e_modelo(CHAVE, agora=lambda: t + TTL_S + 2)
        assert r.leituras == 3


@pytest.mark.anyio
class TestChamarIa:
    @pytest.fixture
    def anyio_backend(self):
        return "asyncio"

    async def test_anthropic_row_routes_to_anthropic_and_is_measured(self):
        reg = FakePromptRegistry([_row()])
        with _Fakes() as f:
            r = await chamar_ia(CHAVE, [{"role": "user", "content": "falhas..."}], registry=reg)
        assert (r.texto, r.vendor, r.modelo) == ("resposta-anthropic", "anthropic", "claude-opus-5-5")
        assert not f.openai.calls
        call = f.anthropic.calls[0]
        assert call["model"] == "claude-opus-5-5"
        assert call["messages"][0] == {"role": "system", "content": "PROMPT"}
        assert call["messages"][1]["content"] == "falhas..."
        (m,) = reg.chamadas
        assert (m.chave, m.vendor, m.modelo, m.ok, m.capacidade) == (CHAVE, "anthropic", "claude-opus-5-5", True, "chat")
        assert (m.tokens_entrada, m.tokens_saida) == (1000, 200) and m.custo_usd and m.custo_usd > 0
        assert m.latencia_ms >= 0 and m.erro is None

    async def test_row_switched_to_openai_routes_the_next_call_to_openai(self):
        reg = FakePromptRegistry([_row()])
        reg.atualizar(CHAVE, vendor="openai", modelo="gpt-5.6-sol")
        with _Fakes() as f:
            r = await chamar_ia(CHAVE, [{"role": "user", "content": "x"}], registry=reg)
        assert (r.texto, r.vendor, r.modelo) == ("resposta-openai", "openai", "gpt-5.6-sol")
        assert not f.anthropic.calls and f.openai.calls[0]["model"] == "gpt-5.6-sol"
        assert (reg.chamadas[0].vendor, reg.chamadas[0].tokens_entrada) == ("openai", 500)

    async def test_uses_the_configured_registry_by_default(self):
        configure_prompt_registry(FakePromptRegistry([_row(vendor="openai", modelo="gpt-5.6-sol")]))
        with _Fakes() as f:
            r = await chamar_ia(CHAVE, [])
        assert r.vendor == "openai" and f.openai.calls

    async def test_provider_failure_is_measured_and_reraised(self):
        reg = FakePromptRegistry([_row()])

        async def boom(messages, **kw):
            raise TimeoutError("vendor down")

        with pytest.raises(TimeoutError):
            await chamar_ia(CHAVE, [], registry=reg, chat=boom)
        (m,) = reg.chamadas
        assert m.ok is False and m.erro == "TimeoutError" and m.tokens_entrada is None

    async def test_a_lost_measurement_never_replaces_the_result(self, caplog):
        reg = FakePromptRegistry([_row()])

        class Quebrado(FakePromptRegistry):
            def registrar_chamada(self, chamada):
                raise OSError("disk")

        q = Quebrado([_row()])
        with _Fakes():
            r = await chamar_ia(CHAVE, [], registry=q)
        assert r.texto == "resposta-anthropic" and "could not record the measurement" in caplog.text
        assert reg.chamadas == []

    async def test_missing_row_raises_before_any_call(self):
        reg = FakePromptRegistry()
        with _Fakes() as f, pytest.raises(RegistroIAIndisponivel):
            await chamar_ia("nao.existe", [], registry=reg)
        assert not f.anthropic.calls and not f.openai.calls and reg.chamadas == []

    async def test_vision_and_transcription_route_by_the_row_and_are_measured(self):
        reg = FakePromptRegistry([
            _row(chave="crm.le_foto", vendor="openai", modelo="gpt-5.6-sol", capacidade="vision", prompt="descreva"),
            _row(chave="crm.ouve", vendor="openai", modelo="whisper-1", capacidade="transcription", prompt="vocab"),
        ])
        with _Fakes() as f:
            v = await chamar_ia_visao("crm.le_foto", b"\x89PNG", registry=reg)
            t = await transcrever_ia("crm.ouve", b"ID3", registry=reg)
        assert (v.texto, t.texto) == ("vista", "transcrito")
        assert {c["method"] for c in f.openai.calls} >= {"analyze_image", "transcribe_audio"}
        assert [(m.chave, m.capacidade, m.ok) for m in reg.chamadas] == [("crm.le_foto", "vision", True), ("crm.ouve", "transcription", True)]


class TestChaveFormat:
    @pytest.mark.parametrize("ruim", ["Agents.Eval", "nosnolimiar", "agents-eval", "agents..x", "1agents.x", "a/b"])
    def test_non_logical_ids_are_refused_before_any_read(self, ruim):
        reg = FakePromptRegistry([_row(chave=ruim)])
        if ruim == "nosnolimiar":  # a single lowercase segment is a valid id shape
            assert prompt_e_modelo(ruim, registry=reg)
            return
        with pytest.raises(RegistroIAIndisponivel, match="logical id"):
            prompt_e_modelo(ruim, registry=reg)
        assert reg.leituras == 0


class TestCatalogAndStats:
    def test_catalog_lists_both_vendors_per_capability(self):
        assert "claude-opus-5-5" in {m["id"] for m in modelos_permitidos("anthropic")}
        assert "gpt-5.6-sol" in {m["id"] for m in modelos_permitidos("openai")}
        assert "whisper-1" in {m["id"] for m in modelos_permitidos("openai", "transcription")}

    def test_stats(self):
        e = calcular_estatisticas([
            {"vendor": "a", "modelo": "m", "custo_usd": 0.01, "latencia_ms": 100, "ok": True},
            {"vendor": "a", "modelo": "m", "custo_usd": None, "latencia_ms": 900, "ok": False},
            {"vendor": "a", "modelo": "m", "custo_usd": 0.03, "latencia_ms": 300, "ok": True},
        ])
        assert e[0]["n"] == 3 and e[0]["p50_latencia_ms"] == 300 and abs(e[0]["custo_medio_usd"] - 0.02) < 1e-9


class _Q:
    def __init__(self, log, rows):
        self.log, self.rows = log, rows

    def __getattr__(self, name):
        def f(*a, **k):
            self.log.append((name, a, k))
            return self
        return f

    def execute(self):
        class R:
            data = self.rows
        return R


class TestReal:
    def test_reads_and_writes_the_public_tables_through_the_core_client(self):
        log: list = []
        row = {"chave": CHAVE, "nome": "n", "descricao": "", "vendor": "openai", "modelo": "gpt-5.6-sol", "prompt": "P",
               "ativo": True, "capacidade": "chat", "atualizado_em": "2026-11-08T10:00:00Z", "atualizado_por": None}

        class Client:
            def table(self, name):
                log.append(("table", (name,), {}))
                return _Q(log, [row])

        reg = make_prompt_registry(lambda: Client())
        assert isinstance(reg, SupabasePromptRegistry)
        e = reg.obter(CHAVE)
        assert (e.vendor, e.modelo, e.atualizado_em.tzinfo is not None) == ("openai", "gpt-5.6-sol", True)
        reg.atualizar(CHAVE, vendor="anthropic", modelo="claude-opus-5-5", prompt="N", actor=None)
        upd = next(a for n, a, k in log if n == "update")[0]
        assert upd["vendor"] == "anthropic" and upd["prompt"] == "N"
        assert [x[1][0] for x in log if x[0] == "table"] == ["plataforma_agentes"] * 2
        from noctusai_lib.integrations.prompt_registry import ChamadaMedida

        reg.registrar_chamada(ChamadaMedida(CHAVE, "openai", "gpt-5.6-sol", 12, False, erro="X" * 500))
        ins = next(a for n, a, k in log if n == "insert")[0]
        assert len(ins["erro"]) == 200 and ins["ok"] is False
        assert ("table", ("plataforma_agente_chamadas",), {}) in log

    def test_factory_refuses_no_client(self):
        with pytest.raises(ValueError):
            make_prompt_registry(None)
