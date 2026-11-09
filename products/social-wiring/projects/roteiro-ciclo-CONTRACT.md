# Roteiro lifecycle — FE↔BE contract (social-wiring) — v1.2

Owner decisions (2026-11-09, verbatim quotes in `~/.noctusai/private/julia/BRIEF-ad-lead-intake-2026-11-09.md`):
- "let's make every edit to the roteiro save it, so drafted status is automatic and auto saves in case they wanna leave
  and comeback later, until it's generated. then it can't remove/add imoveis, only edit for time changes, cancelations,
  observations and other data related to the roteiro de visitas and the visitas themselves."
- The data tracks how many visits each lead has consolidated or lost, how many visits each property has received or
  lost, and broker performance.
- Reagendada is NEUTRAL. The new date goes in a NEW roteiro.
- Reopen: a new SUPERVISOR role ("give Cindy that role"), plus owners and admins. Allowed only while no visit has an
  outcome.
- "gerar pdf only render on the generated roteiro ui, never rendered on draft not-generated roteiro. so we gate the pdf
  generation to only be triggered for generated roteiros". The server refuses too.

Mockup (approved, round 2): `02-roteiro-ciclo-de-vida.html`. State matrix: NOTES.md §2.
Today's code: `card_hub/router.py:456-653`, `card_hub/roteiros_router.py`, `roteiros_service.py`, migrations 082/184/219.

Access tier for every route below: **`org`** (`get_current_user_org`, scoped to org and cliente). The role checks are
named per route. Each route gets an `@access_tier("org", ...)` marker; none exist today.

---

## 1. Data (migration **338**, social_wiring)

**`roteiros`** (add):
- `status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho','gerado'))`
- `gerado_em timestamptz`, `gerado_por uuid`
- `reaberto_em timestamptz`, `reaberto_por uuid`
- `criado_por uuid`
- `updated_at timestamptz NOT NULL DEFAULT now()` (+ trigger)
- `data_visita` stays nullable in the DB. It is REQUIRED only to gerar (it already is nullable).
- Backfill: every existing row → `status='gerado'`, `gerado_em=created_at`. Those roteiros were consolidated on
  creation.

**`visitas`**:
- `status` CHECK → `('pendente','realizada','cancelada','nao_compareceu','reagendada')`.
- `cancelada_por TEXT CHECK (cancelada_por IN ('cliente','proprietario','corretor'))`.
- `cancelada_motivo TEXT CHECK (cancelada_motivo IN ('cliente_desistiu','imovel_indisponivel','outro'))`.
- `reagendada_para_visita_id uuid NULL REFERENCES visitas(id)`.
- `resultado_em timestamptz` and `resultado_por uuid`: when the outcome was recorded, and by whom.
- `horario TIME NULL` (v1.1): the visit's own time of day.
- New-row rule: `status='cancelada'` ⇒ `cancelada_por` and `cancelada_motivo` NOT NULL. Implement it as a CHECK added
  `NOT VALID` AFTER the backfill, so legacy rows stand and every new or updated row is checked.
- Backfill from today's `nao_realizada` + `nao_realizada_motivo`:
  - `cliente_nao_compareceu` → `nao_compareceu`
  - `reagendada` → `reagendada`
  - `cliente_desistiu` / `imovel_indisponivel` / `outro` → `cancelada` with the same `cancelada_motivo` and
    `cancelada_por` NULL (legacy)
  - `nao_realizada` with motivo NULL → `cancelada`, motivo `outro`
- `nao_realizada_motivo` becomes VESTIGIAL. Keep the column (read-only, legacy). Nothing writes to it after this
  change. Name it in the migration comment.

**Supervisor role**:
- Table `social_wiring.usuario_papeis (org_id uuid, user_id uuid, papel text CHECK (papel IN ('supervisor')),
  concedido_por uuid, concedido_em timestamptz, PRIMARY KEY (org_id, user_id, papel))`. Tier `org`; RLS: org
  SELECT, writes via the service client only.
- SEED-FIRST: before creating it, the BE engineer checks whether the seed or core already has a per-product role
  mechanism, and consumes that one if it exists.
