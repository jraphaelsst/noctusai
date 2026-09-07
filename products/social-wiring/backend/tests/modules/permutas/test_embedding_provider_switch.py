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


class TestProvenanceStopsCrossSpaceMixing:
    """The other half of the width hazard, and the one that was left open.

    🔴 THE WIDTH GUARD DOES NOT COVER THIS. Both providers write into the same
    `vector(1536)` column, so an OpenAI vector and a Gemini vector are
    indistinguishable once stored — `_conferir_dimensoes` passes both. The way
    a corpus ends up holding two spaces is the ORDINARY path: embed under
    OpenAI, run out of credit, switch provider (which is exactly what the
    settings UI advises), embed the rest under Gemini. `apenas_pendentes`
    defaults to True and skipped anything that already had vectors, so the
    switch produced a silently mixed corpus with nothing recording which row
    was which.

    The consumer makes the consequence worse than "weaker matches":
    `noctusai_lib.domain.real_estate.matching` takes the COMPOSITE branch
    whenever similarity > 0, and a cross-space cosine is near-zero but not
    exactly zero — so the pair keeps 40% of its weight collapsed instead of
    falling back to the rule score.
    """

    @staticmethod
    def _cliente_gravando(ativos, interesses, gravacoes):
        """Like `_cliente`, but REMEMBERS what was written.

        The other harness returns `self` from `update()` and drops the
        payload, which is fine for asserting what reached the provider and
        useless for asserting what reached the row. Provenance is only
        observable in the payload.
        """
        class _Q:
            def __init__(self, dados): self._d = list(dados)
            def select(self, *a, **k): return self
            def eq(self, *a, **k): return self
            def in_(self, *a, **k): return self
            def order(self, *a, **k): return self
            def limit(self, *a, **k): return self
            def update(self, payload, *a, **k):
                gravacoes.append(payload)
                return self
            def execute(self): return type("R", (), {"data": self._d})()

        tabelas = {"permuta_ativos": ativos, "permuta_interesses": interesses, "imoveis": []}

        class _C:
            def schema(self, _nome): return self
            def table(self, nome): return _Q(tabelas.get(nome, []))
        return _C()

    @staticmethod
    async def _embedder(texts, **_kw):
        return [[0.0] * 1536 for _ in texts]

    def _ativo(self, **over):
        return {**TestTheSwitchReachesTheProviderCall.ATIVO, **over}

    ORG = "6dd73140-74a4-41c6-aeff-bc94b5312b53"

    @pytest.mark.asyncio
    async def test_the_write_records_which_space_the_vectors_are_in(self):
        gravacoes: list[dict] = []
        cliente = self._cliente_gravando(
            [self._ativo()], [TestTheSwitchReachesTheProviderCall.INTERESSE], gravacoes
        )

        await emb.embutir_ativos(
            cliente, self.ORG,
            provider_resolver=lambda _org: "gemini",
            embedder=self._embedder,
        )

        assert len(gravacoes) == 1
        # Same statement as the vectors — a separate update could fail alone
        # and leave a vector whose space nothing records.
        assert gravacoes[0]["embedding_provider"] == "gemini"
        assert gravacoes[0]["embedding_modelo"] == "gemini-embedding-001"
        assert "embedding" in gravacoes[0]

    @pytest.mark.asyncio
    async def test_switching_provider_re_embeds_instead_of_mixing(self):
        """🔴 THE REGRESSION THIS CLASS EXISTS FOR."""
        gravacoes: list[dict] = []
        ja_openai = self._ativo(
            embedding=[0.0] * 1536,
            embedding_interesses=[0.0] * 1536,
            embedding_provider="openai",
            embedding_modelo="text-embedding-3-small",
        )
        cliente = self._cliente_gravando(
            [ja_openai], [TestTheSwitchReachesTheProviderCall.INTERESSE], gravacoes
        )

        r = await emb.embutir_ativos(
            cliente, self.ORG,
            provider_resolver=lambda _org: "gemini",
            embedder=self._embedder,
        )

        assert r["processados"] == 1, "a row from another space is NOT done"
        assert r["reembutidos"] == 1, "and the run says the switch caused it"
        assert gravacoes[0]["embedding_provider"] == "gemini"

    @pytest.mark.asyncio
    async def test_same_provider_still_skips_the_already_done(self):
        """The re-embed must be caused by the SWITCH, not by every run."""
        gravacoes: list[dict] = []
        ja_gemini = self._ativo(
            embedding=[0.0] * 1536,
            embedding_interesses=[0.0] * 1536,
            embedding_provider="gemini",
            embedding_modelo="gemini-embedding-001",
        )
        cliente = self._cliente_gravando(
            [ja_gemini], [TestTheSwitchReachesTheProviderCall.INTERESSE], gravacoes
        )

        r = await emb.embutir_ativos(
            cliente, self.ORG,
            provider_resolver=lambda _org: "gemini",
            embedder=self._embedder,
        )

        assert r["processados"] == 0
        assert r["reembutidos"] == 0
        assert gravacoes == []
        # The early return must still name the space, or the page cannot say
        # which vendor the layer belongs to.
        assert r["provedor"] == "gemini"

    @pytest.mark.asyncio
    async def test_a_vector_with_no_provenance_is_treated_as_stale(self):
        """Rows written before these columns existed are unidentifiable, and
        re-embedding one is cheap next to leaving it in the corpus forever."""
        gravacoes: list[dict] = []
        legado = self._ativo(
            embedding=[0.0] * 1536, embedding_interesses=[0.0] * 1536,
        )
        cliente = self._cliente_gravando(
            [legado], [TestTheSwitchReachesTheProviderCall.INTERESSE], gravacoes
        )

        r = await emb.embutir_ativos(
            cliente, self.ORG,
            provider_resolver=lambda _org: "openai",
            embedder=self._embedder,
        )

        assert r["processados"] == 1
        assert gravacoes[0]["embedding_provider"] == "openai"

    @pytest.mark.asyncio
    async def test_a_row_dropped_for_having_no_text_is_not_counted_as_re_embedded(self):
        """`reembutidos` counts rows actually QUEUED. Counting at the filter
        would report work that never happens."""
        gravacoes: list[dict] = []
        sem_texto = self._ativo(
            id="a2", observacoes=None, natureza="permuta_imovel",
            imovel_codigo=None, tipo_imovel=None, cidade=None, uf=None, valor=None,
            embedding=[0.0] * 1536, embedding_interesses=[0.0] * 1536,
            embedding_provider="openai", embedding_modelo="text-embedding-3-small",
        )
        cliente = self._cliente_gravando([sem_texto], [], gravacoes)

        r = await emb.embutir_ativos(
            cliente, self.ORG,
            provider_resolver=lambda _org: "gemini",
            embedder=self._embedder,
        )

        assert r["processados"] == 0
        assert r["reembutidos"] == 0
