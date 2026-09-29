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

    def test_a_multi_flow_question_is_disambiguated_before_answering(self):
        """Live prod 2026-09-28: "Como faço para cobrar o cliente?" got a
        full answer covering four flows instead of "which one?". The owner's
        rule is ask-first; the preamble must say so for multi-flow questions."""
        prompt = build_system_prompt(product_name="IgIg", knowledge="k")
        assert "MAIS DE UM fluxo" in prompt
        assert "Primeiro pergunte qual deles" in prompt


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

    def test_the_cache_control_marker_actually_reaches_the_anthropic_provider(self):
        """Closes the exact gap `README.md`'s 'Known seed gap' section used
        to document (fixed by 7477a639d, 2026-09-28): the OTHER tests in this
        file only prove `build_conversation_messages` ATTACHES the seed's
        internal `cache_control` marker; `test_anthropic_prompt_cache.py`
        only proves the provider's translation seam handles a synthetic
        message in isolation. Neither, alone, proves the two compose — this
        threads help-chat's own system knowledge through BOTH and asserts
        the marker survives into the Anthropic SDK's content-block shape."""
        from noctusai_lib.integrations.llm.providers.anthropic_provider import (
            _split_system_and_messages,
        )

        system_prompt = build_system_prompt(product_name="IgIg", knowledge="REGRA-X: so admin edita.")
        messages = build_conversation_messages(
            system_prompt=system_prompt,
            history=[{"role": "user", "content": "Como edito uma regra?"}],
            provider="anthropic",
        )

        system, conversation = _split_system_and_messages(messages)

        assert system == [
            {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}},
        ]
        assert conversation == [{"role": "user", "content": "Como edito uma regra?"}]


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
