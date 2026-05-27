"""OpenAI connector settings — API key + default models.

Resolution order (per `_kit.settings.make_get_settings`):
  1. Explicit kwargs to OpenAISettings(...)
  2. Environment variables (`OPENAI_API_KEY`, `OPENAI_DEFAULT_*_MODEL`)
  3. Co-located `mcp/openai/.env` (dev convenience)
  4. Repo-root `.env` fallback (because the platform key lives there)

The repo-root `.env` step is the noc-specific addition: the platform's
single OPENAI_API_KEY lives at `/.env` (not `mcp/openai/.env`), and we
don't want to duplicate the secret across files. `_load_repo_root_env`
walks up from this file looking for the first `.env` in a path that
contains `mcp/`. If found, its keys feed the SAME env-precedence chain
the kit already implements.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings


def _seed_repo_root_env() -> None:
    """Read repo-root `.env` once + populate `os.environ` for any keys
    not already set. The kit's settings layer reads `os.environ` next,
    so this becomes the third tier of precedence (explicit > env > .env).

    Idempotent — the first call seeds; subsequent calls are no-ops because
    keys already exist in os.environ.
    """
    # Walk up from this file to find the repo root (the dir holding `mcp/`).
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "mcp").is_dir() and (parent / ".env").exists():
            try:
                text = (parent / ".env").read_text(encoding="utf-8")
            except OSError:
                return
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
            return


_seed_repo_root_env()


_DEFAULT_CHAT_MODEL = "gpt-4o-mini"
_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_DEFAULT_VISION_MODEL = "gpt-4o"
_DEFAULT_AUDIO_MODEL = "whisper-1"


@dataclass(frozen=True)
class OpenAISettings(ConnectorSettings):
    """Frozen per-tenant OpenAI config (no tool handler can mutate).

    Model fields stay Optional + resolved via @property (mirrors github's
    `gh_path` pattern) — `_kit.settings.make_get_settings` passes `None`
    to the dataclass for unset env vars, which would shadow a non-None
    default. Optional + property keeps the default fallback while still
    allowing env override.
    """

    api_key: Optional[str] = None
    chat_model: Optional[str] = None
    embedding_model: Optional[str] = None
    vision_model: Optional[str] = None
    audio_model: Optional[str] = None
    timeout_seconds: float = 30.0

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def default_chat_model(self) -> str:
        return self.chat_model or _DEFAULT_CHAT_MODEL

    @property
    def default_embedding_model(self) -> str:
        return self.embedding_model or _DEFAULT_EMBEDDING_MODEL

    @property
    def default_vision_model(self) -> str:
        return self.vision_model or _DEFAULT_VISION_MODEL

    @property
    def default_audio_model(self) -> str:
        return self.audio_model or _DEFAULT_AUDIO_MODEL


get_settings = make_get_settings(
    OpenAISettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "api_key": "OPENAI_API_KEY",
        "chat_model": "OPENAI_DEFAULT_CHAT_MODEL",
        "embedding_model": "OPENAI_DEFAULT_EMBEDDING_MODEL",
        "vision_model": "OPENAI_DEFAULT_VISION_MODEL",
        "audio_model": "OPENAI_DEFAULT_AUDIO_MODEL",
    },
)


__all__ = ["OpenAISettings", "get_settings"]
