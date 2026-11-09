# DB-source agent mirror — the Studio is the source, the repo file is its export

> **Rule.** A dev agent whose definition lives in Agents Studio (`agents.fonte = 'db'`, kind `dev-advisor` | `dev-executor`) is edited ONLY in the Studio. Its `.claude/agents/<key>.md` + `agents/<key>/` in git are a GENERATED mirror: rendered at publish, written into the repo by `noctus.dev.agent_export`, never edited by hand. Two legs hold it: keeper `check_db_agent_mirror_integrity` (offline, pre-commit; WARN-only shadow since 2026-11-09, decision D25) and the pre-push `--agent-mirror-check` (online, never blocks).

Born 2026-11-08/09 with media-analyst (owner: the DB is the source of truth; the `.md` mirrors it with a gated sync, caches refreshed on update, and drift detection). Contract: `products/agents/projects/agent-packages/CONTRACT.md` A11 + §M1–M9.

---

## 1 · The flow

1. **Edit** in the Studio (UI or `noctus.agents.content`): sections, texts, skills, evals, and `superficie_claude` (`tools`, `model`, `owns_kb`).
2. **Publish** (a human act). After every gate passes, the publish route renders the mirror tree (`app/studio/espelho.py`, using the SAME renderer as the git package build, `app/studio/claude_surface.py`) and stores it on the version. A render failure refuses the publish (`espelho_falhou`). A published DB-source version therefore always has its mirror.
3. **Export**: `noctus.dev.agent_export key=<key>` (dry-run) → `confirm=True`. The tool fetches `GET /api/agent-packages/{key}/latest` and verifies it: `fonte == db`; the body hashes to `studio.compiled_hash`; paths stay inside `.claude/agents/<key>.md` + `agents/<key>/`. It then writes the files, deletes stale skill files, and refreshes the agent-context cache for that agent IN THE SAME CALL (cache == `.md` == last export).
4. **Commit** the mirror on a self-branch.

The mirror is never an input (§M6): nothing reads it back into the DB.

## 2 · Drift detection

| Drift | Caught by | When |
|---|---|---|
| body edited by hand | `check_db_agent_mirror_integrity`: body hash ≠ `studio.compiled_hash` | pre-commit (any staged `.claude/agents/*.md` or `agents/**`) |
| `.md` exported, `PACKAGE.json` not (partial) / from two versions (mixed) | same keeper: `PACKAGE.json` missing or `version_id` differs | pre-commit |
| a newer Studio publish not yet exported | `cli.py --agent-mirror-check` → loud stderr + `.agents-mirror-pending` | pre-push, never blocks |
| no token / offline | the same check reports `unverified`, NEVER "current" | pre-push |

The pending marker is separate from `.agents-sync-pending` on purpose: the package publish leg rewrites that one on every run, which would silently erase a stale-mirror entry. `agent_export confirm=True` clears the agent's entry.

## 3 · How to apply

- Changing a DB-source agent: Studio → publish → export → commit. If the keeper says "edited by hand", revert the file and export again.
- A new DB-source agent: create it with `kind`, `fonte='db'` and `superficie_claude` set (`criar_agente` / `configurar_agente`). Publishing without `superficie_claude.tools` is refused.
- Knowledge collections are not mirrored in v1. They are listed in `PACKAGE.json.nao_espelhado`, never a silent gap.

## Composes with

`KB § PATTERNS/backend/structure-constructor-parity.md` (born in the same build: `kind`/`fonte`/`superficie_claude` reach every constructor) · `KB § PATTERNS/common/agent-context-architecture.md` (the cache the export refreshes) · `KB § PATTERNS/common/gate-methodology-sync.md` (build triad, shadow first).
