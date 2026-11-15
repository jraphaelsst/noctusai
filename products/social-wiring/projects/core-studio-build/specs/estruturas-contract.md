# Estruturas (platform library of script structures) + unified headline→roteiro chat + Esteira auto-card — build contract v1 (2026-11-15)

> Authored by the contract author (noc-contract-first) on 2026-11-15 against `origin/dev` @ `5e9dcef6a`, from the owner decisions of the same day
> (memory `project_corestudio_estruturas`, settled; this file encodes them and never re-opens them). Shape follows `geracao-contract.md` /
> `esteira-contract.md`. **§14 records the owner's answers to the original open questions (all closed).** Where this file and CoreStudio disagree, this file wins.
>
> **Amendment (same day, owner answers, binding):** (1) the import is a **pure loader of a pre-filled reference dataset — no model call at import**; (2) the 52 unavailable CoreStudio records are **dropped**;
> (3) a platform-wide **catalog of block types** (`cs_estrutura_tipos_bloco`) is added and every block references it; (4) roteiros are generated for **all four formats** now;
> (5) admins can add a video by **pasting a single Instagram post link**; (6) a newly analysed viral video **auto-creates a draft Estrutura**; (7) the platform ingestion org is the **NoctusAI org**;
> (8) headline `[placeholders]` are filled from the **org's brains + bio**, never left in the output; (9) the 3-Estrutura mix cap is confirmed; (10) org members cannot suggest profiles.
>
> **Path note.** The brief asked for `projects/core-studio/specs/`. That folder does not exist; every sibling contract (`geracao-contract.md`,
> `esteira-contract.md`, `apify-biblioteca-contract.md`, …) lives in `products/social-wiring/projects/core-studio-build/specs/`, so this file lives there too
> (the old contracts cite the non-existent `projects/core-studio/specs/` path; that is a stale reference, not a second folder).
>
> **Vendor-derived inputs.** The two import files (§7: `estruturas-referencia.json`, `maquina-de-roteiros-2026-11-15.json`) and the CoreStudio chat captures are vendor-derived (the reference file carries
> vendor text in `formula_headline`/`nota`/`nome_original`): **never committed**. This contract references their local path only; test fixtures are synthetic. `catalogo-blocos.json` is OUR content (§3.1) and may be committed as the seed source. Behaviour reference for the chat: memory `project_corestudio_estruturas` ("How CoreStudio does it").

---

## 0 · Before you dispatch: what the code says (verified on `origin/dev` @ `5e9dcef6a`)

1. **Envelope.** Every `media_creation` router returns `noctusai_lib.primitives.responses.success_response(data[, total])` → `{"data": …}` (`+ "total"` only when passed).
   List endpoints return `{"data": {"items": [...], "total": n, …}}` (`list_lotes`, `list_headlines`, `list_virais`). Creates/accepts declare 201/202 on the route.
2. **Error shape.** FastAPI `HTTPException`: `{"detail": "<pt-BR message>"}` or `{"detail": {"code": "<snake_code>", "detail": "<pt-BR message>", …extra}}`
   (chat `_raise`, headlines `_assert_ia`, esteira `coded()`). SSE failures after the first byte are the frame `{"error": {"code", "message"}}`.
   `require_platform_admin` (`app/dependencies.py`) answers **403 with a plain string detail** ("Restrito a administradores da plataforma NoctusAI."), no `code`.
   A foreign/unknown id is **404 never 403**; a forbidden state is 409; caps are 429 + `Retry-After`; no AI key / worker is 503.
3. **Today's structure source is the per-viral `cs_virais.blueprint` + `blueprint_slots`** (migration 229), cited in chat as `(estrutura #<codigo>)` where `codigo` is the
   viral's identity column. The pool is `headline_pipeline.pool_de_estruturas(carregar_candidatos(db, org_id), referencias_da_marca(...), nichos)`; chat uses
   `chat_contexto._pool_estruturas` (`MAX_ESTRUTURAS = 12`) and `modo_de_selecao` (`post | mencoes | auto`).
4. **The seed LLM layer has no tool use** (`NOC-REMEDIATE[llm-tool-use]`, `geracao-contract.md` §0.3). Retrieval is a server step that runs **before** generation and its result is
   put in a `<material>` block; name resolution is therefore deterministic server code, not a model tool call (§8).
5. **Library tables are org-scoped today** (`cs_perfis_monitorados.org_id`, `cs_virais.org_id`, `cs_biblioteca_referencias.org_id`; RLS `…_select_own_org`, browser `SELECT`).
   `cs_biblioteca_optouts` is already platform-wide and service-role only (migration 233). **Precedent for a platform-wide library with admin-only writes:** `cs_treinamentos`
   (`routers/treinamentos.py`: reads any member, writes `require_platform_admin`, FE probes `GET /treinamentos/admin` → `{is_admin}`).
6. **The name `estrutura` is already taken** by the roteiro *beat order* (`cs_roteiros.estrutura` ∈ `cta_inicio | cta_final`, migration 250; `RoteiroCreate.estrutura`; FE `RoteiroEstrutura`).
   This contract keeps that column/field untouched and calls the new entity **Estrutura (library)**; every new field about the library is `estrutura_ids` / `estruturas…`; every new
   mention of the beat order says **ordem do CTA** (`ordem_cta`, read-only alias of `estrutura`, §6.7). Renaming the legacy field is the cleanup migration M5, not this release.
7. **Chat today:** `cs_chat_conversas.agente ∈ (headline, roteiro)` per conversation; the FE parses headline lines out of the assistant markdown (`components/geracao/chat/citacoes.ts :: extrairHeadlines`).
   8 production conversations (7 headline, 1 roteiro).
8. **Esteira:** `cs_posts` (migration 241) has composite FKs `(headline_id, marca_id)` / `(roteiro_id, marca_id)`, unique per headline and per roteiro; `EsteiraService.criar(PostCreate{marca_id, headline_id})` already puts the card in the
   **second** stage by position ("Headline + roteiro") when a headline is given; `vincular_roteiro` rebinds atomically (`cs_rebind_roteiro`); `RoteiroCreate.post_id` binds the new roteiro to a post.
   Caption: `POST /esteira/posts/{id}/legenda/gerar` returns the caption (never saves; needs a `completo` roteiro, else 422 `sem_roteiro`; cap `legendas_dia_usuario=40`, counter `cs_legenda_geracoes`, migration 242).
9. **Prod audit (tech-lead, read-only, 2026-11-15):** `cs_perfis_monitorados`=0, `cs_virais`=0, `cs_biblioteca_referencias`=0, `cs_biblioteca_optouts`=0 rows ⇒ **no data migration**, schema change only.
10. **Roteiro approval (S3, `feat/cs-roteiro-approval`) is being built in parallel** on the seed approvals organ (S2). This contract references it as an interface (§9.4, assumption A1) and never duplicates it.
11. **Open access-tier findings** (`noctus.dev.findings_ledger action=open_for_scope scope=social-wiring`): 276 open, none on the routes below; the 267 `browser-grant` rows include browser grants on `cs_*` tables.
    M2 removes the browser grants on the two library tables it touches and every new table in this contract is born service-only (burn-down; the reconcile closes the rows, never by hand).

---

## 1 · Decisions encoded (owner, 2026-11-15) and the design calls this contract makes

