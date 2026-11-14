# ImobShotAI — endpoint contract v1 (photo side: S1–S4)

> Frozen 2026-11-14 by the tech-lead (`noc-contract-first`). BE and FE build TO this. A change bumps the version
> and lands in both briefs. Spec: `IMOBSHOTAI-SPEC.md`. Video endpoints (§5 of the spec) are NOT in v1.

## 0 · House conventions (extracted from `modules/edicao_fotos`, origin/dev 2026-11-14)

- **Envelope:** lists use `page_out` → `{"items": [...], "page": n, "page_size": n, "total": n}`. A single object comes back **bare** (no `data` wrapper), like `lote_resumo_out`.
- **Errors:** `api_error(status, code, message)` → body `{"detail": {"detail": "<pt-BR message>", "code": "<code>"}}`. The FE branches on `code`, never on the message.
- **Roles:** `require_member` (platform admin, agency admin, corretor) and `require_org_admin` (platform admin or agency admin) from `app/modules/edicao_fotos/deps.py`. Reuse them; never re-implement them.
- **Strictness:** request bodies are `StrictHttpModel`, so an **unknown field is rejected with 422**.
- **Access tier:** every route below is tier **org** (authenticated, org-scoped). No `public`. Tables are tier **org** with RLS on `org_id`.
- **Auth tests:** strict `== 401` without a token on every route; `== 403` for a corretor on admin routes.

## 1 · `POST /api/imobshotai/lotes` — start a photo edit for a property (funnel step 1)

Request:
```json
{ "imovel_codigo": "ONE8990", "nome": "Fotos ONE8990", "velocidade": "urgente" }
```
- `imovel_codigo`: str, 1–40, trimmed + upper-cased server-side (the `canonical()` rule).
- `nome`: optional str, 1–120. Default `"Fotos <codigo> <dd/mm>"`.
- `velocidade`: optional `"urgente" | "economico"`. Same resolution as `POST /api/edicao-fotos/lotes`.

Response `201`:
```json
{
  "card": CardResumo,
  "lote": LoteResumo
}
```
`LoteResumo` is EXACTLY `lote_resumo_out` (unchanged).

**Side effects / state after (one transaction for the card + its event):**
1. Validates the imóvel exists for the actor's org via `imovel_hub.busca_service.enriquecer(client, org_id, [codigo])`. A row whose `fonte == "nenhuma"` (or a missing key) means it does not exist.
2. Get-or-create `imobshot_cards (org_id, imovel_codigo)`. When the card is new, it writes the event `card_criado`.
3. Creates the lote through the **same service path** as `POST /api/edicao-fotos/lotes`: extract that route's body into a shared function, do not copy it. `origem='vista'`, `imovel_org_id`/`imovel_codigo` set, `fotos_lotes.card_id = card.id`. Then writes the event `lote_vinculado` with `detalhe {lote_id}`.
4. After the call, `GET /api/imobshotai/cards/{card.id}` lists this lote, and the card's `etapa` is `fotos_enviadas` (or later, if older lotes are further on).

Errors:

| status | code | cause | FE message |
|---|---|---|---|
| 401 | — | no session | (redirect to login) |
| 403 | `sem_acesso_edicao_fotos` | role is not a member | "Seu papel não dá acesso ao ImobShotAI." |
| 422 | `imovel_inexistente` | the ref is not in the registry or the mirror for this org | "Nenhum imóvel com esse código." |
| 422 | `modelo_nao_configurado`, `sem_tipos_edicao`, `economico_indisponivel` | same as the lotes route | same messages as the lotes route |

## 2 · Gate on the existing `POST /api/edicao-fotos/lotes`

When `body.imovel` is present, the route also validates existence (step 1.1) and fails with `422 imovel_inexistente`. This is the root fix: it protects plain Edição de Imagem too. An absent `imovel` keeps today's behaviour (until §9 of the spec absorbs it).

## 3 · `GET /api/imobshotai/cards?etapa=&q=&page=&page_size=` — the board

- `etapa`: optional, one value of the enum in §6. `q`: optional prefix on `imovel_codigo` (case-insensitive). `page` ≥ 1, `page_size` 1–100 (default 50).
- Visibility follows the lotes rule: an agency or platform admin sees every card in the org; a corretor sees cards that hold at least one lote they created.
- Response: `page_out` of `CardResumo`, ordered by `atualizado_em desc`.

```ts
type CardResumo = {
  id: string;
  imovel: { org_id: string; codigo: string; titulo: string | null; bairro: string | null };
  etapa: Etapa;
  etapa_desde: string;          // ISO, when the card entered `etapa`
  capa_url: string | null;      // signed URL of the cover (best approved photo), null until one exists
  total_fotos: number;
  fotos_aprovadas: number;
  total_videos: number;         // 0 in v1
  criado_em: string;
  atualizado_em: string;
};
```

## 4 · `GET /api/imobshotai/cards/{card_id}` — card detail

