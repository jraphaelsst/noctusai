"""The Gemini↔OpenAI switch for the semantic layer.

Every assertion here covers a failure that does NOT announce itself:

  * a provider whose vectors are the wrong WIDTH breaks at the INSERT with a
    message about a column, naming nothing about the setting that caused it;
  * `output_dimensionality` sent to OpenAI is an unknown kwarg reaching that
    SDK — the vendors spell the parameter differently;
  * a provider resolved PER BATCH rather than per run would embed half a
    corpus in one vector space and half in another, and the halves would
    never be comparable again.
"""
from __future__ import annotations

import pytest

from app.modules.permutas import embeddings as emb
from app.services import api_keys_store as keys


class TestSpecRegistry:
    def test_anthropic_key_is_still_offered(self):
        """🔴 Explicitly kept. Anthropic cannot do embeddings, but it IS the
        vision fallback and the key must stay configurable."""
        assert "anthropic_api_key" in keys.MANAGED_API_KEYS

    def test_gemini_key_is_offered(self):
        assert "gemini_api_key" in keys.MANAGED_API_KEYS

    def test_embedding_switch_offers_openai_and_gemini(self):
        spec = keys.get_spec("llm_embedding_provider")
        assert set(spec.allowed_values) == {"openai", "gemini"}
        assert spec.default == "openai"

    def test_embedding_switch_never_offers_anthropic(self):
        """The API has no embeddings endpoint — offering it would surface as
        an unexplained empty semantic layer, not as 'wrong vendor'."""
        spec = keys.get_spec("llm_embedding_provider")
        assert "anthropic" not in spec.allowed_values

    def test_vision_switch_kept_anthropic_and_gained_gemini(self):
        spec = keys.get_spec("llm_vision_provider")
        assert set(spec.allowed_values) == {"openai", "anthropic", "gemini"}


class TestProviderResolution:
    def _resolver(self, valor):
        return lambda name, org_id: valor

    def test_unset_falls_back_to_the_spec_default(self):
        assert keys.resolve_embedding_provider(
            "org", store=None, resolver=self._resolver(None)) == "openai"

    def test_stored_choice_wins(self):
        assert keys.resolve_embedding_provider(
            "org", store=None, resolver=self._resolver("gemini")) == "gemini"

    def test_unknown_value_falls_back_rather_than_raising(self):
        """A vendor name the LLM stack cannot route is worse than the
        documented default — it fails a layer down, about a missing key."""
        assert keys.resolve_embedding_provider(
            "org", store=None, resolver=self._resolver("cohere")) == "openai"

    def test_anthropic_can_never_be_resolved_for_embeddings(self):
        assert keys.resolve_embedding_provider(
            "org", store=None, resolver=self._resolver("anthropic")) == "openai"


class TestDimensionGuard:
    def test_correct_width_passes(self):
        emb._conferir_dimensoes([[0.0] * 1536], "gemini", "gemini-embedding-001")

    def test_wrong_width_refuses_the_whole_batch(self):
        """🔴 Gemini's real default is 3072. Nothing is written."""
        with pytest.raises(ValueError, match="3072 dimensões"):
            emb._conferir_dimensoes([[0.0] * 3072], "gemini", "gemini-embedding-001")

    def test_the_message_forbids_truncating_to_fit(self):
        with pytest.raises(ValueError, match="nunca"):
            emb._conferir_dimensoes([[0.0] * 768], "gemini", "x")

    def test_empty_batch_is_not_an_error(self):
        emb._conferir_dimensoes([], "openai", "text-embedding-3-small")


class TestModelMapping:
    def test_every_switch_option_has_a_model(self):
        """A switch option with no model mapped is a runtime crash reachable
        from a dropdown — the registry and the map must not drift."""
        for value in keys.get_spec("llm_embedding_provider").allowed_values:
            assert value in emb.MODELOS, f"{value} tem opção mas não tem modelo"

    def test_only_gemini_is_sent_the_dimension_kwarg(self):
        """OpenAI's parameter is `dimensions`; sending Gemini's spelling would
        reach the OpenAI SDK as an unknown kwarg."""
        assert "gemini" in emb._PRECISA_DIMENSAO
        assert "openai" not in emb._PRECISA_DIMENSAO

    def test_the_target_width_matches_the_column(self):
        assert emb.DIMENSOES == 1536


