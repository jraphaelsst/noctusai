# findings — social-wiring-absorption-debt

Engineer SW-DEBT returned findings as text (subagent `.md`-write default-off);
architect-transcribed at merge per knowledge-tracking. Symbol-first (AI scaffolding).

## Slips / errors

- None in execution. The avoided slip: P1/P2 would have been *speculative
  work against a non-existent problem* — caught by estimate-off-evidence +
  codebase-is-source-of-truth before any migration was authored.

## Mistakes (process)

- **Stale PROJECT.md dispatched.** The brief + PROJECT.md were authored at
  `7137af0` (174 count); dispatch base was `41a8f4d` where the consolidation
  had already cleared the scoped detectors. Cost: a P0 re-baseline pass.
  Lesson → dispatch-time should re-derive the live count vs the doc's epoch
  before briefing (the triage agent flagged readiness off the doc, not a
  fresh `check_all_products()`).

## Lessons

- A project filed as a `fix-on-contact` balloon can be **partly self-resolved
  by an intervening consolidation**. Re-baseline at P0 is mandatory, not
  optional — the doc's count is an epoch-stamped claim, not current truth.
- `check_silent_errors` flags documented control-flow `except X: return None`.
  Resolution is a sanctioned `logger.debug` before the return (contract
  unchanged), not suppression — [R], not [A].

## Interesting

- Infinite-hang root cause was NOT "network tests" (the doc's guess) but a
  bare `MagicMock()` `yt_mock` → `_wait_for_yt_processing` polled a status
  that never readied → `time.sleep(30)` loop to a 10-min cap **per test
  through the publish path**. The doc's "mark+skip network tests" remedy
  would have hidden it; the real fix (timeout + test-double DI) surfaces it.

## Knowledge / methodology routed

- **pytest-timeout CI-hazard = N≥2 fleet-shaped** (E4-AUDIT named instance +
  social-wiring live instance). Seed should ship a default `pytest.ini`
  test-timeout so scaffolded products inherit it; candidate `check_*` for
  products lacking a default test timeout. Routed to the codification
  pipeline (`phase_learnings` + §11 + architect surface). NOT executed here
  (seed/KB = collision-deferred behind parallel `scripts-mcp-absorption` +
  a separate formalization wave).
- Absorbed-product test debt (`check_no_self_monkeypatch` ×50) is **not
  blanket-mechanical** — absence-path tests need per-test config control; a
  blanket autouse fixture re-introduces patching. Per-site judgment →
  dedicated follow-up (`social-wiring-monkeypatch-test-refactor`).
