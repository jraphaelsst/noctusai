---
name: noc-verify-seed
description: Use BEFORE dispatching any "consume seed X" slice — triggers "consume seed", "use seed adapter", "wire to seed X", "verify the seed ships it", "is the seed ready". 30s grep that catches the planned-consume-but-only-Protocol-shipped trap before it costs the engineer ~30min of stale-base work.
version: 1.0.0
---

# noc-verify-seed — seed-ships-it dispatch-time gate

🔴 **The trap (N≥3 codified):** a brief says "consume seed `noctusai_lib.integrations.X`" but only the Protocol+Fake shipped — no Real adapter, no factory, no `__init__.py` export. The engineer either re-builds the seed (scope creep) or hand-rolls a fork (DRY violation). 30s grep at dispatch time saves the 30min.

## Workflow (run BEFORE the brief leaves your message)

1. **Resolve the seed surface against the FORK BASE, not the working tree.**
   - Dispatching = engineer forks off `origin/dev` (or off your architect branch). The truth is what `git ls-tree origin/dev` shows, not your worktree.
   - One call: `git -C <primary> ls-tree -r origin/dev -- noctusai_lib/integrations/<X>/ | grep -E "__init__|adapter|factory"`.

2. **Check the four ships-it gates** (each one a single grep — ALL must pass):
   - **Protocol exported** — `git show origin/dev:noctusai_lib/integrations/<X>/__init__.py | grep -E "^(from|import) .*\b<X>Protocol\b"`.
   - **Fake exported** — same `__init__.py`, `Fake<X>` symbol.
   - **Real exported** — same, `Real<X>` (or `<Vendor><X>` for branded adapters).
   - **Factory exported** — `make_<x>` (lowercase) returns the Protocol; grep for its `def make_<x>(`. The factory IS the consumer-facing seam; missing factory = consumer-side forks.

3. **Verify the consumer-import path the brief will use.**
   - Brief says `from noctusai_lib.integrations.X import make_x`? Resolve: `git show origin/dev:noctusai_lib/integrations/__init__.py | grep -E "^from \.X import"` (or whatever the brief's exact import statement is). Import that doesn't resolve = stale-base dispatch.

4. **Spot the half-shipped slip.**
   - Gates 1+2 pass but 3+4 fail ⇒ the seed has Protocol+Fake but no Real/factory ⇒ scope adjustment BEFORE dispatch: either (a) the brief now includes "ship Real+factory in noctusai_lib", or (b) re-route to a different seed that's complete.
   - Gates all pass but the factory's signature ⊥ what the brief plans to call ⇒ scope adjustment: extend the seed seam (back-compat-defaulted shape-config) before the consumer slice fires. → `KB § PATTERNS/architect/seed-canonical-defaults.md`.

5. **Emit the verification line in your dispatch brief** — engineers read `engineer-seed`; the brief should carry a line like `seed-ships-verified: noctusai_lib.integrations.<X> { Protocol, Fake, Real, make_<x> } @ <origin/dev sha>` so the engineer can trust without re-verifying.

## Guardrails
- ⚠️ **NEVER verify against the working tree** when dispatching — `git ls-tree origin/dev`, not `cat`. The harness's `Agent isolation: "worktree"` famously forks from a stale base; even when using `task_branch`, the truth is the fork base.
- "Consume seed" briefs without this 30s gate are forbidden — the gate is cheaper than the engineer's contextualization tax (~45-60k tokens) plus the rework loop.
- Pure-logic seed modules (no IO) are exempt from the Real/factory gates — they ship as a function, not a Protocol+Fake+Real triple.
- If the verification finds a half-ship, decide IN-FLIGHT (extend seed first OR re-route slice) — don't dispatch a slice you know is broken.

## Depth
`KB § 03-SEED-ARCHITECTURE.md` (the spine) · `KB § PATTERNS/backend/seed-fake-real-adapter.md` (the shape) · `KB § PATTERNS/architect/seed-canonical-defaults.md` (defaults are answers, not coincidences) · memory `feedback_verify_seed_ships_it{,_at_dispatch_time,_on_fork_base}` (the three codifications this skill folds).
