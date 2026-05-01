"""Unit tests for mailing `ai_service` (ai-expansion Phase 14).

Network-free. Uses FakeProvider with scripted canned responses.
"""
from __future__ import annotations

import asyncio
import sys

import pytest


def _run(coro):
    return asyncio.run(coro)


def _install_fake(canned_responses: list[str]):
    from noctusai_lib.integrations.llm import FakeProvider, LLMConfig
    from noctusai_lib.integrations.llm.client import _reset_for_testing, configure_llm
    from noctusai_lib.integrations.llm.registry import register

    _reset_for_testing()
    fake = FakeProvider(chat_responses=canned_responses)

    class _FakeClass:
        def __new__(cls):
            return fake

    register("openai", _FakeClass)  # type: ignore[arg-type]
    configure_llm(LLMConfig(
        key_provider=lambda p, org_id=None: "sk-test",
        default_provider="openai",
    ))
    return fake


def _restore_real_providers():
    import importlib
    from noctusai_lib.integrations.llm.registry import _reset_for_testing as _reset_reg
    _reset_reg()
    for mod in (
        "noctusai_lib.integrations.llm.providers.openai_provider",
        "noctusai_lib.integrations.llm.providers.anthropic_provider",
        "noctusai_lib.integrations.llm.providers.gemini_provider",
    ):
        importlib.import_module(mod)
        importlib.reload(sys.modules[mod])


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    _restore_real_providers()


# ─── M1 — generate_subjects ────────────────────────────────────────────────


class TestGenerateSubjects:
    def test_returns_parsed_variants(self):
        from app.services.ai_service import generate_subjects
        _install_fake([
            '[{"text": "50% off só hoje", "tone": "urgência"},'
            ' {"text": "Você sabia disso?", "tone": "curiosidade"},'
            ' {"text": "Seu resumo semanal chegou", "tone": "direto"}]'
        ])
        result = _run(generate_subjects("Campanha de reativação"))
        assert len(result) == 3
        assert result[0] == {"text": "50% off só hoje", "tone": "urgência"}

    def test_handles_markdown_fenced_json(self):
        from app.services.ai_service import generate_subjects
        _install_fake(['```json\n[{"text": "Oi", "tone": "direto"}]\n```'])
        result = _run(generate_subjects("x"))
        assert result == [{"text": "Oi", "tone": "direto"}]

    def test_returns_empty_on_unparseable(self):
        from app.services.ai_service import generate_subjects
        _install_fake(["not valid JSON"])
        result = _run(generate_subjects("x"))
        assert result == []

    def test_caps_at_5_variants(self):
        from app.services.ai_service import generate_subjects
        _install_fake([
            '[' + ','.join(f'{{"text": "s{i}", "tone": "direto"}}' for i in range(10)) + ']'
        ])
        result = _run(generate_subjects("x"))
        assert len(result) == 5


# ─── M2 — draft_template ───────────────────────────────────────────────────


class TestDraftTemplate:
    def test_returns_html(self):
        from app.services.ai_service import draft_template
        _install_fake(["<h1>Hello</h1><p>Welcome</p>"])
        html = _run(draft_template("welcome email"))
        assert "<h1>Hello</h1>" in html

    def test_returns_empty_on_llm_not_configured(self):
        from app.services.ai_service import draft_template
        from noctusai_lib.integrations.llm.client import _reset_for_testing
        _reset_for_testing()
        assert _run(draft_template("x")) == ""


# ─── M5 — reengagement_variants ────────────────────────────────────────────


class TestReengagementVariants:
    def test_returns_three_variants(self):
        from app.services.ai_service import reengagement_variants
        _install_fake([
            '['
            ' {"tone": "leve", "subject": "Tá sumido!", "body_html": "<p>oi</p>"},'
            ' {"tone": "direto", "subject": "Podemos conversar?", "body_html": "<p>queremos te ouvir</p>"},'
            ' {"tone": "valor", "subject": "Um presente", "body_html": "<p>20% off</p>"}'
            ']'
        ])
        variants = _run(reengagement_variants("inativos 90d+"))
        assert len(variants) == 3
        assert {v["tone"] for v in variants} == {"leve", "direto", "valor"}

    def test_caps_at_3(self):
        from app.services.ai_service import reengagement_variants
        _install_fake([
            '[' + ','.join(
                f'{{"tone": "t{i}", "subject": "s{i}", "body_html": "<p>b{i}</p>"}}'
                for i in range(5)
            ) + ']'
        ])
        variants = _run(reengagement_variants("x"))
        assert len(variants) == 3


# ─── M6 — review_deliverability ────────────────────────────────────────────


class TestReviewDeliverability:
    def test_returns_findings(self):
        from app.services.ai_service import review_deliverability
        _install_fake([
            '{"findings": ['
            ' {"code": "risky_phrasing", "severity": "warning", "message": "Use of CLIQUE AQUI"},'
            ' {"code": "missing_unsubscribe", "severity": "error", "message": "No unsubscribe link found"}'
            ']}'
        ])
        result = _run(review_deliverability("<p>CLIQUE AQUI AGORA!</p>"))
        assert len(result["findings"]) == 2
        assert result["findings"][0]["code"] == "risky_phrasing"

    def test_returns_empty_findings_on_clean_email(self):
        from app.services.ai_service import review_deliverability
        _install_fake(['{"findings": []}'])
        result = _run(review_deliverability("<p>Hello</p>"))
        assert result == {"findings": []}

    def test_returns_empty_on_unparseable(self):
        from app.services.ai_service import review_deliverability
        _install_fake(["garbage"])
        result = _run(review_deliverability("<p>x</p>"))
        assert result == {"findings": []}


# ─── M7 — translate_template ───────────────────────────────────────────────


class TestTranslateTemplate:
    def test_translates_preserving_placeholders(self):
        from app.services.ai_service import translate_template
        _install_fake(["<p>Hello {{name}}, welcome!</p>"])
        html = _run(translate_template("<p>Olá {{name}}, bem-vindo!</p>", "en"))
        assert "{{name}}" in html
        assert "Hello" in html

    def test_unsupported_target_returns_original(self):
        from app.services.ai_service import translate_template
        original = "<p>Olá</p>"
        assert _run(translate_template(original, "jp")) == original

    def test_supports_en(self):
        from app.services.ai_service import translate_template
        _install_fake(["<p>translated-to-en</p>"])
        assert "translated-to-en" in _run(translate_template("<p>olá</p>", "en"))

    def test_supports_es(self):
        from app.services.ai_service import translate_template
        _install_fake(["<p>translated-to-es</p>"])
        assert "translated-to-es" in _run(translate_template("<p>olá</p>", "es"))

    def test_supports_fr(self):
        from app.services.ai_service import translate_template
        _install_fake(["<p>translated-to-fr</p>"])
        assert "translated-to-fr" in _run(translate_template("<p>olá</p>", "fr"))

    def test_llm_not_configured_returns_original(self):
        from app.services.ai_service import translate_template
        from noctusai_lib.integrations.llm.client import _reset_for_testing
        _reset_for_testing()
        original = "<p>Olá</p>"
        assert _run(translate_template(original, "en")) == original
