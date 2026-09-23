"""`SmtpConfig` construction + `from_credentials` — the shared shape both
the digest path and the general-purpose sender build off."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.email.config import SmtpConfig
from noctusai_lib.integrations.email.errors import EmailNotConfigured


class TestSecurityValidation:
    def test_rejects_invalid_security(self):
        with pytest.raises(ValueError):
            SmtpConfig(
                host="h", port=587, username="u", password="p", security="bogus",
            )

    def test_accepts_each_mode(self):
        for mode in ("ssl", "starttls", "none"):
            cfg = SmtpConfig(
                host="h", port=587, username="u", password="p", security=mode,
            )
            assert cfg.security == mode


class TestFromCredentials:
    def test_full_creds_build(self):
        cfg = SmtpConfig.from_credentials({
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_username": "bot@example.com",
            "smtp_password": "sekret",
            "smtp_security": "starttls",
            "email_from": "bot@example.com",
            "email_from_name": "NoctusAI",
        })
        assert cfg.host == "smtp.example.com"
        assert cfg.port == 587
        assert cfg.username == "bot@example.com"
        assert cfg.password == "sekret"
        assert cfg.security == "starttls"
        assert cfg.from_email == "bot@example.com"
        assert cfg.from_name == "NoctusAI"

    def test_missing_host_raises_not_configured(self):
        with pytest.raises(EmailNotConfigured):
            SmtpConfig.from_credentials({
                "smtp_port": "587",
                "smtp_username": "u",
                "smtp_password": "p",
            })

    def test_missing_password_raises_not_configured(self):
        with pytest.raises(EmailNotConfigured):
            SmtpConfig.from_credentials({
                "smtp_host": "h", "smtp_port": "587", "smtp_username": "u",
            })

    def test_non_integer_port_raises_not_configured(self):
        with pytest.raises(EmailNotConfigured):
            SmtpConfig.from_credentials({
                "smtp_host": "h", "smtp_port": "not-a-port",
                "smtp_username": "u", "smtp_password": "p",
            })

    def test_missing_security_defaults_to_starttls(self):
        cfg = SmtpConfig.from_credentials({
            "smtp_host": "h", "smtp_port": "587",
            "smtp_username": "u", "smtp_password": "p",
        })
        assert cfg.security == "starttls"

    def test_invalid_security_falls_back_to_starttls(self):
        cfg = SmtpConfig.from_credentials({
            "smtp_host": "h", "smtp_port": "587",
            "smtp_username": "u", "smtp_password": "p",
            "smtp_security": "bogus",
        })
        assert cfg.security == "starttls"

    def test_missing_email_from_defaults_to_username(self):
        cfg = SmtpConfig.from_credentials({
            "smtp_host": "h", "smtp_port": "587",
            "smtp_username": "bot@example.com", "smtp_password": "p",
        })
        assert cfg.from_email == "bot@example.com"
