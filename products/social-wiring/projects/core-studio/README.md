# core-studio — reference material

Everything extracted from **corestudio.ai** (studied 2026-10-05, read-only, on the owner's own account) to rebuild its headline and roteiro creation system in-home as **Criação de Mídia**, a module of social-wiring (it may become its own product later). Nothing here is code yet; the build has not started.

Start with `specs/page-map-v2.md` (authoritative page map, 2026-10-06) and `specs/mechanisms.md` (how each mechanism works behind the pages), then `docs/platform-study.md` and `DECISIONS.md`. Where the 2026-10-06 files disagree with the 2026-10-05 study, the 2026-10-06 files win; `page-map-v2.md` §0.2 lists every correction.

## Layout

| Folder | What |
| --- | --- |
| `docs/` | The platform study doc (Markdown and PDF export) and its "Spec — Pesquisa & Cérebro" tab. Live version: https://claude.ai/code/artifact/7ce00856-d593-457d-9a6e-99fa58cc8b9c (the Markdown export drops the 19 embedded screenshots; they are in `screenshots/`). |
| `DECISIONS.md` | Every interview answer so far, and what is still open. |
| `specs/` | Build specs and analyses. **`page-map-v2.md`** (every route, its params, sections, fields, data sources, endpoints, categories; route × endpoint matrix; corrections to the first map) · **`mechanisms.md`** (research variables, brains, the three "Extrair" mechanisms, headline and roteiro generation, Biblioteca, Instagram integration, chat; data model, state machines, triggers, AI calls, confidence tags, Método Audience alignment, open questions) · **`xhr-to-fetch.md`** (read-only GETs still needed, plus the GETs that must not be called) · Pesquisa + Segundo Cérebro spec (code + live, §9 wins), research-variable usage map, live variable findings, Biblioteca and roteiro analysis, front-end JS analysis. |
| `prompts/` | CoreStudio's real Pesquisa classifier system prompt, captured verbatim (the only prompt of theirs we have word for word). |
| `screenshots/` | 28 screenshots: sidebar states (01–03, 13), Minha Pesquisa (04–12), Extrair Pesquisa (14–16), Segundo Cérebro (17–24), Gerar Headlines (25–28). |
| `captures/crawl-2026-10-06/` | Fresh crawl of the owner's logged-in account: 54 saved pages (`pages/`), `inventory.json` (150 crawled URLs with headings, modals, forms, tabs, inputs, buttons, scripts, endpoints, links), and the two scripts not captured before (`js/cores.js`, `js/profileInstagramV2.js`). CSRF tokens and Instagram CDN blobs redacted. |
| `captures/raw/` | `corestudio-pages.json` and `corestudio-data.json` (the two page/API captures), `chat-conversations.txt` (the account's 29 chats with CoreStudio's HEADLINE and ROTEIRO agents). |
| `captures/pages/`, `js/`, `css/` | Saved page HTML (13 pages), their scripts and stylesheets. |
| `captures/extracted/` | Per-page split of inline scripts and text (`s_` Minha Pesquisa, `p_` Extrair Pesquisa, `c_` Segundo Cérebro). |
| `captures/analysis-work/` | Intermediate extraction output kept for traceability. |
| `design-systems/` | The four design systems in the Branding Template model (see below). |

## Design systems

| Folder | Brand | Live artifact |
| --- | --- | --- |
| `design-systems/branding-template/` | The canonical model every branding is built from | https://claude.ai/artifact/SxjLEyySWwMn2PGCyeDimW |
| `design-systems/store-visual-identity-gilson/` | Gilson Tangerino — Store Visual Identity (content: posts) | https://claude.ai/artifact/WiVN4zpVQyRRz8LVxePjEL |
| `design-systems/nos-no-limiar-monica/` | Nós no Limiar (Mônica's app identity v0.1); `source/` holds the original identity page | https://claude.ai/artifact/714oAHQjydvAJtXV7SZGj2 |
| `design-systems/noctusai/` | NoctusAI, from the website's bootstrap tokens (pre-rebrand) | https://claude.ai/artifact/5MFHPdxiwh4zTpomohQXva |

Each folder is the design system's own files (`README.md` brand book, `tokens.json`, `components/`, `assets/`, `fonts/`), so it does not depend on the artifact existing. Gilson's `assets/References/` holds the five original WhatsApp exports from `projects/store` under their original names.

## Sensitivity

`captures/` contains the account owner's name, workspace data, research items, private chat history with CoreStudio, and (in the 2026-10-06 crawl) the connected Instagram account's profile data and post metrics. Treat it as private client material. Access tokens and CSRF tokens are redacted; keep it that way for any new capture (see `specs/xhr-to-fetch.md`).
