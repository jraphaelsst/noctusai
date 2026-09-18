# Predeploy leg verify-or-block

**What it is.** A structural rule over `noctus.dev.predeploy_check`'s
`DEFAULT_CHECKS` legs: every leg must either **verify** a real condition
(its `ok` reflects a check that could genuinely fail) or **block**
(fail-closed) when it cannot verify — it must never silently return
`ok=True` because it could not tell. Enforced mechanically by the keeper
`check_predeploy_leg_verify_or_block` (`mcp/noctusai/tools/noctus/dev/compliance.py`).

**Status**: born 2026-09-17/18, part of the same session's gate-integrity
closure as `KB § PATTERNS/common/agent-context-architecture.md` § scoped-refresh
parity and the `wire_env=True` default fix.

## Why

`predeploy_check` is the LAST gate before a product reaches prod
(`KB § GUIDES/production-deploy.md` § 2a, safety-net P5). `schema_exposure`
already got this right by construction: a `not_configured`/`unavailable`/
`error` result there is a **failure**, never a silent pass — "we couldn't
check" must not read as "it's fine" for the exact gate built to catch a
PGRST106-class incident (2026-09-16, agents/academia-de-reciclagem —
`/api/health` stayed 200 while the startup hook failed).

But nothing STRUCTURALLY stopped a future leg from shipping the opposite
posture: an early `return True` on a state it never actually checked (an
exception swallowed into "assume fine", a probe result never inspected).
`schema_exposure`'s own correctness was a single author's discipline, not
an enforced invariant — the other 8 legs each SKIP loudly when genuinely
unverifiable (no prod-env snapshot fed, no frontend dir, `node_modules`
not installed locally), but "SKIP loudly" and "silently trust an
unverified state" produce the IDENTICAL `ok=True` on the wire. Only the
MESSAGE distinguishes them, and nothing was reading the message.

## What it does (mechanics)

The keeper AST-parses `predeploy_check.py` (never a hand-maintained list —
`DEFAULT_CHECKS` and `_default_run_check` are derived from the live code,
so a renamed/added leg is picked up automatically or the derivation itself
fails loudly). For each `if check == "<leg>":` block matching a
`DEFAULT_CHECKS` entry, it walks every `Return` statement in source order
and classifies each `return`'s value:

| Return shape | Treatment |
|---|---|
| **Computed boolean** (`return r.returncode == 0, ...`, `return audit["ok"], ...`) | Exempt by construction — a computed value can genuinely evaluate `False`; this IS verification. |
| **Literal `return False[, msg]`** | Marks `saw_return_false = True` for the rest of this leg's block — evidence the leg actually branches on a real failure condition. |
| **Literal `return True[, msg]`**, occurring AFTER a `return False` was seen in the same block | Allowed — this is the audited happy-path tail (e.g. `if audit["violations"]: return False, ...` then `return True, "...ok..."`). |
| **Literal `return True[, msg]`**, occurring with NO preceding `return False` in the same block | Allowed ONLY if the message contains `"skip"` (case-insensitive — covers this file's two existing spellings, `"... SKIPPED — ..."` and `"... (skipped)"`). Otherwise **flagged**: `predeploy-leg-unverified-ok`. |

A second, independent check: any `DEFAULT_CHECKS` entry with **no** matching
`if check == "<leg>":` block at all is flagged as `predeploy-leg-missing-runner`
(it would silently fall through to the `return False, f"unknown check
'{check}'"` catch-all — not a false-green, since that IS a failure, but a
drift worth naming: the leg is declared but unimplemented).

**This is a heuristic, not a full control-flow verifier.** It does a linear,
source-order flatten of `If`/`Try` bodies (recursing into both branches and
every `except` handler) — sufficient for this file's straight-line,
early-return leg shape, but it is not a general dataflow analysis. A
leg that manufactures a `return False` somewhere unrelated earlier in the
block purely to satisfy this predicate, then follows it with an
unconditional `return True`, would pass. The keeper is precise on every
leg shipped as of 2026-09-18 (zero findings against the real file) and
catches the concrete dangerous shape this pattern exists to prevent: an
unconditional or exception-swallowed `return True` with no adjacent
failure branch and no admission that it skipped.

## When to apply

- **Adding a new leg to `DEFAULT_CHECKS`.** Before shipping, ask: can this
  leg's "ok" path ever be reached without a real check running? If the
  answer involves an `except: return True` or an early `if <can't tell>:
  return True` with no other wording — either add a genuine failure branch
  first, or make the skip say so (the message MUST contain "skip").
- **Reviewing a predeploy leg change.** Run `python mcp/noctusai/cli.py
  --check-predeploy-leg-verify-or-block` (or let `noctus.dev.validate()`
  surface it — it is wired into the platform-wide aggregate).
- **Designing an analogous "gate composed of legs" surface elsewhere**
  (e.g. `audit_product`, `predeploy_check`'s own sibling gates) — the same
  verify-or-block / explicit-skip framing generalizes.

## API / surface

```python
# mcp/noctusai/tools/noctus/dev/compliance.py
def check_predeploy_leg_verify_or_block(repo_root: Path | None = None) -> list[dict]:
    ...
```

```
python mcp/noctusai/cli.py --check-predeploy-leg-verify-or-block
```

Wired into the platform-wide `noctus.dev.validate()` aggregate (severity
`high` — a predeploy gate is the last check before prod).

## Anti-patterns

- **DON'T** swallow an exception into `return True, "assume it's fine"` — if
  a probe can fail in a way you didn't anticipate, that IS the case this
  gate exists to catch. Either handle the specific failure mode explicitly
  (a real `return False`), or re-raise / classify it as `unknown` (the
  existing classify-and-report path already exists for this).
- **DON'T** add a "skip" marker to a message just to satisfy the keeper
  when the leg COULD have verified something — the marker is a promise
  that this leg genuinely had nothing to check, not an escape hatch.
- **DON'T** hand-maintain a parallel list of "legs that are allowed to
  skip" — the keeper reads the message text at the return site itself,
  co-located with the code it describes (the recurring "hand-maintained
  list drifts" failure mode this platform gates against elsewhere too,
  `KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`).

## Composes with

- `KB § PATTERNS/backend/boundary-contract-tests.md` — the sibling
  "canonical test coverage, not a per-product carve-out" discipline.
- `KB § PATTERNS/devops/prod-exposure-consent.md` — another "the gate that
  runs once, at first exposure, must not silently pass" surface.
- `KB § GUIDES/production-deploy.md` § 2a/§ 6 — where `predeploy_check`
  itself is specified end-to-end.

## History

- 2026-09-17/18: born in the same session that fixed the
  `agent_context_cache` scoped-refresh cross-tree parity bug and the
  `task_branch(action='start')` `wire_env` silent-default-flip class — all
  three are "a gate/remedy that looks correct in isolation but silently
  doesn't do what its own contract promises" incidents surfaced in one
  sitting. `schema_exposure` (2026-09-16, PGRST106 incident) is the
  worked example this pattern generalizes from a single leg's discipline
  into a keeper over ALL legs.
