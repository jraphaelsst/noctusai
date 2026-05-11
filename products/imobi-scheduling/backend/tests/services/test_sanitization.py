"""Tests for `app.services.sanitization` — Phase 11 security hardening.

Verifies PII redaction patterns + the `wrap_handler` seam.
"""
from __future__ import annotations

import json

import pytest

from noctusai_lib.domain.chatbot import ToolCall, ToolResult

from app.services.sanitization import (
    sanitize_json_payload,
    sanitize_tool_result,
    wrap_handler,
)


class TestEmailRedaction:
    def test_simple_email(self):
        out = sanitize_tool_result("Contato: user@example.com aqui")
        assert "user@example.com" not in out
        assert "[REDACTED_EMAIL]" in out

    def test_multiple_emails(self):
        out = sanitize_tool_result("a@b.co e c@d.org")
        assert out.count("[REDACTED_EMAIL]") == 2

    def test_email_in_json(self):
        raw = json.dumps({"email": "user@example.com"})
        out = sanitize_tool_result(raw)
        assert "user@example.com" not in out
        # Result still parses as JSON.
        parsed = json.loads(out)
        assert "[REDACTED_EMAIL]" in parsed["email"]


class TestPhoneRedaction:
    def test_formatted_brazilian_phone(self):
        out = sanitize_tool_result("Ligue (11) 99999-9999 hoje")
        assert "99999-9999" not in out
        assert "[REDACTED_PHONE]" in out

    def test_e164_brazilian(self):
        out = sanitize_tool_result("Telefone: +5511999999999")
        assert "5511999999999" not in out
        assert "[REDACTED_PHONE]" in out

    def test_country_code_spaced(self):
        out = sanitize_tool_result("Phone +55 11 99999-9999")
        assert "[REDACTED_PHONE]" in out


class TestCpfRedaction:
    def test_formatted_cpf(self):
        out = sanitize_tool_result("CPF: 123.456.789-00 confirma?")
        assert "123.456.789-00" not in out
        assert "[REDACTED_CPF]" in out

    def test_digit_stream_cpf(self):
        out = sanitize_tool_result("CPF 12345678900 aqui")
        assert "12345678900" not in out
        assert "REDACTED" in out


class TestCnpjRedaction:
    def test_formatted_cnpj(self):
        out = sanitize_tool_result("CNPJ 12.345.678/0001-90 da imobiliaria")
        assert "12.345.678/0001-90" not in out
        assert "[REDACTED_CNPJ]" in out

    def test_digit_stream_cnpj(self):
        out = sanitize_tool_result("CNPJ 12345678000190")
        assert "12345678000190" not in out
        assert "REDACTED" in out


class TestUrlWithCredsRedaction:
    def test_basic_auth_url(self):
        out = sanitize_tool_result("Use https://admin:s3cret@api.example.com/x")
        assert "admin:s3cret" not in out
        assert "[REDACTED_URL_WITH_CREDS]" in out

    def test_normal_url_unaffected(self):
        out = sanitize_tool_result("Veja https://example.com/property/42")
        assert "example.com/property/42" in out
        assert "REDACTED_URL" not in out


class TestMixedPii:
    def test_all_patterns_redacted(self):
        text = (
            "Corretor user@example.com tel (11) 99999-9999 "
            "CPF 123.456.789-00 CNPJ 12.345.678/0001-90 "
            "auth https://u:p@host.com"
        )
        out = sanitize_tool_result(text)
        for sensitive in [
            "user@example.com",
            "99999-9999",
            "123.456.789-00",
            "12.345.678/0001-90",
            "u:p",
        ]:
            assert sensitive not in out

    def test_no_pii_unchanged(self):
        text = "Imovel ID 42 no Condominio Sol, valor 350000"
        out = sanitize_tool_result(text)
        assert out == text

    def test_idempotent(self):
        text = "user@example.com e (11) 99999-9999"
        once = sanitize_tool_result(text)
        twice = sanitize_tool_result(once)
        assert once == twice


class TestEmptyInput:
    def test_empty_string(self):
        assert sanitize_tool_result("") == ""


class TestSanitizeJsonPayload:
    def test_walks_dict(self):
        out = sanitize_json_payload({"email": "u@x.com", "id": 42})
        assert out["email"] == "[REDACTED_EMAIL]"
        assert out["id"] == 42

    def test_walks_nested(self):
        payload = {"corretor": {"phone": "(11) 99999-9999"}, "ids": [1, 2]}
        out = sanitize_json_payload(payload)
        assert "[REDACTED_PHONE]" in out["corretor"]["phone"]
        assert out["ids"] == [1, 2]

    def test_walks_list_of_dicts(self):
        payload = {"crew": [{"email": "a@b.co"}, {"email": "c@d.io"}]}
        out = sanitize_json_payload(payload)
        assert out["crew"][0]["email"] == "[REDACTED_EMAIL]"
        assert out["crew"][1]["email"] == "[REDACTED_EMAIL]"


class TestWrapHandler:
    def test_wrap_sanitizes_content(self):
        def raw_handler(call: ToolCall) -> ToolResult:
            payload = {"property_id": 42, "owner_email": "owner@x.com"}
            return ToolResult(
                call_id=call.call_id,
                content=json.dumps(payload, ensure_ascii=False),
            )

        wrapped = wrap_handler(raw_handler)
        result = wrapped(
            ToolCall(call_id="c-1", name="lookup_property", arguments={})
        )
        parsed = json.loads(result.content)
        assert parsed["property_id"] == 42
        assert parsed["owner_email"] == "[REDACTED_EMAIL]"

    def test_wrap_preserves_call_id(self):
        def raw_handler(call: ToolCall) -> ToolResult:
            return ToolResult(call_id=call.call_id, content='{"ok": true}')

        wrapped = wrap_handler(raw_handler)
        result = wrapped(ToolCall(call_id="c-42", name="noop", arguments={}))
        assert result.call_id == "c-42"

    def test_wrap_no_pii_passes_unchanged(self):
        clean_content = '{"property_id": 42, "status": "available"}'

        def raw_handler(call: ToolCall) -> ToolResult:
            return ToolResult(call_id=call.call_id, content=clean_content)

        wrapped = wrap_handler(raw_handler)
        result = wrapped(ToolCall(call_id="c", name="x", arguments={}))
        assert result.content == clean_content
