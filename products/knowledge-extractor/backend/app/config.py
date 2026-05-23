"""Configuration — noc-native ProductSettings subclass (absorbed 2026-05-23).

Inherits `noctusai_seed.config.ProductSettings` (→ `BaseAppSettings`) so the
product gets noc's standard fields (`supabase_*`, `jwt_secret`, `core_api_url`,
`cors_origins`, `debug`) + the prod-safety validators for free, and declares
only the knowledge-extractor domain fields here.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from noctusai_seed.config import ProductSettings

# Repo root = backend/app/config.py → up 4 = products/<slug>/backend/app →
# .../products/<slug>/backend → .../products/<slug> → .../products → repo root.
REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(ProductSettings):
    """Knowledge-extractor settings — ProductSettings + the domain fields.

    `supabase_url` / `supabase_anon_key` / `supabase_service_role_key` are
    inherited from `BaseAppSettings` (the live KB / vector store reads them).
    """

    # ── OpenAI ──────────────────────────────────────────────────────
    openai_api_key: str = ""
    transcribe_model: str = "gpt-4o-mini-transcribe"
    summary_model: str = "gpt-4o"
    transcribe_language: str = "pt"

    # ── Google Drive ────────────────────────────────────────────────
    # Backend selection: "auto" | "oauth" | "api" | "gdown" (see factory.py).
    drive_backend: str = "auto"
    google_api_key: str = ""
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8140/oauth/google/callback"
    google_oauth_client_secret_file: str = "secrets/client_secret.json"
    google_oauth_token_file: str = "secrets/drive_token.json"

    # ── Pipeline ────────────────────────────────────────────────────
    chunk_seconds: int = 600
    data_dir: str = "data"

    # ── Knowledge base / agents ─────────────────────────────────────
    embedding_model: str = "text-embedding-3-small"  # 1536-dim
    kb_local_path: str = "data/kb_local.json"        # gitignored local cache
    agent_model: str = "gpt-4o"                       # chat model for specialist agents

    @property
    def data_path(self) -> Path:
        """Absolute data directory (resolved relative to repo root)."""
        p = Path(self.data_dir)
        return p if p.is_absolute() else (REPO_ROOT / p).resolve()


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (the `settings` singleton below)."""
    return Settings()


# Module-level singleton — `create_product_app` (app/main.py) + the CLI both
# import `settings`.
settings = get_settings()
