"""Unit tests for `noctusai_lib.domain.digest`.

Network-free. Patches `chat_completion` at the LLM-SDK boundary (the
narrative module's local binding) and `send_digest` at the email-SDK
boundary (the orchestrate module's local binding). Both are external
integrations; not patching our own domain logic.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from noctusai_lib.domain.digest import (
    build_and_send,
    email_template_dir,
    narrative,
    render_digest_pair,
    render_with_narrative,
)
from noctusai_lib.integrations.email.digest import Digest, DigestSendResult


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# narrative()
# ---------------------------------------------------------------------------


class TestNarrative:
    def test_happy_path_returns_stripped_llm_response(self):
        with patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.return_value = "  three\n\nparagraph\n\nresponse  "
            result = _run(narrative(
                system="sys",
                user_prompt="usr",
                model="gpt-4o-mini",
                cache=True,
                org_id="org-1",
                fallback="(fallback)",
            ))
            assert result == "three\n\nparagraph\n\nresponse"
            mock_chat.assert_awaited_once()

    def test_passes_standard_kwargs_to_chat_completion(self):
        with patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.return_value = "ok"
            _run(narrative(
                system="security analyst",
                user_prompt="data",
                model="gpt-4o-mini",
                cache=False,
                org_id="org-2",
                fallback="(fb)",
            ))
            kwargs = mock_chat.await_args.kwargs
            assert kwargs["model"] == "gpt-4o-mini"
            assert kwargs["temperature"] == 0.0
            assert kwargs["max_tokens"] == 600
            assert kwargs["cache"] is False
            assert kwargs["org_id"] == "org-2"
            assert kwargs["messages"] == [
                {"role": "system", "content": "security analyst"},
                {"role": "user", "content": "data"},
            ]

    def test_max_tokens_and_temperature_overridable(self):
        with patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.return_value = "ok"
            _run(narrative(
                system="s", user_prompt="u", model="gpt-4o", cache=True,
                org_id=None, fallback="(fb)", max_tokens=1200, temperature=0.7,
            ))
            kwargs = mock_chat.await_args.kwargs
            assert kwargs["max_tokens"] == 1200
            assert kwargs["temperature"] == 0.7

    def test_llm_failure_returns_fallback(self):
        with patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("provider down")
            result = _run(narrative(
                system="s",
                user_prompt="u",
                model="gpt-4o-mini",
                cache=True,
                org_id="org-1",
                fallback="The fallback narrative.",
            ))
            assert result == "The fallback narrative."

    def test_llm_failure_logs_warning(self, caplog):
        with patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
        ) as mock_chat:
            mock_chat.side_effect = RuntimeError("boom")
            caplog.set_level("WARNING", logger="noctusai_lib.domain.digest.narrative")
            _run(narrative(
                system="s", user_prompt="u", model="m", cache=True,
                org_id=None, fallback="(fb)",
            ))
            assert any(
                "LLM unavailable" in rec.message for rec in caplog.records
            )


# ---------------------------------------------------------------------------
# render_with_narrative()
# ---------------------------------------------------------------------------


class TestRenderWithNarrative:
    def test_auto_derives_paragraphs_and_threads_prompt_version(self, tmp_path):
        # Build minimal templates the helper can locate.
        html = tmp_path / "x.html.j2"
        text = tmp_path / "x.txt.j2"
        html.write_text(
            "<html><body>"
            "{% for p in narrative_paragraphs %}<p>{{ p }}</p>{% endfor %}"
            "<small>{{ prompt_version }}</small>"
            "</body></html>"
        )
        text.write_text(
            "{% for p in narrative_paragraphs %}{{ p }}\n\n{% endfor %}"
            "[{{ prompt_version }}]"
        )
        rendered_html, rendered_text = render_with_narrative(
            html_template="x.html.j2",
            text_template="x.txt.j2",
            narrative="Para A.\n\nPara B.\n\nPara C.",
            context={},
            search_paths=[tmp_path],
            prompt_version="test@v1",
        )
        # Paragraphs derived correctly.
        assert "<p>Para A.</p>" in rendered_html
        assert "<p>Para B.</p>" in rendered_html
        assert "<p>Para C.</p>" in rendered_html
        assert "<small>test@v1</small>" in rendered_html
        assert "Para A." in rendered_text
        assert "[test@v1]" in rendered_text

    def test_caller_context_wins_on_collision(self, tmp_path):
        html = tmp_path / "x.html.j2"
        text = tmp_path / "x.txt.j2"
        html.write_text("HTML:{{ prompt_version }}|{{ extra }}")
        text.write_text("TEXT:{{ prompt_version }}|{{ extra }}")
        rendered_html, rendered_text = render_with_narrative(
            html_template="x.html.j2",
            text_template="x.txt.j2",
            narrative="hi",
            context={"prompt_version": "caller-wins@v9", "extra": "x"},
            search_paths=[tmp_path],
            prompt_version="seed-default@v1",
        )
        assert "caller-wins@v9" in rendered_html
        assert "caller-wins@v9" in rendered_text

    def test_empty_narrative_yields_empty_paragraph_list(self, tmp_path):
        html = tmp_path / "x.html.j2"
        text = tmp_path / "x.txt.j2"
        html.write_text("HTML:{{ narrative_paragraphs|length }}")
        text.write_text("TEXT:{{ narrative_paragraphs|length }}")
        rendered_html, rendered_text = render_with_narrative(
            html_template="x.html.j2",
            text_template="x.txt.j2",
            narrative="",
            context={},
            search_paths=[tmp_path],
            prompt_version="v1",
        )
        assert rendered_html == "HTML:0"
        assert rendered_text == "TEXT:0"

    def test_single_paragraph_yields_single_element_list(self, tmp_path):
        html = tmp_path / "x.html.j2"
        text = tmp_path / "x.txt.j2"
        html.write_text("HTML:{{ narrative_paragraphs|length }}|{{ narrative_paragraphs[0] }}")
        text.write_text("TEXT:{{ narrative_paragraphs|length }}")
        rendered_html, _ = render_with_narrative(
            html_template="x.html.j2",
            text_template="x.txt.j2",
            narrative="Just one paragraph, no double newlines.",
            context={},
            search_paths=[tmp_path],
            prompt_version="v1",
        )
        assert rendered_html.startswith("HTML:1|Just one paragraph")


# ---------------------------------------------------------------------------
# build_and_send()
# ---------------------------------------------------------------------------


class TestBuildAndSend:
    def test_happy_path_returns_5_key_dict(self):
        with patch(
            "noctusai_lib.domain.digest.orchestrate.send_digest",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = DigestSendResult(
                sent=True, dry_run=False, external_id="msg_42", error=None,
                subject="Weekly review",
            )
            digest = Digest(subject="Weekly review", text="body", html="<p>body</p>")
            result = _run(build_and_send(
                digest, recipient="a@b.com", org_id="org-1", log_prefix="WEEKLY",
            ))
            assert result == {
                "sent": True,
                "dry_run": False,
                "external_id": "msg_42",
                "error": None,
                "subject": "Weekly review",
            }
            mock_send.assert_awaited_once()
            call_kwargs = mock_send.await_args.kwargs
            assert call_kwargs["recipient"] == "a@b.com"
            assert call_kwargs["org_id"] == "org-1"
            assert call_kwargs["log_prefix"] == "WEEKLY"

    def test_dry_run_path_carries_dry_run_true(self):
        with patch(
            "noctusai_lib.domain.digest.orchestrate.send_digest",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = DigestSendResult(
                sent=False, dry_run=True, external_id=None, error=None,
                subject="Audit digest",
            )
            digest = Digest(subject="Audit digest", text="body")
            result = _run(build_and_send(
                digest, recipient="admin@org.com", org_id=None, log_prefix="AUDIT",
            ))
            assert result["sent"] is False
            assert result["dry_run"] is True
            assert result["external_id"] is None

    def test_error_path_carries_error_string(self):
        with patch(
            "noctusai_lib.domain.digest.orchestrate.send_digest",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = DigestSendResult(
                sent=False, dry_run=False, external_id=None, error="Resend 5xx",
                subject="X",
            )
            digest = Digest(subject="X", text="b")
            result = _run(build_and_send(
                digest, recipient="x@y.com", org_id="org-2", log_prefix="X",
            ))
            assert result["sent"] is False
            assert result["dry_run"] is False
            assert result["error"] == "Resend 5xx"
            assert result["subject"] == "X"


# ---------------------------------------------------------------------------
# email_template_dir()
# ---------------------------------------------------------------------------


class TestEmailTemplateDir:
    """Replaces `Path(__file__).resolve().parent.parent / "email_templates"`
    that recurred verbatim in 5 products before formalization."""

    def test_resolves_relative_to_caller(self, tmp_path):
        """Given a service file at `<root>/services/<name>_service.py`,
        the helper resolves to `<root>/email_templates/`."""
        services_dir = tmp_path / "app" / "services"
        services_dir.mkdir(parents=True)
        fake_service_file = str(services_dir / "fake_digest_service.py")

        result = email_template_dir(fake_service_file)
        assert result == tmp_path / "app" / "email_templates"

    def test_returns_path_object(self, tmp_path):
        """Adopters use the result as a Path (e.g. for Jinja search_paths
        or os.fspath); confirm the return is `pathlib.Path`."""
        from pathlib import Path

        services_dir = tmp_path / "app" / "services"
        services_dir.mkdir(parents=True)
        result = email_template_dir(str(services_dir / "x_service.py"))
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# render_digest_pair()
# ---------------------------------------------------------------------------


class TestRenderDigestPair:
    """Convenience over `render_with_narrative` for the common case where
    html + text templates share a basename."""

    def test_derives_html_and_text_template_names(self, tmp_path):
        """The basename `audit_digest` resolves to `audit_digest.html.j2`
        + `audit_digest.txt.j2`."""
        templates = tmp_path / "email_templates"
        templates.mkdir()
        (templates / "audit_digest.html.j2").write_text(
            "<p>{{ org_name }}: {{ narrative }}</p>"
        )
        (templates / "audit_digest.txt.j2").write_text(
            "{{ org_name }}: {{ narrative }}"
        )

        html, text = render_digest_pair(
            "audit_digest",
            narrative="Hello world.",
            context={"org_name": "Acme"},
            search_paths=[templates],
            prompt_version="audit@v1",
        )
        assert "Acme: Hello world." in html
        assert "Acme: Hello world." in text

    def test_passes_through_to_render_with_narrative(self, tmp_path):
        """`render_digest_pair` is a thin wrapper — assert it calls
        `render_with_narrative` with the derived template names + the
        same arguments."""
        from unittest.mock import patch

        with patch(
            "noctusai_lib.domain.digest.render.render_with_narrative",
            return_value=("<p>html</p>", "text"),
        ) as mock_render:
            render_digest_pair(
                "weekly_review",
                narrative="N",
                context={"k": "v"},
                search_paths=["/tmp/templates"],
                prompt_version="weekly@v2",
            )
        mock_render.assert_called_once_with(
            html_template="weekly_review.html.j2",
            text_template="weekly_review.txt.j2",
            narrative="N",
            context={"k": "v"},
            search_paths=["/tmp/templates"],
            prompt_version="weekly@v2",
        )
