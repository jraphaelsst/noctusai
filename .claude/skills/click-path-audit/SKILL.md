---
name: click-path-audit
description: Use when a button, toggle or form "does nothing" or leaves the UI in the wrong state although every function involved works — triggers "click path audit", "button does nothing", "handler undoes itself", "state reset by another action", "final UI state is wrong", "after a store refactor", "botão não faz nada", "auditar fluxo de clique". Traces each touchpoint handler call by call against a side-effect map of the shared state stores and finds sequential undo, async races, stale closures, dead paths and effect interference. Complements noc-wiring-audit (route exists, returns data), which cannot see these.
license: MIT (see LICENSE; vendored, adapted)
metadata:
  version: "1.0.0"
  origin: "github.com/affaan-m/ECC/tree/4adeee6732a12d1540f49a4d50a38ce8c97f9a53/skills/click-path-audit"
---

<!-- vendored: github.com/affaan-m/ECC@4adeee6732a12d1540f49a4d50a38ce8c97f9a53 (skills/click-path-audit/SKILL.md) · MIT · adapted 2026-11-25 -->

# click-path-audit — does the final UI state match what the button promises?

Static wiring checks ask "does the handler exist, does it crash, are the types right". They miss handlers whose calls each work but cancel each other. Real shape: `setComposeMode(true)` then `selectThread(null)`, where `selectThread` silently resets `composeMode` — the button does nothing, every function is fine.

## Workflow

1. **Scope.** One page, one store, or the touchpoints of a changed store action. Never the whole app in one pass (expensive) — split by page, one pass each.
2. **Map side effects first (shared store / context / query-cache).** For every action or setter in scope write `name → sets: [...] · resets: [...]`. List **dangerous resets**: actions that clear state they do not own. This map is the input to every later step; build it before auditing any button.
3. **Trace each touchpoint** (onClick, onSubmit, onChange, toggles): list the handler's calls IN ORDER; per call what it reads, writes, and resets as a side effect.
4. **Check the six patterns** against the trace:
   - *Sequential undo* — a later call resets what an earlier one set.
   - *Async race* — two promises write the same field; the winner depends on resolve order.
   - *Stale closure* — two updates read the same captured value (use the functional updater form).
   - *Missing transition* — label says Save/Delete/Send, handler only validates or sets a flag.
   - *Dead path* — a condition that is always false at that point.
   - *Effect interference* — an effect watching the field resets it right after the handler sets it.
5. **Compare** the final state with what the label promises to a user. A mismatch is the bug, whatever each function does alone.
6. **Report** one block per finding: touchpoint (label, file:line) · pattern · ordered trace with the conflicting step · expected vs actual · fix · severity.
7. **Every finding gets a regression test** that clicks the touchpoint and asserts the final state (not that the functions were called).

## Guardrails

- Read-only: this skill traces and reports; fixes go through the normal self-branch flow.
- Not for API-shape bugs (use `noc-wiring-audit` / boundary contract tests), styling (visual review) or performance (`noc-perf-probe`).
- A server-state variant of the same trap — a write that does not fill every cache entry it touches — is `noc-cache-writes`; run both on a store refactor.
- Trace evidence is file:line from the tree, not memory of how the store behaves.

## Depth

`KB § PATTERNS/frontend/product-internal-wiring.md` · `KB § PATTERNS/frontend/mutation-cache-writes.md` · `KB § PATTERNS/frontend/lying-loading-state.md` · evals: `evals.md`.
