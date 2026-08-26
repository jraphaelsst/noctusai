# Roteiros & Visitas — PROJECT / CONTRACT

> Branch `feat/sw-roteiros-visitas`. Authored 2026-08-25 by the tech-lead
> BEFORE either side was built (`noc-contract-first`): one contract, two
> file-disjoint slices (BE / FE) built in parallel against it.

## 0 · The ask, verbatim in substance

The `qualificação → visita` funnel needs a real object. Today the card can
only book an *appointment* whose `tipo` happens to be `visita`, which is a
calendar entry, not a route: it cannot hold several properties, cannot be
ordered, cannot be printed, and cannot be counted as happened / didn't happen.

- The card gets a sidebar tab **Roteiros**.
- `roteiros` and `visitas` each get a table.
- The **Agendar** button stops offering `Visita` — visits now come from a roteiro.
- The tab has a **Criar Roteiro** button opening a modal with a live property
  search (type `ONE9` → every `ONE9xxxx` we hold appears in a popover under the
  field), click a row → the property joins the roteiro list.
- Creating the roteiro creates one **Visita** per listed property. A visita is
  later fed with the corretor's feedback (did it happen?) plus an observation.
  **This must be countable** — visitas that happened vs. that didn't.
- Each listed property renders as a **card** (main photo, ref, condomínio,
  endereço, owner name + cellphone) and is **drag-and-drop reorderable** —
  the order IS the visiting order.
- A **Gerar Roteiro** button produces a PDF cronograma, in order, **one property
  per page**, carrying: condomínio, endereço, corretor responsável pela captação,
  owner name + cellphone.

## 1 · Three ratified decisions (do not re-litigate)

**D1 — Owner data is BLANK for now, and its destination is named (user-ratified 2026-08-25).**
Vista does not expose it. `CANDIDATE_IMOVEL_LIST_FIELDS` /
`CANDIDATE_IMOVEL_DETAIL_FIELDS` (`noctusai_lib/integrations/vista/calibration.py`)
carry no proprietário field, and `social_wiring.imoveis` (migration 040) has no
owner column — so there is no source to read. The user chose to ship the slot
empty rather than invent one.

Consequences, and they are binding:
- **No `proprietario_*` column on `visitas`, and no `proprietario` key on the
  API.** A column nothing can write is a placeholder side
  (`KB § 03-SEED-ARCHITECTURE` — no incomplete commits); a response field that
  is structurally always `null` lies about the contract.
- **The destination is `social_wiring.imovel_dados` (migration 075).** That
  table already exists and is precisely "what WE know about a property, beside
  what Vista tells us" — authored per-imóvel data, keyed `(org_id, codigo)`,
  FK'd to the registry. Owner name + celular are that, exactly. They do NOT go
  on `visitas` (which would retype the same owner for every roteiro) and they
  do NOT go on the mirror (which a sync overwrites).
- The **UI and the PDF render `—`**, each carrying a
  `NOC-REMEDIATE[imovel-owner-data]` marker that names `imovel_dados` as the
  destination (`KB § PATTERNS/common/remediation-markers.md`). That marker is
  the whole paperwork for this divergence — do not silently drop it.

**D2 — The PDF is built server-side with `reportlab` (user-ratified 2026-08-25).**
Nothing in the fleet generates PDFs today; this is the first. `reportlab` is
pure-Python — no Cairo/Pango, so the house single-container image is unchanged
(WeasyPrint was rejected for exactly that cost). Server-side also means the same
bytes can later be attached to an email or a WhatsApp message without a browser.

**D3 — Real FKs, pointed at `imovel_registry` (user-directed 2026-08-25).**
The user's requirement: per-imóvel and per-lead statistics, and a cliente
history durable enough that in 2028 an agent can ask what happened with this
person in 2024 — for sales triggers, and for caution flags.

That requirement is what decides the FK TARGET, and it rules the mirror out
rather than in:

