# lead-card-hub Phase 1 — the person layer · PROJECT

> **Parent roadmap:** `project-history/roadmaps/lead-card-hub-2026-08.md` (D1–D17 ratified
> 2026-08-07). Phase 0 shipped 2026-08-08 (`clients` → `marcas`, 73 files, AST-first).
> **Trigger T1 fired 2026-08-13** — `clientes` is free, user said continue.
> **Status:** ⏳ contract authored → dispatched.

Phase 1 is the foundation. Phases 2, 2b, 3, 4 and 5 all attach to `clientes`, so a
shape mistake here is paid for five times.

---

## 1 · Live measurements (2026-08-13, re-measured — do NOT trust the roadmap's 08-07 figures)

The roadmap's numbers were taken six days ago and the table has grown. Re-measured
against the live DB today:

| Measure | Roadmap 08-07 | **Live 08-13** |
|---|---|---|
| `leads` rows | 13 245 | **13 330** |
| distinct `contato_norm` (≈ people) | ~9 270 | **9 320** |
| groups with a repeated key | 2 101 | **2 113** |
| — identical name after normalisation | — | **1 413** |
| — prefix-compatible (`"Maria Silva"` / `"Maria"`) | — | **389** |
| — same first name, otherwise different | — | **31** |
| — two genuinely different names | — | **212** |
| — three or more distinct names | — | **68** |
| — group containing a nameless row | 7 | **13** |
| `negociacoes_venda` | — | **1 365** (1 154 via `lead_id`, 211 via `meta_ads_lead_id`) |
| `meta_ads_leads` | — | **1 152** |
| `lead_corretores` | 28 | **28** |
| `pipeline_movimentos` | — | **26** |

**Reconciliation note.** A first pass using strict exact-match name equality produced
717 "conflicts" — 3× the roadmap's 223 — which looked like the design had shifted
under us. It had not: the roadmap's predicate was unaccent + prefix-compatible, and
the strict test was simply the wrong test. Recorded because the scare is instructive —
**the auto-merge/review split is a property of the PREDICATE, not of the data**, and it
swings by 3× between two defensible definitions of "compatible". §3 therefore fixes
the predicate in writing rather than leaving it to the implementer.

## 2 · 🔴 The 399 the roadmap never accounted for

**399 `leads` rows have `contato_norm IS NULL`** — no phone, no email. They cannot be
identity-resolved by any predicate, because there is no key to resolve on. The roadmap's
D2/D3 cover match-safety in detail and are silent on these.

They are real leads and must not vanish from the board. **Disposition (decided here):**

- Each keyless lead becomes **its own `cliente`**, with `chave_canonica IS NULL`. One
  cliente per lead — no grouping is possible or attempted.
- They are flagged `identidade_incerta = true`, so the UI can distinguish "this is one
  person we are sure about" from "this is a row we could not key".
- They are **never auto-merged into anything**, in either direction. A null key must
  never compare equal to another null key.
- They stay fully visible on the board. Hiding them would silently drop 3 % of the
  lead base, which is exactly the kind of quiet loss P1.2's losslessness rule exists
  to prevent.

## 3 · The auto-merge predicate — fixed here, not left to the implementer

Two `leads` rows are the **same person** iff their `contato_norm` is equal AND non-null,
AND their names are compatible. Name compatibility, evaluated on
`lower(unaccent(trim(collapse_whitespace(cliente_nome))))`:

| # | Case | Verdict | Live count |
|---|---|---|---|
| C1 | all names in the group identical | **auto-merge** | 1 413 |
| C2 | exactly two distinct, one a prefix of the other | **auto-merge** | 389 |
| C3 | some rows nameless, the named ones satisfy C1/C2 | **auto-merge**, adopt the longest name | 13 |
| C4 | same first name, diverging afterwards | **review queue** | 31 |
| C5 | two genuinely different names | **review queue** | 212 |
| C6 | three or more distinct names | **review queue** | 68 |

⇒ **~1 815 auto-merged · ~311 to review.** These are the numbers the checkpoint is
measured against; report actuals, and if they differ by more than ~5 % **stop and
surface** rather than proceeding — a large divergence means the predicate is not doing
what this table says.

🔴 **C5 is not paranoia.** The 08-07 census found `+5511974781330` resolving to two
genuinely distinct people — a shared phone (a couple, a household, an office line).
Blind phone-merge would have fused two strangers into one card. That single case is
why C4–C6 exist.

## 4 · Schema (P1.1 – P1.4)

Migration `048_clientes_person_layer.sql`. **Forward-only, idempotent.** File only —
🔴 **do NOT apply it.** See §7.

### `clientes`
- `id`, `org_id`, `nome`, `chave_canonica` (E.164 phone or lowercased email, **nullable** per §2)
- `chave_tipo` (`telefone` | `email` | `null`)
- `identidade_incerta boolean NOT NULL DEFAULT false` (§2)
- `ativo boolean NOT NULL DEFAULT true`, `inativo_em timestamptz`, `arquivado_em timestamptz`
- `primeiro_contato_em`, `ultimo_contato_em` — derived from touches, maintained on write
- `UNIQUE (org_id, chave_canonica)` — **partial**, `WHERE chave_canonica IS NOT NULL`.
  🔴 A plain UNIQUE would be satisfied by all 399 nulls (SQL nulls never collide), which
  looks correct and silently permits a second keyed duplicate later. Say so in the header.
