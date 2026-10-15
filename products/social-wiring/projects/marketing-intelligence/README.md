# marketing-intelligence — reference material

Three marketing systems that Mônica designed with ChatGPT (persona "Shelly") between 2026-10-12 and 2026-10-14, extracted 2026-10-15 from the owner's shared conversations so they can be **built in-home inside social-wiring**, next to Criação de Mídia (`../core-studio/`).

| System | What it does | Spec |
| --- | --- | --- |
| **SIMEC** — Sistema de Inteligência de Marketing e Estratégia de Conteúdo | Analyzes performance (Instagram and TikTok, strictly separate) and steers decisions by results; module 2 collects comment text and turns audience demand into content / course / talk opportunities. | `specs/simec.md` |
| **Central Editorial SMM** | Does the work of a social-media manager (research, planning, scripts, captions, scheduling, comments, campaigns), built on the EBAC Social Media Marketing syllabus. Consumes SIMEC's results. | `specs/central-editorial.md` |
| **Método AR3** — Árvore de Ramificação Tripla | Idea-generation method: 3 root themes, each split into 3, recursively, with no repetition, until exhausted. | `specs/ar3-method.md` |

How they fit: **AR3** fills the topic bank → **Central Editorial** plans and produces → the profiles publish → **SIMEC** measures and reads the comments → results and audience demand feed the next AR3 / planning round.

## Who

- **Mônica ("Mô")** — psychoanalyst; brand **Nós no Limiar** (women, maturity, motherhood, adult life; books, community, courses, talks). Design system: `../core-studio/design-systems/nos-no-limiar-monica/`.
- **Gilson** (@gilson_tangerino) — real-estate market. Design system: `../core-studio/design-systems/store-visual-identity-gilson/`.
- **Isadora ("Isa")** — art, architecture, authorial repertoire; works on everything with the other two.
- Future: clients, each isolated.

All three are operators, each with their own data. Nobody on the team programs, so the in-home build replaces the "ChatGPT Projects + spreadsheets + Make" setup the conversations proposed.

## Sources

| Conversation | Share link | Became |
| --- | --- | --- |
| "Explicar estratégia baseada em dados" | https://chatgpt.com/share/6ace496c-f09c-83e9-be15-db9b58bedb99 | `specs/simec.md` |
| "Leitura da página do curso" | https://chatgpt.com/share/6ace4990-4280-83e9-b36b-104eb8f5f8eb | `specs/central-editorial.md` |
| "Expansão Infinita De Ideias" | https://chatgpt.com/share/6acee3e1-516c-83e9-8b8d-0fd488e59956 | `specs/ar3-method.md` + `content/ar3-01-maternidade-maturidade-vida-adulta.md` |

The share pages render with JavaScript (a plain fetch returns only the title); they were read in the owner's Chrome. The links are the recovery pointer for anything not copied here.

**Not retrieved yet** (see `DECISIONS.md` § Open):
- SIMEC 1.0 kit — zip + install instructions, manual, profile registration form, Instagram and TikTok spreadsheets (ChatGPT sandbox files; download buttons on the share page).
- Central Editorial 1.0 kit — 27 files (instructions, commands, per-profile dossiers, CSV bases).
- Mônica's hand-drawn AR3 sketch (WhatsApp image, 2026-10-12).

## Layout

| Path | What |
| --- | --- |
| `DECISIONS.md` | What the owners asked for (decided) vs what ChatGPT proposed (unvalidated), and the open questions. |
| `specs/simec.md` | SIMEC: modules, reliability rules, cadence, v2 automation architecture, comments module, API limits, LGPD. |
| `specs/central-editorial.md` | Central Editorial: EBAC syllabus mapping, environments, commands, loop with SIMEC, SIMEC-vs-Central matrix. |
| `specs/ar3-method.md` | AR3 rules, numbers, command, and its first application's skeleton. |
| `content/ar3-01-maternidade-maturidade-vida-adulta.md` | AR3 application 01, the full tree (3 roots → 729 microthemes): a ready topic bank for Mônica's content. |

## Status

Reference only — **no code yet**. Nothing named SIMEC / Metricool / AR3 exists in the codebase (checked 2026-10-15). Before building, run seed-first discovery: social-wiring already has Instagram components, Segundo Cérebro, Pesquisa, geração, and Meta integrations that may cover parts of the data collection Metricool was proposed for.

## Sensitivity

The conversations name the three owners and their business plans. The comment module (SIMEC module 2) will process audience members' personal and possibly sensitive disclosures — **LGPD applies** even to public comments; design for restricted access and anonymized reporting from the start.
