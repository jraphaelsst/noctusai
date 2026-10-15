# Decisions log

Rule (same as `../core-studio/DECISIONS.md`): nothing is guessed. Every line says **who** decided it. "Owner" = Mônica speaking in the source conversations; "ChatGPT proposed" = a suggestion she did not explicitly confirm, which must be validated with the owner before building.

## Decided by the owner (2026-10-12 → 2026-10-14, in ChatGPT)

### Scope and users
- One system usable by **Mônica, Gilson and Isadora**, each analyzing their own accounts — and later **clients** ("quando eu tiver um cliente… vc me dá a solução").
- **Isa is in everything** — three operators from day one, not two.
- **Instagram and TikTok are independent** — separate metrics, analyses and reports. TikTok is new for them.
- **Automation is mandatory** — "minha rotina é complicada e não posso ficar fazendo isso na mão." Paid tools are acceptable ("não importa que tenha mensalidade"); cheaper is better, but performance comes first.
- Nobody on the team programs.

### SIMEC
- SIMEC must **collect comments and bring them in writing**, so Mônica can build content strategy and think up courses and talks from women's demands.

### Central Editorial SMM
- "**Não quero aula, quero um sistema que faça esses tópicos**" — the EBAC syllabus is a list of jobs for the system to do, not material to study.
- Works for Mônica, Gilson and Isa **separately**, like SIMEC.

### AR3
- Method defined by Mônica (from her sketch): 3 themes → 3 subthemes each → … until exhausted, **without any repetition**.
- Name **Método AR3** (ChatGPT proposed it; Mônica moved straight on to the first test).
- First test: the three roots **Maternidade, Maturidade, Vida Adulta Contemporânea** together → `content/ar3-01-…`.

## Decided by the owner — 2026-10-15 (in Claude Code)

- **Build it ourselves.** SIMEC, the Central Editorial and AR3 are built in-home as social-wiring modules; the ChatGPT Projects + spreadsheets setup is not the target. (Closes open question 1.)
- **Our own data collection — no Metricool / Make.** Collection runs on our own integrations (social-wiring's existing Meta/Instagram stack; TikTok to be added). The Metricool/Make architecture in `specs/simec.md` §7 stays as a requirements reference (what to collect, alerts, cadence), not as the implementation. (Closes open question 2.)
- **Retrieve the kits** — OK to download the SIMEC 1.0 and Central Editorial 1.0 kits from the share pages. Done the same day: both kits are in `kits/`, and the AR3 sketch is in `assets/`. (Closes open questions 3 and 4.)

## Proposed by ChatGPT — not yet validated

- SIMEC tooling: **Metricool Advanced** (US$67/mo, up to 15 brands, API, team permissions) + **Make Core** (US$12/mo) + Google Sheets + Looker Studio + OpenAI API ≈ **US$79/mo + AI usage**. Rollout: Metricool free → verify metrics → Advanced monthly → Make → AI routines.
- Running SIMEC and the Central Editorial as **separate ChatGPT Projects** per person and platform.
- Keeping SIMEC and the Central Editorial **separate but connected** systems.
- **Trello** integration for the Central Editorial's production tasks.
- Cadence: Reel readouts at 72 h and 7 days; weekly 30–45 min strategy session; monthly review; first audit over the last 60–90 days; 4-week validation period.
- Start validation with **Mônica's Instagram**, then Gilson and Isa.

## Open — to ask the owner before building

Questions 1–4 were closed on 2026-10-15 (see above); they stay listed for the record.

1. ~~**Build in-home vs ChatGPT setup.**~~ (closed) Do we rebuild these as social-wiring modules (recommended: data, permissions and LGPD under our control) — and does the team stop using the ChatGPT Projects version?
2. ~~**Metricool or our own collection?**~~ (closed: our own) social-wiring already integrates Meta/Instagram. Metricool's value may be TikTok + the comment API; confirm which accounts are connected and whether a Metricool subscription already exists ("você já possui uma conta no Metricool?" was left unanswered).
3. ~~**Kit files.**~~ (closed: retrieved) Retrieve the SIMEC 1.0 kit and the Central Editorial 27-file kit (download from the share pages, or Mônica exports them from her ChatGPT library) — the spreadsheet formulas and command prompts are the most precise spec we have.
4. ~~**AR3 sketch** — get the original WhatsApp image.~~ (closed: `assets/`)
5. **Where AR3 lives** — inside Pesquisa / Segundo Cérebro (Criação de Mídia) or as its own page?
6. **Comment data and LGPD** — retention period, who can read raw comments, anonymization rules for reports.
7. **Gilson's and Isa's diagnosis** — business goals, audience, objectives per profile (SIMEC needs them; only Mônica's are well developed).
