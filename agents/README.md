# NoctusAI Seed Agents

Two agents orchestrated in a pipeline that protects and evolves the platform.

## Single Command

```bash
python -m agents              # Full pipeline: Guardian → Scientist
```

That's it. One command runs everything:

1. **Guardian** validates platform compliance (pass/fail)
2. If Guardian **passes** → **Scientist** discovers improvements
3. If Guardian **fails** → Scientist is **skipped** (fix the foundation first)

## Orchestration

```
python -m agents
    │
    ├── GUARDIAN (is the platform healthy?)
    │     ├── Hard checks: seed compliance, path references
    │     ├── Score: 0-100 per product
    │     └── Result: PASS (100) or FAIL (<100)
    │
    ├── if FAIL → stop. Fix issues. Re-run.
    │
    └── if PASS → SCIENTIST (how can we improve?)
          ├── File analyzers: patterns, deps, structure, tests
          ├── AI brain: semantic analysis via GPT-4o
          └── Proposals saved to agents/scientist/proposals/
```

Guardian gates the Scientist. No point discovering improvements if the foundation is broken.

## Commands

```bash
python -m agents                    # Full pipeline (recommended)
python -m agents --advisory         # Full pipeline + Guardian AI advisory
python -m agents --guardian         # Guardian only
python -m agents --scientist        # Scientist only (skip Guardian gate)
```

## Individual Agent Docs

Each agent has its own README with detailed documentation:
- [`agents/guardian/README.md`](guardian/README.md) — checks, scoring, AI advisory
- [`agents/scientist/README.md`](scientist/README.md) — analyzers, proposals, dedup, AI brain

## Setup

```bash
pip install -r agents/requirements.txt
```

Required in root `.env`:
```
OPENAI_API_KEY=sk-...
```

Without the key, both agents work — Guardian runs hard checks, Scientist runs file analyzers. AI features are additive.

## Architecture

```
agents/
  __main__.py          Orchestration — Guardian → Scientist pipeline
  shared/              Shared utilities
    config.py          Repo paths, product discovery
    models.py          OpenAI API wrapper
    repo.py            File reading, imports, test runner
  guardian/             Stability agent
    README.md          Documentation (required, synced)
    main.py            Standalone entry point
    checks/            Modular validation checks
  scientist/           Innovation agent
    README.md          Documentation (required, synced)
    main.py            Standalone entry point
    analyzers/         Modular analysis modules
    ai_brain.py        AI reasoning over findings
    proposer.py        Proposal generation + deduplication
    proposals/         Generated proposals
```

## Rules

- **Every agent must have a README.md** — synced with behavior in the same commit.
- **Single run, full analysis.** Each agent completes its entire workflow in one invocation. No multi-step manual runs.
- **Proposals are deduplicated.** Running agents multiple times produces the same proposal count (unless the codebase changed).
- **Guardian gates Scientist.** Fix compliance before seeking improvements.
