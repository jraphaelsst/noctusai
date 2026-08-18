# lead-card-hub Phase 2 — the card · PROJECT + CONTRACT

> **Parent roadmap:** `project-history/roadmaps/lead-card-hub-2026-08.md` (D1–D17, ratified 2026-08-07).
> **Reference screenshots:** `project-history/roadmaps/assets/lead-card-hub-2026-08/trello-reference/`
> — 11 files, recovered 2026-08-18. **Build against the images**, not against prose.
> **Status:** contract authored 2026-08-18; slices dispatched.

This document is the **contract** (`noc-contract-first`): it is authored ONCE and both the
backend and the frontend build to it. Neither side invents a field.

---

## 0 · Scope rulings for this phase (2026-08-18 session)

| # | Ruling | Consequence |
|---|---|---|
| **S1** | `/funil` dedup and the card are built **in parallel**. | P1.4 completion is its own slice (`054`); the card slices must not touch `app/modules/pipeline/` or `pages/funil/*`. |
| **S2** | Documents ship **LGPD-complete from day one** (D5). | Object RLS + per-type retention + delete-on-request + access log land in the same slice as upload. No "attachments now, governance later". |
| **S3** | 🔴 **D13 is reversed for now — build product-local in `social-wiring` only.** *"social wiring only for now"*. | The card does **not** go into `@noctusai/lib` this phase, and erp-imobiliario does not consume it. **Mitigation, mandatory:** every card component stays *presentational* — props in, callbacks out, **zero** imports from `@/pages/**`, `@/hooks/useClientes` or any social-wiring-specific module inside `components/card/**`. Data access is confined to `hooks/useCardHub.ts`. Lifting to `@noctusai/lib` later must be a move, not a rewrite. |

**S3 is an `[A]` accept-with-rationale**, not a silent divergence: it contradicts D13 and the
replication-to-seed rule, the objection was raised at decision time, and the user chose it
anyway. It is recorded here and in the roadmap's decision log so the reversal is legible.
The cost, stated plainly: when erp consumes this, the seam is unproven, and an unproven seam
is usually the wrong seam.

---

## 1 · What already exists (do not rebuild)

| Thing | Where | Note |
|---|---|---|
| `clientes` person layer | `migrations/048_clientes_person_layer.sql:122` | canonical key, RLS, `ativo`/`inativo_em`/`arquivado_em` |
| `cliente_touches` | `048:196` | every `leads` + `meta_ads_leads` row is a touch, idempotent on `(origem_tabela, origem_id)` |
| `cliente_merges` (reversible) | `048:236` | D3's undo record |
| `GET /clientes/{id}` | `app/routers/clientes_router.py:432` | returns cliente + negociações + touch_count — **served, no FE consumer** |
| `GET /clientes/{id}/touches` | `clientes_router.py:415` | the timeline feed — **served, no FE consumer** |
| `ClientesBoard` + `ClienteCard` | `frontend/src/pages/clientes/` | grid, Ativos/Inativos tabs, no click target |
| `EntityDetailDialog` | `seed/lib/frontend/src/components/detail/` | the seed dialog organ `LeadDetailModal` is built on |
| `KanbanBoard` / `PipelineBoard` | `seed/lib/frontend/src/components/{kanban,pipeline}/` | content-agnostic; `renderCard` is the consumer's job |
| `pipeline_movimentos` | migration `034` | stage-move history, **rendered nowhere** — the timeline finally consumes it |

---

## 2 · Data model — migrations `056` (core) and `057` (documents)

Schema `social_wiring`. Every table: `org_id uuid not null`, RLS enabled with the same
`current_org_id()` predicate the rest of the schema uses (`011_rls_current_org_id.sql`),
plus a `service_role` policy. Every table gets `created_at timestamptz not null default now()`.

### `056` — core card surface

**`cliente_notas`** — annotations.
`id` · `org_id` · `cliente_id → clientes(id) ON DELETE CASCADE` · `autor_id uuid` (profiles) ·
`corpo text not null` · **`tipo text not null default 'comentario' check (tipo in ('descricao','comentario'))`** ·
`editado_em timestamptz null` · `deleted_at timestamptz null`.
Soft-delete only — a deleted note leaves a tombstone in the timeline, it does not rewrite history.

🔴 **CORRECTION (2026-08-18).** The first draft of this contract gave notes a single
undifferentiated `corpo`, conflating two distinct Trello concepts: **Descrição** (exactly one
per card, edited in place, top of the left pane) and **Comentários** (many, chronological,
right pane). With no discriminator the frontend was forced to guess — it shipped "the oldest
*loaded* note is the description", which breaks the moment a card's history exceeds one page.
The gap was surfaced by the frontend engineer and fixed here rather than worked around there.

