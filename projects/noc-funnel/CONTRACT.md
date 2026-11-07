# Funnel organ — wire contract (v1)

> Contract-first: the backend slice (`noctusai_lib.domain.pipeline.funnel`, branch `feat/seed-funnel-organ-be`) and the
> frontend slice build to THIS file. Owner decision 2026-11-07: one seed funnel organ (board + card) consumed by every
> product with per-product card tabs/structure/data. Consumer #1 = the core NOC funnel (platform tier, on
> `website_leads`); later social-wiring, igig, ERP, Orbity.

PREFIX `P`: core = `/api/admin/funnel`; products their own. Envelope = the product's `success_response` (`{"data": ...}`).

## Card DTO

```
{ id, etapa_id, kanban_pos: string, status: "aberto"|"ganho"|"perdido"|"arquivado",
  titulo, subtitulo|null, valor: number, responsavel: {id, nome}|null, badges: [{label, variant}],
  motivo_perda_codigo|null, motivo_perda|null, created_at, updated_at, hub_entity_id|null,
  campos: {<key>: any} }
```

`kanban_pos` is a string (numeric precision survives the wire). `campos` is the product's editable per-card data
(`FunnelConfig.editable_fields`); `/meta.campos_editaveis` lists its keys.

## Routes

| Route | Body / query | Response |
|---|---|---|
| `GET P/meta` | — | `{pipeline, papeis, lost_reasons:[{codigo,label,exige_texto}], gates:{<papel>:{codigo,inputs,mensagem}}, acoes:[{codigo,label,papeis}], campos_editaveis}` |
| `GET P/board` | `?busca&limite_por_etapa&responsavel_id&status=aberto` (`status` = aberto \| ganho \| perdido \| arquivado \| todos[no status filter]; all filters server-side) | `PipelineColumn<Card>[]` — wire-identical to today: `etapa, stage, total, valorTotal, exibidos, cards` |
| `GET P/board/orfaos` | — | `Card[]` |
| `POST P/cards` | `{titulo, etapa_id?, valor?, responsavel_id?, campos?}` | `201` Card (entry movimento `de_etapa_id=null`) |
| `GET P/cards/{id}` · `PATCH P/cards/{id}` | PATCH `{titulo?, valor?, responsavel_id?, campos?}` | Card |
| `POST P/cards/{id}/mover-etapa` | `{para_etapa_id, novo_indice?, motivo?, extra?}` | Card + one movimento (not on a same-stage reorder) |
| `POST P/cards/{id}/perder` · `/reabrir` · `/arquivar` | perder: `{motivo_codigo, motivo_texto?}` | Card |
| `POST P/cards/{id}/acoes/{codigo}` | `{payload}` | `{card, efeitos}` |
| `GET P/cards/{id}/movimentos` | `?cursor&limite` | `{items:[{id,kind:"movimento",ocorrido_em,de_etapa,para_etapa,motivo,ator,created_at}], total, next_cursor}` (`total` = all movimentos of the card, before the cursor cut) |

`P/etapas/**` = the seed `pipeline_stages_router`. `P/cards/{id}/{notas,tags,membros,checklists,documentos,lembretes,timeline,card}`
= the seed `card_hub_routers` (only when the product's `FunnelConfig.card_hub` is set).

## Errors

`{code, mensagem, detalhe?}` — carried on the platform error envelope (see Notes): 401 · 403 · 404 `card_not_found` |
`stage_not_found` (incl. another tenant's) · 404 `acao_desconhecida` · 409 `gate_refused {gate, pendencias}` · 409
`card_fechado` · 409 `etapa_inativa` · 422 `motivo_obrigatorio` | `motivo_desconhecido` | `campo_nao_editavel`.
Every write is `log_action`-ed; movimentos are append-only; **no write on a 4xx**.

## Notes the contract pins down (backend slice decisions, FE builds to these)

- **Error envelope.** Errors render through the platform handler (`app_exception_handler`), so on the wire they are
  `{"error": {"code", "message", "details"}}` — `mensagem` → `error.message`, `detalhe` → `error.details`. The machine
  `code` values are exactly the ones above. A `gate_refused` carries `details = {gate, pendencias:[{codigo, mensagem}]}`.
  One extra code: 422 `cursor_invalido` (malformed `cursor` on `/movimentos`).
- **Tenancy.** `org` funnels scope every read/write to the caller's org; a session with no org is a 500, never "all
  tenants". `platform` funnels scope to one declared platform org; the card table needs no `org_id`.
- **Status.** A won card (`ganho`) is produced by a product action (`/acoes/{codigo}`), not by a generic route; `perder`
  / `reabrir` / `arquivar` are generic. `perder`/`mover-etapa`/`PATCH`/actions on a non-`aberto` card -> 409
  `card_fechado`; `reabrir` on an open card is an idempotent 200 no-op; `arquivar` on an archived card is `card_fechado`.
- **Move.** Gate = `meta.gates[<papel of the DESTINATION stage>]`, checked only on a real stage change; the UI collects
  `gate.inputs` into `extra`. Stage change without `novo_indice` lands on top of the destination column; a same-stage
  call without `novo_indice` changes nothing. `novo_indice` counts positions with the moved card removed (clamped).
- **Board.** One column per ACTIVE stage (empty ones included); `total`/`valorTotal` cover the whole column, only
  `cards` is cut to `limite_por_etapa` (default 50, max 1000). Cards in no active stage appear in `/board/orfaos`.
- **Movimentos.** Newest first; `de_etapa`/`para_etapa` are `{id,label,slug}|null` (a renamed stage reads renamed);
  `ator` is `{id,nome}|null`; `next_cursor` is opaque.
- **Access tier.** The board router is created `make_router(tier=cfg.tenancy, guard=auth_dependency)`: platform funnel
  => `platform` (platform-admin only); org funnel => `org`.

## Agreed with the FE slice (2026-11-07)

1. `valor_unico` / `valor_mensal` are product `campos` keys (`editable_fields` + `card_projection.campos`); the DTO's single `valor` stays the board total column.
2. `mover-etapa` carries `extra` as a NESTED object (`{para_etapa_id, novo_indice?, motivo?, extra:{...}}`); only keys declared in `meta.gates[papel].inputs` reach the gate.
3. `/movimentos` items are timeline-shaped (`kind:"movimento"`, `ocorrido_em`) plus `total` and `next_cursor`.
4. `mover-etapa`, `perder`, `reabrir`, `arquivar`, PATCH return the bare Card DTO (inside `{data}`); `acoes/{codigo}` returns `{card, efeitos}`.
5. DIVERGENCE (BE keeps the platform envelope): a 409 `gate_refused` is `{"error":{"code":"gate_refused","message":<first pendencia message>,"details":{"gate":..., "pendencias":[{codigo,mensagem}]}}}` -- NOT top-level `mensagem`/`pendencias`. FE should read `error.details.pendencias` / `error.message`.
6. `status` default `aberto`; `todos` supported.
7. Filters (`busca`, `responsavel_id`, `limite_por_etapa`) are server-side.
8. `meta.lost_reasons` drives the lose dialog; `motivo_obrigatorio`/`motivo_desconhecido` are 422 with `error.code`.
