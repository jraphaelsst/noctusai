# Canonical agent template — the must-haves every agent carries

> **Rule.** Every conversational agent built in Agents Studio carries the canonical template's must-haves. v1 has two: a section that declares the RULE `discordar-com-respeito` (the agent disagrees respectfully and never agrees to please; in the 15-section template it lives inside `honestidade`, readiness checks the rule, never a section key), and behaviour eval cases tagged `bajulacao` (cases that try to make it flatter, confirm an unsourced number, or change its answer under insistence). The generator (`criador-de-agentes`, `papel='gerador'`) writes both into every draft. Prontidão reports a missing one as an `aviso` (group `modelo`), which is the shadow stage. Promotion to blocking is in §4.

Born 2026-11-08. Owner answer (a) to the v03 "LLM Council" report: anti-sycophancy is a MUST-HAVE in the canonical agent template. Answer (b): add 2–3 bajulação cases to Julia's eval loop now.

---

**Every agent is conversational** (owner, 2026-11-09), the media-analyst included, so every agent carries these must-haves. The full conversational base (safety + identity, honesty, conduct, atendimento, human handoff to the org's fallback number, LGPD) becomes the `agente-base` template. SDR content (qualification, offers, booking, scoring) is a layer on top of it, never part of it. Plan: `project-history/roadmaps/agent-templates-2026-11.md`.

## 1 · Why a must-have, not a suggestion

Sycophancy is a model default, not a content bug: asked "this price is great, right?", a model tends to agree. One agent fixing it by hand does not fix the next one. The fix lives where every agent is made (the generator) and where every agent is checked (prontidão).

## 2 · The pieces

| Piece | Where | What it does |
|---|---|---|
| constants | `products/agents/backend/app/studio/regras_secao.py` `REGRA_DISCORDAR` (closed list `REGRAS_SECAO`, column `agent_prompt_sections.regras`, migration 078) and `prontidao.py` `TAG_BAJULACAO` | one name for the section rule and the case tag; an unknown rule is a 422; a child section merged onto a parent's keeps the parent's rules |
| readiness | same file, `_canonico` | `sem_secao_discordar` / `sem_evals_bajulacao` (aviso) or `modelo_canonico` (ok); skipped for the generator itself (it emits JSON, it does not converse) |
| generator | `criador-de-agentes` sections `principios`, `area-secoes`, `area-evals` (Studio data, not code) | every generated draft gets the section and 2–3 `bajulacao` cases |
| groups | `GRUPOS` in prontidao.py ↔ `ProntidaoGrupo` in `frontend/src/api/studio/types-prontidao.ts` | a closed set; a test keeps the two equal, and `compor` refuses an item outside it |

## 3 · How to apply

- New agent: "Gerar com IA" already writes both. Built by hand: tag the section that says it (usually `honestidade`) with the rule `discordar-com-respeito` (written for the agent's context) and 2–3 cases with the `bajulacao` tag.
- A new must-have: add it to `_canonico` (aviso first), to the generator's sections, and to the table above, in the same change.

## 4 · Promotion to blocking (named destination)

Promote both items to `bloqueante` (each with a publish refusal code in `RECUSAS_PUBLICACAO`) once every published conversational agent carries them (Julia first; noc-02 owns her content), and the generator has been published with these sections. Until then a blocking item would refuse Julia's next publish for a reason her owner has not yet acted on.

## Composes with

`KB § PATTERNS/ai/agent-evals.md` (the behaviour suite the `bajulacao` cases live in) · `KB § PATTERNS/common/gate-methodology-sync.md` (shadow before blocking).
