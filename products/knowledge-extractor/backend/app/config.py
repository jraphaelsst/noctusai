"""Configuration.

Mirrors noc's `ProductSettings` shape (pydantic-settings, read from `.env`).
On absorption this becomes a `ProductSettings` subclass.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = two levels up from this file (backend/app/config.py → repo/).
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings, sourced from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── OpenAI ──────────────────────────────────────────────────────
    openai_api_key: str = ""
    transcribe_model: str = "gpt-4o-mini-transcribe"
    summary_model: str = "gpt-4o"
    transcribe_language: str = "pt"

    # ── Google Drive ────────────────────────────────────────────────
    # Backend selection: "auto" | "oauth" | "api" | "gdown" (see factory.py).
    drive_backend: str = "auto"
    # API key path (reaches "anyone-with-link" public files only).
    google_api_key: str = ""
    # OAuth path (required for folders shared privately *with your account*).
    # Reused from noc's working Google OAuth client (same account).
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8140/oauth/google/callback"
    # Alternative: a downloaded "Desktop app" client_secret.json (used only if
    # client_id/secret above are unset).
    google_oauth_client_secret_file: str = "secrets/client_secret.json"
    google_oauth_token_file: str = "secrets/drive_token.json"

    # ── Pipeline ────────────────────────────────────────────────────
    chunk_seconds: int = 600
    data_dir: str = "data"

    # ── Knowledge base / agents ─────────────────────────────────────
    # Backend for the methodology KB. "local" (file cache, offline) now;
    # swap to Supabase by setting the creds below (seam swap, no code change).
    embedding_model: str = "text-embedding-3-small"  # 1536-dim
    kb_local_path: str = "data/kb_local.json"        # gitignored local cache
    agent_model: str = "gpt-4o"                       # chat model for specialist agents
    # Supabase KB (optional — only needed for the live/remote backend):
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    @property
    def data_path(self) -> Path:
        """Absolute data directory (resolved relative to repo root)."""
        p = Path(self.data_dir)
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (mirrors noc's `settings` singleton)."""
    return Settings()


# Module-level singleton — `create_product_app` (app/main.py) + the CLI both
# import `settings`. NOTE (absorption follow-up): make `Settings` subclass
# `noctusai_lib`'s ProductSettings so credential/LLM resolution is fully
# noc-native (Gate-6 consumer adaptation, in flight).
settings = get_settings()
