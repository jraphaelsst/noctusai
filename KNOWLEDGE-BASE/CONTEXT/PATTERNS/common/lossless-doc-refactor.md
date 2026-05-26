# Lossless doc-refactor — the methodology for compacting / restructuring methodology docs

> **What this is.** The standing framework for any change to the *durable doc-set itself* — CLAUDE.md, KB, MEMORY.md, `.claude/agents/*`, MASTER-PROMPTs. It exists because those docs ARE the methodology: a careless trim is silent rule-loss that surfaces as rework weeks later. Born from the 2026-05-18 session (CLAUDE.md −17%, MEMORY.md −20%, KB symbol-tighten + caveman fold-in, all zero-loss). It governs itself — this doc obeys its own rules.

When it fires (the trigger is the *task class*, not the file): the user asks to **compact / shrink / token-optimize docs**, **refactor doc/architecture structure**, **merge or split rules**, **fold in an external pattern**, or any "important change" to the methodology doc-set. Default to this framework without being asked.

---

## 1 · The prime directive — lossless by construction, proven not asserted

A doc-refactor is **lossless** ⟺ every one of these is diff-verified before/after, not eyeballed:

| Invariant | Gate (run it; quote the result) |
|---|---|
| **Pointer-set** | `grep -oE '\`KB § [^\`]+\`'` (+ `CLAUDE/`, `.claude/`) sorted-unique before == after. Zero dropped. A dropped pointer = a severed route to depth = loss. |
| **Rule/section** | header count (`grep -c '^#'`) + every bold sub-rule before == after. Merges keep all sub-rules; trims keep all rules. |
| **Line-structure** | no concatenated list items (`grep -n '\`- \*\*'` mid-line == 0). *2026-05-18 lesson: an Edit ate a newline, fused two bullets; the pointer-set check still passed → structure integrity is a SEPARATE gate, always run it.* |
| **Index pointer** | every memory `[Title](file.md)` line preserved (MEMORY.md is an index — the file IS the source of truth; the hook may shrink, the line never disappears). |
| **Hook-grade** | `python mcp/noctusai/cli.py --verify-kb-sync` ✓ ∧ `check_doc_symbology_drift` == 0. |

"Verification ✓" without the quoted command output is a [[feedback_no_silent_errors]] violation. Absence of loss is a *claim* — prove it with the diff.

---

## 2 · The gate ladder — aggressiveness is the user's call, never assumed

Doc-set surgery is methodology-critical ∧ semi-irreversible (a lost nuance not in any pointer target is gone). So **ask the safety bar before destructive trims** — present concrete before/after, let the user pick:

- **s-lossless** (no approval) — provably-zero-loss only: MEMORY.md hook-tightening (detail lives in `feedback_*.md`); CLAUDE.md cut only phrases the pointer target *provably* carries; bullets over their own stated word-cap trimmed to {rule + one-clause why + ALL pointers}.
- **s-moderate** (gated — show the diff first) — merge single-principle facet-bullets (every pointer kept); symbol-first tighten verbose KB docs (¬ rule/section removal).
- **s-plan-only** — produce the plan + token estimates + per-cut risk, execute in a focused session.

Recommend s-lossless-now + s-moderate-gated by default. Never jump to structural restructure unprompted.

---

## 3 · Source-of-truth trim rule

CLAUDE.md is a router; KB is depth; MEMORY.md is an index ([[feedback_codebase_source_of_truth]] ∧ [[feedback_context_budget_discipline]]). A phrase is safe to cut from the router ⟺ its pointer target **provably** carries it — open the target ∧ confirm, before the cut, never after. The file's own contract ("bodies/examples/slip-history live in the pointer target; ≤N words/bullet") makes over-cap material *by construction* duplicated → trimming to contract is lossless once the target is verified. Excised durable substance with no pointer home ⇒ inline it or STOP — don't cut.

**Registers are not prose.** accept-with-rationale catalog, ledger, divergence registers = data; their entries are the record. Symbol-tighten exposition, never "compress" a register.

### 3a · Always-doc the trim — provenance, never silent (2026-05-18)

