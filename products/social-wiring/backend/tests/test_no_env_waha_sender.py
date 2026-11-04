"""Guard (julia-line CONTRACT A3): no SW code sends through env WAHA settings -- every send resolves the org's line.

Only provisioning (`whatsapp_connections_router`: base_url + api_key to CREATE a connection) and webhook verification
(`webhook_hmac`, `waha_webhook_hmac_secret`) may read a WAHA env setting. The removed settings must stay removed.
"""
from __future__ import annotations

import ast
from pathlib import Path

from app.config import SocialWiringSettings

APP = Path(__file__).resolve().parents[1] / "app"
#: env WAHA settings that are NOT a sender credential, and who may read them.
SENDER_ATTRS = {"waha_base_url", "waha_api_key", "waha_session"}
PROVISIONING = {"routers/whatsapp_connections_router.py", "routers/settings_router.py"}  # settings: key-health display only


def _reads(path: Path) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute) and node.attr in SENDER_ATTRS:
            found.append((node.lineno, node.attr))
    return found


def test_no_app_module_reads_an_env_waha_sender_setting():
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        if rel in PROVISIONING:
            continue
        offenders += [f"{rel}:{ln} {what}" for ln, what in _reads(path)]
    assert not offenders, "env WAHA sender settings read outside provisioning: " + ", ".join(offenders)


def test_waha_session_and_the_one_chat_settings_are_gone():
    fields = SocialWiringSettings.model_fields
    for gone in ("waha_session", "whatsapp_authorized_numbers", "whatsapp_chatbot_enabled"):
        assert gone not in fields


def test_settings_router_never_sends_with_env_credentials():
    src = (APP / "routers/settings_router.py").read_text(encoding="utf-8")
    assert "settings.waha_" not in src
    assert "cfg.waha_session" not in src


def test_the_webhook_hmac_secret_is_kept_for_verification():
    assert "waha_webhook_hmac_secret" in SocialWiringSettings.model_fields
