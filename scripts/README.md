# NoctusAI Scripts

## Quick Start

After cloning the repo, run ONE command:

```bash
bash scripts/setup.sh
```

This installs everything: git hooks, Python venv, backend deps, frontend deps.

---

## Scripts

### `setup.sh` — First-time repo setup

**When:** Run once after cloning. Run again if hooks or deps get out of sync.

**What it does:**
1. Installs git hooks (pre-commit: seed→template sync + KB counts + KB sync verification)
2. Creates Python 3.11 venv + installs all backend requirements
3. Installs `noctusai_lib` in dev mode (`pip install -e seed/lib/backend`)
4. Runs `npm install` in every product frontend
5. Verifies `.env` exists

```bash
bash scripts/setup.sh
```

---

### `sync-seed-template.sh` — Sync seed product → template

**When:** Runs automatically via the pre-commit hook whenever a `products/seed/` file is staged. Can also be run manually.

**What it does:**
1. Backs up current `products/seed/` and `templates/product-seed/` to `.backup/`
2. Copies seed → template (excluding node_modules, __pycache__, .env, etc.)
3. Replaces product-specific values with `{{PLACEHOLDERS}}`
4. Validates all expected placeholders exist

```bash
bash scripts/sync-seed-template.sh          # normal run
bash scripts/sync-seed-template.sh --dry    # preview only
```

**Placeholder mapping:**

| Seed value | Template placeholder |
|------------|---------------------|
| `Seed Product` / `Seed` | `{{PRODUCT_NAME}}` |
| `seed-product` | `{{PRODUCT_SLUG}}` |
| `"seed"` / `'seed'` (schema) | `{{SCHEMA_NAME}}` |
| `8004` | `{{BACKEND_PORT}}` |
| `8100` | `{{FRONTEND_PORT}}` |
| `Sprout` (icon) | `{{PRODUCT_ICON}}` |

---

### `install-hooks.sh` — Install git hooks only

**When:** If you only need to reinstall hooks without the full setup.

```bash
bash scripts/install-hooks.sh
```

---

### `pre-commit` — KB count refresh + sync verification

**When:** Runs automatically on every `git commit`. Can also be invoked manually.

**What it does:**
1. Runs `update-kb-counts.py` — regenerates derived count blocks in KB docs (product inventory, schema table counts, MCP tool count) from the actual codebase.
2. Stages any doc that was updated so it lands in the same commit.
3. Runs `verify-kb-sync.sh` — fails the commit if any CLAUDE.md pointer is broken or any KB doc is missing from `KNOWLEDGE-BASE/INDEX.md`.

**Skip (not recommended):** `git commit --no-verify`.

```bash
bash scripts/pre-commit            # manual run (same as the hook)
```

---

### `update-kb-counts.py` — Regenerate KB derived facts

**When:** Invoked by the `pre-commit` hook; also standalone.

Replaces content between marker pairs in KB docs:

```markdown
<!-- kb-counts:start:inventory -->
...auto-updated table...
<!-- kb-counts:end:inventory -->
```

Implemented regions: `inventory`, `database`, `mcp_tools`, `agent_context_tools`.

```bash
python scripts/update-kb-counts.py            # apply updates
python scripts/update-kb-counts.py --check    # exit 1 if drift detected (CI-friendly)
```

---

### `verify-kb-sync.sh` — KB ↔ CLAUDE.md pointer sync

**When:** Invoked by the `pre-commit` hook; also standalone.

**What it checks:**
1. Every ``KNOWLEDGE-BASE/...md`` pointer in `CLAUDE.md` resolves to a real file.
2. Every KB doc is referenced in `KNOWLEDGE-BASE/INDEX.md`.

Also available as `python mcp/noctusai/cli.py --verify-kb-sync`.

```bash
bash scripts/verify-kb-sync.sh
```

---

### `start.sh` (repo root) — Start all services

**When:** After setup is complete. Starts all backends + frontends.

```bash
bash start.sh
```

Starts: Core (8000), ERP (8001), PF (8002), Therapy (8003) backends + all frontends.

---

## Git Hooks

### `pre-commit` — unified: seed sync + KB counts + KB sync verification

**Trigger:** Every `git commit`.

**Behavior (three ordered steps, all pre-commit — no amend):**

1. **Seed → template mirror.** If any `products/seed/` file is staged, runs `sync-seed-template.sh` and stages `templates/product-seed/` so both land in the same commit.
2. **KB count refresh.** Runs `update-kb-counts.py` — regenerates auto-derived count blocks in KB docs. Stages any updated docs.
3. **KB sync verification.** Runs `verify-kb-sync.sh` — aborts the commit if any `CLAUDE.md` pointer is broken.

The hook is a symlink to `scripts/pre-commit`, so any edit to that file takes effect immediately.

**Legacy:** an older `post-commit` hook used to amend the commit with template changes. That approach was replaced — the seed sync now runs pre-commit, stages the mirror, and the commit proceeds cleanly without amending. `install-hooks.sh` removes the legacy hook if present.

**Bypass (not recommended):** `git commit --no-verify`.
