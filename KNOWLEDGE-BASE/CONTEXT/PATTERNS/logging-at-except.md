# Logging-at-except — the silent-error remediation convention

> Formalized 2026-05-18 as the named §3a remediation convention for the
> silent-except compliance class (`projects/platform-compliance-baseline` —
> ~280 instances across mcp/seed/products). Promotes the existing logging
> rule to a first-class, INDEX-discoverable pattern. Self-contained.

## The rule

Every `except` block does exactly one of: **(a)** `logger.<level>(...)`
(carrying the exception) · **(b)** `raise` / `raise NewError(...) from exc`
· **(c)** return an error-bearing value the caller checks. Never
`except: pass`, never a bare silent `return None`, never a degraded
fallback with no log. **There is no `# silent-ok` escape hatch** — it was
retired 2026-04-28 by user directive; the comment does not suppress the
keeper. The keeper `check_silent_errors` flags swallow-shaped handlers;
`check_no_silent_ok_comment` flags the retired comment. This class is a
large slice of the compliance baseline; logging each site shrinks it.

## The fix — level guide

| Situation | Level |
|---|---|
| Recoverable, expected (cache miss, optional dep absent) | `logger.debug` |
| Recoverable, unexpected (retryable external failure) | `logger.warning` |
| Unrecoverable at this layer, but handled (degraded path taken) | `logger.error` |
| Unrecoverable + want the traceback | `logger.exception` (in `except`) |
| CLI / pre-logger bootstrap surface | `print(..., file=sys.stderr)` (allowlisted) |

`logger.warn` (legacy stdlib alias) is recognized; a bare-name `warn(exc)`
is **not** (too easily satisfied by a same-named domain fn). Re-raising
(`raise`) is always clean.

## Authoritative depth

Full when-to-log / correlation-id / level rationale lives in
`§ CONTEXT/PATTERNS/logging.md`. Keepers + colocated regression tests:
`check_silent_errors` / `TestCheckSilentErrors` and
`check_no_silent_ok_comment` in `mcp/noctusai/tests/test_compliance.py`.
Gate context: `§ CONTEXT/PATTERNS/compliance-regression-baseline.md`.