| # | Owner decision | Where encoded |
|---|---|---|
| D1 | New first-class `cs_estruturas`, profile required, optional source video, headline formula + ordered blocks; per-viral blueprint is replaced as the structure source | §3.1, §3.6 |
| D2 | Library is platform-wide only: profiles, videos, Estruturas; only platform admins write (videos arrive by profile sync **and** by pasting a single Instagram post link); orgs/brands only choose (`cs_biblioteca_referencias`); org members cannot suggest profiles | §3.2, §4, §5 |
| D3 | Import = **pure loader, no AI**: the 841 reference structures (already filled by the owner's in-session reference pass) + the 67 Máquina templates; the 52 unavailable records are dropped; provenance `fonte`/`referencia`/`ia_sugerido`/`admin`, filled fields usable by orgs at once, provenance visible to admins only; MCP tool, idempotent, dry-run first | §7 |
| D4 | AI picks from the brand's selected profiles (whole library if none), may mix (**max 3, confirmed**), must attribute Estrutura + blocks; resolves profile names in free text, asks when ambiguous; 4 surfaces; extend chat, don't fork; headline `[placeholders]` filled from the org's brains + bio | §8 |
| D5 | ONE unified chat; headlines cite their Estrutura(s); click → roteiro written immediately with defaults (duração `auto`, CTA-at-start = `ESTRUTURA_PADRAO`); old 8 conversations become unified | §6.5, §9 |
| D6 | Chosen headline + roteiro saved as real linked records (+ conversation); new top-level page "Headlines e Roteiros" | §3.3, §6.9, §10 |
| D7 | Roteiro generation auto-creates an Esteira card in "Headline + roteiro" awaiting roteiro approval (approval always required, S3), carrying brand/headline/roteiro/Estrutura(s)+profile/formato+duração+CTA order/generated caption; post generation/publishing out of scope | §9 |
| D8 | UI: Biblioteca tabs Perfis · Vídeos · Estruturas; profile page lists its Estruturas; Estrutura detail; admin-only edit; unified chat; combined page; nav keys stable (new keys only); no mockup gate | §11 |
| D9 | **Roteiros for ALL formats now** (reels = spoken script; carrossel = per-slide text; post = on-screen text + caption; stories = per-frame text) | §6.7, §8.7, §9 |
| D10 | **Platform ingestion org = the NoctusAI org** (the one holding the Meta + Apify credentials) | §4.3 |
| D11 | **A newly analysed viral video auto-creates a DRAFT Estrutura** (`rascunho`, never used for generation until an admin publishes it) | §3.1, §6.2, §13 EST-5 |
| D12 | **Block-type catalog** of 21 canonical types (+ `Outro`) is a platform table, admin-editable, seeded in M1 from `catalogo-blocos.json`; every block references it | §3.1, §6.1, §6.2 |

**Design calls (mine, reversible, flagged for the owner's validation — not owner decisions; DC1 was confirmed by the owner):**

- **DC1 · The roteiro is written by the existing roteiro pipeline, not by free chat text** (**confirmed**). Clicking a headline creates a `cs_roteiros` row through `RoteiroService` (job, `saida_ia` validation, S3 approval, versioning) and the chat shows it as a structured message with live status.
- **DC2 · Provenance is per field, as columns** (`*_origem ∈ fonte | referencia | ia_sugerido | admin`), not a jsonb blob. `fonte` = typed by the source system (CoreStudio / Máquina); `referencia` = filled by the owner's reference dataset (`preenchido_por`); `ia_sugerido` = filled by the app's AI (only the auto-draft and "a partir do vídeo" paths — **never the import**); `admin` = an admin typed or confirmed it.
  A field in `referencia` or `ia_sugerido` is **pending review**; confirm/edit by an admin sets `admin`. Orgs never see provenance.
- **DC3 · Estruturas are `status ∈ rascunho | ativa | arquivada`.** Only `ativa` is offered to orgs/AI; `referencia`/`ia_sugerido` fields do **not** block `ativa` (owner Q3). Loaded reference rows are `ativa` immediately; auto-drafts and "a partir do vídeo" are `rascunho` until an admin **publishes** (`POST …/publicar`).
- **DC4 · Headline proposals are server-parsed**, persisted rows (`cs_chat_propostas`), not FE-parsed markdown: a click needs a stable id and a validated Estrutura link. The FE parser is retired (drift-fix: single derivation).
- **DC5 · The platform ingestion org** (owner D10: the NoctusAI org). Ingestion, the Apify/Meta credentials, daily caps, the cost ledger and the transcription lane are all keyed on an `org_id`; platform-wide rows have none, so setting `corestudio_biblioteca_org_id` (DB-first then env) carries it (§4.3).
- **DC6 · Caption by format.** `post` roteiros already contain a `### Legenda` section, so for `post` the finalizer takes the caption from it (no second model call); reels/carrossel/stories use the existing `LegendaService` (made format-aware). (§9.3)
- **DC7 · A mix never crosses formats** (blocks mean seconds in one, slides in another): all Estruturas of one answer/roteiro share the principal's `formato`; the server enforces it (§8.5, §6.7).

## 2 · Glossary (pt-BR UI vocabulary, EN identifiers where the code already is EN)

**Estrutura** = headline formula + ordered **blocos**. **Perfil** = a monitored third-party Instagram profile (library). **Vídeo** = `cs_virais`. **Uso** = a recorded use of an Estrutura (`cs_estrutura_usos`).
**Proposta** = one headline option parsed from an assistant message. **Fluxo** = what happens when the user picks a proposta (headline saved → roteiro → card → caption).
**Ordem do CTA** = the existing `cta_inicio | cta_final`.

---

## 3 · Data (migrations M1–M4 + cleanup M5; numbers via `noctus.dev.next_migration_number` at slice time, never hand-picked)

All DDL: `SET search_path = social_wiring, public;`, idempotent, forward-safe, `lock_timeout` on every `ALTER` of an existing table, constraints on existing tables `NOT VALID` → `VALIDATE`.
**Every migration is backward-compatible with the previous image** (auto-rollback runs N-1 on N): M2/M3 only *add* or *relax*; nothing is dropped or tightened until M5 (≥ 2 deploys later).
Every new table: RLS enabled, `REVOKE ALL … FROM authenticated, anon`, a single `service_role` policy, `COMMENT ON TABLE … IS 'tier:<x>'`. **No new browser grant anywhere** (the API is the only reader).
Every append-only table gets the guard shape of S1's `cs_post_eventos` (`scaffold_migration with_eventos=True` / `with_guc_guard`) **and a `GuardProbe` in `verify_db_guards.py`** (keeper `check_migration_guard_has_probe`).
All state changes + their event row happen **in one SQL function (one PostgREST call = one transaction)**; the function names below are part of the contract.

### 3.1 M1 — `cs_estruturas` family + block-type catalog (needs 229; tier `platform`, no `org_id`)

**`cs_estrutura_tipos_bloco`** — the catalog of canonical block types. It is **our** content (written by the owner's team, no vendor text): the source of truth is NEW `estruturas_tipos_bloco.py`, whose rows are **copied from
`_private-studies/core-studio/estruturas-import/catalogo-blocos.json`** (`versao` 1, 21 rows `{tipo, tempo_tipico, instrucao_referencia}`) plus one system row `Outro`; the migration text is **generated** by `seed_sql()` and a test asserts the migration carries exactly that text
(the `geracao_taxonomias.py` pattern). The 21: Headline, Intensificador do Mistério, Revelação, Opinião Polêmica, Pontos de Identificação, Provas e Argumentações, Fatos Curiosos, Histórias Magnéticas, Notícia do Momento, Valor Prático, Contraste, Pergunta Reflexiva,
Apresentação Magnética, Encerramento, CTA Salvar, CTA Compartilhar, CTA Comentar, CTA Seguir, CTA Curtir, CTA Link/Produto, CTA.
| column | type / rule |
|---|---|
| `id` uuid PK · `nome` | text NOT NULL UNIQUE `1..80` (the 21 names above + `Outro`) |
| `ordem` | int NOT NULL UNIQUE (display order; the seed order) |
| `tempo_tipico` | text NULL `≤ 40` ("0–3s"; a hint, not a rule) |
| `instrucao_referencia` | text NOT NULL `1..600` (the canonical instruction; used as the fallback when a block has no instruction of its own, §8.1) |
| `ativo` | bool NOT NULL DEFAULT true |
| `sistema` | bool NOT NULL DEFAULT false — true only for `Outro`: cannot be renamed, deactivated or deleted |
| `versao` · `created_by`, `updated_by`, `created_at`, `updated_at` | |
**`cs_estrutura_tipo_eventos`** (append-only, no content): `id`, `tipo_id` uuid (no FK), `tipo` CHECK `IN ('criado','editado','ativado','desativado','excluido')`, `campo` text NULL, `ator_id`, `created_at`. `tier:platform`, `GuardProbe`.

**`cs_estruturas`**
| column | type / rule |
|---|---|
| `id` uuid PK · `codigo` bigint `GENERATED ALWAYS AS IDENTITY`, `UNIQUE` | the human id shown as "estrutura #codigo" (chat citation, deep link). New code space; viral `codigo` is no longer cited |
| `perfil_id` | uuid NOT NULL FK `cs_perfis_monitorados` **ON DELETE CASCADE** (opt-out purge must remove derived data; ordinary profile delete is guarded in the service, §4.2) |
| `viral_id` | uuid NULL FK `cs_virais` ON DELETE SET NULL (the source video); `UNIQUE (viral_id) WHERE origem = 'viral_auto'` (one auto-draft per video) |
| `formula_headline` | text NOT NULL, `char_length 1..1000`, trimmed; keeps its `[placeholder]`s |
| `formato` | text NULL CHECK `IN ('reels','carrossel','stories','post')` |
| `objetivos` | text[] NOT NULL DEFAULT `'{}'`, CHECK `objetivos <@ ARRAY['alcance','autoridade','conexao','venda']`, `cardinality ≤ 4`, no duplicates |
| `status` | CHECK `IN ('rascunho','ativa','arquivada')`; CHECK `status <> 'ativa' OR (formato IS NOT NULL AND cardinality(objetivos) >= 1)` |
| `origem` | CHECK `IN ('manual','import_corestudio','import_maquina','viral_auto')` |
| `fonte_externa` / `ref_externa` | text NULL / text NULL; CHECK both null or both set; `UNIQUE (fonte_externa, ref_externa) WHERE ref_externa IS NOT NULL`. The CoreStudio id (bare digits, `corestudio_id`) or Máquina molde id — **never our PK**, only the load's idempotency key |
| `fonte_hash` | text NULL: sha256 of the normalised source row (a re-load detects change) |
| `formula_herdada_de` | text NULL: the `corestudio_id` of the sibling whose formula a variant inherited (informational, from the reference dataset) |
| `referencia_rotulo` | text NULL: the dataset's `preenchido_por` label (e.g. `claude-code-referencia-2026-11-15`) for rows carrying `referencia` fields |
| `formula_origem`, `formato_origem`, `objetivos_origem` | CHECK `IN ('fonte','referencia','ia_sugerido','admin')`, NOT NULL DEFAULT `'admin'` |
| `versao` | int NOT NULL DEFAULT 1 (optimistic concurrency, bumped by every RPC) |
| `created_by`, `updated_by` (uuid NULL = system), `created_at`, `updated_at`, `arquivada_em`, `publicada_em` | |

Indexes: `(perfil_id, status)`; GIN `to_tsvector('portuguese', formula_headline)`; `(status, formato)`; `(viral_id) WHERE viral_id IS NOT NULL`.

**`cs_estrutura_blocos`**
| column | type / rule |
|---|---|
| `id` uuid PK · `estrutura_id` FK `cs_estruturas` ON DELETE CASCADE | |
| `ordem` | int NOT NULL ≥ 1; `UNIQUE (estrutura_id, ordem) DEFERRABLE INITIALLY DEFERRED` (reorder in one statement) |
| `tipo_id` | uuid NOT NULL FK `cs_estrutura_tipos_bloco` **ON UPDATE CASCADE ON DELETE RESTRICT** (a type in use cannot be deleted; `Outro` for anything outside the catalog) |
| `nome` | text NOT NULL `1..120` — the block's own display name (CoreStudio `nome_original`, e.g. "Opiniões Polêmicas encadeadas"); the **type** is the canonical class |
| `tempo` | text NULL `≤ 40` — time **or slide/frame label** ("3–7s", "slide 2", "legenda 1", "imagem") |
| `instrucao` | text NULL `≤ 2000` |
| `nota` | text NULL `≤ 600` — the source's parenthetical (describes the original video's content; shown, not templated; empty string is stored as NULL) |
| `repeticoes` | int NOT NULL DEFAULT 1 CHECK `1..20` — "Opinião Polêmica × 2" |
| `nome_origem`, `tipo_origem`, `tempo_origem`, `instrucao_origem` | CHECK `IN ('fonte','referencia','ia_sugerido','admin')`, NOT NULL DEFAULT `'admin'` |

**`cs_estrutura_eventos`** (append-only; the history of every change, **no content**, so an opt-out purge leaves nothing personal)
| column | type / rule |
|---|---|
| `id` · `estrutura_id` uuid NOT NULL **(no FK: history outlives a hard delete)** · `perfil_id` uuid NULL | |
| `tipo` | CHECK `IN ('criada','criada_automatica','importada','atualizada_import','ia_preenchida','campo_editado','campo_confirmado','bloco_adicionado','bloco_removido','blocos_reordenados','publicada','arquivada','restaurada','excluida')` |
| `campo` | text NULL: `formula_headline \| formato \| objetivos \| bloco.<bloco_id>.nome\|tipo\|tempo\|instrucao\|nota\|repeticoes` |
| `origem_anterior`, `origem_nova` | CHECK `IN ('fonte','referencia','ia_sugerido','admin')` NULL (feeds the confirmation metrics, §10) |
| `ator_id` uuid NULL · `ator_tipo` CHECK `IN ('admin','sistema_import','sistema_ia')` | |
| `importacao_id` uuid NULL · `versao` int NOT NULL (the `cs_estruturas.versao` after the change) · `created_at` | |

**`cs_estrutura_importacoes`** (one row per load run — state, plus `cs_estrutura_eventos.importacao_id` for the per-row trail)
`id`, `fonte` CHECK `IN ('referencia','maquina_de_roteiros')`, `arquivo_sha256` text NOT NULL, `arquivo_nome` text, `status` CHECK `IN ('simulada','em_andamento','concluida','falhou')`, `dry_run` bool,
counters (all int NOT NULL DEFAULT 0): `linhas_total, perfis_criados, perfis_mesclados, estruturas_criadas, estruturas_atualizadas, estruturas_inalteradas, estruturas_ignoradas, blocos_criados`,
`ignoradas_motivos` jsonb `{motivo: n}` (a histogram, not a business list), `erro` text, `iniciada_por` uuid, `created_at`, `finished_at`. **No cost/budget columns: the load never calls a model.**

**`cs_estrutura_usos`** (append-only fact table; the join that makes "which Estrutura served this post" a query, §10)
`id`, `org_id` FK, `marca_id` FK CASCADE, `estrutura_id` FK `cs_estruturas` **ON DELETE RESTRICT**, `contexto` CHECK `IN ('chat','lote_headlines','roteiro_avancado')`,
`papel` CHECK `IN ('principal','mistura')`, `ordem` smallint ≥ 1, `bloco_ids` uuid[] NOT NULL DEFAULT `'{}'`, `headline_id` uuid NULL FK `cs_headlines` ON DELETE SET NULL,
`roteiro_id` uuid NULL FK `cs_roteiros` ON DELETE SET NULL, `proposta_id` uuid NULL, `created_by`, `created_at`;
**No CHECK on "at least one link"** (the `ON DELETE SET NULL` actions would trip it): the service guarantees at least one of `headline_id | roteiro_id | proposta_id` at insert. `UNIQUE (estrutura_id, roteiro_id) WHERE roteiro_id IS NOT NULL`, same for `headline_id` (a retry never double-counts).
Guard: append-only **with the FK-action carve-outs** (`ON DELETE SET NULL` on the two FKs is an UPDATE; org/marca cascade is a DELETE) — implement with `guc_carveout_guard_sql`/`pg_trigger_depth()`, probe both the refusal and the carve-out.

**View `cs_estruturas_resumo`** (derived, never stored): per estrutura `blocos_total`, `campos_pendentes` = count of `referencia` or `ia_sugerido` over the 3 estrutura columns + (`tipo`, `tempo`, `instrucao`) × blocks. Used by the admin "pendentes de revisão" filter. `security_invoker`, service-only.

**RPCs (service role only, `SECURITY DEFINER` ⇒ `REVOKE EXECUTE … FROM PUBLIC, anon, authenticated` in the same file, `SET search_path`)** — each locks the row, checks `expected_versao`, mutates, bumps `versao`, writes the event(s):
`cs_estrutura_criar(p jsonb)` · `cs_estrutura_atualizar(p_id, p_expected_versao, p_patch jsonb, p_ator uuid)` · `cs_estrutura_substituir_blocos(p_id, p_expected_versao, p_blocos jsonb, p_ator)` ·
`cs_estrutura_confirmar(p_id, p_expected_versao, p_campos text[], p_ator)` · `cs_estrutura_publicar(p_id, p_expected_versao, p_ator)` (`rascunho → ativa`; raises when formato / objetivos / ≥ 1 block missing) ·
`cs_estrutura_arquivar(p_id, p_ator)` / `cs_estrutura_restaurar(p_id, p_ator)` · `cs_estrutura_excluir(p_id, p_ator)` (raises when a `cs_estrutura_usos` row exists) ·
`cs_estrutura_tipo_salvar(p jsonb)` / `cs_estrutura_tipo_excluir(p_id, p_ator)` (raises when a block references the type or the row is `sistema`; one event each).
A stale `p_expected_versao` raises a coded exception mapped to 409 `versao_desatualizada`. Provenance rule inside the RPCs: a field the patch changes gets `*_origem = 'admin'` and one `campo_editado` event; `confirmar` flips `referencia`/`ia_sugerido → admin` without touching content (a `fonte` field is authoritative and never "pending").
Tier comments: `cs_estruturas`, `cs_estrutura_blocos`, `cs_estrutura_eventos`, `cs_estrutura_importacoes`, `cs_estrutura_tipos_bloco`, `cs_estrutura_tipo_eventos` = `tier:platform`; `cs_estrutura_usos` = `tier:org` (org-keyed, still service-only).

### 3.2 M2 — platform-scope move of the library (expand only; needs M1 only for the opt-out cascade test)
- `cs_perfis_monitorados`: `ALTER … org_id DROP NOT NULL`; **add** `monitorar boolean NOT NULL DEFAULT true` (library-only profiles — imported, no ingestion — are `false`); **add** `UNIQUE (rede, handle) WHERE org_id IS NULL` (the old `(org_id, rede, handle)` index stays for N-1);
  `DROP POLICY cs_perfis_monitorados_select_own_org`; `REVOKE ALL … FROM authenticated, anon`; `COMMENT … 'tier:platform'`. New rows are written with `org_id = NULL`.
- `cs_virais`: `org_id DROP NOT NULL`; `UNIQUE (codigo)` (the identity column is already globally unique; the per-org unique stays for N-1); drop `…_select_own_org`; REVOKE; `tier:platform`.
- `cs_biblioteca_referencias`: **unchanged shape** (per marca/org stays); its `perfil_id`/`viral_id` FKs now point at platform rows. `cs_biblioteca_optouts`: unchanged.
- `cs_virais` also gets (admin "add by link", §4.2): `ig_shortcode` text NULL with `UNIQUE (ig_shortcode) WHERE ig_shortcode IS NOT NULL` (an Instagram shortcode is globally unique; the existing `UNIQUE (perfil_id, ig_media_id)` is the other dedupe key), `origem_inclusao` text NOT NULL DEFAULT `'sync'` CHECK `IN ('sync','link_manual')`, `incluido_por` uuid NULL.
- **New `cs_perfil_eventos`** (append-only, who/when/what for the admin-only profile and video writes): `perfil_id` (no FK), `viral_id` uuid NULL (no FK), `handle`, `tipo` CHECK `IN ('criado','editado','pausado','retomado','sincronizacao_solicitada','monitorar_ligado','monitorar_desligado','excluido','optout_purgado','importado','video_adicionado_por_link')`, `ator_id`, `ator_tipo`, `created_at`. `tier:platform`.
- Why not drop `org_id` now: N-1 selects/filters on it; M5 drops it after ≥ 2 deploys (0 rows, so the late contraction is free).

### 3.3 M3 — unified chat, propostas, fluxo ledger (needs 229, 241, M1)
- `cs_chat_conversas.agente`: `DROP CONSTRAINT … ; ADD CONSTRAINT … CHECK (agente IN ('headline','roteiro','unificado')) NOT VALID; VALIDATE`. **No backfill in M3**: the N code *reads* any value as unified and writes `'unificado'` (so N-1 still lists the 8 old ones by their old value). M5 backfills + tightens.
- `cs_chat_mensagens`: `ADD COLUMN tipo text NOT NULL DEFAULT 'texto' CHECK (tipo IN ('texto','roteiro_gerado'))`; `ADD COLUMN proposta_id uuid NULL` with `UNIQUE (proposta_id) WHERE proposta_id IS NOT NULL` (the `roteiro_gerado` message is inserted exactly once per proposta).
- **`cs_chat_propostas`** (tier `org`, service-only): `id`, `org_id`, `marca_id`, `conversa_id` FK CASCADE, `mensagem_id` FK `cs_chat_mensagens` CASCADE, `ordem` smallint ≥ 1 (`UNIQUE (mensagem_id, ordem)`),
  `texto` 1..1000 (the headline, citation and gatilho tag stripped), `gatilho_tag` text NULL, `status` CHECK `IN ('proposta','escolhida')`, `fluxo_etapa` CHECK `IN ('headline_salva','roteiro_criado','card_criado','concluido','falhou')` NULL (NULL while `proposta`),
  `fluxo_erro_codigo` text NULL, `fluxo_lease_ate` timestamptz NULL (resume lease), `headline_id` uuid NULL FK `cs_headlines` ON DELETE SET NULL, `escolhida_por` uuid, `escolhida_em`, `created_at`.
- **`cs_chat_proposta_estruturas`**: `proposta_id` FK CASCADE, `estrutura_id` FK `cs_estruturas` ON DELETE CASCADE, `ordem` smallint ≥ 1, `principal` bool; `PK (proposta_id, estrutura_id)`; at most one `principal` per proposta (partial unique). Max 3 per proposta: `CHECK (ordem BETWEEN 1 AND 3)` + `PK (proposta_id, estrutura_id)`.
- **`cs_fluxo_eventos`** (append-only, tier `org`, no FKs except `org_id`/`marca_id`): `id`, `org_id`, `marca_id`, `conversa_id` uuid, `proposta_id`/`mensagem_id`/`headline_id`/`roteiro_id`/`post_id` uuid NULL, `ator_id` uuid NULL (NULL = system),
  `tipo` CHECK `IN ('propostas_geradas','proposta_escolhida','headline_salva','roteiro_criado','roteiro_gerado','roteiro_falhou','card_criado','card_falhou','legenda_gerada','legenda_falhou','fluxo_concluido','fluxo_retomado','perfil_resolvido','perfil_ambiguo','perfil_nao_encontrado','citacao_rejeitada','atribuicao_ausente','placeholder_remanescente','formato_misturado')`,
  `contagem` int NULL (e.g. how many citations were rejected), `codigo` text NULL (an error/reason code, or the sha256 on `legenda_gerada` — never text), `created_at`.
- `cs_headlines`: `ADD COLUMN conversa_id uuid NULL REFERENCES cs_chat_conversas ON DELETE SET NULL`, `ADD COLUMN proposta_id uuid NULL`; `UNIQUE (conversa_id, proposta_id) WHERE proposta_id IS NOT NULL`.
- `cs_roteiros`: `ADD COLUMN conversa_id uuid NULL REFERENCES cs_chat_conversas ON DELETE SET NULL` (linked to the conversation; the headline link already exists); `ADD COLUMN formato text NOT NULL DEFAULT 'reels' CHECK (formato IN ('reels','carrossel','stories','post'))` (every existing row is a Reels script, so the default is the truthful backfill; `ordem_cta` stays the legacy `estrutura` column).
- `cs_posts`: **relax** `cs_posts_formato_check` from `IN ('reel')` to `IN ('reel','carrossel','story','feed')` (S1's vocabulary; relaxing is backward-compatible with N-1). `reels→reel, carrossel→carrossel, stories→story, post→feed` in `estruturas_formatos.py`. The CHECK is the card's truth about what it carries; asset/publication targeting stays S1/S4/S7's.
- `status_pagina`: `INSERT ('media-creation-headlines-roteiros','desenvolvimento') ON CONFLICT DO NOTHING` (the page is owner/dev-only until validated; unlisted pages are hidden).
- **S3 interplay:** S3's migration touches `cs_roteiros`/approvals; M3 adds one nullable column there — independent, but the two migrations enqueue one after the other so the queue re-checks numbering.

### 3.4 M4 — metrics views (wave 3, after S3 lands; needs the approvals tables) — §10.
### 3.5 M5 — cleanup (≥ 2 deploys after M3; owner-gated; **not** part of this release)
Drop `org_id` from `cs_perfis_monitorados`/`cs_virais`; backfill `cs_chat_conversas.agente = 'unificado'` + `CHECK (agente = 'unificado')`; stop writing/drop `cs_virais.blueprint`, `blueprint_slots` (§3.6); optionally rename the beat-order field (`estrutura` → `ordem_cta`).

### 3.6 Deprecation of the per-viral blueprint (decision, documented)
`cs_virais.blueprint` / `blueprint_slots` stay **readable and untouched** (the classifier `prompts/biblioteca_classificador.py` keeps producing them; no code outside the classifier and §6.2 `a-partir-do-viral` reads them). **Nothing in retrieval, headline generation, chat or roteiro reads them after this release** — they are replaced by `cs_estruturas`.
`ViralDetalhe.estrutura_utilizavel`/`blueprint` stay in the response (deprecated, FE stops using them; the UI shows the video's Estruturas instead). The classifier itself still only writes the blueprint; the **auto-draft** Estrutura is a separate post-classification step (§8.8, owner D11). Drop in M5.

---

## 4 · Platform scope: tiers, the org-scope inventory, the ingestion org

### 4.1 Tiers (per `KB § PATTERNS/security/access-tiers.md`)

| Surface | Tier | Gate | Notes |
|---|---|---|---|
| Tables `cs_estruturas*`, `cs_perfis_monitorados`, `cs_virais`, `cs_estrutura_importacoes`, `cs_perfil_eventos` | `platform` | service role only, no browser grant/policy | Platform IP: the curated corpus. The API is the only door |
| Tables `cs_estrutura_usos`, `cs_chat_propostas*`, `cs_fluxo_eventos` | `org` (service-only) | service role only | org-keyed facts |
| **Reads** of the library (`GET /estruturas…`, `GET /biblioteca/perfis\|virais…`) | `org` | `get_current_user_org` | Deliberate: members browse/choose. Response models are explicit (no `select("*")`); paged (≤ 50); **no export/CSV route**; admin-only fields (`proveniencia`, `ref_externa`, `pendente_revisao`, non-`ativa` rows) are stripped for non-admins by the service, proven by a test |
| **Writes** (create/edit/delete/confirm/import/sync of profiles, videos' sync, Estruturas) | `platform` | `require_platform_admin` (403 plain string) | routers built with `make_router(tier="platform", guard=require_platform_admin)` ⇒ `include_in_schema=False`; reads and writes live in **separate routers** so a read can never inherit a write gate or vice-versa |
| `GET /estruturas/admin` (`{is_admin}`) | `org` | `get_current_user_org` + `@access_tier('org', reason="returns the caller's own is_admin flag, nothing else")` | mirrors `GET /treinamentos/admin` |
| Chat / fluxo / headlines-roteiros / esteira origem | `org` | `get_current_user_org`; chat additionally `user_id`-private | |

`PLATFORM_IP_ROUTES['social-wiring']` gets the **write** path shapes (`/api/media-creation/estruturas/importacoes…`, `…/estruturas` non-GET, `…/biblioteca/perfis` non-GET) so a future weaker dependency is `too-open`. Auth tests assert strict `== 401` (no token) and strict `== 403` (org user on a platform route); regenerate `noctus.dev.access_tier_catalog --write`.

### 4.2 Biblioteca router/service changes (`routers/biblioteca.py`, `services/biblioteca_service.py`)
| Endpoint | Before | After |
|---|---|---|
| `GET /biblioteca/perfis` | org's profiles (array, ≤ 30) | library-wide, **paged**: `?marca_id?&q?&limit(≤50,def 30)&offset` → `{"data":{"items":[PerfilMonitorado],"total":n}}`; each item has `selecionado_pela_marca` when `marca_id` is given. (**Breaking shape**: FE-1 ships with it; the array form is retired) |
| `GET /biblioteca/perfis/{id}` | — | new, any member: `PerfilMonitorado` + `estruturas_total` |
| `POST /biblioteca/perfis` | org member requests a profile (+ adds a reference) | **admin**; body `{handle, conta_descoberta_id?, monitorar?: bool=true}` (`marca_id` accepted-and-ignored one release); 201; opt-out ⇒ 409 `perfil_optout`; dup ⇒ 409 `perfil_ja_existe`; cap `biblioteca_max_perfis_plataforma` (new, 1000) ⇒ 409 `limite_perfis` |
| `POST …/perfis/{id}/sincronizar`, `PATCH …/perfis/{id}`, `GET …/perfis/verificar`, `GET …/contas-descoberta` | org member | **admin** |
| **`POST /biblioteca/virais/por-link`** → 201 (200 `ja_existia`) | — (new) | **admin** (tier `platform`, `make_router(tier="platform")`); `@limiter` (AI/ingestion rate); body `{url}`: an `https://(www.)?instagram.com/(p\|reel\|reels\|tv)/<shortcode>/…` link. Flow: parse the shortcode (422 `link_invalido`); **dedupe** — `cs_virais.ig_shortcode` (or `(perfil_id, ig_media_id)` once fetched) already present ⇒ 200 `{viral, ja_existia:true}` and nothing else happens; fetch the single post through the active `biblioteca_fonte` (Apify) with the ingestion org's token; resolve the owner handle; opted-out ⇒ 409 `perfil_optout`; the profile is created if absent (`monitorar=false`, event `criado`); insert the viral through the **same normaliser** as the sync (`origem_inclusao='link_manual'`, `incluido_por`, event `video_adicionado_por_link`); enqueue the **same** thumbnail → transcribe → classify jobs as a synced video (a manually added video is analysed regardless of the viral threshold — the admin chose it). Response `{data:{viral: ViralCard, perfil_criado: bool, ja_existia: bool}}`. Errors: 404 `post_nao_encontrado`, 409 `fonte_nao_suporta_link` (the active source cannot fetch a single post; **the slice verifies the Apify actor accepts a post URL — unverified here**), 503 `ingestao_sem_org_plataforma`, existing 503s |
| `DELETE …/perfis/{id}` | org member | **admin**; 409 `perfil_com_estruturas` + `{estruturas_total}` unless `?apagar_estruturas=true` (the opt-out purge passes it). 204 |
| `PATCH …/perfis/{id}` | `status`, `conta_descoberta_id` | + `monitorar`, `nome` (display override). Every change writes `cs_perfil_eventos` |
| `/referencias*` (per marca) | org | **unchanged** (org tier, brand-scoped): `POST` now validates the target against the **platform** library; `biblioteca_max_perfis_org` (30) now caps **selected profiles per brand** (`_assert_ref_capacity`), message unchanged |
| `GET /virais`, `GET /virais/{id}` | org rows | platform rows, same shape; `ViralDetalhe` + `estruturas: EstruturaRef[]` |
| `/admin/optouts*` | platform admin | unchanged; the purge now cascades Estruturas (§4.3 #7) |

### 4.3 Every code path that assumes org scope (each must change; the slice's acceptance names them)
| # | Path | Org assumption today | After |
|---|---|---|---|
| 1 | `services/biblioteca_service.py :: _org_perfis`, `_perfil_row`, `_find_perfil`, `criar_perfil`, `_perfis_by_id`, `list_virais` filters | `.eq("org_id", self.org_id)` | no org filter on library tables; `org_id` stays only for `cs_biblioteca_referencias` and credentials |
| 2 | `services/biblioteca_ingestao.py` (sync handler): `perfil["org_id"]`, `_default_conta`, Meta adapter `(account_id, org_id)`, Apify token `resolve_api_key("apify_api_token", org_id)`, storage paths `{org_id}/{perfil}/…`, thumbnail puts, `viral["org_id"]` in transcribe/classify | the profile's org | **the platform ingestion org = the NoctusAI org** (owner D10; `settings.corestudio_biblioteca_org_id`, set to that org's id); storage path becomes `platform/{perfil}/{ig_media_id}.jpg` (new rows; old path shape unreadable-safe because 0 rows). Missing/invalid setting ⇒ job `falha` with `erro_codigo=ingestao_sem_org_plataforma` (never silent) |
| 3 | `services/biblioteca_fonte.py :: resultados_hoje(org_id)`, `registrar_uso` (Apify cost ledger) | per org | ledger keyed on the ingestion org; caps `biblioteca_apify_resultados_dia_org`, `biblioteca_classificacoes_dia_org`, `biblioteca_transcricao_*` keep their names and now mean "platform ingestion org" (comment + `config.py` docstring) |
| 4 | `services/biblioteca_transcricao.py :: validar/aplicar`, `transcricoes` lane `origem='biblioteca'` (needs `org_id` + `user_id`) | the profile's `created_by` | the ingestion org + a **system user id** (`corestudio_biblioteca_user_id` setting, DB-first) |
| 5 | `biblioteca_scheduler.py :: enqueue_daily_syncs, sweep_pendentes, _perfis_referenciados, purgar_expirados, varrer_blobs_orfaos` (+ `run_*`) | per-org loops; "referenced" = by a brand | iterate platform profiles with `monitorar = true`; **retention (90 d, `biblioteca_retencao_dias`)**: a profile is exempt from the unreferenced purge while it has ≥ 1 non-`arquivada` Estrutura **or** `monitorar = false`; its viral media/transcripts/thumbnails are still purged by age (the Estruturas are the retained derived data). `_perfis_referenciados` = referenced by a brand ∪ has Estruturas ∪ `monitorar=false` |
| 6 | `services/viral_card.py :: viral_cards` (`PERFIS … select("id,org_id,…")`, `purgar_perfil(db, storage, str(p["org_id"]), p)`) | per org | no org; purge by platform path |
| 7 | `services/biblioteca_service.py :: purgar_perfil / purgar_handle` + `biblioteca_optout.registrar` (LGPD opt-out) | deletes the org's rows | deletes the **platform** profile + virais + blobs **and its Estruturas** (FK cascade) and writes `cs_perfil_eventos.optout_purgado` + `cs_estrutura_eventos.excluida` (no content); the response `purgados` gains `estruturas: n`; the **load also refuses** opted-out handles (§7.3) |
| 8 | `services/headline_pipeline.py :: carregar_candidatos(db, org_id)`, `carregar_virais_por_id`, `referencias_da_marca`, `pool_de_estruturas`; `headline_service.py` (`contagem_estruturas`, `_viral…`) | candidates = the org's classified virais with a blueprint | candidates = `ativa` Estruturas (§8.2); `referencias_da_marca` unchanged (brand-scoped) |
| 9 | `services/chat_contexto.py :: _allowlist, _viral_permitido, _resolver_biblioteca, _pool_estruturas, _mencoes_biblioteca` | org-scoped library | platform library, brand selection from `cs_biblioteca_referencias` |
| 10 | `services/roteiro_service.py :: _exists(VIRAIS…)`, `_contexto` (viral reference), `_viral_for` | `.eq("org_id")` on virais | no org filter on virais; Estruturas via §8 (**wave 3, after S3**) |
| 11 | RLS `…_select_own_org` on both tables; FE direct reads | browser SELECT | dropped (the FE never read them directly — verified: no `supabase.from` on these tables) |
| 12 | `tests/modules/media_creation/test_geracao_biblioteca_*`, `test_headline_pipeline`, `test_geracao_chat`, `test_geracao_scheduler`, `test_biblioteca_*`, `tests/conftest.py` fixtures | seed rows with `org_id` | updated with the slice that owns the code path (EST-2/EST-4a/EST-4b) |

---

## 5 · Endpoint conventions (apply to every endpoint below)
Prefix `/api/media-creation`; envelope §0.1; errors §0.2; strict request models (`StrictHttpModel`, `extra="forbid"`; **no `from __future__ import annotations` on slowapi-wrapped routes**); AI routes `@limiter.limit(DEFAULT_AI_RL)`;
`success_response`. A foreign/unknown id is 404. All text is pt-BR. Marca-scoped endpoints take `marca_id` and 404 a foreign marca. `is_admin` = `get_platform_admin_check`.

**Error code catalog (new; HTTP status · `code` · message):**
| code | status | message (pt-BR) |
|---|---|---|
| `versao_desatualizada` | 409 | "Esta estrutura foi alterada por outra pessoa. Recarregue e tente de novo." |
| `estrutura_em_uso` | 409 | "Esta estrutura já foi usada em headlines ou roteiros. Arquive-a em vez de excluir." |
| `estrutura_inativa` | 409 | "Esta estrutura não está ativa." |
| `perfil_com_estruturas` | 409 | "Este perfil tem estruturas. Confirme para apagá-las também." (+ `estruturas_total`) |
| `perfil_optout` | 409 | "Este criador pediu para não ser monitorado." |
| `perfil_ja_existe` | 409 | "Este perfil já está na biblioteca." |
| `limite_perfis` | 409 | "A biblioteca atingiu o limite de perfis." |
| `perfil_ambiguo` | 422 | "Mais de um perfil combina com \"{trecho}\". Escolha um." (+ `candidatos`) |
| `perfil_nao_encontrado_na_biblioteca` | 422 | "Não encontramos \"{trecho}\" na biblioteca." (+ `sugestoes`) |
| `estrutura_obrigatoria_invalida` | 422 | "Uma das estruturas escolhidas não está disponível." |
| `muitas_estruturas` | 422 | "Escolha no máximo 3 estruturas." |
| `simulacao_obrigatoria` | 409 | "Rode a simulação deste arquivo antes de aplicar." |
| `importacao_em_andamento` | 409 | "Já existe uma importação em andamento." |
| `arquivo_invalido` | 422 | "O arquivo de importação não tem o formato esperado." (+ `motivo`) |
| `link_invalido` | 422 | "Cole o link de um post do Instagram (instagram.com/p/…, /reel/… ou /tv/…)." |
| `post_nao_encontrado` | 404 | "Não encontramos este post (privado ou removido)." |
| `fonte_nao_suporta_link` | 409 | "A fonte de ingestão atual não consegue buscar um post avulso." |
| `tipo_em_uso` | 409 | "Este tipo de bloco está em uso. Desative-o em vez de excluir." |
| `tipo_protegido` | 409 | "O tipo \"Outro\" é do sistema e não pode ser alterado." |
| `rascunho_incompleto` | 422 | "Para publicar, informe formato, ao menos um objetivo e ao menos um bloco." (+ `faltando`) |
| `formatos_misturados` | 422 | "As estruturas escolhidas têm formatos diferentes. Escolha estruturas do mesmo formato." |
| `formato_diferente_da_estrutura` | 422 | "O formato pedido é diferente do formato da estrutura escolhida." |
| `ingestao_sem_org_plataforma` | 503 | "A organização de ingestão da biblioteca não está configurada." |
| `proposta_nao_encontrada` | 404 | "Headline não encontrada." |
| `viral_sem_conteudo` | 422 | "Este vídeo ainda não tem conteúdo para gerar uma estrutura." |
| `viral_sem_estrutura` | 422 | "Este vídeo ainda não tem estruturas." |
| `fluxo_em_andamento` | 200 body `em_andamento:true` | (idempotent re-click, not an error) |
| `limite_diario_roteiros` | 429 + `Retry-After` | existing roteiro cap message |
| `ia_nao_configurada` / `orcamento_ia_excedido` / `geracao_indisponivel` | 503 | existing messages |
Reused unchanged: `stream_em_andamento` 409, `limite_de_mensagens` 429, `sem_roteiro` 422, `headline_ja_em_post` 409, `pendencias` 409.

---

## 6 · API contract

### 6.0 Shared shapes (TS types are §11.1; these are the exact JSON field names)
- `EstruturaPerfilRef` = `{id, handle, nome|null, foto_url|null}`.
- `TipoBloco` = `{id, nome, ordem, tempo_tipico|null, instrucao_referencia, ativo}` (non-admins only receive `ativo` rows).
- `Bloco` = `{id, ordem, nome, tipo: {id, nome}, tempo|null, instrucao|null, nota|null, repeticoes}`; **admin only** adds `proveniencia: {nome, tipo, tempo, instrucao}` each `fonte|referencia|ia_sugerido|admin`.
- `EstruturaResumo` = `{id, codigo, perfil: EstruturaPerfilRef, formula_headline, formato|null, objetivos[], blocos_total, viral: {id, codigo, permalink, thumbnail_url|null}|null, status, selecionada_pela_marca?, updated_at}`; **admin only** adds `pendente_revisao: bool` (any field `referencia` or `ia_sugerido`). Non-admins only ever receive `status: "ativa"` rows.
- `EstruturaDetalhe` = `EstruturaResumo & {blocos: Bloco[], versao}`; **admin only** adds `origem`, `ref_externa|null`, `referencia_rotulo|null`, `formula_herdada_de|null`, `proveniencia: {formula_headline, formato, objetivos}` (each `fonte|referencia|ia_sugerido|admin`).
- `EstruturaRef` = `{id, codigo, perfil: {id, handle, nome|null}, formula_trecho}` (`formula_trecho` ≤ 120 chars).
- `EstruturaUso` = `EstruturaRef & {papel: "principal"|"mistura", blocos: {id, nome}[]}` (`nome` = the block's display name).

### 6.1 Estruturas — reads (`routers/estruturas.py`, tier `org`)
| Method + path | Request | Response / codes |
|---|---|---|
| `GET /estruturas` | `marca_id?` (adds `selecionada_pela_marca`; 404 foreign), `perfil_id?`, `q?` (≤200, tsquery over formula + block names), `formato?` (repeat), `objetivo?` (repeat), `status?` (admin only: `ativa\|rascunho\|arquivada\|todas`; ignored for non-admin), `somente_pendentes_revisao?` (admin), `limit` (1..50, def 20), `offset` | `{data:{items: EstruturaResumo[], total}}` |
| `GET /estruturas/{id}` | — | `{data: EstruturaDetalhe}` · 404 (also for `rascunho\|arquivada` to a non-admin) |
| `GET /estruturas/admin` | — | `{data:{is_admin}}` |
| `GET /estruturas/tipos-bloco` | — | `{data: TipoBloco[]}` ordered by `ordem` (non-admins: `ativo` only; the block editor, the Estrutura detail and the AI prompts read it) |
| `GET /estruturas/resolver-perfil` | `texto` (1..300), `marca_id?` | `{data: ResolucaoPerfis}` — the same deterministic resolver the AI uses (§8.3); FE chips + tests |
`ResolucaoPerfis = {resolvidos: [{perfil_id, handle, nome, via: "mencao"|"handle"|"nome", confianca: number}], ambiguos: [{trecho, candidatos: [{perfil_id, handle, nome}]}], nao_encontrados: [{trecho, sugestoes: [{perfil_id, handle, nome}]}]}`.
Static paths (`/admin`, `/tipos-bloco`, `/resolver-perfil`, `/importacoes`) are declared **before** `/{id}`. Profile page data: `GET /estruturas?perfil_id=…` + `GET /biblioteca/perfis/{id}` (no extra endpoint).

### 6.2 Estruturas — admin writes (`routers/estruturas_admin.py`, tier `platform`; every write returns the fresh `EstruturaDetalhe` with admin fields)
| Method + path | Request | State change · errors |
|---|---|---|
| `POST /estruturas` → 201 | `{perfil_id, viral_id?, formula_headline, formato, objetivos[1..4], blocos: [{nome, tipo_id, tempo?, instrucao?, nota?, repeticoes?}] (1..60), status?: "rascunho"\|"ativa" = "ativa"}` | `cs_estrutura_criar`; all provenance `admin`, `origem='manual'`, event `criada`. 404 perfil/viral/tipo; 422 (shape; `ativa` needs formato + ≥ 1 objetivo + ≥ 1 block); 409 `perfil_optout` |
| `PATCH /estruturas/{id}` | `{expected_versao, formula_headline?, formato?, objetivos?, viral_id?}` (≥ 1 field; **status never changes here** — see publicar/arquivar) | `cs_estrutura_atualizar`; changed fields → `admin`, `campo_editado` event(s); 409 `versao_desatualizada`; 409 `estrutura_inativa` when editing `arquivada` |
| `PUT /estruturas/{id}/blocos` | `{expected_versao, blocos: [{id?, nome, tipo_id, tempo?, instrucao?, nota?, repeticoes?}] (1..60)}` full ordered replace (position = `ordem`) | `cs_estrutura_substituir_blocos`: block with `id` keeps identity + provenance for unchanged fields (changed → `admin`), no `id` = new (`admin`), absent = removed; events `bloco_adicionado\|bloco_removido\|blocos_reordenados\|campo_editado`. 422 unknown `id`/`tipo_id`, dup ids; 409 `versao_desatualizada` |
| `POST /estruturas/{id}/confirmar` | `{expected_versao, campos: string[] (field grammar §3.1) \| todos: true}` (exactly one) | `cs_estrutura_confirmar`: `referencia`/`ia_sugerido → admin`, event `campo_confirmado` per field; confirming a non-pending field is a no-op (200). 422 unknown field |
| `POST /estruturas/{id}/publicar` | `{expected_versao}` | `rascunho → ativa`, `publicada_em`, event `publicada` (the **only** way an auto-draft/"a partir do vídeo" draft becomes usable by orgs/AI); 422 `rascunho_incompleto` + `faltando`; 409 `estrutura_inativa` if not `rascunho` |
| `POST /estruturas/{id}/arquivar` · `/restaurar` | — | `ativa ↔ arquivada` (`restaurar` returns to `ativa`; a `rascunho` can be archived too); `arquivada_em`; event. Archiving is how a used Estrutura "dies" |
| `DELETE /estruturas/{id}` → 204 | — | hard delete only when no `cs_estrutura_usos`; else 409 `estrutura_em_uso`; event `excluida` |
| `POST /estruturas/a-partir-do-viral` → 201 | `{viral_id}` | creates a **`rascunho`** (`origem='manual'`, perfil = the video's, `viral_id` set) whose formula, formato, objetivos and typed blocks are AI-derived from the video's `blueprint`/transcription/caption (EST-5), every field `ia_sugerido`, event `ia_preenchida`. 422 `viral_sem_conteudo` if the video has no blueprint/transcription/caption; 409 if a non-archived Estrutura already links that video as `viral_auto` |
| `POST /estruturas/tipos-bloco` → 201 · `PUT /estruturas/tipos-bloco/{id}` · `DELETE /estruturas/tipos-bloco/{id}` → 204 | `{nome, tempo_tipico?, instrucao_referencia, ativo?, ordem?}` (+ `expected_versao` on PUT) | `cs_estrutura_tipo_salvar/excluir` + event. 409 `tipo_em_uso` on delete (deactivate instead), 409 `tipo_protegido` for `Outro`, 409 `versao_desatualizada`, 422 duplicate `nome` |
`@limiter` on `a-partir-do-viral`; admin AI calls are metered through the org LLM budget of the **ingestion org** (§4.3 #2). **There is no `preencher-ia` route** (the owner removed AI fill from the import; fields are filled by the reference dataset or typed by an admin).

### 6.3 Importação (`routers/estruturas_importacao.py`, tier `platform`; mechanism §7 — a pure loader, **no model call**)
| Method + path | Request | Response / codes |
|---|---|---|
| `POST /estruturas/importacoes` → 202 (200 when `dry_run`) | `{fonte: "referencia"\|"maquina_de_roteiros", conteudo: <the parsed JSON document>, arquivo_nome?, dry_run: bool = true}` | dry-run ⇒ `{data: ImportacaoRelatorio}` synchronously (no DB writes besides the `simulada` lote row); apply ⇒ `{data:{id, status:"em_andamento"}}` (job `estruturas.importar`; bulk insert in per-profile batches). 409 `simulacao_obrigatoria` (no `simulada` lote with the same `arquivo_sha256` in the last 24 h), 409 `importacao_em_andamento` (one at a time), 422 `arquivo_invalido` |
| `GET /estruturas/importacoes/{id}` | — | `{data: ImportacaoRelatorio}` (poll) |
| `GET /estruturas/importacoes` | `limit ≤ 20, offset` | `{data:{items, total}}` |
`ImportacaoRelatorio` = `{id, fonte, status, dry_run, arquivo_sha256, linhas_total, perfis_criados, perfis_mesclados, estruturas_criadas, estruturas_atualizadas, estruturas_inalteradas, estruturas_ignoradas, ignoradas_motivos: {motivo: n}, blocos_criados, campos_nao_importados: string[], erro|null, created_at, finished_at|null}`.
`main.py :: _MAX_BODY_PATH_OVERRIDES["/api/media-creation/estruturas/importacoes"] = 16 MiB` (platform-admin-only route; the reference file is ~2.9 MB and the corpus grows; the default 1 MB would silently cap it).

### 6.4 Biblioteca — see §4.2 (no other new endpoints).

### 6.5 Chat, unified (`routers/chat.py`, `schemas/chat.py`, `services/chat_service.py` — extend, don't fork)
- `Agente` is **deprecated**. `ConversaCreate.agente` stays accepted (optional, ignored) for one release; `GET /chat/conversas?agente=` stays accepted and ignored. Every read returns `agente: "unificado"` (a legacy `headline|roteiro` row is *presented* as unified; never filtered by it). Conversations are listed per `(user, marca)` only.
- `Conversa` = `{id, marca_id, agente: "unificado", titulo, last_message_at}` (unchanged otherwise).
- `Mensagem` (GET messages) = existing fields + `tipo: "texto"|"roteiro_gerado"`, `propostas: Proposta[]` (assistant `texto` messages that carry parsed headlines, else `[]`), `fluxo: Fluxo|null` (only `roteiro_gerado` messages, composed at read time from the truth tables, never stored).
- `Proposta` = `{id, ordem, texto, gatilho_tag|null, estruturas: EstruturaUso-lite[] (= {id, codigo, perfil:{id,handle,nome}, principal: bool}), status: "proposta"|"escolhida", headline_id|null}`.
- `Fluxo` = `{proposta_id, etapa: "headline_salva"|"roteiro_gerando"|"roteiro_pronto"|"falhou", headline: {id, texto}, roteiro: {id, nome, status, formato, duracao, ordem_cta, versao}|null, post: {id, titulo, etapa_label}|null, estruturas: EstruturaUso[], legenda: "pendente"|"gerada"|"indisponivel", erro_codigo|null}`.

**`POST /chat/conversas/{id}/mensagens`** (SSE) is unchanged in transport; the frames grow:
`{"meta": {mensagem_usuario_id, contexto_chars, codigos_permitidos: number[], modo_estrutura: "post"|"mencoes"|"auto"|"perfil_ambiguo"|"perfil_nao_encontrado", resolucao_perfis: ResolucaoPerfis}}` → `{"delta"}`… → [`{"truncated":true}`] → `{"done": {mensagem_id, propostas: Proposta[]}}` | `{"error": {code, message}}`.
`codigos_permitidos` are now **Estrutura `codigo`s** (cited as `(estrutura #N)` or `(estrutura #N + #M)`).
Pre-stream refusals are unchanged (404 foreign conversa/ref, 409 `stream_em_andamento`, 429, 503). New mention type: `MencaoTipo` adds `estrutura` (`id` = Estrutura uuid; 404 if not `ativa`); `biblioteca` keeps `perfil:<uuid>` (= all that profile's Estruturas) and a video uuid (= that video's Estruturas + its transcript snippet). `GET /chat/mencoes?tipo=estrutura&q=&marca_id=&page=` lists Estruturas (label = `#codigo @handle — formula_trecho`).

**`POST /chat/conversas/{conversa_id}/escolher`** → **202** first time, **200** when the flow already exists (`ja_existia: true`); body exactly one of `{proposta_id: uuid}` | `{headline_id: uuid}` (an already-saved headline mentioned with `@`; a proposta row is synthesised, no Estrutura link). **Empty of any other field**: the defaults are fixed (duração `"auto"`, ordem do CTA `cta_inicio`; adjust later in the page via the existing roteiro reprocess).
Response `{data: {proposta: Proposta, fluxo: Fluxo, mensagem_id, ja_existia, em_andamento}}`. Errors: 404 `proposta_nao_encontrada` (other user/org/conversation), 404 foreign headline, 429 `limite_diario_roteiros`, 503 `ia_nao_configurada|orcamento_ia_excedido|geracao_indisponivel`.
Side effects and order: §9.2. State after: the headline is a real `cs_headlines` row (`conversa_id`, `proposta_id`, `favorita=true`), a `cs_roteiros` row exists (`conversa_id`, `headline_id`), a `cs_posts` card is bound, a `roteiro_gerado` assistant message exists exactly once.

### 6.6 Headlines — forms (`routers/headlines.py`, `schemas/headlines.py`; EST-4b)
- `LoteForm`, `LoteViral`: + `estrutura_ids?: uuid[]` (≤ 12; restricts the pool to these `ativa` Estruturas; 422 `estrutura_obrigatoria_invalida`). `referencia` tipo `perfil` now selects that profile's Estruturas (`perfil_ids` 1..2 unchanged).
  `referencia` tipo `formato` / `gatilho` filter **through the Estrutura's source video** (`viral_id`) classification; Estruturas without a source video are excluded from those two filters and counted in `lote.aviso_sem_classificacao` (new int) — never silently ignored.
- `LoteBiblioteca`: `viral_id` **or** `estrutura_id` (exactly one). `viral_id` ⇒ that video's `ativa` Estruturas; none ⇒ 422 `viral_sem_estrutura` ("Este vídeo ainda não tem estruturas.").
- Free text (`assunto`, `assunto_livre`): the resolver (§8.3) runs; `resolvidos` narrow the pool exactly like `referencia: {tipo:"perfil"}`; `ambiguos` ⇒ **422 `perfil_ambiguo` with `candidatos`** (a form cannot ask conversationally); `nao_encontrados` ⇒ 422 `perfil_nao_encontrado_na_biblioteca`. Explicit `estrutura_ids`/`referencia` win over free text; free text is only inspected when both are absent.
- No Estrutura given ⇒ the pool is §8.2's (the brand's selected profiles, else the whole library). `lote.estruturas_total/processadas/com_erro` now count Estruturas. Fallback to Método templates (`fallback_metodo`) is unchanged when the pool is empty.
- Headline out: `Headline` + `estruturas: EstruturaUso[]` (from `cs_estrutura_usos`; `blocos` empty for headlines). `Headline.viral` stays (deprecated; set when the Estrutura has a source video). Every generated headline writes one `cs_estrutura_usos` row per Estrutura used (`contexto='lote_headlines'`).
- **Placeholders (owner Q6b).** A formula's `[placeholders]` (e.g. `[autoridade teórica]`) are filled by the model from the **org-scoped brains (Cérebro, `cs_brains` of the marca) and the bio (Meu Perfil, `cs_marca_perfil`)** under the existing `<material>` fence; **no bracket may remain in an output headline**. The pipeline drops any generated headline that still matches `\[[^\]]+\]` and counts it in the lote's existing discarded-headlines message (`MSG_DESCARTADAS`); when the material has nothing to fill a placeholder with, the model must skip that Estrutura for that headline rather than invent. `{{SLUG}}` research slots no longer occur in Estruturas; the research items (Minha Pesquisa) keep being offered as extra material and `itens_usados` verification stays for items actually used. (EST-4b)

### 6.7 Roteiros — all four formats (`routers/roteiros.py`, `schemas/roteiros.py`, `services/roteiro_service.py`; **EST-RO, after S3 lands**; prompts in EST-FMT, §8.7)
- `RoteiroCreate` + `estrutura_ids?: uuid[]` (1..3; the first is `principal`) + `formato?: "reels"|"carrossel"|"stories"|"post"` + `conversa_id?: uuid` (set by the chat fluxo; 404 foreign). `viral_id` stays accepted but **deprecated and ignored when `estrutura_ids` is present**; `brain_id`, `estrutura` (ordem do CTA), `duracao`, `post_id`, `substituir`, `gerar_perguntas` unchanged.
  **Format rule:** `formato` = the principal Estrutura's `formato` when `estrutura_ids` is given (an explicit different `formato` ⇒ 422 `formato_diferente_da_estrutura`; Estruturas with different formatos ⇒ 422 `formatos_misturados`); with no Estrutura it is the request's `formato` (default `reels`). 422 `muitas_estruturas`, `estrutura_obrigatoria_invalida`.
- `duracao` and `ordem_cta` keep their meaning for **reels**; for the other formats the script follows the Estrutura's own block sequence (`duracao` is stored but only guides length for `stories`; `ordem_cta` is stored as the default `cta_inicio` and only steers the legacy no-Estrutura Método beats). With Estruturas, **the Estrutura's block order is the structure** for every format.
- With no `estrutura_ids`: free-text `instrucoes` is run through the resolver (same rules as §6.6); still none ⇒ §8.2's pool, the pipeline picks one or mixes (same formato only).
- `Roteiro` out: existing fields + `formato`, `ordem_cta` (= `estrutura`, read alias), `estruturas: EstruturaUso[]` (with the **validated** block attribution, §8.5), `conversa: {id, titulo}|null`. `conteudo` is markdown whose shape depends on `formato` (§8.7).
- Output contract added to every roteiro prompt: the script, then a sentinel line `=== ESTRUTURAS_USADAS ===`, then one line per Estrutura `#<codigo>: <nome do bloco>; <nome do bloco>`. The service splits on the sentinel, **stores only the script in `conteudo`**, validates codes ∈ the offered set and block names ∈ that Estrutura's blocks (case/accents-insensitive exact match on `nome`), writes `cs_estrutura_usos` (`papel` principal/mistura by order, `bloco_ids` = matched ids; unmatched names dropped and counted in `cs_fluxo_eventos.citacao_rejeitada`). Sentinel missing ⇒ usos written with empty `bloco_ids` and event `atribuicao_ausente`; **never a failure**. The per-format shape is validated by `saida_ia` (§8.7): an invalid shape is a coded `falha`, never trimmed.
- S3 files this edits (`roteiro_service.py`, `routers/roteiros.py`, `schemas/roteiros.py`): therefore **after S3 is merged** (§13 avoid list); the prompt builders and validators it calls are NEW files (EST-FMT) built before.

### 6.8 Esteira — the card's origin (`routers/esteira_origem.py`, **new file**, tier `org`)
`GET /esteira/posts/{post_id}/origem` → `{data: {headline: {id, texto}|null, roteiro: {id, nome, status, formato, duracao, ordem_cta, versao}|null, estruturas: EstruturaUso[], formato: "reels"|"carrossel"|"stories"|"post"|null, legenda: {texto|null, origem: "ia"|"usuario"|null}, conversa: {id, titulo}|null}}`. 404 foreign post.
Composed at read time from `cs_posts` → `cs_roteiros`/`cs_headlines` → `cs_estrutura_usos` → `cs_estruturas` (`formato` = the **roteiro's** `formato`, mapped to the card's `cs_posts.formato` via `estruturas_formatos.py`; duração/CTA come from the roteiro). `legenda.origem`: the finalizer's `legenda_gerada` event stores `codigo = sha256(generated text)`; `origem = "ia"` iff `sha256(cs_posts.legenda) == codigo` of the latest such event for the card's flow, `"usuario"` when `legenda` is non-NULL and differs (or no such event), `null` when `legenda` is NULL. (`codigo` on that one event type holds the hash, never text.)
This endpoint exists so `esteira_service.py` / `routers/esteira.py` (touched by S3's `_pendencias`) stay untouched by the read side; the only edit this release makes there is UNI-1b's optional `formato` on `criar`/`PostCreate`, **after S3** (§9.2 step 5).

### 6.9 Headlines e Roteiros (`routers/headlines_roteiros.py`, **new file**, tier `org`)
`GET /headlines-roteiros` — `marca_id` (required), `q?` (≤ 200), `estrutura_id?`, `perfil_id?`, `roteiro_status?` (`criando|processando|completo|falha|sem_roteiro`), `aprovacao?` (`pendente|aprovado|rejeitado`; **null-valued until S3 lands**), `limit` (1..50, def 20), `offset`.
Lists the marca's saved headlines (`favorita` ∨ has a roteiro ∨ `conversa_id` set) **plus roteiros without a headline** (Roteiro Avançado with a free `headline_texto`). Item:
`{headline: {id, texto, favorita, created_at, acima_recomendado}|null, headline_texto, roteiro: {id, nome, status, formato, duracao, ordem_cta, versao, aprovacao: {estado: "pendente"|"aprovado"|"rejeitado"}|null}|null, estruturas: EstruturaUso[], conversa: {id, titulo}|null, post: {id, titulo, etapa_label}|null, created_at}` → `{data:{items, total}}`.
Existing `GET /headlines?lista=favoritas|sugeridas`, `GET /roteiros`, favoritar/excluir/reprocessar endpoints are reused by the page; the old pages stay until the redirect slice (§13).

---

## 7 · Import mechanism (EST-3) — a pure loader: `noctus.sw.estruturas_import` + the admin endpoints of §6.3

**There is no model call, no budget and no `ia_sugerido` anywhere in the import.** The owner had Claude Code fill the missing fields *in-session* and exported a complete reference dataset; the loader only reads, validates, maps and writes. Sources (vendor-derived, **never committed**, read from the owner's machine by the MCP tool),
directory `/Users/rapha/Documents/repository/NoctusAI/_private-studies/core-studio/estruturas-import/`:
- `estruturas-referencia.json` — a JSON **array of 841** objects (15 profiles, all `formato:"reels"`, 8 354 blocks): `{corestudio_id, perfil, formula_headline, formula_herdada_de?, formato, objetivos[1..2], preenchido_por, blocos:[{ordem, nome_original, nota, repeticoes, tipo, tempo, instrucao}]}`. `corestudio_id` is bare digits; `formula_headline` is clean (keeps `[placeholders]`); `formula_herdada_de` (23 rows) is the `corestudio_id` of the sibling a variant inherited its formula from; `preenchido_por` = `claude-code-referencia-2026-11-15`; `nota` is a string (`""` when none); `tempo` is `"N–Ms"` (en dash); `tipo` is one of the 21 catalog names or `Outro`.
- `maquina-de-roteiros-2026-11-15.json` — `colecoes.perfis` (7) + `colecoes.moldes` (67 complete templates), unchanged.
- `catalogo-blocos.json` — **not loaded at runtime**: it seeds M1 (§3.1).

**MCP tool** `noctus.sw.estruturas_import` (`mcp/noctusai/tools/noctus/sw/estruturas_import.py`, registered next to `vista_clientes_sync`; same auth as its siblings: `NOCTUS_SW_URL` + `NOCTUS_SW_TOKEN`, here a **platform admin's** bearer, never logged).
`action = "plan" | "apply" | "status"`; `fonte = "referencia" | "maquina_de_roteiros"`; `arquivo` = a local path passed by the caller (default: the directory above). `plan` sha256s the file, POSTs `dry_run=true`, returns the `ImportacaoRelatorio` (**counts and reason codes only — no row text**). `apply` requires `confirm=True` **and** a prior `plan` of the same sha within 24 h (server-enforced `simulacao_obrigatoria`). `status` polls. Idempotent by construction (§7.3).

### 7.1 Mapping — `estruturas-referencia.json` (`fonte='referencia'`, `origem='import_corestudio'`, `status='ativa'`)
| Dataset field | → | Provenance |
|---|---|---|
| `perfil` | `cs_perfis_monitorados.handle` after normalisation (strip `@`, lowercase, must match `^[a-z0-9._]{1,30}$`, else the row is ignored `handle_invalido`); a new profile is `rede='instagram'`, `org_id=NULL`, `monitorar=false`, `status='aguardando'`; an existing profile is left untouched. **Merge by normalised handle across both files**; events `cs_perfil_eventos.importado` / `criado` | — |
| `corestudio_id` | `fonte_externa='corestudio'`, `ref_externa` (must match `^\d+$`, else ignored `id_invalido`) | — |
| `formula_headline` | `formula_headline` | `fonte`; **`referencia` when `formula_herdada_de` is set** (the formula was inherited by the reference pass) |
| `formula_herdada_de` | `formula_herdada_de` | informational |
| `formato` | `formato` (enum) | `referencia` |
| `objetivos` | `objetivos` (⊆ the 4, 1..4) | `referencia` |
| `preenchido_por` | `referencia_rotulo` | — |
| `blocos[].ordem` | `ordem` (must be contiguous `1..n`, else ignored `ordem_invalida`) | — |
| `blocos[].nome_original` | `nome` (≤ 120) | `fonte` |
| `blocos[].nota` | `nota` (`""` → NULL) | `fonte` |
| `blocos[].repeticoes` | `repeticoes` (1..20) | `fonte` |
| `blocos[].tipo` | `tipo_id` by exact name lookup in `cs_estrutura_tipos_bloco`; a name not in the catalog ⇒ row ignored `tipo_desconhecido` (the dataset uses `Outro` for the rest) | `referencia` |
| `blocos[].tempo` | `tempo` | `referencia` |
| `blocos[].instrucao` | `instrucao` | `referencia` |
A row is **ignored with a reason code** (never silently): `handle_invalido`, `id_invalido`, `formula_ausente`, `blocos_ausentes` (0 or > 60), `ordem_invalida`, `tipo_desconhecido`, `formato_invalido`, `objetivos_invalidos`, `perfil_optout`. There is no AI to repair an incomplete row.

### 7.2 Mapping — Máquina de Roteiros (`fonte='maquina_de_roteiros'`, `origem='import_maquina'`, `status='ativa'`)
| Source field | → | Provenance |
|---|---|---|
| `perfis[].handle` (`@andreavermont`) → handle as above; `perfis[].nome` → `cs_perfis_monitorados.nome` when the profile is new | profile (`monitorar=false`) | — |
| `moldes[].id` | `fonte_externa='maquina_de_roteiros'`, `ref_externa`; profile via `perfilId` → `perfis[].id`→handle (no matching profile ⇒ ignored `perfil_ausente`) | — |
| `moldes[].formato` (`reels\|carrossel\|post`) · `objetivos` | `formato`, `objetivos` | `fonte` |
| `moldes[].blocos[].{nome,tempo,instrucao}` | blocks (`ordem` = array order, `repeticoes=1`, `nota=NULL`); `tipo_id` = exact normalised-name match to a catalog type else `Outro` | all `fonte` |
| molde `nome` | not stored (no such field); not used | — |
| **Not imported (owner: outside the field list — confirmed)** | `quandoUsar`, `quandoNaoUsar`, `validacao`, `exemplo`, `aprovado`, `criadoEm`, profile `dna/ganchos/nuncaFaz/pilares/publico/tom`, `marcas[]`, `roteiros[]` — reported as `campos_nao_importados` in every plan so nothing is lost silently | — |
Both loads **skip opted-out handles** (`cs_biblioteca_optouts`): ignored `perfil_optout`.

### 7.3 Idempotency, re-runs, rollback
Key `(fonte_externa, ref_externa)` + `fonte_hash` (sha256 of the normalised row): same hash ⇒ `inalteradas`; changed hash ⇒ update **only** the fields whose `*_origem` is `fonte` or `referencia` (a field an admin touched or confirmed — `admin` — is never overwritten). Running the same file twice yields all `inalteradas`. Every row writes an event with `importacao_id` (`importada` / `atualizada_import`, `ator_tipo='sistema_import'`); there is no "undo import": archive/delete go through §6.2, and a failed run is simply re-run. Apply runs as job `estruturas.importar`, one transaction per Estrutura (row + blocks + event in one RPC), batched per profile.
Acceptance numbers on the real files (an operator check, not a unit test — the rows are vendor-derived): reference `created + updated + unchanged + ignored == 841`; Máquina `== 67`; `blocos_criados` reconciles with the per-row block counts.

### 7.4 Future need (deliberately **out of v1**)
The multi-dialect parser for the **raw** CoreStudio chat rows (`ID | formula Headline → Block (nota) → Block × N`, four dialects: `<ID> | <formula> Headline[ (nota)] → …`; `<ID> | <handle> | "<formula>" (nota) → …`; `ID <ID> | Tema: … | Fórmula: "<formula>" | Headline (…) → …`; `ID <ID> | <N>K views | Fórmula: "<formula>"\nSequência: Headline → …`) is **not built**: the dataset is pre-parsed. A future re-import of a newer raw CoreStudio export would need it (plus the AI/reference fill that the owner did by hand this time) — a separate contract.

## 8 · AI behaviour: retrieval, name resolution, mix, attribution (EST-4a/4b)

### 8.1 What is retrieved, and how it is shown
`services/estruturas_retrieval.py` (new, pure + DB read) returns candidate Estruturas; `prompts/estruturas_contexto.py` (new) renders them as one `<material tipo="estruturas_biblioteca">` block, each as
`estrutura #<codigo> (@<handle>) | formato: <f> | objetivos: <a, b> | FÓRMULA: <formula> | BLOCOS: 1. <tipo> «<nome>» [<tempo>] — <instrucao> (nota) × <n>; 2. …` (a block with no `instrucao` shows its type's `instrucao_referencia`; ≤ ~700 chars each; blocks truncated with a marker, never mid-word). Untrusted text goes through `cerca()`.
Context-char budget is the existing `_Orcamento`: perfil (bio) → memórias → **cérebros da marca** → explicit refs → `selecao_de_estrutura` → pool; the pool is the section that gets clipped first. The **brains section is new for the unified chat** (the headline agent had none): the marca's `cs_brains` (org-scoped), most recently updated first, ≤ 5, each ≤ 6 000 chars, as `<material tipo="cerebro">` blocks — they, with the bio, are what fills a formula's `[placeholders]` (§6.6).

### 8.2 The pool (replaces `pool_de_estruturas` / `_pool_estruturas`; `MAX_ESTRUTURAS = 12` stays)
1. **Scope**: `ativa` Estruturas of the brand's **selected profiles** (`cs_biblioteca_referencias`: `modo='perfil'` profiles ∪ the profile of every `modo='video'` ref); if the brand selected nothing ⇒ the **whole library**. (Never silently empty: an empty pool yields the `fallback_metodo` for batches and a "não há estruturas na biblioteca" material note for chat.)
2. **Filters** when present: `formato` (the surface's formato; chat default none), `objetivos` (when the user's request or the brand profile states one), explicit `estrutura_ids` / `perfil_ids`.
3. **Order**: round-robin across profiles (diversity), within a profile by deterministic seeded shuffle (`hash(conversa_id|lote_id)` so a re-run is stable and different conversations vary); ties never by recency.
4. Cap `MAX_ESTRUTURAS` (12) for chat, the existing per-lote cap for batches.
The `modo_de_selecao` modes keep their meaning with Estruturas: `post` = exactly one `@estrutura` mention (mandatory); `mencoes` = any other set of mentions (`@perfil`, several `@estrutura`, resolved free-text profiles) ⇒ **only** those; `auto` = no mention ⇒ the pool. New modes `perfil_ambiguo` / `perfil_nao_encontrado` (§8.3) offer **no pool**.

### 8.3 Free-text profile-name resolution (deterministic, pre-LLM; `resolver_perfis_no_texto`)
Runs in `ChatContexto` (chat), `headline_service` (forms) and `roteiro_service` (Roteiro Avançado, wave 3), and behind `GET /estruturas/resolver-perfil`.
- **Normalise** (NFKC → casefold → strip accents → keep `[a-z0-9@._ ]` → collapse spaces) both the text and an in-process index of the **library profiles** (handle, handle split on `._`, `nome`; ≤ ~600 rows; cached 60 s; profiles with no `ativa` Estrutura are indexed but flagged `sem_estruturas`).
- **Candidate spans**: an `@handle`; or ≤ 4 tokens after a trigger — `estilo d[oae]s?|de`, `no estilo`, `como (o|a)`, `parecid[oa] com`, `inspirad[oa] (n[oa]|em)`, `do perfil`, `perfil d[oae]`, `baseado em`.
- **Score** (per span × profile): exact handle 1.0 · exact normalised `nome` 0.95 · all span tokens present in `nome` tokens, or the joined span is a substring of the handle with separators removed ("fernando segredo" ⊂ `psifernandosegredo`) 0.8 · one distinctive token (≥ 5 chars) in `nome`/handle 0.6 · else none.
- **Decision**: top ≥ 0.8 and top − second ≥ 0.15 ⇒ **resolved**; ≥ 2 candidates ≥ 0.6 with top − second < 0.15, or only ≤ 0.8 matches ⇒ **ambiguous** (candidates ≤ 5); no candidate ≥ 0.6 ⇒ **not found** (`sugestoes` = top 3 by token overlap). Examples the tests must pin: "um post no estilo do Fernando Segredo" → resolved `psifernandosegredo`; "no estilo do Fernando" with several `fernando*` handles → ambiguous; "estilo do João" with no match → not found.
- **Effect**: resolved ⇒ treated exactly as an `@perfil` mention (mode `mencoes`; message `referencias` gets `{tipo:"biblioteca", id:"perfil:<uuid>", rotulo, via:"texto"}`); ambiguous ⇒ context carries `<material tipo="resolucao_de_perfis">` with the candidates and the rule "pergunte qual perfil o usuário quis; não escolha estrutura" and **no pool** + the SSE `meta.resolucao_perfis` so the FE shows chips (clicking sends the mention); not found ⇒ the block says so and offers `sugestoes`. An explicitly named profile **outside the brand's selection is allowed** (explicit intent beats the default scope).
- Every attempt writes a `cs_fluxo_eventos` row (`perfil_resolvido|perfil_ambiguo|perfil_nao_encontrado`, `contagem`).

### 8.4 Mixing and attribution (prompt contract; `chat-unificado-v1-draft`)
The unified system prompt (`prompts/chat_unificado.py`, new; composed from the headline rules + the `REGRAS_MATERIAL` fence) says, in substance:
- Deliver exactly the number of headlines asked (1..10, default 5), numbered, one line each, each ending `(estrutura #<código>)` or `(estrutura #<código> + #<código>)` (**max 3**) using only codes present in the material; vary Estruturas across headlines when the material has enough.
- May combine Estruturas when the combination serves the request; **when it does, say which Estrutura and which blocos came from each** (`### Estruturas usadas`: `#N (@perfil): Bloco A, Bloco B`).
- Open an answer that used structure with `### Análise da Estrutura Escolhida` (carried over), then the numbered headlines.
- **Never leave a `[placeholder]` in a headline**: fill every `[…]` of the formula from the bio and the brains in the material; if the material cannot fill it, say what is missing (or use another Estrutura) instead of inventing or keeping the bracket.
- Mix **only Estruturas of the same `formato`** (a mix never crosses reels/carrossel/stories/post).
- Do not write the roteiro in chat: "o roteiro é escrito quando o usuário escolhe uma headline" — if asked in text, tell the user to pick a headline from the list (or `@`-mention a saved one).
- Perfil ambiguous/not found ⇒ ask / say so; never invent a profile or code.

### 8.5 Server-side validation of the model's citations (never trust the model)
On `done`, `services/propostas.py` (new, a Python port of `extrairHeadlines`/`citacoes.ts` — **single derivation, FE parser retired**) parses the numbered headline lines: strips the trailing `(estrutura #N[ + #M…])` and the trailing gatilho tag, drops any code not in `codigos_permitidos` **or whose Estrutura `formato` differs from the principal's** (events `citacao_rejeitada` / `formato_misturado`, `contagem`), drops a headline that still matches `\[[^\]]+\]` (event `placeholder_remanescente`, `contagem`; it never becomes a proposta), keeps ≥ 1 headline/≤ 10, writes `cs_chat_propostas` (+ `cs_chat_proposta_estruturas`, first valid code = `principal`) in the same pass that saves the assistant message, and returns them in the `done` frame. A message with no parsable headline simply has `propostas: []`.

### 8.6 No tool use, stated
Everything above is retrieval **before** the single model call. When the seed gains tool calling (`NOC-REMEDIATE[llm-tool-use]`), `resolver_perfis_no_texto` and the pool become tools with no API change.

---

### 8.7 How Estruturas drive the roteiro, per format (EST-FMT: NEW `prompts/roteiro_formatos.py`; validators in `saida_ia.py`; owner D9: all formats now)
The model receives the chosen Estrutura(s) (§8.1 rendering, principal first) + the headline + the org's bio/brains, and **follows the principal's block sequence in order** (a `repeticoes: n` block yields n consecutive units, each developing a different angle of that block's type), borrowing from the other Estrutura(s) only the blocks it attributes to them. Output is markdown, validated by a per-format grammar (invalid ⇒ coded `falha`, never trimmed):
| formato | unit | `conteudo` shape | Validation (config keys, finite defaults) |
|---|---|---|---|
| `reels` | spoken beat | the existing shape (`**(Beat)**` + fala), ≈ 150 words/min per `duracao` (`auto` = 150–220 words); the legacy beat order (`cta_inicio`/`cta_final`) is used only when no Estrutura is given | existing `saida_ia` roteiro checks |
| `carrossel` | slide | `**Slide N — <nome do bloco>**` then the slide text; one slide per block unit (`repeticoes` expands), `tempo` is the slide label | 1..20 slides; each text non-empty, ≤ 400 chars; slide 1 carries the headline |
| `post` | on-screen text + caption | `### Texto na tela` (one line per `**Tela N**`) then `### Legenda` | 1..8 screens ≤ 200 chars each; `### Legenda` present, ≤ 2 200 chars, validated by the existing `validar_legenda` |
| `stories` | frame | `**Quadro N — <nome do bloco>**` then the frame text (≤ 300 chars) | 1..15 frames |
All formats end with the `=== ESTRUTURAS_USADAS ===` sentinel (§6.7). Prompt versions per format (`roteiro-carrossel-v1-draft`, `roteiro-post-v1-draft`, `roteiro-stories-v1-draft`; reels keep `roteiro-v1-draft`/`roteiro-cta-final-v2-draft`) are recorded on the row (`prompt_versao`). Untrusted text stays in `dados_nao_confiaveis` fences; no HTML/links/URLs in output (existing guard). A block whose type is `Outro` is rendered from its own `nome`/`instrucao`.

### 8.8 Auto-draft from analysis (owner D11; EST-5) — a draft, never an offer
When a viral video's **classification completes** (`classificacao_status → concluida`, whether synced or added by link) and it has content to derive from (blueprint ∨ transcription ∨ caption), the ingestion code calls the seam `depois_de_classificar` (EST-2; callbacks `(db, viral_id, org_id)`, exceptions logged, **never** failing the classify job), and EST-5's callback enqueues job `estruturas.rascunho_do_viral` (`dedupe_key = "rascunho:" + viral_id`).
The handler derives, with the same AI service as `POST /estruturas/a-partir-do-viral` (`estruturas_ia.py`, schema-validated by `saida_ia_estruturas.py`, untrusted text fenced): `formula_headline`, `formato` (hint from the media type: video/reel → `reels`, carousel → `carrossel`, image → `post`), `objetivos` (1..2), and ordered blocks each with a catalog `tipo_id` (anything outside the catalog ⇒ `Outro`), `nome`, `tempo`, `instrucao`.
It inserts **one** Estrutura via `cs_estrutura_criar`: `status='rascunho'`, `origem='viral_auto'`, `perfil_id` = the video's, `viral_id` set, **every field `ia_sugerido`**, `ator_tipo='sistema_ia'`, events `criada_automatica` + `ia_preenchida`. Idempotent (`UNIQUE (viral_id) WHERE origem='viral_auto'`; skipped when any non-archived Estrutura already links the video). Capped by `estruturas_autodraft_dia` (finite default) and metered on the ingestion org's budget; invalid model output ⇒ **no draft**, the job's coded failure is the record (never a trimmed/partial Estrutura). A draft is invisible to orgs, retrieval and generation until an admin runs **Publicar** (§6.2); the Estruturas tab shows admins a "Rascunhos" count.

## 9 · The unified chat → roteiro → card flow (UNI-1a / UNI-1b)

### 9.1 State machine (per proposta; every transition writes a `cs_fluxo_eventos` row)
`proposta` → (click) `escolhida/headline_salva` → `roteiro_criado` → `card_criado` → `concluido` | `falhou` (with `fluxo_erro_codigo`). The roteiro itself is `criando → processando → completo | falha` (existing), approval is S3's.

### 9.2 `POST …/escolher` — a resumable saga (each step durable and idempotent; **no fake atomicity**)
1. **Claim**: `UPDATE cs_chat_propostas SET status='escolhida', escolhida_por, escolhida_em, fluxo_lease_ate = now()+60s WHERE id=? AND (status='proposta' OR (fluxo_etapa <> 'concluido' AND (fluxo_lease_ate IS NULL OR fluxo_lease_ate < now()))) RETURNING *`. 0 rows and the flow exists ⇒ return its current state, 200, `ja_existia:true`, `em_andamento:true` (a concurrent double-click is not an error).
2. **Headline**: insert `cs_headlines` (`marca_id`, `texto`, `conversa_id`, `proposta_id`, `modo='manual'`, `favorita=true`, `favoritada_em`, `created_by`) — `UNIQUE (conversa_id, proposta_id)` makes the retry a lookup. Write `cs_estrutura_usos` per cited Estrutura (`contexto='chat'`, `headline_id`, `proposta_id`). Event `headline_salva`; `fluxo_etapa='headline_salva'`.
3. **Pre-flight** (fail fast, before any expensive step): `geracao_jobs.assert_geracao_disponivel`, IA key, `assert_orcamento_ia`, the daily roteiro cap (**no format gate: every formato is supported**). A failure here leaves the headline saved, `fluxo_etapa='headline_salva'`, returns the coded error; the user retries the same click later.
4. **Roteiro**: look up `cs_roteiros` by `(headline_id, conversa_id)`; if absent, `RoteiroService.create(RoteiroCreate{marca_id, headline_id, headline_texto, duracao:"auto", estrutura: ESTRUTURA_PADRAO, estrutura_ids: [cited…], gerar_perguntas:false, conversa_id})` — `formato` is **derived by the service from the principal Estrutura** (reels / carrossel / stories / post; §6.7), `reels` when the headline cited none (job queued; wave 3). Event `roteiro_criado`.
5. **Card**: `EsteiraService.criar(PostCreate{marca_id, headline_id, formato})` (`formato` optional on `PostCreate`, default `reel`; UNI-1b adds it **after S3**, mapped from the roteiro's formato via `estruturas_formatos.py`; lands in the "Headline + roteiro" stage by position, title = the headline) then `vincular_roteiro` (atomic RPC). A card/roteiro unique-violation maps to the existing `headline_ja_em_post` / `roteiro_ja_em_post` (409 carries `post_id`; the saga adopts the existing card). Event `card_criado`; `fluxo_etapa='card_criado'`. `cs_posts.formato` is written truthfully (M3 relaxes the CHECK, §3.3); publication targeting for non-reel cards stays S1/S4/S7's (out of scope: "first the skeleton").
6. **Finalizer**: enqueue job `fluxo.finalizar_card` (`dedupe_key = "fluxo:" + proposta_id`) — §9.3.
7. **Chat message**: insert the assistant `tipo='roteiro_gerado'` message **once** (`cs_chat_mensagens.proposta_id`, unique; a second insert is a no-op) with short text ("Criei o roteiro desta headline e o card na Esteira."); the `fluxo` object is composed at read.
Response is returned after step 6/7 with `fluxo.etapa='roteiro_gerando'` (202). A crash between steps is repaired by the lease: any later `escolher` (or the finalizer's first tick) resumes from the last recorded `fluxo_etapa`.

### 9.3 Finalizer job `fluxo.finalizar_card` (jobs organ, lease, retry — **not** a sleeping task)
Handler reads the roteiro status: `completo` ⇒ produce the card's caption and **save it to `cs_posts.legenda` only if NULL** (a user edit is never overwritten): for **`post`** take the roteiro's `### Legenda` section (already validated by `validar_legenda`; no second model call, DC6); for **reels / carrossel / stories** call `LegendaService.gerar(post_id)` (reuse; **no new caption generator**; `prompts/legenda_reel.py` + `legenda_service.py` become format-aware — EST-FMT — and a `post` whose section is missing falls back to the service) → events `roteiro_gerado`, `legenda_gerada` (`codigo` = sha256 of the saved text), `fluxo_concluido`; `falha` ⇒ events `roteiro_falhou`, `fluxo_concluido` with `codigo`; `criando|processando` ⇒ reschedule itself (`run_at = now + 10 s`, jittered) up to 90 ticks (~15 min), then event `roteiro_falhou` `codigo='demorou'`.
Caption failure (cap 429 `legendas_dia_usuario`, IA 503, `saida_ia` refusal) ⇒ event `legenda_falhou` with the code; the card stays without caption and the user can press the existing "gerar legenda". **Polling budget (written down):** ≤ 200 flows/day × ≤ 12 ticks × 1 indexed read ≈ 2 400 reads/day, only while a flow is active; no idle poller. Add `fluxo.finalizar_card`, `estruturas.importar` and `estruturas.rascunho_do_viral` to `ALL_JOB_TYPES` in `geracao_jobs.py` (collision class C3, all three declared by EST-1); handlers registered through the module startup hook, never a new hand-rolled worker.

### 9.4 Approval (S3) — interface assumptions, verify at wave-3 start
- **A1.** A `completo` roteiro is automatically in S3's "pending approval" state; if S3 requires an explicit submit call, the finalizer calls it (one line) — the card must show "aguardando aprovação do roteiro" with **no code of ours deciding approval**.
- **A2.** S3's esteira gate (roteiro approved to pass `gravacao`) is untouched; the auto-card never skips it.
- **A3.** `GET /headlines-roteiros` fills `aprovacao.estado` from S3's read helper; until then it is `null` and the FE shows no badge.
- If S3's names differ, adapt in the slice and note it in the delivery; do not fork the approval logic.

---

## 10 · Records / Metrics (measurement-by-design leg)

**What is recorded (all dated rows, no content in event tables):** Estrutura lifecycle + every field provenance change (`cs_estrutura_eventos`); each import run + per-row trail; every use of an Estrutura (`cs_estrutura_usos`, with the blocks used); every proposta and its pick; the whole fluxo (`cs_fluxo_eventos`); name-resolution outcomes; rejected citations; admin profile writes (`cs_perfil_eventos`).

| Metric | Single source / definition |
|---|---|
| Estrutura usage (per estrutura / perfil / contexto / period) | `COUNT(cs_estrutura_usos)` grouped; "per post" = usos → `headline_id`/`roteiro_id` → `cs_posts` |
| Mix rate | roteiros with ≥ 2 distinct `estrutura_id` in usos ÷ roteiros with usos |
| Attribution quality | `1 − (citacao_rejeitada.contagem ÷ citations)`; `atribuicao_ausente` rate |
| **Approval rate per Estrutura** (M4 view `cs_estrutura_metricas_v`, wave 3) | per `estrutura_id`: roteiros approved ÷ (approved + rejected) via usos → S3 approval events; reject reasons histogram; `principal` vs `mistura` split |
| Chat funnel | `propostas_geradas` → `proposta_escolhida` → `roteiro_gerado` → `card_criado` → S3 approved → `postado` (etapa role) — distinct `proposta_id` per stage; median click→`roteiro_gerado`; `roteiro_falhou`/`legenda_falhou` rate by `codigo` |
| **Field-review rate** (provenance) | `campo_confirmado` ÷ (`campo_confirmado` + `campo_editado` with `origem_anterior` ∈ {`referencia`,`ia_sugerido`}) per period, split by origin; share of fields still pending (view `cs_estruturas_resumo.campos_pendentes`); median time from load/`ia_preenchida` to first confirm/edit; edit-vs-confirm split tells how good the reference dataset and the AI drafts are |
| Library coverage | Estruturas per profile; share `ativa`; share fully confirmed; profiles with 0 Estruturas |
| Import | the `cs_estrutura_importacoes` counters per run (rows → created/updated/unchanged/ignored by reason; blocks created). No cost: the load never calls a model |
| Name resolution | resolved / ambiguous / not found counts per surface |
| **Auto-draft pipeline** | drafts created (`criada_automatica`) ÷ videos analysed; published ÷ created (`publicada`); archived-without-publish rate; median time draft→publish; fields edited before publish (`campo_editado` on a draft) |
| Videos added by link | `cs_perfil_eventos.video_adicionado_por_link` per period; share deduped (`ja_existia`); share that produced a draft that was later published |
| Roteiros by formato | `cs_roteiros.formato` distribution; failure rate (`roteiro_falhou`) and approval rate per formato; `placeholder_remanescente` rate (headlines dropped for a leftover bracket) |
| Block-type catalog | blocks per `tipo_id`; types never used; blocks typed `Outro` share (signals catalog gaps) |
Each metric has **one** derivation (the view or query named above); dashboards read it, never re-derive.

---

## 11 · Frontend contract (FE builds from this; no mockup gate — owner 2026-11-11)

### 11.1 Types (FE-1 writes these verbatim to NEW `src/types/estruturas.ts`; shared files `types/geracao.ts` get only the additive fields in §11.2)
```ts
export type EstruturaFormato = 'reels' | 'carrossel' | 'stories' | 'post'
export type EstruturaObjetivo = 'alcance' | 'autoridade' | 'conexao' | 'venda'
export type EstruturaStatus = 'rascunho' | 'ativa' | 'arquivada'
export type EstruturaOrigem = 'manual' | 'import_corestudio' | 'import_maquina' | 'viral_auto'
export type OrigemCampo = 'fonte' | 'referencia' | 'ia_sugerido' | 'admin'
export type EstruturaPerfilRef = { id: string; handle: string; nome: string | null; foto_url: string | null }
export type TipoBloco = { id: string; nome: string; ordem: number; tempo_tipico: string | null; instrucao_referencia: string; ativo: boolean }
export type Bloco = { id: string; ordem: number; nome: string; tipo: { id: string; nome: string }; tempo: string | null; instrucao: string | null;
  nota: string | null; repeticoes: number;
  proveniencia?: { nome: OrigemCampo; tipo: OrigemCampo; tempo: OrigemCampo; instrucao: OrigemCampo } /* admin only */ }
export type EstruturaResumo = { id: string; codigo: number; perfil: EstruturaPerfilRef; formula_headline: string; formato: EstruturaFormato | null;
  objetivos: EstruturaObjetivo[]; blocos_total: number; viral: { id: string; codigo: number; permalink: string; thumbnail_url: string | null } | null;
  status: EstruturaStatus; selecionada_pela_marca?: boolean; updated_at: string; pendente_revisao?: boolean /* admin only */ }
export type EstruturaDetalhe = EstruturaResumo & { blocos: Bloco[]; versao: number;
  origem?: EstruturaOrigem; ref_externa?: string | null; referencia_rotulo?: string | null; formula_herdada_de?: string | null;
  proveniencia?: { formula_headline: OrigemCampo; formato: OrigemCampo; objetivos: OrigemCampo } /* admin only */ }
export type EstruturaRef = { id: string; codigo: number; perfil: { id: string; handle: string; nome: string | null }; formula_trecho: string }
export type EstruturaUso = EstruturaRef & { papel: 'principal' | 'mistura'; blocos: { id: string; nome: string }[] }
export type PerfilCandidato = { perfil_id: string; handle: string; nome: string | null }
export type ResolucaoPerfis = { resolvidos: (PerfilCandidato & { via: 'mencao' | 'handle' | 'nome'; confianca: number })[];
  ambiguos: { trecho: string; candidatos: PerfilCandidato[] }[]; nao_encontrados: { trecho: string; sugestoes: PerfilCandidato[] }[] }
export type PropostaEstrutura = { id: string; codigo: number; perfil: { id: string; handle: string; nome: string | null }; principal: boolean }
export type Proposta = { id: string; ordem: number; texto: string; gatilho_tag: string | null; estruturas: PropostaEstrutura[];
  status: 'proposta' | 'escolhida'; headline_id: string | null }
export type FluxoEtapa = 'headline_salva' | 'roteiro_gerando' | 'roteiro_pronto' | 'falhou'
export type Fluxo = { proposta_id: string; etapa: FluxoEtapa; headline: { id: string; texto: string };
  roteiro: { id: string; nome: string; status: RoteiroStatus; formato: EstruturaFormato; duracao: 'auto'|'1'|'2'|'3'; ordem_cta: RoteiroEstrutura; versao: number } | null;
  post: PostRef | null; estruturas: EstruturaUso[]; legenda: 'pendente' | 'gerada' | 'indisponivel'; erro_codigo: string | null }
export type ImportacaoRelatorio = { id: string; fonte: 'referencia' | 'maquina_de_roteiros'; status: 'simulada'|'em_andamento'|'concluida'|'falhou';
  dry_run: boolean; arquivo_sha256: string; linhas_total: number; perfis_criados: number; perfis_mesclados: number; estruturas_criadas: number;
  estruturas_atualizadas: number; estruturas_inalteradas: number; estruturas_ignoradas: number; ignoradas_motivos: Record<string, number>;
  blocos_criados: number; campos_nao_importados: string[]; erro: string | null; created_at: string; finished_at: string | null }
export type VideoPorLinkResultado = { viral: ViralCard; perfil_criado: boolean; ja_existia: boolean }
export type HeadlineRoteiroItem = { headline: { id: string; texto: string; favorita: boolean; created_at: string; acima_recomendado: boolean } | null;
  headline_texto: string;
  roteiro: { id: string; nome: string; status: RoteiroStatus; formato: EstruturaFormato; duracao: 'auto'|'1'|'2'|'3'; ordem_cta: RoteiroEstrutura; versao: number;
    aprovacao: { estado: 'pendente' | 'aprovado' | 'rejeitado' } | null } | null;
  estruturas: EstruturaUso[]; conversa: { id: string; titulo: string } | null; post: PostRef | null; created_at: string }
export type EstruturaOrigemCard = { headline: { id: string; texto: string } | null;
  roteiro: { id: string; nome: string; status: RoteiroStatus; formato: EstruturaFormato; duracao: 'auto'|'1'|'2'|'3'; ordem_cta: RoteiroEstrutura; versao: number } | null;
  estruturas: EstruturaUso[]; formato: EstruturaFormato | null; legenda: { texto: string | null; origem: 'ia' | 'usuario' | null }; conversa: { id: string; titulo: string } | null }
```

### 11.2 Additive changes to existing types (FE-2/FE-4 own the edits in their files)
`Agente` → `'unificado'` (deprecated alias of the old union kept for one release); `MencaoTipo` + `'estrutura'`; `Mensagem` + `tipo`, `propostas`, `fluxo`; `Mencao` + `via?: 'texto'`; `Headline` + `estruturas: EstruturaUso[]`; `Roteiro` + `formato`, `ordem_cta`, `estruturas`, `conversa`; `RoteiroCreate`-side form state + `formato`;
`PerfilMonitorado` + `monitorar: boolean`, `estruturas_total: number`, `selecionado_pela_marca?: boolean`; `ViralDetalhe` + `estruturas: EstruturaRef[]`, `origem_inclusao?: 'sync'|'link_manual'`; `HeadlineLote` + `aviso_sem_classificacao: number`.

### 11.3 Pages, routes, nav
- **Biblioteca** `/media-creation/biblioteca` (existing key `media-creation-biblioteca`): becomes **tabs `Perfis · Vídeos · Estruturas`** (URL `?aba=perfis|videos|estruturas`, default `videos` to keep today's landing). A **profile page** `/media-creation/biblioteca/perfis/:perfilId` (header from `GET /biblioteca/perfis/{id}` + list of its Estruturas + its videos; admin: sync/pause/monitorar/delete); **Estrutura detail** `/media-creation/biblioteca/estruturas/:id` (formula, ordered blocks with tempo/instrução/nota/×N, source video, "Usar no chat" → `/media-creation/chat?estrutura=<id>`; **admin**: edit formula/formato/objetivos, add/remove/reorder blocks (drag), block type picked from the catalog (`GET /estruturas/tipos-bloco`), a per-field provenance badge — "Preenchido por referência" (`referencia`) / "Sugerido pela IA" (`ia_sugerido`) — with Confirmar / Confirmar todos, **Publicar** on a `rascunho` (422 `rascunho_incompleto` rendered with the missing items), archive/restore/delete (confirm dialog, `estrutura_em_uso` explained)). Admin controls render only when `GET /estruturas/admin` says `is_admin`; non-admins never see provenance, `rascunho` or `arquivada`. Admin extras: filters "Pendentes de revisão" (`somente_pendentes_revisao`) and "Rascunhos" (`status=rascunho`, the auto-drafts), import report page `/media-creation/biblioteca/importacoes` (read-only report of `ImportacaoRelatorio`; the load itself is the MCP tool), **block-type catalog** page `/media-creation/biblioteca/tipos-de-bloco` (admin CRUD over `TipoBloco`, 409 `tipo_em_uso`/`tipo_protegido` explained). **Vídeos tab, admin:** "Adicionar por link" dialog (paste an Instagram post URL → `POST /biblioteca/virais/por-link`; renders `link_invalido`, `post_nao_encontrado`, `perfil_optout`, `fonte_nao_suporta_link`, and a "já estava na biblioteca" outcome for `ja_existia`).
  `SolicitarPerfil.tsx` / the member "add profile" flow disappears for non-admins (admins keep it, now a library write); **there is no member suggestion flow** (owner Q10); **Minha Biblioteca** (`/media-creation/minha-biblioteca`) is the brand's *selection* over the platform library (unchanged UI, new data source).
- **Chat** `/media-creation/chat` (existing key): the Headline/Roteiro `Tabs` are removed; one conversation rail per marca; `Composer` unchanged (+ `@estrutura` in `MencaoPicker`); assistant `texto` messages render `propostas` as cards (headline, the Estrutura chip(s) with `@handle`, "Criar roteiro" button; chip → Estrutura detail); `perfil_ambiguo` renders the candidate chips from `meta.resolucao_perfis`; a `roteiro_gerado` message renders `Fluxo` (status badge, the roteiro's `formato`, roteiro preview when `completo` — spoken script for reels, a slide list for carrossel, screen texts + caption for post, a frame list for stories, all from the markdown by the `**Slide/Tela/Quadro N**` headings — links: **Abrir roteiro** → Headlines e Roteiros, **Ver card** → Esteira; the "Estruturas usadas" block list; legenda state). While `etapa='roteiro_gerando'` poll `GET /roteiros/{id}` (≤ 3 s, stops at terminal). `?conversa=<id>` deep-links a conversation. Old conversations open as unified.
- **Headlines e Roteiros** — NEW page `/media-creation/headlines-roteiros`, key `media-creation-headlines-roteiros` (new, via M3 `status_pagina`), nav item added to the CoreStudio **top** items after "Criar Headlines e Roteiros" (icon `Clapperboard`). One row per `HeadlineRoteiroItem`: headline, linked roteiro (status, formato, ordem do CTA, duração, versão, approval badge once S3), Estrutura chips, link to the source conversation, link to the card; actions reuse the existing favoritar / editar / excluir / reprocessar / Roteiro Avançado mutations; filters `q`, estrutura, perfil, roteiro status. **It folds `HeadlinesFavoritas.tsx` + `Roteiros.tsx`**, but those two files and their nav items/keys stay until S8 lands (§13).
- **Esteira card**: a new section `components/geracao/esteira/secoes/EstruturasSecao.tsx` (reads `GET /esteira/posts/{id}/origem`): headline, roteiro link, Estrutura(s) + profile, formato (any of the four), duração, ordem do CTA, caption (editable through the existing PATCH), "aguardando aprovação do roteiro" — one-line mount in `PostCardDialog`.
- **Surface pickers** (one shared **`components/geracao/estruturas/EstruturaPicker.tsx`**): multi-select Estruturas (search, profile filter, max 3) + "Perfil…" shortcut; used by the headline forms (`FormMePublico`, `FormViral`, `GerarHeadlineWizard`), `RoteiroAvancadoModal` (**also gets a `formato` selector**, enabled only while no Estrutura is picked; with Estruturas the formato is theirs; 422 `formatos_misturados`/`formato_diferente_da_estrutura` rendered), the Esteira card dialogs (`GerarHeadlinesDialog`, the roteiro modal opened from the card) and the chat `MencaoPicker`. A `perfil_ambiguo` 422 from a form renders the `candidatos` as buttons (re-submits with `referencia: {tipo:"perfil"}`).
- Nav (`navGroups.ts`): **only** the new item above; every existing key/href stays. `App.tsx`: the 5 new routes (headlines-roteiros, perfis/:id, estruturas/:id, importacoes, tipos-de-bloco) + `?aba` handling — integrated by the tech-lead in one commit (collision class C1).

### 11.4 Server-state rules the FE must obey (`KB § PATTERNS/common/server-state-family-index.md`)
Never `isLoading` as a lie (`showSkeleton = isPending && !data`); every write fills every cache entry it touches (`useCacheWriteMutation`): choosing a headline writes the proposta, the headline lists, the roteiro list/detail, the Esteira board, the card origin; a refusal is never silent (every code in §5 has a pt-BR toast/inline message); a draft says it is unsaved (Estrutura admin editor: dirty badge, `expected_versao` conflict dialog on 409 `versao_desatualizada`).
Consume `@noctusai/lib` organs (no local re-implementation: drag-reorder, dialogs, badges); no `PerfilMonitorado` array assumption (the list is `{items,total}`).

---

## 12 · Security and LGPD (flag: **`security` and `legal-advisor` review EST-2 + EST-3 + EST-5 before integrate**)
1. **Access tier** §4.1; strict `401`/`403` tests; the non-admin response never carries `proveniencia`, `ref_externa`, `referencia_rotulo`, `formula_herdada_de`, `pendente_revisao`, `rascunho|arquivada` rows (a test serialises each response and greps the forbidden keys).
2. **Prompt injection / output**: formulas, notes, block names, transcripts, imported text and the user's chat text are untrusted data inside `<material>` / `dados_nao_confiaveis`; model JSON is schema-validated (`saida_ia`), never executed; citations/blocks validated server-side (§8.5); no HTML/links in AI output (existing guard).
3. **Vendor-derived data**: the reference dataset (vendor text **plus** the owner's in-session fill), the Máquina file and their rows never enter git, logs, tool results or error messages (ids + reason codes only). Provenance of the CoreStudio extraction ("extração autorizada", file header) is recorded in the import row `arquivo_nome`/`fonte`; `legal-advisor` confirms licence/ToS posture before the first `apply` on prod.
4. **LGPD**: Estruturas are derived from third-party creators' public content; update `projects/core-studio-build/ROPA-biblioteca.md` (new categories: Estruturas + notes, imported data, platform-wide scope, retention exemption of §4.3 #5, opt-out cascade §4.3 #7). Opt-out purges profile + videos + blobs + Estruturas and leaves only content-free event rows; the load, `POST /perfis` and `POST /virais/por-link` refuse opted-out handles; `link_manual` videos and auto-drafts follow the same retention/opt-out rules as synced ones.
5. **Spend/abuse**: the load has no model spend (no budget needed); the per-run `importacao_em_andamento` lock; `max_body` override **16 MiB** on one platform-only route; auto-draft AI is capped by `estruturas_autodraft_dia` (config, finite) and metered on the ingestion org's LLM budget; `por-link` and `a-partir-do-viral` carry `@limiter`; library reads paged ≤ 50, no export route (bulk-scrape surface). **Add-by-link SSRF/abuse:** only `instagram.com` post URLs are accepted (host allowlist, the shortcode is extracted and re-composed — the raw URL is never fetched), only through the existing adapter.
6. **Idempotency/concurrency**: `expected_versao` on every Estrutura write; the choose-headline claim + lease (§9.2); import key `(fonte_externa, ref_externa)`.

---

## 13 · Slice plan (file-disjoint within a wave; each slice in its own `task_branch` off `origin/dev`)

**Avoid list (in flight — do not touch; sequence after):**
- **S3 `feat/cs-roteiro-approval`** owns `services/roteiro_service.py`, `routers/roteiros.py`, `schemas/roteiros.py`, `services/esteira_service.py` (`_pendencias` only), `esteira_config.py` (role `agendado` only), `tests/modules/media_creation/test_roteiro_aprovacao.py`, its migration (+ the seed approvals organ render). **Our slices that edit the first three (EST-RO, UNI-1b) run after S3 is merged**; everything else here is built to leave them alone (card origin = a new router; auto-card calls `EsteiraService` without editing it).
- **S5 `feat/cs-media-storage-lifecycle`** owns `midia_storage.py`, `services/post_assets_service.py` (upload path), `tests/…/test_midia_storage.py`. No slice here touches them.
- **Later CoreStudio slices (not yet branched; reserve):** S4 (`services/publish_service.py`, `publicacao_scheduler.py`, `post_publicacoes_service.py` status transitions), **S8** (`pages/geracao/Roteiros.tsx`, `pages/geracao/Esteira.tsx`, NEW `components/corestudio/**`, `hooks/useCorestudioPost*.ts`), S7 (`routers/posts.py`, `services/generation_service.py`, `routers/generation.py`, `pages/geracao/Carrosseis.tsx`). We edit none of these; the combined page and its redirect slice are arranged around S8 (below).
- Re-check `noctus.dev.branch_pointer action=list` and `git branch -r` at every slice start (S3 had no remote branch when this was written).

**Collision classes:** **C1** `frontend/src/App.tsx` + `nav/navGroups.ts` — tech-lead (FE-Z) only, one commit. **C2** `media_creation/__init__.py` and `routers/__init__.py` — additive one-liners, the integrator resolves. **C3** `app/config.py`, `app/main.py`, `services/geracao_jobs.py::ALL_JOB_TYPES` — **EST-1 declares every new setting/override/job type up front** (settings: `corestudio_biblioteca_org_id` = the NoctusAI org, `corestudio_biblioteca_user_id`, `biblioteca_max_perfis_plataforma=1000`, `estruturas_ia_model` (default `biblioteca_llm_model`, must be priced in `llm/models.py`), `estruturas_autodraft_dia`; main.py body override 16 MiB; job types `estruturas.importar`, `fluxo.finalizar_card`, `estruturas.rascunho_do_viral`); later slices read them. **C4** migrations: M1→M2→M3 enqueue strictly one after another (`noctus.dev.next_migration_number`), M4 after S3. **C5** `seed/lib/**` — none touched. **C6** `types/geracao.ts` — FE-2/FE-4 only, additive lines per §11.2. **C8** `saida_ia.py` — EST-FMT only (additive validators); EST-5 keeps its validators in the NEW `saida_ia_estruturas.py`. **C9** `services/biblioteca_ingestao.py` — EST-2 owns it and exposes the `depois_de_classificar` seam; EST-5 only registers a callback from its own file. **C7** `mcp/noctusai/tools/noctus/dev/verify_db_guards.py` — each migration slice appends its own probes.

| Wave | Slug | Agent | Files owned (file-disjoint) | Depends on | Migration | Acceptance criteria |
|---|---|---|---|---|---|---|
| 0 | **EST-1** `cs-est-model-api` | backend-engineer | NEW `migrations/<M1>_cs_estruturas.sql`; NEW `modules/media_creation/estruturas_tipos_bloco.py` (the 21 + `Outro` rows copied from `catalogo-blocos.json`, `seed_sql()`), `estruturas_formatos.py` (enums; `reels→reel, carrossel→carrossel, stories→story, post→feed`); NEW `schemas/estruturas.py`, `services/estruturas_service.py`, `routers/estruturas.py` (§6.1 incl. `tipos-bloco` read), `routers/estruturas_admin.py` (§6.2: create/patch/blocos/confirmar/**publicar**/arquivar/restaurar/delete + tipos-bloco admin; **not** `a-partir-do-viral`); `__init__.py` + `routers/__init__.py` (2 lines); `app/config.py` (all C3 settings), `app/main.py` (16 MiB override), `geracao_jobs.py::ALL_JOB_TYPES` (3 names); NEW `verify_db_guards.py` probes (events append-only, usos carve-outs, tipo events, status/formato CHECK, UNIQUE keys, `sistema` row protection); NEW `tests/modules/media_creation/test_estruturas_*.py`, `test_estruturas_tipos_bloco_seed.py` | — | **M1** | every §3.1 table/constraint/RPC exists and replays twice on PGlite; the migration carries exactly `seed_sql()`; blocks reference the catalog (`Outro` exists, cannot be deleted); each mutation is one RPC writing its event in the same call; stale `expected_versao` ⇒ 409 `versao_desatualizada`; provenance rules (edit ⇒ `admin`, confirm flips `referencia`/`ia_sugerido`, untouched fields keep origin); `publicar` refuses an incomplete draft (`rascunho_incompleto`); non-admin responses carry no admin fields (serialise-and-grep test); strict `401`/`403` tests on every route; `ativa` without formato/objetivos refused; hard delete refused with usos; `access_tier_catalog` shows reads `org`, writes `platform`; scan_wiring clean |
| 0 | **FE-1** `cs-est-fe-biblioteca` | frontend-engineer | NEW `types/estruturas.ts` (§11.1 verbatim, first commit); NEW `hooks/geracao/useEstruturas.ts` (+test; incl. tipos, importações, por-link); `pages/geracao/Biblioteca.tsx` (tabs, admin "Adicionar por link"); NEW `pages/geracao/BibliotecaPerfil.tsx`, `EstruturaDetalhe.tsx`, `BibliotecaImportacoes.tsx`, `BibliotecaTiposBloco.tsx`; NEW `components/geracao/biblioteca/estruturas/**` (list, card, blocks editor with catalog type select, provenance badges, confirm bar, publish bar, por-link dialog); `components/geracao/biblioteca/SolicitarPerfil.tsx` (admin-only), `ViralModal.tsx` (+ `estruturas` chip list), `hooks/geracao/useBiblioteca.ts` (`{items,total}` perfis, admin gating); tests | EST-1 contract only (builds against §6/§11 with fixtures; integrated after EST-1) | no | tabs + profile page + detail + admin editor + catalog + importações + por-link dialog per §11.3; non-admin sees no provenance/admin controls/drafts; 409 conflict dialog; confirm per field and all; `showSkeleton`/refusals rendered; no local organ re-implementation; routes **not** added here (FE-Z) |
| 1 | **EST-2** `cs-est-platform-scope` | backend-engineer | NEW `migrations/<M2>_cs_library_platform_scope.sql`; `routers/biblioteca.py`, `schemas/biblioteca.py`, `services/biblioteca_service.py`, `biblioteca_ingestao.py` (+ the `depois_de_classificar` seam), `biblioteca_fonte.py`, `biblioteca_transcricao.py`, `biblioteca_optout.py`, `viral_card.py`, `biblioteca_scheduler.py`; **`POST /biblioteca/virais/por-link`** (+ service); probes; updated biblioteca tests/conftest; ROPA doc update | EST-1 (M1 for the cascade) | **M2** | every row of §4.3 changed; reads `org`, writes `platform` (strict 401/403); library tables have no browser grant/policy; ingestion uses the NoctusAI org (`ingestao_sem_org_plataforma` is a visible `falha`, never a silent skip); opt-out purge deletes Estruturas and writes content-free events; `perfil_com_estruturas` guard; retention exemption works; `/perfis` paged shape; `cs_perfil_eventos` written by every admin write; **por-link**: dedupe by shortcode and by `(perfil_id, ig_media_id)` (second paste ⇒ 200 `ja_existia`, no new job), profile auto-created `monitorar=false`, opt-out ⇒ 409, same normaliser + jobs as sync, `link_invalido`/`post_nao_encontrado`/`fonte_nao_suporta_link` coded, host allowlist test, Apify single-post support **verified or the coded 409 kept**; the seam fires once per classification and never fails the job; **security + legal-advisor review before integrate** |
| 1 | **EST-3** `cs-est-loader` | backend-engineer | NEW `services/estruturas_import.py` (validators, mapping §7.1/§7.2, merge by handle, idempotent upsert via the EST-1 RPCs), `schemas/estruturas_importacao.py`, `routers/estruturas_importacao.py` (§6.3), job handler `estruturas.importar`; NEW `mcp/noctusai/tools/noctus/sw/estruturas_import.py` (+ `sw/__init__.py` registration, MCP tests); NEW **synthetic** fixtures (the shape of both files, ~20 rows, no vendor text) + tests. **No model client, no `saida_ia`, no prompts.** | EST-1 | no | maps every field of §7.1/§7.2 with the stated provenance (`fonte`/`referencia`; `referencia` formula when `formula_herdada_de`); every row accounted for (`created+updated+unchanged+ignored == linhas_total`) with the coded reasons of §7.1; tipo looked up by name in the catalog (`tipo_desconhecido` ignored; Máquina → name match else `Outro`); profiles merged by normalised handle across both files, new ones `monitorar=false`; dry-run writes nothing but the `simulada` lote; apply refused without a same-sha simulation (409); same file twice ⇒ all `inalteradas`; `admin`-origin fields never overwritten; opted-out handles skipped; **grep test: the module imports no LLM client**; MCP tool returns counts + codes only and logs no row text |
| 1 | **EST-4a** `cs-est-retrieval-chat` | backend-engineer + ai-engineer (prompts) | NEW `services/estruturas_retrieval.py`, `services/propostas.py`, `prompts/estruturas_contexto.py`; `services/chat_contexto.py` (pool, mentions, **brains section**), `prompts/chat_headline.py` (shared fence only if needed), NEW `routers/estruturas_resolver.py` (the `resolver-perfil` route; included **before** EST-1's `estruturas` router); tests | EST-1 (EST-2 for brand-selection semantics, merged first is easiest) | no | §8.1–§8.3 implemented; resolver pinned by the examples + a table-driven set (accents, `@handle`, nome exact, ambiguous, not found, no-trigger text ⇒ nothing resolved); pool scope (selected profiles → whole library) + round-robin + seeded determinism; `modo_de_selecao` with Estruturas incl. `perfil_ambiguo` (no pool in context); **brains + bio present in the context** and the placeholder rule in the material; citation validator drops unknown codes, different-formato codes and leftover-bracket headlines and logs the events; the model is never asked to use tools; context budget respected |
| 1 | **UNI-1a** `cs-uni-chat-headlines` | backend-engineer + ai-engineer (prompt) | NEW `migrations/<M3>_cs_unified_chat.sql`; `routers/chat.py`, `schemas/chat.py`, `services/chat_service.py`, NEW `services/fluxo_service.py` (steps 1–3 + proposta persistence), NEW `prompts/chat_unificado.py`; probes; tests incl. the 8-conversation legacy read | EST-1 | **M3** | `agente` ignored/accepted, legacy rows listed as unified; SSE `meta`/`done` frames per §6.5; propostas persisted with validated Estrutura links; `escolher` claim/lease idempotency (double click ⇒ one headline, `ja_existia`); headline saved `favorita` with `conversa_id`/`proposta_id`; usos written; `fluxo_etapa` recorded; pre-flight refusals coded; every transition writes `cs_fluxo_eventos`; M3 also adds `cs_roteiros.formato` and relaxes `cs_posts_formato_check`; strict 401 |
| 1 | **FE-2** `cs-uni-fe-chat` | frontend-engineer | `pages/geracao/Chat.tsx`, `components/geracao/chat/**`, `hooks/geracao/useChat.ts`, `types/geracao.ts` (additive §11.2 chat lines); tests | UNI-1a/UNI-1b contract only | no | per §11.3 Chat: no tabs; propostas cards; ambiguity chips; `roteiro_gerado` rendering per formato + polling; `?conversa=` and `?estrutura=` deep links; FE parser `extrairHeadlines` removed (server propostas only); refusals visible |
| 2 | **EST-4b** `cs-est-retrieval-forms` | backend-engineer | `services/headline_pipeline.py`, `services/headline_service.py`, `schemas/headlines.py`, `routers/headlines.py`, `prompts/headline_geracao.py`; tests | EST-1, EST-2, EST-4a | no | §6.6 + §4.3 #8: pool = Estruturas; `estrutura_ids` / (`viral_id` xor `estrutura_id`); formato/gatilho filters through the source video with `aviso_sem_classificacao`; free-text resolution with 422 `perfil_ambiguo`; **placeholders filled from brains + bio, bracketed headlines dropped and counted**; usos written per headline; legacy `viral` kept; `fallback_metodo` intact |
| 2 | **EST-5** `cs-est-autodraft` | ai-engineer + backend-engineer | NEW `services/estruturas_ia.py`, `services/estruturas_autodraft.py` (callback for the EST-2 seam + job handler `estruturas.rascunho_do_viral`), `prompts/estruturas_derivacao.py`, `saida_ia_estruturas.py`, `routers/estruturas_ia.py` (`POST /estruturas/a-partir-do-viral`); tests | EST-1, EST-2 (seam) | no | §8.8: one `rascunho` (`viral_auto`, all fields `ia_sugerido`, typed blocks, events `criada_automatica` + `ia_preenchida`) per analysed video, idempotent; invalid model output ⇒ coded job failure, **no** partial Estrutura; daily cap and ingestion-org metering enforced; drafts invisible to non-admins, retrieval and generation until `publicar`; `a-partir-do-viral` shares the service (422 `viral_sem_conteudo`, 409 duplicate); untrusted text fenced; **security + legal-advisor review before integrate** |
| 2 | **EST-FMT** `cs-est-formatos` | ai-engineer | NEW `prompts/roteiro_formatos.py` (carrossel / post / stories builders + the sentinel contract, reels delegates to the existing builder); `saida_ia.py` (per-format validators, additive); `prompts/legenda_reel.py`, `services/legenda_service.py` (format-aware; `post` reuses the roteiro's `### Legenda`); tests | — (S6 landed; **re-check S3 has not edited `saida_ia.py`**) | no | §8.7 grammars validated exactly (slides 1..20 ≤ 400 chars, screens 1..8 ≤ 200 + `### Legenda` ≤ 2 200, frames 1..15 ≤ 300); invalid ⇒ coded `falha`, never trimmed; prompt versions recorded; sentinel parser shared with EST-RO; no URLs/HTML; reels behaviour unchanged (existing roteiro tests green) |
| 2 | **HR-1** `cs-est-hr-endpoints` | backend-engineer | NEW `routers/headlines_roteiros.py`, `services/headlines_roteiros_service.py`, NEW `routers/esteira_origem.py`, `services/esteira_origem_service.py`; tests | EST-1, UNI-1a (M3 columns) | no | §6.8 / §6.9 exact shapes incl. `formato`; foreign marca/post 404; `aprovacao` is `null` until wave 3; roteiros without headline appear; strict 401 |
| 2 | **FE-3** `cs-est-fe-hr-page` | frontend-engineer | NEW `pages/geracao/HeadlinesRoteiros.tsx`, `components/geracao/headlines-roteiros/**`, `hooks/geracao/useHeadlinesRoteiros.ts`; NEW `components/geracao/esteira/secoes/EstruturasSecao.tsx` (+ the one-line mount in `PostCardDialog.tsx`); tests | HR-1 contract | no | §11.3 combined page + card section (formato shown for all four); reuses existing mutations; no edit of `Roteiros.tsx`/`Esteira.tsx`/`HeadlinesFavoritas.tsx`; approval badge hidden while `aprovacao === null` |
| 2 | **FE-4** `cs-est-fe-pickers` | frontend-engineer | NEW `components/geracao/estruturas/EstruturaPicker.tsx`; `components/geracao/headlines/{FormMePublico,FormViral,GerarHeadlineWizard}.tsx`, `components/geracao/roteiro/RoteiroAvancadoModal.tsx` (+ formato selector), `components/geracao/esteira/GerarHeadlinesDialog.tsx`; `types/geracao.ts` (additive non-chat lines); tests | FE-1 (`useEstruturas`), EST-4b contract | no | picker used on all four surfaces (chat picker is FE-2's `MencaoPicker`); ambiguity candidates rendered; max 3 and same-formato enforced client + server; formato selector only without Estruturas; no `isLoading` lies |
| 3 | **EST-RO** `cs-est-roteiro` | backend-engineer + ai-engineer | `services/roteiro_service.py`, `routers/roteiros.py`, `schemas/roteiros.py`, `prompts/roteiro_geracao.py` (reels path wiring only); tests | **S3 merged**, EST-4a, EST-FMT | no | §6.7: `estrutura_ids`, `formato` (derived/explicit/422s), `conversa_id`, `ordem_cta`, `estruturas` out; **all four formats generate through the EST-FMT builders and validators**; sentinel parsing + validated block attribution; missing sentinel ⇒ `atribuicao_ausente`, not failure; `viral_id` ignored when `estrutura_ids` present; resolver on `instrucoes`; S3 approval flow untouched (its tests green) |
| 3 | **UNI-1b** `cs-uni-roteiro-card` | backend-engineer | `services/fluxo_service.py` (steps 4–7), NEW `services/fluxo_finalizar.py` (job handler + registration), `services/esteira_service.py` (`criar` only) + `schemas/esteira.py` (`PostCreate.formato?`), tests | UNI-1a, EST-RO, **S3 merged** | no | §9.2–§9.4: roteiro created through `RoteiroService` with defaults and the derived formato; card in "Headline + roteiro" bound with the truthful `cs_posts.formato`; finalizer saves the caption only when `legenda IS NULL` (post: from the roteiro's `### Legenda`; others: `LegendaService`) and records `legenda_falhou` codes; A1–A3 verified against S3 (note divergences); crash-resume test (kill after each step ⇒ re-click resumes, no duplicates); polling budget respected; events complete |
| 3 | **MET-1** `cs-est-metrics` | backend-engineer | NEW `migrations/<M4>_cs_estruturas_metricas.sql` (views), `services/estruturas_metricas_service.py`, `GET /estruturas/{id}/metricas` (admin) in NEW `routers/estruturas_metricas.py`; tests | S3 merged, UNI-1b | **M4** | each §10 metric has one view/query; approval rate per Estrutura joins S3 events; admin endpoint returns counts only |
| 4 | **FE-3b / cleanup** | frontend-engineer, backend-engineer | redirect `Roteiros`/`HeadlinesFavoritas` routes to the new page; hide their nav items; M5 (owner-gated) | S8 merged; ≥ 2 deploys after M3 | **M5** | old URLs still resolve (redirect), keys stable; M5 per §3.5 |
| — | **FE-Z** (tech-lead, inline) | — | `App.tsx` (5 routes + redirects), `nav/navGroups.ts` (1 item) | FE-1…FE-4 | no | one commit; `filterNavByPageStatus` shows the page only after the M3 row |

**Order of integration:** EST-1 → (EST-2, EST-3, EST-4a, UNI-1a; migrations M2 then M3 sequentially) → (EST-4b, HR-1, EST-5 after EST-2, EST-FMT) → FE slices against the merged APIs → **S3** → EST-RO → UNI-1b → MET-1. Re-run `gate_sweep` on the merged tip, `migration_replay`, `predeploy_check social-wiring`; M1–M3 are applied to prod with owner consent via `migrate_product` **before** the image deploy; the library pages stay `desenvolvimento` (owner-only) until validated; **the load `apply` on prod happens only after the security/legal review and the owner's go** (it is a data load with no model spend; the auto-draft pipeline stays dark until `biblioteca_ingestao_habilitada` is turned on).

---

## 14 · Owner answers (closed 2026-11-15) — no open owner question remains
| Q | Owner answer (binding) | Encoded in |
|---|---|---|
| Q1 ingestion org | **The NoctusAI org** (the one holding the Meta + Apify credentials) | §4.3 #2, DC5 |
| Q2 roteiro formats | **All formats now**: reels, carrossel (per-slide text), post (screen text + caption), stories (per-frame); `formato_sem_roteiro` removed | §6.7, §8.7, §9, §11 |
| Q3 unconfirmed fields | Filled fields are **usable by orgs immediately**; provenance visible to admins only | DC2, DC3, §6.0 |
| Q4 admins add videos | By profile sync **and** by pasting a single Instagram post link (new admin endpoint, tier `platform`, deduped by IG media id/shortcode) | §4.2, §13 EST-2 |
| Q5 Máquina extra fields | Not imported (kept) | §7.2 |
| Q6a derive the 52 | Moot: the 52 unavailable records are **dropped** | §7 |
| Q6b `[placeholders]` | Filled by the AI from the **org-scoped brains (Cérebro) + bio (Meu Perfil)**; no brackets left in output | §6.6, §8.1, §8.4, §8.5 |
| Q7 AI-fill cost | Moot: **no AI fill at import** (reference dataset loaded as is) | §7 |
| Q8 roteiro as job | The job design stands (DC1 confirmed) | DC1 |
| Q9 auto-draft | **Yes**: a newly analysed viral video auto-creates a **draft** Estrutura, not usable until an admin publishes | §8.8 |
| Q10 member suggestions | **No**: only admins add profiles | §4.2, §11.3 |
| Mix cap | **3, confirmed** | §8.4, §6.7 |

**Verification items for the slices (facts to check in code/at runtime, not owner questions):** (1) EST-2: does the Apify actor accept a single post URL? If not, `por-link` answers the coded 409 `fonte_nao_suporta_link` until a source can (the contract does not assume it). (2) EST-2: confirm the classify handler's gating so a manually added post is classified regardless of the viral threshold. (3) UNI-1b: S3's initial approval state (A1–A3, §9.4). (4) EST-1/EST-5: `estruturas_ia_model` is priced in `llm/models.py` (an unpriced model records cost 0 and disarms `enforce_budget`). (5) EST-FMT: S3 has not edited `saida_ia.py` since this was written. (6) EST-1: the catalog's `Outro` description text is written by the slice (the owner's file has 21 rows, no `Outro`).

## 15 · Tests (minimum, per slice; red-first)
Strict `== 401` / `== 403` per route (no `in (…)`); RPC-level tests on real Postgres (PGlite replay twice) for every Estrutura mutation incl. stale `expected_versao`, reorder with the deferred unique, provenance transitions, hard-delete-with-usos refusal; serialise-and-grep for non-admin responses; loader on a **synthetic** corpus shaped like both files (every ignore reason, `formula_herdada_de`, `Outro`, empty `nota`, Máquina name-match vs `Outro`, handle merge across files, opted-out handle); load idempotency (twice ⇒ zero changes) and a no-LLM-import grep test; catalog seed pinned to `seed_sql()`; por-link dedupe/opt-out/host-allowlist; auto-draft idempotency and invalid-output-no-draft; per-format roteiro grammars (valid + each rejection) and `post` caption reuse; placeholder-remanescente drop; resolver table tests; citation validator; SSE frame order incl. `done.propostas`; saga crash-resume at each step; finalizer reschedule/terminal/caption-NULL-only; opt-out cascade; retention exemption; legacy conversation read; `test_migration_*` pins; GuardProbes for every new trigger/CHECK/UNIQUE (`verify_db_guards`).
