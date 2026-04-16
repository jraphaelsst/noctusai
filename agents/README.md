# NoctusAI Seed Agents

Two agents that protect and evolve the seed infrastructure.

## Agents

| Agent | Purpose | Command | AI |
|-------|---------|---------|-----|
| **Guardian** | Validate compliance, block drift | `python -m agents.guardian` | Hard checks (deterministic) + advisory (GPT-4o) |
| **Scientist** | Discover improvements, propose changes | `python -m agents.scientist` | File analyzers + AI brain (GPT-4o) |

Each agent has its own `README.md` with full documentation:
- [`agents/guardian/README.md`](guardian/README.md)
- [`agents/scientist/README.md`](scientist/README.md)

## Setup

```bash
pip install -r agents/requirements.txt
```

Required in root `.env`:
```
OPENAI_API_KEY=sk-...
```

Without the key, both agents still work — Guardian runs hard checks only, Scientist runs file analyzers only. AI features are additive, not required.

## Architecture

```
agents/
  shared/              Utilities used by both agents
    config.py          Repo paths, product discovery
    models.py          OpenAI API wrapper (ask_ai, is_ai_available)
    repo.py            File reading, import extraction, test runner
  guardian/            Seed Guardian — stability agent
    README.md          Full documentation (required)
    checks/            Modular validation checks
    main.py            CLI entry point
  scientist/           Seed Scientist — innovation agent
    README.md          Full documentation (required)
    analyzers/         Modular analysis modules
    ai_brain.py        AI reasoning over findings
    proposer.py        Proposal generation + deduplication
    proposals/         Generated proposals (markdown)
```

## Rules

- **Every agent must have a README.md.** The README is the agent's documentation. It must explain: what the agent does, how to run it, what checks/analyzers it has, and how its output works.
- **READMEs must stay in sync.** When an agent's behavior changes (new check, new analyzer, new CLI flag), update its README in the same commit. Stale docs are worse than no docs.
- **New agents follow the same pattern.** `agents/<name>/README.md`, `agents/<name>/main.py`, `agents/<name>/__main__.py`, `agents/<name>/__init__.py`.
