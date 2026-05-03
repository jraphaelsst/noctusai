"""Unit tests for `noctusai_lib.email.digest` — Tier 2 Phase 4 (P3 pattern).

Network-free. Uses `monkeypatch` to swap `_resolve_resend_config` and
`_post_to_resend` so we never reach Resend.
"""
from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.email.digest import (
    Digest,
    DigestSendResult,
    send_digest,
)
from noctusai_lib.integrations.email import digest as digest_module


def _run(coro):
    return asyncio.run(coro)


class TestDigestDataclass:
    def test_html_optional(self):
        d = Digest(subject="Hi", text="hello")
        assert d.html is None

    def test_with_html(self):
        d = Digest(subject="Hi", text="hello", html="<p>hello</p>")
        assert d.html == "<p>hello</p>"


class TestSendDigestDryRun:
    def test_no_resend_key_returns_dry_run(self, monkeypatch):
        monkeypatch.setattr(digest_module, "_resolve_resend_config", lambda org_id: None)
        d = Digest(subject="Test", text="body")
        result = _run(send_digest(d, recipient="a@example.com"))
        assert result.sent is False
        assert result.dry_run is True
        assert result.subject == "Test"
        assert result.error is None

    def test_dry_run_includes_subject(self, monkeypatch):
        monkeypatch.setattr(digest_module, "_resolve_resend_config", lambda org_id: None)
        d = Digest(subject="Weekly review", text="b")
        result = _run(send_digest(d, recipient="x@y.com", log_prefix="WEEKLY"))
        assert result.subject == "Weekly review"


