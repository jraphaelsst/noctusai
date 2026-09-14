# CONTRACT — Julia: `academia-de-reciclagem` knowledge API + `agents` product (W0)

> Written by the tech-lead on 2026-09-14, BEFORE any slice is dispatched. Every slice builds to THIS document, and it is the acceptance gate for each of them.
> Roadmap: `project-history/roadmaps/julia-agents-academia-2026-09.md`. Procedure: `KB § PATTERNS/architect/fe-be-contract-first-dispatch.md`.
>
> **Sourcing.** Every sibling-derived shape was EXTRACTED from the sibling workspace at `2cbbe16`: its `mcp/academia/types.py`, `backend/app/schemas`, `realtime.py`, `permissions.py`, and the knowledge-base file structure. Nothing is guessed. Sections marked ⏳ wait on the noc interface inventory (auth dependency names, SSE router, ChatWindow seams, SDK tool API) and are filled in before W0 is committed.
>
> **Public repo.** This file contains shapes only. No client or company facts, people's names or knowledge content belong here or in any fixture.

---

## 0 · Naming and conventions

- **Field names stay PT-BR** (`titulo`, `contexto`, `motivo`, `estado`, …), exactly as the sibling's tools defined them. Julia's skills and tool calls are already written against these names; renaming them would silently break every skill. Code identifiers, commits and docs are EN.
- **Stable codes:**
  - Decisions: `D-nn` (2+ digits).
  - Open questions: `Q-nn`.
  - Tasks: `T-nnn` (3 digits).
  - Roadmap phases: `P<n>`.
  - Content drafts: `C-nnn`.

  Codes are allocated server-side, under a row lock in `code_counters`. A client never sends a code on create.
- **Timestamps:** ISO-8601 `timestamptz` in UTC. Dates without a time (`data`) are `YYYY-MM-DD`.
- **Envelope.**
  - Every list response is `{"items": [...], "total": <int>}`.
  - Every single-resource response is the bare object.
  - Every error uses the seed error shape: `{"detail": "<pt-BR message>", "code": "<machine_code>"}`.
- **Strictness.**
  - Request models REJECT unknown fields (`extra="forbid"` → 422), so a stale client fails loudly instead of being silently ignored.
  - Response models may gain fields; consumers must ignore unknown response fields.

---

## A · academia-de-reciclagem — data model (schema `academia_de_reciclagem`)

Every table has these columns: `id uuid pk`, `org_id uuid not null` with RLS via `public.current_org_id()`, `created_at`, `updated_at`. RLS is enabled on every table.

### A.1 `kb_entries`

| Column | Type | Rule |
|---|---|---|
| `slug` | text | Unique per org. Kebab-case, e.g. `dominio-regulatorio-pnrs`. |
| `categoria` | text | CHECK in (`contexto`, `dominio`, `instrucoes`, `skills`, `workflows`, `mcp-servers`, `historico`, `marca`, `evals`, `geral`). Derived from the sibling's top-level KB folder on import. |
| `subcategoria` | text null | E.g. `regulatorio`, `residuos`, `metodologia` (from `DOMINIO/<sub>/`). |
| `titulo` | text | First `#` heading, or the frontmatter `titulo`. |
| `resumo` | text null | |
| `tags` | text[] | Default `{}`. |
| `corpo_md` | text | The markdown body, without frontmatter. |
| `frontmatter` | jsonb | Default `{}`. Holds unknown frontmatter keys verbatim, e.g. `origem`. |
| `current_revision_id` | uuid | FK to `kb_revisions`. |
| `arquivado` | bool | Default false. Replaces delete: entries are never hard-deleted. |

### A.2 `decisions`

| Column | Type | Rule |
|---|---|---|
| `codigo` | text | Unique per org. |
| `titulo` | text | |
| `contexto` | text null | |
| `decisao` | text | |
| `motivo` | text | |
| `alternativas_rejeitadas` | text null | |
| `data` | date | |
| `estado` | text | CHECK in (`vigente`, `superseded`). |
| `substitui` | text null | FK by code to `decisions.codigo`. |
| `superseded_by` | text null | |
| `relacionadas` | text[] | Default `{}`. E.g. an amendment: D-21 lists `D-10`. |

**Append-only.** A trigger rejects UPDATE of any column except `estado` and `superseded_by`, and rejects DELETE outright.

### A.3 `open_questions`

`codigo` · `pergunta` · `por_que_importa` · `bloqueia` · `destino_kb` (text null, a `kb_entries.slug`) · `estado` CHECK in (`aberta`, `respondida`) · `resposta` null · `respondida_em` null.

### A.4 `roadmap_phases`

`codigo` · `titulo` · `objetivo` · `concluida_quando` · `estado` CHECK in (`pendente`, `em-andamento`, `concluida`, `cancelada`) · `ordem` int.

### A.5 `tasks`

`codigo` · `titulo` · `fase` (a phase `codigo`) · `detalhe` null · `estado` (same CHECK as phases) · `bloqueada_por` text null (a task code, question code, or free text).

### A.6 `content_drafts`

`codigo` · `tipo` CHECK in (`roteiro`, `trilha`, `quiz`, `copy`, `proposta`, `outro`) · `titulo` · `corpo_md` · `referencia` null · `fontes` text[] (kb slugs).

### A.7 `timeline_events`

`data` date · `titulo` · `descricao`. Order by `data DESC, created_at DESC`.

### A.8 `research_sources`

`url` · `titulo` · `trecho_citado` · `resumo` · `kb_slug` (the entry the source is attached to) · `vigencia_confirmada` bool · `exige_da_empresa` null · `accessed_at` timestamptz NOT NULL.

### A.9 `code_counters`

`(org_id, prefix)` pk · `ultimo` int. Allocation is `UPDATE … SET ultimo = ultimo + 1 RETURNING` inside the create transaction. Seeded by the importer to the highest imported code per prefix.

### A.10 `kb_revisions` — append-only history for EVERY entity above

| Column | Type | Rule |
|---|---|---|
| `entity_type` | text | CHECK in (`kb_entry`, `decision`, `open_question`, `roadmap_phase`, `task`, `content_draft`, `timeline_event`, `research_source`). |
| `entity_id` | uuid | |
| `rev_no` | int | Unique with (`entity_type`, `entity_id`). |
| `op` | text | CHECK in (`create`, `update`, `archive`, `supersede`, `import`). |
| `snapshot` | jsonb | The full entity row AFTER the change. |
| `author_kind` | text | CHECK in (`human`, `agent`, `import`). |
| `user_id` | uuid null | |
| `agent_id` | uuid null | |
| `approval_id` | uuid null | UNIQUE on (`approval_id`, `entity_type`, `entity_id`) when not null. One approved call may legitimately write several revisions: a supersede writes two, the new decision and the old one. The single-use replay guard is the separate table `approval_consumptions(jti uuid pk, org_id, consumed_at)`; its INSERT happens first, in the same transaction, and a duplicate returns 409 `assertion_used`. |
| `channel` | text null | |
| `conversation_id` | uuid null | |
| `motivo` | text null | |
| `git_sha` | text null | |
| `git_author_raw` | text null | |
| `git_committed_at` | timestamptz null | |
| `git_message` | text null | |

