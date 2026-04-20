# Proposal: AI-Expansion Phase 1 — Opportunity Atlas bundled improvements

**Agent:** claude-opus-4-7
**Origin:** project:ai-expansion:phase-1
**Generated:** 2026-04-19 14:01
**Severity:** low
**Effort:** low
**Affected products:** core, erp-imobiliario, personal-finance, therapy-platform, daily-life, mailing
**Status:** pending

---

## 1. Context

Phase 1 of AI-EXPANSION-PROJECT was the Opportunity Atlas — cataloguing 48 AI UX opportunities across Core + 6 live products + AdConnect scaffold, with LGPD/effort/deps tags. This proposal bundles the retrospective observations captured while building the atlas, so they are triageable before Phase 2 (user triage) begins and influences the implementation phases.

---

## 2. Situation

The atlas is a single document (`AI-EXPANSION-PROJECT.md` §5) covering 8 products. Writing it end-to-end in one pass exposed three systemic weaknesses: the atlas is source-only (I read `services/` directories but not the live UI), LGPD tags were assigned by rule-of-thumb rather than the formal 5-question procedure, and effort sizing is gut-feel with no calibration data. These don't block Phase 2 but they shape what Phase 2's triage inherits.

---

## 3. Proposed Solution

### 3.1 Linkage — why this solution fits this situation

Each improvement strengthens the atlas's reliability as the triage input — calibrating effort estimates, grounding opportunities in real UI, and giving the `high`-LGPD items a proper review path.

### 3.2 Application instructions

#### 1. Cross-reference every atlas opportunity with the product's frontend/src/pages

**Linkage:** Atlas was written from `backend/services/` surface. Some opportunities may not match an existing or planned page, or may be misnamed vs the product's real UX vocabulary. A page-level pass catches those before triage.

**Steps:**
1. For each product with an atlas row, list the pages under `products/<name>/frontend/src/pages/`.
2. Cross-reference each opportunity to a target page (existing or planned).
3. Trim/rename opportunities that don't map to any page. Note in the row where the UI would live.
4. Re-run the count in §5 of AI-EXPANSION-PROJECT.md; update if changed.

**Risks:** Low — read-only pass + doc edit.

*Independent:* can be applied without other bundled improvements.

#### 2. Formalize LGPD 5-question review for every `high`-tagged item

**Linkage:** Atlas tags LGPD by heuristic. Items tagged `high` need the full 5-question procedure (see `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md`) before they enter any implementation phase.

**Steps:**
1. Walk each `high` row in §5.
2. For each, document: data class, legal basis, retention, transit path, subject consent.
3. If the basis is weak, downgrade to `med` or flag as blocked pending product-legal decision.
4. File results as an annex in `AI-EXPANSION-PROJECT.md` or as `LGPD-WARNINGS.md` entries (one per item).

**Risks:** Medium — the check may block items that looked shippable.

*Independent:* can be applied without other bundled improvements.

#### 3. Calibrate effort sizing against Phase 3's first concrete build

**Linkage:** S/M/L tags today are guesses. The first Phase-3 implementation is a natural calibration point — if it took 2 days and we tagged it S, fine; if L, re-tag.

**Steps:**
1. After the first Phase-3 opportunity ships, measure wall-time (backend + frontend + tests + docs).
2. Compare to the atlas tag. If off by one category or more, re-tag at least the S/M/L boundary cases in §5.
3. Document the calibration heuristic in §3 (Design principles).

**Risks:** Low — re-tagging doesn't change already-triaged items.

*Depends on:* improvement(s) #Phase 3 first implementation shipping.

### 3.3 Seed APIs / shared lib involved

N/A — change is local to the product.

### 3.4 Risks before applying

Low — bundled improvements all operate on docs, not code.

### 3.5 Alternatives considered

N/A — the situation dictates the fix.

---

## 4. Effects

When this is applied, these change:

- **Coverage:** Atlas → UI cross-reference closes a blind spot before triage.
- **Risk profile:** Formal LGPD review surfaces blocked items early, avoids shipping + retracting.
- **Ergonomics:** Effort calibration makes Phase 2 prioritization more credible.

---

## 5. Acceptance Criteria

- [ ] Fix applied to every affected product (not just the one that triggered detection)
- [ ] `python mcp/noctusai/cli.py --validate` shows 100/100 for the affected product(s)
- [ ] `python mcp/noctusai/cli.py --review --product core` files no new proposals for this issue
- [ ] Backend tests still pass for the affected product(s)
- [ ] If the change touched shared code, `python mcp/noctusai/cli.py --catalog` shows no new orphans or duplicate candidates
- [ ] Documentation updated KB-first, CLAUDE.md second (per `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md → Docs stay in sync`)
- [ ] AI-EXPANSION-PROJECT.md §5 updated with UI-resolved opportunity rows
- [ ] Every `high` row has either an LGPD approval log or a flagged-blocked reason
- [ ] Effort-calibration heuristic documented in §3 after first Phase-3 ship

---

## 6. Related files

- `AI-EXPANSION-PROJECT.md` — Phase 1 deliverable — the atlas itself.
- `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md` — 5-question procedure.
- `LGPD-WARNINGS.md` — Destination for blocked `high` items.