- Helper `pode_supervisionar_roteiros(user, org) = org role ∈ {owner, admin} OR papel 'supervisor'`.
- Post-deploy SQL (owner-run, NOT in the migration): grant `supervisor` to Cindy Kumagai in the One org.

**`roteiro_eventos`** (v1.2 — owner: "visitas should be objects in the db and have their own tables so we can track all of them
and generate data for metrics and performance analysis ... everything inside our products must be measured"): the
APPEND-ONLY ledger of the lifecycle. Columns `id, org_id, roteiro_id, visita_id NULL, tipo, de, para, dados jsonb, ator_id NULL,
criado_em default now()`; indexes `(org_id, roteiro_id, criado_em)` and `(org_id, tipo, criado_em)`. `tipo` ∈ `roteiro_criado |
roteiro_gerado | roteiro_reaberto | roteiro_excluido | visita_adicionada | visita_removida | visita_reordenada | visita_resultado
(de/para = status, dados = cancelada_por/motivo) | visita_horario | visita_reagendada (dados = nova_visita_id/novo_roteiro_id) |
data_alterada`. No UPDATE/DELETE for anyone (no grant, service_role included: SELECT + INSERT only, plus a refusing trigger); no
FK (events outlive their roteiro). Tier `org`, service-only like every table since 328/330 (read through the API); NO route in this
slice — a timeline endpoint can come later. Backfill: one `roteiro_criado` + one `roteiro_gerado` per existing roteiro (at
created_at) and one `visita_resultado` per visita that already has an outcome (at feedback_em/realizada_em), all with
`dados.origem = 'backfill'`. `roteiros.atualizado_por` / `visitas.atualizado_por` (uuid) carry the actor of every write.

**`cliente_imovel_interesses.origem`** CHECK: add `'julia'` (F4). The `roteiro` origem already exists.

## 2. Shapes

`Roteiro` (bare object; every roteiro route returns it unless stated otherwise):

```
{ id, atendimento_id, titulo, data_visita (YYYY-MM-DD|null), hora_visita (HH:MM|null), created_at, updated_at,
  status: "rascunho"|"gerado", gerado_em, gerado_por, reaberto_em, reaberto_por, criado_por,
  gerado_por_nome: string|null, reaberto_por_nome: string|null /* v1.1: joined server-side from noctus_users */,
  feedback_status, feedback_em,
  visitas: Visita[] (ordered by ordem),
  contagem: { total, pendentes, realizadas, canceladas, nao_compareceu, reagendadas,
              consolidadas /* = realizadas */, perdidas /* = canceladas + nao_compareceu */,
              neutras /* = reagendadas + pendentes */ },
  permissoes: { editar_imoveis: bool, gerar: bool, motivo_gerar: string|null,
                baixar_pdf: bool, reabrir: bool, motivo_reabrir: string|null } }
```

- `permissoes` is computed by the SERVER for the calling user. The FE renders from it and never re-derives the rules.
- `motivo_*` is pt-BR copy, e.g.:
  - "Adicione ao menos um imóvel."
  - "Informe a data da visita."
  - "Já tem 2 resultados registrados."
  - "Só supervisores, administradores e o proprietário da conta podem reabrir."

`Visita`: today's fields (`id, roteiro_id, codigo, ordem, status, observacao, feedback_em, created_at, realizada_em,
proposta_*`, `imovel`) + `cancelada_por, cancelada_motivo, reagendada_para_visita_id, resultado_em, resultado_por`
+ `horario` ("HH:MM"|null, v1.1). `hora_visita` and `horario` are returned as "HH:MM".
`nao_realizada_motivo` is removed from the response.

`contagem` replaces today's `{total, realizadas, nao_realizadas, pendentes}`. `nao_realizadas` is removed. The FE
moves to the new keys in the same release.

## 3. Endpoints (prefix `/api/clientes/{cliente_id}/roteiros`)

| # | Method + path | Request | Success | Errors |
|---|---|---|---|---|
| R1 | GET `` | – | `{items: Roteiro[], total}` (drafts included) | 404 cliente |
| R2 | POST `` | `{titulo?, data_visita?, hora_visita?, atendimento_id?, imoveis?: str[] (0–50)}` | 201 Roteiro, **status `rascunho`**. **No funnel move** (it moves on gerar). `funil` is no longer returned here. | 409 `AmbiguousAtendimento`; 404 unknown código; 422 shape |
| R3 | PATCH `/{rid}` | `{titulo?, data_visita?, hora_visita?}` | Roteiro | allowed in BOTH statuses; 422 `data_visita` null on a gerado |
| R4 | DELETE `/{rid}` | – | 204 | 409 `roteiro_gerado_com_resultados` if gerado and any visita ≠ pendente |
| R5 | PUT `/{rid}/ordem` | `{visita_ids: uuid[]}` | Roteiro | **409 `roteiro_gerado`** when gerado; 400 set mismatch |
| R6 | POST `/{rid}/visitas` | `{codigo}` | 201 full **Roteiro** (v1.1) | **409 `roteiro_gerado`** |
| R7 | DELETE `/{rid}/visitas/{vid}` | – | **200** full **Roteiro** (v1.1) | **409 `roteiro_gerado`** |
| R8 | **POST `/{rid}/gerar`** | – | Roteiro (`status:"gerado"`) | 409 `roteiro_ja_gerado`; 422 `roteiro_sem_imoveis` ("Adicione ao menos um imóvel."); 422 `roteiro_sem_data` ("Informe a data da visita.") |
| R9 | **POST `/{rid}/reabrir`** | – | Roteiro (`status:"rascunho"`) | 403 `sem_permissao_reabrir`; 409 `roteiro_nao_gerado`; 409 `roteiro_com_resultados` (`{quantidade}`) |
| R10 | GET `/{rid}/pdf` | – | `application/pdf` (unchanged) | **409 `roteiro_rascunho`**: `"Este roteiro ainda é um rascunho. Gere o roteiro para baixar o PDF."` |
| R11 | PATCH `/{rid}/visitas/{vid}` | `{status?, observacao?, cancelada_por?, cancelada_motivo?, horario?}` (`horario` in BOTH statuses) | full **Roteiro** (v1.1) | 409 `roteiro_rascunho` when setting a status ≠ pendente on a draft (observacao is allowed on a draft); 422 `cancelada_incompleta` (cancelada needs `cancelada_por` + `cancelada_motivo`); 422 for `status:"reagendada"` here (use R12) |
| R12 | **POST `/{rid}/visitas/{vid}/reagendar`** | `{data_visita?, hora_visita?}` | 201 `{visita: Visita, novo_roteiro: Roteiro}` | 409 `roteiro_rascunho`; 409 `visita_ja_tem_resultado` if status ∉ {pendente} |
| R13 | PATCH `/{rid}/visitas/{vid}/proposta` | unchanged | unchanged | 409 `roteiro_rascunho` (a proposta needs a visited, gerado roteiro) |
| R14 | POST `/{rid}/feedback` | today's body + per visita an optional `resultado` ∈ {realizada, cancelada, nao_compareceu, reagendada}, `cancelada_por?`, `cancelada_motivo?` | Roteiro | 409 `roteiro_rascunho`. Legacy `realizada:false`+`motivo` still accepted, mapped as in the backfill (new rows have no legacy cancelada; a legacy `cancelada` with no `cancelada_por` → 422 `cancelada_incompleta`) |

| R15 | GET `/api/metricas/atendimentos` (v1.1) | `de?, ate?, corretor_id?` | the funnel; `visitas_nao_realizadas` is REPLACED by `visitas_consolidadas, visitas_perdidas, visitas_neutras, visitas_canceladas, visitas_nao_compareceu, visitas_reagendadas`; every other key unchanged (`visitas_agendadas` = visitas of gerado roteiros; `visitas_realizadas` = consolidadas); drafts excluded | – |

No bulk "cancelar pendentes" route in this slice (v1.1).

Error envelope (v1.1, THESE routes only): an `HTTPException` whose detail is the seed's flat shape, so the body is
`{"detail": <pt-BR message>, "code": <code>, "message": <pt-BR message>, "details"?: {...}}`. (A bare
`detail={"code","message"}` is NOT passed through by the seed's `http_exception_handler` — it is stringified into
`HTTP_ERROR`; the handler passes through only a dict carrying both `detail` and `code`.) `ApiError.code` reads `code`; the FE
shows `message`; `details` carries e.g. `{quantidade}`. Pydantic 422s keep the seed's validation envelope.

## 4. Side-effects and state after

- **R2:** the row exists as `rascunho`. Nothing is linked to the lead and no funnel move happens. `criado_por` = the
  caller.
- **Events (v1.2).** Every write of R2–R14 produces its event(s) IN THE SAME TRANSACTION as the change: they are written by
  AFTER triggers on `roteiros` / `visitas`, so the change and its event are one statement — a failed event write fails the
  request and no code path can skip it. The actor is read from the row (`criado_por`, `gerado_por`, `reaberto_por`,
  `resultado_por`, else `atualizado_por`, which every route stamps). A write that changes nothing (the autosave touching
  `updated_at`) writes no event. Events per route: R2 `roteiro_criado` + `visita_adicionada` per imóvel; R3 `data_alterada`
  (date or time); R4 `roteiro_excluido`; R5 `visita_reordenada` per visita that moved; R6 `visita_adicionada`; R7
  `visita_removida`; R8 `roteiro_gerado`; R9 `roteiro_reaberto`; R11 `visita_resultado` / `visita_horario`; R12
  `visita_resultado` + `visita_reagendada` (+ the new roteiro's `roteiro_criado` and `visita_adicionada`); R14 one
  `visita_resultado` per visita whose status changed.
- **R3/R5/R6/R7 (autosave):** every call bumps `updated_at` and returns the full Roteiro. The FE writes the response
  into the cache (no refetch).
- **R8 gerar** does all of this in ONE transaction:
  - `status='gerado'`, `gerado_em=now()`, `gerado_por`;
  - the funnel moves to `visitas` (today's R2 behaviour, moved here; the response carries `funil` as today's POST
    does);
  - **links the lead:** for each visita `codigo`, upsert `cliente_imovel_interesses (cliente_id, codigo,
    origem='roteiro', lead_id = the atendimento's lead_id, meta_ads_lead_id)`. It fills empty only and never changes
    an existing row's origem;
  - the roteiro enters the feedback flow: `pendentes-feedback` lists ONLY gerado roteiros.
- **R9 reabrir:**
  - `status='rascunho'`, `reaberto_em/por`;
  - the interesses created by R8 are kept (a lead link is not undone);
  - funnel unchanged;
  - an in-app notification goes to `gerado_por` when it is not the caller. Use the product's existing notification
    organ. If none exists, it is a named deferral, not a silent skip.
- **R11 outcome:**
  - stamps `resultado_em/por`;
  - `realizada` also stamps `realizada_em` (today's behaviour);
  - an outcome can be changed back to `pendente`, which clears the stamps;
  - after any outcome exists, R9 is refused.
- **R12 reagendar:**
  - the visita → `reagendada`;
  - creates a NEW `rascunho` roteiro for the same atendimento with that one `codigo` (+ the date/time if given);
  - sets `reagendada_para_visita_id` = the new visita;
  - returns both.
- **R4 delete of a gerado without outcomes:** allowed (today's behaviour, including withdrawing an accepted proposta).

**Counts.** There is ONE derivation for lead / imóvel / corretor. `consolidadas = realizada`, `perdidas = cancelada
+ nao_compareceu`, `neutras = reagendada + pendente`. Drafts are excluded from every count (only gerado roteiros
count). `metricas_service` moves to these keys. A per-corretor breakdown waits for the intake's `imovel_corretores`
(feat/sw-ad-lead-intake). It is a follow-up slice named here, not part of this one.

**Strictness.** Request bodies reject unknown fields (422). The existing card_hub schemas already do this, so keep it
that way.

**Deprecations.**
- `nao_realizada` status and `nao_realizada_motivo` (vestigial, legacy read only).
- `contagem.nao_realizadas`.
- R2's funnel move.
- The FE's auto-download of the PDF right after create.
- The per-roteiro "Gerar Roteiro" PDF button label, which becomes "Baixar PDF".

## 5. FE behaviour (from the approved mockup)

- **One editor for create and edit.** It replaces the create-only `CriarRoteiroDialog`.
  - It creates the draft (R2) on the FIRST meaningful edit: first imóvel, or the date.
  - It autosaves every change after that (debounced about 800 ms; ordem and add/remove go out immediately).
  - Status chip: "Salvando…" / "✓ Salvo há N s" / "Não salvo" + banner + "Tentar de novo". The input is kept on error.
  - A close-guard dialog appears when the last save failed.
  - Closing never loses a draft. The draft shows in the list with "Continuar editando".
- **Reorder with ↑/↓ buttons** (the first ↑ and last ↓ are disabled with a reason), plus an `aria-live` announcement.
  Drag is optional.
- **"Gerar roteiro"** → a confirmation dialog → R8. Its enabled state comes from `permissoes.gerar` +
  `motivo_gerar`.
- **Gerado:**
  - the list is locked (no add/remove/reorder; `permissoes.editar_imoveis=false`);
  - per visita: an outcome select. Cancelada asks for motivo + quem cancelou, both required. Reagendada uses R12:
    "Criar novo roteiro com ONExxxx" opens the new draft;
  - date, time and observations stay editable.
- **"Baixar PDF"** is rendered ONLY when `permissoes.baixar_pdf`, i.e. gerado. It never appears on a draft. If R10
  ever answers 409, show its `message`.
- **"Reabrir como rascunho"** is rendered only when the user may reopen (`reabrir` or a `motivo_reabrir` about
  results). It is disabled with `motivo_reabrir`. A confirmation dialog warns that a PDF already downloaded is out of
  date.
- `ImovelInteressesList` "Gerar roteiro" opens the editor with those imóveis as a new draft. The immediate PDF
  download is removed.
- `RoteirosSection`: the status chip per roteiro; drafts show "Continuar editando"; gerado shows "Baixar PDF".
- Visit-history copy: reagendada reads "não conta".
- Hooks:
  - extend `useRoteiroMutations` (`useCacheWriteMutation`; every write puts the returned Roteiro into
    `roteirosKeys`);
  - add `gerar`, `reabrir` and `reagendar` (which writes both roteiros);
  - drop the `nao_realizadas` usage;
  - follow the server-state family (never `isLoading`, a refusal is never silent, a draft says it is unsaved).

## 6. Acceptance (both sides)

- BE: a test per row of §3, including strict `== 401` unauthenticated and the 403/409/422 codes above; migration
  backfill tests; R8 transaction atomicity; `permissoes` per role (owner, admin, supervisor, member); and the
  access-tier keepers.
- FE: tests per state-matrix row (NOTES §2); hooks assert this exact shape (no private guessed mock); vite build.
- E2E-shape check after both land: a real call to R1/R8/R10 against the built backend, asserting the FE-consumed keys.

## 7. Implementation notes (BE, 2026-11-09 — deviations from v1.0 decided at build time)

- **R8 transaction.** The atomic unit is the `social_wiring.roteiro_gerar` RPC (migration 338): row lock, guards, status flip,
  `gerado_*`, and the lead link commit together or not at all. The funnel move (stage gate + `pipeline_movimentos` +
  handoffs) is Python and runs AFTER that commit; its outcome rides on `funil` and never fails the call (the funnel's own
  contract: a refusal is a return value). A funnel failure therefore never un-generates a roteiro.
- **`usuario_papeis` is service-only** (RLS on, `REVOKE` from `anon`/`authenticated`, `tier:org`): the server computes `permissoes`, so
  nothing in the browser reads it. Seed-first check: the seed/core know ONE `org_role` per user per org
  (`noctusai_lib.primitives.roles`); there is no additive per-product role mechanism.
- **Reabrir notification** uses `noctusai_lib.domain.notifications.write_in_app` (core `public.notifications`, kind `roteiro_reaberto`).
- **Legacy cancelada.** Backfilled canceladas have `cancelada_por NULL`; the NOT VALID CHECK checks every updated row, so any edit that touches
  one (even an observation) is 422 `cancelada_incompleta` until `cancelada_por` is given.
- **Legacy feedback body.** `aconteceu=false` with no per-visita answer maps to `cancelada` (motivo `outro`) which needs `cancelada_por`: 422.
  The FE sends `resultado` per visita.
- **Timeline.** A draft is not a timeline event; a gerado roteiro appears at `gerado_em` (backfill = `created_at`).
