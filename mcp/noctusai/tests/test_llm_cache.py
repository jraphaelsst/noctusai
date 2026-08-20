"""Phase 8 tests: response cache + LGPD gate."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from noctusai_lib.testing.conftest_helpers import restore_real_llm_providers

_LIB = Path(__file__).resolve().parents[3] / "seed" / "lib" / "backend"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import noctusai_lib.integrations.llm  # noqa: F401,E402


class TestKeyBuilder:
    def test_deterministic(self):
        from noctusai_lib.integrations.llm.cache import build_cache_key

        k1 = build_cache_key(
            product="erp", provider="openai", model="gpt-4o-mini",
            prompt_version="v1", payload=[{"role": "user", "content": "hi"}],
        )
        k2 = build_cache_key(
            product="erp", provider="openai", model="gpt-4o-mini",
            prompt_version="v1", payload=[{"role": "user", "content": "hi"}],
        )
        assert k1 == k2

    def test_different_payload_different_key(self):
        from noctusai_lib.integrations.llm.cache import build_cache_key

        k1 = build_cache_key(
            product="erp", provider="openai", model="gpt-4o-mini",
            prompt_version="v1", payload="prompt-a",
        )
        k2 = build_cache_key(
            product="erp", provider="openai", model="gpt-4o-mini",
            prompt_version="v1", payload="prompt-b",
        )
        assert k1 != k2

    def test_prompt_version_invalidates(self):
        from noctusai_lib.integrations.llm.cache import build_cache_key

        k1 = build_cache_key(product="x", provider="p", model="m",
                             prompt_version="v1", payload="same")
        k2 = build_cache_key(product="x", provider="p", model="m",
                             prompt_version="v2", payload="same")
        assert k1 != k2

    def test_org_id_isolates_cache_entries(self):
        """Regression for Tier 1.5 G5 (2026-04-24): two orgs running an
        identical prompt must NOT share a cache entry."""
        from noctusai_lib.integrations.llm.cache import build_cache_key

        common = dict(
            product="erp", provider="openai", model="gpt-4o-mini",
            prompt_version="v1", payload=[{"role": "user", "content": "draft follow-up for João Silva"}],
        )
        k_org_a = build_cache_key(**common, org_id="org-aaa")
        k_org_b = build_cache_key(**common, org_id="org-bbb")
        assert k_org_a != k_org_b
        assert "org=org-aaa" in k_org_a
        assert "org=org-bbb" in k_org_b

    def test_org_id_none_uses_platform_segment(self):
        """When no org_id is provided (platform-wide prompt), the segment
        falls back to a sentinel so the cache key shape stays uniform."""
        from noctusai_lib.integrations.llm.cache import build_cache_key

        k = build_cache_key(
            product="x", provider="p", model="m",
            prompt_version="v1", payload="docs-prompt",
        )
        assert "org=__platform__" in k

    def test_no_org_id_collides_with_platform_segment(self):
        """An org literally named '__platform__' is the only edge case where
        platform-default and an org could collide; document the choice
        explicitly so a future agent doesn't break the assumption."""
        from noctusai_lib.integrations.llm.cache import build_cache_key

        k_default = build_cache_key(
            product="x", provider="p", model="m",
            prompt_version="v1", payload="x",
        )
        k_platform_org = build_cache_key(
            product="x", provider="p", model="m",
            prompt_version="v1", payload="x", org_id="__platform__",
        )
        # Both produce the same key — acceptable because '__platform__' is
        # not a valid Supabase UUID and would never appear as a real org_id.
        assert k_default == k_platform_org


class TestInMemoryBackend:
    def test_set_then_get(self):
        from noctusai_lib.integrations.llm.cache import InMemoryCacheBackend, try_get, try_set

        b = InMemoryCacheBackend()
        asyncio.run(try_set(b, "k", "hello", ttl_seconds=60))
        hit, val = asyncio.run(try_get(b, "k"))
        assert hit is True
        assert val == "hello"

    def test_miss_is_not_error(self):
        from noctusai_lib.integrations.llm.cache import InMemoryCacheBackend, try_get

        hit, val = asyncio.run(try_get(InMemoryCacheBackend(), "absent"))
        assert hit is False
        assert val is None

    def test_backend_error_is_swallowed(self):
        """Cache-layer failures never propagate — they're logged + treated as miss."""
        from noctusai_lib.integrations.llm.cache import try_get

        class Broken:
            async def get(self, key):
                raise RuntimeError("redis down")
            async def setex(self, key, ttl, value):
                raise RuntimeError("down")
            async def delete(self, *keys):
                return 0

        hit, val = asyncio.run(try_get(Broken(), "k"))
        assert hit is False
        assert val is None


