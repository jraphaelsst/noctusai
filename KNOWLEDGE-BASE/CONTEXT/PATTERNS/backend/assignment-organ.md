# Assignment organ (seed-lib) — who owns a lead

> `noctusai_lib.domain.assignment` (backend) + `@noctusai/lib` `assignment/` (frontend). CRM vertical seed, roadmap
> `project-history/roadmaps/crm-cms-erp-vertical-seeds-2026-11.plan.md` § 2.1 row `assignment` (slice W1-4). Formalizes the
> N=3 copies of "who owns this lead" — social-wiring `julia_equipes_service` (teams, keep-last, cursor), erp-imobiliario
> `distribuicao` (mode switch + rule maps), and the igig/orbity owner fields — so the 4th is forbidden. SW and igig migrate to it
> in W3-S3 / W7-O, not here.

> **Plan correction (2026-11-11).** The plan names igig `distribuicao_router.py` as "the richest copy, lift base". It is not an
> assignment router: it is CONTENT-publication distribution (schedule a pauta on a channel). Nothing was lifted from it. The lift
> base is SW `julia_equipes_service` (richest assignment mechanics) + erp-imobiliario `distribuicao_service`. SW
> `julia_roteamento_router` is WhatsApp line routing and `leads/routers/corretores.py` is the import-alias dimension of a lead
> list; neither is assignment. igig's real copy of this problem (publication distribution) belongs to the CMS content-board
> slice, not here.

## 1. What it is

One org picks ONE strategy. Teams hold members. An assignment picks a member, and the pick is ONE transaction.

| Strategy | Picks | Reads |
|---|---|---|
| `round_robin` | the next member of the `auto` team whose cursor moved least recently | teams, cursors |
| `by_team` | the next member of the team named in the call, else the default team | `ctx.team_id`, `default_team_id` |
| `by_source` | the next member of the team a `source` rule maps `ctx.source` to, else the default team | `asg_rules` |
| `by_unit` | the same over `ctx.org_unit_id` (a `unit` rule, else a team stamped with the unit, else the default) | `asg_rules`, `asg_teams.org_unit_id` |
| `manual` | nobody (a human assigns) | — |
| `<custom>` | whatever the host hook returns, checked to be an ELIGIBLE member of a snapshot team | `strategy_hooks` |

`keep_last` (a setting, default on) runs first for every non-manual strategy: a returning subject goes back to its current owner
while that person is eligible. A member is eligible when `active` ∧ not inside an out-of-office window ∧ below `capacity` (max OPEN
subjects; NULL = unlimited) ∧ still an active member of the org. Round-robin walks the members in `position` order and skips the
unavailable ones; a cursor sitting on someone now unavailable still advances past them.

`by_unit` is the declared seam of the Filiais row (plan § 4): `org_unit_id` is a nullable uuid convention on teams, assignments and
events — no unit table lives in the seed. Promote it to an org setting at N=2 (T-UNIT).

## 2. Records and metrics (measurement by design)

Tables (all `tier:org`, service-role only — no `authenticated` / `anon` privilege; the API is the only door, org-scoped):
`asg_settings` · `asg_teams` · `asg_members` · `asg_rules` · `asg_cursors` · `asg_assignments` (the CURRENT owner, one row per
`(org, subject_kind, subject_id)`) · `asg_events` (APPEND-ONLY, trigger-guarded).

`asg_events.event` ∈ `assigned` · `reassigned` · `unassigned` · `closed` · `no_candidate`, each with `from_user_id`, `to_user_id`, `team_id`,
`org_unit_id`, `strategy`, `criterion` (`round_robin` · `by_team` · `by_source` · `by_unit` · `keep_last` · `manual` · `custom:<name>` · or the
no-candidate reason), `actor_id`, `note`, `created_at`. The assign RPC writes the assignment row, the cursor, the event and the host's
`FunnelConfig.responsavel_field` (when the host named its card table) in one transaction under a per-member advisory lock.

Metrics this enables, each a query over `asg_events` / `asg_assignments`, never a stored counter: distribution share per member and
per team; reassignment rate and who reassigns; `no_candidate` rate per reason (how often a lead waited for a human); capacity
pressure (open per member vs capacity); time-to-first-owner and owner churn per subject; which criterion produced the owner.

## 3. Backend surface

| Piece | Name |
|---|---|
| DDL | `assignment_migration(AssignmentConfig(schema=...), schema)` (organ `assignment`; `noctus.dev.render_organ_migration organ=assignment`) |
| Config | `AssignmentConfig(schema, table_prefix="asg_", subject_kind="card", card_table=None, responsavel_field="responsavel_id", card_has_org_id=True)` · `AssignmentConfig.for_funnel(schema, funnel_cfg)` |
| Store | `AssignmentStore(tables: OrgTableStore, ledger: AssignmentLedger)` · `build_assignment_store(cfg, use_fake=, supabase_client=, card_writer=)` — Fake + Real over the same suite |
| People | `UserDirectory` Protocol · `FakeUserDirectory` · `CoreUserDirectory` (ACTIVE `org_memberships`, never `noctus_users.org_id`) |
| Engine | `strategy.decide(snapshot, ctx, hooks)` — pure; `StrategyHook = (snapshot, ctx) -> Pick | None` |
| Service | `AssignmentService(store, directory, cfg, hooks=)`: teams / members / rules / settings, `assign` · `reassign` · `unassign` · `close`, `workload`, `events` |
| Router | `make_assignment_router(auth, admin, get_service=)` (tier `org`) · seed mount `noctusai_seed.organs.mount_assignment(..., strategy_hooks=)` |