A partial unique index enforces **at most one live `descricao` per cliente**
(`where tipo = 'descricao' and deleted_at is null`) — a DB constraint, not an application
promise. Consequences: `POST .../notas` takes `{corpo, tipo?}` (default `comentario`) and
returns a **typed error** on a second `descricao`; the timeline emits only `comentario` as
`kind: "nota"` — **the description is card state, not an activity event**, and putting it in
the thread would make every edit look like a new comment; `CardResumo` carries
`descricao: {id, corpo, editado_em} | null`, and `badges.tem_descricao` derives from it rather
than from "any note exists".

**`cliente_tags`** — the org's tag catalogue (D6: **one** system, no separate "classification").
`id` · `org_id` · `nome text not null` · `cor text not null` (hex) · `UNIQUE (org_id, lower(nome))`.

**`cliente_tag_links`** — `cliente_id` · `tag_id` · `criado_por` · `PRIMARY KEY (cliente_id, tag_id)`.

**`cliente_membros`** — assignment (Trello *Membros*).
`cliente_id` · `lead_corretor_id → lead_corretores(id)` · `PRIMARY KEY (cliente_id, lead_corretor_id)`.
Points at `lead_corretores.id`, **never** at a name — D10 adds `user_id` there in Phase 3 and
this table must not need changing when it does.

**Columns added to `clientes`** (Trello *Datas*, screenshot 06):
`data_inicio timestamptz null` · `data_entrega timestamptz null` ·
`entrega_concluida boolean not null default false` ·
`lembrete_minutos_antes integer null` · `recorrencia text null` (`null|diaria|semanal|mensal|anual`).

**`cliente_lembretes`** — the reminder mechanism, which **exists nowhere in the product today**.
`id` · `org_id` · `cliente_id` · `dispara_em timestamptz not null` · `enviado_em timestamptz null` ·
`cancelado_em timestamptz null` · `destinatarios jsonb`.
Index on `(dispara_em) WHERE enviado_em IS NULL AND cancelado_em IS NULL` — the sweep's read path.

**`cliente_checklists`** (D11 — **both** halves).
`id` · `org_id` · `cliente_id` · `titulo text not null` · `posicao integer not null` ·
`origem text not null check (origem in ('ad_hoc','etapa'))` · `etapa_id uuid null`.
`origem='etapa'` is a stage-required checklist instantiated onto the card; `'ad_hoc'` is
user-created (screenshot 07). **Multiple checklists per card is required** (screenshot 10).

**`cliente_checklist_itens`** —
`id` · `checklist_id ON DELETE CASCADE` · `texto text not null` · `concluido boolean not null default false` ·
`concluido_em` · `concluido_por` · `posicao integer not null`.

### `057` — documents, LGPD-complete (D5 · ruling S2)

**`cliente_documentos`** —
`id` · `org_id` · `cliente_id` · `storage_path text not null` · `nome_original text not null` ·
`mime_type text not null` · `tamanho_bytes bigint not null` ·
`tipo_documento text not null` · `categoria_lgpd text not null` ·
`retencao_ate date null` · `enviado_por uuid` ·
`deleted_at timestamptz null` · `delete_motivo text null` · `delete_solicitado_por uuid null`.

**`cliente_documento_acessos`** — the access log; **every** read, download and delete appends here.
`id` · `documento_id` · `usuario_id` · `acao text check (acao in ('view','download','delete'))` · `created_at`.
Append-only: no `UPDATE`/`DELETE` policy for any role but `service_role`. An access log a user
can edit is not an access log.

**Storage:** org-scoped bucket path `social-wiring/{org_id}/clientes/{cliente_id}/{document_id}`,
with **object-level RLS** — not merely a hard-to-guess path. Signed URLs, short TTL, minted
per request and logged.

**Retention:** `retencao_ate` is derived from `tipo_documento` by a table-driven policy, not by
a hardcoded `if`. A sweep soft-deletes past-retention documents and appends to the access log.

🔴 **Before any RG/CPF-bearing document type is enabled**, file the data-category intake via
`noctus.dev.lgpd_flag`. The upload surface ships with a **conservative default document-type
list** that excludes identity documents until that intake is filed.

---

## 3 · API contract — `/api/clientes/{cliente_id}/...`

**Envelope conventions (house):** list responses are `{"items": [...], "total": n}`; errors go
through `AppException` → `{"error": {"code": "...", "message": "..."}}` — **never** `{"detail": ...}`.
All routes are org-scoped and auth-required. Auth tests assert strict `== 401`.

### Timeline (D9 — one thread containing everything)

```
GET /api/clientes/{id}/timeline?cursor=&limit=50&kinds=nota,touch,movimento,documento,checklist,sistema
  → {"items": [TimelineEntry], "total": n, "next_cursor": str|null}
```

