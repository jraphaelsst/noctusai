# Remediation markers — greppable in-code deferral for batch evaluation

> **What this is.** A single greppable token an agent leaves **in the code** at a spot that needs later remediation, so the whole backlog can be **swept and evaluated in batches** at a future moment — instead of each deferral living only in a project doc that gets archived. The marker IS the named destination, so a deferral stays **non-silent** (no-silent-errors) while still being deferred.

---

## The token

```
<comment-leader> NOC-REMEDIATE[<class>]: <what + why deferred> — <YYYY-MM-DD>
```

- **`NOC-REMEDIATE`** — fixed, uppercase, namespaced (distinct from the ~1.7k noisy generic `TODO`s). Greppable in every language: `# NOC-REMEDIATE` (Python) · `// NOC-REMEDIATE` (TS/TSX) · `/* NOC-REMEDIATE */`.
- **`[<class>]`** — a short batch-filter tag. **Open/self-extending** taxonomy (a non-fitting instance ⇒ add a class, never force-fit): `perf` · `dry` · `security` · `lgpd` · `test` · `typing` · `seed` · `a11y` · `cleanup` · **`codify`** …
  - **`codify` is a *special* class** — it's the structured token for a **deferred codification** (a Stage-3 rule judged ripe-but-not-yet-built). Besides the advisory `scan_remediation_markers` sweep, it is read every compliance run by the `check_codification_debt` keeper (the always-on gate form of the `/codify` command's *detection* half — `[[methodology-codification-pipeline]]`). Leaving a codification deferral in free prose ("we should codify X someday") instead of a `[codify]` marker is the gap that keeper closes. Put `[codify]` markers in the rule's **durable** KB doc (never `projects/` — archived), with a real date (a placeholder/missing date ⇒ the keeper flags it `high`).
- **`<what + why deferred>`** — one clause; enough for a batch-sweeper with zero context to act.
- **`<date>`** — absolute (ages the backlog).

Examples:
```python
# NOC-REMEDIATE[dry]: 3rd copy of this date-bucket helper; lift to seed when the 4th lands — 2026-05-25
```
```tsx
// NOC-REMEDIATE[perf]: re-renders on every keystroke; memoize in the next perf batch — 2026-05-25
```

---

## The rules (how it reconciles with the rest of the methodology)

- **It is a sanctioned, NON-silent deferral channel.** The marker satisfies *defer-with-a-named-destination* — the destination is "the next `NOC-REMEDIATE` batch sweep." A deferral with a marker is **not** a silent error.
- **NOT a replacement for fix-on-contact.** In-scope ∧ fixable-now ⇒ **fix it** (fix-on-contact). The marker is only for genuinely **batch-able / out-of-current-scope** remediation — an improvement, not a live bug.
- **NEVER an error-suppressor.** Never on an `except` / swallowed failure (`except: pass  # NOC-REMEDIATE` is forbidden — that is the retired `# silent-ok` shape). Every `except` still logs ∨ raises ∨ returns-error-bearing ([[logging-at-except]]). The marker tags deferred *remediation*, never a swallowed error.
- **Pairs with triage.** A marker is the in-code form of a deferred `[R]`/`[F]` or an `[A]` ([[accept-with-rationale]]); recurrence (`N≥3` of one class) ⇒ stop marking, **promote to a real project / seed lift** (the recurrence rule).

---

## Batch evaluation (the payoff)

Sweep the whole backlog at a chosen moment, optionally by class:

```bash
grep -rn "NOC-REMEDIATE" products/ seed/ mcp/            # everything
grep -rn "NOC-REMEDIATE\[perf\]" products/ seed/ mcp/    # one class
```

A batch session triages the sweep (`[F]`/`[R]`/`[A]`), fixes what's cheap together (shared context ⇒ cheaper than one-at-a-time), and promotes recurrences to projects. **Stage-4 (built 2026-05-25):** `noctus.dev.scan_remediation_markers` (+ `cli.py --scan-remediation-markers`) — the deterministic batch-sweep surface: parses real `[class]` + `— <date>` age, groups by class, flags malformed (missing date) + **FORBIDDEN on-`except`** markers, surfaces any class at **N≥3** (promote to project/seed lift). Advisory query (exit 1 on defects); requires a real `[class]` so it never trips on the prose that *defines* the token (the placeholder-exclusion lesson). The analogue of a keeper `check_*` for *deferred-remediation* shapes ([[methodology-codification-pipeline]]).

The `codify` class gets a second surface — the **`check_codification_debt` keeper** in the compliance gate (built 2026-05-25). It reuses the *same* parser (`markers_of_class` over the shared `_iter_markers` — one parser, two surfaces) but runs *always-on* inside `check_all_products`, so a deferred codification surfaces every gate run, not only when someone remembers to sweep. `[codify]` markers are `warning` (sanctioned, non-blocking); malformed/on-`except` are `high`; backlog ≥3 adds a "run `/codify` sweep" warning. This is the bridge from the advisory scan into the keeper gate — the `/codify` command's *detection* half mechanized.

---

## Composition / codification
- Connects to [[branching]] §6 (self-improvement loop) — an in-flight bump too small/out-of-scope to fix now is left as a `NOC-REMEDIATE` marker, swept into the batch later; the in-code sibling of the `findings.md` capture surface.
- Reconciles with: [[logging-at-except]] (never an error-suppressor) · [[accept-with-rationale]] (the durable-register sibling) · [[project-execution]] (defer-with-destination · the recurrence rule).
- Codification: s1 emerged 2026-05-25 (user: *"agents leave greppable pattern comments on code for remediation, so we might evaluate them in batches in future moments"*) → s2 memory → s3 this doc + CLAUDE.md §1 pointer; s4 = `scan_remediation_markers` (built 2026-05-25 via the `/codify` command — `projects/codification-backlog-drain/`).