class TestSendDigestSuccess:
    def test_returns_external_id_on_success(self, monkeypatch):
        monkeypatch.setattr(
            digest_module, "_resolve_resend_config",
            lambda org_id: {"api_key": "k", "from_email": "f@e.com", "from_name": "F"},
        )

        async def _fake_post(config, to, dig):
            return {"id": "msg_abc123"}

        monkeypatch.setattr(digest_module, "_post_to_resend", _fake_post)
        d = Digest(subject="Hi", text="b", html="<p>b</p>")
        result = _run(send_digest(d, recipient="a@b.com"))
        assert result.sent is True
        assert result.dry_run is False
        assert result.external_id == "msg_abc123"
        assert result.error is None

    def test_passes_html_when_provided(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(
            digest_module, "_resolve_resend_config",
            lambda org_id: {"api_key": "k", "from_email": "f@e.com", "from_name": "F"},
        )

        async def _capture(config, to, dig):
            captured["digest"] = dig
            captured["to"] = to
            return {"id": "x"}

        monkeypatch.setattr(digest_module, "_post_to_resend", _capture)
        d = Digest(subject="S", text="t", html="<p>t</p>")
        _run(send_digest(d, recipient="a@b.com"))
        assert captured["digest"].html == "<p>t</p>"
        assert captured["to"] == "a@b.com"


class TestSendDigestErrors:
    def test_invalid_recipient_returns_error(self):
        d = Digest(subject="Hi", text="b")
        result = _run(send_digest(d, recipient="not-an-email"))
        assert result.sent is False
        assert result.dry_run is False
        assert result.error and "invalid recipient" in result.error

    def test_empty_recipient_returns_error(self):
        d = Digest(subject="Hi", text="b")
        result = _run(send_digest(d, recipient=""))
        assert result.sent is False
        assert result.error

    def test_resend_failure_swallowed(self, monkeypatch):
        monkeypatch.setattr(
            digest_module, "_resolve_resend_config",
            lambda org_id: {"api_key": "k", "from_email": "f@e.com", "from_name": "F"},
        )

        async def _boom(config, to, dig):
            raise RuntimeError("Resend down")

        monkeypatch.setattr(digest_module, "_post_to_resend", _boom)
        d = Digest(subject="Hi", text="b")
        result = _run(send_digest(d, recipient="a@b.com"))
        assert result.sent is False
        assert result.error == "Resend down"
        assert result.dry_run is False


class TestResolveResendConfig:
    def test_no_key_returns_none(self, monkeypatch):
        from noctusai_lib.config import credentials as creds
        monkeypatch.setattr(creds, "resolve_credential", lambda key, org_id=None: None)
        from noctusai_lib.integrations.email.digest import _resolve_resend_config
        assert _resolve_resend_config(org_id="org-1") is None

    def test_with_key_uses_defaults_when_from_unset(self, monkeypatch):
        # `resolve_credential` returns the api key but not the from-overrides.
        def fake_resolve(name, org_id=None):
            if name == "resend_api_key":
                return "re_xxx"
            return None
        from noctusai_lib.config import credentials as creds
        monkeypatch.setattr(creds, "resolve_credential", fake_resolve)
        # Need to re-import the digest module's reference too because it
        # imported `resolve_credential` at module load time.
        monkeypatch.setattr(digest_module, "resolve_credential", fake_resolve)
        from noctusai_lib.integrations.email.digest import _resolve_resend_config
        cfg = _resolve_resend_config(org_id="org-1")
        assert cfg is not None
        assert cfg["api_key"] == "re_xxx"
        assert cfg["from_email"] == "noreply@noctus.app"
        assert cfg["from_name"] == "NoctusAI"


# ---------------------------------------------------------------------------
# Jinja `render()` (formalized 2026-04-25 after 5 adopters)
# ---------------------------------------------------------------------------


class TestRender:

    def _write(self, root, name, content):
        path = root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_extends_lib_base_layout_html(self, tmp_path):
        from noctusai_lib.integrations.email.digest import render
        self._write(tmp_path, "demo.html.j2", (
            '{% extends "_digest_base.html.j2" %}'
            '{% block header %}Olá {{ name }}{% endblock %}'
            '{% block body %}<p>{{ count }} itens</p>{% endblock %}'
            '{% block footer %} · v1{% endblock %}'
        ))
        self._write(tmp_path, "demo.txt.j2", (
            '{% extends "_digest_base.txt.j2" %}'
            '{% block header %}Olá {{ name }}{% endblock %}'
            '{% block body %}{{ count }} itens{% endblock %}'
            '{% block footer %} · v1{% endblock %}'
        ))
        html, text = render(
            html_template="demo.html.j2",
            text_template="demo.txt.j2",
            context={"name": "Ana", "count": 7},
            search_paths=[tmp_path],
        )
        assert "<h2" in html and "Olá Ana" in html
        assert "7 itens" in html
        assert "Gerado por NoctusAI" in html
        assert "Olá Ana" in text
        assert "-- NoctusAI · v1" in text

    def test_autoescape_blocks_xss_by_default(self, tmp_path):
        from noctusai_lib.integrations.email.digest import render
        self._write(tmp_path, "x.html.j2", (
            '{% extends "_digest_base.html.j2" %}'
            '{% block body %}{{ payload }}{% endblock %}'
        ))
        self._write(tmp_path, "x.txt.j2", (
            '{% extends "_digest_base.txt.j2" %}'
            '{% block body %}{{ payload }}{% endblock %}'
        ))
        html, _ = render(
            html_template="x.html.j2",
            text_template="x.txt.j2",
            context={"payload": '<script>alert(1)</script>'},
            search_paths=[tmp_path],
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_safe_filter_passes_pre_rendered_html(self, tmp_path):
        from noctusai_lib.integrations.email.digest import render
        self._write(tmp_path, "y.html.j2", (
            '{% extends "_digest_base.html.j2" %}'
            '{% block body %}{{ trusted | safe }}{% endblock %}'
        ))
        self._write(tmp_path, "y.txt.j2", (
            '{% extends "_digest_base.txt.j2" %}'
            '{% block body %}{{ trusted }}{% endblock %}'
        ))
        html, _ = render(
            html_template="y.html.j2",
            text_template="y.txt.j2",
            context={"trusted": '<p>narrative</p>'},
            search_paths=[tmp_path],
        )
        assert "<p>narrative</p>" in html

    def test_product_template_overrides_lib_when_same_name(self, tmp_path):
        from noctusai_lib.integrations.email.digest import render
        self._write(tmp_path, "_digest_base.html.j2", "<custom>{% block body %}{% endblock %}</custom>")
        self._write(tmp_path, "_digest_base.txt.j2", "[CUSTOM] {% block body %}{% endblock %}")
        self._write(tmp_path, "z.html.j2", (
            '{% extends "_digest_base.html.j2" %}'
            '{% block body %}body{% endblock %}'
        ))
        self._write(tmp_path, "z.txt.j2", (
            '{% extends "_digest_base.txt.j2" %}'
            '{% block body %}body{% endblock %}'
        ))
        html, text = render(
            html_template="z.html.j2",
            text_template="z.txt.j2",
            context={},
            search_paths=[tmp_path],
        )
        assert "<custom>" in html
        assert "[CUSTOM]" in text

    def test_template_not_found_raises(self, tmp_path):
        from jinja2.exceptions import TemplateNotFound
        from noctusai_lib.integrations.email.digest import render
        with pytest.raises(TemplateNotFound):
            render(
                html_template="missing.html.j2",
                text_template="missing.txt.j2",
                context={},
                search_paths=[tmp_path],
            )
