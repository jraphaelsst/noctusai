# NoctusAI Scripts

> **Rule: new automation defaults to an MCP tool, not a script here.**
> A new automation capability is agent-exposable → it belongs in the
> `noctus.dev.*` toolkit (`mcp/noctusai/`) with a `cli.py` flag + a
> colocated test, NOT a `scripts/*.sh|*.py` one-off. Full rule + the
> keeper-parsed classification manifest: `KB § PATTERNS/mcp-first-scripts.md`.
> Enforced by `check_new_script_lacks_mcp_analog` (adding a top-level
> `scripts/*.{sh,py}` without a manifest row is a keeper warning).

## Quick Start

```bash
bash scripts/setup.sh        # one-time: hooks + venv + backend/frontend deps
```

## What lives here (8 structural carve-outs only)

Everything absorbable was ported into the MCP toolkit on 2026-05-18
(`scripts-mcp-absorption`). Only scripts where the MCP runtime is
**structurally unavailable** remain — each has a `[carve:*]` row in the
manifest + an `accept-with-rationale` entry:

### `[carve:hook]` — git invokes it as a shell process directly

- **`pre-commit`** — thin dispatcher. Each step's *logic* lives in the
  toolkit; the hook just calls `python mcp/noctusai/cli.py --<flag>`
  (seed→template sync, KB counts, version stamp, ledger render, KB-sync
  verify, propagation drift, phase-state, outline-ability). Symlinked
  into `.git/hooks/` by `install-hooks.sh`.

### `[carve:bootstrap]` — runs before the venv the MCP lives in exists

- **`setup.sh`** — one-command repo setup (hooks + venv + deps).
- **`first-time-setup.sh`** — pre-venv repo bootstrap.
- **`install-hooks.sh`** — symlink `scripts/pre-commit` → `.git/hooks/`.
- **`bootstrap-worktree.sh`** — hydrate a `git worktree` (pre-venv).
- **`bootstrap-seed-workspace.sh`** — hydrate a sibling seed-workspace.
- **`build-init-local-db.sh`** — regenerate `init-local-db/` SQL.

### `[carve:docker]` — pure `docker build` plumbing, no extractable logic

- **`build-base-images.sh`** — build the shared `noctus-seed-*-base`
  images thin per-product Dockerfiles inherit via `FROM`.

Non-script entries: `codemods/` (AST codemod library), `init-local-db/`
(SQL data), `*.log`, this file — out of the rule's scope by construction.

## Absorbed → where it went

The former `scripts/{mole,verify-kb-sync,update-kb-counts,archive-clean,
disk-usage-monitor,check-framework-deps,cleanup-stale-worktrees,
merge-debt-monitor,render-project-history,backfill-project-history,
gen-promotions-index,sync-seed-template,stamp-seed-version,
propagate-composes,propagate-dockerfiles,smoke-fleet}` are now
`noctus.dev.*` MCP tools, each with a `cli.py` flag:

```bash
python mcp/noctusai/cli.py --help        # full flag list
python mcp/noctusai/cli.py --mole scan   # e.g. former scripts/mole.sh scan
```

Durable landing map: `KB § PATTERNS/mcp-first-scripts.md` §3.