- `social_wiring.imoveis` is a **cache** by construction (040: "MIRROR of the
  Vista catalog"), and Vista's `/imoveis/listar` returns only ACTIVE listings.
  Measured on prod 2026-08-25 (migration 076's header): the registry holds 3017
  imóveis and **1062 of them — 35% — are no longer in the 2008-row mirror**.
- So `visitas → imoveis` would reject a third of the catalog at INSERT, and the
  third it rejects is the wrong one: an imóvel leaves the catalog when it is
  SOLD, which is exactly the moment its visit history matters most.
- And it would destroy the very history D3 exists to keep. On delist,
  `ON DELETE CASCADE` deletes our visitas; `ON DELETE RESTRICT` breaks the
  nightly sync. Either way the 2024→2028 memory is gone or the product is.

`imovel_registry` (migration 063) is the answer the schema already has: "one row
per código we have EVER seen, from any source. APPEND-ONLY: nothing is ever
deleted. **Everything of ours joins HERE, never to the mirror.**" Migration 076
re-ratified it eleven hours before this contract was written, by moving
`imovel_dados`'s FK off the mirror and onto the registry for these same two
reasons (reachability + durability).

So: **yes to enforced referential integrity — `visitas (org_id, codigo)` →
`imovel_registry (org_id, codigo_canonical)`, `ON DELETE CASCADE`**, copying
`imovel_dados`'s post-076 shape verbatim, down to the composite key and the
service-side `.upper()`. The cascade is a statement about integrity, not a live
deletion path: the registry is append-only.

This is not a weaker FK than the one asked for. It is the only one that keeps
the 2024 row readable in 2028.

**D3 also has three consequences beyond the FK**, because integrity alone is not
memory:
1. **A statistics view ships with the tables** (§2.6). "How many visitas did
   ONE4770 generate, how many happened" must be a SELECT, not an aggregate each
   consumer re-invents.
2. **Every visita outcome writes a cliente timeline entry** (§3.4). The timeline
   is what the card shows and what an agent reads; a status column nobody
   narrates is not a memory.
3. **Roteiros hang off the ATENDIMENTO** (§2.1), so 2024's route stays attached
   to 2024's deal instead of polluting a live negotiation — while still
   appearing on the person's card, because the card is the person.

**Out of scope, needs its own go-ahead:** retrofitting the same registry FK onto
`leads` (11 375 rows, of which 063 measured 7 177 non-resolving) and onto the
campanha/venda tables. 063 already backfilled the registry FROM leads, so the
data is ready — but it is a live-data migration on another agent's active
surface, and it is not this branch's to run. Surface it; do not fold it in.

## 2 · Database — migration `082_roteiros_visitas.sql`

Schema `social_wiring`. Forward-only + idempotent. **MIGRATION FILE ONLY** — not
applied to any DB by this change; applying is `noctus.dev.migrate_product` after
the tech-lead states the row counts and the user gives an explicit go-ahead
(the standard banner 040/075 carry).

Everything through `081` is applied, so this is `082`.

### 2.1 `roteiros`

| column | type | notes |
|---|---|---|
| `id` | UUID PK default `gen_random_uuid()` | |
| `org_id` | UUID NOT NULL | |
| `atendimento_id` | UUID NOT NULL → `atendimentos(id)` ON DELETE CASCADE | |
| `titulo` | TEXT NULL | optional; UI falls back to the creation date |
| `created_at` | TIMESTAMPTZ NOT NULL default `now()` | |
| `deleted_at` | TIMESTAMPTZ NULL | soft delete |

**Whose roteiro is it — the ATENDIMENTO's, not the person's.** This is migration
`061`'s ruling applied unchanged: a person accumulates deals over time (D17) and
a route walked for a 2024 purchase must not pile onto a live negotiation's list.
The card is the person and reads across all of their atendimentos, exactly as it
already does for agendamentos. Deviating here would give the card two different
ownership models for two adjacent tabs — and it is also what makes D3's 2028
question answerable *per deal* rather than as one undifferentiated pile.

**No `data_prevista`, no `criado_por`, no `status`.** None was asked for, and
`061` settled the precedent in this module: "a status field nobody requested is
a field the UI must then explain." The roteiro's state is derivable from its
visitas; a second, hand-maintained copy is how the two drift.

### 2.2 `visitas`

| column | type | notes |
|---|---|---|
| `id` | UUID PK default `gen_random_uuid()` | |
| `org_id` | UUID NOT NULL | |
| `roteiro_id` | UUID NOT NULL → `roteiros(id)` ON DELETE CASCADE | |
| `codigo` | TEXT NOT NULL | **canonical form** (`upper(btrim(...))`); the FK column |
| `ordem` | INTEGER NOT NULL | 0-based visiting order |
| `status` | TEXT NOT NULL default `'pendente'` | CHECK ∈ `pendente` \| `realizada` \| `nao_realizada` |
| `observacao` | TEXT NULL | the corretor's feedback |
| `feedback_em` | TIMESTAMPTZ NULL | stamped when `status` first leaves `pendente` |
| `created_at` | TIMESTAMPTZ NOT NULL default `now()` | |
| `deleted_at` | TIMESTAMPTZ NULL | soft delete |

```sql
CONSTRAINT visitas_registry_fk
    FOREIGN KEY (org_id, codigo)
    REFERENCES social_wiring.imovel_registry (org_id, codigo_canonical)
    ON DELETE CASCADE
```

- **The FK is D3.** Same target, same composite key, same cascade as
  `imovel_dados` after migration 076 — read that header before changing
  anything here.
- `codigo` stores the **already-canonical** spelling and the service applies
  `.upper()` on the way in, exactly as `imovel_dados`'s service does. No
  generated column and no second normalisation: migration 062's
  `upper(btrim(...))` is the one canonical expression in this schema, and
  076 verified that `imovel_registry.codigo_canonical` and `imoveis.codigo` are
  already uppercase everywhere (0 exceptions).
- `ordem` is a plain INTEGER with **no UNIQUE constraint** — same shape as
  `checklists.posicao` in this module. A UNIQUE would force a deferred
  constraint or a two-phase rewrite on every drag. Ties break on `created_at`.
- `status` has three values, not a boolean: "hasn't happened yet" and "didn't
  happen" are different facts and the counters must not merge them. This column
  IS the contabilização the user asked for.

### 2.3 Registry membership — REUSE `ensure_imovel`, do not build an upsert

An earlier draft of this contract had roteiro creation upsert the código into
`imovel_registry` with a new `origem_descoberta='roteiro'` value. **That was
wrong and is withdrawn** — the mechanism already exists and no roteiro ever
discovers a new código:

- `app/modules/imovel_hub/dados_service.ensure_imovel(client, org_id, codigo)`
  is the canonical check. It reads `imovel_registry` (never the mirror) and
  raises `NotFoundError` → **404 "imóvel não encontrado"**, deliberately
  explicitly rather than leaving it to the FK, because a foreign-key violation
  surfaces as a 500 from the driver and 404 is what a caller can act on.
- Migration 076 verified on prod that **every one of the 2008 mirror rows
  already has a registry row (0 missing)**, and the dialog can only pick a
  código the mirror search returned. A picked código is therefore always
  registered.
- So `origem_descoberta` gains **no new value** and the CHECK is **not**
  touched. A código with no registry row is a genuine 404, not something for
  this feature to invent.

Call `ensure_imovel` once per código on `POST /roteiros` and `POST /visitas`,
before insert. That is the whole registry leg.

### 2.4 RLS

Mirror `061` exactly, both tables: `ENABLE ROW LEVEL SECURITY`; `SELECT` for
`authenticated` USING `org_id = public.current_org_id()`; `ALL` for
`service_role`. Never `auth.jwt()` top-level, never `user_metadata`.

### 2.5 Indexes

`(org_id, roteiro_id, ordem)` on visitas · `(org_id, status)` on visitas ·
`(org_id, codigo)` on visitas · `(org_id, atendimento_id)` on roteiros.

### 2.6 `vw_imovel_visita_contagem` — D3's statistics surface

One row per `(org_id, codigo)` that has ever been visited:

```
org_id · codigo · total · realizadas · nao_realizadas · pendentes
       · clientes_distintos · primeira_visita_em · ultima_visita_em
```

`security_invoker = true`, the same posture as `vw_lead_corretor_contagem`
(migration 080) and `vw_nome_conferencia`. Aggregate in the database: 080 exists
because per-row round trips made `GET /api/leads/corretores` the slowest
endpoint the container served (3343ms against a p50 of 6.4ms), and this view is
the same lesson applied before the N+1 is written rather than after.

Excludes soft-deleted visitas and roteiros. Grouped on `codigo`, which is the
registry key — so a sold imóvel keeps its counts forever, which is the point.

## 3 · API — `card_hub`, prefix `/api/clientes/{cliente_id}`

Mounted in the existing `card_hub` router, exactly where agendamentos live and
for the same reason: **the card is the person**, so it reads across all of that
person's atendimentos, while the row itself hangs off one atendimento.

🔴 **Every route proves the row belongs to THIS cliente before touching it** —
an id alone must never be enough to read or edit someone else's roteiro. Copy
`agendamentos_service._obter`'s ownership-proof shape; it IS the authorisation.

```
GET    /roteiros                                   → {items: RoteiroOut[], total}
POST   /roteiros                                   → RoteiroOut          201
PATCH  /roteiros/{roteiro_id}                      → RoteiroOut
DELETE /roteiros/{roteiro_id}                      → 204   (soft)
PUT    /roteiros/{roteiro_id}/ordem                → RoteiroOut
POST   /roteiros/{roteiro_id}/visitas              → VisitaOut           201
PATCH  /roteiros/{roteiro_id}/visitas/{visita_id}  → VisitaOut
DELETE /roteiros/{roteiro_id}/visitas/{visita_id}  → 204   (soft)
GET    /roteiros/{roteiro_id}/pdf                  → application/pdf
```

### 3.1 Bodies (all `StrictHttpModel`, per `KB § PATTERNS/backend/pydantic-strict-http.md`)

```python
class RoteiroCreateBody(StrictHttpModel):
    titulo: Optional[str] = None
    imoveis: list[str] = Field(min_length=1)   # códigos, IN VISITING ORDER
    atendimento_id: Optional[UUID] = None      # required only when ambiguous

class RoteiroPatchBody(StrictHttpModel):
    titulo: Optional[str] = None

class RoteiroOrdemBody(StrictHttpModel):
    visita_ids: list[UUID] = Field(min_length=1)   # the FULL ordered set

class VisitaCreateBody(StrictHttpModel):
    codigo: str = Field(min_length=1)

class VisitaPatchBody(StrictHttpModel):
    status: Optional[str] = None       # pendente | realizada | nao_realizada
    observacao: Optional[str] = None
```

- `POST /roteiros` resolves the atendimento with
  `agendamentos_service.resolve_atendimento_id` — **reuse it, do not re-derive
  it**. It already raises `AmbiguousAtendimento` → **409** when the person has
  more than one open deal, which is the correct answer: guessing files the
  roteiro against the wrong deal.
- `POST /roteiros` and `POST /visitas` canonicalise the código, then upsert it
  into `imovel_registry` (§2.3) before insert.
- `PUT /ordem` takes the **complete** ordered id list and rewrites `ordem` to
  the array index. If the set does not match the roteiro's live visitas exactly
  (missing or foreign id) → **422** naming the offending ids. A partial reorder
  that silently succeeds is a silent error.
- `PATCH /visitas/{id}` stamps `feedback_em = now()` when `status` moves off
  `pendente` and leaves it untouched afterwards. `status` validated against the
  same value set as the DB CHECK — both exist on purpose (schema guards the API,
  CHECK guards every other writer).

### 3.2 Response shapes

```jsonc
// GET /roteiros answers the house envelope `{"items": [...], "total": n}`
// (this router's docstring), NOT a bare array — `useRoteiros` reads `.items`
// exactly as `useAgendamentos` does.
//
// RoteiroOut
{
  "id": "uuid", "atendimento_id": "uuid",
  "titulo": "string|null",
  "created_at": "iso8601",
  "visitas": [ /* VisitaOut, ordered by `ordem` then `created_at` */ ],
  "contagem": { "total": 3, "realizadas": 1, "nao_realizadas": 1, "pendentes": 1 }
}

// VisitaOut
{
  "id": "uuid", "roteiro_id": "uuid",
  "codigo": "ONE9481",
  "ordem": 0,
  "status": "pendente",
  "observacao": "string|null",
  "feedback_em": "iso8601|null",
  "created_at": "iso8601",
  "imovel": {                      // never null — the FK guarantees a registry row
    "codigo": "ONE9481",
    "titulo": "string|null",
    "empreendimento": "string|null",   // ← this is "condomínio"
    "logradouro": "string|null", "numero": "string|null",
    "complemento": "string|null", "bairro": "string|null",
    "cidade": "string|null", "uf": "string|null", "cep": "string|null",
    "foto_destaque": "url|null",
    "captacao": {                      // who brought the property in
      "user_id": "uuid|null",          // imovel_dados.captador_user_id (canonical)
      "nome": "string|null"            // resolved via the team surface
    },
    "corretores": [ { "nome": "string", "email": "string|null" } ],
    "ativo_no_vista": true,
    "fonte": "imoveis" | "registry"
  }
}
```

**Enrichment — registry-anchored, mirror-preferred.** D3 changes this from a
fallback chain into a join with a preference:
1. The registry row **always exists** (the FK guarantees it), so `imovel` is
   never `null`. `ativo_no_vista` comes from it, and it is real information —
   "this property has left the catalog" is exactly what a corretor needs to know
   before knocking on the door.
2. When the mirror has the código (`imoveis` on `(org_id, codigo_norm)`), read
   the display fields from it → `fonte: "imoveis"`.
3. Otherwise read the registry's `snap_*` columns → `fonte: "registry"`
   (no `logradouro`/`corretores` there; emit `null`/`[]`).
4. `captacao.user_id` reads `imovel_dados.captador_user_id` (migration 075) —
   **the canonical model for "corretor responsável pela captação"**, deliberately
   a user id and not a name, because the commission slice is attributed to it and
   two spellings of a free-text name become two people. `nome` is resolved from
   the team surface. NULL there is the honest state, never silently reassigned.
5. **Never** fall back to a live Vista call — roadmap
   `social-wiring-imoveis-vista-2026-08` P2.5 is explicit that a clean miss is a
   real, actionable fact.

Enrich the whole page in **one batched `in_` query per source** (registry,
mirror, `imovel_dados`), never one query per visita.

### 3.3 The PDF

`GET /roteiros/{id}/pdf` → `application/pdf`,
`Content-Disposition: attachment; filename="roteiro-<first-8-of-id>.pdf"`.

- A4 portrait, **one visita per page**, in `ordem`. Empty roteiro → 422 (there
  is nothing to print, and a zero-page PDF is a broken file, not an empty state).
- Per page: `Imóvel N de M` · the código, large · **Condomínio**
  (`empreendimento`) · **Endereço** (logradouro, número, complemento, bairro,
  cidade/UF, CEP) · **Captação** — `captacao.nome` when `imovel_dados` names a
  captador, else every `corretores[].nome` joined by ` · ` (13.1% of the catalog
  carries 2–3, and a first-only read discards the rest), else `—` ·
  **Proprietário: —** / **Celular: —** (D1; marker required).
- **No photo in the PDF.** The user listed exactly four data points and a photo
  is not among them; fetching remote images server-side would add a failure mode
  the feature does not need.
- Header on every page: the roteiro's `titulo` (or its creation date) + the
  cliente's name.

### 3.4 Timeline — a GATHERER, not a log

🔴 The card timeline is **derived, not written**. `timeline_service.py` has no
insert path: `_ALL_KINDS` names six kinds and `_GATHERERS` maps each to a
function that reads existing rows and synthesises entries on the fly
(`_gather_sistema` derives "criado"/"arquivado"/"merged" straight off
`clientes` and `cliente_merges`). Adding a write-side event log here would be a
fork of the module's whole design.

So: add a `"visita"` kind to `_ALL_KINDS` and a `_gather_visitas` to
`_GATHERERS`, reading this person's visitas across their atendimentos and
emitting, in the module's existing entry shape
(`{id, kind, ocorrido_em, ator, payload:{evento, detalhe}}`):

| when | `ocorrido_em` | `evento` | `detalhe` |
|---|---|---|---|
| roteiro created | `roteiros.created_at` | `roteiro_criado` | `"N imóveis"` |
| visita marked realizada | `visitas.feedback_em` | `visita_realizada` | `codigo` + `observacao` |
| visita marked não realizada | `visitas.feedback_em` | `visita_nao_realizada` | `codigo` + `observacao` |

`feedback_em` is the honest timestamp and it is exactly why the column exists —
follow `_gather_sistema`'s ruling on "restored": an event with no honestly
derivable timestamp is omitted, never stamped with `now()`. A `pendente` visita
therefore produces no entry, which is correct: nothing has happened yet.

This gatherer IS D3's memory leg. It is what answers "what happened with this
cliente in 2024" in 2028 — the statistics view answers the other half.
