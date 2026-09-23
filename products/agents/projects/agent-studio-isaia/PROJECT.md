# Agent Studio + IsaIA — Project Document

> Living document. Write-for-a-zero-context-reader: everything needed to continue is here or in `CONTRACT.md`.

- **Created:** 2026-09-21
- **Last updated:** 2026-09-21
- **Status:** On `dev` (5626935dc) — live-verified in the prod image; prod promotion awaits the owner
- **Owner / stakeholders:** repo owner (product decisions) · tech-lead session (orchestration)
- **Related docs:** `CONTRACT.md` (this folder — the binding shape) · `products/agents/MASTER-PROMPT.md` · `project-history/roadmaps/julia-agents-academia-2026-09.md` (Julia's plan; Julia stays untouched here) · `KB § PATTERNS/frontend/lying-loading-state.md` · `KB § PATTERNS/backend/database-rls.md`
- **Project slug:** `agent-studio-isaia` (single-product → `products/agents/projects/`)

---

## 1. Context & Purpose

The `agents` product runs managed AI agents on the Claude Agent SDK. Today one agent (Julia) is wired by
hand: her prompt and skills are files in the image; only a few persona fields are editable in the UI.

The owner is developing **IsaIA**, an Instagram content-creation strategist built on four source
methodologies (tags `[AU]` `[KE]` `[CA]` `[IG]`) plus a synthesis layer (four engines: strategy, unit
construction, orchestration, measurement/learning; decision cards; a tool/mechanism registry; epistemic
rules; a video-performance diagnosis protocol). The material arrived as a ~1 000-file package produced by
other LLMs across ~40 versions — a strong core (~200 KB) under heavy version sediment.

This project does two things:
1. **Agent Studio** — make an agent a *versioned, UI-managed definition* (prompt sections, skills with
   reference files, settings/tool policy, knowledge library, eval cases, client brains), published behind an
   eval gate, compiled by ONE function into the **master prompt**, with an inspector page that shows exactly
   what each turn ran with.
2. **IsaIA** — rebuild the agent cleanly as the first Studio agent: lean always-loaded prompt, job-shaped
   skills, the four methodologies + synthesis as a provenance-tagged knowledge library, and an eval suite
   distilled from the package's adversarial cases.

## 2. Confirmed constraints (owner's words, 2026-09-21)

- "make all parts of it manageable via ui fields and pages" → A1 (DB-held, UI-edited).
- "those pieces will join into a master prompt that composes the agent. I also need an ui to see this master
  prompt, that is used on the agent, to make sure everything is built correctly" → A4/A7 + the inspector.
- "The canonical reference is going to be IsaIA. Julia isn't developed yet" → Studio is the canonical agent
  shape; Julia keeps her path for now (`definition_mode='legacy'`), migration named in CONTRACT §K.
- "stop and report after deploying to dev, testing, refining issues and improvements, redeploying. Then I'll
  tell you to deploy to prod or not yet." → this project ends its current leg at `dev` + local verification;
  **no bless/promote/deploy_image without the owner's explicit go**.
- Repo is public (MASTER-PROMPT rule) → no methodology corpus, prompt text, person/company names in git.
  IsaIA content is authored outside the repo and imported through the §F endpoint.
- The Supabase project is shared with prod (dev fleet dormant) → migrations 012/013 are additive-only and are
  applied to the shared DB only with the owner's go (asked before live testing).

## 3. Design principles

Seed-first (reuse the agents product's store Protocol+Fake+Real+factory pattern, the slot runtime, the
`ChatWindow` organ); one compiler, many consumers; immutability over mutation; eval gate as the review
control; fail closed (no silent fallbacks in tools, judge, or import).

## 3a. Seed-first analysis

| Need | Existing seam | Verdict |
|---|---|---|
| Stores | agents' Protocol + Fake + Supabase + factory pattern (`app/stores/*`) | consume |
| Chat UI | seed `ChatWindow` organ via `JuliaChatWindow` | consume (extract shared wrapper if it removes duplication) |
| Runtime | `ClaudeAgentSdkRuntime` + slot pool + `append.md` handoff | extend (generic `AgentSpec`, studio toolset) |
| LLM judge | `noctusai_lib.integrations.llm` | consume |
| Versioned-content shape | social-wiring `fotos_guias_estilo` (rascunho/ativa/substituida, restore-as-clone) | mirror |
| Knowledge search | knowledge-extractor tables (pgvector) | deferred (FTS v1, CONTRACT A9/§K) |
| Markdown editor / diff viewer / token bar | none in `@noctusai/lib` | product-local, declared; lift when a 2nd product needs it |

## 4. Scope

In: CONTRACT §B–§H; IsaIA content bundle; local verification (unit + route tests, `vite build`, local run of the
product against the shared DB once migrations are approved, real-agent eval run). Out: prod deploy (owner-gated),
Julia migration, embeddings, studio write tools.

## 4a. Dispatch routing

### 4a.1 Slice → Lens table

| Slice | Lens | Files | Dispatched as |
|---|---|---|---|
| W1 · BE-DEF | backend-engineer | CONTRACT §J row BE-DEF | Agent (worktree `feat/agent-studio-be-def`) |
| W1 · BE-KE | backend-engineer | CONTRACT §J row BE-KE | Agent (worktree `feat/agent-studio-be-ke`) |
| W1 · FE-DEF | frontend-engineer | CONTRACT §J row FE-DEF | Agent (worktree `feat/agent-studio-fe-def`) |
| W1 · FE-KE | frontend-engineer | CONTRACT §J row FE-KE | Agent (worktree `feat/agent-studio-fe-ke`) |
| W1 · CONTENT | tech-lead inline (+ general-purpose helpers) | outside repo | inline |
| W2 · BE-RT | backend-engineer (opus) | CONTRACT §J row BE-RT | Agent after W1 merges |
| W3 · integrate + verify + refine | tech-lead | whole feature | inline + advisors (security, compliance-reviewer) |

### 4a.2 Codification expectations

| Slice | s1 | s2 | s3 | s4 | Why |
|---|---|---|---|---|---|
| BE-DEF | yes | no | no | no | versioned-definition shape is N=2 (after photo guides) → triage at close |
| others | no | no | no | no | feature work |

### 4a.3 Routes-not-taken

| Route | Why rejected |
|---|---|
| Skills as files in the image (Julia's shape) | not UI-manageable; public repo |
| Materialize a per-version plugin dir for the SDK `Skill` tool | needs a `julia-cli-slot` §E.11 security-contract change; DB-backed MCP tools give the same progressive disclosure with zero filesystem surface |
| `claude_code` preset + append for IsaIA | invisible coding prompt above ours — the inspector could never be complete |
| One skill per source methodology | contradicts IsaIA's own doctrine ("route by problem, not by teacher"); methodologies are knowledge collections |
| Multi-agent pipeline (researcher → strategist → critic → writer) | sequential shared-context work; single agent + skills is cheaper and more coherent; critique stays a skill/eval |
| pgvector embeddings in v1 | cost + provider dependency with no evidence FTS is insufficient; named trigger in §K |

### 4a.4 Notes
Engineers return the engineer-seed short-form delivery (files · tests · acceptance · `drift-found:` · `scoped-improvement:`).
A better route than the brief ⇒ STOP and report (no silent divergence).

## 5. Architecture / Data Model

→ `CONTRACT.md` §B (DB), §C (compiler), §D (API), §E (runtime), §F (bundle), §G (UI).

## 6. Implementation phases

### Phase 0 — Audit ✅
- [x] Read the IsaIA package (4 parallel readers) and the agents product (runtime, stores, routes, pages)
- [x] Web research: agent architecture, Agent Skills spec, context engineering, evals
- [x] Contract authored

**Improvements:** Julia's `spec.yaml` lists bare skill names while the SDK docs namespace plugin skills as `plugin:skill` — possible live defect in Julia's skill loading; recorded here, verification deferred → Phase 3 (a live check of the `init` message's `skills` array during local runtime testing).

### Phase 1 — Wave 1 (parallel): BE-DEF · BE-KE · FE-DEF · FE-KE · CONTENT ✅
- [x] BE-DEF merged
- [x] BE-KE merged
- [x] FE-DEF merged
- [x] FE-KE merged
- [x] IsaIA bundle v1 authored (outside repo)

**Improvements:** none identified.

### Phase 2 — Wave 2: BE-RT (runtime, studio tools, conversations, eval runner, router registration) ✅
- [x] BE-RT merged; Julia runtime tests green untouched

**Improvements:** none identified.

### Phase 3 — Integrate, verify, refine (dev) ⏳
- [x] Full gate on merged tip (backend 1157 · agents FE 150 · seed lib 516 · academia FE 73 · toolkit 351)
- [x] Security + compliance advisor pass; findings fixed (BE-HARDEN, FE-FIX, reconcile)
- [x] Owner go for migrations on the shared DB → 012/013 applied via migrate_product; 15/15 live guard probes pass
- [ ] Local run: import ✅ · compile ✅ · eval gate ✅ (0.881 → 0.974) · publish + chat + inspector-by-hash — blocked: Anthropic account credit exhausted mid-run 3
- [x] Refinement loop; integrate to `dev`
- [ ] Report to owner (prod = owner's call)

**Improvements:** applied — uvicorn `--loop asyncio` (uvloop rejected subprocess `user=`, every slot quarantined in the prod image); studio system prompt via `{type:file}` (neutral identity line); judge aligns by criterion number; eval-run writes retry transient transport errors; startup steps independent + retried; studio turns decoupled from Julia-only config; trigram index dropped (pg_trgm lives in another product's schema); tests can never reach the shared DB (conftest blanks the service key); pre-commit always refreshes the shared auto-improvement cache; `cli.py --validate` no longer crashes on global issues. Deferred → owner decision: prod promotion; Julia migration to studio (CONTRACT §K).

### Phase 4 — IsaIA built through the UI in prod (2026-09-23) ⏳
Source: `products/agents/projects/IsaIA/PLAYGROUND` only (gitignored), split per record by
`isaia-private/playground/split_for_ui.py` — regenerated from PLAYGROUND and byte-identical. Target: the owner's
real org, agent `isaia` (created empty by the owner). The bundle import was deliberately NOT used.

| Content | UI surface | Verified |
|---|---|---|
| 7 prompt sections | Prompt → "+ Seção" (título · chave · conteúdo) → Salvar seções | md5 of all 7 = source |
| model/effort/turns/idioma/tools + notas | Configurações | saved |
| 12 skills (nome · descrição · corpo) | Skills → "+ Skill" (bodies pasted from the .md, as a person would) | md5 of 12 desc + 12 corpo = source |
| 5 collections (slug · nome · tag · descrição · ordem) | Conhecimento → Nova coleção | compiled catalog lines = source |
| 32 eval cases (entrada · contexto · deve[] · não deve[] · rubrica · tags) | Avaliações → Novo caso | one md5 over all 32 = `authoring/evals.json` (PLAYGROUND carries no evals; the publish gate needs them) |
| 382 knowledge documents · 21 skill reference files | Conhecimento / Skills → "Enviar arquivos" | ⏳ waits for the uploader fix to reach prod |

**Master-prompt validity.** PLAYGROUND's `01_MASTER_PROMPT_RUNTIME.md` IS the compiler's output (manifest hash
`sha256:3e51b0b5…`), so the UI-built draft is checked by hash, not by eye. With sections + skills + collections in
and 0 documents, the inspector shows `sha256:4de28ad0…` / 22 474 chars — exactly the PLAYGROUND text with the five
`(N documentos)` counts set to 0 (−6 chars). Referential integrity of the prompt + skill bodies: every backticked
tool (8), skill (88), reference path (53) and document slug (390) resolves; `carrossel` reads `roteiro-reels`'
references through `ler_arquivo_skill("roteiro-reels", …)`, which the tool allows.

**Improvements** (found only by driving the real UI — the QA "pre-flight" called the API with its own parser):
- fixed `2d9cbf8bf` — KnowledgeUploadDialog dropped the nested `proveniencia:` block (all 382 docs carry one);
  SkillFilesUploadDialog stored a picked file as `arquivos.md` while skill bodies cite `references/arquivos.md`
  (`ler_arquivo_skill` matches exactly).
- open → next Studio FE slice: no file/bulk path for **skill bodies** (12 × ~14 KB pasted by hand) nor for **eval
  cases** (32 forms, 198 criteria typed one by one); the upload preview does not show parsed provenance.

## 7. Open questions
- Rights to use the third-party course material in a commercial agent — owner's call; content stays DB-only regardless.
- Missing sources (per-format script doc of `[CA]`; provenance of the 15-sequence Stories bank of `[KE]`) — recorded as gaps in the knowledge library.

## 8. Dependencies & blockers
- Owner go before applying migrations to the shared Supabase project.
- `noctusai` MCP server currently fails to connect; tools are driven through their Python entry points.

## 9. Success criteria
- An admin can create/edit/publish an agent entirely from the UI; every published version is immutable and diffable.
- The inspector shows the exact compiled prompt; each assistant message links to the hash it ran with, and the text at that hash equals what the runtime wrote to `append.md`.
- Publishing is blocked without a passing eval run on the current hash (or a recorded override).
- IsaIA answers in pt-BR, routes by problem, uses skills + knowledge just-in-time, cites provenance tags, and passes its eval suite.
- Julia's behaviour and tests are unchanged.

## 10. How to use this plan
Read `CONTRACT.md` first. Backend: `cd products/agents/backend && pytest`. Frontend: `cd products/agents/frontend && npx vite build && npx vitest run`.

## 11. Change log
- 2026-09-21 — Project created; contract v1 locked; Wave 1 dispatch.
- 2026-09-21 — Waves 1+2 merged; security/compliance hardening; 012/013 applied (owner go); integrated to dev.
- 2026-09-22 — Live verification in the prod image (QA org): 3 eval rounds, 5 production bugs found and fixed; paused on Anthropic credit exhaustion.
