# Entre sessões — session context (saved 2026-11-01, before an OS restart)

Read this first to resume. Then `01-EVALUATION.md` and `02-PLAN.md`.

## Naming (owner, emphatic)

- **Nós no Limiar** = the BRAND and COMPANY (Mônica Tangerino, psicanalista).
- **Entre sessões** = ONE of its apps: the diary between analysis sessions. Never call the app "Nós no Limiar".

## Where things are

| What | Path |
|---|---|
| Specs from the creator agent (guide v1.0, 31/10/2026) | `projects/app/entre-sessoes/guia-diario-entre-sessoes/` (original copy in `~/Downloads/guia-diario-entre-sessoes/`) |
| Design system v2.1 | `projects/app/entre-sessoes/design-system/Design-System-Nos-no-Limiar.md` — byte-identical to the specs' `09-referencias/design-system-v2.1.md`. THE visual base (D4) |
| Live web app (current) | https://claude.ai/artifact/VeCEaLoN3gFxYn18Abjcpu ("Diário entre sessões", published artifact template v21 — a template version, not the DS version) |
| My study of it (outside git) | `~/Documents/repository/NoctusAI/_private-studies/diario-entre-sessoes/` — `MAP.md` (full map), `source/page.html`, `local/index.html` (isolated copy), `ui/screens-v2/` (47 states @3x + `INDEX.md`), `ui/shoot.cjs` (re-runnable Playwright capture: `node ui/shoot.cjs <url> <outDir>`, needs playwright from `noctusai/products/core/frontend/node_modules`) |
| App repo | `~/Documents/repository/NoctusAI/entre-sessoes` (Expo SDK 58, GitHub `jraphaelsst/entre-sessoes`, public; was `limiar-app`). Work branch `feat/entre-sessoes` |

## Done so far

1. limiar-app upgraded to **Expo SDK 58** (RN 0.88.1, React 19.3) on branch `chore/expo-sdk-58`, commit `a8effda` — NOT merged, NOT pushed. tsc 0 · lint ok · jest 22 suites/1009 tests · expo-doctor 20/20. (An Expo server was running on port 8082; port 8081 had a foreign stale SDK-57 process, pid 82492, not killed.)
2. Mapped the artifact end to end (code + UI) → `MAP.md`; 47-state screenshot pass.
3. Graded my map against the creator's spec → `01-EVALUATION.md`.
4. Decisions (João):
   - **D1** build Entre sessões inside **limiar-app**, renamed.
   - **D2** **delete** limiar-app's current content (activities, games, reflections, "Quer pensar", safety pack).
   - **D3** design system = v2.1 above (replaces limiar-app's mockup-v0 theme: wine #651B19/ink #222 → wine #5C0003, brown #4B291D, cream #F5EFE5, rose #C9826C; Lora/Cormorant → Bodoni Moda + Inter).
5. Plan drafted → `02-PLAN.md`. **Nothing built yet.**

## Decided 2026-11-01 (after restart) — P0 started

- **D4** visual base = **design system v2.1** (not the artifact template "v21", not the dark "teste").
- **D5** full rename (name, slug/scheme/bundle id, EAS project, GitHub repo → `entre-sessoes`).
- **D6** Expo Go → EAS internal tracks **+ a hosted web link**. Open: where to host it (plan §5 #3).
- Go given for P0.

## P0 done (2026-11-01) — next: P1 (content + domain) ∥ P3 (UI kit)

App repo `feat/entre-sessoes` @ ae9abad (pushed; `main` = SDK 58 @ a8effda, pushed): renamed (bundle id
`br.com.entresessoes`, no EAS project yet), previous app deleted, one-screen shell with the safety text, DS v2.1
theme (`src/theme/`, Bodoni Moda + Inter, contrast tests), CLAUDE.md/docs re-pointed, agent `entre-sessoes` 0.1.0
(noc `products/agents/packages/entre-sessoes/`) replaces `nos-no-limiar`. tsc · lint · jest 94/94 · web export green;
not yet run on a device.

Carried into P3: no visible focus ring yet; `textSubtle` (brown 64%, 4.03:1) only for icons/large text; primitives to
replace listed in the theme commit (fe419da). Open for Mônica: `products/agents/packages/entre-sessoes/knowledge/
proposito-e-limites/precisa-da-monica.md` (11 items). Owner: git-ignored old `Nos-no-Limiar-Design-System/` (v1.0.0)
still in the app folder — delete if unneeded.

## Side effects to remember

- noc `products/agents/backend/app/public_ask/` ships a Limiar route + vendored safety pack, and `projects/limiar-open-question/` is open. D2 deletes their source in limiar-app → separate decision (pause/close), not part of this plan.
- Analisandas' real entries live in the artifact's browser storage; a native app can't read them → the artifact needs an "Exportar" before anyone switches (plan P6).

## Rules from the specs that bind every slice

Mônica's authority first; her texts verbatim (never paraphrase); no "paciente/terapia/cliente/usuária"; psychoanalysis vocabulary, feminine; no AI interpretation, no gamification; safety text (SAMU 192 / CVV 188) on every screen; nothing leaves the device without her gesture; catalogs never reordered; migrations tested and data-preserving; commits cite RN-/ADR- codes.
