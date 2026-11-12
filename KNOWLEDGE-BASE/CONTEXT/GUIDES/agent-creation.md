# GUIDE — creating a complete agent (the Julia recipe)

> **When you need this.** You are about to create an agent in the agents product (Studio, MCP `noctus.agents.content`, or the
> new-agent wizard) and you want it to come out **complete** — not a shell that publishes by luck. Julia (the real-estate
> SDR) is the reference: she has every artifact a production agent needs. This guide lists the artifacts, where Julia's
> live, the order to build a new agent, what each publish gate checks, how the AI generator helps (and what it never
> does), and the one call that tells you what is still missing: `GET /api/studio/agents/{key}/prontidao`.
>
> Owner directive 2026-11-03: *"document this complete-agent creation process and update our code, so future agents get
> built properly and mostly complete. We'll use Julia as the reference for filling and AI generation."* The skill
> `noc-new-agent` is the short procedure; this is the depth.

An agent's **definition is data** (migrations 031/049): rows in the agents database, owned by the platform org
(`definition_scope='plataforma'`), edited only by platform admins (Studio UI) or by the `studio:content-write` token of
`noctus.agents.content`. No prompt text and no agent key lives in code (`KB § PATTERNS/compliance/` keeper
`check_agent_prompt_text_in_code`). What lives in code is only what must: tool **schemas** (`app/channels/tool_registry.py`),
the closed registries of tool names and text keys (`app/studio/ferramentas_registry.py`, `app/studio/textos_registry.py`),
and the gates.

---

## 1 · The artifacts of a complete agent — and where Julia's live