Response `200` (bare):
```ts
type CardDetalhe = CardResumo & {
  lotes: LoteResumo[];                       // newest first
  fotos: Array<{
    id: string; lote_id: string;
    comodo: string | null;                   // room label when known (S5 fills it); null in v1
    status: string;                          // fotos_fotos.status verbatim
    original_url: string;                    // signed
    editada_url: string | null;              // signed, latest approved/edited version
  }>;
  videos: [];                                // v1: always empty
  eventos: Array<{ tipo: EventoTipo; etapa_de: Etapa | null; etapa_para: Etapa | null;
                   ator_id: string | null; em: string; detalhe: Record<string, unknown> }>;  // newest first, ≤ 50
};
```
Errors: `404 card_nao_encontrado` (also for a card from another org or one the corretor can't see; never `403`, so nothing leaks).

## 5 · Approval (D6): photo decisions on ImobShotAI lotes are admin-only

The existing photo decision route in `edicao_fotos` (the reviewer's approve/reject) refuses when the photo's lote has a `card_id` and the actor is not an org or platform admin: `403 restrito_admin_organizacao` (`require_org_admin`'s message). Lotes without `card_id` keep today's rule. The FE hides approve/reject for non-admins on ImobShotAI pages and shows "Aguardando aprovação de um administrador."

## 6 · Etapa (card stage) — a projection, never set by hand

`Etapa = "fotos_enviadas" | "fotos_em_edicao" | "fotos_em_revisao" | "fotos_aprovadas" | "video_em_montagem" | "video_renderizando" | "video_em_revisao" | "concluido" | "arquivado"`. In v1 only the first four are reachable.

It is derived from the card's lotes and photos:

| Condition (over all the card's lotes) | etapa |
|---|---|
| at least 1 photo approved AND no photo still to edit or decide | `fotos_aprovadas` |
| some photo awaiting a decision (`aguardando_decisao`), none still being edited | `fotos_em_revisao` |
| some lote `submetido`/`processando`, or a photo in an editing state | `fotos_em_edicao` |
| otherwise (only `rascunho` lotes, or no photos yet) | `fotos_enviadas` |

`sincronizar_etapa(card_id)` recomputes it and, **only when it changed**, updates `imobshot_cards.etapa` + `etapa_desde` and writes an `etapa_mudou` event (`etapa_de`, `etapa_para`) in the same transaction. Call sites are the lote submit, the photo decision, the retry, the `fotos.lote_pronto` job hook and `POST /api/imobshotai/lotes`. The GET routes return the stored value and do not write.

## 7 · Records / metrics (measurement by design)

- `imobshot_cards` (dated: `created_at`, `updated_at`, `etapa_desde`, `fotos_concluidas_at`) and `imobshot_eventos` (append-only; `tipo` enum `card_criado | lote_vinculado | etapa_mudou | card_arquivado`; plus `actor`, `at`, `detalhe jsonb`). `fotos_lotes.card_id uuid null` (FK, indexed).
- Metrics enabled: time from `card_criado` to `fotos_aprovadas` per card; cards per etapa (the board counts); drop-off (cards stuck in `fotos_enviadas` for more than 7 days); approval rate per card (from `fotos_decisoes`).

## 8 · Pages (FE) and their `status_pagina` keys

| Route | Page | status_pagina key | Initial status |
|---|---|---|---|
| `/imobshotai` | Board (seed `KanbanBoard` with `draggable={false}`, columns = the 4 reachable etapas; v1.1: the etapa is a projection, so there is no drag-to-move; `FunnelBoard` needs move endpoints this contract does not have) | `imobshotai` | `producao` |
| `/imobshotai/fotos/novo` | Photo funnel | `imobshotai-fotos-novo` | `producao` |
| `/imobshotai/imoveis/:cardId` | Card detail | `imobshotai-card` | `producao` |
| `/imobshotai/video/novo` | placeholder "em breve" (video is blocked) | `imobshotai-video-novo` | `desenvolvimento` |

The BE slice owns the migration that adds these `status_pagina` rows, so there is only one migration per slice.

Photo funnel steps (FE):
1. **Imóvel + velocidade:** `ImovelCodigoPicker` in **select-only** mode. Free text can never be submitted. Under 2 characters it shows "Digite ao menos 2 caracteres". An empty result shows "Nenhum imóvel com esse código". Picking a ref, then choosing velocidade (urgente/econômico) and pressing "Continuar", calls §1. *(v1.1, 2026-11-14: the velocidade moved here because a lote's velocidade is fixed at creation by §1.)*
2. **Fotos:** the existing upload (`/api/edicao-fotos/lotes/{id}/fotos`, ≤ 10 files per request, the same component/hook as NovoLote). It also offers "Puxar fotos do Vista" (`/{id}/vista`).
3. **Estilo:** a read-only view of the chosen velocidade and the org's active guia.
4. **Enviar:** `/{id}/submeter`, then progress by polling `GET /api/edicao-fotos/lotes/{id}` (seed polling; SSE comes later).
5. **Revisão:** the existing review UI (`LoteRevisao` content) embedded; the D6 rule applies.
6. **Pronto:** a link to `/imobshotai/imoveis/:cardId`, plus a disabled CTA "Criar vídeo (em breve)".
