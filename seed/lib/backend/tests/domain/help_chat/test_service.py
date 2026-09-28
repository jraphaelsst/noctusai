"""Unit tests for the help-chat service module — knowledge loading, system
prompt assembly, multi-turn message ordering, and the rate limiter — none
of which need a FastAPI app."""
from __future__ import annotations

import pytest
from noctusai_lib.domain.help_chat.service import (
    HelpChatKnowledgeMissing,
    HelpChatRateLimiter,
    build_conversation_messages,
    build_system_prompt,
    load_knowledge,
)


class TestLoadKnowledge:
    def test_reads_a_real_file(self, tmp_path):
        p = tmp_path / "k.md"
        p.write_text("# Ola\nconteudo", encoding="utf-8")
        assert load_knowledge(p) == "# Ola\nconteudo"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(HelpChatKnowledgeMissing):
            load_knowledge(tmp_path / "nope.md")

    def test_empty_file_raises(self, tmp_path):
        p = tmp_path / "k.md"
        p.write_text("   ", encoding="utf-8")
        with pytest.raises(HelpChatKnowledgeMissing):
            load_knowledge(p)

    def test_callable_source(self):
        assert load_knowledge(lambda: "texto dinâmico") == "texto dinâmico"

    def test_callable_returning_empty_raises(self):
        with pytest.raises(HelpChatKnowledgeMissing):
            load_knowledge(lambda: "")


class TestBuildSystemPrompt:
    def test_includes_product_name_and_knowledge(self):
        prompt = build_system_prompt(product_name="IgIg", knowledge="REGRA-X")
        assert "IgIg" in prompt
        assert "REGRA-X" in prompt

    def test_encodes_the_clarifying_question_and_no_data_access_rules(self):
        prompt = build_system_prompt(product_name="IgIg", knowledge="k")
        assert "pergunta curta de esclarecimento" in prompt
        assert "senhas" in prompt


class TestBuildConversationMessages:
    def test_single_turn(self):
        messages = build_conversation_messages(
            system_prompt="SISTEMA", history=[{"role": "user", "content": "oi"}], provider="anthropic",
        )
        assert messages == [
            {"role": "system", "content": "SISTEMA", "cache_control": {"type": "ephemeral"}},
            {"role": "user", "content": "oi"},
        ]

    def test_multi_turn_preserves_order(self):
        history = [
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "2"},
            {"role": "user", "content": "3"},
        ]
        messages = build_conversation_messages(system_prompt="SISTEMA", history=history, provider="anthropic")
        assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
        assert [m.get("content") for m in messages] == ["SISTEMA", "1", "2", "3"]

    def test_openai_provider_has_no_cache_control(self):
        messages = build_conversation_messages(
            system_prompt="SISTEMA", history=[{"role": "user", "content": "oi"}], provider="openai",
        )
        assert "cache_control" not in messages[0]


class TestHelpChatRateLimiter:
    def test_allows_up_to_the_limit_then_denies(self):
        clock = {"t": 0.0}
        limiter = HelpChatRateLimiter(max_requests=2, window_seconds=60.0, clock=lambda: clock["t"])
        assert limiter.allow("user-1") is True
        assert limiter.allow("user-1") is True
        assert limiter.allow("user-1") is False

    def test_resets_after_the_window(self):
        clock = {"t": 0.0}
        limiter = HelpChatRateLimiter(max_requests=1, window_seconds=60.0, clock=lambda: clock["t"])
        assert limiter.allow("user-1") is True
        assert limiter.allow("user-1") is False
        clock["t"] = 61.0
        assert limiter.allow("user-1") is True

    def test_keys_are_independent(self):
        limiter = HelpChatRateLimiter(max_requests=1, window_seconds=60.0)
        assert limiter.allow("user-1") is True
        assert limiter.allow("user-2") is True
        assert limiter.allow("user-1") is False
