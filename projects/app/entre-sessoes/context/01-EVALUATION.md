# My map vs the creator agent's spec (2026-10-31)

Source parity: the code I mapped == the spec's `fonte/template_v21.html` (only base64-vs-placeholder diffs).
The spec also ships an unpublished dark "teste" variant (`template.html`) — not visible from the artifact.

## Matched exactly
6 storage keys; record shape; `isLevar`; catalogs 16/5/6/3 + 43 quotes; required steps; limits
(1500/2000/30/40); 40-card cap; 3500-char WhatsApp cap; examples never in Levar but counted in Resumo;
message template; delete confirmations; private-tab warning; tokens, fonts, 480px column.

## What I missed (findable in code)
1. Quote counter starts at random 0–999; Resumo tie-break order not written.
2. Stale copy: Como usar says "botões redondos" but filters are squares.
3. Stored indexes (`q`, `awakened`) → reordering catalogs corrupts old records (not flagged).
4. Platform risks: Safari 7-day eviction; Google Fonts sends IP (LGPD).
5. No way to change the name after the opening screen.
6. Used "patient" in MAP.md (forbidden vocabulary).

Only the creator/owner could supply: purpose + clinical limits, authority order, approved deviations
(18px body, 13px tabs), the teste variant, build pipeline/asset names, ADRs, roadmap.

## Weaknesses in the creator agent's spec
1. Says v21 is official but calls `template.html` (teste) the source of truth; its "official texts"
   (Como usar step 2, no name) come from the teste version → would ship unapproved copy.
2. Codifies current behaviour as rules without auditing: "Sim" entry unticked shows no tag; "Talvez"
   entry ticked stays under Talvez filter; Resumo total counts examples; search ignores question text.
3. Missed bug: step error stays after the fix (esp. step 5); test E4 only checks it appears.
4. Backup merge "newest updatedTs wins" — v1 never bumped a timestamp on Levar changes; no tie rule.
5. No screenshots despite requiring them for tests and approval (our screens-v2 + shoot.cjs fill it).
6. Target architecture (plain-JS PWA, Postgres + E2E crypto before legal review) doesn't fit our
   environment; one therapist's WhatsApp hard-coded in rules and DDL.

Strengths to keep: clinical principles, writing rules, RN rules, ADR log, migration plan.
Lessons saved as memory `reverse-engineer-spec-gap-checklist`.