`TimelineEntry` is a **discriminated union** on `kind`, newest-first:

| `kind` | source | payload |
|---|---|---|
| `nota` | `cliente_notas` | `{id, corpo, autor: {id, nome}, editado_em, deleted_at}` |
| `touch` | `cliente_touches` | `{id, origem_tabela, origem_id, origem_rotulo, resumo, dados}` |
| `movimento` | `pipeline_movimentos` | `{id, de_etapa, para_etapa, autor}` — **finally rendered** |
| `documento` | `cliente_documentos` | `{id, nome_original, mime_type, tamanho_bytes}` |
| `checklist` | derived | `{checklist_id, titulo, item_texto, concluido}` |
| `sistema` | derived | `{evento, detalhe}` — created, merged, archived, restored |

Every entry carries `{id, kind, ocorrido_em, ator: {id, nome} | null}`. **`ocorrido_em` is the
sort key and it is the event's own time, never `created_at` of the row that records it** — a
backfilled touch from March must sort in March.

Cursor pagination, not offset: the thread grows at the head.

### Notes

```
POST   /api/clientes/{id}/notas          {corpo}          → 201 Nota
PATCH  /api/clientes/{id}/notas/{nota_id} {corpo}         → 200 Nota   (sets editado_em)
DELETE /api/clientes/{id}/notas/{nota_id}                 → 204        (soft)
```

### Tags

```
GET    /api/clientes/tags                                 → {items:[Tag], total}   (org catalogue)
POST   /api/clientes/tags                {nome, cor}      → 201 Tag
PATCH  /api/clientes/tags/{tag_id}       {nome?, cor?}    → 200 Tag
DELETE /api/clientes/tags/{tag_id}                        → 204   (also unlinks; refuse with a
                                                                   typed error if you would
                                                                   rather warn — do not silently
                                                                   orphan links)
PUT    /api/clientes/{id}/tags           {tag_ids: [...]} → 200 {items:[Tag], total}  (full set)
```

### Membros

```
GET  /api/clientes/{id}/membros                           → {items:[Membro], total}
PUT  /api/clientes/{id}/membros  {lead_corretor_ids:[..]} → 200 {items, total}
```

### Datas + lembretes (screenshot 06)

```
PATCH /api/clientes/{id}/datas
  {data_inicio?, data_entrega?, entrega_concluida?, lembrete_minutos_antes?, recorrencia?}
  → 200 {data_inicio, data_entrega, entrega_concluida, lembrete_minutos_antes,
         recorrencia, proximo_lembrete: {id, dispara_em} | null}
```

Setting `data_entrega` + `lembrete_minutos_antes` **must** materialise a `cliente_lembretes`
row; clearing either cancels it. A reminder UI that stores an intention nobody acts on is a
lying UI — if the delivery path is not wired in this slice, the endpoint must say so via
`proximo_lembrete: null` plus a documented `NOC-REMEDIATE[reminder-delivery]` marker, not by
quietly accepting the value.

### Checklists

```
GET    /api/clientes/{id}/checklists                      → {items:[Checklist], total}
POST   /api/clientes/{id}/checklists     {titulo}         → 201 Checklist
PATCH  /api/clientes/{id}/checklists/{cid} {titulo?, posicao?} → 200
DELETE /api/clientes/{id}/checklists/{cid}                → 204
POST   /api/clientes/{id}/checklists/{cid}/itens  {texto} → 201 ChecklistItem
PATCH  .../itens/{iid}  {texto?, concluido?, posicao?}    → 200 ChecklistItem
DELETE .../itens/{iid}                                    → 204
```

`Checklist` carries `{id, titulo, posicao, origem, etapa_id, itens: [...], total_itens,
concluidos}` — the progress bar is served, not counted in the browser.

### Documentos (LGPD)

```
GET    /api/clientes/{id}/documentos                      → {items:[Documento], total}
POST   /api/clientes/{id}/documentos    (multipart)       → 201 Documento
GET    /api/clientes/{id}/documentos/{did}/url            → 200 {url, expires_at}   (logs 'view')
DELETE /api/clientes/{id}/documentos/{did}?motivo=...    → 204  (soft; logs 'delete')
GET    /api/clientes/{id}/documentos/{did}/acessos        → {items:[Acesso], total}
GET    /api/clientes/documentos/tipos                     → {items:[TipoDocumento], total}
```

`Documento` carries `{id, nome_original, mime_type, tamanho_bytes, tipo_documento,
categoria_lgpd, retencao_ate, enviado_por: {id,nome}, created_at, thumbnail_url|null}`.

Limits enforced **server-side**: max size, MIME allow-list. A rejected upload returns a typed
error naming the limit it hit — never a generic 400.

