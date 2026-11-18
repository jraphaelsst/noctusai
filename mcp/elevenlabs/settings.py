"""ElevenLabs connector settings.

The API key is a secret and lives in the connector's own co-located
`.env` (`mcp/elevenlabs/.env`, gitignored by the repo-wide `.env` rule),
independent of the product/root `.env` ("every connector owns its own
auth store", `KB § INTEGRATIONS/vista.md § 1`). Env wins over the file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings

DEFAULT_BASE_URL = "https://api.elevenlabs.io"
DEFAULT_MAX_CHARS = 5000
_FALSE = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class ElevenLabsSettings(ConnectorSettings):
    """Frozen per-operator config. Every field arrives as a string (or None)."""

    api_key: Optional[str] = None
    output_dir: Optional[str] = None
    max_chars: Optional[str] = None
    zero_retention_raw: Optional[str] = None
    base_url_raw: Optional[str] = None
    timeout_seconds: float = 120.0  # TTS of long texts is slow

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def base_url(self) -> str:
        return (self.base_url_raw or DEFAULT_BASE_URL).rstrip("/")

    @property
    def max_chars_cap(self) -> int:
        try:
            v = int(self.max_chars or DEFAULT_MAX_CHARS)
        except ValueError:
            return DEFAULT_MAX_CHARS
        return v if v > 0 else DEFAULT_MAX_CHARS

    @property
    def zero_retention(self) -> bool:
        """Default ON (privacy-first); an explicit false/0/no/off turns it off."""
        return (self.zero_retention_raw or "true").strip().lower() not in _FALSE

    @property
    def default_output_dir(self) -> Path:
        """`ELEVENLABS_OUTPUT_DIR`, else `<private root>/elevenlabs` — the same
        private root every noc tool uses (`NOCTUS_PRIVATE_DIR`, default
        `~/.noctusai/private`), outside every git tree by construction."""
        if self.output_dir:
            return Path(self.output_dir).expanduser()
        raw = os.environ.get("NOCTUS_PRIVATE_DIR") or str(Path.home() / ".noctusai" / "private")
        return Path(raw).expanduser() / "elevenlabs"


get_settings = make_get_settings(
    ElevenLabsSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "api_key": "ELEVENLABS_API_KEY",
        "output_dir": "ELEVENLABS_OUTPUT_DIR",
        "max_chars": "ELEVENLABS_MAX_CHARS",
        "zero_retention_raw": "ELEVENLABS_ZERO_RETENTION",
        "base_url_raw": "ELEVENLABS_BASE_URL",
    },
)

__all__ = ["ElevenLabsSettings", "get_settings", "DEFAULT_BASE_URL"]
