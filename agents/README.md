# NoctusAI Seed Agents

Two AI-powered agents that protect and evolve the seed infrastructure.

## Agents

### Seed Guardian (Stability)

Monitors, validates, and ensures the seed and all products stay healthy. Detects seed compliance violations, structural code duplication, broken tests, and doc drift.

```bash
python -m agents.guardian                          # Full health check
python -m agents.guardian --product mailing        # Single product
python -m agents.guardian --check seed_compliance  # Single check
```

**Output:** Health score (0-100) per product + detailed issue report.

### Seed Lab (Innovation)

Experiments, discovers improvements, and proposes changes. Analyzes code patterns, audits dependencies, researches ecosystem trends, and builds prototypes in isolated branches.

```bash
python -m agents.lab                               # Full analysis
python -m agents.lab --analyze patterns            # Pattern analysis
python -m agents.lab --experiment proposal-001     # Test a proposal
```

**Output:** Improvement proposals in `agents/lab/proposals/`.

## Setup

```bash
pip install -r agents/requirements.txt
```

Required env vars in `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

## Architecture

- **AI Models:** Anthropic Claude API (primary) + OpenAI API (embeddings)
- **Shared utilities:** `agents/shared/` — config, model wrappers, repo analysis, reporting
- **Guardian checks:** `agents/guardian/checks/` — modular validation checks
- **Lab analyzers:** `agents/lab/analyzers/` — modular analysis modules

See `PLAN-SEED-AGENTS.md` at repo root for the full implementation plan.
