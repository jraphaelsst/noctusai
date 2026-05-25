# Codification backlog drain — discipline → mechanism, proactively

> **User ask (2026-05-25, verbatim intent):** *"what else do we have on our docs that could be codified? why hasn't it been doc→codified yet? Code is simpler to understand than complex text discipline — file this as a doc-codification project, then a codification-first command, evaluate whether we should or not apply, implement + refactor docs where applicable for cheaper workflows."*

## 1 · Premise (the evaluation outcome)

The user is **right with one correction**:
- ✅ Codifiable discipline → a mechanical gate is **cheaper** (keeper ≈ 0 agent-tokens/turn + removes the "did-the-agent-remember" failure mode) ∧ **more reliable**. This IS Stage 4 of `KB § PATTERNS/methodology-codification-pipeline.md`; **54 keepers** already exist.
- ⚠️ **Correction:** code ≠ replacement for prose (code = WHAT/HOW gate; prose = WHY/history/exceptions/override — keep both, trim prose to rationale+pointer, never delete) ∧ **not all discipline is codifiable** (judgment rules stay Stage 3 — §5 of the pipeline).
- 🎯 **The real gap:** codification is **reactive** (a rule earns a keeper when it painfully recurs), not a **systematic drain**. This project makes the drain **proactive + repeatable** via the `/codify` command.

## 2 · Honest headline finding (the audit result)

**The pipeline is already well-drained.** With 54 keepers, an Explore audit + verification found **few genuinely-ripe-uncodified** rules — most ripe rules ARE codified, and most remaining discipline is **legitimately judgment** (stays prose). That's a *healthy* result: the codify-instinct, applied rigorously, confirms the system works. The drain is about the *small ripe tail* + a standing command, not a mass docs→code refactor.

## 3 · Verified candidate table (CLAUDE.md §1 + memory; KB only where a rule lives there)

| # | Candidate | Predicate (deterministic?) | Recurrence | Decision | Wave |
|---|---|---|---|---|---|
| C1 | **NOC-REMEDIATE marker sweep** (`KB § PATTERNS/remediation-markers.md`) | grep `NOC-REMEDIATE[<class>]: … — <date>`, parse class+age, group, flag malformed / on-`except` / N≥3-of-class | N=1 (marker convention 2026-05-25) — but a **scan tool** (advisory query) doesn't need N≥3 | **APPLY as a `scan_*` tool** (not a gating keeper) — doc explicitly filed it | **W1 (this)** |
| C2 | **Seed integration Fake+Real+factory shape** (`KB § PATTERNS/seed-fake-real-adapter.md`) | AST-walk `seed/lib/backend/noctusai_lib/integrations/<name>/` — each ships Protocol + Fake + Real + `get_<name>_adapter` factory | **N=3** (google_calendar/google_maps/whatsapp) ✓ | **APPLY as keeper** — BUT predicate has a seed-ahead-Protocol-only edge ⇒ careful design (allowlist integrations/, exempt documented Protocol-only) to avoid seed-wide false-positives | **W1 (filed, design-first)** |
| C3 | Minimum-viable-rebuild scope (`KB § PATTERNS/minimum-viable-rebuild.md`) | `git diff base..HEAD` ∋ `products/<p>/` before rebuilding `<p>` | N=2 (doc defers to N≥3) | **DEFER** (recurrence) — candidate watch | backlog |
| C4 | CI Trivy `limit-severities-for-sarif` (`KB § PATTERNS/ci-security-gates.md §2a`) | parse `test.yml` trivy step: `format:sarif` ∧ severity-pinned ∧ missing `limit-severities-for-sarif:true` | N=1 | **DEFER** (recurrence); trivial predicate, promote on N=2 | backlog |
| — | CORE_URL hand-rolled fallback | — | — | **ALREADY CODIFIED** (`check_handrolled_core_url`) — Explore false-positive | n/a |

**Stays prose (judgment — do NOT codify):** "no quick fixes / root-cause", "accept-vs-refactor triage", "parallelize-vs-serial", "verify in prod shape" (no static predicate for "did you live-probe"), "branching-first estimate". Judgment IS the rule.

**Half-codified advisory scanners** (`scan_recurrence` / `scan_block_patterns` / `scan_cross_product_helpers`) → promote a *specific* finding to a keeper only when its recurrence hits N≥3; the scanners themselves stay advisory by design.

## 4 · Waves
- **Wave 1 (this project):** C1 `noctus.dev.scan_remediation_markers` (shipped) + C2 seed-integration-shape keeper (design-first — careful predicate, then ship).
- **Wave 2 (`codify-mechanical-gate`, 2026-05-25 — shipped):** `/codify`'s own *detection* half mechanized — `check_codification_debt` keeper reads `NOC-REMEDIATE[codify]` markers every compliance run (the always-on gate form). C2 is now a **tracked durable `[codify]` marker** in `seed-fake-real-adapter.md` (no longer prose-buried "filed design-first"); the worktree-sensitivity guard likewise migrated to a marker in `branching.md`. `KB § PATTERNS/methodology-codification-pipeline.md` §4.8.
- **Backlog (watch):** C3, C4 — promote on N≥3 (the `/codify` command re-evaluates on demand).
- **Standing:** the `/codify` command (`.claude/commands/codify.md`) is the repeatable drain — invoke it on any rule/request to evaluate + decide + apply. Deferrals now leave a `[codify]` marker (gate-tracked), not prose.

## 5 · Deliverables
- ✅ `.claude/commands/codify.md` — the repeatable evaluate→decide→apply command (default sweep = CLAUDE.md §1 + memory; KB only per-candidate).
- ⏳ C1 scan tool + C2 keeper (Wave 1).
- Three-way sync per codification (KB + CLAUDE.md/topical pointer + memory); prose kept as rationale.

## 6 · Success criteria
- The ripe tail (C1, C2) codified with colocated tests + baseline + 3-way sync; prose trimmed-to-rationale, not deleted.
- `/codify` documented + usable; future drains are one command.
- The honest boundary (what stays prose) recorded so the pipeline isn't over-drained into false precision.
