# Defer ≠ Resolve — Filing In-Scope Work Is a Slip, Not a Triage Outcome

> **A follow-up project filed for work already inside the active project's explicit scope is a deferral slip, not a triage outcome. Resolve it in-project.**
>
> The recurrence/triage register (`[F]`/`[R]`/`[A]` + "file a follow-up project") exists for newly-discovered cross-cutting work — NOT for de-scoping the active brief. Filing in-scope work as a parked stub is a scope-shrink dressed as triage = silent-error shape one level up: the deliverable becomes a stub instead of shipped work.

---

## 1. The rule (R5)

"File a follow-up project" ∧ the triage register `[F]`/`[R]`/`[A]` are for **newly-discovered cross-cutting** work surfaced *during* execution — work that was not in the original ask and genuinely belongs elsewhere ∨ needs a decision. They are **¬** a mechanism for shrinking the active brief.

**The scope test (apply before filing ANY follow-up):**

> *"Was this in the user's original explicit ask ∨ the project's stated scope?"*
>
> - **Yes** ⇒ resolve in-project. Filing it is the slip.
> - **No, and it is genuinely a different domain ∨ needs a decision** ⇒ file with a named destination (correct triage).

In-scope ∧ resolvable-now ⇒ do it. A filed stub for in-scope work is not a deferral — it is the deliverable not being shipped, relabelled.

## 2. Why — the evidence

`gmail-seed-lift` was filed 2026-05-17 as a follow-up stub for the Gmail adapter — even though the user's original ask was explicitly *"google = calendar + maps + youtube + drive + **gmail** + …"*. Gmail was never out-of-scope; it was in the original explicit enumeration. The user flagged it directly: *"should've never been filed, should've been resolved at once."* Resolution: the Gmail lib adapter was built in-project ∧ the `gmail-seed-lift` stub was `git rm`'d the same project. The follow-up project existed for ~1 day purely as a scope-shrink artifact.

The slip is seductive because it *looks* like disciplined triage — there is a filed destination, there is a slug, there is a stub `.md`. But the destination test is not "is there a destination?" — it is "**was this mine to ship in the first place?**"

## 3. How to apply

Before filing any follow-up project ∨ stub:

1. Re-read the user's **original** ask ∧ the project's stated §4 scope. Not the current mental model of scope — the original written scope.
2. Apply the scope test (§ 1).
3. In-scope ∧ resolvable-now ⇒ resolve in-project, never file. The cost of resolving now is the cost the project signed up for.
4. Genuinely out-of-domain ∨ needs-a-decision (a different product's RLS, a schema decision, a separate vendor) ⇒ file with named destination — that is correct triage, not the slip. (Example of correct routing: social-wiring RLS was legitimately routed out of the connector project — different product, needs a schema decision.)

The slip and the legitimate triage are distinguished entirely by the scope test, not by the presence of paperwork.

## 4. Relationship to other rules

- **Sibling of *absorption ships consume-docs* (R1)** (`KB § PATTERNS/absorption-ships-consume-docs.md`) — both are *completeness ≠ deferral*. R1: the consume-doc is in-scope for the absorbing project; R5: any in-scope work is in-scope for its project. Filing the R1 consume-doc as a follow-up is a textbook R5 violation.
- **Sibling of *fix-on-contact for pre-existing debt*** (CLAUDE.md §1) — bumped in-scope debt is fixed in-flight, not surface-only / filed-only.
- **Sharpens the recurrence/triage rule** (`KB § PATTERNS/project-execution.md § 2.7`) — triage outcomes apply to *newly-surfaced* patterns; they do not license retroactively de-scoping the brief that surfaced them.
- **Instance of *no silent errors*** — a deferred deliverable whose true destination is "this project, now" is a silent scope-shrink one level up.

s1 (user flagged `gmail-seed-lift`) → s2 (memory `feedback_defer_is_not_resolve`) → **s3 (this doc + CLAUDE.md pointer + INDEX.md)**. s4 is unlikely: the scope test is irreducibly judgment-dependent (it requires reading the user's *original intent*), so this rule legitimately stays at s3 — a `check_*` cannot decide "was this in the original ask?"

## 5. Anti-patterns

- **Filing a stub for the hard 20% of the brief and shipping the easy 80%.** The stub is the deliverable not shipped; the project reports "done" while incomplete.
- **"There is a filed destination, so it is triaged."** Destination presence ≠ legitimacy. The test is the scope test, not the paperwork.
- **Re-reading the *current* scope mental-model instead of the *original* written ask.** Scope drifts in an agent's head mid-project; the original written ask is the anchor.
- **Treating user enumeration ("X = a + b + c + d") as a menu.** Every enumerated item is in-scope; dropping one is the slip.

---

**Memory:** `feedback_defer_is_not_resolve`. **CLAUDE.md:** §1 *Defer ≠ resolve* pointer. **Companion:** `KB § PATTERNS/absorption-ships-consume-docs.md` (R1 sibling), `KB § PATTERNS/project-execution.md § 2.7` (the triage rule this sharpens), `KB § PATTERNS/methodology-codification-pipeline.md` (why this stays s3).