class TestChatCompletionCacheGating:
    """The cache must gate on all four conditions:
       cache=True × cache_enabled=True × cache_backend != None × temperature==0
    """

    def _install_counting_fake(self, cache_enabled: bool):
        from noctusai_lib.integrations.llm import (
            FakeProvider,
            InMemoryCacheBackend,
            LLMConfig,
        )
        from noctusai_lib.integrations.llm.client import _reset_for_testing, configure_llm
        from noctusai_lib.integrations.llm.registry import register

        _reset_for_testing()
        fake = FakeProvider(chat_responses=["r1", "r2", "r3"])

        class _FC:
            def __new__(cls):
                return fake

        register("openai", _FC)  # type: ignore[arg-type]
        configure_llm(LLMConfig(
            key_provider=lambda p, org_id=None: "sk-k",
            default_provider="openai",
            cache_enabled=cache_enabled,
            cache_backend=InMemoryCacheBackend() if cache_enabled else None,
        ))
        return fake

    def teardown_method(self):
        from noctusai_lib.integrations.llm.client import _reset_for_testing

        _reset_for_testing()
        # Was an inline copy of the re-import loop that called
        # `importlib.reload(sys.modules[mod])` WITHOUT importing first — a
        # KeyError the moment a provider module had not been imported yet.
        restore_real_llm_providers()

    def test_second_call_is_cached_when_enabled_and_deterministic(self):
        from noctusai_lib.integrations.llm import chat_completion

        fake = self._install_counting_fake(cache_enabled=True)
        msgs = [{"role": "user", "content": "hi"}]
        r1 = asyncio.run(chat_completion(messages=msgs, temperature=0))
        r2 = asyncio.run(chat_completion(messages=msgs, temperature=0))
        assert r1 == "r1"
        assert r2 == "r1"  # cache hit — same response
        # Provider was called only once.
        call_count = sum(1 for c in fake.calls if c["method"] == "chat_completion")
        assert call_count == 1

    def test_cache_bypassed_when_cache_false(self):
        """cache=False is the LGPD gate — Therapy clinical calls use this."""
        from noctusai_lib.integrations.llm import chat_completion

        fake = self._install_counting_fake(cache_enabled=True)
        msgs = [{"role": "user", "content": "clinical text"}]
        r1 = asyncio.run(chat_completion(messages=msgs, temperature=0, cache=False))
        r2 = asyncio.run(chat_completion(messages=msgs, temperature=0, cache=False))
        # Both calls hit the provider — cache never consulted.
        call_count = sum(1 for c in fake.calls if c["method"] == "chat_completion")
        assert call_count == 2
        assert r1 != r2  # different scripted responses

    def test_cache_bypassed_when_nondeterministic(self):
        """temperature != 0 means the caller intentionally wants variability
        — never cache those."""
        from noctusai_lib.integrations.llm import chat_completion

        fake = self._install_counting_fake(cache_enabled=True)
        msgs = [{"role": "user", "content": "same prompt"}]
        asyncio.run(chat_completion(messages=msgs, temperature=0.7))
        asyncio.run(chat_completion(messages=msgs, temperature=0.7))
        call_count = sum(1 for c in fake.calls if c["method"] == "chat_completion")
        assert call_count == 2

    def test_cache_bypassed_when_platform_disabled(self):
        """cache_enabled=False at LLMConfig level overrides everything."""
        from noctusai_lib.integrations.llm import chat_completion

        fake = self._install_counting_fake(cache_enabled=False)
        msgs = [{"role": "user", "content": "x"}]
        asyncio.run(chat_completion(messages=msgs, temperature=0))
        asyncio.run(chat_completion(messages=msgs, temperature=0))
        call_count = sum(1 for c in fake.calls if c["method"] == "chat_completion")
        assert call_count == 2


class TestFlushForModel:
    def test_in_memory_flush(self):
        from noctusai_lib.integrations.llm.cache import InMemoryCacheBackend, flush_for_model, try_set

        b = InMemoryCacheBackend()
        # Populate entries for two models.
        asyncio.run(try_set(b, "llm:erp:openai:gpt-4o-mini:v1:hash1", "v", 60))
        asyncio.run(try_set(b, "llm:erp:openai:gpt-4o-mini:v1:hash2", "v", 60))
        asyncio.run(try_set(b, "llm:erp:openai:gpt-4o:v1:hash3", "v", 60))

        n = asyncio.run(flush_for_model(b, product="erp", provider="openai", model="gpt-4o-mini"))
        assert n == 2
        # The gpt-4o entry survives.
        assert "llm:erp:openai:gpt-4o:v1:hash3" in b._store
