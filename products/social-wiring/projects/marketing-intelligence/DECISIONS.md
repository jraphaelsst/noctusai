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

## Decided by the owner — 2026-10-16 (after the Phase-0 audit, `specs/phase0-audit.md` §6)

- **One org per person.** Mônica, Gilson and Isadora each get their own org; clients get their own org too. Isolation comes from the existing org-level RLS, so no per-marca grants are needed (closes audit risk 1).
  - ~~Consequence: a data migration out of a shared org.~~ Superseded 2026-10-19: the orgs already exist and hold no Instagram data (see below).
- **Comment bank: keep everything; only the owner and admins can see it.** No automatic deletion; raw comment text is readable only by the org's owner and admins (closes audit risk 2 as far as the owner is concerned).
  - ⚠️ Note for the record: indefinite retention of sensitive data (LGPD art. 11) runs against the necessity and storage-limitation principles (art. 6 III, art. 15–16). Mitigations kept in the design regardless: authors pseudonymised by HMAC (no usernames), anonymised quotes in reports, a ROPA entry, and the `purge_at` column present (null = keep) so a retention period can be set later without a migration.
- **Skip TikTok for now.** Phase P6 (seed TikTok adapter, `modules/tiktok`, SIMEC-TikTok) is removed from the current roadmap until the owner says otherwise. Everything is built for Instagram; the SIMEC calculator still keeps per-platform denominators so TikTok can be added later.

## Decided by the owner — 2026-10-19

- **Nothing hardcoded — every SIMEC number is configuration.** "Pure code" means only that the calculator has no I/O (it never touches the database or the network), so it can be tested against the workbooks. It does **not** mean fixed numbers. The split:
  - **Code (the operations):** a ratio over reach, a sum of interactions, a check that a reading falls inside its window, deduplication, a comparison against the profile's own baseline. These are verbs, not values.
  - **Configuration (stored per org and per profile, editable without a deploy):**
    - reading windows and their tolerance. The workbook has `7d` = 7–10 days after posting and `30d` = 30–35 days fixed inside its formulas; the chat also asked for 72 h. All of these become config rows.
    - which indicators are computed (numerator, denominator, label), so an indicator can be added or removed without code;
    - the baseline lookback (the chat's first audit covers 60–90 days) and the minimum sample before a baseline counts;
    - alert thresholds, defined as deviations from the profile's own baseline, never universal cut-offs (SIMEC rule);
    - which metrics each platform actually provides, so a missing metric shows as "not available" and is never estimated;
    - the review cadence (weekly, monthly) and the decision-validation period (the chat said 4 weeks).
  - The workbook's 200-row limit is a spreadsheet artifact and goes away.
  - Defaults ship as seed config, the values the methodology recommends. An org can override them, and every readout records which config version produced it, so numbers stay traceable (reliability rule 1).
- **Org map: one org per person for their personal brand, separate from their companies.** Checked against the database on 2026-10-19:

  | Org | Purpose | State today | Action |
  |---|---|---|---|
  | Mônica Tangerino (`indv_monica-tangerino`) | Mônica's personal brand | exists, Mônica owner, marca "Mônica Tangerino" | **SIMEC pilot lands here** |
  | Nós no Limiar (`comp_nos-no-limiar`) | separate company, not Mônica's personal brand | exists, Mônica owner + Isa admin | untouched by the pilot |
  | Isadora personal | Isa's personal brand | **missing** | create (P7) |
  | TangerISA (`indv_tangerisa`) | Isa's company/brand | exists, Isa owner, **no marca yet** | add marca (P7) |
  | Gilson Tangerino (`gilson-tangerino`) | Gilson's personal brand | exists with 2 marcas (one is a "— CoreStudio" duplicate), **no members** | add Gilson as owner; resolve duplicate marca (P7) |
  | One Consultoria (`one-consultoria`) | Gilson's company | exists, Gilson admin | untouched |
  | NoctusAI | the owner's company | exists | untouched; the owner's personal org is **not** created now |

  - No shared-org data migration is needed: no org has any Instagram media or profile snapshots yet, and Criação de Mídia rows are almost empty (1 post in Nós no Limiar, brand kits per org).
  - Isa already belongs to two orgs (TangerISA, Nós no Limiar), so multi-org membership already works.
- **P0 finding: no Instagram account is connected in any org** (`integration_accounts` has only Meta-for-Gmail/YouTube/n8n rows, in One Consultoria and NoctusAI). Before the pilot shows real data, Mônica connects her personal Instagram in her own org through Instagram Login. If the comments scope (`instagram_business_manage_comments`) lands first, a single connection covers both SIMEC and the comment bank.

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
