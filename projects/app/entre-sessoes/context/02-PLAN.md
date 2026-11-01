# Entre sessões — implementation plan (draft for João)

Brand/company: **Nós no Limiar**. App: **Entre sessões**.
Date: 2026-11-01. Status: APPROVED 2026-11-01 (João: go). **P0 done** (see 00-CONTEXT). Next: P1 ∥ P3.

Inputs:
- Specs: `noctusai/projects/app/entre-sessoes/guia-diario-entre-sessoes/` (guide v1.0, 31/10/2026)
- Design system: `noctusai/projects/app/entre-sessoes/design-system/Design-System-Nos-no-Limiar.md`
  (v2.1, byte-identical to the specs' `09-referencias/design-system-v2.1.md`)
- My study: `_private-studies/diario-entre-sessoes/` (MAP.md, 47 screen states, `ui/shoot.cjs`)

## 0 · Decisions already taken (João, 2026-10-31 / 11-01)

| # | Decision |
|---|---|
| D1 | Build in the **limiar-app** Expo repo, renamed to Entre sessões |
| D2 | **Delete** limiar-app's current content (activities, games, reflections, "Quer pensar", safety pack); git history is the only record |
| D3 | Design system = v2.1 (the file above). Replaces limiar-app's mockup-v0 theme (and the older, git-ignored `Nos-no-Limiar-Design-System/` v1.0.0 bundle) |
| D4 | **Visual base = design system v2.1.** Not the artifact's published template (`template_v21.html` — "v21" is an artifact template version, unrelated to the DS version) and not the dark "teste" variant. Where either template differs from DS v2.1, DS v2.1 wins (authority order: Mônica → paleta/logo → DS). No switchable variants |
| D5 | **Full rename:** app name "Entre sessões", slug/scheme/bundle id `entre-sessoes`, EAS project and GitHub repo `limiar-app` → `entre-sessoes` |
| D6 | **Distribution:** Expo Go for Mônica's review → EAS internal tracks, **plus a hosted web link** from the start |

## 1 · What changes when the specs (written for a web page) land in Expo

| Spec assumption | In our Expo app |
|---|---|
| Single HTML + `build.py` + base64 images | Normal Expo assets (`assets/images/*.webp`), no build script |
| localStorage → IndexedDB (phase 1) | One `repositorio` over device storage (see D-open 4). The spec's contract is kept 1:1, in TypeScript |
| PWA + Safari 7-day eviction risk | Gone on native. Still true for the web link (D6) → the web build must show the spec's eviction/private-tab warning and push Backup early (P5 before the web link goes out) |
| Google Fonts (IP leak, ADR-12) | Bundled with `@expo-google-fonts/bodoni-moda` + `inter` — solved by construction |
| `innerHTML` / `el()` / CSP rules | N/A in React Native (Text never parses HTML); CSP headers apply to the hosted web link (D6) |
| Clipboard / WhatsApp link | `expo-clipboard` / `Linking.openURL('https://wa.me/…')`. The 3500-char cap stays (RN-21) |
| Backup download/upload | `expo-file-system` + `expo-sharing` (export) and `expo-document-picker` (import) |
| Backup encryption (Web Crypto AES-GCM, PBKDF2 600k) | Hermes has no `crypto.subtle`. Needs a pure-JS lib (@noble/ciphers + @noble/hashes); PBKDF2 at 600k iterations may take many seconds on a cheap phone → measure before promising it (D-open 5) |
| Phase-0 data model (indexes `q`, `awakened`) | We start directly at **v2** (ids p1..p5, d1..d6, `questionText`, `updatedTs`, `levar` always present). v1 only exists as an IMPORT format |

## 2 · Reuse / delete / new in limiar-app

**Keep (rebuild on DS v2.1):** Expo Router + TS setup, `src/lib/a11y.ts`, the `storage.ts` pattern (validate-on-read,
never silently drop — file deleted in P0, its old keys were all previous-app; P2 rebuilds it as `dados/armazenamento.ts` from git history a8effda), `src/theme/` structure + contrast tests, `components/ui` primitives that survive the restyle
(AppText, Button, IconButton, Screen, BackBar, CheckItem, Chip/OptionPill), `tools/sim` walk, `agents/` (mobile-dev;
the `nos-no-limiar` content agent re-pointed to the new guide), verify chain in CLAUDE.md.

**Delete (D2):** `src/app/{atividade,atividades,jogos,mundo,reflexao,sofa,boas-vindas,…}`, `(tabs)/{explorar,perfil,salvos}`,
`src/data/*`, `src/lib/{recommend,reflexao,steps,share}`, `src/state/*` except storage, `safety/`, `tools/revisao`,
`docs/spec/especificacao-mestre-v1.0.md` + `docs/plan/fase-1-mvp.md` (superseded), Lora/Cormorant fonts, their tests.

**New:**
```
src/
  conteudo/   emocoes.ts perguntas.ts despertares.ts levar.ts citacoes.ts textos.ts   (data only, stable ids)
  dominio/    regras.ts (isLevar, janelaSeteDias, filtrar, contar*) · mensagem.ts (montar, linkWhatsApp)   (pure, `agora` injected)
  dados/      repositorio.ts (the spec's contract) · armazenamento.ts (adapter) · esquema.ts (validators)
              exemplos.ts · backup.ts · legado.ts (v1 import from the web diary)
  app/        _layout (Abertura gate) · (tabs)/{semana,registrar,levar,resumo,como-usar}
  components/ RegistroCard, FiltroTile, PassoHeader, CitacaoCard, AvisoSeguranca, Rodape, …
```
Every screen shows the safety footer (RN-28, P4).

## 3 · Phases (each ends green: tsc → lint → jest → web export --clear → Expo Go)

| Phase | Content | Done when |
|---|---|---|
| **P0 · Ground** | Merge `chore/expo-sdk-58` → main. Branch `feat/entre-sessoes`. Rename (app.json `name` "Entre sessões"; scheme/slug/bundle per D-open 2). Delete old content (D2). DS v2.1 tokens (4 colors + opacities, type scale, space, radii) + fonts; contrast tests for every allowed pair, forbidden pairs asserted. CLAUDE.md + agents re-pointed to the guide | App boots to an empty Entre sessões shell; old tests gone, theme tests pass |
| **P1 · Content + domain** | Catalogs with stable ids (16/5/6/3 + 43 quotes, texts verbatim from `04-textos-oficiais.md`). Pure rules RN-08/10/11/13/14/19/21/23–27 + message template | Unit test per RN, incl. the spec's edge cases (23:59/00:00, ties, `levar:false`+`bring:'sim'`) |
| **P2 · Data** | `repositorio` (listar/obter/salvar/marcarLevar/apagar/apagarExemplos/config/disponivel), v2 validators, example seeding once (RN-16), storage-failure + quota handling that never loses typed text | Repository tests with a fake adapter; corrupt-data test reports, doesn't wipe silently |
| **P3 · UI kit** | DS components: primary/secondary button, field, search, tag, filter tile, entry card, step header + progress, tab bar (5 tabs, ADR-09), safety block, toast, empty states. 48px targets, focus, 200% text | Sim walk default + max text |
| **P4 · Screens** | Abertura (T0), Semana (T1), Registrar 7 steps (T2), Levar (T3), Resumo (T4), Como usar (T5), footer. Draft survives tab switches (in-memory) | Spec E1–E13 as jest/RTL flows; screen-by-screen compare against `screens-v2` |
| **P5 · Backup** | Export JSON (backup.schema v2, real entries + nome/sessão), import with merge by id (`updatedTs` wins; tie rule defined, see §4), summary "N novos, M atualizados", never delete on import. Optional encryption only if D-open 5 says yes | E15 adapted; round-trip test on a clean install |
| **P6 · Bridge from the web diary** | Analisandas' entries live in the claude.ai artifact's browser storage — the native app can't read it. Add "Exportar meus registros" to the artifact (v1 dump), and `legado.ts` imports it into v2 (E14 rules) | Import of the 3 examples + a `levar:false`/`bring:'sim'` record keeps the same Levar marks |
| **P7 · QA + approval** | `shoot.cjs` adapted to the web export → side-by-side contact sheet vs the current app; device pass on a small Android; report to Mônica (her rules: plain words, options, screenshots) | Mônica approves screenshots (acceptance criterion 10) |
| **P8 · Distribution** | D6: Expo Go internal → EAS TestFlight/Play internal track + hosted web link (host per open #3) with CSP, no analytics, self-hosted fonts | Web link + both internal tracks reachable by Mônica |

Parallelism: P1 and P3 are file-disjoint after P0 (two agents). P2 after P1. P4 needs P2+P3. P5/P6 after P2.

## 4 · Fixes we carry in (from my map vs the spec)

No approval needed (behaviour/bug):
- Step error clears as soon as the field becomes valid (my gap #12; spec misses it).
- 40-entry cap → "Ver mais registros" paging (RN-12 / roadmap 0.3).
- Backup merge tie: same `updatedTs` → keep local, count as "ignorado".
- Save `questionText` with every entry (ADR-10).

Need Mônica (text or rule):
- "Trocar meu nome" (B8) — wording.
- Como usar "botões redondos" → squares (B12) — wording.
- Tag oddities: a "Sim" entry unticked in Levar shows no tag; a "Talvez" entry ticked still sits under the Talvez filter. Keep, or change?
- Resumo total counts examples (RN-24). Keep?
- Quote changes on every app open vs once a day.
- Search ignores the chosen question's text. Include it?
- All new texts (backup, import, export in the artifact, name change).

## 5 · Open decisions (blocking where marked)

| # | Question | Recommendation | Blocks |
|---|---|---|---|
| 1 | ~~Visual base~~ | **Decided D4:** DS v2.1 | — |
| 2 | ~~Rename depth~~ | **Decided D5:** full rename | — |
| 3 | Distribution decided (D6, web link included). Still open: **where to host the web link** (EAS Hosting, or the noc fleet via `serve_spa`) and its domain | EAS Hosting (`expo export` + `eas deploy`) — no server of ours, no data path; noc fleet only if it must live under a Nós no Limiar domain we route | P8 |
| 4 | Storage engine: AsyncStorage (already installed) or expo-sqlite? | AsyncStorage behind the repository for now (hundreds of entries fit); verify the Android size limit in P2 and switch adapters if needed | P2 |
| 5 | Encrypted backup in v1? | Ship plain export first, encryption after a speed test on a low-end phone | P5 |
| 6 | noc side: the `agents` product ships a Limiar `public_ask` route + vendored safety pack, and `projects/limiar-open-question` is open. D2 deletes their source. | Separate decision — mark the noc project paused/closed; don't touch the route in this plan | not blocking |
| 7 | Bridge (P6) edits the live artifact Mônica's analisandas use | Needs Mônica's go + whoever owns the artifact | P6 |

## 6 · Risks

- Entries in the web diary are lost if the export isn't shipped before people switch (P6 first, then announce).
- Clinical content: every text is Mônica's; no paraphrase. Agent `nos-no-limiar` reviews screens before any build goes to her.
- LGPD: on-device only, no analytics, no server (ADR-01). Phase 2 (server) is out of this plan.
