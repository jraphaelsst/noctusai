# Edição de Fotos — API contract (v1)

> **Contract-first** per skill `noc-contract-first`: authored ONCE, both sides build
> to it. Backend and frontend slices may proceed in parallel against this document.
> **Status:** draft for owner review. Not implemented.
> Base prefix: `/api/edicao-fotos`. All pt-BR in UI copy; all identifiers English.

## 0 · Conventions

- Auth: session cookie, as every social-wiring route. Every route below returns
  **strict `401`** when unauthenticated (asserted per `CLAUDE.md` §1 auth-boundary
  rule) and `403` when the role matrix denies.
- Org scoping: every resource is `org_id`-scoped and RLS-enforced except the two
  documented platform-scope tables (reference pool, style guides).
- Errors: typed envelope `{"detail": {"code": "...", "message": "..."}}`. No silent
  fallbacks; a missing dependency returns `503` with a named cause.
- Pagination: `?page=1&page_size=50` → `{items, page, page_size, total}`.
- Timestamps: ISO-8601 UTC. Money: integer cents + explicit `currency`.

## 1 · Role matrix

| Capability | platform admin | photo curator | agency admin | corretor |
|---|---|---|---|---|
| Reference pool CRUD | ✅ | ✅ | ❌ | ❌ |
| Activate guide version | ✅ | ✅ | ❌ | ❌ |
| Org settings (edit types, model, speed) | ✅ | ❌ | ✅ | ❌ |
| Approve org rules | ✅ (+override) | ❌ | ✅ | ❌ |
| See AI verdict | ✅ | ❌ | ✅ | 🔴 **never** |
| Create / review / download own batch | ✅ | ❌ | ✅ (all in org) | ✅ (own) |
| Platform dashboard | ✅ | ❌ | ❌ | ❌ |
| Org dashboard | ✅ | ❌ | ✅ | ❌ |

Roles resolve server-side: agency admin = org role in `(owner, admin, manager)`;
corretor = `(member, corretor)`; platform admin = `noctus_users.role='admin'`;
curator = a `photo_curator` grant in Core `public.user_permission_grants`.

🔴 **The AI verdict is hidden from corretores by table separation, not by field
omission** — `fotos_avaliacoes` is its own table so RLS can withhold the whole row.
A response shape that merely omits the field is a leak waiting for a refactor.

## 2 · Capabilities — `GET /capacidades`

Drives every FE gate. Server-computed; **never** derived from SSO metadata.

```json
{
  "pode_criar_lote": true,
  "pode_ver_veredito": false,
  "pode_gerir_pool": false,
  "pode_aprovar_regras": false,
  "pode_ativar_guia": false,
  "dashboard": "org",
  "modelo_configurado": true,
  "economico_disponivel": false,
  "economico_bloqueado_motivo": "modelo_sem_batch",
  "tipos_edicao_ativos": ["cor_luz", "ceu", "declutter"],
  "limites": { "fotos_por_lote": 100, "bytes_por_foto": 26214400 }
}
```

`modelo_configurado=false` ⇒ batch creation is blocked (there is **no platform
default image model**, deliberately, so models can be compared across orgs).

## 3 · Batches — `/lotes`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/lotes` | List visible batches (own for corretor; org-wide for agency admin) |
| `POST` | `/lotes` | Create a batch (metadata only) |
| `POST` | `/lotes/{id}/fotos` | Upload photos (multipart) — needs `_MAX_BODY_PATH_OVERRIDES` |
| `POST` | `/lotes/{id}/vista` | Pull photos from a Vista imóvel ✅ proven |
| `POST` | `/lotes/{id}/submeter` | Submit — snapshots the effective guide, enqueues jobs |
| `GET` | `/lotes/{id}` | Batch detail + per-photo state |
| `POST` | `/lotes/{id}/fotos/{foto_id}/retentar` | Manual retry of a `falhou` photo |
| `GET` | `/lotes/{id}/zip` | Download approved `.zip` — 409 until every photo is decided |

