# Newsletters — SPEC (owner interview 2026-11-13; owner "go" 2026-11-13)

> Spec for two NEW, independent noc products: `tech-newsletter` and `promo-finder`.
> Background research (vendor-derived material) lives OUTSIDE git under `_private-studies/` (`daltonlab/`, `newsletters-research/`) — pointers only, never quotes (keeper `check_no_vendor_study_in_git`).

## Decisions
| Date | Decision | Chosen |
|---|---|---|
| 11-13 | Hosting | Both are OWN noc products, built from scratch; no Substack/beehiiv |
| 11-13 | Independence | Two independent products, each with its own schema/DB tables/models; everything recorded (events + metrics, measurement-by-design) |
| 11-13 | Run mode | Built as manual TRIGGERS first (pull + validate output), then switched to a ROUTINE once validated; different routines per product |
| 11-13 | Tech product | Daily tech news; email + WhatsApp + Telegram |
| 11-13 | Tech format | All formats: daily digest (5 curated items, each with an editor's-take paragraph) + essay pieces |
| 11-13 | Tech audience | BR professionals/business AND BR developers, pt-BR |
| 11-13 | Promo product | "Promo finder": searches online for discounted offers from reliable sellers, auto-posts |
| 11-13 | Promo channels | WhatsApp Channel + Telegram channel + email digest + public web deals page |
| 11-13 | WhatsApp format | Channel ONLY (one-way) for BOTH products — no member messages, no phone exposure (replaces "group") |
| 11-13 | WhatsApp transport | WAHA line, QR connect in UI (existing seed integration) |
| 11-13 | Telegram | NEW seed integration: Bot API (N bots per org = "Telegram lines", token in UI); MTProto later — SUPERSEDED by the MTProto row below |
| 11-13 | Curation | Fully automatic posting; score uses listing signals (likes, sales count, reviews/ratings, stock, seller reputation, real discount) |
| 11-13 | Monetization | Promo = affiliate commissions (accounts not yet created); Tech = sponsors/ads later; course CTA in future only — no CTA now |
| 11-13 | Tech sources | ALL: global tech/AI press RSS + BR press RSS + dev signals (HN, GitHub trending, releases, arXiv, Product Hunt) + social/YouTube — gather everything first, evaluate keep/discard later (per-source quality metrics) |
| 11-13 | Validation gate | Trigger phase: every run = draft, owner approves/rejects with reason (recorded); routine phase: scheduled + fully automatic, kill switch + daily report |
| 11-13 | Config | Routine schedules AND search/source configs editable in the UI |
| 11-13 | Reliable seller | Official/marketplace-sold + reputation thresholds + product signals, plus researched extras (fulfilment by marketplace/Full/Prime, return/warranty policy, seller age, claims/cancel rate, review recency, real-discount vs own price history) — all thresholds in UI |
| 11-13 | Names | Working slugs `tech-newsletter`, `promo-finder`; public brands later |
| 11-13 | Entity | Start on CPF (test until revenue); SLU plan prepared and parked until revenue (accountant checklist) |
| 11-13 | Guardrails | All legal guardrails built in (re-verify, timestamp, own-history de/por, expiry bot, evidence log, CONAR label) — each with a UI toggle (owner accepts exposure when off; toggles audited as events) |
| 11-13 | Data access | Scraping first (Apify where possible), APIs added after — owner accepted ToS/account risk flagged by legal |
| 11-13 | Surfaces | Admin apps FIRST (CMS/CRM/ERP — the whole business inside the apps), public pages later; reuse knowledge from existing noc modules |
| 11-13 | Public page | Minimal public page EARLY (read-only deals feed + about/contact/disclosure) so ML/Amazon can approve affiliates; rest of public surfaces later |
| 11-13 | Admin modules | Each product gets: CMS/editorial · Audience+channels · CRM (sponsors & affiliate programs) · ERP (money). TWO DIFFERENT BUSINESSES — no shared tables between them |
| 11-13 | Cadence | Tech: collect continuously (in-house registry), send ONE daily bundle at 12:00 BRT on all channels. Promo: post immediately above threshold, no daily cap. All outbound via seed `noctusai_lib.rate_limit` |
| 11-13 | E-mail | Resend (same as noreply@noctusai.com); sending subdomains `news.noctusai.com` and `promo.noctusai.com` |
| 11-13 | Build order | Wave 0 shared seed seams (Telegram, broadcast-channel, collector, run lifecycle) → Wave 1 two pilots in parallel |
| 11-13 | Telegram | Study → spec done (architect; `TELEGRAM-SPEC-summary.md`); reviewed 11-13 |
| 11-13 | TG connect | Org admin connects a Telegram line (paste token); platform admin keeps oversight/suspend. Owner: same as WhatsApp lines (connected by orgs) |
| 11-13 | TG bot sharing | ONE shared bot for both products during test/validation → line registry in CORE (architect option b) referenced by both products; split into per-product lines after validation (expand→migrate→contract) |
| 11-13 | TG posting | NO expiry rule for now; link previews on (tech) / off (promo); forwarding allowed |
| 11-13 | MTProto | Dropped entirely — Telegram is publish-only (API ToS §1.5 AI clause) |
| 11-13 | Owner enablement | Owner needs the affiliate + sponsorship business processes researched and designed together with the owner |

## Research facts (sources in agent reports)
- Seed already ships: `noctusai_lib.domain.digest.BaseDigestService` (digest-seed), `integrations/{resend,mailchimp,email,whatsapp,apify,llm,outbound_webhook,quota,rate_limit}`.
- Amazon BR: PA-API 5 deprecated → Creators API (sales-gated). E-mail promotion of affiliate links likely forbidden (unconfirmed for BR).
- CONAR 2026 influencer guide: affiliate links = advertising → ostensive disclosure per post.
- WhatsApp unofficial client (WAHA) → ban risk; mitigate with dedicated number.
- LEGAL (legal-advisor, 11-13): CDC 30/37/38 — auto-posting does NOT reduce liability; guardrails: price timestamp "visto às HH:MM em <loja>", re-verify right before post, "de/por" only from OUR stored price history, expiry/correction bot, evidence log per post (screenshot+JSON, ≥5y), company ID + complaint channel (Dec. 7.962). CONAR 2026 (in force 01/06/2026): first line of every deal post "Publicidade · link de afiliado"; "PATROCINADO por X" next to sponsored block. LGPD email: consent + double opt-in, one-click unsubscribe, hashed suppression list, disclose pixels; prefer per-campaign sub-ids over per-person. Channels: store no follower PII. Images/data via official API/affiliate feeds; ratings counts OK, review TEXT not. WAHA: contractual ban risk → dedicated number, WA treated as disposable; Telegram/email/web primary. OAB items listed in agent report.
- TAX (accountant, 11-13): NoctusAI has no CNPJ yet. PF test 3–6 months OK but costly (IRRF + 11% INSS); MEI 7319-0/02 a stretch (CRC call). Recommended: separate SLU (ME, Simples) for media; affiliate + advertising both under Fator R (≥28% payroll ⇒ Anexo III, else V). Commission = revenue on program APPROVAL; clawbacks after approval = cancelamento. 2027 IBS/CBS-outside-DAS window 03/11–20/12/2026. CRC-required list in report.
- PLAYBOOK (research, 11-13; V=official page read): ML Afiliados (V) — CPF ok, Mercado Pago, **public profile reviewed by ML**, 24h window, electronics 5% / home 12% / beauty-fashion 16%, payout ≥R$30 from ≥3 buyers within 60d, terms NAME WhatsApp/Telegram groups ("Divulgadores de Ofertas", >R$50k/mo special table), **email needs ML written consent (4.3a)**, ML public search API 403 unauthenticated → OAuth app. Amazon BR (V) — needs **public site with original content**, 8% electronics / 13% beauty / 7% other, 24h (89d if carted), R$30 bank deposit, **bans "off-line" promotion; email/DM only if solicited**, price timestamp required, no image caching; WhatsApp/Telegram not named → ask Associates in writing; Creators API (OAuth2) BR eligibility unclear. Shopee — CPF via ShopeePay (11% INSS+IRRF withheld), PJ needs NF 17.06/17.25; GraphQL affiliate API w/ subIds (U). KaBuM via Awin 2.3%, 1-day. Lomadee: CPF + Pix. Sponsorship: flat fee per slot most common in BR (Manual do Usuário 6.4k subs = R$1.5k/week), media kit after ~60 days; Passionfroot free; beehiiv network BR payout unclear. CONAR PDF read: "#publi/#publicidade" in pt-BR, "visível em primeiro plano", AI content fully covered.
- CONFLICT: ML + Amazon approval need a PUBLIC page/profile with original content → affects "admin only for now".

## Open items
- [x] all interview items closed 11-13 · [x] Telegram spec review (owner, 11-13) · [ ] Amazon Associates written question (WA/Telegram = "Site"?) · [ ] ML written consent for e-mail · [ ] OAB items (legal report) · [ ] CRC items (accountant report)

## Plan

### Wave 0 — seed seams (parallel, file-disjoint; nothing per-product)
1. **Telegram integration** `noctusai_lib.integrations.telegram` — Protocol+Fake+Real+factory, Telegram lines (bot token encrypted, connect in UI), channel binding, outbound log (message_id → edit/delete), webhook w/ secret_token, rate-limit bucket. From the architect spec (reviewed by the owner 11-13); line registry in core during validation; webhook clobber guard 409; tables telegram_lines/channels/posts/line_events/channel_snapshots.
2. **Broadcast-channel seam** — one interface `publish(post, targets)` over WhatsApp Channel (WAHA), Telegram channel, e-mail (Resend broadcast w/ double opt-in, one-click unsubscribe, suppression list); per-target render (HTML / MarkdownV2 / WA text), edit/expire, delivery events. Verify-seed first (digest-seed, outbound_webhook, whatsapp may already cover parts).
3. **Collector seam** — sources registry (RSS, Apify actors, scrapers, YouTube, HN/GitHub/arXiv APIs) with schedule, per-source rate bucket, raw item store + dedup hash, per-source quality metrics (kept/discarded ratio). Config editable in UI.
4. **Run lifecycle seam** — trigger → draft → approve/reject(reason) → routine (schedule, kill switch, daily report) — reusable by both products.

### Wave 1 — two independent products (parallel; own schema each)
**`tech-newsletter`** — collects continuously; LLM clusters/ranks; daily 12:00 bundle in our digest template (hook → table of contents → 5 items, each with facts + editor's take → sign-off) + essay format; per-channel render; issue archive later.
**`promo-finder`** — scrapes first (Apify), APIs later; price-history store (own series → legit "de/por"); scoring (seller: official/marketplace-sold, reputation tier, age, claims rate, fulfilment Full/Prime; product: rating ≥, review count, recency, sales, stock; deal: % vs own 30/90-day history, category minimums) — all weights/thresholds in UI; guardrails w/ audited toggles (re-verify pre-post, timestamp, CONAR first-line label, expiry/correction bot, evidence log); affiliate link builder w/ sub-id per channel/post; minimal public deals page early.
Each product's admin: **CMS** (sources, items, drafts, editor, previews, queue, schedule) · **Audience & channels** (subscribers, lines, follower counts over time, send logs) · **CRM** (sponsors pipeline + media kit for tech; affiliate programs/accounts/terms for promo) · **ERP** (clicks → orders → commissions pending/approved/clawed-back; sponsor invoices; costs Apify/LLM/ESP; P&L per channel).

### Measurement (EOA, append-only events per product)
Collector: items fetched/kept/discarded per source, latency, cost. Editorial: drafts, approvals/rejections+reason, time-to-approve. Delivery: sends/delivered/bounced/opened/clicked per channel & issue/post; follower/subscriber counts daily; unsubscribes. Promo: deals scored/posted/skipped(reason)/expired/corrected, price re-check deltas, clicks → orders → commission per post/channel/program. Money: revenue (approved), clawbacks, costs, margin.

### Owner business track (parallel to build)
1. Create affiliate accounts on CPF: Mercado Livre (after public page), Shopee, Lomadee, Awin (KaBuM); Amazon after public page + written question on channels. 2. Ask ML for written e-mail consent. 3. Dedicated WhatsApp number for the Channels. 4. Create ONE shared Telegram bot (BotFather) for the validation phase; split per product after validation. 5. After ~60 days of sends: media kit + Passionfroot listing for tech sponsors. 6. SLU plan parked until revenue (accountant checklist; note IBS/CBS window).

### Gates before code
Telegram spec reviewed by owner → `noc-verify-seed` on each Wave-0 seam → `noc-contract-first` per product → `noc-new-product` scaffold ×2 → owner "go".