- RLS mirroring `025_leads.sql`: authenticated SELECT via `public.current_org_id()`
  (SECURITY DEFINER — **never** `auth.jwt()` top-level or `user_metadata`), service_role ALL.

### `cliente_touches` (P1.2 — lossless)
One row per source row. **No source row is modified or deleted by this migration.**
- `cliente_id`, `org_id`, `origem_tabela` (`leads` | `meta_ads_leads`), `origem_id`
- `ocorreu_em`, plus the denormalised bits the timeline needs
- `UNIQUE (origem_tabela, origem_id)` — re-running the backfill must never double-count.
- Verification is arithmetic, not vibes: `count(cliente_touches) == 13 330 + 1 152 = 14 482`.
  Assert it in a test.

### `cliente_merges` (P1.3 — D3, undoable)
- `cliente_id_sobrevivente`, `cliente_id_absorvido`, `motivo` (`C1`…`C6`), `automatico bool`,
  `desfeito_em`, plus enough of the absorbed row to rebuild it.
- **A merge must be reversible from this table alone.** If splitting back needs data this
  table does not hold, the table is wrong — that is D3's whole point.

### `negociacoes_venda` (P1.4)
- Add `cliente_id UUID REFERENCES clientes(id)`; backfill from `lead_id` (1 154) and
  `meta_ads_lead_id` (211) via the touch mapping.
- **Retire `exactly_one_origin`.** Keep `lead_id` / `meta_ads_lead_id` columns —
  dropping them is lossy and not required by anything in Phase 1.
- **One-to-many from the start (D17):** a cliente holds many negociações; closed ones
  stay as history. Do not build a one-to-one and widen it later.
- After backfill, assert **zero** `negociacoes_venda` rows with a NULL `cliente_id`.

### Lifecycle (P1.5)
180 days of silence ⇒ inactive (**D16**), configurable in the UI — so the threshold is a
**stored setting, not a constant**. Archive + manual restore (**D4**), full history
preserved on return. Board shows active only; inactive reachable and restorable.

## 5 · API contract (both sides build to THIS)

Base `/api/clientes`. `org_id` from auth context, never a client parameter. Auth
boundary asserts strict `== 401`.

| Route | Purpose |
|---|---|
| `GET /api/clientes` | board list; `?ativo=`, `?q=`, `?corretor_id=`, pagination. Default **active only** (D4) |
| `GET /api/clientes/{id}` | one person + negociações (active **and** closed, D17) + touch count |
| `GET /api/clientes/{id}/touches` | the timeline feed, chronological, paginated |
| `PATCH /api/clientes/{id}` | nome, ativo/arquivado (manual restore, D4) |
| `GET /api/clientes/revisao` | **the review queue** — the ~311 C4–C6 groups, each with its candidate rows and the reason code |
| `POST /api/clientes/revisao/{grupo}/merge` | operator confirms a merge; writes `cliente_merges` |
| `POST /api/clientes/revisao/{grupo}/manter-separados` | operator rejects; the group must **not** resurface |
| `POST /api/clientes/merges/{id}/desfazer` | undo (D3) |

`GET /api/clientes/revisao` returning an empty list on day one would be a bug — there are
~311 groups waiting. A test should assert it is non-empty against a seeded fixture.

## 6 · Slices

| Slice | Owner | Files |
|---|---|---|
| **A** migration `048` + resolution engine + backfill + tests | backend-engineer | `backend/migrations/048_*.sql`, `backend/app/services/clientes_service.py`, `.../identidade_service.py`, `backend/tests/**` |
| **B** routers (§5) + lifecycle setting + tests | backend-engineer | `backend/app/routers/clientes_router.py`, `backend/app/main.py`, `backend/tests/routers/**` |
| **C** review-queue UI + board switch to clientes | frontend-engineer | `frontend/src/pages/`, `frontend/src/hooks/`, `frontend/src/components/clientes/**` |

A and B share `clientes_service.py`'s interface only — B builds to §5, A to §3/§4.

## 7 · 🔴 Applying this is a separate, human decision

Every migration applied so far this program (`040`, `043`, `047`) was **additive** — new
tables, or a view replacement. No existing row was read or written.

`048` is not. It rewrites `negociacoes_venda`'s origin model across 1 365 rows, retires a
CHECK constraint, and derives ~9 320 people from 13 330 leads — **against the single live
Supabase project**, while WhatsApp intake keeps writing to `leads`. There is no dev
database (2026-05-23 decision, re-confirmed 2026-08-03: the Supabase free tier's
2-active-project cap means dev runs against the production project).

Therefore:
- The engineer **writes and tests** `048`. The engineer does **not** apply it.
- Before it is applied, the tech-lead states the row counts it will touch and gets an
  explicit decision from the user.
- The backfill must be **idempotent and re-runnable**, and there must be a documented
  reversal for the `negociacoes_venda` change specifically — `cliente_merges` covers the
  merges, not the repoint.
- Concurrency: intake writes to `leads` during the backfill. A lead arriving mid-run must
  not be silently skipped. Either handle it, or make the backfill re-runnable such that a
  second pass picks up stragglers — and say which.

## 8 · Checkpoint

The board shows one card per human; nothing is lost (`14 482` touches, zero orphaned
negociações); the review queue is walkable and non-empty; a merge can be undone; the 399
keyless leads are visible and flagged.
