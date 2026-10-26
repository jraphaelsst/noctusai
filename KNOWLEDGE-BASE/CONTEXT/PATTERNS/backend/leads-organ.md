# Leads organ (seed-lib) — WhatsApp-fed funnel

> `noctusai_lib.domain.leads` (backend) + `@noctusai/lib` `leads/` (frontend). Formalizes three divergent
> product copies (social-wiring `leads` 025, orbity `leads` 005, igig `lead` 012) — the 4th instance is
> forbidden (`KB § PATTERNS/architect/project-execution.md`). First consumer: `monica` (psicanálise).

## 1. What it is

One lead = a person who reached out (usually by WhatsApp) and where they are in the funnel. **Lite on purpose:**
name · phone · e-mail · origin · stage · notes · tags · first contact · last-message preview. No pipeline-stage
tables, no activities log, no money — a product that needs those extends, it does not fork.

## 2. Data, not enums

`LeadsConfig(stages=[LeadStage(slug, label, color?)], origins=[LeadOrigin(slug, label)])` is supplied by the
product. `stage` / `origin` are plain `TEXT` columns (no CHECK) so **changing the lists never needs a migration**.
Leads on a stage the config no longer lists are NOT hidden: the board adds a synthetic "Sem etapa" column
(`ORPHAN_STAGE`) and they can be dragged back. Strings are accepted as shorthand (`stages=["lead", "fechado"]`).

## 3. Backend surface

| Piece | Name |
|---|---|
| DDL | `leads_table_ddl(schema)` / `leads_migration(schema)` (registered as organ `leads`; `noctus.dev.render_organ_migration organ=leads`) |
| Store | `LeadsStore` Protocol · `FakeLeadsStore` · `SupabaseLeadsStore` · `build_leads_store(client, schema=, fake=)` (no client + no `fake=True` is an error — never a silent in-memory store) |
| Service | `LeadsService(store, config)`: `create/update/delete/get/list_leads/board/move`, `upsert_from_whatsapp`, `touch_last_message` |
| Router | `create_leads_router(store_factory=, get_current_user_org=, config=)` · seed mount `noctusai_seed.organs.mount_leads` |

Routes: `GET /api/leads?stage=&origin=&from=&to=&q=&limit=&cursor=` · `POST /api/leads` · `GET /api/leads/board` ·
`GET /api/leads/config` · `GET|PATCH|DELETE /api/leads/{id}` · `POST /api/leads/{id}/move {stage, position}`.
Everything is org-scoped (a foreign id is a 404) and any org member may do anything — a lead is fully CRUD-able.

### Ordering (one write per drag)
`position` is `NUMERIC` and fractional (`domain.pipeline.ordering`): dropping between two cards stores the midpoint,
a new lead goes above the column. `move`'s `position` is the **destination index** the kanban reports (0 = top).
Board = `position`, then `created_at`; list = newest first contact first (cursor is an opaque offset).

### Phone
Stored canonical E.164 (`primitives.phone.normalize_phone`); an unparseable non-empty phone is a 422
`telefone_invalido`, never stored. **Search matches what the user types**: a term without letters and with ≥3
digits also matches the stored phone's digits (`parse_search`), so "(11) 99457-3387", "99457" and "+55 11 99457"
all find `+5511994573387`. Text matches name / e-mail / notes (`ILIKE`, accent-sensitive).

### WhatsApp seam
`await service.upsert_from_whatsapp(org_id, connection_id, chat)` is call-compatible with the inbox organ's
`on_new_chat`; `chat` is any object or mapping with `chat_id, name, phone, last_message_preview, last_message_at`.
Idempotent by `(org, connection, chat)` — the `uq_leads_chat` partial UNIQUE index is the real guard (a lost race
re-reads the winner). A deleted lead is NOT recreated by `touch_last_message`; the inbox fires `on_new_chat` once
per chat, so deleting a non-lead number is permanent. Keep the card fresh by passing `LeadsService.touch_last_message` from the inbox's `on_message` seam (inbound AND outbound) -- see `monica`'s `app/services/whatsapp_leads.py`.

## 4. Frontend surface

`createLeadsHooks(api)` → `useLeadsConfig · useLeadsBoard · useLeadsList · useLead · useCreateLead · useUpdateLead ·
useDeleteLead · useMoveLead`; components `LeadsBoard` (seed `KanbanBoard`), `LeadCard`, `LeadsList`,
`LeadDetailModal` (needs `ConfirmProvider`; `onOpenConversation(lead)` prop), `LeadFormDialog`, `LeadsFilterBar`.
Filters are controlled-optional (`filters` / `onFiltersChange`) so Funil and Lista can share one search.

Rules it follows (all keeper-backed): every write is a `useCacheWriteMutation` (move = optimistic card move across
every cached board, rolled back on refusal; update = drawn at once, server row committed; delete = gone on the click;
create = committed into the UNFILTERED board/list, filtered views converge on the settle refetch); loading is
`showSkeleton = isPending && !data` — a filter change keeps the previous board on screen; a failed load shows
the error with a retry, never an empty claim.

## 5. Known limits
- A drag on a **filtered** board computes its index against the unfiltered column (the server knows no filters on `move`).
- Search is accent-sensitive (`ilike`, no `unaccent`).
- The PostgREST test double does not evaluate `or_()`: the search rule is tested on the Fake and the Real store's
  expression is pinned as a string; the UNIQUE/CHECK guards are proven on PGlite (`tests/domain/leads/test_sql.py`).

Composes with: `seed-fake-real-adapter` · `database-rls` · `mutation-cache-writes` · `lying-loading-state` ·
`whatsapp-chatbot-seed` (the inbox organ that feeds `on_new_chat`) · `products-consume-canonical-organs`.
