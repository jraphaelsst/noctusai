# core-studio-build — our own specs for Criação de Mídia

Our build contracts, decisions, test checklist, LGPD records and design systems for **Criação de Mídia**, the headline/roteiro creation module of social-wiring (it may become its own product later). These are OUR documents.

The study of the reference app (corestudio.ai) is **private and lives outside git**: `~/Documents/repository/NoctusAI/_private-studies/core-studio/` (page maps, mechanisms, captures, screenshots, saved pages and scripts, draft prompts, the platform study). Where a doc here says `[private study: <name>]`, that is the file `<name>` in that folder. Moved out of git on 2026-10-19 (owner decision); vendor material never goes back into the repo (`KB § PATTERNS/common/app-reverse-engineering.md`).

Frozen, already-applied migration files still cite the old path `projects/core-studio/`; read it as `projects/core-studio-build/`.

## Layout

| Path | What |
| --- | --- |
| `specs/*-contract.md` | Our build contracts: pesquisa, pesquisa wave 2, cerebro, geracao, esteira, transcription. |
| `specs/instagram-insights-api.md` · `specs/branding-import.md` | Implemented API contract and the branding import runbook. |
| `specs/biblioteca-lia.md` · `ROPA-biblioteca.md` | LGPD legitimate-interest assessment and record of processing for the Biblioteca de virais. |
| `DECISIONS.md` | Every interview answer so far, and what is still open. |
| `TEST-CHECKLIST.md` | Live test checklist. |
| `MENUS.md` | Regrouped menus of the active products. |

## Design systems

| Folder | Brand | Live artifact |
| --- | --- | --- |
| `design-systems/branding-template/` | The canonical model every branding is built from | https://claude.ai/artifact/SxjLEyySWwMn2PGCyeDimW |
| `design-systems/store-visual-identity-gilson/` | Gilson Tangerino — Store Visual Identity (content: posts) | https://claude.ai/artifact/WiVN4zpVQyRRz8LVxePjEL |
| `design-systems/nos-no-limiar-monica/` | Nós no Limiar (Mônica's app identity v0.1); `source/` holds the original identity page | https://claude.ai/artifact/714oAHQjydvAJtXV7SZGj2 |
| `design-systems/noctusai/` | NoctusAI, from the website's bootstrap tokens (pre-rebrand) | https://claude.ai/artifact/5MFHPdxiwh4zTpomohQXva |

Each folder is the design system's own files (`README.md` brand book, `tokens.json`, `components/`, `assets/`, `fonts/`), so it does not depend on the artifact existing. Gilson's `assets/References/` holds the five original WhatsApp exports from `projects/store` under their original names.

## Sensitivity

Client names, workspace data, research items, chat history and Instagram profile data never go in committed files. Access tokens and CSRF tokens are always redacted.
