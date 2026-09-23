"""Shared doubles + config for the e-mail slice tests (wave-2 slice B).

Config reaches the code through ONE injected value (`EmailSettings`, via the
`app.email_deps.get_email_settings` dependency) — tests build it here instead
of mutating the global settings object.
"""
from __future__ import annotations

from dataclasses import replace

from cryptography.fernet import Fernet
from noctusai_lib.integrations.email import FakeEmailSender
from noctusai_lib.integrations.email.errors import EmailSendError

from app.dependencies import coerce_org_uuid
from app.services.email_config import EmailSettings

ORG = str(coerce_org_uuid("test-org-123"))
CHAVE = Fernet.generate_key().decode()
BASE = "https://igig.example.test"
MAILBOX = "agencia@gmail.com"
SENHA = "senha-smtp-super-secreta"
SMTP = {
    "host": "smtp.gmail.com", "port": 465, "username": "agencia@gmail.com",
    "password": SENHA, "security": "ssl",
    "from_email": "agencia@gmail.com", "from_name": "Agência Sol",
}

SEM_GCP = EmailSettings(
    cofre_key=CHAVE,
    google_oauth_client_id="cid.apps.googleusercontent.com",
    google_oauth_client_secret="csecret",
    public_url=BASE,
)
COM_GCP = replace(
    SEM_GCP,
    gmail_push_gcp_project="noctus-proj",
    gmail_push_topic="gmail-replies",
    gmail_push_audience=f"{BASE}/api/webhooks/gmail/push",
    gmail_push_service_account="gmail-push@noctus-proj.iam.gserviceaccount.com",
)
TOPICO = "projects/noctus-proj/topics/gmail-replies"


class ConfigBox:
    """Mutable holder the `get_email_settings` override reads per request."""

    def __init__(self, valor: EmailSettings = SEM_GCP) -> None:
        self.valor = valor

    def __call__(self) -> EmailSettings:
        return self.valor


class Senders:
    """The sender-factory double: records every resolved `SmtpConfig` and
    hands back ONE `FakeEmailSender`, so a test can read `.fake.sent`."""

    def __init__(self) -> None:
        self.fake = FakeEmailSender()
        self.configs: list = []
        self.falhar = False

    def __call__(self, config):
        self.configs.append(config)
        return _Quebrado() if self.falhar else self.fake


class _Quebrado:
    async def send(self, email):
        raise EmailSendError("SMTP auth failed for 'agencia@gmail.com'")
