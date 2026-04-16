# Seed Guardian

Validates seed compliance across all products. The immune system of the platform.

## How it works

Two layers — deterministic checks that block CI, and AI advisory that warns.

```
Hard checks (file analysis)  →  pass/fail score  →  blocks CI if fail
AI advisory (GPT-4o)         →  warnings only     →  never blocks
```

## Usage

```bash
python -m agents.guardian                          # Hard checks only (default)
python -m agents.guardian --advisory               # Hard + AI advisory
python -m agents.guardian --product mailing        # Single product
python -m agents.guardian --check seed_compliance  # Single hard check
python -m agents.guardian --json                   # JSON output for CI
```

Exit code 0 = all clear. Exit code 1 = hard issues found. Advisory findings never affect exit code.

## Hard checks (deterministic)

| Check | What it validates |
|-------|------------------|
| `seed_compliance` | `main.py` uses `create_product_app()`, `App.tsx` uses `createProductApp()`, no boilerplate routers (health/team/notificacoes), no manual Layout.tsx |
| `path_references` | All requirements.txt, tsconfig.json, tailwind.config.ts reference `seed/backend/lib` and `seed/frontend/lib` correctly |

### Scoring

Each product gets a score 0-100:
- Critical issue: -25 points
- High issue: -10 points
- Warning: -3 points

Platform score = average of all product scores.

## AI advisory (non-blocking)

Requires `OPENAI_API_KEY` in root `.env`. Uses GPT-4o to:

1. Read CLAUDE.md engineering rules
2. Read each product's key files (main.py, config.py, dependencies.py, App.tsx, vite.config.ts)
3. Validate code against rules
4. Report violations as advisories (never blocks)

The AI advisory automatically enforces new rules. Add a rule to CLAUDE.md → next Guardian run checks for it. No code changes to the Guardian needed.

Without the API key, only hard checks run (still fully functional).

## When to run

- **Every PR/commit**: hard checks only (`python -m agents.guardian`). Fast, free, deterministic.
- **Weekly/on-demand**: with advisory (`python -m agents.guardian --advisory`). Deeper, AI-powered, catches semantic violations.

## Difference from the Scientist

| | Guardian | Scientist |
|-|----------|-----------|
| Purpose | Validate compliance | Discover improvements |
| Output | Pass/fail score | Improvement proposals |
| Blocks CI | Yes (hard checks) | Never |
| AI role | Advisory (warns) | Brain (reasons + proposes) |
| Run frequency | Every commit | On-demand / weekly |
