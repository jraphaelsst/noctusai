"""`make_email_sender` — the Fake/Real seam consumers reach for."""
from __future__ import annotations

from noctusai_lib.integrations.email.config import SmtpConfig
from noctusai_lib.integrations.email.factory import make_email_sender
from noctusai_lib.integrations.email.fake_adapter import FakeEmailSender
from noctusai_lib.integrations.email.smtp_adapter import SmtpEmailSender


class TestMakeEmailSender:
    def test_no_config_returns_fake(self):
        assert isinstance(make_email_sender(None), FakeEmailSender)

    def test_no_args_returns_fake(self):
        assert isinstance(make_email_sender(), FakeEmailSender)

    def test_config_present_returns_real(self):
        cfg = SmtpConfig(
            host="h", port=587, username="u", password="p", from_email="u@h",
        )
        sender = make_email_sender(cfg)
        assert isinstance(sender, SmtpEmailSender)
        assert sender.config is cfg
