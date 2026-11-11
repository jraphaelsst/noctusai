# Activities organ — frozen contract (W1-5)

> Slice W1-5 of `crm-cms-erp-vertical-seeds-2026-11.plan.md` §2.1 row "activities". BE `noctusai_lib.domain.activities`, FE `seed/lib/frontend/src/activities/`. Frozen BEFORE the code (skill `noc-contract-first`); a change after this point edits this file in the same commit.

## 1 · Model (tables `act_*`, schema = the product's)

| Table | Rows | Notes |
|---|---|---|
| `act_types` | `(org_id, slug)` PK, `label`, `kind` ∈ `task·call·meeting·visit`, `position`, `active` | market DATA. Seeded lazily per org from `ActivitiesConfig.default_types` (= `CrmPreset.activity_types`); the org edits label/position/active, the `slug` is immutable. `chave_retirada` / `chave_devolucao` / `manutencao` / `campo` are rows, never code. |
| `act_activities` | `id`, `org_id`, `entity_kind` (slug), `entity_id` (uuid, polymorphic, no FK), `type_slug` (FK with `org_id`), `kind` (copied from the type at create), `title`, `notes`, `due_at`, `assignee_id` (plain user id, nullable), `org_unit_id` (nullable convention, no FK), `done_at`, `done_by`, `outcome`, `cancelled_at`, `created_by`, `created_at`, `updated_at` | open = `done_at IS NULL AND cancelled_at IS NULL`. Never hard-deleted (`cancelar` is the intent). `outcome` ∈ `realizada·nao_realizada·sem_resposta`. |
| `act_events` | `id`, `seq`, `org_id`, `activity_id`, `event`, `actor_id`, `occurred_at`, `data` jsonb | APPEND-ONLY (trigger). Written by the RPCs in the same transaction as the state change. `data` carries ids and changed fields, never free text (LGPD). |

Events: `atividade_criada` · `atividade_concluida` · `atividade_reaberta` · `atividade_reatribuida` (`from`,`to`) · `atividade_reagendada` (`from`,`to`) · `atividade_editada` (`fields`) · `atividade_cancelada`.

Metrics this enables (measurement-by-design): completion rate per type, overdue rate, time-to-complete (created→concluida), reassignment count, outcome mix per kind, load per assignee and per `org_unit_id`.

## 2 · Access tier

Every table and RPC is **service-only** (tier `service`): `authenticated` has a SELECT policy on own-org rows only (RLS floor, `org_id = (SELECT current_org_id_for(<schema>))`), no write grant; all writes go through the service-role RPCs, which `REVOKE` from `PUBLIC/anon/authenticated`. The HTTP routes are org-staff (`org` tier) with server-side `org_id` isolation: an id from another org is a 404.

## 3 · HTTP (`/api/activities`, envelopes `{data}` / `{data, pagination}`)

| Route | Who | Body / query | Answer |
|---|---|---|---|
| `GET /types?active=` | staff | | `{data:[Type]}` (lazy-seeds an empty org) |
| `POST /types` | admin | `{slug,label,kind,position?}` | `201 {data:Type}` · `409 tipo_duplicado` |
| `PATCH /types/{slug}` | admin | `{label?,position?,active?}` | `{data:Type}` |
| `GET /` | staff | `entity_kind,entity_id,assignee_id,status(open·done·cancelled·all, default open),type_slug,kind,overdue,due_from,due_to,page,page_size` | `{data:[Activity],pagination}` |
| `GET /mine` | staff | same filters minus `assignee_id` | the caller's own, ordered by `due_at` (nulls last) |
| `POST /` | staff | `{entity_kind,entity_id,type_slug,title,notes?,due_at?,assignee_id?,org_unit_id?}` | `201 {data:Activity}` |
| `GET /{id}` · `GET /{id}/events` | staff | | `{data:Activity}` / `{data:[Event]}` |
| `PATCH /{id}` | staff | `{title?,notes?}` | `atividade_editada` |
| `POST /{id}/complete` | staff | `{outcome?}` (default `realizada`) | `atividade_concluida` (idempotent: second call answers the row, no second event) |
| `POST /{id}/reopen` | staff | | `atividade_reaberta` |
| `POST /{id}/reassign` | staff | `{assignee_id: uuid\|null}` | `atividade_reatribuida`; the assignee must be an ACTIVE member of the org (`422 responsavel_invalido`) |
| `POST /{id}/reschedule` | staff | `{due_at: iso\|null}` | `atividade_reagendada` |
| `POST /{id}/cancel` | staff | | `atividade_cancelada` |

`Activity` = the row + `overdue: bool` (derived on read, never stored). Refusals: `404`, `409 atividade_encerrada` (editing a done/cancelled one), `422 tipo_invalido|responsavel_invalido|desfecho_invalido`.

## 4 · FE (`@noctusai/lib`, folder `activities/`)

`createActivitiesHooks(api)` → `useActivities(params)`, `useMyActivities(params)`, `useActivityTypes()`, `useActivityEvents(id)`, `useActivityMutations()` (create · complete · reopen · reassign · reschedule · edit · cancel, all through `useCacheWriteMutation`). `ActivitiesPanel({hooks, entityKind, entityId, assigneeLabel?, assigneeOptions?})` = the card-hub tab; `MyTasksPage({hooks, ...})` = the page. Page keys + paths exported as `ACTIVITIES_PAGES` (`crm_atividades` → `/crm/atividades`) for `defineModule`; BE `ACTIVITIES_PAGES` mirrors them. pt-BR copy in `messages.ts`.

## 5 · Out of scope (named destinations)

Assignment strategies/distribution → `feat/crm-assignment-organ`. Reminder DELIVERY (notifying on due) → `NOC-REMEDIATE[reminder-delivery]` (same marker the card-hub carries). Migrating erp-imobiliario `atividades.py` / orbity `tasks_router.py` / SW `lembretes` onto the organ → their canon migration slices (W3-S2, W7-O, ERP-imob). Assignee display names → host seam `assigneeLabel`.