🔴 **CORRECTION (2026-08-18): `motivo` is a QUERY PARAM, not a body.** The seed `ApiClient.delete()`
has no body parameter, so a DELETE-with-body forced the frontend into a raw `fetch` workaround —
and DELETE bodies are poorly supported across the stack generally. `motivo` stays **required**:
an LGPD delete without a recorded reason is not an LGPD delete.

🔴 **The upload ceiling is NOT a card-hub number.** A 1 MB **app-wide** body cap
(`MaxBodySizeMiddleware`, `settings.max_body_bytes`) sits in front of every route, so the first
implementation had to cap documents at 800 KB just to fit under it — which makes photos
impossible. Found in passing: the same cap has been silently killing `POST /api/videos/upload`
(browser drag-drop) since it shipped. Fixed at the right level — a per-path override in the seed
middleware — rather than by raising the cap app-wide, which would weaken the DoS guard on the
webhook routes where it actually earns its keep. **The frontend must never hardcode the limit**;
the server's typed error is the single source of truth.

### Card summary (the badge row — screenshot 11)

```
GET /api/clientes/{id}/card       → CardResumo
```

```
CardResumo = {
  cliente: {...},                         # existing GET /clientes/{id} shape
  tags: [Tag],
  membros: [Membro],
  datas: {data_inicio, data_entrega, entrega_concluida, lembrete_minutos_antes, recorrencia},
  badges: {
    notas: int, documentos: int, touches: int,
    checklist_total: int, checklist_concluidos: int,
    tem_descricao: bool, temperatura: {valor, rotulo, provisoria: true} | null
  },
  negociacoes: [...]                      # D17 — active AND closed, as history
}
```

The `badges` block exists so the **board** can render card faces without N+1 calls: the board
list endpoint must return these counts inline for every card. Trello's own `Card.badges` object
(`checkItems`, `checkItemsChecked`, `comments`, `attachments`, `description`, `due`,
`dueComplete`) is the precedent — that shape is not an accident, it is what a board needs.

`temperatura` is D8's provisional formula (recency of last touch + touch count) and **must**
carry `provisoria: true` so the UI can label it as provisional. D8 deferred the *formula*, not
the *component*.

---

## 4 · Frontend — `products/social-wiring/frontend/src/components/card/`

Per ruling **S3**, everything under `components/card/**` is presentational: props in, callbacks
out, no data fetching, no product-specific imports. All queries/mutations live in
`hooks/useCardHub.ts`.

### The card face — `ClienteCardFace.tsx` (screenshot 11)

Colour strip (first tag's colour) · title · badge row: due-date pill (with state colouring),
description glyph, `📎 n`, `☑ done/total`, temperature. Badges render **only when non-zero** —
Trello shows nothing rather than a zero, and so do we.

### The detail — `ClienteCardDialog.tsx` (screenshots 02, 03, 09, 10)

**Two panes.** Left = content: title, action row (`+ Adicionar` · Etiquetas · Datas · Checklist ·
Membros · Anexo), then `Etiquetas` chips, `Data Entrega` pill, `Descrição`/notes with a
`Mostrar mais` collapse, `Anexos`, then each checklist with its own `%` bar.
Right = **`Comentários e atividade`**: the composer on top, then the unified timeline.

Popovers, each matching its screenshot: `AdicionarPopover` (04) · `EtiquetasPopover` (05,
including **`modo compatível para daltonismo`** — not optional, it is in the shot) ·
`DatasPopover` (06, start + due + time + recurrence + reminder) · `ChecklistDialog` (07) ·
`MembrosPopover` (08).

**pt-BR copy throughout**, matching the screenshots verbatim where they show a string.

### Mandatory FE rules

- 🔴 Gate every loading UI on **`isPending || isFetching`**, never `isLoading` — keeper
  `check_lying_loading_state`. This product shipped that exact bug to a real customer.
- Every surface has all four states: loading · empty · error · success. "Empty" only when
  **truly** empty.
- The dialog is reachable from **both** `ClientesBoard` (which has no click target today) and,
  once slice `054` lands, the funil card. One dialog, two entry points — never two dialogs.

---

## 5 · Anti-goals

- No `@noctusai/lib` extraction this phase (S3) — but no product-specific coupling either.
- Do not touch `products/orbity` or `products/erp-imobiliario` (standing user scope ruling).
- Do not build Phase 2b (WhatsApp/DM embed+reply). The timeline is built **with a slot for it**
  — a `kind` union that accepts a new member without a rewrite — and nothing more.
- Do not build stage-aware fields/actions (D12) or corretor-as-user (D10) — Phase 3.
- Do not invent a field. If the contract is missing something the screenshots require,
  **surface it** rather than adding it silently on one side.
