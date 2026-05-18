"""GitHub connector MCP settings — per-tenant routing config.

Credentials are owned by the operator's `gh` CLI keyring (`gh auth`),
NOT this module — same "MCP owns its own config store" isolation the
other connectors follow (`KB § INTEGRATIONS/vista.md § 1`), minus the
secret (gh holds it). Only non-secret routing config lives here.

The dotenv + env-precedence machinery lives in `_kit.settings`; this
module just declares the frozen carrier + the env map. Per the
`make_get_settings` contract, every `env_map` field is passed to the
dataclass on every build (as `None` when the env/`.env` is unset), so
fields needing a real default (`gh_path`) are kept Optional and resolved
via a property — exactly how vista keeps `timeout_seconds` off `env_map`.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _kit.settings import ConnectorSettings, make_get_settings


@dataclass(frozen=True)
class GitHubConnectorSettings(ConnectorSettings):
    """Frozen per-tenant config (a tool handler can't corrupt server state).

    - `default_repo` — `OWNER/REPO`; `None` ⇒ `gh` infers it from the cwd
      git remote (the common case when run inside the repo).
    - `gh_path`      — override the `gh` binary location; `None` ⇒ `"gh"`
      resolved on `PATH`.
    - `timeout_seconds` — subprocess timeout; pure default (off `env_map`).
    """

    default_repo: Optional[str] = None
    gh_path: Optional[str] = None
    timeout_seconds: float = 20.0

    @property
    def effective_gh_path(self) -> str:
        """The `gh` binary to invoke — env/`.env` override or the default."""
        return self.gh_path or "gh"

    @property
    def configured(self) -> bool:
        """True when the `gh` binary is resolvable. Auth state is a
        separate runtime check (`github.diagnostics.connection_status`) —
        a resolvable binary that is not logged in is still 'configured'
        but not 'authenticated'."""
        return shutil.which(self.effective_gh_path) is not None


# Env wins over the co-located `.env`; process-cached. `timeout_seconds`
# intentionally omitted from `env_map` so it keeps its dataclass default
# (vista's exact rule — see module docstring).
get_settings = make_get_settings(
    GitHubConnectorSettings,
    dotenv_dir=Path(__file__).resolve().parent,
    env_map={
        "default_repo": "GITHUB_DEFAULT_REPO",
        "gh_path": "GITHUB_GH_PATH",
    },
)


__all__ = ["GitHubConnectorSettings", "get_settings"]
