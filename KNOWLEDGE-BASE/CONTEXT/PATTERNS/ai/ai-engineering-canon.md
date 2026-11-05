# AI-engineering canon — building LLM features and agents on this platform

> **What this is.** The profession's canon for building LLM features and agents (agent architecture,
> prompt and context engineering, tool design, structured outputs, model routing and cost, retrieval,
> observability, failure modes, production readiness), mapped onto the house mechanisms that already
> implement it. Owner: `ai-engineer` (`.claude/agents/ai-engineer.md`). Authored 2026-11-05
> (agent-refinement W2-S1). The eval discipline has its own doc: `KB § PATTERNS/ai/agent-evals.md`.
>
> **Why it exists.** The agents product (`products/agents/`) already encodes hard-won rules: a compiled
> prompt with a content hash, a judge that never decides pass/fail, a pass^k mechanism suite, a
> readiness view that mirrors the publish gate, per-run cost caps. They were learned one incident at a
> time and live in docstrings. An engineer who knows only the incidents re-derives them by hand; one
> who knows the canon recognizes each mechanism as an instance of a named practice and extends it in
> the same shape.
>
> **How to use it.** (1) **The house mechanism wins.** When a seed primitive, a studio module or a
> `noctus.*` tool covers a point, use it; this doc explains why it exists. A canon idea with no house
> mechanism is a *proposal to surface* (`noctus.dev.surface_to_tech_lead`), never a licence to hand-roll a
> per-product version (CLAUDE.md §1 seed-first, replication-to-seed). (2) Read the section your slice
> touches, run its checklist; § 12 has the one-page checklists. (3) **Security is composed, not
> duplicated:** threat model, prompt injection, lethal trifecta, red-team ASR and denial of wallet are
> `agents-security`'s, in `KB § PATTERNS/security/ai-agent-security-canon.md`. This doc points there.

Path shorthand: `A:` = `products/agents/backend/app/` · `SW:` = `products/social-wiring/backend/app/` ·
`LLM:` = `seed/lib/backend/noctusai_lib/integrations/llm/` · `DOC:` = `seed/lib/backend/noctusai_lib/integrations/documents/`.

## 0 · Standard term ↔ house term

| Standard term | House mechanism | Where |
|---|---|---|
| Agent definition / system prompt | agent definition + version rows (sections, texts, tools, decisions, specs, skills) compiled by ONE pure function | `A:studio/compiler.py:1-35` |
| Prompt version / prompt registry | `compiled_hash` = sha256 over text AND every content row AND the version settings | `A:studio/compiler.py:458-527` |
| Template variables / tenant context | org specs, `{{org.chave}}` placeholders resolved per org before hashing | `A:studio/compiler.py:31-34`; `KB § INTEGRATIONS/agents-org-specs.md` |
| Progressive disclosure / just-in-time context | `sob_demanda`: skill bodies, skill files, knowledge collections listed, never inlined | `A:studio/compiler.py:23-24` |
| Tool schema (ACI) | strict Pydantic argument models in code; descriptions + parameter labels are DB rows | `A:channels/tool_registry.py:1-20,122-123,243` |
| Agent loop / tool loop | seed `run_tool_loop` (iteration cap), driven per version by `LlmToolRuntime` | `LLM:tool_loop.py:1-17`; `A:runtime/llm_runtime.py:224,354` |
| Model routing (static) | `agent_versions.provider/model/effort` rows under a DB CHECK | `products/agents/backend/migrations/024_llm_provider_runtime.sql:40-46` |
| Vendor switch | `resolve_llm_provider(capability, org_id, allowed, default)` (manual, never failover) | `LLM:provider_choice.py:77-130`; `KB § PATTERNS/backend/llm-provider-selection.md` |
| Measured model routing table | `documents.roteamento` (generated from evidence) + `noctus.dev.roteamento_modelos_recalibrar` | `DOC:roteamento.py:1-17`; `DOC:roteamento_calibracao.py:1-25` |
| Prompt caching | `build_cached_messages` (stable-first + `cache_control` for Anthropic) | `LLM:chat.py:215-272` |
| Usage / cost telemetry | central ledger `public.ai_usage` (attributed, priced at write, append-only) | `KB § PATTERNS/backend/llm-usage.md` §0 |
| Tool-call audit trail | `tool_call_audits` per product | `KB § PATTERNS/backend/llm-tool-audit.md` |
| Spend limits | per-org monthly BRL budget + per-org daily USD cap, pre-turn | `A:runtime/llm_runtime.py:162-194` |
| Output guardrail | conformance rules (`bloquear` ⇒ one corrective re-run, then silence + hand-off) | `A:channels/turno.py:9-12`; `A:channels/conformidade.py:583` |
| Prompt-leak detector | `GuardaVazamento` + canary / honeytoken / per-turn provenance tag | `A:channels/conformidade.py:642`; `A:channels/proveniencia.py:1-14` |
| Production-readiness review | `prontidao` (readiness == publish gate, same predicates) | `A:studio/prontidao.py:1-22` |
| Eval harness | judge suite (`evals.py`) + mechanism suite pass^k (`eval_mecanismo.py`) | `KB § PATTERNS/ai/agent-evals.md` |
| Retrieval (RAG) | agentic, lexical: `kb_buscar` / `kb_ler` over Postgres FTS (`portuguese`) | `products/agents/backend/migrations/013_agent_studio_knowledge_evals.sql:98-120,347,398-403` |
| Agent authoring workflow | skill `noc-new-agent`; generator drafts, a human completes + publishes | `KB § GUIDES/agent-creation.md` |

---

## 1 · Agent architectures — workflows first, agents when earned

