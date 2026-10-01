"""Tests for `app/services/captcha.py` — soft-launch captcha-off mode
(user decision 2026-10-01). The resolver is driven through its `resolve=`
DI seam (KB § PATTERNS/backend/di-test-seam.md) — never a monkeypatch.
"""
from __future__ import annotations

import asyncio
import logging

from noctusai_lib.integrations.turnstile import FakeTurnstileVerifier, RealTurnstileVerifier

from app.services.captcha import (
    CAPTCHA_DESATIVADO_LOG,
    CAPTCHA_SEM_SITE_KEY_LOG,
    CaptchaGate,
    resolve_captcha,
)

ORG = "00000000-0000-0000-0000-000000000001"


def _resolver(values: dict):
    return lambda name, org_id: values.get(name)


def _run(coro):
    return asyncio.run(coro)


class TestResolveCaptcha:
    def test_no_secret_is_explicitly_disabled_never_a_fake(self):
        gate = resolve_captcha(ORG, resolve=_resolver({}))
        assert gate.verificador is None
        assert gate.obrigatorio is False
        assert gate.publico() == {"obrigatorio": False, "site_key": None}

    def test_site_key_alone_does_not_enable_captcha(self):
        gate = resolve_captcha(ORG, resolve=_resolver({"turnstile_site_key": "0xsite"}))
        assert gate.publico() == {"obrigatorio": False, "site_key": None}

    def test_secret_and_site_key_build_the_real_verifier(self):
        gate = resolve_captcha(
            ORG, resolve=_resolver({"turnstile_secret_key": "0xsecret", "turnstile_site_key": "0xsite"}),
        )
        assert isinstance(gate.verificador, RealTurnstileVerifier)
        assert gate.publico() == {"obrigatorio": True, "site_key": "0xsite"}

    def test_secret_without_site_key_stays_required_and_logs_error(self, caplog):
        with caplog.at_level(logging.ERROR, logger="app.services.captcha"):
            gate = resolve_captcha(ORG, resolve=_resolver({"turnstile_secret_key": "0xsecret"}))
        assert gate.publico() == {"obrigatorio": True, "site_key": None}
        assert any(r.levelno == logging.ERROR and r.getMessage() == CAPTCHA_SEM_SITE_KEY_LOG for r in caplog.records)


class TestVerificar:
    def test_disabled_accepts_empty_token_and_warns_once(self, caplog):
        with caplog.at_level(logging.WARNING, logger="app.services.captcha"):
            ok = _run(CaptchaGate.desativado().verificar(None, remote_ip="1.2.3.4", rota="checkout"))
        assert ok is True
        warnings = [r for r in caplog.records if r.getMessage() == CAPTCHA_DESATIVADO_LOG]
        assert len(warnings) == 1
        assert warnings[0].levelno == logging.WARNING
        assert warnings[0].evento == "captcha_desativado"
        assert warnings[0].rota == "checkout"

    def test_enabled_rejects_missing_token(self):
        gate = CaptchaGate.com_verificador(FakeTurnstileVerifier(), site_key="0xsite")
        assert _run(gate.verificar(None, remote_ip=None, rota="checkout")) is False

    def test_enabled_rejects_bad_token(self):
        fake = FakeTurnstileVerifier()
        fake.rejected_tokens.add("bad")
        gate = CaptchaGate.com_verificador(fake, site_key="0xsite")
        assert _run(gate.verificar("bad", remote_ip=None, rota="checkout")) is False

    def test_enabled_accepts_valid_token(self):
        fake = FakeTurnstileVerifier()
        gate = CaptchaGate.com_verificador(fake, site_key="0xsite")
        assert _run(gate.verificar("tok", remote_ip="9.9.9.9", rota="cadastro")) is True
        assert fake.calls == [("tok", "9.9.9.9")]
