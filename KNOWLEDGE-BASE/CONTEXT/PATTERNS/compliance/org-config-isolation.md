# Org-config isolation — configuration reaches an org only by explicit grant

**Rule (owner directive, 2026-10-26):** another org receiving one org's / one app's settings is unacceptable. Org- or
app-specific configuration is reachable only by orgs *explicitly granted* it — never by default. The default is
CLOSED; opening is a named, audited act.

## The leak this closes

`agents.agents.instanciavel` defaulted `TRUE` (049) and so did every store default, while `ensure_instancias` gave every
org an instance of every published `instanciavel` platform definition. A product-owned agent (julia → social-wiring,
monica-leads → monica) therefore reached every org. "Default open" was the root, not the individual agent.

## Enforcement (by construction, then backstopped)

| Layer | Mechanism |
|---|---|
| DB default | `instanciavel DEFAULT FALSE` (agents 050) |
| DB allow-list | `agents.definition_org_grants(definition_id, org_id, granted_by, created_at)` — RLS on, service-role only |
| DB CHECK | `agents_product_owned_not_instanciavel`: a platform definition with `owner_product` is never `instanciavel` |
| DB guard | `guard_agent_definition_scope` raises `definition_not_granted` for an instance of a closed definition without a grant |
| App | store defaults `False`; `plataforma._pode_instanciar` = open ∨ granted; Fake mirrors the guard + CHECK |
| Tool | `noctus.agents.content action=conceder` (`concessoes` lists) → `POST /api/studio/plataforma/agents/{key}/grants` |
| Probes | `agents.product_owned_definition_never_instanciavel`, `agents.instance_requires_grant` (`noctus.dev.verify_db_guards`) |
| Keepers | `check_org_owned_definition_not_instanciavel` (declarations in `products/*/ops/agents/**`, agent `package.yaml`); `check_new_org_table_rls` |

Backfill (050): grants are inserted from the existing instance rows **by `definition_agent_id`** (the real keying — an
instance points at its definition, not at a key) *before* any definition is closed, so no org loses an agent it has.

## The delta RLS gate — `check_new_org_table_rls`

Promoted from the advisory `check_table_has_rls`. A table created in a **new** migration with an `org_id` column must
enable RLS **and** either carry an org-scoped SELECT (or ALL) policy naming `org_id`/`current_org*`, or be explicitly
service-role-only (`REVOKE ALL ... FROM ... authenticated`). Existing tables are baselined, never re-failed (pre-commit
passes the staged *added* migrations; with no `--paths` it uses the migrations added vs `origin/dev`). Reviewed escape:
`-- noc-allow: org-table-rls — <reason>` in the file. The sweep of existing org settings surfaces (brand kits,
`platform_settings` vs org settings, SW org settings) is *not* done by this gate — product backends read through the
service role, so their isolation is code-only and is audited separately.

## Giving one org an agent

1. Create the definition with `instanciavel: false` (the default).
2. `noctus.agents.content action=conceder agent=<key> payload_path={"org_id": "<uuid>"}` (dry-run, then `confirm=True`).
3. The org's instance is created on first use. Never `instanciavel=true`, never hand SQL.

Related: `KB § PATTERNS/backend/tenancy-license-gate.md` · `KB § PATTERNS/backend/database-rls.md` · `KB § INTEGRATIONS/agents-org-specs.md`.