`POST /lotes` body: `{"nome": str, "imovel": {"org_id": str, "codigo": str} | null}`.

Photo state machine (every transition writes `fotos_eventos`, which is what the
throughput charts read):

```
recebida → normalizando → pronta → (editando | em_lote_openai)
        → editada → avaliando → aguardando_decisao → aprovada | rejeitada
                                                   ↘ falhou (after 1 auto-retry)
```

`falhou` photos are excluded from the zip and never block the batch.

## 4 · Review — `/revisao`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/revisao/{lote_id}` | Photos for review; includes `avaliacao` **only** if `pode_ver_veredito` |
| `POST` | `/revisao/{lote_id}/fotos/{foto_id}/decisao` | `{"decisao": "aprovar"\|"rejeitar", "comentario": str\|null}` |

`comentario` is **required** when `decisao="rejeitar"` (422 otherwise). Decisions are
always changeable, including after download — the zip is regenerated on next fetch.

## 5 · Reference pool — `/referencias` (platform scope)

`GET` / `POST` / `DELETE /referencias/{id}` (delete = **archive**, kept for history,
no longer counts toward the limit). A pair is `{antes_url, depois_url, comodo,
tipos_edicao[], nota}`. `POST` returns **409 `pool_cheio`** when the pair limit is
reached (limit counted **in pairs**; blank/0 = unlimited).

## 6 · Style guides — `/guias` (platform scope)

`GET /guias` · `POST /guias/regenerar` (manual) · `POST /guias/{versao}/ativar` ·
`POST /guias/{versao}/restaurar` (clones as a **new** version — versions are
immutable). Every new version is a **draft** until a platform admin or curator
activates it. Regeneration is also automatic, debounced after pool changes settle.

Effective guide for an org = **active company guide + that org's approved rules**,
deterministic text + `sha256`, **snapshotted onto the batch at submit** so an
in-flight batch never changes mid-run.

## 7 · Learning rules — `/regras`

`GET /regras` · `POST /regras/{id}/aprovar` · `POST /regras/{id}/rejeitar`.
AI proposes "don't do this" rules from that agency's rejection comments; a human
approves before they take effect. Only the platform admin may override an agency
admin's decision.

## 8 · Settings, models, curators, dashboard

- `GET|PUT /configuracoes` — org edit types, image model, speed override.
- `GET /modelos` — catalog: name, version, performance/cheap tag, batch-capable tag,
  live metrics (approval rate, AI score, cost per approved photo) + AI-written notes.
- `GET|POST|DELETE /curadores` — curator grants (platform admin only).
- `GET /painel` — dashboard: pipeline throughput · queue & health · activity ·
  learning loop · costs. Scope follows `capacidades.dashboard`.

## 9 · Loading-state contract (FE, binding)

Per `CLAUDE.md` §1 and `KB § PATTERNS/frontend/lying-loading-state.md` — **two
signals, never `isLoading`**:

```ts
const showSkeleton  = isPending && !data;
const isRefreshing  = isFetching && !!data;
```

Batch-detail and review queries key on `lote_id`; a key change **must** carry
`placeholderData` or the grid unmounts content that exists.

## 10 · Open — blocks implementation

- ✅ **C5 resolved** — `POST /lotes/{id}/vista` body `{"codigo": str}`. The adapter
  reads `GET /imoveis/detalhes` with `fields: ["Codigo", {"Foto": ["Codigo","Foto",
  "FotoPequena","Destaque","Tipo","Descricao"]}]` using the **existing** `VISTA_API_KEY`.
  Response `Foto` is a **dict keyed by photo code** — normalize with `list(.values())`.
  Ingest order follows `Destaque` first, then `Codigo`.
- Plan prices, trial lengths, grace days (owner fills in admin UI).
- Retention policy (currently "keep everything").
- Whether rejected photos get an automatic re-edit (owner reviewing first).
- Supabase storage price per GB-month (admin setting).
