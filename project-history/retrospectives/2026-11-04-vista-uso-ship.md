# Retrospective, 2026-11-02 → 2026-11-04: Vista, Uso & Custos, hardware calibration, the train ship

Owner ask: "learn from the last few days." This page records each friction point, its cause, and where the fix now lives.
Rules live at the pointers. This page is only the record.

## What ships (in flight on 2026-11-04 via noctusai-3d's `feat/jl-ship`, carrying train `feat/train-vista-uso-ship`)

- RG optional for every contract party (SW).
- Property overlay CRUD over the Vista mirror (SW 315), with sync runs persisted (SW 316).
- Julia catalog source `espelho|vista` (SW 314, default espelho).
- Vista divergence alerts: per-org switch and destination, plus the Settings UI (SW 317). Transitional.
- Core `/admin/uso` "Uso & Custos": agents and our dev cost, aggregated and broken down per agent/session, with filters.
- LLM agent attribution: `llm_usage_context` had ZERO callers, so every prod `ai_usage` row had a NULL agent_key. It is now opened at the runtime seam and guarded by a keeper.

## Friction → cause → fix

| # | What happened | Cause | Fix (where it lives now) |
|---|---|---|---|
| 1 | Integrate 1 blocked | 5 docs had not followed the code | docs-follow-code gate (worked as designed) |
| 2 | Integrate 2: 6 gates gave no verdict | the 3600 s ceiling counted slot WAIT | `b60607b6d`: ceiling counts running time only |
| 3 | Integrate 3: real SW red | a test pinned the pre-decision "RG required" policy | `c5a067401`; rule in `KB § PATTERNS/compliance/testing.md` (owner decision reversed ⇒ grep tests) |
| 4 | Integrate 4: e2e:core red ×2, green alone | fixed port 5173 with `reuseExistingServer`, so a concurrent server could be reused (risk of a FALSE GREEN on another tree) | `ef4d275e4`: port must be free (else HARNESS INVALID), e2e runs with CI=1 |
| 5 | Integrate 5: a different vitest test red, plus an unnamed pytest red | load flakes; pytest gates did not name failures | `322d6be1d`: pytest failing_tests; under load a red with ≤10 failures reruns once alone |
| 6 | Integrate 6: `waiting_for_slot`, relaunched by hand | integrate exited instead of queuing | `b3b749d82`: FIFO slot queue, 4 h shared deadline |
| 7 | Every retry re-ran ~30 gates (~45 min) from zero | no verdict reuse | `bedf59a5d`: gate verdict cache (greens only, keyed by input closure + runner fingerprint) |
| 8 | A wrapped `gate_sweep` waited 57 min, then was refused as a stale tree | wrapping a self-gating tool in `hw_admission run` | `KB § PATTERNS/devops/hardware-admission-budget.md` (don't wrap) |
| 9 | Predeploy reds from a checkout moving mid-run | measured tree not pinned | `6ce2b1203`: predeploy names head_start/head_end, refuses a moving tree |
| 10 | The box swapped at 2 parallel full suites | memory (8 GB), not CPU or load average, is the ceiling | hardware admission gate; owner row: 2 slots + memory veto (`d474c0880`); continuous calibration roadmap |
| 11 | Three sessions about to drive prod at once (train, Julia, nosnolimiar rename) | no shared driver protocol | `KB § PATTERNS/devops/ship-consent-riders.md` § Concurrent sessions + noc-ship guardrail |

## What worked

- **One train integrate for 6 riders** instead of 6 integrates.
- **Re-measure before retrying.** Every red was re-run alone on the merged tip before it was called false. That evidence is what got the harness fixed at the root instead of by retrying.
- **Peer sessions owning their surfaces.** The gate harness belongs to noctusai-86 and Julia to noctusai-3d. Requests went to the owner of the surface; nobody forked their work.

## Still open (named destinations)

- Post-deploy, owner + noctusai-04: Vista key …644c in Settings › Chaves API; first sync and a check of `imoveis_sync_execucoes`; the divergence destination; tuning `imoveis_sonda_max_falhas`; `/admin/uso` reviewed on real data (prototype-on-real-data), then polish.
- `NOC-REMEDIATE` markers in code: `transicao-vista-divergencias`, `transicao-vista-divergencias-staff-send`, `sanitizar-para-staff-compartilhado`, `resolve-user-phones`, `julia-empreendimento-vista-live`, `vista-env-keys-removed`, `waha-hmac-prod`, `relatorio-rotulos-em-linhas`.
- `/admin/uso` FE: a filter dropdown can keep an option after the data stops containing it (minor).
- Owner: Vista support message, revoke test key …bced, enroll MFA.
