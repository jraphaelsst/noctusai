# Pesquisa (Minha Pesquisa) — build contract v1 (2026-10-09)

The single contract the backend and frontend slices build to. Behaviour reference:
`pesquisa-cerebro-spec.md` §1 (CoreStudio's Minha Pesquisa) and `variables-usage.md` §6
(the 40 variables). Where this file differs from CoreStudio, this file wins — the
differences are deliberate and listed in §6.

Scope of v1 = **Minha Pesquisa** only: the per-brand list, manual add, AI-classified add,
approve / reject / delete / bulk / empty. **Extrair Pesquisa** (items from our own content
and the connected Instagram) is wave 2 and reuses the same item table with
`origin='extraction'`. Segundo Cérebro, headlines and roteiros are later modules.

## 1 · Owner decisions this contract encodes

- Research is scoped **per marca** (`social_wiring.marcas`); the page has a brand switcher.
- **All 40 variables** (29 CoreStudio DB variables + 4 globals + 7 classifier-only).
  Meaning of the unclear ones gets refined later from real usage — "first a fully working
  prototype, then refine".
- Approval like CoreStudio: **manual add = approved; AI-produced = pending; rejected = hidden**
  (soft, kept for audit/dedupe, never listed).
- The classifier prompt is OUR prompt, drafted from CoreStudio's captured one
  (`prompts/pesquisa-classifier-prompt.md`) and extended to all non-global variables.
  It is a **DRAFT for owner validation** — the module docstring says so.

## 2 · Data model (migration **217**, schema `social_wiring`)

### `cs_research_variables` — static taxonomy, seeded by the migration
| column | type | notes |
|---|---|---|
| `slug` | text PK | e.g. `DORES-TANGIVEIS-DO-AVATAR` (CoreStudio slug where one exists; `LOCAIS-CONHECIDOS-PELO-AVATAR` spelled correctly; globals get `VERBOS-PODEROSOS`, `ADJETIVOS-PODEROSOS`, `MOMENTO-DO-DIA`, `GPT`) |
| `label` | text | CoreStudio UI label, trailing spaces trimmed; classifier-only ones get a pt-BR label (`Frustrações do meu público`, `Crenças limitantes do meu público`, `Inimigo comum`, `Mecanismo único`, `Promessa principal`, `Prova social`, `Nicho ou mercado`) |
| `grupo` | text CHECK in (`publico`,`especialista`,`produto`,`global`) | UI: Meu Público / Sobre Mim / Produto / Globais. `produto` = MECANISMO-UNICO, PROMESSA-PRINCIPAL, PROVA-SOCIAL, NICHO-OU-MERCADO |
| `description` | text | one-line definition (the classifier table text; written for those that lack one) |
| `corestudio_id` | int NULL | CoreStudio variable id (traceability only) |
| `sort_order` | int | CoreStudio select order, then classifier-only, then globals |
| `classifiable` | bool | true for every non-global variable (the AI may route a line there) |

Read-only for authenticated users (RLS select = true); no write policy.

### `cs_research_items`
| column | type | notes |
|---|---|---|
| `id` | uuid PK default gen_random_uuid() | |
| `org_id` | uuid NOT NULL | RLS: `org_id = (SELECT public.current_org_id_for('social_wiring'))` |
| `marca_id` | uuid NOT NULL FK → `social_wiring.marcas(id)` ON DELETE CASCADE | |
| `variable_slug` | text NOT NULL FK → `cs_research_variables(slug)` | |
| `content` | text NOT NULL, 1..500 chars, trimmed | |
| `status` | text CHECK in (`pending`,`approved`,`rejected`) | |
| `origin` | text CHECK in (`manual`,`ai_classified`,`extraction`) | `manual` ⇒ status starts `approved` |
| `source_ref` | jsonb NULL | wave 2: `{kind:'instagram_media'|'post', id, url, plays}` |
| `plays` | bigint NULL | views of the source post (sort "Mais views") |
| `created_by` | uuid NULL | |
| `created_at`, `updated_at` | timestamptz default now() | |

Unique `(marca_id, variable_slug, lower(content))` — adding an existing value is a no-op
reported as `skipped` (a rejected duplicate stays rejected: re-adding does not resurrect it
unless added manually, which flips it to `approved`).
Index `(marca_id, status, created_at desc)`.

## 3 · Endpoints — prefix `/api/media-creation/pesquisa`, auth `get_current_user_org`

All responses use `success_response` (`{success, data}`); errors are `HTTPException` with a
pt-BR `detail`. `marca_id` must belong to the caller's org → else **404**.

| # | Method + path | Request | `data` |
|---|---|---|---|
| 1 | `GET /variables` | — | `Variable[]` ordered by `sort_order` |
| 2 | `GET /items` | query `marca_id` (req), `status=approved\|pending` (default approved), `variable_slug?`, `sort=recent\|plays` (default recent), `limit` (1–200, default 50), `offset` | `{items: Item[], total: int}` |
| 3 | `GET /items/counts` | query `marca_id` | `{approved:int, pending:int, by_variable:{[slug]:{approved:int,pending:int}}}` |
| 4 | `POST /items` | `{marca_id, variable_slug, lines: string[1..200]}` | `{saved:int, skipped:int, items: Item[]}` — manual ⇒ `approved` |
| 5 | `POST /items/classify` | `{marca_id, text}` (≤ 20 000 chars, newline-separated) | `{saved:int, skipped:int, classified:{[slug]: string[]}, unclassified: string[]}` — saved as `pending`, `origin='ai_classified'` |
| 6 | `POST /items/{id}/approve` | — | `Item` |
| 7 | `POST /items/{id}/reject` | — | `Item` |
| 8 | `DELETE /items/{id}` | — | 204 |
| 9 | `POST /items/bulk` | `{marca_id, action:'approve'\|'reject'\|'delete', ids: uuid[1..500]}` | `{affected:int}` |
| 10 | `POST /items/empty` | `{marca_id, confirm: true}` | `{deleted:int}` — hard-deletes ALL items (all statuses) of that marca |

```ts
type Variable = { slug: string; label: string; grupo: 'publico'|'especialista'|'produto'|'global';
                  description: string; classifiable: boolean; sort_order: number }
type Item = { id: string; marca_id: string; variable_slug: string; content: string;
              status: 'pending'|'approved'; origin: 'manual'|'ai_classified'|'extraction';
              plays: number|null; source_ref: object|null; created_at: string }
```
`rejected` items are never returned by any read endpoint.

**Classify (5)**: one `chat_completion` call via `noctusai_lib.integrations.llm` (never a
raw OpenAI client); output format = CoreStudio's `{{SLUG}}\n[conteúdo literal]` pairs;
the parser accepts only slugs in `cs_research_variables` with `classifiable=true`; any line
the model returns under an unknown slug, or any input line absent from the output, goes to
`unclassified`. Synchronous; LLM failure → **502** `detail="Falha ao classificar com IA"`
(no silent fallback, no partial save). Prompt lives in
`app/modules/media_creation/prompts/pesquisa_classifier.py` (DRAFT header).

## 4 · Frontend

- Route `/media-creation/pesquisa`, page title **Minha Pesquisa**, subtitle
  "Gerencie as variáveis de pesquisa de cada marca para criar headlines inteligentes."
- Sidebar (both nav configs in `App.tsx`): group **Criação de mídia** becomes
  `Criação de mídia` (existing link, unchanged) + sub-group **Pesquisa** › **Minha Pesquisa**.
  (Extrair Pesquisa joins that sub-group in wave 2.)
- Brand switcher (marcas of the org, remembered per user in localStorage, try/catch).
- Toolbar: sort `Mais recentes | Mais views` · status `Aprovados (n) | Pendentes (n)` ·
  variable select grouped by `grupo` (`Todas as variáveis` default) · `Agrupar` toggle · count.
- Row: accent bar (purple approved / orange pending) · checkbox · content + meta
  `label · grupo [· manual|IA] [· 1.234.567 views]` · actions: pending → Aprovar / Rejeitar;
  approved → Excluir (confirm).
- Bulk bar: `n selecionado(s)` · Selecionar todos · Ações modal: Aprovar (pending filter only),
  Excluir selecionados (confirm), Zerar toda a pesquisa da marca (confirm, typed brand name).
- Add modal "Inserir itens na pesquisa": textarea one item per line (Ctrl+Enter saves, live
  count). If a variable is selected in the modal's select → `POST /items` (manual, approved).
  If "Classificar com IA" (default when no variable selected) → `POST /items/classify`,
  processing state, then a result view (saved/skipped, classified groups, unclassified list,
  "Inserir mais" / "Fechar"); toast on success, list + counts refetched.
- Loading: the two-signal rule (`showSkeleton = isPending && !data`,
  `isRefreshing = isFetching && !!data`), `placeholderData` on filter/brand key changes;
  empty state "Nenhum item encontrado."; error state with "Tentar novamente".
  Paging: "Carregar mais" (offset), disabled when `Agrupar` is on (then limit=200).

## 5 · Tests (minimum)

Backend: variables seed has exactly 40 rows with the 4 groups; CRUD + status transitions;
manual duplicate → skipped; cross-org `marca_id` → 404; rejected never listed; classify
parser (valid pairs, unknown slug, missing line, model chatter) with the LLM seam faked;
classify LLM error → 502 and nothing saved; auth `== 401` strict.
Frontend: page renders list from mocked API, add-modal both modes, approve/reject/bulk flows.

## 6 · Deliberate differences from CoreStudio

- Per-marca (CoreStudio: per workspace/user). UUIDs, single table with `status` (CoreStudio:
  two stores + `source`). Rejected is soft (CoreStudio: unclear). Classifier covers all 36
  classifiable variables (CoreStudio: 13 slugs). No job fallback for classify in v1.
  "Assuntos Virais" pane, prompt-editing UI and legacy per-variable editor are not built.
