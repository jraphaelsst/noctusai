# SIMEC — Sistema de Inteligência de Marketing e Estratégia de Conteúdo

Source: https://chatgpt.com/share/6ace496c-f09c-83e9-be15-db9b58bedb99 (extracted 2026-10-15). Everything below is ChatGPT's design unless `DECISIONS.md` marks it as owner-decided.

## 1 · Purpose

One marketing-intelligence system combining three professions:
- Digital-marketing strategist
- Marketing data analyst
- Social-media strategist

It lets each operator follow their profiles' performance, understand results, plan content and make decisions grounded in data. Same method for every profile; recommendations specific to each.

## 2 · Separation rules

- One **environment per profile**, so data and audience traits never mix.
- **Instagram and TikTok are separate** even for the same brand: own metrics, analyses, reports. Instagram data comes from Insights; TikTok's from TikTok Studio. Never compare indicators across platforms (definitions differ).
- Three distinct tasks, kept apart so analyses can be checked: **record** the platform data → **calculate** indicators → **interpret** results.
- The structure is reusable; each installation carries its own data only (copying it to another account carries no private data).

## 3 · Module 1 — Performance Intelligence

| Module | Work |
| --- | --- |
| Profile diagnosis | Positioning, audience, results, opportunities |
| Data intelligence | Computes indicators, finds trends, compares periods |
| Reels analysis | Retention, drop-off, reach, shares, follows gained |
| Audience intelligence | Comments, questions, interests, recurring demands |
| Editorial strategy | Topics, formats, priorities, publishing calendar |
| Competitive intelligence | Studies other profiles, flags approaches worth studying |
| Commercial strategy | Tracks content → interest → sign-ups → sales |
| Results control | Checks whether past recommendations produced the expected results |

**Results control is the key module:** every recommendation carries a justification **and** an indicator to evaluate it.

### Metrics

- **Instagram:** reach, views, rate of views above 3 s, average retention, shares, saves, followers, editorial performance.
- **TikTok:** views, traffic source, average watch time, % full views, interactions, account growth (availability varies by account type).

### Report content

- Reels that beat the profile's usual performance, **among comparable posts**.
- Topics that brought followers vs only views.
- Where the audience dropped off during videos.
- Hypotheses that may explain results, **each with a confidence level**.
- Topics and formats to test next week.
- Which actions actually contribute to commercial goals.

Baselines come from **the profile's own history** (duration, topic, reach), never universal rules — e.g. "keep Reels skip rate under 40%" is not an algorithm law.

## 4 · Reliability — five mandatory rules

1. **Traceability** — every number has a source, date and reference period.
2. **Verifiable calculations** — rates and comparisons are computed by defined formulas (spreadsheet/tools), not by the language model.
3. **Facts vs hypotheses** — the system says when it is interpreting; it never attributes causes the data do not show.
4. **Decision validation** — every strategic change is followed up to check its effect.
5. **Editorial guardrail** — recommendations respect each profile's positioning; for Mônica especially, **no content that exploits emotional suffering just to raise engagement**.

Plus a **decision log**: what was recommended, what was implemented, what resulted — consultable months later.

AI can be wrong; conference mechanisms are part of the design. A metric that is unavailable is **never replaced by an estimate presented as fact**.

## 5 · Cadence

| Routine | Proposal |
| --- | --- |
| Reels readout | at 72 h and at 7 days |
| Weekly strategy | ~30–45 min, after data is organized |
| Monthly review | results, goals, tests, plan adjustments |

Implementation: (1) technical protocol (metrics, formulas, comparison criteria, report templates) → (2) structured spreadsheet with per-profile panels → (3) initial audit over the last 60–90 days → (4) 4-week test against original data.

## 6 · v1.0 kit (ChatGPT) — verbatim in `../kits/simec-1.0/`

Files: full kit (zip) · instructions to install in ChatGPT · install-and-usage manual · per-profile registration form · Instagram intelligence spreadsheet · TikTok intelligence spreadsheet. Spreadsheets: formulas, checks, separate dashboards, 200 rows per platform per profile, tested with fake data including missing values and duplicate rows. Install: one ChatGPT Project per account, paste instructions, attach the platform's spreadsheet. No sync between accounts.

