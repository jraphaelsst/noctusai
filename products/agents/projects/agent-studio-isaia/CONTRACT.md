# Agent Studio — CONTRACT (v1, 2026-09-21)

> The single shape every slice builds to. Backend builds *to* it, frontend consumes *to* it,
> the content bundle conforms *to* it. A slice that needs to deviate STOPS and reports —
> it never "aligns at integration". Project plan: `PROJECT.md` (same folder).

**What this is.** The `agents` product today runs one hand-wired agent (Julia): prompt and
skills are files baked into the image, only a few persona fields are editable. Agent Studio
makes an agent a **versioned, UI-managed definition**: prompt sections, skills (+ attached
reference files), model/limits/tool policy, a knowledge library, eval cases, and client
brains — all editable in pages, published as immutable versions behind an eval gate, and
compiled by ONE function into the **master prompt** the runtime uses and the inspector shows.
The first studio agent is **IsaIA** (Instagram content strategist). Julia is untouched
(`definition_mode='legacy'`).

---

## §A · Decisions (binding)

| # | Decision | Why |
|---|---|---|
| A1 | Agent definitions live in the DB (schema `agents`), never in git. Content (prompt text, skills, knowledge, evals) arrives via the UI or the import endpoint (§F). | UI-manageable by construction; the repo is public and the knowledge corpus is third-party material. |
| A2 | Julia keeps her current path byte-for-byte (`definition_mode='legacy'`, `build_julia_spec`, baked plugin). Studio agents use `definition_mode='studio'`. | Julia is live; no regression surface. |
| A3 | A version is **immutable once published**. Exactly one `rascunho` (draft) and at most one `ativa` per agent. "Restore" = clone an old version into a new draft. | Auditability; the conversation↔version link means something. |
| A4 | ONE compiler (`app/studio/compiler.py::compile_prompt`) produces the master prompt. The runtime, the inspector and the publish step all call it. The UI never re-implements composition. | What you see is what runs. |
| A5 | Studio agents run with a **fully custom system prompt**: no `claude_code` preset, no plugin dir, no SDK `Skill` tool. The compiled text is delivered through the existing per-slot `append.md` handoff (agent-agnostic, already security-reviewed). | The coding preset would sit invisibly above our prompt; the inspector must be complete. No change to `julia-cli-slot` / §E.11. |
| A6 | Progressive disclosure is served by **read-only in-process MCP tools** (`mcp__studio__*`, §E.3) reading the DB — not by filesystem `Read`. | Keeps `Read/Grep/Glob/Bash` disallowed (Julia's hardened posture) while skills and knowledge still load just-in-time. |
| A7 | Every turn records `version_id` + `compiled_hash`; the exact compiled text is stored once per hash in `compiled_prompts`. | "Proof of use": open the exact prompt any turn ran with. |
| A8 | Publishing requires a concluded eval run on the draft's **current** compiled hash with `score >= agents.publicacao_limiar` — or an admin override with a written reason (recorded). | The eval gate is the substitute for code review now that prompt/skills are data. |
| A9 | Knowledge search v1 = Postgres full-text (`portuguese` config, weighted title/resumo/body; no trigram index — pg_trgm lives in another product's schema on this project). Embeddings are a later hybrid leg (§K). | Deterministic, zero cost, no new provider dependency; the corpus is navigated mostly by structure (cards/registry/indices). |
| A10 | Model allowlist: `claude-opus-5` / `claude-sonnet-5` (same CHECK as personas), widened by `015_haiku_model.sql` to add `claude-haiku-4-5` (cheapest/fastest option — already proven by `eval_runs.modelo_geracao`'s narrower allowlist, §L). Eval judge = `claude-sonnet-5` via `noctusai_lib` LLM layer, generator = the version's model. | Reuse the existing allowlist; judge ≠ generator where possible. |

---

## §B · Database — two migrations (numbers are reserved; do not renumber)

Conventions (identical to `006_agents.sql`): every table has `id uuid pk default gen_random_uuid()`,
`org_id uuid not null`, `created_at`/`updated_at timestamptz default now()`, RLS enabled with
`"<table>_select_own_org"` (`org_id = current_org_id()`, `TO authenticated`) + the literal
`"service_role_bypass"` policy, `idx_agents_<table>_org`, and the `agents.set_updated_at()`
trigger. Every SECURITY DEFINER function is followed by the `REVOKE ALL ... FROM PUBLIC, anon,
authenticated` + `GRANT EXECUTE ... TO service_role` pair. Routes use the admin client (RLS =
defence in depth). The anon-grant lockdown of `011_anon_grant_lockdown.sql` must hold for the
new tables (mirror whatever 011 does for tables created after it).

**Hardening (wave-1 security review, slice BE-HARDEN — applied in place, 012/013 were never deployed):**
- **Grants (M5):** every studio table restates `REVOKE ALL ... FROM anon` and
  `REVOKE INSERT, UPDATE, DELETE, TRUNCATE ... FROM authenticated` (mirrors 009/010); `authenticated` keeps SELECT only.
- **Size caps (M3)** — enforced by the HTTP schemas, the stores (Fake AND Real) and a DB `CHECK`
  (single source: `app.studio.models.LIMITS`): collection `nome` ≤ 120 / `tag` ≤ 12 / `descricao` ≤ 600;
  client `resumo` ≤ 8 000; entry `titulo` ≤ 200 / `conteudo` ≤ 4 000; ≤ 200 `ativo` entries per client
  (trigger `guard_client_entry_cap` → 409 `client_entries_cap`); section `conteudo` ≤ 40 000; skill `corpo`
  ≤ 60 000; skill file `conteudo` ≤ 120 000; knowledge document `conteudo` ≤ 2 000 000.
  **Collection metadata (nome/tag/descricao + doc counts) and the client brain (resumo + active entries) are
  LIVE prompt inputs**: they are compiled into every turn, are not frozen by a published version and never
  pass the eval gate — which is why they carry the tightest caps.
- **Every studio write** goes through `app/stores/_db_errors.py`: the functions/triggers raise the machine
  code as the message; `23505` → 409 with the route's code, `23503` → 409 (`draft_referenced` / `case_in_use`),
  `23514` → 422 `invalid_field`.

### B1 · `012_agent_studio_definitions.sql` (slice BE-DEF)

```sql
ALTER TABLE agents.agents
  ADD COLUMN definition_mode TEXT NOT NULL DEFAULT 'legacy'
      CHECK (definition_mode IN ('legacy','studio')),
  ADD COLUMN descricao TEXT NULL,
  ADD COLUMN publicacao_limiar NUMERIC(4,3) NOT NULL DEFAULT 0.800
      CHECK (publicacao_limiar >= 0 AND publicacao_limiar <= 1);

agents.agent_versions (
  agent_id uuid not null references agents.agents(id),
  versao int not null,                       -- 1..n per agent, assigned by functions
  status text not null check (status in ('rascunho','ativa','substituida')),
  notas text null,                           -- changelog note for this version
  model text not null check (model in ('claude-opus-5','claude-sonnet-5')),  -- widened to add 'claude-haiku-4-5' by 015_haiku_model.sql (§A10); this literal block stays as 012 shipped it
  effort text not null check (effort in ('low','medium','high','xhigh','max')),
  max_turns int not null default 40 check (max_turns between 1 and 200),
  idioma text not null default 'pt-BR',
  tool_policy jsonb not null default '{"web_search": true, "knowledge": true}',
  based_on_version_id uuid null references agents.agent_versions(id),
  created_by uuid not null,
  published_by uuid null, published_at timestamptz null,
  compiled_hash text null,                   -- hash of the compile WITHOUT client, refreshed on every draft save
  eval_run_id uuid null,                     -- the run that satisfied the gate (FK added in 013)
  publish_override_reason text null,
  unique (agent_id, versao)
);
-- partial unique: one ativa per agent; one rascunho per agent.

agents.agent_prompt_sections (
  version_id uuid not null references agents.agent_versions(id) on delete cascade,
  chave text not null check (chave ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  titulo text not null,
  ordem int not null,
  conteudo text not null default '',
  ativo boolean not null default true,
  unique (version_id, chave)
);

agents.agent_skills (
  version_id uuid not null references agents.agent_versions(id) on delete cascade,
  nome text not null check (nome ~ '^[a-z0-9]+(-[a-z0-9]+)*$' and length(nome) <= 64),
  descricao text not null check (length(descricao) between 1 and 1024),
  corpo text not null default '',
  ordem int not null default 0,
  ativo boolean not null default true,
  unique (version_id, nome)
);

agents.agent_skill_files (
  skill_id uuid not null references agents.agent_skills(id) on delete cascade,
  caminho text not null check (caminho ~ '^[a-z0-9][a-z0-9._/-]*$' and caminho !~ '\.\.'),
  titulo text null,
  conteudo text not null default '',
  unique (skill_id, caminho)
);

agents.agent_clients (                      -- "client brain": per-client durable context
  agent_id uuid not null references agents.agents(id),
  slug text not null check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  nome text not null,
  resumo text not null default '',          -- markdown: brand, audience, positioning, offer
  ativo boolean not null default true,
  unique (agent_id, slug)
);

agents.agent_client_entries (
  client_id uuid not null references agents.agent_clients(id) on delete cascade,
  tipo text not null check (tipo in ('marca','publico','posicionamento','trava','decisao','aprendizado','evidencia','nota')),
  titulo text not null,
  conteudo text not null default '',
  status text not null default 'ativo' check (status in ('ativo','arquivado'))
);

agents.compiled_prompts (                   -- exact text per hash, write-once
  hash text not null,                        -- 'sha256:<hex>'
  version_id uuid not null references agents.agent_versions(id),
  client_id uuid null references agents.agent_clients(id),
  texto text not null,
  manifest jsonb not null,
  unique (org_id, hash)
);

ALTER TABLE agents.conversations
  ADD COLUMN version_id uuid null references agents.agent_versions(id),
  ADD COLUMN client_id uuid null references agents.agent_clients(id);
ALTER TABLE agents.messages
  ADD COLUMN version_id uuid null references agents.agent_versions(id),
  ADD COLUMN compiled_hash text null;
```

**Immutability triggers** (BEFORE UPDATE/DELETE): on `agent_versions`, when `OLD.status <> 'rascunho'`
only the transition `ativa → substituida` is permitted (all content columns frozen); on the three
child tables, any INSERT/UPDATE/DELETE whose parent version is not `rascunho` raises
`version_immutable`. `compiled_prompts` rows are never updated NOR deleted (trigger raises) — the ONE
deletion path is `agents.erase_compiled_prompts(p_org_id, p_client_id) returns int` (service_role only,
LGPD erasure of one client's prompts).

**Publish race (M1):** every content write under a draft (child INSERT/UPDATE/DELETE, or a change of
`model/effort/max_turns/idioma/tool_policy`) sets the draft's `compiled_hash` to NULL (the child guards
row-lock the parent first). The API re-stamps it after its own writes with a compare-and-set on
`updated_at`; `GET .../compiled` never writes (L7).

**Threshold + audit (H2):** `agents.publicacao_limiar` has a CHECK floor `>= 0.5`
(`agents_publicacao_limiar_floor`); `agent_versions` gains `limiar_aplicado`/`eval_score` numeric(4,3) null
(snapshotted by publish) and the CHECK `agent_versions_override_reason_len` (≥ 20 chars once trimmed).
`agents.agent_audit_log (org_id, agent_id, actor, acao, antes jsonb, depois jsonb)` is append-only
(trigger); `acao ∈ limiar_alterado | publicado | publicado_override | rascunho_descartado`. Threshold
changes are logged by a trigger (actor via `agents.set_agent_publicacao_limiar(p_org_id, p_agent_id,
p_limiar, p_actor)`); publish/discard write their row inside their function.

**Functions** (SECURITY DEFINER, locked search_path, EXECUTE → service_role only):
- `agents.create_agent_draft(p_org_id, p_agent_id, p_source_version_id uuid null, p_created_by) returns uuid`
  — raises `draft_exists` if a rascunho exists. `p_source_version_id` null ⇒ empty draft with defaults
  (`claude-opus-5`, `high`, 40); non-null ⇒ deep-copies settings + sections + skills + skill files,
  sets `based_on_version_id`. New `versao = max+1`.
- `agents.publish_agent_version(p_org_id, p_version_id, p_published_by, p_eval_run_id uuid null, p_override_reason text null, p_expected_hash text, p_texto text, p_manifest jsonb) returns void`
  — one transaction: assert rascunho; `draft_changed` unless `p_expected_hash` = the row's `compiled_hash`;
  re-checks the gate (run of this version, `concluida`, `completa`, `total ≥ 1`, stamped `p_expected_hash`,
  score ≥ the agent's current threshold, agent still has ≥ 1 active case — else `eval_required`; without a
  run the override reason needs ≥ 20 non-whitespace chars); stores the proof-of-use `compiled_prompts` row
  (idempotent by hash); flips ativa → substituida, this → ativa; snapshots `limiar_aplicado`/`eval_score`;
  appends the audit row. The Python gate still runs first (it builds the rich 409 body).
- `agents.discard_agent_draft(p_org_id, p_version_id, p_actor)` — deletes a rascunho (cascade, incl. its
  eval runs) + audit row; `draft_referenced` if a compiled prompt points at it.
- `agents.replace_draft_sections(p_org_id, p_version_id, p_secoes jsonb)` — `PUT .../draft/sections` in ONE
  transaction (ids of existing rows kept; chave unique deferred for swaps).
- `agents.replace_draft_bundle(p_org_id, p_version_id, p_secoes jsonb, p_skills jsonb)` — ATOMIC replacement of
  a draft's sections + skills + skill files (the importer's write; store method
  `replace_draft_bundle(org_id, version_id, secoes, skills)`, skills items `{nome, descricao, corpo, ordem,
  ativo, arquivos: [{caminho, titulo, conteudo}]}`).

### B2 · `013_agent_studio_knowledge_evals.sql` (slice BE-KE)

```sql
agents.knowledge_collections (
  agent_id uuid not null references agents.agents(id),
  slug text not null check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  nome text not null,
  tag text null,                             -- provenance tag shown to the model, e.g. 'AU','KE','CA','IG','SYN'
  descricao text not null default '',
  ordem int not null default 0,
  unique (agent_id, slug)
);

agents.knowledge_documents (
  collection_id uuid not null references agents.knowledge_collections(id) on delete cascade,
  agent_id uuid not null references agents.agents(id),
  slug text not null check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  titulo text not null,
  tipo text not null check (tipo in ('fonte','sintese','card','template','indice','outro')),
  proveniencia jsonb not null default '{}',  -- {autor, origem, referencia, pagina, licenca, notas}
  resumo text null,
  conteudo text not null,
  source_sha text not null,                  -- sha256 of conteudo (import idempotency)
  ativo boolean not null default true,
  busca tsvector generated always as (
    setweight(to_tsvector('portuguese', coalesce(titulo,'')), 'A') ||
    setweight(to_tsvector('portuguese', coalesce(resumo,'')), 'B') ||
    setweight(to_tsvector('portuguese', left(coalesce(conteudo,''), 900000)), 'C')
  ) stored,
  unique (agent_id, slug)
);
-- GIN(busca). (No trigram index — see A9.)

agents.knowledge_revisions (                -- append-only audit
  document_id uuid not null references agents.knowledge_documents(id) on delete cascade,
  op text not null check (op in ('create','update','archive','import')),
  snapshot jsonb not null,
  author_id uuid null, motivo text null
);

agents.eval_cases (
  agent_id uuid not null references agents.agents(id),
  slug text not null check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
  titulo text not null,
  entrada text not null,                     -- the user message sent to the agent
  contexto text null,                        -- optional prior context prepended as a system note to the case
  criterios jsonb not null,                  -- {"deve": [str,...], "nao_deve": [str,...]}  (>=1 total)
  rubrica text null,                         -- extra judge guidance
  tags text[] not null default '{}',
  ativo boolean not null default true,
  unique (agent_id, slug)
);

agents.eval_runs (
  agent_id uuid not null references agents.agents(id),
  version_id uuid not null references agents.agent_versions(id),
  compiled_hash text not null,               -- the draft hash the run judged
  status text not null check (status in ('pendente','executando','concluida','falhou','cancelada')),
  total int not null default 0, aprovados int not null default 0,
  score numeric(4,3) null, limiar numeric(4,3) not null,
  started_by uuid not null, started_at timestamptz null, finished_at timestamptz null,
  erro text null
);
-- one pendente|executando run per version (partial unique).

agents.eval_results (
  run_id uuid not null references agents.eval_runs(id) on delete cascade,
  case_id uuid not null references agents.eval_cases(id),
  status text not null check (status in ('pendente','aprovado','reprovado','erro')),
  saida text null, score numeric(4,3) null,
  veredito jsonb null,                       -- [{"criterio": str, "tipo": "deve"|"nao_deve", "ok": bool, "motivo": str}]
  notas_juiz text null, duracao_ms int null,
  unique (run_id, case_id)
);

ALTER TABLE agents.agent_versions
  ADD CONSTRAINT agent_versions_eval_run_fk FOREIGN KEY (eval_run_id) REFERENCES agents.eval_runs(id);
```

**Hardening (BE-HARDEN):** `eval_runs.completa boolean not null default false` — true only when the run
covered every active case (`case_ids` omitted); the publish gate requires it (H1). `eval_runs.version_id`
is `ON DELETE CASCADE` (L8). `agents.create_eval_run(...)` inserts the run + its pending results in ONE
transaction (L6; explicit ids deduped, ≤ 200). `agents.list_knowledge_documents(...)` runs the list filter
as a bound, LIKE-escaped parameter (`q` ≤ 200, L4). `agents.search_knowledge` caps `q` ≤ 512 and headlines
over `left(conteudo, 50000)` (L5).

Knowledge + evals are **agent-scoped, not version-scoped** (the corpus is large and evolves on its
own clock; the revision log is its history). The version snapshot freezes prompt, skills and
settings; the manifest records the knowledge catalog state (collection slugs + doc counts) at compile.

---

## §C · The compiler (slice BE-DEF owns `app/studio/compiler.py`)

```python
@dataclass(frozen=True)
class CompileInput:
    agent_nome: str
    version: VersionBundle          # settings + active sections (ordered) + active skills (ordered, with file list)
    knowledge: list[CollectionSummary]   # slug, nome, tag, descricao, doc_count (active docs)
    client: ClientBundle | None     # nome, resumo, active entries
    tool_policy: dict

@dataclass(frozen=True)
class CompiledPrompt:
    texto: str
    hash: str                       # "sha256:" + hexdigest(texto.encode("utf-8"))
    manifest: list[ManifestSection] # in output order
    tokens_estimados: int           # ceil(len(texto)/4)
    sob_demanda: list[OnDemandItem] # the just-in-time layer (never inside texto)

def compile_prompt(inp: CompileInput) -> CompiledPrompt: ...   # pure, deterministic, no IO
```

`ManifestSection = {chave, titulo, origem: {tipo: "secao"|"auto", id: uuid|None, campo: str|None}, inicio: int, fim: int, chars: int, tokens: int}`
(`inicio`/`fim` are offsets into `texto` counted in **Unicode code points** (Python `str` indices — NOT
UTF-16 code units; a JS consumer must index with `Array.from(texto)` / code-point iteration, not
`String.prototype.slice`) — the inspector uses them to highlight and link).
`OnDemandItem = {tipo: "skill"|"arquivo_skill"|"colecao", nome: str, caminho: str|None, chars: int, tokens: int, gatilho: str}`.

**Output layout** (exact; `\n\n` between blocks, trailing newline stripped):
1. For each active section by `ordem`: `# {titulo}\n\n{conteudo.strip()}` (empty `conteudo` ⇒ the section is skipped AND reported in compile warnings).
2. `# Skills` (auto, only if ≥1 active skill):
   ```
   Skills são procedimentos especializados. Quando o pedido corresponder à descrição de uma skill,
   chame `abrir_skill` com o nome dela ANTES de responder e siga as instruções que ela devolver.
   Arquivos de referência de uma skill são lidos com `ler_arquivo_skill`.

   - `{nome}` — {descricao}
   ```
3. `# Base de conhecimento` (auto, only if `tool_policy.knowledge` and ≥1 collection):
   ```
   Use `kb_buscar` para encontrar documentos e `kb_ler` para ler um documento pelo slug.
   Cite a origem com a tag da coleção (ex.: [AU]) quando usar um conteúdo.

   - `{slug}` [{tag}] — {nome}: {descricao} ({doc_count} documentos)
   ```
4. `# Ferramentas` (auto): one line per enabled tool family (web search on/off, knowledge on/off, skills).
5. `# Cliente em foco: {nome}` (auto, only when a client is set): `resumo`, then active entries grouped by `tipo`
   in the fixed order marca, publico, posicionamento, trava, decisao, aprendizado, evidencia, nota —
   `## {Tipo label}\n- **{titulo}** — {conteudo}`.

Compile **warnings** (returned by the compile endpoint, block publish when `bloqueante`):
empty active section (bloqueante), zero active sections (bloqueante), skill with empty `corpo`
(bloqueante), duplicate `chave`/`nome` (impossible by DB, still checked), `tokens_estimados > 12000`
(aviso), a section title that duplicates an auto title (aviso).

Hash stability: the compiler must not embed timestamps, UUIDs of drafts, or dict-order-dependent text.
Test: same input ⇒ identical `texto` + `hash`; any field change ⇒ different hash.

---

## §D · HTTP API (all JSON; errors are FLAT on the wire: `{"detail": str, "code": str, ...extra}` — e.g. `eval_required` adds `hash_atual` + `ultima_execucao` at the top level)

Auth: `require_member` for reads, `require_admin` for writes (existing deps). Every route resolves the
agent by `(ctx.org_id, key)` → 404 `agent_not_found`; a legacy agent on a studio route → 409 `not_studio_agent`.
Mutating a non-draft → 409 `version_immutable`. Unknown fields → 422 (`StrictHttpModel`).

### D1 · Agents & versions (BE-DEF)
| Method · Path | Body | 2xx response |
|---|---|---|
| `GET /api/studio/agents` | — | `{items: [AgentSummary]}` — `AgentSummary = {id, key, nome, descricao, definition_mode, ativo, publicacao_limiar, versao_ativa: int|null, tem_rascunho: bool}`; includes legacy agents (read-only badge) |
| `POST /api/studio/agents` (admin) | `{key, nome, descricao?}` | 201 `AgentSummary` — creates a `studio` agent, `runtime='claude_sdk'`, `ativo=false`, plus an empty draft v1. 409 `key_taken`. |
| `GET /api/studio/agents/{key}` | — | `AgentDetail = AgentSummary + {versoes: [VersionSummary]}`; `VersionSummary = {id, versao, status, notas, model, created_at, published_at, compiled_hash, eval_score: number|null}` newest first |
| `PATCH /api/studio/agents/{key}` (admin) | `{nome?, descricao?, ativo?, publicacao_limiar? (0.5–1)}` | `AgentSummary` (a threshold change is audited) |
| `GET /api/studio/agents/{key}/versions/{vid}` | — | `VersionDetail = VersionSummary + {effort, max_turns, idioma, tool_policy, based_on_version_id, published_by, publish_override_reason, eval_run_id, limiar_aplicado: number|null, secoes: [Section], skills: [Skill]}` (a published version's `eval_score` is the score snapshotted at publish; null for an override); `Section = {id, chave, titulo, ordem, conteudo, ativo}`; `Skill = {id, nome, descricao, corpo, ordem, ativo, arquivos: [{id, caminho, titulo, chars}]}` |
| `POST /api/studio/agents/{key}/draft` (admin) | `{from_version_id?: uuid}` | 201 `VersionDetail`. 409 `draft_exists`. Omitted ⇒ clone of the active version, or empty if none. |
| `DELETE /api/studio/agents/{key}/draft` (admin) | — | 204. 404 when no draft. |
| `PATCH /api/studio/agents/{key}/draft` (admin) | `{notas?, model?, effort?, max_turns?, idioma?, tool_policy?}` | `VersionDetail` (422 `invalid_field` on allowlist) |
| `PUT /api/studio/agents/{key}/draft/sections` (admin) | `{secoes: [{id?, chave, titulo, ordem, conteudo, ativo}]}` — full replace | `VersionDetail` |
| `POST /api/studio/agents/{key}/draft/skills` (admin) | `{nome, descricao, corpo, ordem?, ativo?}` | 201 `Skill`; 409 `skill_exists` |
| `PATCH /api/studio/agents/{key}/draft/skills/{skill_id}` (admin) | any of `{nome, descricao, corpo, ordem, ativo}` | `Skill` |
| `DELETE /api/studio/agents/{key}/draft/skills/{skill_id}` (admin) | — | 204 |
| `PUT /api/studio/agents/{key}/draft/skills/{skill_id}/files` (admin) | `{caminho, titulo?, conteudo}` (upsert by caminho) | `{id, caminho, titulo, chars}` |
| `GET /api/studio/agents/{key}/skills/{skill_id}/files/{file_id}` | — | `{id, caminho, titulo, conteudo}` |
| `DELETE /api/studio/agents/{key}/draft/skills/{skill_id}/files/{file_id}` (admin) | — | 204 |
| `GET /api/studio/agents/{key}/versions/{vid}/compiled?client_id=` | — | `CompiledOut = {texto, hash, tokens_estimados, manifest, sob_demanda, avisos: [{codigo, mensagem, bloqueante}], version_id, client_id}` (compiles live; a READ — never writes `agent_versions.compiled_hash`, L7) |
| `GET /api/studio/agents/{key}/versions/{a}/diff/{b}` | — | `{a: {version_id, hash}, b: {...}, texto_a, texto_b, secoes: [{chave, estado: "igual"|"alterada"|"nova"|"removida"}], skills: [{nome, estado}], configuracoes: [{campo, a, b}]}` |
| `POST /api/studio/agents/{key}/draft/publish` (admin) | `{notas?, override_reason?: str(≥ 20 non-whitespace chars, stored trimmed)}` | `VersionDetail` (now `ativa`). 409 `eval_required` with `{hash_atual, ultima_execucao: {id, score, limiar, compiled_hash, completa}|null}` when the gate fails (only a `completa` run counts) and no override; 409 `compile_blocked` with `avisos` when a blocking warning exists (no override possible); 409 `draft_changed` when the draft moved between the gate check and the publish. |
| `GET /api/studio/prompts/{hash}` | — | `{hash, texto, manifest, version_id, client_id, created_at}` — 404 `prompt_not_found` |

### D2 · Clients (BE-DEF)
`GET/POST /api/studio/agents/{key}/clients` · `GET/PATCH /api/studio/agents/{key}/clients/{client_id}` ·
`POST /api/studio/agents/{key}/clients/{client_id}/entries` · `PATCH/DELETE .../entries/{entry_id}`.
`Client = {id, slug, nome, resumo, ativo, entradas: [{id, tipo, titulo, conteudo, status, created_at}]}` (list omits `entradas`, adds `total_entradas`).

### D3 · Knowledge (BE-KE)
| Method · Path | Body | 2xx |
|---|---|---|
| `GET /api/studio/agents/{key}/knowledge` | — | `{colecoes: [{id, slug, nome, tag, descricao, ordem, total_documentos}]}` |
| `POST /api/studio/agents/{key}/knowledge` (admin) | `{slug, nome, tag?, descricao?, ordem?}` | 201 collection; 409 `slug_taken` |
| `PATCH /api/studio/agents/{key}/knowledge/{col_id}` (admin) | fields | collection |
| `GET /api/studio/agents/{key}/knowledge/{col_id}/documents?q=(≤200)&tipo=&page=&page_size=` | — | `{items: [{id, slug, titulo, tipo, resumo, chars, ativo, updated_at}], total}` |
| `POST /api/studio/agents/{key}/knowledge/{col_id}/documents` (admin) | `{slug, titulo, tipo, conteudo, resumo?, proveniencia?}` | 201 `Document` |
| `GET /api/studio/agents/{key}/documents/{doc_id}` | — | `Document = {id, collection_id, slug, titulo, tipo, resumo, conteudo, proveniencia, ativo, chars, updated_at}` |
| `PATCH /api/studio/agents/{key}/documents/{doc_id}` (admin) | fields + `motivo?` | `Document` (writes a revision) |
| `GET /api/studio/agents/{key}/documents/{doc_id}/revisions` | — | `{items: [{id, op, motivo, author_id, created_at}]}` |
| `GET /api/studio/agents/{key}/knowledge/search?q=(≤512)&colecao=&limite=` | — | `{items: [{doc_id, slug, titulo, colecao, tag, tipo, trecho, rank}]}` — the SAME function the `kb_buscar` tool calls |

### D4 · Evals (BE-KE)
| Method · Path | Body | 2xx |
|---|---|---|
| `GET /api/studio/agents/{key}/evals/cases` | — | `{items: [EvalCase]}`; `EvalCase = {id, slug, titulo, entrada, contexto, criterios: {deve: [str], nao_deve: [str]}, rubrica, tags, ativo}` |
| `POST /api/studio/agents/{key}/evals/cases` (admin) | EvalCase minus id | 201; 409 `slug_taken` |
| `PATCH/DELETE /api/studio/agents/{key}/evals/cases/{case_id}` (admin) | | DELETE of a case with results → 409 `case_in_use` (deactivate instead) |
| `POST /api/studio/agents/{key}/evals/runs` (admin) | `{version_id, case_ids?: [uuid] (≤ 200, deduped)}` | 202 `EvalRun = {id, version_id, compiled_hash, status, total, aprovados, score, limiar, started_at, finished_at, erro, completa}` — runs in background; `completa` only when `case_ids` is omitted; `compiled_hash` = the version compiled at run creation (seam `get_current_hash_dep`, 503 `compile_unavailable` unbound); 409 `run_in_progress` |
| `GET /api/studio/agents/{key}/evals/runs?version_id=` | — | `{items: [EvalRun]}` |
| `GET /api/studio/agents/{key}/evals/runs/{run_id}` | — | `EvalRun + {resultados: [{case_id, case_slug, case_titulo, status, score, saida, veredito: [{criterio, tipo, ok, motivo}]|null, notas_juiz, duracao_ms}]}` |
| `POST /api/studio/agents/{key}/evals/runs/{run_id}/cancel` (admin) | — | `EvalRun` |

### D5 · Import (BE-RT owns the endpoint — it needs both the BE-DEF and BE-KE stores; the bundle format is §F)
`POST /api/studio/agents/{key}/import` (admin) — body = the §F bundle (JSON, ≤ 25 MB; raise the body limit for this route only).
Query `?dry_run=true` returns the plan without writing. Response:
`{dry_run, agente: {criado: bool}, rascunho: {version_id, secoes, skills, arquivos}, conhecimento: {colecoes_criadas, documentos_criados, documentos_atualizados, documentos_inalterados}, evals: {criados, atualizados}, clientes: {criados}, avisos: [str]}`.
Semantics: creates the agent if absent (studio); **replaces the draft's sections + skills** (creating a draft
from the active version first if none exists); knowledge + evals + clients upsert by slug (documents keyed
by `source_sha` — unchanged ⇒ `inalterados`, no revision; created/updated ⇒ an `op='import'` revision; a slug
living in ANOTHER collection ⇒ 409 `slug_in_other_collection`, never a silent move). Never publishes.

### D6 · Conversations (BE-RT) — extends the existing routes, Julia shape unchanged
- `ConversationCreateRequest` gains `agent_key: str = "julia"` and `client_id: UUID | None = None`
  (`client_id` only valid for studio agents, must belong to that agent → 422 `invalid_client`).
- `ConversationOut` gains `agent_key: str`, `version_id: UUID | None`, `client_id: UUID | None`.
- `GET /api/conversations?agent_key=` filters by agent; **default `julia`** when omitted (Julia's existing hook sends no filter — the default keeps her page byte-identical; studio pages always pass `agent_key`).
- `MessageOut` gains `version_id: UUID | None`, `compiled_hash: str | None` (assistant messages of studio agents).
- `POST /api/conversations/{id}/messages` for a studio agent: 409 `no_active_version` if the agent has no
  `ativa` version; 409 `agent_inactive` if `agents.ativo=false`. SSE event names/payloads unchanged.
- The conversation pins `version_id` at creation; a newer publish does NOT move an existing conversation
  (a new conversation picks the new version). `compiled_hash` is recomputed per turn (client entries may change).

---

## §E · Runtime (slice BE-RT)

E1. `AgentSpec` (`runtime/types.py`) becomes generic, backward-compatible:
`key: str`, `prompt_mode: Literal["preset_append","custom"] = "preset_append"`, `toolset: Literal["academia","studio"] = "academia"`,
`agent_id: UUID | None = None`, `version_id: UUID | None = None`, `compiled_hash: str | None = None`,
`web_search: bool = True`. `build_julia_spec` sets the Julia defaults explicitly; nothing about Julia's launch changes
(existing `tests/runtime/test_claude_runtime.py` must pass untouched).

E2. `build_studio_spec(agent, conversation) -> AgentSpec` (`app/studio/spec.py`): loads the conversation's pinned
version bundle + client, calls `compile_prompt`, upserts `compiled_prompts`, returns the spec with
`prompt_append = compiled.texto`, `prompt_mode="custom"`, `toolset="studio"`, model/effort/max_turns from the version.

E3. `build_launch_options` for `toolset=="studio"`:
- `system_prompt`: the SDK's no-preset form (the engineer VERIFIES against installed `claude-agent-sdk` that it
  yields no Claude Code preset text and documents the finding in the code); the compiled prompt still arrives via
  `append-system-prompt-file` (same handoff).
- `plugins=[]`, `skills=[]`, `tools = ["WebSearch"] if spec.web_search else []`.
- `mcp_servers={"studio": build_studio_tools(org_id, agent_id, version_id)}` with EXACTLY these read-only tools:
  - `abrir_skill(nome: str)` → `{nome, descricao, corpo, arquivos: [{caminho, titulo}]}` or `{erro: "skill_inexistente", disponiveis: [...]}`
  - `ler_arquivo_skill(nome: str, caminho: str)` → `{caminho, titulo, conteudo}` or `{erro}`
  - `kb_buscar(consulta: str, colecao: str | None = None, limite: int = 8)` → `{resultados: [{slug, titulo, colecao, tag, tipo, trecho}]}` (limite ≤ 20)
  - `kb_ler(slug: str, parte: int = 1)` → `{slug, titulo, colecao, tag, tipo, proveniencia, parte, total_partes, conteudo}` — pages of ≤ 24 000 chars, split on paragraph boundaries.
- `allowed_tools` = those four `mcp__studio__*` names (+ `WebSearch` when enabled); `disallowed_tools` = the
  existing `DISALLOWED_TOOLS` plus `Skill`. `can_use_tool` denies anything else (no approval flow for studio v1 —
  there are no write tools).
- Tools read through the BE-KE/BE-DEF stores (never raw SQL in the tool layer); knowledge honours `tool_policy.knowledge`.

E4. The turn runner stamps `version_id` + `compiled_hash` on the assistant message it persists.

E5. `FakeAgentRuntime` handles studio specs (echo-style reply that includes the spec key and the first 40 chars of the
compiled hash) so route tests run without the SDK.

E6. Eval runner (`app/studio/evals.py`, BE-RT owns — it drives the runtime): for each case, run ONE turn through the same
`AgentRuntime` with a fresh ephemeral conversation context (not persisted as a user conversation; tagged `eval`), collect the
final assistant text, then judge with `noctusai_lib` LLM (`claude-sonnet-5`) using the rubric prompt (criteria list + rubric +
output) returning strict JSON `{veredito: [...], score: 0..1, notas: str}`. Case passes when every `deve` is ok and no
`nao_deve` is violated. Run `score` = mean case score; `aprovados` = passed cases. Concurrency 2. A judge/LLM failure marks
the case `erro` (counts as failed) — never silently skipped. Slot capacity is respected (a busy pool waits, bounded).

---

## §F · Import bundle (content ↔ BE contract; IsaIA's content is authored OUTSIDE the repo)

```json
{
  "formato": "noctus.agent-bundle/v1",
  "agente": {"key": "isaia", "nome": "IsaIA", "descricao": "..."},
  "versao": {"notas": "...", "model": "claude-opus-5", "effort": "high", "max_turns": 40, "idioma": "pt-BR",
             "tool_policy": {"web_search": true, "knowledge": true}},
  "secoes": [{"chave": "identidade", "titulo": "...", "ordem": 10, "conteudo": "...", "ativo": true}],
  "skills": [{"nome": "roteiro-reels", "descricao": "...", "corpo": "...", "ordem": 10, "ativo": true,
              "arquivos": [{"caminho": "references/arquiteturas.md", "titulo": "...", "conteudo": "..."}]}],
  "conhecimento": [{"slug": "audience", "nome": "...", "tag": "AU", "descricao": "...", "ordem": 10,
                    "documentos": [{"slug": "...", "titulo": "...", "tipo": "fonte", "resumo": "...",
                                    "proveniencia": {}, "conteudo": "..."}]}],
  "evals": [{"slug": "...", "titulo": "...", "entrada": "...", "contexto": null,
             "criterios": {"deve": ["..."], "nao_deve": ["..."]}, "rubrica": null, "tags": ["..."]}],
  "clientes": [{"slug": "...", "nome": "...", "resumo": "...", "entradas": [{"tipo": "marca", "titulo": "...", "conteudo": "..."}]}]
}
```
Validated with Pydantic (strict; unknown keys rejected with the JSON path in the error).

---

## §G · Frontend (slices FE-DEF, FE-KE) — routes, pages, data

Nav: add **"Agent Studio"** (`/studio`, icon `Blocks`/`Boxes`) to the principal group. Julia's pages untouched.

| Route | Page | Owner |
|---|---|---|
| `/studio` | Agent list (cards/table: nome, key, modo, ativo toggle, versão ativa, rascunho badge) + "Novo agente" (admin) | FE-DEF |
| `/studio/:key` | Agent shell with tabs (URL-driven `?tab=`): **Visão geral · Prompt · Skills · Configurações · Conhecimento · Avaliações · Clientes · Versões · Prompt compilado · Conversar** | FE-DEF (shell + Visão geral/Prompt/Skills/Configurações/Versões/Prompt compilado), FE-KE (Conhecimento/Avaliações/Clientes/Conversar) — each tab is its own component file under `src/pages/studio/tabs/` |

Tab contracts:
- **Visão geral**: status, versão ativa/rascunho, last eval score, limiar, quick actions (criar rascunho, publicar, abrir inspector).
- **Prompt**: ordered list of sections of the DRAFT (drag or ▲▼ reorder, add, remove, toggle ativo, edit título/chave/conteúdo in a monospace markdown textarea with char/token counter). Save = `PUT .../draft/sections`. Read-only (with "Criar rascunho" CTA) when no draft.
- **Skills**: list + editor (nome, descrição with 1024 counter, corpo textarea) + attached files list with add/edit/delete.
- **Configurações**: model, effort, max_turns, idioma, tool_policy toggles, publicacao_limiar (agent-level).
- **Versões**: table of versions (status badges), "Criar rascunho a partir desta" (restore), diff picker (two versions → `diff` endpoint: section/skill states + side-by-side compiled text), publish dialog (shows gate status: last eval score vs limiar for the current hash; override reason field shown only when gate fails; blocking warnings listed).
- **Prompt compilado** (the inspector): version selector (default draft if exists else ativa) + optional client selector; renders `texto` with section boundaries from `manifest` (each block labelled with its source; click → navigate to the Prompt/Skills tab item); header shows `hash`, `tokens_estimados`, per-section token bar; warnings panel; **"Camada sob demanda"** list from `sob_demanda`; "Comparar com publicada" toggle using the diff endpoint; copy-to-clipboard. Also reachable as `/studio/prompts/:hash` (from a message's "prompt usado" link).
- **Conhecimento**: collections sidebar; documents table with search (`q`), tipo filter; document viewer/editor (markdown textarea, provenance fields, revision list); search playground calling `knowledge/search` (shows exactly what `kb_buscar` would return).
- **Avaliações**: cases list/editor (entrada, contexto, deve[]/nao_deve[] editable lists, rubrica, tags); runs list; "Rodar avaliação" on the draft; run detail (per case pass/fail, score, saída, veredito per criterion, judge notes) polling while `executando`.
- **Clientes**: client list/editor (resumo markdown + typed entries CRUD).
- **Conversar**: chat with the agent — reuse the seed `ChatWindow` organ exactly as `Julia.tsx`/`JuliaChatWindow` do (extract a shared `AgentChatWindow` if it removes duplication; do NOT fork the organ), with a client selector at conversation creation; each assistant message shows `versão N · prompt sha256:abcd…` linking to `/studio/prompts/:hash`.

Rules: TanStack Query hooks in `src/hooks/studio/*.ts` (one file per resource); loading = `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data` (never `isLoading`); key-changing queries use `placeholderData`; admin-only controls hidden for members AND the server enforces it; every page has loading/empty/error/success states; pt-BR copy; consume `@noctusai/lib` design-system components (check the organ catalog before building any UI primitive — a markdown editor, diff view or token bar that other products could use goes to `@noctusai/lib` only if it is generic; otherwise keep it product-local and declared).

---

## §H · Security invariants (all slices)

1. Studio routes: admin for every write, member for reads; org-scoped by `ctx.org_id` on every query (a foreign `vid`/`doc_id`/`case_id` → 404, never 403-leak).
2. No studio tool can write anything. `can_use_tool` for studio denies every name outside the allowlist.
3. `compiled_prompts` is write-once; `agent_versions` published rows immutable (DB triggers, tested).
4. The eval gate cannot be bypassed without an override reason ≥ 20 chars, recorded on the version.
5. No person/company names in any committed file of this feature (content lives in the DB).
6. Auth tests assert strict `== 401` / `== 403` / `== 404` — never `in (...)`.
7. Import is admin-only, size-capped, strictly validated; it never publishes.

## §J · Slices & ownership (file-disjoint)

| Slice | Owns (creates/edits) | Must not touch |
|---|---|---|
| **BE-DEF** | `migrations/012_*`, `app/studio/{__init__,compiler,models}.py`, `app/stores/studio_definitions.py`, `app/routers/studio_agents_router.py`, `app/routers/studio_clients_router.py`, `app/schemas/studio.py`, tests under `tests/studio/def/` | runtime/, conversations_router, 013 |
| **BE-KE** | `migrations/013_*`, `app/stores/studio_knowledge.py`, `app/stores/studio_evals.py`, `app/routers/studio_knowledge_router.py`, `app/routers/studio_evals_router.py`, `app/schemas/studio_ke.py`, tests under `tests/studio/ke/` | compiler, runtime/ |
| **BE-RT** (wave 2) | `runtime/*`, `app/studio/{spec,tools,evals,importer}.py`, `app/routers/studio_import_router.py`, `conversations_router.py`, `schemas/agents.py` (additive), `dependencies.py` (additive), `main.py` router registration for all studio routers, tests under `tests/studio/rt/` + existing runtime tests kept green | migrations |
| **FE-DEF** | `src/pages/studio/{StudioList,StudioAgent}.tsx`, `src/pages/studio/tabs/{Overview,Prompt,Skills,Settings,Versions,Compiled}Tab.tsx`, `src/pages/studio/PromptByHash.tsx`, `src/hooks/studio/{useStudioAgents,useVersions,useCompiled,useClients}.ts`, `src/api/studio/types.ts` (the TS mirror of §D — FE-DEF authors it, FE-KE imports), `App.tsx` routes+nav | KE tabs |
| **FE-KE** | `src/pages/studio/tabs/{Knowledge,Evals,Clients,Chat}Tab.tsx`, `src/hooks/studio/{useKnowledge,useEvals,useStudioChat}.ts`, `src/components/studio/*` it needs | FE-DEF files (imports `types.ts` read-only; if it needs a type added, it adds it in `src/api/studio/types-ke.ts`) |
| **CONTENT** (orchestrator) | IsaIA bundle JSON — authored OUTSIDE the repo | repo |

`main.py` router registration: BE-DEF and BE-KE each export `router` objects; **BE-RT registers all of them** (single owner of `main.py`) — until then BE-DEF/BE-KE tests mount their routers on a test app.

## §J2 · Cross-slice seams (pinned so wave-1 slices never import each other's unfinished code)

1. **Eval gate** — BE-DEF defines in `app/studio/models.py`:
   ```python
   @dataclass(frozen=True)
   class GateRun: id: UUID; score: float | None; limiar: float; compiled_hash: str; status: str
   class EvalGate(Protocol):
       def latest_concluded_run(self, org_id: UUID, version_id: UUID) -> GateRun | None: ...
   class FakeEvalGate: ...   # in-memory, settable in tests
   ```
   BE-DEF's publish route depends on `get_eval_gate_dep` (BE-DEF adds it to its own router module as a
   FastAPI dependency returning `FakeEvalGate()` ONLY under the test app; the production binding is added by
   BE-RT). BE-KE implements `SupabaseEvalGate` in `app/stores/studio_evals.py` satisfying that Protocol
   (it imports `GateRun` from `app.studio.models` — BE-KE copies the 5-field dataclass verbatim into its tests'
   expectations; the import resolves once BE-DEF merges, and BE-KE's own module must import lazily inside the
   method so BE-KE's branch builds standalone). Gate rule (BE-DEF): pass ⇔ run exists ∧ status='concluida' ∧
   run.compiled_hash == draft.compiled_hash ∧ score >= agent.publicacao_limiar.
2. **Eval scheduling** — BE-KE's `POST .../evals/runs` inserts the run as `pendente` (with the version's current
   `compiled_hash`; NULL hash → 409 `compile_required`) then calls `scheduler.schedule(run_id)` from dependency
   `get_eval_scheduler_dep`. BE-KE's default binding raises → 503 `eval_runner_unavailable` (fail closed); BE-RT
   binds the real runner.
3. **Router registration** — only BE-RT edits `main.py`. Wave-1 tests mount routers on a local test app.
4. **Frontend tab modules** — each tab file default-exports `function XTab({ agentKey }: { agentKey: string })`.
   FE-DEF's shell lazy-imports all ten tab files by the §J names. FE-DEF ships the four KE tab files as minimal
   compiling stubs ("Disponível em breve") so its branch builds; FE-KE REPLACES those four files wholesale
   (orchestrator merges FE-DEF first, then takes FE-KE's side for exactly those four paths).

## §K · Deliberately later (named destinations)
- Embedding hybrid search over `knowledge_documents` (pgvector + `noctusai_lib.integrations.llm.embeddings`) — trigger: search misses reported in evals ≥ 3.
- Studio write tools (client-brain writeback through the approval gate) — trigger: first request to let the agent record decisions.
- Migrating Julia to `definition_mode='studio'` — trigger: owner decision.

## §L · Controle de custo

**WHY.** 2026-09-21: 5 eval runs (160 cases — Opus-5 generator via the Claude Agent SDK + Sonnet-5
judge via `noctusai_lib`) cost ~$20 of Anthropic credit while nothing in this product recorded what
a turn or a case cost. This section makes cost visible, bounded, and cheap to iterate on. Migration
`014_agent_studio_cost.sql` (additive, written not applied — shared prod DB, tech-lead applies with
user consent).

**L1 · Schema additions (014).**
- `agents.eval_results`: `custo_usd numeric(10,4) null` (generator + judge, summed), `tokens_entrada
  int null`, `tokens_saida int null`, `tokens_cache_leitura int null` (the generator turn's SDK
  `ResultMessage.usage` counts). `status` CHECK gains `'pulado'` — a case the runner never started
  because the run's `limite_usd` was already reached; `notas_juiz` carries
  `app.studio.models.BUDGET_EXCEEDED_NOTA` (`"limite de custo atingido"`). Distinct from `'erro'`
  (the turn or judge actually failed).
- `agents.eval_runs`: `modelo_geracao text null` (cheaper-iteration override, CHECK `IN
  ('claude-sonnet-5','claude-haiku-4-5')` — narrower than `agent_versions.model`'s allowlist; `NULL` =
  the version's own model), `limite_usd numeric(10,2) null` (CHECK `0 < x <= 50`), `custo_usd
  numeric(10,4) null` (accumulated over every result).
- `agents.messages` (assistant turns): `custo_usd numeric(10,4) null`, `tokens_entrada int null`,
  `tokens_saida int null` — straight off the same SDK `ResultMessage`, stamped by the turn loop
  (`app/routers/conversations_router.py`) on the last assistant message a turn persisted.
- `agents.create_eval_run` (013) gains trailing `p_modelo_geracao text default null`, `p_limite_usd
  numeric default null`, stamped in the same one-transaction insert (L6). The 7-parameter overload is
  dropped first (Postgres treats a different parameter list as a distinct function identity).

**L2 · Cost capture.**
- **Generator** — `app.runtime.claude_runtime.run_turn` reads `total_cost_usd` + `usage` (input/
  output/cache-read tokens) off the SDK's `ResultMessage` and surfaces them on the turn's final
  `session.status` event (additive fields `custo_usd`/`tokens_entrada`/`tokens_saida`/
  `tokens_cache_leitura`). No pricing lookup on this side. Absent (no `ResultMessage` observed) stays
  `null` — logged, never a silent 0. `FakeAgentRuntime` accepts the same four as constructor kwargs
  (default `None`, byte-identical to every pre-existing script) so tests can drive a fixed per-turn cost.
- **Judge** — `noctusai_lib.integrations.llm.chat_completion` only ever returns text; usage is reported
  to a `UsageSink` the caller never sees back. `app.studio.evals._call_with_usage` installs a small
  composing capture sink on `get_llm_config().usage_sink` (wraps — never replaces — any real sink),
  serialized by one process-wide `asyncio.Lock` (correctness of per-call attribution over judge-call
  parallelism; `EVAL_CONCURRENCY=2` and only the short judge call is serialized, not the generator
  turn). Reads `UsageEvent.cost_estimate_usd` (already computed by the provider via
  `noctusai_lib.integrations.llm.usage.estimate_cost_usd` against `models.py` pricing — no
  reimplementation). `eval_results.custo_usd` = generator + judge (`app.studio.evals.combine_cost`,
  field-by-field sum, `None` only when BOTH legs are `None`).
- **Chat messages** — the same generator capture, persisted via `app.stores.messages.MessageStore.
  set_turn_cost` on the last assistant message the turn loop wrote, when the final `session.status`
  event carries cost/token keys.

**L3 · Cheaper iteration mode.** `POST .../evals/runs` body gains optional `modelo_geracao ∈
{"claude-sonnet-5","claude-haiku-4-5"}` (422 `invalid_modelo_geracao`-shaped `ValueError` outside the
allowlist). The runner (`app.studio.evals.EvalRunner._execute_claimed`) applies it via
`dataclasses.replace(spec, model=...)` right after `build_studio_spec` — `AgentSpec` is frozen, and the
compiled hash (unaffected by which model runs) is checked before the override, so this never disturbs
the hash-match guard. **A run with `modelo_geracao` set can never satisfy the publish gate** —
`app.stores.studio_evals.SupabaseEvalGate.latest_concluded_run` filters `.is_("modelo_geracao",
"null")` in addition to `completa`/`status`.

**L4 · Rerun only failures.** `POST .../evals/runs` body gains optional `repetir_falhas_de: uuid` —
the router resolves it into `case_ids` server-side (`status != 'aprovado'` results of that run, same
org+agent via the existing `get_run` resolver — 404 `eval_run_not_found` otherwise) before calling
`store.create_run`. Mutually exclusive with `case_ids` (422, `EvalRunCreateRequest`'s
`model_validator`).

**L5 · Budget cap per run.** Optional `limite_usd` (`0 < x <= 50`); omitted ⇒
`settings.studio_eval_run_budget_usd` (env `STUDIO_EVAL_RUN_BUDGET_USD`, default `2.00`). The runner's
`_CostTracker` accumulates `custo_usd` (deliberately UN-locked — every read/write happens with no
`await` in between, so `asyncio`'s cooperative scheduling already serializes it across the
concurrency-2 workers); once `total >= limite_usd` a worker takes no further case (same "no await
between check and take" invariant the pre-existing empty-queue check uses). The run then:
`app.stores.studio_eval_runs.EvalRunWriter.skip_pending_results` flips every still-`pendente` result to
`'pulado'`; `finish_run` is called with `status="falhou"`, `erro=BUDGET_EXCEEDED_NOTA`,
`custo_usd=<accumulated>`, and **`completa=False`** — even a run created over every active case (whose
`completa` 013's `create_eval_run` stamped `True` at creation) is downgraded so it can never satisfy
the publish gate once the cap cut it short. `GET .../evals/runs/{id}` exposes `run.custo_usd` (the
sum) and every result's `custo_usd`/`tokens_*`.

**L6 · HTTP additions (all additive; existing fields/shapes unchanged).**
- `POST .../evals/runs` body: `+ modelo_geracao?, limite_usd?, repetir_falhas_de?` (still mutually
  exclusive with `case_ids`).
- `EvalRun`/`EvalRunOut`: `+ modelo_geracao, limite_usd, custo_usd`.
- `EvalResult`/`EvalResultOut`: `+ custo_usd, tokens_entrada, tokens_saida, tokens_cache_leitura`.
- `MessageOut`: `+ custo_usd, tokens_entrada, tokens_saida` (assistant messages; null otherwise).

**L7 · Not in this slice (named destination).** Frontend surfacing (cost badges, a budget-cap banner,
a "cheaper iteration" model picker in the run-launch UI) — trigger: the next Agent Studio FE slice.
`products/agents/frontend/src/api/studio/types-ke.ts` already mirrors L6's `EvalRun`/`EvalResult`
additions (and `StudioMessage` mirrors the message ones) so that slice starts from a synced contract.

## §M · UI bulk ingest (2026-09-23)

**WHY.** IsaIA's own knowledge corpus is 382 documents / 12 skills with 21 reference files — building
that entirely through the Studio UI (the goal, instead of one `import` bundle authored outside the
repo) was impossible at one-document/one-file-per-call. Both routes reuse existing store semantics
verbatim — no new upsert logic, no new DB objects.

**M1 · `POST .../knowledge/{col_id}/documents/batch`** (admin). Body `{"documentos": [{slug, titulo,
tipo, conteudo, resumo?, proveniencia?}, ...]}` — same fields/caps as the single-document
`DocumentCreateRequest` (`app/schemas/studio_ke.py::DocumentBatchItemIn`), 1..100 items
(`DOCUMENTS_BATCH_MAX`, 422 beyond — a Pydantic list-length error, not a 413; the 413 backstop is the
route's raised body-size cap below). Calls the SAME `StudioKnowledgeStore.
upsert_document_by_source_sha` the §F importer uses per item — idempotent re-upload (`"inalterado"`,
no revision written), a slug already in ANOTHER collection → per-item `"erro"`
(`slug_in_other_collection`), never a 409 for the whole call. Response: `{resultados: [{slug, status:
"criado"|"atualizado"|"inalterado"|"erro", doc_id?, erro?}], criados, atualizados, inalterados,
erros}` — one bad document never loses the other 99 (§H "PER-ITEM results, never all-or-nothing").
`proveniencia` was already accepted on the single-document create route (`DocumentCreateRequest.
proveniencia: dict | None`) — no schema change needed there.

**M2 · `PUT .../draft/skills/{skill_id}/files/batch`** (admin). Body `{"arquivos": [{caminho, titulo?,
conteudo}, ...]}` — same fields/caps/path-traversal guard as the single-file `SkillFileUpsertRequest`,
1..50 items (`SKILL_FILES_BATCH_MAX`). Draft-only: `_resolve_draft_skill` 409s `version_immutable` for
the WHOLE call if the target version isn't a `rascunho` (same as the single-file route — a batch never
opens a weaker path onto a published version). Calls `upsert_skill_file` per item (upsert keyed on
`caminho`); the router determines created-vs-updated by diffing against the skill's file set fetched
once before the loop. Response: `{resultados: [{caminho, status: "criado"|"atualizado"|"erro", id?,
titulo?, chars?, erro?}], criados, atualizados, erros}`.

**M3 · Body-size overrides (`app.main`).** Both routes are JSON bodies above the seed's 1 MB
webhook-DoS default, registered in `max_body_path_overrides` the same way as `.../import` (whole-
segment wildcard patterns, `DOCUMENTS_BATCH_BODY_LIMIT_PATTERN` / `SKILL_FILES_BATCH_BODY_LIMIT_PATTERN`
in each router module): 20 MB for documents (generous headroom over a realistic 100-doc batch; well
under the 100×2 MB pathological max `document.conteudo` alone would allow), 8 MB for skill files
(50×120 KB pathological max is 6 MB). Narrower than the 25 MB bundle-import cap in both cases — each
call is one collection's or one skill's slice, not a whole agent.

**M4 · Validation parity (§H4).** Every cap/allowlist the single-item route enforces applies
identically per batch item — `tipo` allowlist, slug pattern, `document.conteudo`/`skill_file.conteudo`
size caps, `caminho` pattern + `..`-exclusion — via the SAME Pydantic field constraints
(`DocumentBatchItemIn`/`SkillFileBatchItemIn` mirror the single-item request schemas field-for-field)
and the SAME store-layer validation (`_validate_slug`/`_validate_tipo`/`_check_cap` — no batch-only
code path bypasses them). No weaker path into `knowledge_documents` or `agent_skill_files`.
