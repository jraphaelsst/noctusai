# Decision record: skill gate -> auto-load (Julia turn redesign, 2026-11-05)

## 1. Problem (verified in code)
- Every tool was visible from turn 1, but a tool tied to a skill (`oferecer_imoveis` <- `ofertar-imoveis`, any tool in a library skill's `obrigatoria_para`) was REFUSED with `skill_nao_aberta` until `abrir_skill` ran in the THREAD. A greeting that touched two such tools hit the budget (`max_recusas_por_turno=2`) and ended in a customer-facing hand-off.
- "Opened" was stored per thread and outlived the context (history is text-only, last 20 messages): on turn 5 the skill counted as open while its body was gone. The gate was too strict on turn 1 and meaningless later.
- No external source endorses "let the model call, then refuse" as gating; Anthropic's Agent Skills do not gate tools. Make invalid calls impossible or load the instructions; tool errors must be actionable; hand off for customer-intent failure or high risk, not for the bot's own slip.

## 2. Options
| option | verdict |
|---|---|
| A. Hide the gated tools until the skill is open | rejected: the model then cannot call what the prompt tells it to call; a second state machine; tools list changes mid-turn (breaks the provider cache of `tools`) |
| B. Preconditions only (drop the skill link) | rejected: loses the "read the procedure before acting" guarantee the skills exist for |
| **C. Auto-load + preconditions** | **chosen** |

## 3. Chosen design
- The first call, IN A TURN, to a tool tied to a skill: the server opens the skill for that turn (`JuliaTurno.skills_carregadas`), books the opening (audit, unchanged) and runs the tool. Its business preconditions are still the only reason to refuse (`nao_pode_ofertar`, `limite_ofertas`, `imovel_ja_oferecido`, `sem_codigo_campanha`). The result carries `procedimento_obrigatorio: [{skill, corpo}]` (body capped at 4000 chars). The procedure text is NOT a source of figures for the `valor_sem_ferramenta` check.
- "Loaded" is scoped to the turn (and reset by a re-run): a new turn re-delivers the procedure with its first gated call. `abrir_skill` stays as an optional tool and marks the skill loaded.
- `skill_nao_aberta` is retired as a refusal (kept as an accepted optional text row so existing drafts validate; never emitted). A gate naming a skill the library lacks is logged, not a lead-facing refusal.
- Stop causes are split. PROCEDURAL (`limite_recusas`, `falhas_repetidas`): one silent re-run on fresh budgets, then `runtime.resposta_fallback` (or silence) plus an operator alert (`alerta` action, tipo `erro_agente`, code only) and a `parada_segura` violation; NEVER a hand-off. HAND-OFF causes unchanged: explicit request for a person, `fora_do_escopo`, security escalation, rights requests, compliance blocked twice.
- The corrective (compliance) re-run also starts with fresh counters (`reiniciar_tentativa`): before, it inherited spent refusals and calls.

## 4. Same change, other structural fixes
- **Compile cache.** `_compilar` caches the compiled prompt of a PUBLISHED version keyed by (definition org, version id, org-specs hash, standard version id); a publish, a spec write or a new standard version misses by construction. Drafts (eval runs) are never cached. The proof of use (`save_compiled_prompt`) is written once per (org, hash) per process. System message 1 (prompt + canary + marker line) is byte-stable across turns; per-turn data lives in system message 2.
- **Tool descriptions once.** The compiled `# Ferramentas` block no longer lists per-tool lines; the provider `tools` parameter (filtered by capabilities and restricted mode) is the single copy. Tool rows stay in the hash.
- **Judge harness.** Judge cases of a channel agent run through the SAME `EvalTurnDriver` path as the mechanism suite; the case `contexto` is rendered into the state block (system message 2), never into the lead's turn.
- **Temperature.** `tool_policy.temperature` (0..1) per version, default 0.3 (`TEMPERATURA_CANAL_PADRAO`). Finding: the Anthropic provider never forwarded `temperature` at all (so the old "1.0" was the API default); the tool-calling path now forwards it when it differs from 1.0. See measured results in the iteration log.

## 5. Measured outcome (k=3, claude-haiku-4-5, prod DRAFT, local `LiveEvalTurnDriver`)
Full table and the red-team note: `KNOWLEDGE-BASE/CONTEXT/PATTERNS/ai/agent-evals.md` section 12. Headline: before 53/57 cases (162/171 executions, US$ 1.24,
28.4k input tokens/turn, 1.22 LLM calls/turn); after 59/65 on the larger set (181/195, US$ 1.36, 26.1k tokens/turn, 1.20 calls/turn);
temperature 1.0 vs 0.3 is within noise (kept 0.3); history 40 kept (61/65 and 59/65 vs 57/65 at 20); the prompt is ~25k tokens/turn at a 96% cache-read share.
Greeting cases did not reproduce the prod safe stop on this draft (0/20 hand-offs before and after); they cost US$ 0.137 -> 0.061 and 1.65 -> 1.0 calls/turn.
Two defects found BY the new real-path runs, both structural: the eval world never offered `sinalizar_alerta` (no alerts store), and the leak
fingerprint blocked a legitimate answer that quoted the org's own opening hours (reply now masked of org spec values before the check).

## 6. Draft content changes (prod DRAFT of `julia`, never published; mirror in `content-v3-iter4/julia-v3-secoes-iter4.json`)
`erros-e-insatisfacao` (harassment examples: flirting / photo request / sexual content -> alert `outro`), `transferencia` and `limites` (the return-time
sentence no longer a ready 12+ token copy). Effect: `mec-spec-ausente-insiste-oferece-pessoa` 0 -> 3/3; `mec-abuso-assedio` still open (JL-007).

## 7. What is built vs scheduled
Built: ledger file + reconcile hook (`ledger/`), local runners, the guards above. NOT built: automatic runs (on content change before publish, on a schedule
within a budget, over production handoffs / safe stops) and the `noctus.dev.findings_ledger` plug (NOC-REMEDIATE[ledger-plug]).
