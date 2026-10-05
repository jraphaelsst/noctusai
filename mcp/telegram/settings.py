"""Telegram connector settings — MTProto user-account (Telethon) credentials.

Unlike every HTTP connector in this repo, Telegram's user API is MTProto, a
binary protocol over its own TCP transport — so `_kit.transport` (stdlib
`urllib`) does NOT apply here. Telethon owns the wire; `client.py` wraps it
behind a DI seam, the same role `client.py` plays for trello.

Secrets live in this connector's own gitignored `mcp/telegram/.env`
(`TELEGRAM_API_ID`, `TELEGRAM_API_HASH` from https://my.telegram.org). The
authenticated login lives in a Telethon session file under the gitignored
`mcp/telegram/.session/` — a session file IS a full account login, so it is
never committed, never logged, and is created 0600 in a 0700 directory by
`login.py` (the interactive carve-out; MCP tools never take codes/passwords).

Deliberately NOT backed by a `noctusai_lib.integrations` seed adapter: no
product consumes Telegram, so a seed IO module would ship Fake+Real+factory
for a consumer that does not exist (same stance as `mcp/trello`).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings

CONNECTOR_DIR = Path(__file__).resolve().parent
#: Gitignored, 0700. Holds the Telethon session (a full account login).
SESSION_DIR = CONNECTOR_DIR / ".session"
#: Telethon appends `.session` itself; this is the path WITHOUT the suffix.
SESSION_BASE = SESSION_DIR / "noctus"
SESSION_FILE = SESSION_DIR / "noctus.session"
#: Gitignored. `telegram.messages.export` only ever writes under here.
EXPORTS_DIR = CONNECTOR_DIR / ".exports"


@dataclass(frozen=True)
class TelegramConnectorSettings(ConnectorSettings):
    """Frozen config. `api_id`/`api_hash` are secrets — never echoed."""

    api_id: Optional[str] = None
    api_hash: Optional[str] = None
    session_base: str = str(SESSION_BASE)
    session_file: str = str(SESSION_FILE)
    #: Optional override (TELEGRAM_EXPORTS_DIR); default `.exports/`.
    exports_dir_override: Optional[str] = None
    #: Upper bound on a single FloodWait sleep (seconds) during export.
    max_flood_wait_seconds: int = 120

    @property
    def exports_dir(self) -> str:
        return self.exports_dir_override or str(EXPORTS_DIR)

    @property
    def configured(self) -> bool:
        """Both halves present and `api_id` numeric. Whether the SESSION is
        logged in is a separate question (`connection_status`)."""
        return bool(self.api_id) and bool(self.api_hash) and str(self.api_id).isdigit()


get_settings = make_get_settings(
    TelegramConnectorSettings,
    dotenv_dir=CONNECTOR_DIR,
    env_map={"api_id": "TELEGRAM_API_ID", "api_hash": "TELEGRAM_API_HASH",
             "exports_dir_override": "TELEGRAM_EXPORTS_DIR"},
)

__all__ = [
    "CONNECTOR_DIR", "SESSION_DIR", "SESSION_BASE", "SESSION_FILE", "EXPORTS_DIR",
    "TelegramConnectorSettings", "get_settings",
]
