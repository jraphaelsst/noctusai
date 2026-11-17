# Sales page anatomy — the long-form direct-response page, done our way

**What it is.** The section-by-section skeleton of a Brazilian long-form sales page (infoproduct / course /
SaaS launch style), written in our own words. For each section you get what it does, which seed marketing
organ renders it (or that none does yet), what it must record, and the legal limits. Use it when a product
needs a page that *sells* (checkout-bound), not just a landing that informs.

**Why it exists.** On 2026-11-17 the owner asked to fold into the environment what a competitor's public
funnel teaches. The competitor was a R$ 1.497 "AI for non-technical business owners" hub that reached us
through a Meta ad. Its page follows the canonical BR direct-response sequence, and that buyer is the same ICP
as our done-for-you products (agents, social-wiring, erp-imobiliario). The raw study (verbatim, third-party
material) stays outside git in `_private-studies/vibehub-academy/STUDY-pagina-de-vendas.md`. This file keeps
only the transferable method.

**How to use it.** Specs go through `product-manager`, copy and layout through `product-designer`, and the
build through the organs in `KB § PATTERNS/frontend/marketing-organs-and-motion.md`. Before publishing, run §3
(legal) with `legal-advisor` and §4 (measurement).

---

## 1 · The sequence

The order matters: each block answers the question the previous block raised. A CTA follows almost every
block (the reference page had about 15), each phrased as the reader's own wish ("Quero …", "Testar sem risco").

| # | Section | Job | Seed organ |
|---|---|---|---|
| 1 | **Hero** | a numeric promise + a subhead that pre-empts the top three objections ("mesmo que você não seja técnico, não tenha tempo, já tenha tentado") | `Hero` (`stats`, media slot) |
| 2 | **Pain** | the cost of standing still, framed against competitors | `FeatureGrid` text variant (no dedicated organ) |
| 3 | **Symptom mirror** | two checklists ("se você está cansado de…" / "provavelmente você também já…") so the reader feels seen | **gap**: checklist organ |
| 4 | **Origin story** | "I was where you are": the founder or company once had the same problem | **gap**: story/bio organ |
| 5 | **Turning point / reframe** | one named insight that changes the frame (theirs: "AI is a workforce, not a chatbot") | `CtaBand` / prose |
| 6 | **Authority** | partners, numbers, track record (each verifiable, §3) | `Hero` `stats` / logo strip (**gap**) |
| 7 | **Named mechanism** | the method as a named system with 3 parts (theirs: a "tríade" of product, marketing, management) | `Steps` / `FeatureGrid columns={3}` |
| 8 | **Proof** | customer results: screenshots, cases, testimonials | **gap**: proof carousel organ |
| 9 | **Objection triplet** | the three biggest "mas eu…" objections, answered inline | `FeatureGrid` |
| 10 | **How it works** | each pillar expanded with concrete bullets | `FeatureGrid` `bullets` |
| 11 | **Inside view** | what the buyer actually gets access to | `FeatureGrid` / screenshots |
| 12 | **Ecosystem** | "not a folder of lessons, a whole hub": the surrounding value (community, tools, marketplace) | `ProductCatalogGrid` / `FeatureGrid` |
| 13 | **Value stack** | each included item with its value | **gap**: offer-stack organ |
| 14 | **Price** | the real price, installments, and a per-day framing | **gap**: pricing/offer organ (checkout link) |
| 15 | **Who's behind it** | a bio aligned with the reader's identity | **gap**: bio organ |
| 16 | **Guarantee** | risk reversal (the legal 7 days + anything contractual on top, §3) | **gap**: guarantee badge organ |
| 17 | **FAQ** | the ~12 objections in the buyer's words: zero-start, coding, time, fit, no business yet, tools, staleness, access, support, price, "what if it doesn't work", "why you" | `Faq` |
| 18 | **Future pacing** | scenario A (stand still) vs scenario B (adopt) | `CtaBand` `variant="inverse"` |
| 19 | **Footer recap** | price + guarantee one more time, plus a WhatsApp handoff | `LandingFooter` + an agents/WAHA handoff |