## 4. Endpoint contract (frozen before the FE; `/api/assignment`, tier `org`, envelope `{data: ...}`)

Auth: every route requires an authenticated member of the SELECTED org (strict 401 otherwise). Reads, `assign`, `close`: any org
member. `reassign` / `unassign`: org admin OR the subject's CURRENT owner handing off (else 403 `sem_permissao`). Configuration writes
(settings, teams, members, order, rules): org admin (403 otherwise). Bodies reject unknown fields (422); the org is never in a body.

| Route | Request | Response `data` |
|---|---|---|
| `GET /settings` | — | `{strategy, default_team_id, keep_last, builtin: string[], custom: string[]}` |
| `PUT /settings` | `{strategy?, default_team_id?: uuid\|null, keep_last?}` | settings |
| `GET /teams` · `GET /teams/{id}` | — | `Team[]` / `Team` |
| `POST /teams` (201) | `{name, auto?, org_unit_id?}` | `Team` |
| `PATCH /teams/{id}` · `DELETE /teams/{id}` (204) | `{name?, auto?, org_unit_id?}` | `Team` |
| `POST /teams/{id}/members` (201) | `{user_id, active?, capacity?: int>=1\|null, ooo_from?, ooo_until?}` | `Team` |
| `PATCH /teams/{id}/members/{user_id}` · `DELETE` (204) | `{active?, capacity?, ooo_from?, ooo_until?}` (explicit null clears) | `Team` |
| `PUT /teams/{id}/order` | `{order: uuid[]}` — exactly the team's members | `Team` |
| `GET /rules` · `PUT /rules` · `DELETE /rules/{id}` (204) | `{kind: "source"\|"unit", match_value, team_id}` (upsert per kind+value) | `Rule[]` / `Rule` |
| `GET /workload` | — | `[{user_id, name, open_count, teams: uuid[], available, unavailable_reasons: string[]}]` |
| `GET /events?subject_kind&subject_id&limit&offset` | — | `Event[]` newest first |
| `GET /assignments/{subject_kind}/{subject_id}` | — | the current `Assignment` (404 `Atribuição` when none) |
| `POST /assign` | `{subject_kind, subject_id, source?, org_unit_id?, team_id?, note?}` | `{assigned: true, user_id, team_id, criterion, strategy, changed, event}` or `{assigned: false, reason, strategy}` |
| `POST /reassign` | `{subject_kind, subject_id, to_user_id, team_id?, note?}` | `{assigned: true, user_id, team_id, criterion: "manual", strategy: "manual", changed, event}` |
| `POST /unassign` · `POST /close` | `{subject_kind, subject_id, note?}` | `{changed, event}` |

`Team = {id, name, auto, org_unit_id, members: [{user_id, name, in_org, active, position, capacity, ooo_from, ooo_until, open_count,
unavailable_reason: null|"inactive"|"out_of_office"|"at_capacity"|"left_org"}]}`. `Event = {id, org_id, subject_kind, subject_id, event,
from_user_id, to_user_id, team_id, org_unit_id, strategy, criterion, actor_id, note, created_at}`.

State after: `assign` ⇒ the subject has exactly one open owner, the event row exists, the cursor moved (rotation only) and the host's
`responsavel_field` equals the owner. No candidate is an OUTCOME (200, `assigned: false`, a `no_candidate` event) — never a 5xx.
Idempotent: assigning the current owner again returns `changed: false` and writes nothing.

Errors (`status · code · pt-BR`): 422 `equipe_invalida` · 409 `equipe_duplicada` · 422/409 `membro_invalido` / `membro_duplicado` ·
422 `ordem_invalida` · 422 `regra_invalida` · 422 `estrategia_invalida` · 422 `filtro_invalido` · 409 `capacidade_esgotada` (every candidate
filled up while the distribution ran, after 3 fresh-snapshot retries) · 403 `sem_permissao` · 404 for a missing / foreign-org id.

## 5. Frontend surface (`@noctusai/lib` `assignment/`)

`createAssignmentHooks(api)` (TanStack, `useCacheWriteMutation` on every write, `showSkeleton` / `isRefreshing`, never `isLoading`) ·
`<TeamsManager hooks canWrite/>` · `<AssignmentRulesPage hooks canWrite/>` · `ASSIGNMENT_PAGE_KEYS` + `assignmentModuleItems(...)` so a
module mounts both pages under its own paths. pt-BR copy in `messages.ts`; error codes map through `assignmentErrorMessage`.

## 6. Named seams and what stays out

- `assignment_strategy`: builtin set + `strategy_hooks={name: hook}` (a market's plantão / account-manager rule). A hook sees the same
  snapshot the builtin strategies do and can only return an eligible member.
- Out of this organ: corretor / plantão nouns (preset data), the lead's own table, notifications to the new owner, the SW alias map
  of imported owner names (`lead_corretor_aliases` — lead-import dimension, stays with lead intake W2-2).
- Known follow-ups: a projection-reconcile pair for `asg_assignments.user_id` vs the host's `responsavel_field`
  (`noctus.dev.projection_reconcile` registry; per product, at the first consumer); per-team capacity weights if a market asks.

## Composes with

`KB § PATTERNS/architect/vertical-seed.md` (CRM seams) · `KB § PATTERNS/architect/event-oriented-architecture.md` ·
`KB § PATTERNS/architect/measurement-by-design.md` · `KB § PATTERNS/security/access-tiers.md` · `KB § PATTERNS/backend/leads-organ.md` ·
`KB § PATTERNS/frontend/mutation-cache-writes.md`.
