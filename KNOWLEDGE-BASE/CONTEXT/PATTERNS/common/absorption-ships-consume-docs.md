# Absorption Ships Consume-Docs

> **An absorption is not complete until its consume-side KB integration docs ship — in the SAME project that lifts the code.**
>
> This is the documentation sibling of the established absorption insight *"an absorption is a methodology-epoch merge — reconcile the derived surfaces."* When externally-developed code is absorbed into the seed library, code-lifted-but-undocumented is silent debt: products cannot discover or consume the seam, and the next agent re-derives or re-forks it.

---

## 1. The rule (R1)

When externally-developed code is absorbed into the seed library (`noctusai_lib.integrations.*` ∨ `noctusai_lib.domain.*`), the consume-side `KB § INTEGRATIONS/<x>.md` is a **required absorption deliverable** of the absorbing project — ¬ a follow-up.

The consume-side doc carries four things:
- **what-ships** — the exact `__all__` / public surface the absorbed package exposes.
- **consume recipe** — how a product wires the package via NAMED seams (import → factory → credential-resolver injection → router mount).
- **auth modes** — the resolution order (e.g. system-user → user-OAuth → Fake) and what each requires.
- **gaps** — what is out-of-scope-v1, named with a destination, never silently stubbed.

Code-lifted ∧ ¬ documented ⇒ silent debt: the seam exists but is undiscoverable; the next consumer re-derives ∨ re-forks the very code the absorption was meant to centralize.

## 2. Why — the evidence

`social-wiring-absorption` (archived 2026-05-16) lifted `meta` / `whatsapp` / `google` connectors into the seed lib but shipped **zero** `KB § INTEGRATIONS` consume docs. The gap surfaced only weeks later when the user asked *"shouldn't products consume the func?"* — at which point the consume recipe had to be reverse-engineered from `__init__.py` rather than read from a doc that should have shipped with the lift.

The lift without the doc is the same shape as the broader absorption lesson: an absorption is a **methodology-epoch merge** — the MCP introspection tests, the compliance baseline, and the dependency pins were the derived surfaces that earlier absorptions had to reconcile. **Consume-docs is the same shape for the docs surface.** A package that ships without its consume-doc is a half-reconciled merge.

## 3. How to apply

The consume-side KB doc per lifted package is a **gate of the absorbing project**, not a follow-up project:

- The 10-gate absorption procedure (`KB § GUIDES/absorb-seed-workspace.md`) treats the consume-doc as part of the seed-reconcile gate — a lifted package is not "reconciled" until its `KB § INTEGRATIONS/<x>.md` exists.
- The doc is authored from the package's actual `__init__.py` `__all__` (codebase-is-source-of-truth) — not from the absorbed repo's prose, which may describe a pre-absorption shape.
- Three-way sync still applies: KB doc → `INDEX.md` row + `KB § INTEGRATIONS` map → CLAUDE.md Situation→read pointer → memory entry.

**The completeness test:** *"did this project lift code into the seed lib?"* → if yes, the consume-doc is in-scope for THIS project. Filing it as a follow-up is a deferral slip (see § 4).

## 4. Relationship to other rules

- **Sibling of *defer ≠ resolve* (R5)** (`KB § PATTERNS/common/defer-is-not-resolve.md`) — both are *completeness ≠ deferral*. R1 is the absorption-docs instance; R5 is the general scope-shrink instance. Filing the consume-doc as a follow-up is exactly the de-scope R5 forbids.
- **Instance of *codebase is source of truth*** — the consume-doc is authored from the shipped `__all__`, never the absorbed repo's stale prose.
- **Instance of *no silent errors*** — code-lifted ∧ ¬ documented = a deferred deliverable without a named destination = silent-error shape one level up.

s1 (user flagged the social-wiring gap) → s2 (memory `feedback_absorption_ships_consume_docs`) → **s3 (this doc + CLAUDE.md pointer + INDEX.md)**. s4 (a `check_*` keeper asserting every absorbed `noctusai_lib.integrations.*` package has a matching `KB § INTEGRATIONS/<x>.md`) is a viable future codification — deterministic predicate ∧ recurrence-evidenced ∧ clear remediation — but stays a candidate until the absorb cadence recurs enough to warrant the detector.

## 5. Anti-patterns

- **"The code is in; the docs can come later."** "Later" = the next agent re-forks. The doc ships with the lift ∨ the absorption is incomplete.
- **Filing `<vendor>-consume-docs` as a follow-up project.** That is R5's exact slip — in-scope work parked as a stub.
- **Authoring the consume-doc from the absorbed repo's README.** The absorbed prose describes the pre-absorption shape; author from the shipped `noctusai_lib` `__all__`.
- **Documenting only what-ships, omitting the consume recipe.** A symbol list is not a seam recipe. The product author needs the import → factory → injection → mount path, not just the export surface.

---

**Memory:** `feedback_absorption_ships_consume_docs`. **CLAUDE.md:** §1 *Absorption ships consume-docs* pointer. **Companion:** `KB § GUIDES/absorb-seed-workspace.md` (the gate home), `KB § PATTERNS/common/defer-is-not-resolve.md` (R5 sibling), `KB § PATTERNS/common/methodology-codification-pipeline.md` (the s1→s4 model this doc is the s3 of).
