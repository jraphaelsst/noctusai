# dev_team — MASTER-PROMPT (for AI agents touching this package)

> **Audience.** A future Claude Code session (or any AI agent) that needs to extend, debug, or invoke the agno multi-agent dev team in this repo.

## What this package is

`dev_team/` is the agno multi-agent dev team for NoctusAI. 11 specialists + 3 sub-teams + hybrid memory + provider-agnostic YAML config + MCP exposure (`noctus.team.*`). Lives at repo root as a sibling to `mcp/`.

Built from the design at `projects/agno-dev-team-rollout/design-reference.md` (the 469-line sibling spec preserved for posterity).

## Behavioral rules every dev_team agent inherits

The shared charter at `src/dev_team/charters/shared.md` reproduces the universal rules from `CLAUDE.md §1` (resynced 2026-11-05). Every specialist also loads a role-specific charter in `src/dev_team/charters/<role>.md`.

Key rules every agent follows:
- **Seed first** — products inherit via `create_product_app`/`createProductApp`; named-seam discipline.
- **No quick fixes / no workarounds / no monkey-patching of our own code, in production OR tests.**
- **No silent errors.**
- **AST-first edits** — `libcst` (Python) / `ts-morph` (TypeScript). Never regex on source.
- **Recurrence rule** — N=2 triage, N=3+ formalize.
- **Replication-to-seed-symmetry** — "per-product X" / "mount across N" = slip.
- **Eight-way sync** — CLAUDE.md, MEMORY.md, agent files, KB, CONTEXTUALIZE.md, skills, commands and caches move together (`KB § PATTERNS/common/eight-way-sync.md`).
- **Landing flow** — code reaches `dev` only through the CI merge queue (`KB § PATTERNS/devops/merge-queue.md`).

## Charter source of truth

Role charters are derived from the refined Claude-side specialists, `.claude/agents/*.md` (lean L1 indexes) and the craft-canon docs they own (refinement of 2026-11-05). Each charter ends with a `Craft canon` section naming the profession's frameworks and the `read_kb(...)` canon docs for depth. When a Claude agent or its canon changes, update the matching charter; the KB wins over the charter on any disagreement. Charters are content only: the agno team is not used for development yet.

Roles that exist only on the Claude side (no agno role) and the agno charter that carries their lens:

| Claude-only role | Lens carried by |
|---|---|
| `integrations-engineer` | `backend_engineer` |
| `ai-engineer` | `backend_engineer` (with `security_engineer` for prompt/agent risk) |
| `tooling-engineer` | `devops_engineer` |
| `legal-advisor` | `product_manager` (legal/consumer lens, escalates to an OAB lawyer) |
| `accountant` | `product_manager` (unit-economics/finance lens, escalates to a CRC contador) |
| `ops-steward` | `leader` and `devops_engineer` |
| `reverse-engineer` | `solution_architect` |
| `skill-scout` | `technical_writer` (vendored skills: `KB § PATTERNS/common/vendored-skills.md`) |
| `agents-security` | `security_engineer` |

Adding any of these as agno roles is future wiring and an owner decision, not part of this content pass.

## Add a new agent

1. Create `src/dev_team/agents/<role>.py` with a `build_<role>(config) -> Agent` factory.
2. Create `src/dev_team/charters/<role>.md` (~1-2K tokens — mission/responsibilities/outputs/handoffs/tools).
3. Add the role to `src/dev_team/tools/allowlists.py` (which tools the agent may call).
4. Add a model assignment to `src/dev_team/configs/default.yaml`.
5. Wire into `src/dev_team/team.py::build_team` (and any sub-team if relevant).
6. Add a smoke test in `tests/test_team_assembly.py`.

## Add a new tool

1. Create `src/dev_team/tools/<tool>.py` with a `build_<tool>_tool() -> Callable | dict` factory.
2. Decide allowlist — add to `src/dev_team/tools/allowlists.py::TOOL_ALLOWLIST`.
3. Add a test in `tests/test_tool_allowlists.py`.
4. **Prefer wrapping existing `noctus.dev.*` MCP tools over re-implementing.**

## Switch model providers

Edit `src/dev_team/configs/default.yaml` (or create `<provider>-eval.yaml`). The agno provider routing handles the actual swap — we just change the YAML.

## Run the team

```bash
# CLI
python -m dev_team run "<task>"

# MCP (from a Claude Code session with mcp/noctusai loaded)
# The user / Claude says "use the agno team here for this: <task>"
# Claude calls noctus.team.run(task="<task>")
```

## Don't

- Don't import from `automations/` (that sibling repo will be deleted).
- Don't bypass the charter loader — every agent's instructions come from `src/dev_team/charters/`.
- Don't write test code that monkey-patches our own modules. External integration mocks (LLM API) are fine; internal-monkey-patching is not.
- Don't add a 4th MCP namespace segment (`noctus.team.<sub>.<action>`). Stay 3-segment per `KB § PATTERNS/mcp-tool-conventions.md § 1`.

## Pointers

- KB pattern (depth): `KB § PATTERNS/dev-team.md` (lands in B5 of agno-dev-team-rollout).
- Project root: `projects/agno-dev-team-rollout/`.
- Design reference: `projects/agno-dev-team-rollout/design-reference.md`.
- Sibling spec source (will be deleted): `~/Documents/repository/NoctusAI/automations/KNOWLEDGE-BASE/CONTEXT/07-DEV-TEAM.md`.