**Organ gaps** (checklist, story/bio, logo strip, proof carousel, offer stack, pricing, guarantee): these
are *candidates*. Do not build them for one page. They become organs when the second product page needs
them (DRY recurrence rule; pilot-products-first). Until then, compose them from `primitives` inside the
product, using a declared named seam.

**What the reference did well and we keep:** every major objection gets answered twice (inline in §9, then
in the FAQ); the mechanism has a name; the CTAs speak in the first person; the funnel ends in a WhatsApp
conversation, where our agents (Julia / SDR) can recover and close.

**What we skip:** stacking urgency nine ways, "30 segundos para decidir", and proof carousels that repeat
items to look bigger. These read as pressure to the ICP we sell to (small business owners who have been
burned by courses), and several of them run into §3.

## 2 · Positioning learnt (market intel, 2026-11)

- A market exists of non-technical business owners paying about R$ 1.5k for *education* on making AI do
  operational work (product, marketing, management). Course hubs serve it, competing on community and
  "behind the scenes" access.
- Their "management" pillar (an AI-filled CRM, kanban and tasks) and "marketing" pillar (WhatsApp agents,
  prospecting) are what our organs already run in production. Our angle: **sell the operating system, done
  for you, not the course that teaches you to build it.** The same FAQ objections apply (no tech skills, no
  time, "does it fit my market?"), so our pages should answer them too.
- Their earning angle ("sell AI services for R$ 3–7k") widens the buyer pool to people who have no business
  yet. That is a possible reseller or white-label channel for our products. This is the owner's decision
  (`product-architect` for the pack/tier shape).

## 3 · Legal limits (CDC). Confirm with `legal-advisor` before publishing

Depth: `KB § PATTERNS/legal/consumer-ecommerce.md` §3 and §5. This is the minimum floor:

- **No fictitious "de/por" anchor.** A strike-through price must be a price we actually charged. The
  reference page anchored at "De R$ 4.997" while stating a different "normal" price. That is misleading
  advertising risk under CDC 37 §1, and the advertiser must prove the claim (CDC 38). Derive the "de" only
  from our own price history.
- **The 7 days are the law, not a gift.** For online sales, withdrawal within 7 days is CDC 49 (public
  order). Present it as the legal right, and present anything longer as a contractual extra.
- **Every number must be provable.** User counts, revenue screenshots and "partnership with X" claims need
  evidence on file. A partnership claim also needs that partner's permission to use its name.
- **Scarcity must be true.** A deadline or bonus exclusivity must actually expire. A deadline that rolls
  over is misleading.
- **Consent for the WhatsApp handoff.** Opt-in before any outbound message (`consumer-ecommerce.md` §8;
  the agents-security STOP floor).
- Price-display rules (Lei 10.962/2004, Decreto 5.903/2006) are not yet read into the KB, so ask
  `legal-advisor`.

## 4 · Measurement (measurement-by-design)

Per `KB § PATTERNS/architect/measurement-by-design.md`, a sales page is a funnel that must record:
- `section_viewed` (section id from §1, so drop-off shows *where* in the sequence readers leave);
- `cta_clicked` (CTA id + section id, which shows which of the ~15 CTAs converts);
- `checkout_started` / `checkout_completed` / `refund_requested` (outcome enum; refund within 7 days is the
  honesty metric for the promise);
- `whatsapp_handoff` (lead → `leads` organ, attribution carried from the UTM set).

Success metric for any page built from this pattern: CTA→checkout rate and the 7-day refund rate, judged by
`product-analyst`.

## 5 · Sources

- Public sales page `vibehub.academy/vha-especial`, read 2026-11-17 through a Meta ad link. Only the public
  page was read, no paid content. Verbatim study in `_private-studies/vibehub-academy/` (outside git).
- CDC, Lei 8.078/1990, arts. 37, 38, 49 (as summarised in `consumer-ecommerce.md`).
