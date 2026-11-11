# Activities organ (seed-lib) — tasks, calls, meetings, visits on any entity

> `noctusai_lib.domain.activities` (backend) + `@noctusai/lib` `activities/` (frontend). Slice W1-5 of the CRM vertical seed (`project-history/roadmaps/crm-cms-erp-vertical-seeds-2026-11.plan.md` §2.1; frozen contract `…activities-contract.md`). Formalizes three copies — erp-imobiliario `atividades.py`, orbity `tasks_router.py`, social-wiring card-hub `lembretes` — the 4th is forbidden (`KB § PATTERNS/architect/project-execution.md`). The products migrate onto it in their own slices.

## 1. Model

| Table | What |
|---|---|
| `act_types` | The market's activity TYPES, as data: `(org_id, slug)`, `label`, `kind` ∈ `task·call·meeting·visit`, `position`, `active`. Seeded lazily per org from `ActivitiesConfig.default_types` = `CrmPreset.activity_types` (empty ⇒ tarefa / ligação / reunião); the org edits label / position / active; the slug is immutable. Key custody, maintenance and field work are rows of a market preset, never code. |
| `act_activities` | One activity linked to `(entity_kind, entity_id)` (polymorphic, no FK), with `due_at`, `assignee_id` (a plain user id), nullable `org_unit_id` (the multi-branch convention, carried and never interpreted), done / undone / cancelled and an enum `outcome`. Never hard-deleted. |
| `act_events` | APPEND-ONLY (trigger). `atividade_criada · concluida · reaberta · reatribuida · reagendada · editada · cancelada`, written by the RPC in the same transaction as the change; `data` holds ids and changed field names, never free text. |

## 2. Rules

- **Event-oriented.** Every write is one row-locked RPC (`act_create`, `act_apply(intent)`): state change + event in one transaction. A repeated intent that changes nothing answers `replayed` and appends no event. A refusal rolls back and leaves no event. `NOC-REMEDIATE[transition-log-primitive]`: the events table is hand-written until the E1 primitive lands on `dev`.
- **Access tier.** Tables and RPCs are service-only (RLS own-org SELECT floor, no write grant, RPC `EXECUTE` for `service_role` only). Routes are org staff; the activity TYPES writes need an org admin. Server-side org isolation: a foreign id is a 404.
- **Assignee.** A plain user id validated against ACTIVE org membership through `ActivitiesContext.is_member`, which `mount_activities` wires over `domain.org_memberships.get_membership`. No dependency on the assignment organ (strategies live there).
- **Overdue is derived on read**, never stored.
- **Guards** (CHECK / append-only trigger) are declared with the generator (`activities_guard_probes`) and proven on PGlite through `migration_replay`.

## 3. Mount

```python
organ = mount_activities(schema="crm", auth_dependency=..., get_admin_client=..., get_core_client=..., preset=PRESET)
sql = organ_migration_sql("activities", "crm")        # or noctus.dev.render_organ_migration organ=activities
```

FE: `createActivitiesHooks(api)` → `<ActivitiesPanel hooks entityKind entityId/>` as a card-hub subpage and `<MyTasksPage hooks/>` under `ACTIVITIES_PAGES.myTasks` (`crm_atividades`, `/crm/atividades`). Names of assignees are a host seam (`assigneeLabel`, `assigneeOptions`).

## 4. Not here (named destinations)

Assignment strategies → `crm-assignment-organ`. Reminder delivery → `NOC-REMEDIATE[reminder-delivery]`. Activity types settings screen → the CRM module slice (`crmModule`, Configurações). Migrating the three product copies → their canon slices.
