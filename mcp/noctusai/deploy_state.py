"""Deploy-local manifest (D3) — the canonical list of files that are filled
in-place on the VPS and MUST be gitignored + survive every `git pull`.

Lifted 2026-05-22 from the transient `projects/.../deploy/STATE.json` into a
durable code constant next to its only two consumers, so it can never be lost
to a project-folder archive (the prior silent-skip risk):
  • `noctus.dev.predeploy_check` (`deploy_local_gitignored` check) ENFORCES it —
    each pattern must be NOT tracked ∧ git-ignored, else the deploy gate blocks.
  • `noctus.dev.deploy_pull` (C1 backup) reads it to know which files to tar
    before any HEAD move on production.

The human-facing rule + rationale lives in prose at
`KB § GUIDES/production-deploy.md § 2a` (nets P4 / D3) — this file is just the
DATA. Patterns are **gitignore-style and location-independent** (they mirror
the `**/tunnel/...` rules in `.gitignore`), so they keep working wherever the
deploy artifacts physically live (today a project folder; a future durable
`deploy/` home tomorrow).
"""
from __future__ import annotations

# Each entry: a gitignore-style pattern + why it is deploy-local. The pattern
# must (a) match a `.gitignore` rule and (b) match nothing git-tracked.
DEPLOY_LOCAL_FILES: list[dict[str, str]] = [
    {
        "pattern": "**/tunnel/config.yml",
        "reason": (
            "cloudflared named-tunnel config — holds the live <TUNNEL_ID> + "
            "credentials-file path; rendered from config.yml.template on the box."
        ),
    },
    {
        "pattern": ".env",
        "reason": "root runtime secrets (Supabase keys, LLM keys) — deploy-local, never tracked.",
    },
    {
        "pattern": "**/tunnel/*.json",
        "reason": (
            "cloudflared tunnel credentials JSON (<TUNNEL_ID>.json) — generated "
            "by `cloudflared tunnel create`, chmod 600, never committed."
        ),
    },
]

# Invariants this manifest asserts (documented here; enforced by predeploy_check
# and honored by deploy_pull's safe-git allowlist).
INVARIANTS: list[str] = [
    "Every pattern is git-ignored (git check-ignore HIT) AND matches nothing tracked.",
    "No deploy GUIDE/runbook/script frames `git reset --hard origin` or "
    "`git checkout -- <deploy-local>` as a sync step (the destructive-command ban).",
]

__all__ = ["DEPLOY_LOCAL_FILES", "INVARIANTS"]
