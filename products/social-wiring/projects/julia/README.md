# julia — our own design docs for the Lais-inspired module

Our build contracts, decisions, roadmap and test checklist for **Julia**, the WhatsApp SDR for a real-estate org (module of social-wiring). These are OUR documents.

The study of the vendor product (Lais, by Lastro) that inspired it is **private and lives outside git**: `~/Documents/repository/NoctusAI/_private-studies/lais/` (analysis, captures, screenshots, page maps, mechanisms, helper tools). Where a doc here says `[private study: <name>]`, that is the file `<name>` in that folder. Moved out of git on 2026-10-19 (owner decision); vendor material never goes back into the repo (`KB § PATTERNS/common/app-reverse-engineering.md`).

Frozen, already-applied migration files still cite the old path `projects/lais/`; read it as `projects/julia/`.

## Layout

| Path | What |
| --- | --- |
| `specs/julia-agent-contract.md` | The agent contract: runtime, channel turns, dedup, security, disclosure. |
| `specs/lais-build-contract.md` | Build contract for the SW pages and migrations (Conhecimento, Perguntas, Envio, Reengajamento, Visitas, ...). |
| `specs/sw-reconstruction-map.md` | Where each reference-app page lands in social-wiring, build order, data wiring. |
| `BUILD-ROADMAP.md` | Our module: reuse inventory, pages 0-5, risks, owner questions. |
| `DECISIONS.md` | Owner answers and open questions. |
| `TEST-CHECKLIST.md` | Live test checklist per shipped page. |

## Sensitivity

Lead names, phones, e-mails, staff lists, chat text, access codes and tokens never go in committed files (summaries only).