**Grants and trigger.** UPDATE and DELETE are revoked from every role, and a trigger raises on both.

**Invariant.** Every write to A.1–A.8 inserts exactly one `kb_revisions` row in the same transaction. A write without one is a bug, and the tests assert it. The one exception is `supersede`, which writes two revisions (one per entity).

### A.11 `KnowledgeStore` Protocol — the seam shared by A1 (implements) and A2/B-routes (consume)

Location: `products/academia-de-reciclagem/backend/app/knowledge/store.py`. `FakeKnowledgeStore` (in-memory, same invariants) and `PgKnowledgeStore` sit beside it, with factory `get_knowledge_store(settings) -> KnowledgeStore`. Every method is `async`. Every method takes `org_id: UUID` first and a `prov: Provenance` on writes.

```python
@dataclass(frozen=True)
class Provenance:
    author_kind: Literal["human", "agent", "import"]
    user_id: UUID | None = None
    agent_id: UUID | None = None
    approval_id: UUID | None = None          # consumed via approval_consumptions BEFORE any write
    channel: str | None = None
    conversation_id: UUID | None = None
    motivo: str | None = None
    git_sha: str | None = None
    git_author_raw: str | None = None
    git_committed_at: datetime | None = None
    git_message: str | None = None

class KnowledgeStore(Protocol):
    # kb entries
    async def search_kb(self, org_id, *, consulta: str | None, categoria: str | None,
                        subcategoria: str | None, tag: str | None, limite: int, offset: int) -> tuple[list[dict], int]
    async def get_kb(self, org_id, slug: str) -> dict            # raises NotFound
    async def create_kb(self, org_id, data: dict, prov: Provenance) -> dict        # raises Conflict
    async def update_kb(self, org_id, slug: str, changes: dict, prov: Provenance) -> dict  # novo_slug inside changes; raises NotFound/Conflict
    async def archive_kb(self, org_id, slug: str, prov: Provenance) -> dict
    async def list_revisions(self, org_id, entity_type: str, entity_id: UUID) -> list[dict]
    # decisions
    async def list_decisions(self, org_id, *, estado: str | None) -> list[dict]
    async def get_decision(self, org_id, codigo: str) -> dict
    async def create_decision(self, org_id, data: dict, prov: Provenance) -> dict
    async def supersede_decision(self, org_id, codigo: str, data: dict, prov: Provenance) -> tuple[dict, dict]  # (nova, substituida); raises Conflict if already superseded
    # open questions
    async def list_questions(self, org_id, *, estado: Literal["aberta", "respondida", "todas"]) -> list[dict]
    async def create_question(self, org_id, data: dict, prov: Provenance) -> dict
    async def answer_question(self, org_id, codigo: str, resposta: str, prov: Provenance) -> dict  # raises Conflict if answered
    # roadmap + tasks
    async def list_phases(self, org_id) -> list[dict]
    async def update_phase(self, org_id, codigo: str, changes: dict, prov: Provenance) -> dict
    async def list_tasks(self, org_id, *, fase: str | None, estado: str | None) -> list[dict]
    async def create_task(self, org_id, data: dict, prov: Provenance) -> dict       # raises Invalid if fase unknown
    async def update_task(self, org_id, codigo: str, changes: dict, prov: Provenance) -> dict
    async def session_prep(self, org_id) -> dict
    # content / timeline / sources
    async def list_content(self, org_id, *, tipo: str | None) -> list[dict]
    async def get_content(self, org_id, codigo: str) -> dict
    async def create_content(self, org_id, data: dict, prov: Provenance) -> dict
    async def list_timeline(self, org_id, *, limite: int) -> list[dict]
    async def create_timeline_event(self, org_id, data: dict, prov: Provenance) -> dict
    async def create_source(self, org_id, data: dict, prov: Provenance) -> dict     # raises NotFound if kb_slug unknown
    # import (A2)
    async def import_entity(self, org_id, entity_type: str, natural_key: str, snapshot: dict,
                            prov: Provenance) -> dict   # upsert-by-natural-key + one 'import' revision; idempotent on (git_sha, natural_key)
    async def seed_counters(self, org_id, counters: dict[str, int]) -> None           # sets code_counters to max(current, given)
```

- **Errors:** `NotFound`, `Conflict` and `Invalid` are defined in `app/knowledge/errors.py`. B-routes map them to 404, 409 and 422. `approval_consumptions` duplicates raise `AssertionUsed`, which maps to 409 `assertion_used`.
- **Natural keys for `import_entity`:**
  - `kb_entry`: `slug`
  - `decision`, `open_question`, `task`, `content_draft`: `codigo`
  - `roadmap_phase`: `codigo`
  - `timeline_event`: `data|titulo`
  - `research_source`: `url|kb_slug`
- **Transactions:** a single import transaction is opened by the caller. `PgKnowledgeStore` exposes `async with store.transaction():`, and the Fake mirrors it with an in-memory snapshot and rollback.

---

## B · academia-de-reciclagem — HTTP API (prefix `/api`)

### B.0 Auth posture

**One dependency for every route.** It is composed in `app/dependencies.py` exactly like social-wiring's: `make_get_auth_context(session_store=…, api_token_resolver=SupabaseApiTokenResolver(schema="academia_de_reciclagem"), legacy_jwt_resolver=<JWT bridge>)` (seed `api/auth/session/dep.py:43`), and it returns `AuthContext`. The resolution order is the seed's: cookie `nai_session`, then `Bearer pk_*`, then legacy JWT, otherwise 401.

**Seed changes these routes depend on** (all from SEED-1, back-compat — every new field defaults so existing consumers are unchanged):
- **`AuthContext`** (`session/types.py:29`) gains `principal_agent_id: UUID | None = None` and `expires_at: datetime | None = None`.
- **`SupabaseApiTokenResolver(admin_client, *, schema)`** is promoted from `products/social-wiring/backend/app/services/api_token_resolver.py`. It selects `id, org_id, scopes, revoked_at, expires_at, principal_agent_id`. It refuses a token when `revoked_at IS NOT NULL` or `expires_at <= now()`, which returns 401. The social-wiring and erp-imobiliario product-local copies migrate to it in the same slice.
- **`require_scopes(*scopes, user_roles: frozenset[str])`** is a FastAPI dependency factory over `get_auth_context`. No scope check exists anywhere in the seed today; this is the first.
  - For `caller_kind == "product"`: every listed scope must be in `ctx.scopes`, else 403 `scope_missing`.
  - For `caller_kind == "user"`: the caller's org role (`public.noctus_users.org_role` ∈ `owner | admin | member | viewer`, core `001_noctusai_core.sql:39`; resolved like seed `_require_org_admin`, `auth_router.py:228`) must be in `user_roles`, else 403 `role_missing`. User sessions carry `scopes=[]` today (`session/store.py:178`), so scopes are never the user's authorization.
  - Routes use the admin client and therefore bypass RLS, so every query filters by `ctx.org_id` explicitly. RLS is defence in depth, never the authorization.
  - Role sets used below: `READ = {owner, admin, member, viewer}` · `WRITE = {owner, admin, member}` · `ADMIN = {owner, admin}`. (Security review 2026-09-14 suggested an `editor` role; noc has none, so `member` holds that position.)