| # | Artifact | What it is | Julia's | Authored by |
|---|---|---|---|---|
| 1 | **Platform definition** | the row: `key`, `nome`, `runtime`, `owner_product`, `escopo_qualificacao`, `padrao_qualificacao`, `rascunho_padrao`, `instanciavel`, `papel` | `julia` (`owner_product=social-wiring`, `padrao_qualificacao=imob-lead`) — `GET /api/studio/plataforma/agents/julia` | human / `criar_agente` |
| 2 | **Prompt sections** | the persona and rules, in order (`secoes`) | `GET /api/studio/agents/julia/draft` → `secoes` | AI first draft → human |
| 3 | **System texts** (`textos`) | every compiler/runtime string as a row, keyed by the registry (`textos_registry.py`); required ones block publish | `.../versions/{id}/textos` | AI (registry-aware) → human |
| 4 | **Tool descriptions** (`ferramentas`) | per tool: description + **parameter labels** (`parametros`) + `obrigatoria_skill`; the schema is in code, the words are rows | `.../versions/{id}/ferramentas`; schemas `app/channels/tool_registry.py` | AI → human |
| 5 | **Decisions** (`decisoes`) | typed choices with options and exactly one default (never prose in a section) | `.../versions/{id}/decisoes` | AI → human |
| 6 | **Org spec declarations** (`specs`) | the `{{org.chave}}` placeholders each org fills | `.../versions/{id}/specs` | AI (declares) → **orgs fill values** |
| 7 | **Library skills + pins** | shared, versioned skills (`/api/skills-biblioteca`); the agent pins versions and gates tools with `obrigatoria_para` | `GET .../draft/skills-biblioteca` | human (library) / AI (chooses pins) |
| 8 | **Qualification standard** | versioned criteria/stages/params (`/api/qualificacao`), pinned per agent version | `imob-lead` | **human only** |
| 9 | **Behaviour eval cases** (`suite=comportamento`) | judge cases with `deve`/`nao_deve` criteria, synthetic fixtures | `GET .../evals/cases` (Julia's 19 cases at the time of writing) | AI first draft (area `evals`) → human |
| 10 | **Mechanism eval cases** (`suite=mecanismo`) | scripted multi-turn cases with deterministic asserts, pass^k, LIVE model — the publish gate for a channel agent | `noctus.agents.content kind=evals_mecanismo` | **human only** |
| 11 | **Conformance rules** | reply filters/limits as data (`conformidade_*`, `canal_limites`) | `kind=conformidade_regras` | human only |
| 12 | **Controls** | `ligado` / `drenando` / `desligado` per agent; a new agent starts `desligado` | `PUT /api/studio/agents/julia/controle` | human only |
| 13 | **Settings** | provider, model, effort, `max_turns`, `idioma`, `tool_policy` | `rascunho_padrao` + the draft | AI proposes → human |

Read Julia as the model: `noctus.agents.content action=get kind=<secao|texto|ferramenta|decisao|spec|skill_ref|evals_mecanismo>
agent=julia` (needs the content token; output is platform IP — **never paste it into git**). Because a generated draft is
shaped by the exemplar's *structure*, marking Julia as an **exemplar** (§4) is what makes "like Julia" mean something.

---

## 2 · The recipe, step by step

0. **Decide it is a new agent.** A new customer org of an existing agent is **not** a new agent — it is an *instance* + org specs
   (`definition_scope='instancia'`). A new definition is for a new behaviour.
1. **Create the definition** — `noctus.agents.content action=criar_agente agent=<key>` (payload: `nome`, `runtime`,
   `owner_product`, `escopo_qualificacao`/`padrao_qualificacao` if it qualifies leads, `rascunho_padrao`, `instanciavel`). An
   empty shell with an empty draft; idempotent. Or the wizard `/agentes/novo`.
2. **Generate the first draft with Julia as the reference** — `action=gerar` with `payload_path = {briefing, referencia:
   "julia", areas?, limite_usd?}` (UI: the briefing form). `referencia` must be an agent a platform admin marked
   **exemplar** (`PUT /api/studio/plataforma/agentes/julia/exemplar {"exemplar": true}`); without it the generator imitates
   *every* exemplar. The run fills `secoes`, `textos`, `ferramentas`, `decisoes`, `specs`, `skills`, `configuracoes` and
   **`evals`** (behaviour cases) as a **draft**. Cost is capped (§5). Poll with `action=geracao`.
3. **Read the gaps (`lacunas`).** Every area reports what the generator could not (or must not) invent
   — `texto_obrigatorio_ausente:<chave>`, `chave_desconhecida:`, `placeholder_invalido:`, `ferramenta_desconhecida:`,
   `skill_inexistente:`, `eval_com_pii:<slug>:<tipo>`, `slug_ocupado:`… Fix each by hand; repeat an area with
   `POST .../geracoes/{id}/areas/{area}/repetir`. An item you edited shows as `editado` and is never overwritten without `forcar`.
4. **Pin the qualification standard** (if the agent qualifies): author or reuse a standard (human, `/api/qualificacao`), publish
   it, then `PUT .../draft/qualificacao` (or let publish pin the newest). A declared standard with **no published version blocks
   publish** (`qualificacao_indisponivel`).
5. **Specs.** The generator *declares* the `{{org.*}}` keys; the **values** belong to each org (`PUT /api/studio/agents/{key}/specs`
   by that org's admin). `GET .../prontidao` lists required specs the current org has not filled.
6. **Evals.** The generator drafts behaviour cases; **you** review them (they are the definition of "good") and add the
   mechanism cases (`evals_mecanismo`) for a channel agent. Fixtures are synthetic (no phone/CPF/CNPJ/e-mail — refused).
7. **Ask the draft what it owes** — `action=prontidao` / `GET /api/studio/agents/{key}/prontidao`. Blocking items are exactly
   what would make publish answer 409; advisories are what a *complete* agent has and this one does not (stale skill pins,
   a tool without a description row, missing parameter labels, unfilled org specs, generator gaps, controls off).
   Stale skill pins: `action=atualizar_skills` (`POST .../draft/skills-biblioteca/atualizar`) re-pins every skill to its newest
   published version — an **explicit** act (a pin never moves by itself; a published version stays immutable).
   Eval refinement loop via the same tool (`noctus.agents.content`): `loop_iniciar` · `loops` · `loop` · `loop_parar` · `rodada` · `run` (writes dry-run unless `confirm=True`; server 409/422 returned verbatim under `servidor`; token `NOCTUS_AGENTS_EVALS_TOKEN` else the content token).
8. **Run the evaluations on the current hash** — judge suite (`POST .../evals/runs`, no `case_ids`, the version's own model) and,
   for a channel agent, the mechanism suite (`POST .../mecanismo-runs`, LIVE driver). Any later edit changes the hash and In the studio these are buttons in the "Prontidão para publicar" panel (Rodar avaliação completa / Rodar suíte de mecanismo / Ligar agente); no readiness item shows an API path.
   invalidates the run; `prontidao` says `eval_juiz_hash_diferente` / `mecanismo_hash_diferente`.
9. **Publish — a human act.** `POST .../draft/publish` (UI "Publicar rascunho"). The MCP token never publishes. A 409 carries the same
   `prontidao` list, so one refusal shows everything still owed.
10. **Turn it on.** A published channel agent is still `desligado`: `PUT .../controle {"modo":"ligado"}`. Orgs fill their specs.

---

## 3 · The publish gates (what `POST .../draft/publish` checks, in order)

| # | Gate | Refusal (409 `code`) | Readiness item(s) (`recusa_publicacao`) | Override |
|---|---|---|---|---|
| 1 | The agent's qualification standard has a published version, or the draft pins one | `qualificacao_indisponivel` | `qualificacao_indisponivel` | none |
| 2 | The draft compiles with **no blocking warning** and no required text/tool/decision/spec hole | `conteudo_incompleto` (a missing content row) / `compile_blocked` (any other blocking warning) | every blocking compile warning (`texto_ausente`, `secao_vazia`, `placeholder_desconhecido`, `ferramenta_desconhecida`, `decisao_sem_opcao_padrao`, `spec_nao_declarada`, …) | none |
| 3 | If the agent requires the mechanism suite: a finished, complete, under-budget, **LIVE-driver** run of the **current hash**, every case pass^k | `mecanismo_reprovado` (+ `motivo`) | `mecanismo_sem_casos` / `_sem_execucao` / `_hash_diferente` / `_driver_nao_live` / `_nao_concluida` / `_orcamento_excedido` / `_incompleta` / `_reprovada` | **none** (no human override either) |
| 4 | A complete judge run of the **current hash**, ≥ 1 case, score ≥ the agent's `publicacao_limiar` | `eval_required` | `eval_sem_casos` / `eval_juiz_sem_execucao` / `_hash_diferente` / `_incompleta` / `_abaixo_do_limiar` | a **human** may publish with `override_reason` (≥ 20 chars, audited); under the mechanism gate the judge suite is advisory unless the agent opted in to blocking |

`pronto_para_publicar` is true iff none of the above would refuse. The readiness module and the publish route call the **same
predicates** (`recusa_de_compilacao`, `juiz_aprovado`, `decidir_portao`), and a test (`tests/studio/def/test_prontidao.py`)
publishes a draft in each state and checks the refusal is the one a blocking item names — a gate without a readiness item (or the
reverse) fails the suite. **The human override of gate 4 is the only thing the view cannot predict.**

Advisory items never block: `skill_desatualizada`, `padrao_atualizacao_disponivel`, `ferramenta_sem_descricao`,
`rotulo_parametro_ausente`, `spec_org_faltando`, `geracao_lacunas`, `geracao_area_nao_concluida`, `geracao_em_andamento`,
`mecanismo_nao_configurado`, `controles_desligado`, and the non-blocking compile warnings (`spec_nao_usada`, `titulo_reservado`,
`prompt_extenso`).

---

## 4 · The reference agent (`referencia`) and the exemplar flag

- `agents.agents.exemplar` (migration 058) marks a platform definition the generator may imitate. **Only a platform admin
  session** toggles it: `PUT /api/studio/plataforma/agentes/{key}/exemplar {"exemplar": bool}` — not the content token, not
  `PATCH`. The generator itself (`papel='gerador'`) cannot be an exemplar.
- `POST .../geracoes {"referencia": "julia"}` → the run imitates only that exemplar (422 `referencia_invalida` if it is not
  one, or has no published version). If it stops being an exemplar before the job runs, the run fails visibly
  (`referencia_indisponivel`).
- What the generator sees of the reference (structured context, never instructions): section layout and sizes, which text slots
  are filled, tool names with their **parameter labels**, decisions with their **options**, the **eval-case shapes**
  (title, number of criteria, tags) and the qualification **standard key**. The **verbatim text** (section/text/description
  bodies, parameter labels, option labels, criteria) is included **only when the target agent lives in the platform org**; for any
  other org the structure is shared and the text is not — and a generated output that reproduces exemplar text is blocked
  (`vazamento_detectado`, fingerprint check over *all* exemplar text, including eval criteria and labels).

---

## 5 · The generator: what it does, what it costs, what it never does

Platform agent with `papel='gerador'` (found by role, never by key); its **published version** is the prompt: its sections
`planejamento` and `area-<area>` are the per-area instructions — **data**, edited in the Studio like any content. One
planning call, then one call per area (≤ 2 in parallel). **Cost cap:** `limite_usd` ≤ **US$ 5 per run** (DB `CHECK`), enforced
*before* each call by a worst-case estimate (input ÷ 2.5 chars/token + `max_tokens` × output price); a call that might exceed the
remainder is not made (area `pulado`, run `parcial`). Unmeasured usage is charged at the estimate. One run in flight per agent.
Areas: `secoes textos ferramentas decisoes specs skills configuracoes evals`. A missing `area-<x>` instruction fails that area
with `instrucao_ausente` — write the section in the generator's draft and publish it.

**What never comes from AI (a human supplies it):**

- the **qualification standard** (criteria, stages, parameters) and any **new library skill** — the generator only *chooses* from
  published library skills, and reports `skill_inexistente` otherwise;
- **org spec VALUES** (the generator declares keys; each org fills its own);
- **mechanism eval cases** (`evals_mecanismo`), **conformance rules**, **controls** (`ligado/desligado`);
- **tool names** outside the code registry (`ferramenta_desconhecida` gap), **text keys** outside the registry;
- the **exemplar flag**, the **content token**, and the **publish** — always a human platform admin.

---

## 6 · Security notes

- **Content is DATA; lead input is never instructions.** A prompt, a text, a tool description is a row; the model never treats a
  lead's words as a system rule (provenance envelopes, `KB § PATTERNS/` conformance + IP protection). The generator is told
  the briefing as a JSON *field* (`briefing`), not as an instruction; its output is validated against a closed schema and the
  registries before anything is written, and only ever to the **draft**.
- **Edits need Studio auth** — platform admin session, or the `studio:content-write` token (issuer `noctus-platform`, minted by a
  platform admin, optional expiry, revocable). Reads of the definition are audited (`definicao_lida`); token writes are audited
  (`conteudo_editado_mcp`); the exemplar toggle and the skill re-pin are audited even for a human.
- **Publish requires a human.** No MCP code path calls a publish route (the API layer refuses the path outright).
- **PII.** The briefing's `exemplos` are PII-checked before any LLM call (`exemplos_com_pii`); every generated eval case is
  PII-checked (phone, CPF/CNPJ with valid check digits, e-mail) and the case with PII is dropped into `lacunas` (kind only, never
  the value) — fixtures are synthetic (Meta WhatsApp terms 4.7).
- **IP.** Platform prompts never enter git (payload files for the MCP tool live outside any work tree); the exemplar's text is
  verbatim only inside the platform org; reproduced text is blocked by the leak guard.
- **Cost.** Spend is capped per run; the run records `custo_usd` per area.

---

## 7 · Checklist (what "complete" means)

`GET /api/studio/agents/{key}/prontidao` returns `pronto_para_publicar: true` **and** no `aviso` you cannot justify:
sections + required texts filled · every tool the agent works with described, parameters labelled · decisions typed · specs
declared and filled by the org · skills pinned at their newest version · standard published and pinned · behaviour cases
written and passing on the current hash · (channel agent) mechanism suite green on the current hash · conformance rules set ·
generator gaps resolved · controls set after publish.

Composes with: `KB § GUIDES/new-product.md` (a *product*, not an agent), `products/agents/projects/julia-v2/CONTRACT.md` (the design),
`products/agents/README.md`, `.claude/skills/noc-new-agent/SKILL.md`.
