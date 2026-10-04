# Agent Packages — CONTRACT (v1, 2026-10-03)

> The single shape every slice builds to. Builds ON Agent Studio (`../agent-studio-isaia/CONTRACT.md`,
> referenced as **Studio §X**) and changes nothing about Julia or IsaIA. A slice that needs to deviate
> STOPS and reports — it never "aligns at integration". Project plan: `PROJECT.md` (same folder).

**What this is.** One agent, two surfaces, zero drift. An agent **package** is authored in git exactly the
way IsaIA is authored (sections · skills · knowledge · evals). ONE build turns it into:
1. **Claude Code files** a consumer repo commits (`.claude/agents/<key>.md` + `agents/<key>/`) — the
   **primary** surface (runs on the owner's Claude plan, no per-token cost);
2. a **Studio bundle** (`noctus.agent-bundle/v1`, Studio §F) imported into Agent Studio — the **secondary**
   surface (chat in the agents product, evals, versions, inspector).

Consumer repos then keep the Studio copy seeing what a Claude Code session sees — project docs, source,
decision board, learnings — by syncing on **every push**.

First packages: `mobile-dev` (en, general mobile-dev advisor) and `nos-no-limiar` (pt-BR, product guardian
for the Nós no Limiar app). First consumer: `jraphaelsst/limiar-app`.

---

## §A · Decisions (binding — owner decisions of 2026-10-03, recorded on the Decision Board)

| # | Decision | Why |
|---|---|---|
| A1 | **Git is the source of truth for packages**, authored IsaIA-style under `products/agents/packages/<key>/`. **Amends Studio §A1** for `kind = dev-advisor` only: their content is safe to publish (no third-party corpus, no secrets). Runtime agents (IsaIA, Julia) keep Studio §A1 unchanged. | One source, two generated surfaces ⇒ they cannot drift. |
| A2 | **Claude Code is the primary surface; Studio is secondary.** Both are generated from the same package by the same build; neither is hand-edited. | Owner's plan makes Claude Code the cheap path; Studio adds UI, evals, remote chat. |
| A3 | **ONE compiler for both surfaces.** The Claude Code agent body is produced by Studio's `compile_prompt` (`app/studio/compiler.py`, a pure function over `CompileInput`) — never re-implemented. Surface differences are confined to a **surface adapter block** (§C2). | Studio §A4 "what you see is what runs", extended across surfaces. |
| A4 | **Consumers pin.** A consumer commits `agents.lock.json` (key, version, sha) and the materialized files; upgrading is an explicit commit made by `agent_pull`. | Reproducible, offline, reviewable. |
| A5 | **Sync runs on every push** (git `pre-push`) in BOTH directions that apply: noc pushes publish packages to Studio (§F); consumer pushes sync project context + learnings to Studio (§G, §H). A sync failure never blocks the push and is never silent: loud stderr + a `.agents-sync-pending` marker retried on the next push. | Owner chose push; offline pushes must still work. |
| A6 | **Studio's copy sees what Claude Code sees**: package content + the consumer's project docs, source snapshot, decision-board snapshot and learnings, as knowledge collections (§G). | Owner requirement: the product agent works "as if it were the Claude Code session". |
| A7 | **Learnings are local-first**: appended to `agents/<key>/LEARNINGS.md` in the consumer in the same commit as the work; pushed to Studio (§H); promoted into the package in noc by an explicit tool (§H3) → new version → consumers pull. | Learning must never wait on network; promotion is reviewed. |
| A8 | **Machine auth = scoped project token** (`pk_…`, Studio's existing `agents.api_tokens`), kept in the developer's local env, never committed. Scopes (§I) grant only package read, project-knowledge write and learnings write (plus `studio:publish`, see §I — the noc pre-push publish leg only). | A git hook can't do SSO; today every route refuses non-user callers (403 `user_required`). |
| A9 | `agents.kind ∈ {runtime, dev-advisor}`; one registry, same versions/sections/skills/knowledge/evals/audit. Tabs that don't apply to dev-advisors (Clientes) hide. | Owner: "build them alike IsaIA". |
| A10 | Dev-advisors are **read-only**: Claude Code wrapper `tools: Read, Grep, Glob`; Studio toolset = Studio §E3 read-only tools. No write tools on either surface. | Owner: advisors, never editors. |

---

## §B · Package layout (`products/agents/packages/<key>/`) — the authoring source

```
package.yaml            identity + version + runtime + consumer surface settings (§B1)
sections/NN-<chave>.md  always-loaded prompt, frontmatter {chave, titulo, ordem, ativo?}   (= Studio secoes)
skills/<nome>/SKILL.md  frontmatter {nome, descricao, ordem}; body per IsaIA SKILL_SPEC   (= Studio skills)
skills/<nome>/references/*.md                                                             (= skill arquivos)
knowledge/<colecao>/_collection.yaml   {nome, tag, descricao, ordem}
knowledge/<colecao>/<slug>.md          frontmatter {titulo, tipo, resumo?, proveniencia{…}}  (= Studio conhecimento)
evals.json              Studio §F `evals[]` shape, verbatim
LEARNINGS.md            append-only table (§H1)
CHANGELOG.md            one entry per version
```
Rules: file names, frontmatter keys and JSON keys are fixed (pt keys as in Studio §F); **content language is
per package** (`package.yaml: idioma`). Sections must be **surface-neutral**: they say "abra a skill X" /
"consulte o conhecimento Y", never a tool name or a file path (§C2 supplies those per surface).

### B1 · `package.yaml`
```yaml
formato: noctus.agent-package/v1
key: nos-no-limiar               # kebab, = folder name, = Studio agents.key
nome: Nós no Limiar — guardião
descricao: "<≤ 600 chars, 3rd person: what + when; becomes the Claude Code `description` and Studio descricao>"
kind: dev-advisor
idioma: pt-BR                    # content language
versao: 0.2.0                    # semver; bumped by the author; CHANGELOG entry required
owners: [joao, monica]
runtime: {model: claude-sonnet-5, effort: medium, max_turns: 30, tool_policy: {web_search: false, knowledge: true}}
claude_code: {tools: [Read, Grep, Glob]}     # A10 — the build refuses any write-capable tool for dev-advisor
consumers: [jraphaelsst/limiar-app]          # informational; enables project-context collections (§G)
```

---

## §C · Build (`noctus.dev.agent_package_build key= [--check]`)

C1. Validates the package (frontmatter, unique `chave`/`nome`/slugs, evals schema, A10), then builds the
Studio bundle in memory (Studio §F shape + §C4 additions) and calls `compile_prompt` on it.

C2. **Surface adapter block** — the ONLY surface-specific text, appended by the build after the compiled prompt:
- Claude Code: "Skills: `agents/<key>/skills/<nome>/SKILL.md`; references beside it. Conhecimento:
  `agents/<key>/knowledge/<colecao>/<slug>.md`. Aprendizados: `agents/<key>/LEARNINGS.md` (newest rows win).
  Project context = the repository itself." (rendered in the package language)
- Studio: nothing extra — Studio §E3 tools already render in its compiled `_tools_block`.

C3. Outputs under `products/agents/packages/<key>/dist/` (gitignored by the root `dist/` rule, never committed):
- `dist/bundle.json` — Studio import body;
- `dist/claude/` — `.claude/agents/<key>.md` (frontmatter `name`, `description`, `tools`; body =
  compiled prompt + adapter) and `agents/<key>/{PACKAGE.json, skills/, knowledge/, LEARNINGS.md}`;
- `PACKAGE.json` = `{key, versao, sha, compiled_hash, built_at}`; `sha` = sha256 over the package tree
  (sorted paths + contents), `compiled_hash` = `prompt_hash` of the compiled text.

C4. Bundle additions (Studio importer must accept them; strict validation stays): `agente.kind`,
`versao.versao_semver`, `versao.package_sha`, and top-level `claude: [{caminho, conteudo}]` = the `dist/claude`
tree, stored at import (amended 2026-10-03 by BE-API: LEARNINGS.md/PACKAGE.json are not derivable server-side).
A dev-advisor import must carry semver + sha; a published semver is never re-imported (409 `semver_published`);
an existing agent's kind never flips (409 `kind_change_refused`).

C5. `--check` mode: build + compare against the committed consumer files (used by consumer CI to detect a
hand-edited materialized file → fail with the diff).

---

## §D · Studio changes (agents product)

D1. Migration (number via `noctus.dev.next_migration_number`): `agents.kind text not null default 'runtime'
check (kind in ('runtime','dev-advisor'))`; `agent_versions.versao_semver text null`, `package_sha text null`;
tables `agent_learnings` (§H2) and `agent_project_sources` (§G3). RLS org-scoped like Studio §B.
D2. Importer accepts §C4 keys; for `dev-advisor` it sets `kind`, records semver + package_sha on the draft.
D3. UI: Studio list shows a `kind` badge; agent shell hides **Clientes** for dev-advisors; new tab
**Aprendizados** (§H2 review); **Conhecimento** groups project collections under "Projeto: <slug>" with
last-sync time and source sha.
D4. Publish for dev-advisors goes through the normal eval gate (Studio §A8). The noc push pipeline (§F)
imports + runs evals; it **publishes only if the gate passes** — otherwise it leaves the draft and reports.

---

## §E · Consumer layout (what `agent_pull` writes into a consumer repo)

```
agents.lock.json                     {"formato":"noctus.agents-lock/v1","agents":[{key,versao,sha}],"project":{§G1}}
.claude/agents/<key>.md              generated — header comment "GENERATED by agent_pull — do not edit"
agents/<key>/PACKAGE.json            generated
agents/<key>/skills/…                generated
agents/<key>/knowledge/…             generated
agents/<key>/LEARNINGS.md            consumer-owned, append-only (pull MERGES upstream rows, never overwrites local)
.githooks/pre-push                   installed by agent_pull --install-hook (calls §G + §H sync)
```
`noctus.dev.agent_pull key= versao= repo=<path>` fetches the published package via §I API (or, when run
inside noc, builds locally from `products/agents/packages/`), writes the files, updates the lock.
A consumer **never hand-edits** generated files; `--check` in CI enforces it.

---

## §F · noc → Studio (package publish on push)

noc `pre-push` (extend `scripts/hooks/`): if `products/agents/packages/**` changed in the pushed range →
`agent_package_build` → `POST /api/studio/agents/{key}/import` → `POST .../evals/runs` on the draft → if the
gate passes, `POST .../draft/publish`. Prod Studio is the only Studio (dev fleet dormant). Failure ⇒ A5 rules.

## §G · Consumer → Studio: project context

G1. `agents.lock.json.project` = `{slug, fontes: {docs: [globs], codigo: [globs], quadro: "<path to board snapshot json>"}, agentes: [keys]}`.
For limiar-app: `docs: ["docs/**/*.md","CLAUDE.md","README.md"]`, `codigo: ["src/**/*.ts","src/**/*.tsx","app.json","package.json"]`,
`quadro: "docs/design/decision-board.json"`.
G2. `noctus.dev.agent_context_sync repo=<path>` → `PUT /api/studio/agents/{key}/projects/{slug}/sources`
with `[{path, sha256, tipo: doc|codigo|quadro, conteudo}]` — full manifest each time; server upserts by
`(project, path)` keyed on `sha256` (unchanged ⇒ no revision), **deletes paths absent from the manifest**,
stores them as knowledge collection `projeto-<slug>` (tag `PRJ`) so Studio §E3 `kb_buscar`/`kb_ler` reach
them. Size cap 25 MB per call; files > 200 KB skipped with a listed warning.
G3. `agent_project_sources` = `(org_id, agent_id, project_slug, path, sha256, tipo, document_id, synced_at)`.
G4. Board snapshot: the Decision Board lives in a claude.ai artifact a git hook cannot read. The Claude Code
session that reads/answers the board writes `docs/design/decision-board.json` (open + decided items) and
commits it; the push then syncs it. "Live" = as of the last commit — stated in Studio's UI.

## §H · Learnings

H1. Row format (both surfaces): `| Data | Tipo | Aprendizado | Evidência | Status |`; tipo ∈ {pitfall|armadilha,
practice|prática, decision|decisão}; status ∈ {new|novo, absorbed|absorvido, promoted|promovido}. Row
identity = sha256 of (date, learning text).
H2. Consumer push → `POST /api/studio/agents/{key}/learnings` (new row ids only) → `agent_learnings`
`(id, org_id, agent_id, project_slug, row_sha, data, tipo, texto, evidencia, status, created_at, reviewed_by, reviewed_at)`.
Studio **Aprendizados** tab: list, filter by project, mark `aceito` / `descartado` with a note.
H3. `noctus.dev.agent_learnings_promote key=` (run in noc): pulls `aceito` rows → appends to the package's
`LEARNINGS.md` (status `promoted`) and prints which knowledge files they suggest editing; the author bumps
`versao` → push → §F publishes → consumers `agent_pull`.

## §I · API and auth (all JSON, flat errors as Studio §D)

| Route | Scope | |
|---|---|---|
| `GET /api/agent-packages/{key}/versions` | `packages:read` | published semvers + sha |
| `GET /api/agent-packages/{key}/{versao}` | `packages:read` | the `dist/claude/` tree as `{files:[{path, conteudo}], package}` |
| `PUT /api/studio/agents/{key}/projects/{slug}/sources` | `project-knowledge:write` | §G2 |
| `POST /api/studio/agents/{key}/learnings` | `learnings:write` | §H2 |
| `GET /api/studio/agents/{key}/learnings` | `learnings:read` / member | list (promote tool, UI) |
| `PATCH /api/studio/agents/{key}/learnings/{id}` | admin user | review |
| `GET /api/studio/agents/{key}/projects` | member | per-project sync info (UI) |
| `POST /api/studio/agents/{key}/import` | `studio:publish` / admin user | token: dev-advisor only (existing, or new with the bundle declaring it) |
| `POST /api/studio/agents/{key}/evals/runs`, `GET …/evals/runs`, `GET …/evals/runs/{id}` | `studio:publish` / admin (write) · member (read) | token: dev-advisor only |
| `POST /api/studio/agents/{key}/draft/publish` | `studio:publish` / admin user | token: dev-advisor only, must pass the eval gate; override → 403 `override_requires_user` |

Tokens: Studio's `agents.api_tokens.scopes` (already present since migration 007); scopes are `packages:read`,
`project-knowledge:write`, `learnings:write`, plus `learnings:read` (amended: needed by `agent_learnings_promote`).
Mint via `POST /api/settings/api-tokens {label, scopes, expires_at ≤ 90 days}` (owner/admin) — re-mint every 90 days.
**Amendment 2026-10-03 — `studio:publish`** (found by the HOOKS slice: import/eval/publish were user-only, so the
pre-push pipeline's token got 403 `user_required`). Used by the noc pre-push publish leg ONLY; never given to consumer
repos (they hold `packages:read`, `project-knowledge:write`, `learnings:*`). Accepted only on the five routes above and
only when the target agent is `kind='dev-advisor'`; Julia/IsaIA stay user-only (403 `user_required`). A token never
reaches the publish override (403 `override_requires_user`) — the eval gate always decides. Audit rows
(`agent_audit_log.actor`, `published_by`, `created_by`, run `started_by`) carry the token row id. Mint like any other scope.
Previously planned wording: a product-caller is accepted ONLY on
routes whose scope it holds (all other routes keep 403 `user_required`). Token lives in
`~/.config/noctus/agents.env` (`NOCTUS_AGENTS_TOKEN`, `NOCTUS_AGENTS_URL=https://agents.noctusai.com`).

## §J · Security invariants
1. No write tools for dev-advisors on either surface (A10); the build refuses otherwise.
2. Project sync ships only the globs in the lock; `.env*`, keys, `node_modules`, binaries are hard-excluded
   and a secret scan (reuse `knowledge_bundle_export`'s scanner) aborts the sync on a hit.
3. Learnings/sources are org-scoped; a token sees only its own org and its granted scopes.
4. Auth tests assert strict `== 401/403/404` (CLAUDE.md §1).

## §K · Slices (file-disjoint) — see PROJECT.md for waves
| Slice | Owns |
|---|---|
| **PKG-BUILD** (engineer) | `mcp/noctusai/tools/noctus/dev/agent_package*.py` (build, pull, context_sync, learnings_promote) + tests |
| **BE-API** (engineer) | `products/agents/backend/` migration + importer additions + §I routes + scopes + tests |
| **FE-STUDIO** (engineer) | `products/agents/frontend/src/pages/studio/**` kind badge, Aprendizados tab, project collections |
| **HOOKS** (engineer) | `scripts/hooks/` noc pre-push §F + consumer hook template |
| **CONTENT** (orchestrator) | `products/agents/packages/{mobile-dev,nos-no-limiar}/` |

## §L · Deliberately later
Embedding search (Studio §K) · auto-promotion of learnings · write tools for advisors · Julia/IsaIA as packages.
