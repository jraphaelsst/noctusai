"""`llm.catalog_overrides` — the operator overlay over the static catalog.

Proves the ONE seam reaches every catalog consumer (`models_for`,
`estimate_cost_usd`, `image_edit.capabilities_for_model`), that a disabled
row disappears and an added row appears, that `is_priced` refuses a gap,
and that both stores version every save. The overlay is process-global, so
every test starts and ends with it cleared (its public API — no patching).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from noctusai_lib.integrations.image_edit import capabilities_for_model
from noctusai_lib.integrations.llm import (
    InMemoryModelCatalogStore,
    ModelCatalogStore,
    ModelOverride,
    ModelOverrideConflict,
    SupabaseModelCatalogStore,
    base_models_for,
    clear_model_overrides,
    estimate_cost_usd,
    get_model_override,
    is_priced,
    make_model_catalog_store,
    models_for,
    refresh_model_overrides,
    set_model_overrides,
)
from noctusai_lib.testing import MockSupabaseClient

SUNBURST = "gpt-image-2.5-sunburst"
GPT_IMAGE_2 = "gpt-image-2"


@pytest.fixture(autouse=True)
def _clean_overlay():
    clear_model_overrides()
    yield
    clear_model_overrides()


def _gpt_image_2(**changes) -> ModelOverride:
    base = ModelOverride(
        provider="openai",
        kind="image_edit",
        model_id=GPT_IMAGE_2,
        label="GPT Image 2",
        cost_per_1m_input_tokens=5.0,
        cost_per_1m_image_input_tokens=10.0,
        cost_per_1m_image_output_tokens=40.0,
        supports_batch=True,
        tag_performance="economico",
    )
    return ModelOverride(**{**base.__dict__, **changes})


def _ids(kind: str = "image_edit") -> list[str]:
    return [m.id for m in models_for("openai", kind)]


def test_no_overlay_is_the_static_catalog() -> None:
    assert models_for("openai", "image_edit") == base_models_for("openai", "image_edit")
    assert capabilities_for_model(GPT_IMAGE_2).known is False


def test_added_row_reaches_capabilities_and_pricing() -> None:
    set_model_overrides([_gpt_image_2()])
    assert _ids() == [SUNBURST, "gpt-image-2.5-flare", GPT_IMAGE_2]
    caps = capabilities_for_model(GPT_IMAGE_2)
    assert (caps.known, caps.supports_batch, caps.priced) == (True, True, True)
    cost = estimate_cost_usd(
        provider="openai",
        model=GPT_IMAGE_2,
        prompt_tokens=1_000_000,
        completion_tokens=None,
        image_input_tokens=1_000_000,
        image_output_tokens=1_000_000,
    )
    assert cost == pytest.approx(55.0)


def test_override_replaces_prices_of_a_static_row() -> None:
    static = next(m for m in base_models_for("openai", "image_edit") if m.id == SUNBURST)
    set_model_overrides([ModelOverride.from_entry(static, cost_per_1m_image_output_tokens=60.0)])
    effective = next(m for m in models_for("openai", "image_edit") if m.id == SUNBURST)
    assert effective.cost_per_1m_image_output_tokens == 60.0
    assert effective.label == static.label and effective.snapshot == static.snapshot
    assert estimate_cost_usd(
        provider="openai", model=SUNBURST, prompt_tokens=0, completion_tokens=0,
        image_output_tokens=1_000_000,
    ) == pytest.approx(60.0)


def test_disabled_row_disappears_everywhere() -> None:
    static = next(m for m in base_models_for("openai", "image_edit") if m.id == SUNBURST)
    set_model_overrides([ModelOverride.from_entry(static, enabled=False)])
    assert SUNBURST not in _ids()
    assert capabilities_for_model(SUNBURST).known is False
    assert estimate_cost_usd(
        provider="openai", model=SUNBURST, prompt_tokens=10, completion_tokens=10
    ) == 0.0


def test_unpriced_leg_is_refusable() -> None:
    set_model_overrides([_gpt_image_2(cost_per_1m_image_output_tokens=None)])
    caps = capabilities_for_model(GPT_IMAGE_2)
    assert caps.known and not caps.priced
    entry = next(m for m in models_for("openai", "image_edit") if m.id == GPT_IMAGE_2)
    assert is_priced(entry) is False


def test_overlay_is_scoped_by_provider_and_kind() -> None:
    set_model_overrides([_gpt_image_2()])
    assert GPT_IMAGE_2 not in _ids("chat")
    assert GPT_IMAGE_2 not in [m.id for m in models_for("gemini")]
    assert GPT_IMAGE_2 in [m.id for m in models_for("openai")]
    assert get_model_override("openai", "image_edit", GPT_IMAGE_2) is not None


def test_is_priced_per_kind() -> None:
    chat = next(m for m in models_for("openai", "chat") if m.id == "gpt-4o-mini")
    whisper = next(m for m in models_for("openai", "audio"))
    assert is_priced(chat) is True
    assert is_priced(whisper) is False


def test_override_validates_its_own_values() -> None:
    with pytest.raises(ValueError):
        _gpt_image_2(tag_performance="rapido")
    with pytest.raises(ValueError):
        _gpt_image_2(cost_per_1m_input_tokens=-1.0)


def test_in_memory_store_versions_every_save() -> None:
    async def scenario() -> None:
        store = make_model_catalog_store(use_fake=True)
        assert isinstance(store, ModelCatalogStore)
        first = await store.save_override(_gpt_image_2(), changed_by="u1")
        second = await store.save_override(
            _gpt_image_2(cost_per_1m_image_output_tokens=45.0), changed_by="u2"
        )
        assert (first.version, second.version) == (1, 2)
        assert [o.version for o in await store.list_versions("openai", "image_edit", GPT_IMAGE_2)] == [2, 1]
        assert await refresh_model_overrides(store) == 1
        entry = next(m for m in models_for("openai", "image_edit") if m.id == GPT_IMAGE_2)
        assert entry.cost_per_1m_image_output_tokens == 45.0

    asyncio.run(scenario())


class _StableSchemaClient:
    """Repeated `.schema(name)` returns the SAME scoped mock (the mock builds
    a fresh one per call, which would drop table state between statements)."""

    def __init__(self) -> None:
        self.base = MockSupabaseClient(validate_schema=True)
        self._scoped: dict[str, object] = {}

    def schema(self, name: str):
        if name not in self._scoped:
            self._scoped[name] = self.base.schema(name)
        return self._scoped[name]


def test_supabase_store_round_trip_against_the_real_columns() -> None:
    at = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)

    async def scenario() -> None:
        client = _StableSchemaClient()
        store = SupabaseModelCatalogStore(client, schema="social_wiring", now=lambda: at)
        assert isinstance(store, ModelCatalogStore)
        saved = await store.save_override(
            _gpt_image_2(), changed_by="00000000-0000-4000-8000-000000000001"
        )
        assert saved.version == 1 and saved.updated_at == at
        history = await store.list_versions("openai", "image_edit", GPT_IMAGE_2)
        assert [h.version for h in history] == [1]
        assert history[0].cost_per_1m_image_output_tokens == 40.0
        assert history[0].supports_batch is True
        # The seed mock does not propagate `upsert` (its payload IS
        # column-validated above); seed the current table with the same row
        # to prove the read path decodes the real column set.
        row = {k: v for k, v in client.schema("social_wiring").from_(
            SupabaseModelCatalogStore.HISTORY
        ).select("*").execute().data[0].items() if k != "id"}
        client.schema("social_wiring").set_table_data(SupabaseModelCatalogStore.CURRENT, [row])
        listed = await store.list_overrides()
        assert [o.model_id for o in listed] == [GPT_IMAGE_2]
        assert listed[0].version == 1 and listed[0].tag_performance == "economico"

    asyncio.run(scenario())


def test_supabase_store_maps_a_version_collision() -> None:
    class _Dup(Exception):
        code = "23505"

    class _Builder:
        def __init__(self, rows=None, exc=None):
            self.rows, self.exc = rows or [], exc

        def __getattr__(self, _name):
            return lambda *a, **k: self

        def execute(self):
            if self.exc:
                raise self.exc
            return type("R", (), {"data": self.rows})()

    class _Client:
        def schema(self, _name):
            return self

        def from_(self, table):
            if table == SupabaseModelCatalogStore.HISTORY:
                return _Builder(exc=_Dup("duplicate"))
            return _Builder(rows=[])

    store = SupabaseModelCatalogStore(_Client(), schema="social_wiring")
    with pytest.raises(ModelOverrideConflict):
        asyncio.run(store.save_override(_gpt_image_2(), changed_by=None))


def test_factory_requires_a_client() -> None:
    assert isinstance(make_model_catalog_store(use_fake=True), InMemoryModelCatalogStore)
    with pytest.raises(RuntimeError, match="supabase_client is required"):
        make_model_catalog_store()
