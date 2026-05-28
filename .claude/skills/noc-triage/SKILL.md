---
name: noc-triage
description: Use at every divergence / discovery / surfaced-pattern decision point — triggers "should we accept this?", "what about X?", "divergence found", "this came up", "is this a one-off?", "F/R/A". Mechanizes the boring legs (count recurrence, surface past similar verdicts, propose the verdict from N) so the human only ratifies + writes the one-line rationale. The verdict isn't art — it's mostly bookkeeping.
version: 1.0.0
---

# noc-triage — mechanized accept-with-rationale

🔴 **Why the rule used to feel ceremonial:** the human did all the work (count, classify, write paperwork). This skill flips that — the **tools count**, the **tools surface past similar verdicts**, the **tools propose the verdict**, the human **ratifies + writes a one-line rationale**. If you ever feel like the triage is a chore, you're doing a step that should have been mechanized.

## Workflow

1. **Auto-count + auto-suggest verdict — ONE call each.**
   - For code/function/test/migration patterns: `noctus.dev.scan_recurrence` (returns count + sites).
   - For prose/methodology/architectural patterns: `noctus.dev.kb_recurrence_radar consult text="<one-line description>"` (semantic — finds patterns NOT named the same).
   - Suggested verdict from N:
     - **N=1** → suggest **[A]** (default; accept-with-rationale is cheap, kb_recurrence_radar will surface it next time).
     - **N=2** → suggest **[FLAG]** (architect-eyes; the next instance is the formalize trigger).
     - **N≥3** → verdict is **[F]** (forced; the 4th instance is structurally forbidden — `KB § PATTERNS/architect/project-execution.md`).

2. **Surface past similar verdicts — ONE call.**
   - `noctus.dev.auto_improvement_query` filter by `kind=improvement` + cosine match via `kb_recurrence_radar.consult` against the divergence description.
   - **score ≥ 0.8 hit** ⇒ a sibling triage already exists — read its rationale, COMPOSE rather than re-decide. The catalog row is now load-bearing precisely because past-you wrote it.

3. **Human ratifies + writes the one-line rationale.**
   - Override the suggested verdict ONLY with a stated reason (e.g. "N=2 but cross-cutting + matches a [F] sibling at 0.85 ⇒ promote to [F] now, don't wait for N=3").
   - Rationale shape: `<why the verdict>` — keep it one line. The catalog row is the value; long rationales never get read.

4. **Write the paperwork — ONE call (no copy-paste).**
   - `noctus.dev.codify_log target=<pattern-id> kind=improvement status=<s1-emergent|s2-memory> description="<rationale>" source_ref=<session-id>` for methodology / cross-cutting.
   - For product-local **[A]** with no methodology implication: a `NOC-REMEDIATE[accept]: <rationale> — <date>` marker at the divergence site is sufficient. `noctus.dev.scan_remediation_markers` will surface it later.
   - For **[F]** verdicts at N≥3: trigger the actual formalization (extract to seed/shared-lib/KB) in-flight — the verdict isn't done until the formalization lands.

5. **Replication-to-seed symmetry sanity** (auto-checked at codify_log time, but verify yourself): does your rationale contain "per-product" / "across N" / "mount everywhere"? Those phrases ARE the slip signal — the right count for cross-cutting concerns is ZERO. If the rationale leaks that language, your suggested-[A] should have been [F]. → `KB § PATTERNS/architect/project-execution.md`.

## Guardrails
- ⚠️ Skipping step 1 (the count) = silent-error shape. If you don't run the recurrence scan, you don't know N, and your verdict is guess-work. The scan is ~5s.
- ⚠️ Skipping step 2 (past-verdict surface) = the catalog rows die unread. The whole point of the paperwork is that step 2 can find it.
- The skill mechanizes the bookkeeping; it does NOT mechanize judgment. When step 1 says N=2 and step 2 shows a 0.85 sibling, the human still decides whether to promote-now vs wait-for-N=3. That's where rationale earns its keep.
- For verdicts you can't decide alone (cross-product impact, methodology shift, contract change), the verdict is **[SURFACE]** not [A] — block on tech-lead approval via `noctus.dev.file_proposal kind=surface`. → `KB § PATTERNS/common/dispatch-with-project-and-notes.md`.
- Triage runs AT decision time (during the work), not at wrap — `noc-wrap-up` survey will flag un-triaged divergences as unresolved s2-memory.

## Depth
`KB § PATTERNS/common/accept-with-rationale.md` (the canonical home) · `KB § PATTERNS/architect/project-execution.md` (DRY recurrence rule + replication-to-seed symmetry) · `KB § PATTERNS/common/methodology-codification-pipeline.md` (s1→s2→s3→s4 progression) · `KB § PATTERNS/common/kb-recurrence-radar.md` (the surface-past-verdicts engine).
