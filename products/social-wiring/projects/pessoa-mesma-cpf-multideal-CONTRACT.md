# Contract — mesma pessoa em múltiplos negócios (CPF), `/api/clientes`

**Owner request (2026-09-28).** The same real person shows up as more than
one `clientes` row because two independent card_hub deals each minted their
own party record for them — prod evidence (P2 test cards): the sellers of
card 890 are the buyers of card 893, and the sellers of 882 are the buyers
of 881 (identical uploaded documents, by hash). One person, two rows, both
now carrying the same extracted CPF.

Backend-owned. This doc pins the contract BEFORE the frontend engineer
builds the UI against it — per `noc-contract-first`. Backend implementation:
`app/services/identidade_service.py` (CPF pure logic), `app/services/
clientes_service.py` (`list_cpf_review_groups`, `_repoint_cliente_scoped_
tables`, `negociacoes_do_cliente`), `app/routers/clientes_router.py`.
Migration: `migrations/174_cliente_revisao_cpf.sql` (file only — not
applied; tech-lead applies after the user states row counts).

## 0 — Existing mechanism this extends (read before touching either axis)

`identidade_service`'s review groups already decide when two `clientes`
rows are the SAME person, with a human-confirm review page (`/clientes/
revisao`, `cliente_revisao_rejeitadas` — migration 050). That existing
axis clusters `identidade_incerta` LEADS by `cliente_touches.chave_canonica`
(phone/email) — it can never see a card_hub deal party, which is created
directly (migration 073/098), is never `identidade_incerta`, and has no
`cliente_touches` row.

