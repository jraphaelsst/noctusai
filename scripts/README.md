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
1. Installs git hooks (post-commit: seed auto-sync)
2. Creates Python 3.11 venv + installs all backend requirements
3. Installs `noctusai_shared` in dev mode (`pip install -e shared/backend`)
4. Runs `npm install` in every product frontend
5. Verifies `.env` exists

```bash
bash scripts/setup.sh
```

---

### `sync-seed-template.sh` — Sync seed product → template

**When:** Runs automatically via post-commit hook. Can also be run manually.

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

### `start.sh` (repo root) — Start all services

**When:** After setup is complete. Starts all backends + frontends.

```bash
bash start.sh
```

Starts: Core (8000), ERP (8001), PF (8002), Therapy (8003) backends + all frontends.

---

## Git Hooks

### `post-commit` — Seed auto-sync

**Trigger:** Any commit that changes files in `products/seed/`.

**Behavior:**
1. Detects if `products/seed/` was modified in the commit
2. Runs `sync-seed-template.sh` (backup → copy → placeholders → validate)
3. Stages updated template files
4. Amends the commit to include template changes

The template is **always** in sync with the seed — one commit, both updated.

**Lockfile:** `.seed-syncing` prevents infinite loop (commit → hook → amend → hook). Gitignored.
