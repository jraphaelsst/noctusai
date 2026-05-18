# Setup Guide

## First clone

```bash
git clone <repo>
cd noctusai
bash scripts/setup.sh
```

`setup.sh`:
- Creates a single root venv at `venv/`.
- Installs root `requirements.txt`.
- Installs `seed/lib/backend` + `seed/framework/backend` in editable mode.
- Installs git hooks.
- Runs any one-time initialization.

Run **once** after clone. Re-run if `requirements.txt` changes.

## Running the platform

```bash
bash start.sh
```

Starts all backends (Core, ERP, PF, Therapy, Seed, Daily Life, Mailing) and frontends in the background. Each on its dedicated port (see `02-LANDSCAPE.md`).

## Running one product manually

Backend:
```bash
venv/bin/uvicorn app.main:app --reload --port 8001 --app-dir products/erp-imobiliario/backend
```

Frontend:
```bash
cd products/erp-imobiliario/frontend && npm run dev
```

## Tests

```bash
cd <product>/backend && pytest
```

See `PATTERNS/testing.md` for the three-layer test discipline.

## Git hooks

`scripts/setup.sh` installs a single `pre-commit` hook (symlinked to `scripts/hooks/pre-commit`). It runs three checks in order, staging any auto-generated updates into the same commit:

1. **Seed → template sync** — if any `products/seed/` file is staged, runs `noctus.dev.sync_seed_template` and stages `templates/product-seed/`.
2. **KB count refresh** — runs `noctus.dev.kb_sync` to regenerate auto-derived count blocks in KB docs, stages any updated files.
3. **KB sync verification** — runs `noctus.dev.kb_sync`; **aborts the commit** if any `CLAUDE.md` pointer is broken or a KB doc is missing from `KNOWLEDGE-BASE/INDEX.md`.

No post-commit amend — everything lands in one commit. Skip (not recommended): `git commit --no-verify`.

## Environment file

Create `.env` at repo root. Template at `.env.example` (if present) lists required keys. See `PATTERNS/environment.md` for the full list of vars and the VITE/non-VITE security rule.

---

See also:
- `scripts/README.md` — full script catalog
- `PATTERNS/environment.md` — env var conventions
