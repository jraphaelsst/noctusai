# Seed Scientist

Discovers improvements and generates proposals for the NoctusAI platform.

## How it works

```
File analyzers (fast, free)  →  findings  →  AI brain (GPT-4o)  →  proposals
```

1. **File analyzers** scan the codebase for patterns, dependency issues, structural gaps, and test coverage
2. **AI brain** reasons over the combined findings — identifies semantic duplicates, prioritizes by impact, generates concrete fix proposals
3. **Proposals** are saved as markdown files in `agents/scientist/proposals/`

## Usage

```bash
python -m agents.scientist                    # Full analysis (file + AI)
python -m agents.scientist --analyze patterns # Pattern analysis only
python -m agents.scientist --analyze deps     # Dependency audit only
python -m agents.scientist --analyze structure # Structure analysis only
python -m agents.scientist --analyze tests    # Test coverage only
python -m agents.scientist --proposals        # List pending proposals
```

## Analyzers

| Analyzer | What it checks |
|----------|---------------|
| `pattern_finder` | Duplicated functions across products, inline hooks, similar service methods |
| `dependency_audit` | Python/frontend version mismatches, missing seed package references |
| `structure_analyzer` | Expected file structure, code metrics per product |
| `test_coverage` | Router/service/integration/E2E/auth-boundary test gaps |

## Proposal lifecycle

1. Scientist runs → generates proposals in `proposals/`
2. Human reviews → accepts, rejects, or defers each proposal
3. Accepted proposals get implemented
4. Rejected proposals stay as records (with reason)

## Deduplication

Proposals are **deduplicated by key entity**. If a proposal about `criar_meta` already exists, running the Scientist again will NOT create a duplicate — regardless of whether the title says "Extract", "Centralize", or "Consolidate". The proposer extracts the key entity (function name, package name) and checks existing files.

This means:
- Run the Scientist as often as you want — no duplicate spam
- New proposals only appear when NEW issues are discovered
- The proposal count reflects UNIQUE improvements, not run count

## AI brain

Requires `OPENAI_API_KEY` in root `.env`. Uses GPT-4o for:
- Semantic duplication detection (same logic, different names)
- Cross-product reasoning (shared patterns)
- Prioritized proposals with concrete steps
- Deep analysis of whether "same-named" functions are truly duplicates

Without the API key, only file analyzers run (still useful, just less intelligent).
