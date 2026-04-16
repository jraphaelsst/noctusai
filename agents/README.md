# NoctusAI Seed Agents

Two agents orchestrated in a pipeline that protects and evolves the platform.

## Two Modes

### Pipeline mode (assess)
```bash
python -m agents                    # Guardian → Scientist
```

### Heal mode (fix)
```bash
python -m agents --heal             # detect → fix → verify → repeat until clean
python -m agents --heal --product mailing  # heal a specific product
```

**Heal mode is the development loop.** After changing code, run `--heal`. The agents detect issues, auto-fix what's deterministic, create proposals for what needs human review, and re-run until the platform is clean. Like Claude Code's break-fix cycle — iterate until working.

## How it works

```
python -m agents --heal
    │
    ├── GUARDIAN — detect issues
    │     ├── Deterministic issue? → AUTO-FIX → re-run to verify
    │     ├── Non-deterministic?   → CREATE PROPOSAL for human review
    │     └── Repeat until clean (max 10 iterations)
    │
    └── if clean → SCIENTIST — discover improvements
          ├── File analyzers: patterns, deps, structure, tests
          ├── AI brain: reasoning via GPT-4o
          └── All findings → PROPOSALS (never auto-fix)
```

**Key rule:** Deterministic issues are auto-fixed. Non-deterministic issues become proposals. The Scientist never auto-fixes — it always proposes.

## Commands

```bash
python -m agents                            # Full pipeline (assess only)
python -m agents --heal                     # Heal: fix loop + scientist
python -m agents --heal --product mailing   # Heal a specific product
python -m agents --heal --advisory          # Heal + AI advisory (proposals)
python -m agents --guardian                 # Guardian only
python -m agents --scientist                # Scientist only
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