**Principle.** Anthropic separates *workflows* ("LLMs and tools are orchestrated through predefined
code paths") from *agents* (LLMs "dynamically direct their own processes and tool usage"). Five
workflow patterns cover most needs: prompt chaining, routing, parallelization (sectioning or voting),
orchestrator-workers, evaluator-optimizer. The recommendation is the simplest solution that works:
agents trade latency and cost for performance and carry compounding-error risk, so they need
sandboxed testing and guardrails. Three principles: simplicity, transparency of planning, a carefully
crafted agent-computer interface (ACI).

**How it applies here.**

| Pattern | House instance |
|---|---|
| Prompt chaining with a gate | the generator: one planning call, then one call per area, each validated against a closed schema + the registries before anything is written (`KB § GUIDES/agent-creation.md` §5-§6) |
| Routing | document reads: doc type ⇒ primary + fallback model (`DOC:roteamento.py:1-17`); the agents runtime: `spec.runtime == "llm"` ⇒ provider-neutral loop, else the Claude Agent SDK runtime (`A:studio/evals.py:599-606`) |
| Parallelization — voting | the document "agreement gate": an independent second read by a different model; a disagreement is reported, never silently overridden (`DOC:providers.py:139-147,166-168`) |
| Parallelization — guardrail as a separate check | conformance rules run on the reply after generation, not inside the prompt (`A:channels/turno.py:9-12`) |
| Evaluator-optimizer | the conformance corrective re-run: a blocked reply is re-run once with the DB correction text, then silence + hand-off (`A:channels/conformidade.py:583`) |
| Orchestrator-workers / supervisor | Maya (supervisor over every block, scores specialists, reports to the owner) over specialist blocks: Julia = SDR/qualification block 1; later negociação, jurídico, financeiro. v1 shipped in social-wiring (`atendimento_blocos`, `supervisao`; memory `project_maya_julia_agent_architecture`) |
| Autonomous agent with tools | Julia: a channel agent on `LlmToolRuntime`, toolset gated server-side (`A:channels/tool_registry.py:12-20`) |

**Design rules that follow.**
- **Blocks behind explicit handoffs.** A later stage's logic never folds into an earlier agent; a new
  stage is a new block with a handoff trigger and its own criteria (owner decision, memory
  `project_maya_julia_agent_architecture`). Julia stays leads-only: operator or privileged tools live
  in a separate operator agent (One Chat), because lead text is attacker-controlled
  (`KB § PATTERNS/security/ai-agent-security-canon.md` §3 lethal trifecta).
- **Deterministic where the requirement is deterministic.** Qualification state, offering limits,
  identity rules and escalations are code (`A:channels/tool_registry.py:12-20`), and the model is asked
  only for what needs language. "Agent" is not a reason to move a rule from code into prose.
- **Bounded loops.** Every loop has a hard iteration cap (`A:runtime/llm_runtime.py:224,354`:
  `min(max_iterations, spec.max_turns)`) and a per-turn refusal/error budget that stops the turn
  (`A:channels/tool_registry.py:12-15`).
- **A new agent definition is for a new behaviour.** A new customer of an existing agent is an
  *instance* + org specs, never a new definition (`KB § GUIDES/agent-creation.md` §2 step 0).

**Checklist.** Could a single call with retrieval + examples do it? Is the step count predictable
(⇒ workflow)? Which block does this belong to, and what is the handoff? Is every loop capped? Which
rules are code and which are prompt?

**Anti-patterns.** Agent-shaped code for a fixed pipeline. A framework that hides the prompt and the
response (Anthropic advises starting with direct API calls). Folding a second stage into Julia.
Privileged tools in a lead-facing agent.

---

## 2 · Prompt engineering — the compiled prompt is a build artifact

**Principle.** Before prompt engineering: success criteria, a way to test against them empirically,
a first draft (Anthropic prompt-engineering overview). Then: be clear and direct ("Think of Claude
as a brilliant but new employee who lacks context on your norms and workflows"); give the *why*
behind instructions; 3-5 relevant, diverse examples wrapped in tags; XML tags to separate
instructions, context, examples and variable input; long documents at the top, the query at the end
(up to 30 percent better on complex multi-document input). Current models over-trigger on aggressive
language: write "Use this tool when…", not "CRITICAL: You MUST use this tool when…". Not every
failing eval is a prompt problem: latency and cost often move more by changing the model.

**How it applies here.**
- **The prompt is data, compiled.** Prompt text never lives in code or git (keeper
  `check_agent_prompt_text_in_code`; memory `feedback_agent_content_db_only`). Sections, system texts,
  tool descriptions, decisions and specs are rows; `compile_prompt` is pure and deterministic and is
  the one composer the runtime, the inspector and publish all call (`A:studio/compiler.py:1-9`).
- **Fixed layout** (`A:studio/compiler.py:10-21`): active sections by `(ordem, chave)` ⇒ `# Skills` ⇒
  `# Base de conhecimento` ⇒ `# Ferramentas` (every family stated on/off — "the model must know a family
  is OFF, not just not see it") ⇒ `# Cliente em foco`. An empty section is skipped *and* reported as
  blocking.
- **Typed decisions, not prose.** A choice with options and exactly one default is a `decisao` row;
  a decision written as prose inside a section is a blocking warning (`decisao_em_secao`,
  `A:studio/compiler.py:121-125`).
- **Every word is a row; a missing required string blocks, never defaults** (`texto_ausente`,
  `A:studio/compiler.py:26-30`). A silent default string is how two orgs end up with different
  agents without anyone deciding it.
- **Lead text is the `user` role, always.** Contact names and similar never enter the system prompt;
  platform lines (attendant, another agent, a thread event) arrive as a separate `system` envelope with
  a per-turn random tag (`A:runtime/llm_runtime.py:18-22`; `A:channels/proveniencia.py:5-8`).
- **Size.** `estimate_tokens = ceil(len/4)` (`A:studio/compiler.py:128-130`); above 12 000 estimated
  tokens the compiler raises the non-blocking `prompt_extenso` (`:76`). Treat it as a context-budget
  signal (§3), not a style warning.

**Checklist (prompt change).** Success criterion named? Eval case exists that would fail without the
change? Change made in rows (Studio or `noctus.agents.content`, dry-run first), never in code? New
hash ⇒ judge + mechanism suites re-run on it (`KB § PATTERNS/ai/agent-evals.md` §6)? No shouting
language added? `prontidao` green?

**Anti-patterns.** A prompt string in a Python file. A fix that adds "NEVER do X" without an eval case
that shows X. Editing production behaviour without moving the hash. Examples copied from one real
lead's conversation (PII + overfitting; fixtures are synthetic, `A:studio/eval_pii.py:1-9`).

---

## 3 · Context engineering — the smallest set of high-signal tokens

**Principle.** Context engineering asks "what configuration of context is most likely to generate our
model's desired behavior?" across the whole token state, not only the prompt. Recall degrades as
context grows ("context rot"), so context is an attention budget: find "the smallest set of
high-signal tokens that maximize the likelihood of your desired outcome." System prompts sit at the
"right altitude" between brittle hard-coded logic and vague guidance. Prefer just-in-time retrieval
(lightweight references, loaded by tools) over pre-loading; hybrid often works best. Long-horizon
techniques: compaction, structured note-taking, sub-agents with clean windows returning condensed
summaries.

**How it applies here.**
- **Just-in-time by construction.** Skill bodies, skill files and knowledge collections are listed in
  `sob_demanda`, never in the prompt text (`A:studio/compiler.py:23-24`); the model opens a skill with
  `abrir_skill` and reads knowledge with `kb_buscar` / `kb_ler` (`A:studio/compiler.py:108-116`).
  A required skill is gated: the tool refuses until the skill was opened under the current hash
  (`A:channels/tool_registry.py:17-18`).
- **Memory without an SDK session.** `LlmToolRuntime` sends the compiled prompt + the last N stored
  messages + the new prompt (`A:runtime/llm_runtime.py:18-22`). Durable facts about the lead live as
  structured records on the shared lead (qualification criteria), so later blocks never re-ask
  (memory `project_maya_julia_agent_architecture`). That is structured note-taking in the canon's sense.
- **Tenant data enters as data.** Org specs are substituted into placeholders at compile time for that
  org; a lead's words never become a system rule (`KB § GUIDES/agent-creation.md` §6). Tenant-spec
  injection is a security finding class (`KB § PATTERNS/security/ai-agent-security-canon.md` §15 WE-2).
- **Our own dev harness is the same discipline.** L1 agent files are lean indexes and depth is pulled
  on demand (`KB § PATTERNS/common/agent-context-architecture.md`). Subagents return condensed reports.

**Checklist.** Does every block of the compiled prompt earn its tokens? Could this content be a
just-in-time tool read instead? Is anything per-request placed before stable content (breaks caching,
§7)? Is tenant- or lead-supplied text kept out of the system role?

**Anti-patterns.** Inlining a whole knowledge collection "to be safe". Putting the lead's name or the
date in the system prompt. Growing the history window instead of recording structured state.

---

## 4 · Tool design for agents (the ACI)

**Principle (Anthropic, "Writing effective tools for agents" + "Building effective agents").** Few,
targeted tools for high-impact workflows ("More tools don't always lead to better outcomes"), each
with "a clear, distinct purpose"; consolidate multi-step operations; namespace related tools; return
high-signal fields (names over UUIDs) and offer a concise vs detailed response format; paginate,
filter and truncate with sensible defaults (Claude Code caps tool responses at 25 000 tokens);
actionable errors instead of opaque codes; write descriptions as for a new hire, unambiguous
parameter names; poka-yoke the arguments ("Change the arguments so that it is harder to make
mistakes"); evaluate tools with realistic multi-step tasks and read the transcripts.

**How it applies here.**
- **Schemas in code, words in rows.** `TOOLS` maps a tool name to a strict argument model; the JSON
  schema the provider sees is derived from it with no description; descriptions, parameter labels and
  enum labels are rows of `agent_version_ferramentas`. A tool whose row is missing is not offered
  (`A:channels/tool_registry.py:3-7`).
- **Strict arguments.** `_Args` is `extra="forbid", strict=True` (`A:channels/tool_registry.py:122-123`):
  the model's invented field is a refusal, not a silently ignored key.
- **Poka-yoke on identity.** "The model never names an org or a lead." Every id a handler uses comes
  from the server-built turn object (`A:channels/tool_registry.py:9-10`). That removes a whole class of
  cross-tenant tool calls by construction.
- **Typed refusals with DB wording.** A refused call returns a `codigo` whose wording is the row
  `ferramenta.resultado.recusa.<codigo>`; refusals and errors are budgeted per turn and past the budget
  the toolset stops the turn (`A:channels/tool_registry.py:12-15`).
- **Derive, never re-type, a tool argument name.** The mechanism suite reads `abrir_skill`'s argument
  from the strict model itself (`A:studio/eval_mecanismo.py:106-110`), so an eval cannot drift from the
  schema the model is given.
- **Closed registry.** Tool names and text keys outside the code registries are generator gaps
  (`ferramenta_desconhecida`), never invented (`KB § GUIDES/agent-creation.md` §5).
- **Audit + meter every dispatch.** `tool_call_audits` per product (`KB § PATTERNS/backend/llm-tool-audit.md`)
  and the central usage ledger (`KB § PATTERNS/backend/llm-usage.md` §0).

**Checklist (new tool).** One clear purpose, not an endpoint wrapper? Strict model, `extra="forbid"`?
No org/lead id in the arguments? Description + every parameter labelled as a row (readiness flags
`ferramenta_sem_descricao` / `rotulo_parametro_ausente`)? Response bounded (limit, truncation) and
high-signal? Refusal codes typed with DB wording? Added to the per-turn budget? A mechanism case
asserting it is called (`ferramentas_incluem`) and not called (`ferramentas_proibidas`) when it must
not be (`A:studio/eval_mecanismo.py:74-97`)? Threat-model the new capability with `agents-security`
(§11).

**Anti-patterns.** A tool description in code. A free-form `org_id` parameter. A tool returning raw
UUIDs the model then has to echo. An unbounded list result. A tool added without a mechanism case.

---

## 5 · Structured outputs and validation

**Principle.** Anthropic structured outputs constrain decoding to a JSON schema
(`output_config.format` with `type: "json_schema"`) and `strict: true` tools validate tool inputs:
"Always valid… Type safe… No retries needed for schema violations." The guarantee has named
exceptions: a refusal (`stop_reason: "refusal"`), a truncated reply (`max_tokens`), and enum casing.
Unsupported schema features (numeric/string length constraints, recursive schemas,
`additionalProperties` other than `false`, …) return 400; there are complexity limits (20 strict
tools, 24 optional parameters, 16 union parameters per request).

**How it applies here.**
- **The judge's contract is a strict parse, server-side.** `parse_judge_output` requires one entry per
  criterion, in order, each with an integer `n == position` and a boolean `ok`; `criterio`/`tipo` are
  attached from OUR list, never from the model (`A:studio/evals.py:257-289`). The call itself asks for
  `response_format={"type": "json_object"}` (`:343`), which guarantees JSON, not this shape.
- **Model output is data; the server decides.** The judge never decides pass/fail; the runner computes
  pass and score from the booleans (`A:studio/evals.py:14-18,292-300`). The generator's output is
  validated against a closed schema + registries before any write (`KB § GUIDES/agent-creation.md` §6).
- **Fail loudly on a malformed reply.** A judge reply that is not the strict shape raises `JudgeError`
  and the case becomes `erro` (counted as failed, never skipped) (`A:studio/evals.py:22-23,189-191`).

**Canon ⇒ house gap (proposal, not built).** The judge and other strict-JSON reads could use
Anthropic `json_schema` structured outputs through the seed provider instead of `json_object` + a
hand parser. Keep the server-side checks either way (alignment `n`, our own labels): constrained
decoding guarantees the schema, not the semantics, and refusal/`max_tokens` still escape it. Seed-level
change ⇒ surface to the tech-lead; do not hand-roll it in one product.

**Checklist.** Is every LLM output that drives code parsed against a closed shape? Are labels the
server already knows attached server-side? Are refusal and truncation handled as results? Is enum
comparison case-insensitive?

**Anti-patterns.** `json.loads` then trusting whatever keys came back. Asking the model to echo data
the server owns (the 2026-09-21 mislabel, § 13 WE-2). Treating a parse failure as a pass or a skip.

---

## 6 · Model routing, cost and caching

**Principle.** Pick the smallest model that meets the success criteria on *your* distribution,
measured, and spend more only where the measurement says so. Anthropic's current lineup: Opus 5.5
(`claude-opus-5-5`, $4/$20 per MTok in/out, the default start "for most workloads"), Sonnet 5.5
(`claude-sonnet-5-5`, $2/$10, speed + intelligence), Haiku 5.5 (`claude-haiku-5-5`, from $0.10/$0.50,
classification, extraction, routing), Fable 5.1 (`claude-fable-5-1`, $10/$50, demanding reasoning).
Batch API: 50% off, results within 24 h (most within 1 h), up to 100 000 requests or 256 MB per batch,
results kept 29 days, not ZDR-eligible. Prompt-cache reads cost 10% of base input (5% on Opus 5.5 /
Sonnet 5.5).

**How the house routes today (the code is the truth).**
- **Agents: routing is data with a DB CHECK.** `agent_versions.provider/model` must be one of
  `claude-opus-5 | claude-sonnet-5 | claude-haiku-4-5` (anthropic) or `gpt-5.6-sol | -terra | -luna`
  (openai) (`products/agents/backend/migrations/024_llm_provider_runtime.sql:40-46`). The model is part
  of the content hash (`A:studio/compiler.py:467-470`), so **a model swap is a new hash and re-runs
  every eval**.
- **The judge is fixed:** `claude-sonnet-5`, never the generator's choice (`A:studio/evals.py:108-109,316-320`).
- **Eval iteration may run cheaper, never pricier:** `modelo_geracao ∈ {claude-sonnet-5, claude-haiku-4-5}`
  (`A:studio/models.py:128-137`); such a run never satisfies the publish gate (`A:studio/evals.py:55-60`).
- **Vendor per org, manual, never failover:** `resolve_llm_provider` reads `llm_<capability>_provider`
  through org_settings ⇒ platform_settings ⇒ env; a default outside `allowed` is an assertion, an
  unknown saved value logs and uses the default (`LLM:provider_choice.py:77-130`). A silent vendor swap
  changes which model answered with nobody told (`KB § PATTERNS/backend/llm-provider-selection.md`
  § Anti-patterns).
- **A model id is not portable across vendors:** selecting a provider must select its model
  (`DOC:providers.py:14-17`); a mismatched pair 404s and reads like a broken key.
- **Measured routing tables beat global pins.** Document reads route per doc type / field from a table
  *generated* from benchmark + production evidence, moving only on a sufficiently sampled separation
  (`DOC:roteamento.py:1-17`; `DOC:roteamento_calibracao.py:1-25`). § 13 WE-3 is the full story.
- **Escalate only what failed.** A stronger model re-reads only documents that already triggered a
  re-read (`DOC:providers.py:127-147`).

**Recommending tiers (canon, for new work).** Classification / routing / extraction / short replies ⇒
start at `claude-haiku-5-5`; conversational agents with tools ⇒ `claude-sonnet-5-5`; hard
reasoning, generators, judges of complex behaviour ⇒ `claude-opus-5-5`; escalate further only on
evidence. In this house a *new* id means: a pricing-catalog entry in `LLM:models.py` (already present
for `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-opus-5-5`, `claude-fable-5-1`), a migration
widening `agent_versions_model_check` and (for eval iteration) `EVAL_RUN_MODEL_ALLOWLIST` + its
migration CHECK, then the § 12 model-swap checklist. Never pin a dated id beside its alias: a second,
unpriced spelling of the same model (`DOC:providers.py:56-60`).

**Prompt caching.** The cache key is the exact prefix in order `tools ⇒ system ⇒ messages`; a change
at a level invalidates it and everything after; default TTL 5 min (1 h at 2× write cost); writes cost
1.25×, reads 0.1× base (0.05× on Opus 5.5 / Sonnet 5.5). Minimum cacheable prefix depends on the model:
512 tokens (Opus 5.5, Sonnet 5.5, Haiku 5.5), 1 024 (Sonnet 5), **4 096 (Haiku 4.5)**; shorter prefixes
are silently not cached. House helper: `build_cached_messages` puts stable content first and marks
the system message `cache_control: ephemeral` for Anthropic (`LLM:chat.py:215-272`).
- **Gap to surface:** the helper warns below ~1 024 tokens (`LLM:chat.py:26-30`), which is wrong in
  both directions now: Haiku 4.5 needs 4 096, the 5.5 family only 512. A per-model threshold belongs in
  the seed (proposal).
- Usage accounting: Anthropic's `input_tokens` *excludes* cached tokens; total input =
  `input_tokens + cache_read + cache_creation`. The judge cost leg does not surface cache reads today
  (`A:studio/evals.py:310-313`).

**Cost controls that exist (use them).** Per-org monthly BRL budget + daily USD cap before every turn
(`A:runtime/llm_runtime.py:162-194`); concurrency limiter (`:138-159`); per-run eval cap (default
US$ 2, max 50; `A:config.py:256`, `A:studio/models.py:138-145`); generator run cap ≤ US$ 5 with a
worst-case pre-call estimate (`KB § GUIDES/agent-creation.md` §5). Monthly budget is fail-open by seed
design when the read fails; the Redis-down spend case is `agents-security`'s (§11; PROJECT §6 item 8).

**Checklist.** Measured on the real distribution (not only synthetic)? Run-to-run variance measured
(≥3 runs)? Cost per unit reported in US$? Cheapest model that meets the bar? Stable prefix ≥ the
model's cache minimum? Cap in place before the first live call?

**Anti-patterns.** "Upgrade to the bigger model" without a failing eval. Auto-failover between vendors.
A model id hard-coded beside the routing table. A cost claim with no ledger number.

---

## 7 · Retrieval, memory and knowledge (RAG)

**Principle.** Retrieval-augmented generation (Lewis et al., 2020) pairs a model's parametric memory
with an external, non-parametric memory accessed by a retriever, which helps with provenance and with
updating knowledge without retraining. The agentic variant lets the model decide when to retrieve
(just-in-time, § 3). Measure retrieval separately from generation: a wrong answer from a missing
document is a retrieval bug.

**How it applies here.**
- **Agentic lexical retrieval.** Agent knowledge is Postgres full-text search with the `portuguese`
  config, weighted title (A) / resumo (B) / conteudo (C), queried with `websearch_to_tsquery` and
  ranked by `ts_rank` (`products/agents/backend/migrations/013_agent_studio_knowledge_evals.sql:98-120,347,398-403`).
  The model calls `kb_buscar` then `kb_ler`, and the studio search route is "the SAME function
  `kb_buscar` calls" (`A:routers/studio_knowledge_router.py:357-379`), so what a human tests is what the
  model gets.
- **Citations.** The knowledge intro tells the model to cite the collection tag (`[AU]`) when it uses a
  document (`A:studio/compiler.py:113-116`); an eval criterion can check it.
- **Embeddings exist elsewhere** (`generate_embeddings_batch`; pgvector `vector(1536)` consumers), but
  Anthropic has no embeddings endpoint: never offer `"anthropic"` for capability `embedding`
  (`KB § PATTERNS/backend/llm-provider-selection.md` § Anti-patterns). A dead embedding provider must
  never read as "no results" (same doc, Deliverable C.5).
- **Structured memory over transcripts.** Qualification facts are records on the shared lead; later
  blocks read them instead of re-asking (§ 3).
- Retrieval poisoning, vector-store isolation and memory injection are `agents-security`'s
  (`KB § PATTERNS/security/ai-agent-security-canon.md` §8).

**Checklist.** Does an eval case cover "answer only from the knowledge base" and "say you don't know"?
Does the search route return the expected document for each golden question (retrieval-only check)?
Is the knowledge source per-agent and per-org scoped? Are embeddings routed to a vendor that has them?

**Anti-patterns.** Pre-loading every document into the prompt. Adding a vector store before lexical
search was measured and found short. Swallowing a retrieval exception into an empty list.

---

## 8 · LLM observability

**Principle.** Log every LLM interaction as a searchable trace and look at the data constantly
(Husain: "You must remove all friction from the process of looking at data"). The OpenTelemetry GenAI
semantic conventions (status: Development) name the fields: span `{gen_ai.operation.name}
{gen_ai.request.model}`, `gen_ai.provider.name` (`"anthropic"`), `gen_ai.request.model` /
`gen_ai.response.model`, `gen_ai.usage.input_tokens` / `output_tokens` /
`cache_read.input_tokens` / `cache_write.input_tokens`, `gen_ai.response.finish_reasons`,
`gen_ai.conversation.id`; agent spans `invoke_agent {gen_ai.agent.name}` and `execute_tool`; metrics
such as `gen_ai.client.operation.duration`.

**House mapping (no OTel exporter today; the ledger is the analog).**

| OTel GenAI field | House field |
|---|---|
| operation / feature | `ai_usage.feature` = `"METHOD /route/template"` or `llm_usage_context(feature=…)` |
| provider / model | `ai_usage` provider + model, priced with `price_version` (`unpriced` flagged, never free) |
| usage tokens | prompt/completion tokens per row; eval rows add `tokens_cache_leitura` |
| conversation id / agent | `llm_usage_context(agent_key=, conversation_id=)` |
| error / finish | `status ∈ {ok, error, partial}`; streams cut short are `partial` with estimated tokens |
| request correlation | `request_id` = the correlation id |
| tool span | `tool_call_audits` row (status, tool, args redacted per LGPD) |

Sources: `KB § PATTERNS/backend/llm-usage.md` §0 (central ledger, attribution, pricing, append-only
proven by `verify_db_guards`), `KB § PATTERNS/backend/llm-tool-audit.md`. Eval runs record cost and
tokens per case and per run (`A:studio/evals.py:29-44`).

**Rules.** Every LLM call goes through the seed entry points (the sink is installed by
`create_product_app`), so attribution is by construction. Wrap agent work in
`llm_usage_context(agent_key=…, conversation_id=…, purpose=…)` so a cost question has an answer. Never
log prompt or reply text where a count is enough (LGPD; platform prompts are IP). If OTel export is
ever added, emit the GenAI attribute names above from the ledger write path: one seed change, not
per product.

**Checklist.** Can you answer "what did this agent cost per conversation this week" from `ai_usage`?
Is every call attributed (feature, org, agent)? Is a provider failure a row with `status=error`?

**Anti-patterns.** A product-local cost counter. `print`-debugging prompts into logs. A trace that
stores the lead's message verbatim.

---

## 9 · Failure modes and mitigations

| Failure | What it looks like | Mitigation (house mechanism first) |
|---|---|---|
| Hallucinated fact | invented property, price, document field | answer only from tools / knowledge (§ 7); a mechanism assert on what was offered (`ofertas_por_lote`); for documents, an independent second read + disagreement reported (`DOC:providers.py:139-147`); a real-document benchmark (§ 13 WE-3) |
| Hallucinated tool argument | an id or field the server never gave | ids come from the server-built turn, `extra="forbid"` models (`A:channels/tool_registry.py:9-10,122-123`) |
| Refusal | `stop_reason: "refusal"`; empty reply | treat as a result; the runner marks "no answer" `erro` (`A:studio/evals.py:655-656`); the channel's safe stop + hand-off |
| Truncation | `max_tokens` cut, invalid JSON | size `max_tokens` to the output; a parse failure is `erro`. Real case: Sonnet hit the 4 096-token cap on a Guia de ITBI (`DOC:providers.py:72-74`) |
| Tool loop / runaway turn | repeated tool calls, cost spike | iteration cap (`A:runtime/llm_runtime.py:224,354`), per-turn refusal/error budget ⇒ stop (`A:channels/tool_registry.py:12-15`), per-turn timeout in evals (`A:studio/evals.py:635,651-652`), daily cap (`A:runtime/llm_runtime.py:184-192`) |
| Policy violation in reply | forbidden claim, external link, PII | conformance `bloquear` ⇒ one corrective re-run ⇒ silence + hand-off (`A:channels/conformidade.py:583`); asserts `sem_links_externos`, `sem_pii` |
| Prompt leak | reply reproduces the compiled prompt | `GuardaVazamento` + canary + honeytoken (`A:channels/conformidade.py:642`; `A:channels/proveniencia.py:9-13`); eval outputs filtered for non-admins (`A:studio/evals.py:657-661`; `A:studio/vazamento.py:16-28`) |
| Drift: spec changed after eval | gate judged one body, shipped another | content hash covers text + rows + settings + skill bodies (`A:studio/compiler.py:458-511`); every gate checks the current hash |
| Drift: model/provider behaviour change | same prompt, new failures | model is in the hash; re-run suites on any model change; red-team cadence on provider change (`KB § PATTERNS/security/ai-agent-security-canon.md` §9) |
| Run-to-run variance | passes once, fails in prod | pass^k on mechanism cases (`A:studio/eval_mecanismo.py:504-506`); ≥3 runs in benchmarks |
| Silent provider death | empty results read as "nothing found" | named `missing_credentials` / `status=error` rows; never `except: return []` (`KB § PATTERNS/backend/llm-provider-selection.md` C.5) |
| Orphaned async work | a run stuck `executando` after restart | `sweep_orphaned_runs` at startup (`A:studio/evals.py:665-679`) |

"Julia behaves wrong" triage order: reproduce as an eval case (synthetic) ⇒ is it retrieval, tool,
conformance, prompt, or model? (read the transcript: tool calls, refusals, conformance events) ⇒ fix
at that layer ⇒ the case now passes on the new hash ⇒ no regression in the rest of the suite.

---

## 10 · Production readiness — `prontidao` is the review

**Principle.** A production-readiness review lists everything a service owes before launch, and it
must not be a parallel opinion: the checklist and the gate are the same predicate.

**How it applies here.** `prontidao.compor` is pure; `coletar` does the reads
(`A:studio/prontidao.py:4-7`). `pronto_para_publicar` is true iff `POST .../draft/publish` would not
refuse, except a concurrent edit and the human judge-suite override (`:9-11`). The route and the
module call the SAME predicates (`recusa_de_compilacao`, `juiz_aprovado`/`juiz_motivo`,
`decidir_portao`; `:63-100`). Every blocking item names a refusal code from the closed set
`RECUSAS_PUBLICACAO` (`:55-57`), and `compor` raises on a blocking item without a refusal or an
advisory item with one (`:460-467`). A test publishes a draft in each state and checks the refusal
matches the item (`KB § GUIDES/agent-creation.md` §3, `tests/studio/def/test_prontidao.py`).

The four gates in order: qualification standard published/pinned ⇒ compiles with no blocking warning ⇒
(channel agent) mechanism suite LIVE, complete, under budget, pass^k on the current hash ⇒ judge run
complete on the current hash, score ≥ `publicacao_limiar` (human override allowed only here)
(`KB § GUIDES/agent-creation.md` §3). Publish is always a human act; a new channel agent starts
`desligado`.

**Rule for anyone adding a gate:** a new publish refusal ships with its readiness item and its entry in
`RECUSAS_PUBLICACAO` in the same commit (CLAUDE.md §1 gate↔methodology sync).

---

## 11 · Hand-off to `agents-security` (compose, never duplicate)

`ai-engineer` builds and measures; `agents-security` threat-models and attacks. Call it (advisor,
read-only) when a slice:
- adds or widens a tool, especially one with side effects or reaching outside the org (trifecta legs,
  canon §3);
- adds a new channel or an anonymous surface (`public_ask`), or changes provenance envelopes;
- changes conformance rules, the leak guard, the budget guard, BYOK or credential resolution;
- adds retrieval sources or memory that crosses conversations (§8 there);
- changes the model or provider of a public agent (red-team cadence, canon §9 there).

What you bring: the compiled-hash, the tool list with schemas, the trifecta table of the agent, the
mechanism + judge results. What you get: ranked findings + proof tests. Security proof tests land as
eval cases tagged `seguranca` and their ASR is reported per content hash
(`KB § PATTERNS/security/ai-agent-security-canon.md` §9; `KB § PATTERNS/ai/agent-evals.md` §8).
OWASP LLM Top 10 (2025) is the shared vocabulary: LLM01 Prompt Injection … LLM10 Unbounded Consumption.

---

## 12 · One-page checklists

**New agent** (skill `noc-new-agent`; `KB § GUIDES/agent-creation.md`)
1. New behaviour, or an instance + org specs of an existing agent?
2. Which block, which handoff in and out (§ 1)? Leads-only vs operator tools?
3. `criar_agente` ⇒ `gerar` with `referencia: "julia"` (exemplar) under a cost cap ⇒ fix every `lacuna`.
4. Human-only artifacts: qualification standard, library skills, spec values, mechanism cases,
   conformance rules, controls.
5. Success criteria written before cases (`KB § PATTERNS/ai/agent-evals.md` §1); behaviour cases
   reviewed; mechanism cases for a channel agent.
6. `prontidao` ⇒ fix blockers, justify each advisory.
7. Cheap iteration (Haiku `modelo_geracao`, failures-only, cap) ⇒ one full run on the version's model.
8. `agents-security` review (§ 11) ⇒ human publish ⇒ controls `ligado` deliberately.

**Prompt change**
1. Failing (or new) eval case first; record the current hash and its scores.
2. Edit rows (dry-run, then `confirm`), never code; read the compiled diff.
3. New hash ⇒ judge suite + mechanism suite on it (iterate cheap, finish on the version model).
4. Compare per case vs the previous hash: no case that passed may now fail without a written reason.
5. Report the US$ spent.

**New tool**: § 4 checklist + a mechanism case + `agents-security` review + readiness green.

**Model swap**
1. Hypothesis + metric (quality, cost per conversation, latency) written first.
2. Pricing catalog has the id; migration widens the CHECK; no dated duplicate of an alias.
3. Run the full judge + mechanism suites on the new hash (model is in the hash); ≥3 runs where variance
   matters; compare with the old model's numbers on the same cases.
4. Cost per case from the eval run's `custo_usd`, not list prices.
5. Red-team starter set re-run (provider/model change is a cadence trigger).
6. Decide on evidence; record the table where the pin lives (the `DOC:providers.py` docstring shape).

**New LLM feature outside the agents product**: seed entry points only (`chat_completion*`,
`run_tool_loop`); `resolve_llm_provider` if the vendor must be switchable; `llm_usage_context`;
strict parse of outputs; an eval set (even 20 cases) before shipping; a cost cap.

---

## 13 · Worked examples (grounded)

### WE-1 — Julia's readiness view is the publish gate

*Problem.* Authors kept discovering missing pieces one 409 at a time, and a separate "readiness"
opinion would drift from the gate. *House answer* (`A:studio/prontidao.py`). The pure `compor(e)`
builds items from a snapshot; blocking items carry the refusal code they stand for and `compor`
raises if a blocking item names no refusal (`:460-467`). `_avaliacao` turns the judge result into one
item per reason (`sem_execucao`, `hash_diferente`, `incompleta`, `abaixo_do_limiar`) and the mechanism
gate into `mecanismo_<codigo>` via the same `decidir_portao` the route calls (`:321-376`). When the
agent requires the mechanism suite and the judge suite is not blocking, judge items degrade to
advisories (`:323-326`). *Canon.* A production-readiness review that is the gate itself (§ 10),
gate↔methodology sync. *Lesson for new gates:* add the predicate once, call it from both sides, test
each state.

### WE-2 — a prompt change shipped behind an eval regression

*Incident (2026-09-21/22).* The judge prompt asked the model to echo each criterion's `tipo`; it
mislabelled a `nao_deve` criterion and 2 of 32 live IsaIA cases erred. *Fix* (commit `bab6525f0`):
the judge returns `{n, ok, motivo}`, `n` must equal the position, and `criterio`/`tipo` come from our
list (`A:studio/evals.py:257-289`, docstring `:261-263`), with tests in
`tests/studio/rt/test_evals_runner.py`. *Second instance (2026-10-20, commit `9d565cba5`).* Skill bodies
are on-demand, so a skill edit did not move the hash: "the gate could judge one body and ship
another". `_skills_hash` now puts every skill body and file sha256 into the hash
(`A:studio/compiler.py:500-511`), and the skill PATCH got a compare-and-set. *Canon.* Prompt versions
are content-addressed; a regression gate is only as good as the identity of what it judged (§ 2, § 9
drift row). *Lesson:* anything the model reads at runtime must be inside the hash, or the eval is
about a different artifact.

### WE-3 — a model-routing cost cut, and its reversal on real data

*Step 1 (2026-09-22).* OpenAI credit ran out; document reads moved to Claude. On 11 synthetic scans,
Haiku 4.5 matched Opus 5 on every field (42/42) at US$ 0.034 vs 0.398 OCR cost (~1/11th), so Haiku was
pinned on both rungs (`DOC:providers.py:36-60`). *Step 2 (2026-09-27/28).* A real closed deal showed
Haiku stable on most documents but variable run to run, and Sonnet 5 escalation was added only for
reads that already failed a check (`DOC:providers.py:62-83,127-147`). *Step 3 (2026-10-13).* A real
benchmark (27 documents, 15 deals, 6 models × 3 runs, scored against signed-contract answer keys)
reversed the pin: Haiku 4.5 75.1% fields with 30% run-to-run consistency vs Sonnet 5 98.9% at
US$ 0.018/doc (`DOC:providers.py:149-177`). Sonnet 5 became the first read, Opus 5.5 the independent
second read (most consistent; Fable excluded for data retention), and identity reads now route from a
generated per-type table with a recalibration tool (`DOC:roteamento.py:1-17`;
`DOC:roteamento_calibracao.py:1-25`). *Canon.* Choose the smallest model that meets the bar **on
your real distribution**, measure variance, escalate only failures, keep the evidence beside the pin.
*Lesson:* a synthetic single-run benchmark is a capability smoke test, not a routing decision.

---

## 14 · Anti-patterns (summary)

Prompt text in code · a fix with no eval case · a change that does not move the hash · a judge that
decides pass/fail · asking the model to echo server-known labels · unbounded tool loops · a model swap
"because it is better" · auto-failover between vendors · pinning on a synthetic one-run benchmark ·
a cost claim without a ledger number · inlining knowledge instead of just-in-time retrieval · folding
a later stage into Julia · privileged tools in a lead-facing agent · re-implementing a security
control instead of consulting `agents-security`.

## Sources

- Anthropic — Building effective agents — https://www.anthropic.com/engineering/building-effective-agents — workflows vs agents, five patterns, simplicity, ACI, poka-yoke (§ 1, § 4). Accessed 2026-11-05.
- Anthropic — Writing effective tools for agents — https://www.anthropic.com/engineering/writing-tools-for-agents — few targeted tools, namespacing, meaningful context, 25 000-token cap, descriptions, tool evals (§ 4). Accessed 2026-11-05.
- Anthropic — Effective context engineering for AI agents — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents — attention budget, right altitude, just-in-time retrieval, compaction, notes, sub-agents (§ 3). Accessed 2026-11-05.
- Anthropic — Prompt engineering overview — https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview — prerequisites, "not every failing eval is a prompt problem" (§ 2). Accessed 2026-11-05.
- Anthropic — Prompting best practices — https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices — clear/direct, context, 3-5 examples, XML tags, long-context order, soften aggressive language (§ 2). Accessed 2026-11-05.
- Anthropic — Prompt caching — https://platform.claude.com/docs/en/build-with-claude/prompt-caching — prefix order, breakpoints, TTL, multipliers, per-model minimums, invalidation, usage fields (§ 6). Accessed 2026-11-05.
- Anthropic — Structured outputs — https://platform.claude.com/docs/en/build-with-claude/structured-outputs — `output_config.format`, strict tools, guarantee + exceptions, limits (§ 5). Accessed 2026-11-05.
- Anthropic — Tool use overview — https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview — client vs server tools, the loop, `tool_choice`, strict tool use, tool token overhead (§ 4). Accessed 2026-11-05.
- Anthropic — Models overview — https://platform.claude.com/docs/en/about-claude/models/overview — current ids, prices, "start with Opus 5.5", cache-read discounts (§ 6). Accessed 2026-11-05.
- Anthropic — Batch processing — https://platform.claude.com/docs/en/build-with-claude/batch-processing — 50% off, 100 000 requests / 256 MB, 24 h, 29-day results, not ZDR (§ 6). Accessed 2026-11-05.
- Lewis et al. — Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks (NeurIPS 2020) — https://arxiv.org/abs/2005.11401 — parametric + non-parametric memory, provenance, updating knowledge (§ 7). Accessed 2026-11-05.
- Hamel Husain — Your AI Product Needs Evals (2024-03-29) — https://hamel.dev/blog/posts/evals/ — look at your data, log traces (§ 8). Accessed 2026-11-05.
- OpenTelemetry — GenAI semantic conventions (moved repo, status Development) — https://github.com/open-telemetry/semantic-conventions-genai — upstream pages docs/gen-ai/anthropic.md, gen-ai-agent-spans.md, gen-ai-metrics.md in that repo (§ 8). Accessed 2026-11-05. (The old `opentelemetry.io/docs/specs/semconv/gen-ai/` pages now only point here.)
- OWASP — Top 10 for LLM Applications 2025 — https://genai.owasp.org/llm-top-10/ — LLM01-LLM10 names (§ 11, pointer only). Accessed 2026-11-05.

## Composes-with

`KB § PATTERNS/ai/agent-evals.md` (eval discipline) · `KB § PATTERNS/security/ai-agent-security-canon.md`
(agents-security) · `KB § GUIDES/agent-creation.md` + skill `noc-new-agent` · `KB § PATTERNS/backend/llm-usage.md` ·
`KB § PATTERNS/backend/llm-provider-selection.md` · `KB § PATTERNS/backend/llm-tool-audit.md` ·
`KB § PATTERNS/backend/document-extraction-learnings.md` · `KB § PATTERNS/backend/backend-craft-canon.md` §9.