- **Audit:** every resolved product-token call writes `api_token_audit(api_token_id, org_id, method, path, status, at)`, best-effort and logged loudly on failure.
- **Token table columns** (per product schema, migration-added): `expires_at timestamptz NOT NULL` for new tokens, `principal_agent_id uuid NULL`, `issuer text NULL`, `human_personal bool NOT NULL DEFAULT false`, `minted_by uuid NULL`.
- **Backfill of existing social-wiring/erp tokens.** They get `expires_at = now() + interval '365 days'`, under three conditions:
  - The migration is applied BEFORE the resolver that reads `expires_at` is deployed; the reverse order breaks every live token.
  - An audit row is written per backfilled token.
  - An alert fires 30 days before any token expires.

**How the agents product gets its academia token.** Tokens are minted in the TARGET product by an org admin via the seed route `POST /api/settings/api-tokens {label, scopes}` (`auth_router.py:173,266`), extended with `expires_at` (required, ≤ 90 days) and `principal_agent_id`. The secret is shown once and stored as the agents secret `ACADEMIA_API_TOKEN` (deploy secret, slice D1). It never goes into the Julia CLI's `env`.

**Two caller kinds, both org-scoped:**
- **SSO user**: browser session or JWT. Terminal-Julia uses a personal product token minted without `principal_agent_id`.
- **Product token** `pk_…` held by the `agents` control plane, with `principal_agent_id` = Julia's agent id and the scopes below.

**Scopes:**
- `academia:read`: every GET.
- `academia:kb:write` · `academia:decisions:write` · `academia:questions:write` · `academia:roadmap:write` · `academia:content:write` · `academia:sources:write`
- `academia:import`: admin-only, never granted to an agent.