## 7 · v2.0 — automated architecture (ChatGPT proposal)

> **Owner decision 2026-10-15: build it in-home on our own collection — no Metricool / Make.** Keep this section as the *requirements* reference (what to collect, cadence, alerts, permissions), not as the implementation.

```
Instagram / TikTok (authorized professional accounts)
        ↓
Metricool  — gathers available metrics
        ↓
Make       — scheduled routines, transfers, alerts
        ↓
Instagram base  |  TikTok base   (Google Sheets: own data + history)
        ↓
Looker Studio dashboards (per profile, per platform)
        ↓
SIMEC + AI (OpenAI API) — diagnoses, recommendations, reports
```

Automated:
- Daily collection of available metrics.
- Per-profile database updates, preserving each post's history over time.
- Period comparisons; above/below-pattern content detection.
- Weekly strategic report (email) and fuller monthly report (Metricool also sends scheduled monthly PDFs on paid plans).
- **Alerts**: connection dropped, collection failed, incomplete data, metric crossed a threshold.

Human approval stays mandatory before publishing, spending on ads, or sending sensitive replies — the system prepares, people decide.

| Service | Plan | Monthly |
| --- | --- | --- |
| Metricool | Advanced (up to 15 brands, team permissions, API) | US$ 67 |
| Make | Core, 10k credits | US$ 12 |
| Google Sheets / Drive | basic | — |
| Looker Studio | basic | — |
| OpenAI API | usage-based | variable |
| **Fixed estimate** | | **≈ US$ 79 + AI + taxes** |

Prices from vendor pages at the time; reconfirm. Metricool's API + Make integration requires Advanced or Custom. Instagram needs a professional account linked to a Facebook Page for full metrics.

Access: one central Metricool with the brands registered and per-person permissions — Mônica: admin, all brands · Gilson: his profiles and reports · Isadora: the profiles she helps run. Clients' data must never reach unauthorized people.

### Known limits

- Not confirmed: importing the **full second-by-second retention curve** or the **exact Reels skip rate** as shown in the Instagram app. Verify on connection.
- Each network exposes different indicators via integration — verify per network.

## 8 · Module 2 — Audience & Product-Development Intelligence (comments)

Owner request: collect comments and bring them **in writing** to drive content strategy, courses and talks from women's demands. Same priority as performance analysis.

Pipeline:
1. **Collection** — Metricool API + Make, daily.
2. **Comment bank** — original text (never rewritten), date, post/video, dedup of already-registered comments.
3. **AI analysis** — direct questions, personal accounts, disagreements, suggestions, requests to go deeper; recurring topics, expressed feelings, interests.
4. **Opportunity report** — suggested content, talks, courses, research with the audience; comment count per topic, source posts, **anonymized** example quotes.

Query example: *"SIMEC, mostre todos os comentários em que mulheres falam sobre a mudança da relação com os filhos adultos e organize as dúvidas mais frequentes."* → texts grouped by topic, with sources.

Illustrative report rows (not real data):

| Topic | What to investigate | Possible use |
| --- | --- | --- |
| Children who left home | Loss of routine, missing them, identity change | Talk on motherhood in maturity |
| Marriage after the children leave | Rediscovering cohabitation, conflicts | Reels series or themed meetup |
| Guilt when setting limits | Responsibility, expectations, approval | Course or workshop |
| Returning to personal interests | Desires, routine, postponed projects | Discussion group |

Rule: **recurring comments show interest, not proven commercial demand** — the system must say so and recommend ways to validate interest before building a product.

Works for Gilson and clients too, with categories adapted to each business.

### Limits

- **Instagram:** Metricool's API reads comments of the **50 most recent posts** → collect daily and keep our own bank; older history beyond that window is not guaranteed.
- **TikTok:** comments appear in Metricool's Inbox for business accounts; API extraction is documented but unvalidated.
- **LGPD** applies to publicly available data too. The audience shares personal, potentially sensitive experiences → restricted access to the bank, reports without names or identifiable data.
