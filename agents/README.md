# NoctusAI Agents

AI-powered agents that maintain and evolve the platform. Each agent has a specific purpose and its own directory under `agents/`.

## Current Agents

| Agent | Purpose | Command |
|-------|---------|---------|
| **Keeper** | Fixer + improver — validates, heals, discovers | `python -m agents.keeper` |

## Quick Start

```bash
python -m agents              # Runs the Keeper (full pipeline)
python -m agents.keeper --heal # Fix loop until clean
```

See [`agents/keeper/README.md`](keeper/README.md) for full documentation.

## Adding Future Agents

```
agents/
  proposals/           Shared — all agents write proposals here
  shared/              Shared — config, models, repo utilities
  keeper/              Agent: fixer + improver
  <future-agent>/      Each agent gets its own directory
```

Each agent follows the same structure:

```
agents/<agent-name>/
  __init__.py
  __main__.py          # python -m agents.<name>
  main.py              # Core logic
  README.md            # Required, synced with behavior
```

Proposals go to `agents/proposals/` — one folder, all agents. When a future agent generates proposals, they land in the same place.

## Rules

- **Every agent has a README.md** — synced in the same commit as behavior changes.
- **Single run, full analysis.** Each agent completes its workflow in one invocation.
- **Deterministic first, AI second.** File analysis runs before AI. AI is additive, not required.
- **`OPENAI_API_KEY` in root `.env`** enables AI features. Without it, agents still work.

## Setup

```bash
pip install -r agents/requirements.txt
```
