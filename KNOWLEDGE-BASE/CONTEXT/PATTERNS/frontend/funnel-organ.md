# Funnel organ — one board + card, declared per product

> **Rule.** A sales/CRM funnel is the seed's `FunnelBoard` + `FunnelCardDialog` configured by a
> `defineFunnel` schema. What differs between products (face, tabs, actions, hub link) is a
> **schema literal**; the component is the same in every context. Never a per-product board, card
> face, lost dialog or "move" menu.
> → `seed/lib/frontend/src/components/pipeline/funnel/` · design/notes: owner decisions 2026-11-07

## 1 · Why (owner, 2026-11-07)

"The card tabs, structure and data must be dynamicized per product — the card in SW is not the card
in IgIg or NoctusAI, but it is the same component in different contexts." Mockups approved the same
day (card in SW / IgIg / NoctusAI / Orbity contexts; NoctusAI board + drawer).

## 2 · Composition (nothing new at the bottom)

| Layer | Reused | Added by the funnel |
|---|---|---|
| Board | `PipelineBoard` → `KanbanBoard` (drag, totals, load-more, stage editor, `onBeforeMove`) | `FunnelBoard` = PipelineBoard + views (Abertos / Perdidos) + refusal panel |
| Face | `CardHubFace` | `FunnelCardFace` through the face's declared **seam** (`leading` / `subtitle` / `chips` / `footer` / `onOpen`) |
| Detail | `CardHubDialog` (rail + subpage registry + activity pane) | `FunnelCardDialog`: tabs come from the schema |
| Data | `createPipelineHooks`, `createCardHubHooks` | `createFunnelHooks`: meta, card, lose/reopen/archive, actions, update; ONE move mutation |

`CardHubFace`/`CardHubDialog` got two additive, backwards-compatible changes: the face seam above,
and `activity.composer` optional (a funnel with no hub has a read-only history pane).

## 3 · The schema

```ts
const funnel = defineFunnel<MyCard>({
  id: 'sw', entityLabel: 'atendimento',
  face: { avatar, chips, value, owner, due, score, roleAction, iconAction }, // all optional accessors
  tabs: [{ id, label, icon, order?, when?(card), section }],                  // section kinds below
  actions: [{ code, label, icon?, placement: 'header' | 'face', confirm?, inputs? }],
  hubEntityId: (card) => card.hub_entity_id,                                  // null = no card-hub
});
```

Section kinds: `geral` (hub spine — product renderer) · `fields` · `form` (edit through PATCH, only
`meta.campos_editaveis`) · `list` · `linked {endpoint, columns, onOpen}` · `schedule` ·
`reminders` · `conversation` (product renderers — they need product services) · `timeline` ·
`custom {render}`. A kind with no renderer says so on screen — never a blank tab.
`defineFunnel` THROWS on a duplicate tab/action id (fails at module load, not silently at render).

## 4 · Behaviours the organ owns (fix once, not per product)

- **Statuses, not columns.** `ganho | perdido | arquivado` are `card.status`. The board has two
  views (Abertos / Perdidos); a lost card offers **Reabrir**. Lost reason = coded list from
  `meta.lost_reasons`; `exige_texto` ("Outro") makes the text required (422 `motivo_obrigatorio`
  is shown inline).
- **Moving without drag (WCAG 2.5.7).** "Mover para…" menu on every open card AND an "Etapa" select in
  the dialog header; drag still works. All three go through the same mutation.
- **Gate refusals are never silent.** 409 `gate_refused` → the move mutation rolls the card back
  (snap-back) and the board/dialog lists `pendencias`; any other refusal toasts the server's
  `mensagem`.
- **Keyboard + names.** The title is a `<button>` (dnd-kit owns Enter/Space on the card wrapper for
  keyboard drag, so opening needs a control inside); icon-only buttons carry `aria-label`.
- **Value = one-off + monthly.** `campos.valor_unico` / `campos.valor_mensal` →
  "R$ 18.000,00 + R$ 794,00/mês"; else `valor`; none → hidden on the face, "—" in the detail.
- **Cache contract** (skill `noc-cache-writes`): every card mutation writes optimistically where it
  can and commits the SERVER card into every board entry (`[queryKey, filtros]`, prefix) and the
  detail entry; a status change is applied per view (`showsStatus`: an `aberto` board loses a lost
  card, a `perdido` board gains it); settle refetches the board for server totals.

## 5 · Wire contract (backend slice `feat/seed-funnel-organ-be`)

`GET P/meta` · `GET P/board?busca&limite_por_etapa&responsavel_id&status` · `POST P/cards` ·
`GET|PATCH P/cards/{id}` · `POST P/cards/{id}/mover-etapa|perder|reabrir|arquivar|acoes/{codigo}` ·
`GET P/cards/{id}/movimentos?cursor`. Errors `{code, mensagem, detalhe?}`; `gate_refused` carries
`{gate, pendencias:[{codigo,label}]}`. `parseFunnelError` reads flat / `error` / `detail` / `detalhe`
envelopes.

## 6 · Board convergence (DRY — one board)

The seed has three board components; the funnel is NOT a fourth. `PipelineBoard` is the target.

| Board | Status | Convergence path |
|---|---|---|
| `PipelineBoard` | the organ (FunnelBoard composes it) | — |
| `KanbanBoard` | presentation layer UNDER `PipelineBoard` (not a duplicate) | stays; consumers needing data use PipelineBoard |
| `leads/LeadsBoard` | duplicate: KanbanBoard + static stages + own move hook | `NOC-REMEDIATE[pipeline-board-organ]` — becomes a `FunnelBoard` schema once leads stages are served as `PipelineStage` rows (`/api/leads/config` → board columns) |
| Orbity `Funil.tsx` (KanbanBoard + own `useCrm`) | product fork | converge on `FunnelBoard` per the orbity absorption slice |

## 7 · Out of scope here / follow-ups

- Gate **inputs** collected before the move (`meta.gates[papel].inputs`): the refusal path shows what
  is missing; a pre-move input dialog is the `onBeforeMove` seam (pass-through on `FunnelBoard`).
- `geral` / `schedule` / `reminders` / `conversation` renderers per product (hub-spine adapter is a
  follow-up: `NOC-REMEDIATE[funnel-geral-spine]`).
- Contrast tokens (muted-foreground 42% light, primary 46% dark) are a design-system token change —
  coordinate with the tokens owner, do not fork in the organ.
