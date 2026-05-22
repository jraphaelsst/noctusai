"""Supabase connector MCP settings — Management API auth config.

The Supabase Management API authenticates with a **Personal Access
Token** that has no external store (unlike `mcp/github`'s `gh` keyring),
so the token DOES live here — in the connector's own co-located `.env`
(`mcp/supabase/.env`, gitignored), independent of the product/root
`.env` ("every connector owns its own auth store",
`KB § INTEGRATIONS/vista.md § 1`; this is vista's / n8n's / hostinger's /
cloudflare's exact shape).

`project_ref` is read here too — almost every Management endpoint is
project-scoped (`/v1/projects/{ref}/database/query`, ...), so a default
project ref saves passing it on every call. Every project-scoped tool
ALSO accepts an explicit `project_ref` override arg (the arg wins over
this default); a tool that needs a ref but has neither surfaces a typed
never-faked 424 rather than building a malformed path. `project_ref` is
NOT a secret (it is the public project reference, e.g. `abcd...wxyz`).

Unlike vista/n8n there is no per-tenant `base_url` — Supabase's
Management API is a single public host — but `base_url` is kept off
`env_map` with a canonical default so tests can override it.
`timeout_seconds` is likewise kept off `env_map` so it keeps its
dataclass default (vista's exact rule — every `env_map` field is passed
on every build, `None` when unset).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings

from .api import DEFAULT_BASE_URL, normalize_base_url


@dataclass(frozen=True)
class SupabaseConnectorSettings(ConnectorSettings):
    """Frozen API config (a tool handler can't corrupt server state).

    - `access_token` — Supabase Personal Access Token (`Authorization:
      Bearer <token>`). Secret.
    - `project_ref`  — default project reference for project-scoped tools;
      overridable per-call. NOT a secret (the public project reference).
    - `base_url`     — API host; defaults to the canonical Supabase
      Management base. Off `env_map` (a single public API) but overridable
      in code for tests.
    - `timeout_seconds` — HTTP timeout; pure default (off `env_map`).
    """

    access_token: Optional[str] = None
    project_ref: Optional[str] = None
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 30.0

    @property
    def root(self) -> str:
        """The normalized API base (canonical default when unset)."""
        return normalize_base_url(self.base_url or "")

    @property
    def configured(self) -> bool:
        """True iff the access token is present. Reachability / auth
        validity is a separate runtime check
        (`supabase.diagnostics.connection_status`). `project_ref` is not
        part of configured-ness — `project.list` works without it; only
        project-scoped tools require it (they surface a typed error when
        it is missing and not passed)."""
        return bool(self.access_token)


# Env wins over the co-located `.env`; process-cached. `base_url` +
# `timeout_seconds` intentionally omitted from `env_map` so they keep
# their dataclass defaults (vista's exact rule — see module docstring).
get_settings = make_get_settings(
    SupabaseConnectorSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "access_token": "SUPABASE_ACCESS_TOKEN",
        "project_ref": "SUPABASE_PROJECT_REF",
    },
)


__all__ = ["SupabaseConnectorSettings", "get_settings"]
