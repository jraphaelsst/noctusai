# DECISIONS — clinical tools + Entre sessões in monica

## Decided (owner, 2026-11-02)

| # | Topic | Decision |
|---|---|---|
| D1 | Home | A feature **inside monica**. monica's patients (`clients` organ) are the data source. Not a new product. |
| D2 | Posture | The reference app is a reference for *what the feature needs*, not a template. We design our own model, properly: few orthogonal concepts (`ENGINE.md`). No copied content, wording or structure. |
| D3 | Engine | **Seed organ**, consumed by monica. Entre sessões native app / therapy-platform reuse it later without a fork. |
| D4 | Patient side | **Entre sessões web area inside monica**, personal link, no login. Diary + tools live there. The native Entre sessões app comes later on the same organ API. |
| D5 | Pause | Progress is saved on the server after every step, and the patient resumes at the same step from the same link. |
| D6 | Quick exit | Instant neutral screen, no Back return, nothing left on the device. On the next open **the patient chooses** keep or discard. |
| D7 | Tools as data | A tool is a versioned document (5 question kinds · 3 modifiers · 6 result blocks). Answers are stored by stable ids and pinned to the tool version. |
| D8 | First release | **6 pilot tools**, one per theme, in our own words, gender-neutral; covers every kind + modifier and one sensitive tool. |

## Proposed — awaiting owner/Mônica

### P1 · Themes (ours)
Relação consigo · História · Vínculos · Corpo e rotina · Repetições · Desejo e futuro.
These are a first draft for Mônica to rename in her own clinical language.

### P2 · The 6 pilot tools (concepts only; content to be written with Mônica)

| Theme | Pilot concept | Kinds + modifiers it exercises | Result blocks |
|---|---|---|---|
| Relação consigo | **A voz que eu uso comigo**: how one speaks to oneself across everyday situations, and what one would say to someone dear | `choose`+`for_each` · `write`+`when` | `map` · `tally` · `quotes` |
| História *(sensitive)* | **O que eu perdi e o que ficou**: losses and what remains of them | `choose` (multi, `allow_other`) · `order` · `write` | `quotes` · `reflection` (quick exit tested here) |
| Vínculos | **Quem está perto**: placing people in close / middle / far circles | `group` · `choose`+`options_from` | `chart:circles` · `quotes` |
| Corpo e rotina | **Minha semana de verdade**: a week as lived, and where energy goes | `choose`+`for_each`(days, `one_per_screen`) · `distribute` | `map` · `chart:share` |
| Repetições | **O que volta a acontecer**: recurring situations, ranked, and what precedes them | `choose` (multi) · `order` · `write`+`when` | `chart:bars` · `quotes` |
| Desejo e futuro | **O que eu quero e o que me segura**: wishes against what holds them back | `write` · `distribute` · `choose`+`options_from` | `chart:scale` · `session_questions` |

Coverage: all 5 kinds, all 3 modifiers, all 6 blocks, 1 sensitive tool.

## Open questions

| # | Question | Notes |
|---|---|---|
| Q1 | Can Mônica edit or create tools in the UI from day one? | The engine supports org-owned tools (`org_id`). The editor is a separate slice. |
| Q2 | Which parts of the Entre sessões diary specs (`projects/app/entre-sessoes/guia-diario-entre-sessoes/`) come into the web area, and when? | Specs were written for the native app. |
| Q3 | LGPD: consent text on first open; answer retention; can the patient see past results; what happens on patient deletion | Health data, art. 11. Review by the `security` advisor before build. |
| Q4 | Link life: valid until completed + N days? revocable only? | No time bomb mid-exercise (the reference's 60-min links were a defect). |
| Q5 | Does the patient also receive their own result (e.g. a PDF), or only Mônica? | |
| Q6 | Organ name in the seed | Proposal: `guided-tools` (generic: also usable outside clinical contexts). |