class TestTheSwitchReachesTheProviderCall:
    """Integration-level: the operator's pick must arrive at the LLM call.

    The unit tests above prove each piece; this proves they are WIRED. A
    correct resolver and a correct model map still produce an OpenAI call if
    nobody threads the choice through — and that failure is invisible, because
    the run succeeds and simply embeds with the wrong vendor.

    🔴 DI SEAMS, NOT MONKEYPATCH. `embutir_ativos` takes `provider_resolver`
    and `embedder`; the substitutes are PASSED. Rebinding this module's own
    globals would leave the real call path untested while these assertions
    went green — the failure mode `KB § PATTERNS/compliance/testing.md` names.
    The adapter is NOT stubbed either: the fake client below answers the three
    real queries it makes, so the projection under test is the production one.
    """

    @staticmethod
    def _cliente(ativos, interesses, imoveis=()):
        """A Supabase-shaped fake that answers the adapter's real queries.

        Complete enough that `listar_ativos_para_scorer` runs unmodified —
        which is the point: stubbing it would hide a broken projection.
        """
        class _Q:
            def __init__(self, dados): self._d = list(dados)
            def select(self, *a, **k): return self
            def eq(self, *a, **k): return self
            def in_(self, *a, **k): return self
            def order(self, *a, **k): return self
            def limit(self, *a, **k): return self
            def update(self, *a, **k): return self
            def execute(self): return type("R", (), {"data": self._d})()

        tabelas = {
            "permuta_ativos": ativos,
            "permuta_interesses": interesses,
            "imoveis": imoveis,
        }

        class _C:
            def schema(self, _nome): return self
            def table(self, nome): return _Q(tabelas.get(nome, []))
        return _C()

    #: One `permuta_imovel` — it carries its own snapshot, so no catalog row
    #: is needed and the adapter resolves it without an `imoveis` join.
    ATIVO = {
        "id": "a1",
        "natureza": "permuta_imovel",
        "imovel_codigo": None,
        "status": "ativo",
        "tipo_imovel": "Casa",
        "cidade": "Cotia",
        "uf": "SP",
        "valor": 900000.0,
        "regiao_preferida": [],
        "observacoes": "estuda permuta de 30% a 50%, casa sem escada",
        "embedding": None,
        "embedding_interesses": None,
    }
    INTERESSE = {
        "id": "i1", "ativo_id": "a1", "tipo": "imovel",
        "tipo_imovel": "Casa", "valor_maximo": 800000,
        "observacoes": "quintal amplo",
    }

    def _cliente_padrao(self):
        return self._cliente([self.ATIVO], [self.INTERESSE])

    @pytest.mark.asyncio
    async def test_gemini_pick_sends_its_model_and_the_1536_truncation(self):
        visto: dict = {}

        async def embedder(texts, **kw):
            visto.update(kw); visto["n"] = len(texts)
            return [[0.0] * 1536 for _ in texts]

        r = await emb.embutir_ativos(
            self._cliente_padrao(), "6dd73140-74a4-41c6-aeff-bc94b5312b53",
            provider_resolver=lambda _org: "gemini",
            embedder=embedder,
        )

        assert visto["provider"] == "gemini"
        assert visto["model"] == "gemini-embedding-001"
        assert visto["output_dimensionality"] == 1536
        assert visto["n"] == 2, "perfil + interesses, um par por ativo"
        assert r["provedor"] == "gemini"
        assert r["dimensoes"] == 1536
        assert r["processados"] == 1

    @pytest.mark.asyncio
    async def test_openai_pick_never_sends_geminis_kwarg(self):
        """OpenAI's parameter is `dimensions`; Gemini's spelling would reach
        that SDK as an unknown kwarg."""
        visto: dict = {}

        async def embedder(texts, **kw):
            visto.update(kw)
            return [[0.0] * 1536 for _ in texts]

        await emb.embutir_ativos(
            self._cliente_padrao(), "6dd73140-74a4-41c6-aeff-bc94b5312b53",
            provider_resolver=lambda _org: "openai",
            embedder=embedder,
        )

        assert visto["provider"] == "openai"
        assert visto["model"] == "text-embedding-3-small"
        assert "output_dimensionality" not in visto

    @pytest.mark.asyncio
    async def test_a_wrong_width_response_writes_nothing(self):
        """🔴 The guard fires BEFORE the update loop, so a misconfigured
        provider cannot leave a half-embedded corpus behind."""
        async def embedder(texts, **kw):
            return [[0.0] * 3072 for _ in texts]   # Gemini's real default

        with pytest.raises(ValueError, match="3072 dimensões"):
            await emb.embutir_ativos(
                self._cliente_padrao(), "6dd73140-74a4-41c6-aeff-bc94b5312b53",
                provider_resolver=lambda _org: "gemini",
                embedder=embedder,
            )

    @pytest.mark.asyncio
    async def test_an_unmapped_provider_fails_before_calling_anything(self):
        """A switch option with no model must not reach the LLM stack, where
        it would surface as a missing-credential error naming the wrong thing."""
        async def embedder(texts, **kw):  # pragma: no cover - must not run
            raise AssertionError("o embedder não deveria ser chamado")

        with pytest.raises(ValueError, match="não tem modelo mapeado"):
            await emb.embutir_ativos(
                self._cliente_padrao(), "6dd73140-74a4-41c6-aeff-bc94b5312b53",
                provider_resolver=lambda _org: "cohere",
                embedder=embedder,
            )

    @pytest.mark.asyncio
    async def test_production_callers_get_the_real_chain(self):
        """The seams DEFAULT to the real functions — a test-only parameter
        that production silently bypasses would prove nothing."""
        import inspect
        sig = inspect.signature(emb.embutir_ativos)
        assert sig.parameters["provider_resolver"].default is emb.resolve_embedding_provider
        assert sig.parameters["embedder"].default is emb.generate_embeddings_batch