A trim / de-drift / de-dup is **¬ a silent deletion** — it leaves a **tracked provenance breadcrumb in-place**: *when · why · what-was-removed · where-the-source-of-truth-is-now*. Applies to **both** a trim you do now (future-trimming) ∧ a trim already done that you discover lacks a breadcrumb (already-trimmed → add one retroactively, fix-on-contact). Without it a future agent re-adds the drift (the exact failure that produced the AGENT-CONTEXT.md stale roster — a hand-table re-grown after a prior silent removal), or wastes time hunting where the data went. The breadcrumb is short (a `> **Trimmed YYYY-MM-DD (always-doc-the-trim)** …` blockquote at the trim site) ∧ points at the authoritative source. Hand-maintained data that duplicates an auto-derived source is itself a drift generator → trim-to-pointer is the *root* fix, ¬ patch-the-number. This is `no-silent-errors` ∧ `durable-docs-self-contained` applied to the deletion itself. Worked example: AGENT-CONTEXT.md roster trim, this session.

**Trim-to-pointer is only valid if the pointer target is *provably* tree-derived (verified, ¬ itself a frozen literal).** Relocating hand-drift into a hardcoded generator list is **¬ eliminating it** — it just hides the same drift one layer down where the next self-test catches it later. Before pointing a doc at "the auto-derived source", **open the generator ∧ confirm it actually enumerates the tree/registry** (not a frozen `_LITERAL`); if it's frozen, the root fix is to make it derive (e.g. `parse_products_registry()` per `feedback_hardcoded_product_slug_set_keeper`), then re-point. 2nd-pass worked example (same session): the AGENT-CONTEXT roster trim pointed at `02-LANDSCAPE.md`'s "auto-derived" inventory, but `kb_sync.py:_PRODUCTS`/`ordered` were frozen literals omitting `social-wiring` — caught by the 2nd clean-context self-test, root-fixed by deriving from `parse_products_registry()` + the live schema counts. **Self-test oracle deepened:** every git-tracked `products/<slug>/` with a product `main.py` MUST appear in the authoritative roster (tree-vs-doc assertion, ¬ merely "the doc points somewhere").

---

## 4 · Symbol-first, scan-enforced

Author/refactor every doc per the caveman-aligned glossary by default — `KB § PATTERNS/common/doc-symbology.md` ([[feedback_symbol_first_authoring]]). Lossless-swap test gates each swap; prose expansion retained inline where a glossary-less reader would otherwise lose meaning. ¬ on error messages / first-paragraph / quoted-user / commits. New symbol needed ⇒ add to the glossary, never invent inline. **Enforcement teeth**: `check_doc_symbology_drift` (s4, live-parses the glossary) — platform baseline is **zero-drift**; a refactor that ends non-zero is not done. A swap that *adds* meaning fails the test ⇒ keep prose (calibrated zero-change is the rule working, ¬ a skipped deliverable).

---

## 5 · Safe parallelization — file-disjoint or inline

Independent doc tasks parallelize ⟺ **strictly file-disjoint** (per [[feedback_branching_first_orchestration]]). Architect sets up the worktree off the *real HEAD* (¬ stale main — `git worktree add -b <b> <wt> HEAD`; unpushed commits otherwise invisible, [[feedback_worktree_base_verification]]). Engineer stages+returns; **architect certifies 100% from its own true-disk context** (the invariants of §1, ¬ the engineer's self-report — [[feedback_harness_overlay_worktree_divergence]]) before merge. Not safely disjoint ⇒ do NOT parallelize: inline-architect-mode instead. Engineer touches ONLY its file-set; a needed edit to an architect-owned file (CLAUDE.md / memory) is *surfaced*, applied inline post-merge — never cross-edited.

---

## 6 · Fix-on-contact during the refactor

A defect met mid-refactor (a pre-existing stale cross-ref, a self-inflicted concatenation, a drifted memory claim vs code) is fixed in-flight THEN surfaced with root-cause + solution — never surface-only, never deferred silently ([[feedback_fix_on_contact_pre_existing]]). The refactor commit carries the fix; the lesson feeds back here (§1 gained the line-structure gate this way).

---

## 7 · Close-out — three-way sync ∧ self-application

Any methodology/rule the refactor changes lands in all layers same session: KB → CLAUDE.md (or topical) pointer → memory + MEMORY.md ([[feedback_three_way_doc_sync]]). This doc is itself proof: authored symbol-first, pointer-complete, scan-clean, indexed. Commit per [[feedback_terminal_commit_guarantee]] — no uncommitted doc-refactor residue left in the shared tree.

→ companions: `KB § PATTERNS/common/doc-symbology.md` · `KB § PATTERNS/common/methodology-codification-pipeline.md` · `KB § 01-PHILOSOPHY.md § Context budget discipline`