**Product-token writes.** EVERY write by a `caller_kind == "product"` caller MUST carry a valid `X-Approval-Assertion` (§D), whether or not the token has a principal agent. The only exception is a token flagged `human_personal = true` (terminal-Julia's personal token): it needs no assertion, and its writes record `kb_revisions.user_id = minted_by`. A write-scoped product token without an assertion and without `human_personal` gets 403 `assertion_invalid`. An SSO user's write needs no assertion, but does need the `WRITE` role set.

**Role set per route:** every `GET` needs `READ`; every write in B.1–B.5 needs `WRITE`; `/api/import` needs `ADMIN`.

**Status taxonomy** (all endpoints):

| Status | Cause | Message for the user |
|---|---|---|
| 401 | No or invalid credential, or expired token | "Sessão expirada — entre novamente." |
| 403 `scope_missing` | Token lacks the scope | "Sem permissão para esta ação." |
| 403 `assertion_invalid` | Agent write with a missing, bad or expired assertion, or one that doesn't match the body | "Aprovação inválida — peça de novo." |
| 404 | Unknown code/slug, or it belongs to another org | "Não encontrado." |
| 409 `assertion_used` | The approval was already consumed | "Esta aprovação já foi usada." |
| 409 `conflict` | Slug exists, or the entity is already superseded or answered | Specific message per endpoint |
| 422 | Validation, including unknown request fields | Field-level |

Auth tests assert `== 401` strictly.

### B.1 Knowledge base

| Method + path | Request | Response | Notes |
|---|---|---|---|
| `GET /api/kb?consulta=&categoria=&subcategoria=&tag=&limite=20&offset=0` | — | `{items: KbEntrySummary[], total}` | Full-text search over `titulo`, `resumo`, `corpo_md`. `limite` ≤ 200. |
| `GET /api/kb/{slug}` | — | `KbEntry` | |
| `POST /api/kb` | `KbEntryCreate {slug?, categoria, subcategoria?, titulo, resumo?, tags?, corpo_md, motivo}` | `201 KbEntry` | `slug` is derived from `titulo` when omitted. 409 if the slug exists. |
| `PUT /api/kb/{slug}` | `KbEntryUpdate {titulo?, resumo?, tags?, corpo_md?, categoria?, subcategoria?, novo_slug?, motivo}` | `KbEntry` | Replaces the listed fields. `novo_slug` replaces the old `kb.mover` (409 on collision). |
| `POST /api/kb/{slug}/archive` | `{motivo}` | `KbEntry` | Sets `arquivado=true`. |
| `GET /api/kb/{slug}/revisions` | — | `{items: Revision[], total}` | Newest first. |

**Shapes.**
- `KbEntrySummary` = `{slug, categoria, subcategoria, titulo, resumo, tags, updated_at}`.
- `KbEntry` = the summary plus `{corpo_md, frontmatter, arquivado, current_revision: RevisionRef}`.
- `RevisionRef` = `{rev_no, author_kind, created_at}`.
- `Revision` = `{rev_no, op, author_kind, user_id, agent_id, approval_id, channel, conversation_id, motivo, git_sha, git_committed_at, created_at, snapshot}`.

**Side-effect.** Every write returns only after its `kb_revisions` row is committed. `motivo` is required on every write, as the sibling already required.

### B.2 Decisions

| Method + path | Request | Response | Notes |
|---|---|---|---|
| `GET /api/decisions?estado=` | — | `{items: Decision[], total}` | Ordered by code. |
| `GET /api/decisions/{codigo}` | — | `Decision` | |
| `POST /api/decisions` | `{titulo, contexto, decisao, motivo, alternativas_rejeitadas?, relacionadas?}` | `201 Decision` | Code is allocated. `data` = today. |
| `POST /api/decisions/{codigo}/supersede` | the same body | `201 {nova: Decision, substituida: Decision}` | One transaction: the new row gets `substitui=codigo`, and the old row gets `estado='superseded'` and `superseded_by=<new>`. 409 if the old one is already superseded. |

There is no PUT and no DELETE.

### B.3 Open questions

| Method + path | Request | Response |
|---|---|---|
| `GET /api/questions?estado=aberta\|respondida\|todas` (default `aberta`) | — | `{items, total}` |
| `POST /api/questions` | `{pergunta, por_que_importa, bloqueia, destino_kb?}` | `201 OpenQuestion` |
| `POST /api/questions/{codigo}/answer` | `{resposta}` | `OpenQuestion` |

- **Answer is idempotent-refused:** answering a question that is already answered returns 409.
- **The answer response includes** `aviso` when `destino_kb` is set: "Registre a resposta em /kb/{destino_kb}". The server does NOT write the KB entry, which keeps the sibling's behaviour.

### B.4 Roadmap and tasks

| Method + path | Request | Response |
|---|---|---|
| `GET /api/roadmap` | — | `{items: Phase[], total}` ordered by `ordem` |
| `PATCH /api/roadmap/{codigo}` | `{estado?, titulo?, objetivo?, concluida_quando?}` | `Phase` |
| `GET /api/tasks?fase=&estado=` | — | `{items: Task[], total}` |
| `POST /api/tasks` | `{titulo, fase, detalhe?, bloqueada_por?}` | `201 Task` (422 if `fase` doesn't exist) |
| `PATCH /api/tasks/{codigo}` | `{estado?, detalhe?, bloqueada_por?}` | `Task` |
| `GET /api/session-prep` | — | `{fase_atual: Phase\|null, proximas: Task[], bloqueadas: Task[], perguntas_abertas: int, perguntas_bloqueantes: OpenQuestion[]}` |

`/api/session-prep` has the same shape as the sibling's `tarefa.preparar_sessao` output.

### B.5 Content, timeline and sources

| Method + path | Request | Response |
|---|---|---|
| `GET /api/content?tipo=` | — | `{items, total}` |
| `GET /api/content/{codigo}` | — | `ContentDraft` |
| `POST /api/content` | `{tipo, titulo, corpo_md, referencia?, fontes?}` | `201 ContentDraft` |
| `GET /api/timeline?limite=20` | — | `{items, total}` (≤ 500) |
| `POST /api/timeline` | `{titulo, descricao, data?}` | `201 TimelineEvent` |
| `POST /api/sources` | `{url, titulo, trecho_citado, resumo, kb_slug, vigencia_confirmada, exige_da_empresa?}` | `201 ResearchSource` |

- **`POST /api/content`:** `aviso` is returned when `fontes` is empty for `roteiro`, `trilha` or `quiz`.
- **`POST /api/sources`:**
  - `url` must parse with a real host (no substring matching). The response carries `aviso` when the host is not on the primary-source allowlist.
  - `accessed_at` = now.
  - 404 if `kb_slug` doesn't exist.

### B.6 Import (admin)

`POST /api/import` accepts JSONL (`application/x-ndjson`) or multipart `bundle`. Scope `academia:import`, SSO admin only. Response: `{verificacao: {revisoes_git: int, revisoes_importadas: int, entidades: {<entity_type>: int}, hashes_head_ok: bool, codigos: {D: int, Q: int, T: int}}, avisos: string[]}`.

**Behaviour:**
- **Idempotent.** A re-import of the same bundle is a no-op; the dedup key is `git_sha` + path.
- **All-or-nothing:** a single transaction.
- **Refusal:**
  - Path denylist: any file whose path matches `.env*`, `*.pem`, `*.key`, `id_rsa*`, `*secret*`, `credentials*` or `.npmrc` is rejected with 422.
  - Content secret scan: a server-side scan (entropy threshold plus known token patterns such as `pk_`, `sk-`, `ghp_`, `AKIA`, `-----BEGIN`) runs on every line's `content`, and any hit is 422 `secret_detected`, naming the path but never the value.
  - Size cap: 422 `bundle_too_large` above 20 MB or 5,000 lines.

**Bundle line shape:**
```
{"path": "<repo-relative path>", "git_sha": "…", "git_author_raw": "…",
 "git_committed_at": "…", "git_message": "…", "content": "<file text at that commit>"}
```

**Mapping rules** (from the extracted sibling structure):
- **KB files.** `KNOWLEDGE-BASE/<FOLDER>/**.md` becomes a `kb_entry` (`categoria` = folder lower-cased, `DOMINIO/<SUB>/` gives `subcategoria`). Root `AGENT-CONTEXT.md` and `INDEX.md` are **skipped**: they are generated or agent-spec material, not project knowledge.
- **Bundled decisions file.** `KNOWLEDGE-BASE/DECISOES/0001-*.md` is split per table row `| D-nn | Decisão | Motivo |`. Each row becomes a `decision` with `titulo` = `decisao` = the Decisão cell, `motivo` = the Motivo cell, `data` = the file's frontmatter `data`, and `estado` = `vigente`.
- **Single-decision files.** `KNOWLEDGE-BASE/DECISOES/00nn-*.md` (not 0001) is one decision. Frontmatter supplies `codigo`, `titulo`, `data` and `estado`; the sections `## Contexto`, `## Decisão`, `## Motivo` and `## Alternativas rejeitadas` fill the fields. D-codes mentioned in the body are added to `relacionadas`.
- **Skipped:** `DECISOES/INDEX.md` (derived).
- **Timeline.** `KNOWLEDGE-BASE/HISTORICO/TIMELINE.md` becomes `timeline_event` rows, one per `## YYYY-MM-DD[ — título]` section.
- **Project state.** `projects/state/open-questions.json`, `roadmap.json` and `tasks.json` become rows, one per array item. Each commit's version of the JSON produces revisions only for the items that changed.
- **Specs.** `docs/SPEC.md` and `docs/OPEN-QUESTIONS.md` become `kb_entry` rows with `categoria='geral'`.
- **Revisions and authors.** Each revision's `snapshot` is parsed from THAT commit's content. `author_kind='import'`, and `user_id` = the importing admin (the raw git author is kept in `git_author_raw`).
- **Verification.** `hashes_head_ok` compares sha256 of each entity's latest body against the bundle's newest line per path.
- **What `revisoes_importadas` counts** (settled at A2 integration, 2026-09-14). It counts `import_entity` calls issued in this run, not net-new `kb_revisions` rows. `import_entity` returns the row whether or not it wrote, so a full idempotent re-run reports the same number while writing zero new revisions. Idempotency is proven by the store's revision count, never by this field.

**The bundle never enters the repo.** Exporting it is a local `noctus.dev.*` tool that writes outside the repo tree (scratch dir) and secret-scans first (built in slice A2).

---

## C · `academia.*` MCP tools → HTTP (sibling tool → contract)

The stdio server stays at `mcp/academia/`, rebuilt as a thin HTTP client: base URL plus a personal or product token, on noc's `mcp/_kit`. Tool names are UNCHANGED, so Julia's skills keep working.

| Sibling tool | Class | HTTP | Change |
|---|---|---|---|
| `academia.kb.buscar {consulta, pasta?, limite}` | read | `GET /api/kb` | `pasta` becomes `categoria[/subcategoria]` |
| `academia.kb.ler {caminho}` | read | `GET /api/kb/{slug}` | `caminho` becomes `slug` |
| `academia.kb.escrever {caminho, conteudo, motivo}` | write | `POST`/`PUT /api/kb` | Becomes `{slug?, categoria, titulo, corpo_md, motivo}` |
| `academia.kb.mover {origem, destino, motivo}` | write | `PUT /api/kb/{slug}` with `novo_slug` | Renamed semantics, same tool name |
| `academia.kb.index_sync` | — | — | **DEPRECATED, removed.** The DB has no unindexed documents. |
| `academia.kb.link_check` | — | — | **DEPRECATED, removed.** No file pointers any more. |
| `academia.decisao.registrar` | write | `POST /api/decisions` | Unchanged fields |
| `academia.decisao.listar {estado?}` | read | `GET /api/decisions` | |
| `academia.decisao.substituir {…, substitui}` | write | `POST /api/decisions/{substitui}/supersede` | |
| `academia.pergunta.adicionar` / `listar` / `responder` | write / read / write | B.3 | Unchanged fields |
| `academia.historico.append {titulo, descricao, data?}` / `timeline {limite}` | write / read | B.5 | |
| `academia.roadmap.ler` / `atualizar` | read / write | B.4 | |
| `academia.roadmap.render` | — | — | **DEPRECATED, removed.** The UI renders the roadmap. |
| `academia.tarefa.criar` / `atualizar` / `listar` / `preparar_sessao` | write / write / read / read | B.4 | |
| `academia.conteudo.salvar` / `listar` / `ler {caminho}` | write / read / read | B.5 | `ler` takes `codigo` instead of `caminho` |
| `academia.pesquisa.capturar_fonte {…, destino}` | write | `POST /api/sources` | `destino` path becomes `kb_slug` |

**Each tool's output = the HTTP response.** Errors map to the sibling's `_Out.error` shape: `{"ok": false, "error": {"status": <int>, "code": "<code>", "detail": "<msg>"}}`.

---

## D · Approval assertion (agents → academia), security H2

**The key.** Both products declare the settings field `approval_assertion_secrets: list[str]` on their `ProductSettings` subclass, loaded from env `APPROVAL_ASSERTION_SECRETS` (comma-separated, deploy secret, slice D1).
- **agents** signs with element `[0]`.
- **academia** accepts any element. Rotation = prepend the new key, deploy both, then drop the old one.
- **Missing or empty list:** the product refuses to start in prod (`required_prod_config`, `create_product_app` `app.py:57`). The key is never in the Julia CLI's `env`.

**One key list per audience.** `approval_assertion_secrets` is keyed by `aud`. Before a second target product accepts assertions, it gets its own list; a key for `academia-de-reciclagem` must never validate for another audience.

**Header:** `X-Approval-Assertion: <compact JWS, HS256>`. The claims:
```
{"jti": "<approval uuid>", "iss": "agents", "aud": "academia-de-reciclagem",
 "sub": "<agent uuid>", "org": "<org uuid>", "tool": "academia.kb.escrever",
 "method": "PUT", "path": "/api/kb/dominio-regulatorio-pnrs",
 "body_sha256": "<hex of the canonical JSON request body>",
 "approved_by": "<user uuid who approved>", "requested_by": "<user uuid who owns the conversation>",
 "iat": <int>, "exp": <iat + 60>}
```

**Why method and path are signed:** the body alone does not identify the target. `PUT /api/kb/{slug}` carries the slug in the path, and two tools can produce identical bodies.

**Canonical JSON:** UTF-8, sorted keys, no insignificant whitespace (`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`).

**academia verifies these, in order:**
1. Signature.
2. `aud`.
3. `exp`.
4. `org` equals the token's org.
5. `sub` equals the token's principal agent.
6. `body_sha256` equals the canonical hash of the received body.
7. `method` and `path` equal the received request exactly, and `tool` maps to that route in the §C table. A mismatch is 403 `assertion_invalid`.
8. `approved_by` holds the `WRITE` role set in this org (B.0), checked at verification time, not at approval time. A mismatch is 403 `approver_not_allowed`.

Then, in one transaction, it inserts `approval_consumptions(jti)` (duplicate → 409 `assertion_used`) and writes the revision(s) with `approval_id = jti`, `user_id = approved_by`, `agent_id = sub`.

**The assertion is minted ONLY by the agents control plane, AFTER a human approved the specific tool call.** The Julia CLI process never sees the signing key or the product token.

---

## E · agents product (schema `agents`, prefix `/api`)

**Auth.** The same `make_get_auth_context` composition as B.0 (the scaffold's JWT-only `get_current_user_org` is replaced). Every route below is **user-only**: a `caller_kind == "product"` caller gets 403 `user_required`. Only humans chat with, approve for, or configure agents.

**Roles.** They come from the org role on `public.noctus_users`:
- `admin` / `owner`: persona writes, agent toggles, approve.
- Any org member: chat, and read their own conversations.

### E.1 Data model

Every table has `id uuid pk`, `org_id uuid not null`, `created_at`, `updated_at`, RLS via `public.current_org_id()` (scaffold idiom `001_agents.sql:87-89`), and `updated_at_trigger` (seed `sql/triggers.py:62`).

| Table | Columns | Rules |
|---|---|---|
| `agents` | `key` text (unique per org: `julia`, `one-chat`) · `nome` · `runtime` CHECK in (`claude_sdk`, `external`) · `owner_product` text null (`social-wiring` for `one-chat`) · `external_ref` jsonb null (`{"connection_id": "<uuid>"}` for one-chat) · `ativo` bool default false | Seeded by migration: `julia` (`claude_sdk`) and `one-chat` (`external`). The admin sets `one-chat`'s `external_ref.connection_id` in the UI; it is never hardcoded. |
| `agent_personas` | `agent_id` fk · `versao` int · `nome` · `papel` · `tom` null · `system_prompt_append` null · `model` CHECK in (`claude-opus-5`, `claude-sonnet-5`) · `effort` CHECK in (`low`, `medium`, `high`, `xhigh`, `max`) · `idioma` default `pt-BR` · `org_display_name` null · `project_display_name` null · `ativa` bool · `created_by` uuid | Partial unique `(agent_id) WHERE ativa`. Append-only by versao: an edit inserts a new version and flips `ativa` in one transaction. |
| `conversations` | `agent_id` fk · `owner_user_id` uuid · `titulo` · `sdk_session_id` null · `status` CHECK in (`ativa`, `arquivada`) · `last_message_at` null | |
| `messages` | `conversation_id` fk · `role` CHECK in (`user`, `assistant`, `system`) · `texto` · `blocks` jsonb default `[]` (tool cards) · `token_usage` jsonb null | |
| `approvals` | `conversation_id` fk · `tool_name` · `tool_input` jsonb · `classe` CHECK in (`escrita`) · `resumo` · `diff` jsonb null (`{"antes": str\|null, "depois": str}` for KB/content writes) · `decision` CHECK in (`pendente`, `aprovada`, `negada`, `expirada`) · `decided_by` uuid null · `decided_at` null · `requested_by` uuid · `instance_id` text · `consumed_at` null | |

**Dropped from the sibling:** `whatsapp_connections`, `whatsapp_allowlist`, `app_settings`, `credentials`, `conversations.owner_msisdn`, `messages.channel`/`waha_message_id`/`ack_status`. There is no WhatsApp for Julia (roadmap T1).

### E.2 HTTP API

| Method + path | Request | Response | Rules |
|---|---|---|---|
| `GET /api/agents` | — | `{items: Agent[], total}` | `Agent = {key, nome, runtime, owner_product, ativo, estado_externo: {auto_reply_enabled: bool}\|null}`. `estado_externo` for `one-chat` is fetched live from social-wiring (E.6); `null` plus `aviso` if unreachable. |
| `POST /api/agents/{key}/toggle` | `{ativo: bool}` | `Agent` | admin. `julia`: sets `agents.ativo`; while false, E.2 message POSTs return 409 `agent_off`. `one-chat`: calls E.6, and the response reflects social-wiring's returned state. 502 `upstream_failed` if social-wiring errors. |
| `GET /api/agents/julia/persona` | — | `Persona` (the active version) | |
| `PUT /api/agents/julia/persona` | `{nome, papel, tom?, system_prompt_append?, model, effort, idioma?, org_display_name?, project_display_name?}` | `Persona` | admin. Inserts a new version. 422 if `model` is outside the allowlist. |
| `GET /api/conversations` | — | `{items: Conversation[], total}` | Own conversations only. |
| `POST /api/conversations` | `{titulo?}` | `201 Conversation` | For agent `julia`. |
| `GET /api/conversations/{id}` | — | `Conversation` | 404 if not the owner. |
| `GET /api/conversations/{id}/messages?before=&limite=50` | — | `{items: Message[], total}` | Newest last. 404 unless the caller owns the conversation; admins may read. |
| `POST /api/conversations/{id}/messages` | `{texto}` (1..8000) | `202 {mensagem: Message, status: "processando"}` | 404 unless the caller OWNS the conversation; admins may read but never post. Persists the user message, publishes `message.new`, starts the turn in the background. 409 `turn_in_progress` if a turn is already running for this conversation (one in-flight turn per conversation, DB lock). 409 `agent_off`. 429 on the per-user rate limit. |
| `GET /api/approvals?estado=pendente` | — | `{items: Approval[], total}` | Approvals in the caller's own conversations; admins see all in the org. |
| `POST /api/approvals/{id}/decision` | `{aprovada: bool}` | `Approval` | Requester or admin. |

**Approval decision errors:**

| Status | Meaning |
|---|---|
| 404 | Unknown id, or another org |
| 409 `already_decided` | The approval was already settled |
| 409 `orphaned` | No live turn is waiting (the process restarted) |
| 403 `not_allowed` | The caller may not decide this approval |

**Side-effect of approving:** the waiting tool call proceeds, the control plane mints the §D assertion and calls academia. The approval row is then `aprovada`, and after academia returns 2xx, `consumed_at` is set.

**Admin decisions:** an admin may decide another member's approval. First decision wins, and a later one gets 409 `already_decided`. The assertion carries `approved_by`, so academia re-checks the approver's role (§D step 8). Admins can read every conversation in the org; this data-access fact is recorded in the LGPD flag for `agents`.

**Timeout:** `APPROVAL_TIMEOUT_SECONDS` (default 900). An unanswered request becomes `expirada` and the tool call is denied.

**Startup:** every `pendente` row whose `instance_id` equals this instance becomes `expirada`, never other instances' rows (security finding 5).

### E.3 SSE

- **Router:** `create_sse_router(get_realtime_bus(...), scope_resolver=…, auth_dependency=get_auth_context, path="/api/conversations/{conversation_id}/stream")` (seed `sse.py:144`).
- **Scope:** `agents:julia:conv:<conversation_id>`. The `scope_resolver` returns 404 unless `ctx.user_id` owns the conversation (or the caller is admin).
- **Frontend:** `useRealtimeStream(url, {getAuthToken, events: [...E3_EVENTS]})` (`realtime.ts:117`). The `events` list MUST name all of the events below, or they are dropped.

| Event | Payload |
|---|---|
| `message.new` | `Message` |
| `message.delta` | `{message_temp_id, texto_parcial}` (from `include_partial_messages=True`) |
| `tool.started` | `{tool_use_id, tool_name, classe: "leitura"\|"escrita", resumo}` |
| `tool.finished` | `{tool_use_id, tool_name, resultado: "ok"\|"erro"\|"negada"}` |
| `approval.requested` | `Approval` |
| `approval.resolved` | `{approval_id, decision, decided_by}` |
| `session.status` | `{status: "pensando"\|"ociosa"\|"erro"}` |
| `conversation.upsert` | `Conversation` |

`message.ack` and `chat.upsert` are deprecated (WhatsApp-only, and renamed respectively).

### E.4 The gate: tool classes (Julia's allowlist is exhaustive)

| Class | Tools | Decision |
|---|---|---|
| **leitura** | `mcp__academia__kb_buscar`, `kb_ler`, `decisao_listar`, `pergunta_listar`, `historico_timeline`, `roadmap_ler`, `tarefa_listar`, `tarefa_preparar_sessao`, `conteudo_listar`, `conteudo_ler` · `WebSearch` · `Skill` (explicit list) | allow |
| **escrita** | `mcp__academia__kb_escrever`, `kb_mover`, `decisao_registrar`, `decisao_substituir`, `pergunta_adicionar`, `pergunta_responder`, `historico_append`, `roadmap_atualizar`, `tarefa_criar`, `tarefa_atualizar`, `conteudo_salvar`, `pesquisa_capturar_fonte` | ask |
| **anything else** | Including Bash, Write, Edit, Read, Grep, Glob, Task, WebFetch, NotebookEdit, other MCP servers | deny. Also listed in `disallowed_tools`, so the CLI never offers them. |

- **Exact matching:** names are matched by exact string equality, never `endswith` (architect debt).
- **The approval card** shows `resumo` plus `diff`. For `kb_escrever`, the control plane first `GET`s the current entry, and the diff compares it with the proposed `corpo_md`.

### E.5 Julia launch (SEC-A) and the tool proxy

`ClaudeAgentOptions` (SDK 0.2.152, `types.py:1941`):
**Why a wrapper is mandatory.** The SDK builds the CLI's environment as `{**os.environ (minus CLAUDECODE), "CLAUDE_CODE_ENTRYPOINT": ..., **options.env, "CLAUDE_AGENT_SDK_VERSION": ...}` (`_internal/transport/subprocess_cli.py:809-815`, verified 2026-09-14). `options.env` can ADD keys but never REMOVE inherited ones, so without the wrapper every control-plane secret would reach the CLI: `ACADEMIA_API_TOKEN`, `SOCIAL_WIRING_API_TOKEN`, `APPROVAL_ASSERTION_SECRETS`, the database key. The wrapper at `/app/bin/julia-cli-exec` runs `exec env -i HOME=<tmpfs> PATH=<minimal> ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" CLAUDE_CODE_ENTRYPOINT="$CLAUDE_CODE_ENTRYPOINT" CLAUDE_AGENT_SDK_VERSION="$CLAUDE_AGENT_SDK_VERSION" <claude binary> "$@"`, re-exporting only the allowlisted keys from its own (inherited) environment.

**Why `tools=` is the primary restriction.** Tools that need no permission, such as the read-only built-ins and MCP resource reads, never reach `can_use_tool`. A hand-kept `disallowed_tools` list goes stale as the CLI adds tools. So the base tool set is pinned with `tools=` (SDK `types.py:1944`, the `--tools` flag), and `disallowed_tools` remains only as defence in depth.

**`allowed_tools` must never contain an escrita tool** (contract defect corrected 2026-09-14, found by G2 against the installed SDK). In SDK 0.2.152 a bare `allowed_tools` entry is a whole-tool auto-approval that is granted BEFORE `can_use_tool` runs (`claude_agent_sdk/types.py` `_whole_tool_allowed` / `_get_can_use_tool_shadowed_warning`). Listing escrita names there would silently skip the gate, the broker and the approval assertion for every write. Only LEITURA names go in `allowed_tools`; escrita names reach the CLI solely through the in-process MCP server, and every call falls through to `can_use_tool`. The regression is pinned by `tests/runtime/test_claude_runtime.py::TestAllowedToolsNeverShadowsTheGate`.

**Plugin invariant, enforced by a build-time test:** `agents/julia/plugin/` contains ONLY `skills/` (no `hooks/`, `.mcp.json`, `agents/` or `commands/`). No `SKILL.md` frontmatter declares `allowed-tools`.

```
cli_path="/app/bin/julia-cli-exec"     # env -i wrapper, see above (SDK types.py:2064)
tools=["WebSearch", "Skill"]           # base built-in set; the academia proxies arrive via mcp_servers
setting_sources=[]                     # no project CLAUDE.md / settings / hooks
system_prompt={"type":"preset","preset":"claude_code","append": JULIA.md + persona}
plugins=[{"type":"local","path": "<image>/app/agents/julia/plugin"}]
skills=[<explicit ar-* list>]
mcp_servers={"academia": create_sdk_mcp_server("academia", tools=[...E.4 proxies])}
strict_mcp_config=True
allowed_tools=[E.4 LEITURA names + "WebSearch" + "Skill" ONLY]   # NEVER escrita names — see note below
disallowed_tools=["Bash","Write","Edit","MultiEdit","NotebookEdit","Read","Grep","Glob","Task","WebFetch"]
can_use_tool=<gate>                    # PermissionResultAllow / PermissionResultDeny (types.py:238,247)
env={}                                # adds nothing; the wrapper is what strips inherited keys
user="julia-cli"
include_partial_messages=True
max_turns=<config, default 40>
resume=<conversations.sdk_session_id>
```

**How tools reach academia.** Tools are in-process SDK MCP tools (`@tool`, `__init__.py:251`) executed by the control plane, not by the CLI. Each proxy:
1. Validates its input against the sibling-extracted schema (§C).
2. For an `escrita` call, has already passed the gate, so it holds the approval id.
3. Calls academia with `ACADEMIA_API_TOKEN` plus `X-Approval-Assertion`.
4. Returns `{"content":[{"type":"text","text": <json of the §C output>}]}`.

**SEC-C proves both invariants on the real image.**
- It reads `/proc/<julia-cli pid>/environ` and asserts the key set is exactly `{HOME, PATH, ANTHROPIC_API_KEY, CLAUDE_CODE_ENTRYPOINT, CLAUDE_AGENT_SDK_VERSION}`.
- It asserts that the CLI's `init` message lists exactly the E.4 tools, and nothing else.

`ANTHROPIC_API_KEY` is a dedicated, spend-capped key for Julia's workspace, never shared with any other product.

### E.6 social-wiring One Chat toggle (slice SW1 — a new route, the existing route unchanged)

| Method + path | Auth | Request | Response |
|---|---|---|---|
| `GET /api/agents-bridge/one-chat/{connection_id}` | `get_auth_context` + `require_scopes("social-wiring:one-chat:read")` | — | `{connection_id, label, auto_reply_enabled}` |
| `PUT /api/agents-bridge/one-chat/{connection_id}/auto-reply` | `require_scopes("social-wiring:one-chat:toggle")` | `{enabled: bool}` (same as `AutoReplyToggleRequest`, `schemas/whatsapp_connection.py:351`) | `{connection_id, auto_reply_enabled}` (same as `AutoReplyToggleOut`) |

- **What it calls:** `WhatsAppConnectionStore.update_auto_reply` (the same store call as the existing route at `whatsapp_connections_router.py:1150`).
- **Audit:** an audit row is written.
- **Errors:** 404 for an unknown connection or another org, 403 `scope_missing`, 401 for a bad or expired token.
- **Product-only:** `caller_kind != "product"` gets 403 `product_required` (a user session must not pass through this bridge). The token's `issuer` must be `agents`.
- **Nothing else in social-wiring changes:** no prompt, tool, sender-policy or webhook change.
- **Token:** the agents product holds `SOCIAL_WIRING_API_TOKEN` (deploy secret) with only these two scopes.

### E.7 ChatWindow seams (slice SEED-2 — additive, optional; existing consumers unchanged)

Additions to `seed/lib/frontend/src/design-system/chat/ChatWindow.tsx`:
- `ChatMessage` gains optional `pending?: boolean` (streaming placeholder) and `blocks?: ChatBlock[]`.
- `ChatBlock` = `{kind: "tool", toolUseId, name, status: "running"|"ok"|"erro"|"negada", resumo?}` | `{kind: "approval", approvalId, resumo, diff?: {antes: string|null, depois: string}, decision: "pendente"|"aprovada"|"negada"|"expirada"}`.
- `ChatWindowAdapter` gains optional `useApprovalAction?(scopeId) => {decide(approvalId: string, aprovada: boolean): Promise<void>; isPending: boolean}`.
- When `blocks` is absent the rendering is byte-identical to today. With `blocks`, `MessageBubble` renders tool chips and an approval card (Aprovar / Negar buttons only when `decision === "pendente"` and `useApprovalAction` exists).
- **Organ bookkeeping:** `ChatWindow.organ.yaml` is updated, and the exports are added to `index.ts`.

### E.8 Prompt and skills port rule (W0 audit, 2026-09-14)

The audit of the sibling router, topics, 10 `ar-*` skills and 2 agents found no phone numbers or emails. A company name appears 8 times and a person's name 14 times, including the hardcoded approver.

**The port rule:**
- `JULIA.md` and the skills contain NO person or company names.
- The approver is "a pessoa que aprova", resolved from SSO at runtime.
- Company and project display names come from `agent_personas.org_display_name` / `project_display_name`, and are appended at runtime.
- Sibling rules that no longer apply are dropped: the read-only `../noctusai`, the vendored `_kit`, the files-as-truth rule, the git-status reads, and WhatsApp.
- `.github/CODEOWNERS` lists `products/agents/backend/app/agents/**`. **This is advisory only.** As of 2026-09-14 `dev` has no branch protection, so CODEOWNERS only requests review on pull requests; direct pushes bypass it. Making Julia's prompt and skills enforce-reviewed needs branch protection with required code-owner review. That is a repository-settings decision for the user (roadmap open question Q4) and is NOT assumed here.

### E.9 The runtime seam between the agents routes (G1b) and the runtime + gate (G2)

The routes call the runtime and the broker. G2 implements them. Neither side guesses. Everything below lives in `products/agents/backend/app/runtime/`.

```python
# types.py
@dataclass(frozen=True)
class TurnContext:
    org_id: UUID
    conversation_id: UUID
    requested_by: UUID                 # the conversation owner (E.2)
    instance_id: str                   # this process; stored on approvals + turn lock
    sdk_session_id: str | None         # conversations.sdk_session_id, for resume

@dataclass(frozen=True)
class AgentSpec:
    key: Literal["julia"]
    model: str                         # from the active persona, already allowlist-checked
    effort: Literal["low", "medium", "high", "xhigh", "max"]
    prompt_append: str                 # JULIA.md + persona fields, composed by build_julia_spec()
    skills: tuple[str, ...]            # explicit ar-* list (E.5)
    tools: tuple[str, ...]             # exactly the E.4 leitura + escrita names
    max_turns: int                     # default 40

AgentEvent = TypedDict("AgentEvent", {"event": str, "payload": dict})
# `event` is exactly one of the E.3 names. `payload` has exactly the E.3 shape.

@dataclass(frozen=True)
class ApprovalDecision:
    aprovada: bool
    approval_id: UUID
    approved_by: UUID | None           # None when not decided by a human
    via: Literal["web", "timeout", "restart"]

class ApprovalBroker(Protocol):
    # runtime side, called by G2's can_use_tool for every `escrita` tool
    async def request(self, ctx: TurnContext, *, tool_name: str, tool_input: dict,
                      resumo: str, diff: dict | None) -> ApprovalDecision
    # route side, called by G1b's POST /api/approvals/{id}/decision
    async def resolve(self, org_id: UUID, approval_id: UUID, *, aprovada: bool,
                      decided_by: UUID) -> dict        # the updated approvals row
    # raises stores.errors.AlreadyDecided → 409 already_decided
    # raises runtime.errors.Orphaned      → 409 orphaned
    # raises stores.errors.NotFound       → 404
    async def expire_orphans_on_startup(self) -> int   # only rows with this instance_id

class AgentRuntime(Protocol):
    def run_turn(self, spec: AgentSpec, ctx: TurnContext, prompt: str,
                 broker: ApprovalBroker) -> AsyncIterator[AgentEvent]
```

**Factories** (`runtime/__init__.py`):
- `get_agent_runtime(settings) -> AgentRuntime`. Returns `ClaudeAgentSdkRuntime` when `ANTHROPIC_API_KEY` is configured, and `FakeAgentRuntime` in tests and dev. In prod, an unconfigured key raises at startup. There is no silent Fake in prod.
- `get_approval_broker(settings) -> ApprovalBroker`, a process singleton. Its Fake variant resolves in-process with no timeout drift.
- `build_julia_spec(persona_row) -> AgentSpec`.

**What the routes must do with a turn (G1b owns this, and it is the only consumer):**
1. `POST /api/conversations/{id}/messages` persists the user message, then `try_acquire_turn`. On failure it returns 409 `turn_in_progress`.
2. It starts a background task (reference kept alive on `app.state`) that iterates `run_turn(...)`.
3. For each event, the task persists it where E.3 implies:
   - `message.new` → a `messages` row
   - `tool.*` → appended into the current assistant message's `blocks`
   - `approval.*` → an `approval` block

   Then it publishes the event on scope `agents:julia:conv:<id>`.
4. `message.delta` is published only, never persisted.
5. When the iterator finishes, the task persists the `sdk_session_id` carried by the final `session.status` payload (`{"status": "ociosa", "sdk_session_id": "..."}`) and calls `release_turn`.
6. If the iterator raises, the task persists a `system` message ("O turno falhou." — generic, no exception text, per security finding 8), publishes `session.status` with `{"status": "erro"}`, and calls `release_turn`.

**What the runtime must guarantee (G2):**
- **Tool events are paired.** Every `tool.started` has exactly one `tool.finished` with the same `tool_use_id`.
- **Escrita tools follow a fixed sequence:** `approval.requested` → `approval.resolved`, then a `tool.finished` whose `resultado` is `"negada"` when not approved.
- **The last event is always `session.status`**, whether the turn succeeds or fails.
- **The runtime never writes to the database.** It only yields events and calls the broker. The broker owns `approvals` rows via `stores.approvals`.

**`FakeAgentRuntime`** is scriptable: `FakeAgentRuntime(script: list[AgentEvent | ("escrita", tool_name, tool_input)])`. A tuple entry calls `broker.request(...)` and emits the approval and tool events exactly as the real runtime would. G1b's route tests use it, so they exercise the real broker without an LLM.

## F · Reserved migration numbers

| Product | Numbers | Owner |
|---|---|---|
| academia-de-reciclagem | `006_knowledge.sql` (A.1–A.9), `007_revisions.sql` (A.10 + triggers), `008_api_tokens.sql` (B.0 token table + audit) | A1 |
| agents | `006_agents.sql` (E.1), `007_api_tokens.sql` (B.0 token table + audit) | G1 |
| social-wiring | `105_api_tokens_scopes_and_audit.sql`: `api_tokens` gains `expires_at` / `principal_agent_id` / `issuer` / `human_personal` / `minted_by` plus backfill, and `api_token_audit` is created | SEED-1 (moved from SW1 at dispatch: the resolver change needs the columns in the same slice). SW1 now only adds the bridge route. |
| erp-imobiliario | `046_api_tokens_scopes_and_audit.sql`, same shape as social-wiring | SEED-1 |
| academia-de-reciclagem | `009_status_pagina_pages.sql`: `status_pagina` rows for the A3 UI routes (status `desenvolvimento`) | A3 |
| agents | `008_status_pagina_pages.sql`: `status_pagina` rows for the G4 UI routes (status `desenvolvimento`) | G4 |

**Deploy order is mandatory for 105 and 046.** Apply both migrations to the database BEFORE any social-wiring or erp-imobiliario image containing the SEED-1 resolver is deployed. The resolver selects `expires_at`, so the reverse order breaks every live product token.

**Not built by SEED-1, with named destinations:**
- **Audit-writer call-site wiring.** The writer (Protocol + Fake + Real + factory) needs the response status, which only an ASGI middleware sees. It is wired by the first routes that accept product tokens: wave 1b academia API and the SW1 bridge.
- **30-day token-expiry alert.** This belongs to a monitoring/cron concern, slice D1.
- **erp-imobiliario token routes have zero tests.** This predates SEED-1, but those routes now require `expires_at`, so the minimum 401/422/201 tests land in wave 1b alongside SW1.

No frontend in any product calls the token-mint route (checked 2026-09-14), so requiring `expires_at` breaks no UI. Direct API callers must now send it.
| core | none | — |

## G · E2E-shape checks (closing gate, one per contract edge)

1. **academia:** `curl` `POST /api/kb` as an SSO user, then `GET /api/kb/{slug}/revisions` → `rev_no == 1`, `author_kind == "human"`.
2. **agents → academia:** approve a Julia `kb_escrever` in the browser. The academia revision has `approval_id` == the approval id. Replaying the same assertion → 409 `assertion_used`.
3. **agents → social-wiring:** toggle One Chat in the Agents UI → `social_wiring.whatsapp_connections.auto_reply_enabled` flips, plus an audit row. A token without scope → 403.
4. **SSE:** the Agents UI receives `tool.started`, then `approval.requested`, then `approval.resolved`, then `message.new` for one write turn, in that order, rendered through the E.7 seams.
