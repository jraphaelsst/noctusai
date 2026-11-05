# Agent refinement — tech-lead running log

## Wave 1 — slice returns

### W1-S4 frontend-engineer — merged 13b809e94
- Commits c408363be (L1 + canon) · 7f228e16e (fix-on-contact). Canon `frontend/frontend-craft-canon.md` 857 lines, 66 URLs verified (LBI art. 63 unverified — planalto timeout).
- L1 67 → 79 lines (52 body). Over the ~64 target: §3b sections + 10 new rules.
- Fixed on contact: frontend.md:40 invalidate advice + staleTime vs seed 5-min default; useMemo section → canon §1.3; 01-CORE.md rewritten to code reality; asleep banners on 02/03/04; 2 out-of-glossary glyphs.
- Audit corrections: seed `Dialog` is NOT Radix (no focus trap/return; Radix = CardHubDialog*); react-hook-form declared in 4 FEs but used once; dual-React vitest gap fixed 2026-05-29 (only in symlinked worktrees); React 18 not 19.
- Wave-3 todo: INDEX.md:487 prototype row still says "never mock-data" (stale vs mockup-first); CLAUDE/frontend.md:20 asleep-products note; no FE domain docs for social-wiring/agents/monica.

## Follow-up code defects (added during the run)
- NEW (S4): stored XSS path — FaqAccordion.tsx:43 JSON-LD writes admin-editable FAQ unescaped (server escapes `<` at website_html.py:137, client JSON.parse undoes it at settings.tsx:32). Admin-only write.
- S4: seed Dialog lacks focus trap/initial focus/return; 3 date-format families in seed (N=3 → triage); core uses plain `lazy` on 38 routes; seed ErrorBoundary copy + raw error.message toast; 5,612 *ByTestId vs 1,367 *ByRole.
