# Compliance regression-baseline gate

> Filed 2026-05-18 — Option A of `projects/platform-compliance-baseline`
> §7(A), locked by the user. Self-contained (durable-docs rule); references
> code paths + dated facts, never the project slug.

## The problem it solves

`check_all_products()` returns `(score, issues)` where each product's score
is `max(0, 100 − Σ severity-penalties)` averaged across the fleet. The
methodology-codification pipeline keeps *adding* keeper detectors (working
as designed), each retroactively surfacing **pre-existing** debt. So an
absolute `assert score == 100` gate is **aspirational, not a regression
detector** — it goes red the moment any new detector lands, independent of
whether the current change regressed anything. CI then either blocks every
unrelated PR ∨ gets `--no-verify`'d into noise.

## The pattern — regression semantics + informational score

s1 **GATE = no NEW high/critical issue vs a committed baseline.** A
fingerprint set of the current high/critical issues is committed
(`mcp/noctusai/tests/compliance_baseline.json`). The gate test computes the
live high/critical fingerprint set and asserts `live − baseline == ∅`. A
NEW high/critical issue (regression) fails; pre-existing debt does not.

s2 **Absolute score is INFORMATIONAL.** The gate test still calls
`check_all_products()`, but the absolute `score` is `print`ed (visible in
`-s` / CI logs), **never asserted**. It is a tracked metric, not a contract.

s3 **Fingerprint = line-churn-robust identity.**
`"<product>|<file>|<severity>|<symbol>"` where `<symbol>` is the backticked
``patches our own symbol `X` `` token when present, else the issue text's
first 80 chars with digits → `#`. Refactors that shift line numbers do not
flap the gate; a genuinely new violating site does.

s4 **Non-deterministic env-artifact classes are excluded** from BOTH the
baseline and the live set so the gate cannot flap on wall-clock / stamp-lag:
`Seed drift:` (seed-version stamp lag — pre-commit HEAD vs post-commit SHA),
`Archive entry` (archive-staleness, date-relative), `Dispatcher`
(dispatcher-staleness, date-relative). Single source of truth:
`is_env_artifact` / `ENV_ARTIFACT_PREFIXES` in
`mcp/noctusai/tests/refresh_compliance_baseline.py`, imported by the gate.

## Refresh contract

The baseline is **deterministic ∧ regenerable**:
`mcp/noctusai/.venv/bin/python mcp/noctusai/tests/refresh_compliance_baseline.py`
(from repo root) re-emits a byte-identical set from the real
`check_all_products()`. Refresh ONLY when:
- debt is intentionally **resolved** → baseline **shrinks** (good);
- a new pre-existing class is **triaged-and-accepted** → baseline **grows**,
  and the commit message MUST cite the triage decision ([A] entry).

Never refresh to silence a *regression* — that re-introduces the silent-error
shape the gate exists to prevent. The regenerator and the gate import the
same `fingerprint` / `is_env_artifact` so the fixture and the check can never
drift apart.

## Where it lives

- Baseline fixture: `mcp/noctusai/tests/compliance_baseline.json`
- Regenerator + shared identity fns: `mcp/noctusai/tests/refresh_compliance_baseline.py`
- The 2 gate tests: `mcp/noctusai/tests/test_compliance.py`
  (`TestSeedCompliance::test_all_products_compliant`,
  `TestAIFeatureCompleteness::test_real_products_pass_validate`)

The two *remediation* conventions for draining the baseline (so it can
shrink) are formalized separately:
`§ CONTEXT/PATTERNS/di-test-seam.md` (the `test_patch_target` /
self-monkeypatch class) and `§ CONTEXT/PATTERNS/logging-at-except.md` (the
silent-except class).