**The existing review policy, stated explicitly (per the brief's ask):**
`POST /revisao/{grupo}/merge` is a **full merge**, not a link — it deletes
the absorbed `clientes` row after moving its `cliente_touches` to the
survivor (`clientes_service.merge_clientes`). There is no separate
"canonical-person link" outcome in this codebase; confirming same-person
has only ever meant one row survives. This CPF axis reuses that exact
same outcome (`merge_clientes`), not a new link concept, and the SAME
`cliente_revisao_rejeitadas` reject table + router pagination shape —
migration 174 widens `cliente_revisao_rejeitadas.motivo`'s CHECK (and,
for the same reason, `cliente_merges.motivo`'s) to also accept `'CPF'`.

**Why reusing `merge_clientes` needed a fix, not just a call site.**
`merge_clientes` used to delete the absorbed row having repointed
*only* `cliente_touches`. Every table that FKs `clientes(id) ON DELETE
CASCADE` — `atendimento_partes`, `atendimentos.cliente_id`,
`cliente_documentos`, notes, tags, checklists — would have been silently
erased by the CASCADE. That was safe for the lead-identity axis (a fresh,
`identidade_incerta` lead has none of that yet) and NOT safe for a
card_hub deal party, which routinely does. `_repoint_cliente_scoped_tables`
(in `clientes_service.py`, called from `merge_clientes` before the delete)
fixes this for BOTH axes — `cliente_documentos` is never dropped (LGPD
retention); every other table de-dupes on its own real uniqueness
constraint, never on `cliente_id` alone, so a genuine duplicate fact
collapses instead of raising mid-merge.

**Detection is a live query, not a batch job.** `list_cpf_review_groups`
scans `clientes.cpf` fresh on every call — there is no cache table and no
backfill to run. A CPF written by `identidade_extracao_service` is visible
on the very next `GET /revisao-cpf`. Existing rows are covered by the same
query (no migration-time data rewrite needed).

## 1 — Detection + review queue (independent CPF axis)

`clientes.cpf` (extracted OR operator-confirmed — migration 097 stores
both under the one column, with separate `_origem`/`_confirmado_por`
provenance) is normalized (`identidade_service.normalizar_cpf`: punctuation
stripped, must be exactly 11 digits, check-digits must be valid — an
`"11111111111"`-shaped fake fails too) and grouped. `ativo` and
`identidade_incerta` are irrelevant to this axis.

### `GET /api/clientes/revisao-cpf`
- Auth: `Depends(get_current_user_org)` (same as every `/api/clientes` route).
- Query: `page` (default 1), `page_size` (default 12, max 100).
- Response (200): `{items: [...], total: int, page: int, pages: int}` — the
  house `PageOut` envelope, identical shape to `GET /revisao`.
- Each `items[]` entry: `{chave_canonica: <normalized 11-digit CPF>,
  motivo: "CPF", candidatos: [{id, org_id, nome, cpf, ...all clientes
  columns}, ...]}`.
- A previously-`manter-separados`'d group is excluded before pagination
  (same discipline as `GET /revisao`: filter-then-paginate, never the
  reverse).

### `POST /api/clientes/revisao-cpf/{grupo}/merge`
- `{grupo}` = the normalized CPF string from `chave_canonica` above.
- Request: `{cliente_id_sobrevivente: <uuid>}` (`StrictHttpModel`,
  `extra="forbid"`).
- Side effects / state after: every OTHER candidate in the group is folded
  into the survivor via `clientes_service.merge_clientes` — one call per
  candidate. After this call: the absorbed clientes row(s) no longer exist;
  every `atendimento_partes` row, every `atendimentos.cliente_id` titular
  pointer, every `cliente_documentos`/note/tag/checklist row that pointed
  at an absorbed cliente now points at the survivor (or, on a genuine
  duplicate-fact collision, was safely collapsed — see §0); `GET
  /revisao-cpf` no longer lists this group.
- Response (200): `{cliente_id: <survivor uuid>, merged_ids: [...],
  merge_ids: [...]}` — identical shape to `POST /revisao/{grupo}/merge`.
- Errors: `404` — unknown `{grupo}`, or `cliente_id_sobrevivente` not a
  member of the group. `401` — no/invalid auth (strict `== 401`).
- Strictness: unknown body fields are rejected (422), never silently
  dropped.

### `POST /api/clientes/revisao-cpf/{grupo}/manter-separados`
- No request body.
- Side effect / state after: durable rejection — a row in
  `cliente_revisao_rejeitadas` (`motivo='CPF'`). Idempotent: rejecting an
  already-rejected group is a no-op, not a second row or an error. After
  this call, `GET /revisao-cpf` never resurfaces this `{grupo}` again.
- Response (200): `{cpf_normalizado: <the grupo string>, rejeitado: true}`.
- Errors: `404` — unknown `{grupo}`. `401` — strict.

## 2/3 — Multi-deal read for the UI

### `GET /api/clientes/{cliente_id}/negociacoes`
Additive — does **not** change `GET /api/clientes/{cliente_id}`'s existing
`atendimentos` field (which only ever covered the buyer-side titular
relationship and predates card_hub's multi-party model).

- Response (200):
  ```json
  {
    "cliente_id": "<uuid>",
    "negociacoes": [
      {
        "atendimento_id": "<uuid>",
        "titulo": "string | null",
        "status": "string | null",
        "etapa_id": "<uuid> | null",
        "etapa_label": "string | null",
        "pipeline": "string | null",
        "imovel_codigo": "string | null",
        "lado": "comprador | vendedor",
        "papel": "titular | proprietario | conjuge | procurador | comprador | ..."
      }
    ],
    "total_negociacoes": 2,
    "candidatos_pendentes": [
      {
        "cpf_normalizado": "<11 digits>",
        "candidatos": [{"id": "<uuid>", "nome": "string | null", "cpf": "string | null"}]
      }
    ]
  }
  ```
- `negociacoes` covers EVERY atendimento this cliente is attached to: as
  the buyer-side titular (`atendimentos.cliente_id` — synthetic
  `lado="comprador"`, `papel="titular"`, since there is no
  `atendimento_partes` row for the titular by design) AND as any party
  (`atendimento_partes` — co-buyer, spouse, seller side; real `lado`/
  `papel` from that row).
- `total_negociacoes` = `len(negociacoes)`, including the caller's OWN
  current card if rendering one — this route has no notion of "current
  card". **The FE computes "N OTHER deals" by excluding its own
  `atendimento_id` from the list client-side** (there is no
  `excluir_atendimento_id` query param).
- `candidatos_pendentes` — every NOT-YET-rejected CPF group this cliente
  is a member of (same exclusion rule as `GET /revisao-cpf`). Empty list
  when there is nothing pending — never omitted, never `null`.
- Errors: `404` — unknown `cliente_id`. `401` — strict.

## 4 — Tests (backend, `products/social-wiring/backend/`)

- `tests/services/test_identidade_service.py::TestNormalizarCpf` (8 cases) —
  punctuation, two formattings of one CPF normalize identically, wrong
  check-digits, all-repeated-digits, wrong length, `None`/empty, garbage.
- `tests/services/test_clientes_service.py::TestCpfReviewGroups` (5 cases)
  + `TestChainedDealSamePersonByCpf` (3 cases) — the owner's exact chained-
  deal shape: seller of card A + buyer of card B share a CPF → surfaces as
  one candidate group; after `merge_clientes`, the survivor's
  `negociacoes_do_cliente` shows BOTH deals with the correct `lado`/`papel`
  and the absorbed row's `atendimentos.cliente_id` pointer was actually
  repointed (not left dangling); the candidate no longer surfaces
  afterward.
- `tests/routers/test_clientes_router.py::TestRevisaoCpf` (4) +
  `TestMergeGrupoCpf` (3) + `TestNegociacoesRoute` (3) — the same shapes
  through the HTTP layer, plus 404s. Strict `== 401` on all four new routes
  is covered by the file's existing route-enumerating
  `test_every_clientes_route_requires_auth` (walks every mounted
  `/api/clientes` route — no route was hand-listed and none needed to be).

## Out of scope (deliberately)

- `identidade_extracao_service` / `contrato_gerador`'s `nome_oficial`
  selection for married people — a parallel engineer's territory; not
  touched by this slice.
- `cliente_vinculo` (migration 074, `vinculado_a_cliente_id`) — a
  RELATED-different-people link, not a merge key; untouched.
- A UNIQUE constraint on `clientes.cpf` — migration 097's header already
  rules this out (breaks the XLSX bulk importer + the existing
  merge-after-the-fact flow); not revisited here.
