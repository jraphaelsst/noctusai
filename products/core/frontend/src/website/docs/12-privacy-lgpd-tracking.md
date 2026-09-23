# 12 · Privacy, LGPD & tracking

> ⚠️ **Policy conflict to resolve before launch.** The fleet-wide privacy content says the platform uses **only strictly-necessary cookies and no advertising cookies** (`consent.ts:320-326`, seed consent content). The owner's decision to run **GA4 + Meta Pixel** (after opt-in) contradicts that text. The seed consent content must be updated, and **compliance-reviewer consulted**, before any tracking code ships. The LGPD data-category intake (`noctus.dev.lgpd_flag`) is filed for: lead contact data, consent records, analytics identifiers.

## Consent banner (seed organ `ConsentBanner`)

- A **bottom bar**, never a modal over content ([P12](04-pattern-synthesis.md#p12-one-overlay-at-a-time)).
- **Equal-weight "Rejeitar" / "Aceitar" + "Personalizar"** on the first layer (the Blip/Pipefy model; Conta Azul's and Sharplink's variants are anti-patterns).
- **Categories:**
  - Necessários (always on: session, theme, language, consent record);
  - Medição (privacy-first analytics, if its configuration requires consent);
  - Marketing (GA4, Meta Pixel).
- The choice is stored first-party with a **text version**. A "Preferências de cookies" link in the footer reopens it.
- Consent is re-asked whenever the text version changes.
- pt-BR/EN via the seed i18n primitive.

## Loaders

- **0 third-party scripts before consent.** GA4 and Meta Pixel are injected only after "Marketing" is granted, and removed (with cookies cleared, as far as the browser allows) if consent is revoked.
- **Privacy-first analytics (Plausible or Umami, self-hosted preferred):** cookieless. It can run under legitimate interest *if* the policy text says so. **OPEN:** decide with compliance-reviewer whether it runs before consent or waits for "Medição".
- The WebGL bundle never contains tracking code.

## First-party events

`site_events` (no PII): `page_view`, `cta_click {cta, section, product}`, `whatsapp_click`, `waitlist_submit`, `brief_submit`, `signup_start`, `theme_change`, `locale_change`, `hero3d_opt_in`.
- It uses an anonymous first-party id, which counts as strictly necessary only if it's session-scoped. **Persistent anon ids wait for "Medição" consent.**
- It feeds the Leads dashboard strip and the section-level conversion metrics that guide which sections the admin keeps on.

## Lead data (LGPD)

- **Lawful basis:**
  - consent for marketing contact (opt-in checkbox with purpose text);
  - pre-contractual steps for replying to a brief the visitor sent.
- **Stored consent:** the text version, timestamp, and a hashed IP.
- **Minimisation:** no CNPJ, no cargo, no fields we don't use.
- **Retention:** leads that aren't won are anonymised after **OPEN** months (proposal: 18). Retention is enforced by a scheduled job.
- **Data-subject requests** (access, correction, deletion) are handled from the lead detail and audit-logged.
- **The future AI agent** only contacts leads with marketing consent and identifies itself as automated ([10](10-conversion-and-leads.md#agent-ready-design)).

## Legal pages

`/privacidade`, `/termos` and `/cookies` in pt-BR and EN. Content comes from the updated seed consent content and names the legal entity (razão social, CNPJ, address), the DPO/encarregado contact, processors (hosting, e-mail provider, WhatsApp/WAHA, analytics, Google, Meta), and international transfers (GA4 and Meta).
