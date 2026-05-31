"""Regression tests for the single LLM-config bootstrap + funnel self-config.

Guards the funnel-self-satisfies-preconditions fix: the embed funnel
(`_embedding_corpus.embed_sync`) must configure the seed LLM client ITSELF so
every caller works in-process (CLI / MCP server / hook / test), instead of
offloading `configure_llm()` onto callers (only the CLI ever did it → the
recurring "LLM not configured" drift on every MCP-server embed path).

KB § PATTERNS/common/funnel-self-satisfies-preconditions.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import noctusai_lib.integrations.llm as _llm_mod  # noqa: E402
import noctusai_lib.integrations.llm.client as _client_mod  # noqa: E402

from tools.noctus.dev import _embedding_corpus as ec  # noqa: E402
from tools.noctus.dev import _llm_bootstrap as lb  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_bootstrap_flag(monkeypatch):
    """Each test starts with the once-per-process flag cleared."""
    monkeypatch.setattr(lb, "_LLM_CONFIGURED", False)


class TestSourceEnv:
    def test_sources_key_from_dot_env_when_absent(self, monkeypatch, tmp_path):
        (tmp_path / ".env").write_text(
            '# comment\nOPENAI_API_KEY="sk-from-env-file"\nOTHER=ignored\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(lb, "_env_candidate_roots", lambda: [tmp_path])
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        lb._source_env_for_key()
        import os
        assert os.environ.get("OPENAI_API_KEY") == "sk-from-env-file"

    def test_does_not_overwrite_existing_key(self, monkeypatch, tmp_path):
        (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-from-file\n", encoding="utf-8")
        monkeypatch.setattr(lb, "_env_candidate_roots", lambda: [tmp_path])
        monkeypatch.setenv("OPENAI_API_KEY", "sk-already-in-env")
        lb._source_env_for_key()
        import os
        assert os.environ.get("OPENAI_API_KEY") == "sk-already-in-env"


class TestEnsureLLMConfigured:
    def test_returns_true_without_reconfigure_when_already_configured(self, monkeypatch):
        called = []
        monkeypatch.setattr(_client_mod, "get_llm_config", lambda: object())
        monkeypatch.setattr(_client_mod, "configure_llm", lambda cfg: called.append(cfg))
        assert lb.ensure_llm_configured() is True
        assert called == []  # already configured → never reconfigured

    def test_configures_when_not_yet_configured(self, monkeypatch):
        called = []

        def _raise():
            raise RuntimeError("not configured")

        monkeypatch.setattr(_client_mod, "get_llm_config", _raise)
        monkeypatch.setattr(_client_mod, "configure_llm", lambda cfg: called.append(cfg))
        monkeypatch.setattr(lb, "_source_env_for_key", lambda: None)
        assert lb.ensure_llm_configured() is True
        assert len(called) == 1  # configured exactly once

    def test_idempotent_across_calls(self, monkeypatch):
        called = []

        def _raise():
            raise RuntimeError("not configured")

        monkeypatch.setattr(_client_mod, "get_llm_config", _raise)
        monkeypatch.setattr(_client_mod, "configure_llm", lambda cfg: called.append(cfg))
        monkeypatch.setattr(lb, "_source_env_for_key", lambda: None)
        lb.ensure_llm_configured()
        lb.ensure_llm_configured()
        lb.ensure_llm_configured()
        assert len(called) == 1  # real work fires once per process

    def test_graceful_degrade_returns_false_when_lib_unimportable(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "noctusai_lib" or name.startswith("noctusai_lib."):
                raise ImportError("simulated fresh clone")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(lb, "_source_env_for_key", lambda: None)
        monkeypatch.setattr(builtins, "__import__", _fake_import)
        assert lb.ensure_llm_configured() is False  # no crash — degrade


class TestEmbedSyncSelfConfigures:
    """The root-fix assertion: the funnel configures the LLM ITSELF, before the
    embed, with no caller ritual."""

    def test_embed_sync_calls_ensure_before_embedding(self, monkeypatch):
        order = []
        monkeypatch.setattr(ec, "ensure_llm_configured", lambda: order.append("ensure") or True)
        monkeypatch.setattr(ec, "_throttle_embed", lambda: order.append("throttle"))
        monkeypatch.setattr(
            _llm_mod, "generate_embedding", lambda text: order.append(("embed", text)) or "coro"
        )
        monkeypatch.setattr(ec, "run_coro_blocking", lambda coro: [0.0] * ec.EMBEDDING_DIM)

        out = ec.embed_sync("hello")

        assert out == [0.0] * ec.EMBEDDING_DIM
        assert order[0] == "ensure", "funnel must self-configure FIRST"
        assert ("embed", "hello") in order
        # ensure precedes the embed (the precondition is satisfied before use)
        assert order.index("ensure") < order.index(("embed", "hello"))


class TestEmbedTextSelfConfigures:
    """`vectorize.embed_text` is the AD-HOC embed funnel — the path used by
    codification_radar / kb_recurrence_radar / find_reusable_component. It must
    self-configure the LLM too. It previously bypassed the bootstrap that
    `embed_sync` already carried (it calls `generate_embedding` via
    `run_coro_blocking` directly, not `embed_sync`), so it raised
    "LLM not configured" in the live MCP server (codification_radar observed
    failing 2026-05-31). The half-wired-funnel gap."""

    def test_embed_text_calls_ensure_before_embedding(self, monkeypatch):
        from tools.noctus.dev import vectorize as vz

        class _Cfg:
            default_embedding_model = "text-embedding-3-small"
            default_provider = "openai"

        order = []
        monkeypatch.setattr(lb, "ensure_llm_configured", lambda: order.append("ensure") or True)
        monkeypatch.setattr(
            _llm_mod, "generate_embedding", lambda text: order.append(("embed", text)) or "coro"
        )
        monkeypatch.setattr(ec, "run_coro_blocking", lambda coro: [0.0] * ec.EMBEDDING_DIM)
        monkeypatch.setattr(_client_mod, "get_llm_config", lambda: _Cfg())

        out = vz.embed_text("hello")

        assert out["ok"] is True
        assert out["dim"] == ec.EMBEDDING_DIM
        assert order[0] == "ensure", "embed_text must self-configure FIRST"
        assert order.index("ensure") < order.index(("embed", "hello"))
