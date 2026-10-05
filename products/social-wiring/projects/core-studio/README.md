# core-studio — reference material

Everything extracted from **corestudio.ai** (studied 2026-10-05, read-only, on the owner's own account) to rebuild its headline and roteiro creation system in-home as **Criação de Mídia**, a module of social-wiring (it may become its own product later). Nothing here is code yet; the build has not started.

Start with `docs/platform-study.md`, then `DECISIONS.md`.

## Layout

| Folder | What |
| --- | --- |
| `docs/` | The platform study doc (Markdown and PDF export) and its "Spec — Pesquisa & Cérebro" tab. Live version: https://claude.ai/code/artifact/7ce00856-d593-457d-9a6e-99fa58cc8b9c (the Markdown export drops the 19 embedded screenshots; they are in `screenshots/`). |
| `DECISIONS.md` | Every interview answer so far, and what is still open. |
| `specs/` | Build specs and analyses: Pesquisa + Segundo Cérebro spec (code + live, §9 wins), research-variable usage map, live variable findings, Biblioteca and roteiro analysis, front-end JS analysis. |
| `prompts/` | CoreStudio's real Pesquisa classifier system prompt, captured verbatim (the only prompt of theirs we have word for word). |
| `screenshots/` | 28 screenshots: sidebar states (01–03, 13), Minha Pesquisa (04–12), Extrair Pesquisa (14–16), Segundo Cérebro (17–24), Gerar Headlines (25–28). |
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

`captures/` contains the account owner's name, workspace data, research items and private chat history with CoreStudio. Treat it as private client material.
