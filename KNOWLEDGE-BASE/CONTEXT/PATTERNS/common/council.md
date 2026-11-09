# Council: independent, blind, measured challenge before a decision locks

> Procedure: skill `noc-council` (v1.0.0). This doc holds the WHY, the protocol, the stage map and the
> measurement loop. Ledger contract: `project-history/assistant-chatbot/contracts/council-ledger.md`.
> Born 2026-11-09 (assistant-chatbot run; owner decisions D6-D17).

## 1 · Why (evidence)

| Source | Finding that matters here |
|---|---|
| Sharma et al. 2023 (Anthropic), https://arxiv.org/abs/2310.13548 | Sycophancy is general across assistants, driven partly by preference data favouring agreement: the author of a plan leans toward agreeing with itself. |
| Zheng et al. 2023, https://arxiv.org/abs/2306.05685 | LLM judges show self-enhancement bias: a model judging its own plan is biased. |
| Liang et al. 2024, https://arxiv.org/abs/2305.19118 | Degeneration-of-thought: a single model self-reflecting stops producing new ideas once confident. |
| Kim et al. 2025, https://arxiv.org/abs/2506.07962 | Errors are correlated across models, more so within one family: N copies of one model are not N independent reviewers. |
| Verga et al. 2024, https://arxiv.org/abs/2404.18796 | A panel of disjoint-family models beats one big judge; model-family diversity is the lever (we are Claude-only for now). |
| Wang et al. 2024, https://arxiv.org/abs/2402.18272 and Smit et al. 2023, https://arxiv.org/abs/2311.17371 | Counter-evidence: for reasoning tasks a strong single prompt roughly matches multi-agent debate. Hence independence is reserved for high-stakes calls. |
| Anthropic Engineering, multi-agent research system, https://www.anthropic.com/engineering/multi-agent-research-system | Multi-agent costs about 4-15x chat tokens. |
| Karpathy `llm-council`, https://github.com/karpathy/llm-council | Protocol shape only (independent answers, anonymised review, chairman); not evidence. |

Caveat: the studies are QA/reasoning benchmarks; none measures council value for design review.
The measurement loop (section 6) exists to measure it locally. Source table:
`project-history/assistant-chatbot/research/council-and-product-done.md` section 2a.

## 2 · Protocol (blind, parallel, anonymised)

Open session, compose a brief WITHOUT the author's recommendation, dispatch every seat in
parallel as a background subagent (`councillor` per lens, advisors by name), anonymise objections
as A/B/C, dispatch `council-chair` (Opus), record the verdict, surface to the tech-lead, record
outcomes later. Every row goes through `noctus.dev.council_ledger` (`open_session`,
`record_objection`, `record_verdict`, `record_event`, `report`). Steps in the skill.

Hybrid by owner decision (2026-11-09): NOW every seat is a Claude Code background subagent
(no direct API calls). Seat models: lenses Sonnet, advisors their configured model, chair Opus.

## 3 · Stage map

The owner-approved stage x seat matrix (M must, O optional) lives in the skill, the single
canonical place; the research file section 3b is its origin. Seats per stage = all five lenses
plus every advisor marked M or O on that stage's row.

## 4 · Triggers: when the council meets

- Project `assistant-chatbot`: the full council at every stage (D13, trigger `stage_map`).
- Future runs: the trigger set `new_product`, `irreversible`, `trust_boundary`, `prod_exposure`
  (the council informs, the owner decides), `money_legal_lgpd`, `seed_fanout` (3+ products),
  `large_estimate`, `unrebutted_objection`.

## 5 · Single-chat vs independent

Single-chat (one model, one context) surfaces counter-arguments but is not independent; it is
allowed only where no trigger fires, and must be labelled "not independent" (`mode=single_chat`).
Independent subagents give separate context plus each advisor's own domain evidence, which is what
single-chat cannot. Known limit: one model family means correlated errors; diversity comes from
evidence and role.

## 6 · Measurement loop

Outcomes (`vindicated`, `refuted`, `untested` + evidence) are recorded later against each
objection. Metrics per seat (hit rate, unique hit rate, false-alarm rate, acceptance rate, cost
per hit) have one derivation each in the contract section 3, computed by
`council_ledger action=report`. Retune signal: a seat with 10+ resolved objections on a stage and
hit rate under 0.2 is proposed M to O; over 0.6 while O is proposed O to M. The owner ratifies;
nothing auto-edits the map.

## 7 · In-app (future)

Lens and chair prompts become rows in the core prompt registry
(`noctusai_lib.integrations.prompt_registry`, edited on Studio "Agentes da plataforma"), the chair
an Opus API call, and the tech-lead that called the council tool ratifies or overrules (events
`ratified`/`overruled`, `mode=api`, `chair_kind=api_chair`). Not built yet.

## 8 · Waiting consumers

- `noc-iterate` step 4 (council before a refine): same five lenses, stage `iterate`.
- `agent-creator` section 3: links each refine to the `eval_run` id (`subject_kind=eval_run`,
  `subject_ref=<eval_run id>`), so outcomes can be tied to evaluation evidence.
- `noc-questionnaire`: high-stakes questions run this council first (stage `owner_question`).

Composes with `KB § PATTERNS/common/owner-questionnaire.md` · `KB § PATTERNS/architect/measurement-by-design.md` · `KB § PATTERNS/common/agent-context-architecture.md`.
