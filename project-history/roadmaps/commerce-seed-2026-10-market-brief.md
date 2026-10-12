# Commerce seed — market research brief (2026-10-12)

> Companion to [`commerce-seed-2026-10.md`](commerce-seed-2026-10.md). Web research done 2026-10-12. Figures marked "3p" come from third-party pages. Fiscal and legal points must be confirmed by each client's accountant or lawyer; they are inputs to design, not settled answers.

## A. Digital goods (photo · video · music)

**Reference models**
- **Client galleries / proofing** (Pixieset, ShootProof, Pic-Time, Zenfolio, SmugMug): private or PIN gallery → favorites/proofing → store (downloads + lab prints via WHCC/Loxley/Prodigi, 2–5× markup, 3p). Pixieset: 15% commission on the free tier, 0% on paid tiers. https://www.pixpa.com/blog/best-pixieset-alternatives · https://toolradar.com/tools/pixieset/pricing
- **Event photos in Brazil**: Fotop (face recognition since 2016, white-label to venues, ~25% take reported, 3p), Banlek (R$260M sold since 2020, 10% take free / R$97/mo + 9%, selfie search), Fotto. https://maquinadoesporte.com.br/?p=140985 · https://braziljournal.com/4jn7
- **Stock agencies** (Adobe Stock, Shutterstock, Alamy, PhotoShelter): standard vs extended license, editorial-only without releases; subscriptions/credits/on-demand. Adobe pays 33% (photo) / 35% (video). https://helpx.adobe.com/ie/stock/contributor/help/royalty-details.html
- **Music** (BeatStars, Airbit): non-exclusive tiers (MP3 → WAV → stems → unlimited) + exclusive (selling it retires the beat). https://airbit.kayako.com/article/199-what-do-the-different-licenses-mean
- **Video**: Artlist (subscription license), Pond5 (per-clip marketplace).
- **Gumroad / Lemon Squeezy**: "product = file + license" checkout as merchant of record; useful model, wrong fiscal fit for Brazil.

**Mechanics the platform needs**
- Previews: low-resolution watermarked derivatives at upload (EXIF/IPTC kept); video low bitrate + burned-in mark; audio voice tag.
- Secure delivery: originals in a private bucket; signed URLs that expire (minutes–hours); download limits per order (e.g. 3–5) and window (e.g. 30 days); download log.
- License certificate: PDF with license id, buyer, asset id/hash, rights, date + public verification page ("DRM-lite"), optionally invisible watermark.
- Pricing: per item, bundles, packs/credits, subscriptions, license-tier multipliers.

## B. Physical small goods (Brazil)

- Reference platforms: Nuvemshop, Tray, Loja Integrada, Shopify, Wix (VTEX too heavy for a small shop).
- Catalog with variants (size/material/color), SKU + EAN, stock per location, reservation during checkout.
- Packaging profiles + cubic weight (L×W×H / 6000).
- Freight quotes in the cart through an aggregator (Melhor Envio, Frenet, Kangu): Correios PAC/SEDEX/Mini Envios, Jadlog, Loggi, J&T. Label purchase/print, tracking webhooks. Every shipment needs an NF-e or a declaração de conteúdo. https://melhorenvio.com.br/blog/sobre-nos/melhor-envio-como-funciona
- Returns: 7-day withdrawal, reverse-logistics code, refund, restock.
- Marketplace sync (Mercado Livre, Shopee, Amazon) usually via an ERP hub (Bling); stock-sync lag is the common complaint. https://www.capterra.com/p/191410/Bling/reviews/?page=3
- WMS-lite for small storage: bin locations, pick lists, batch picking, packing checklist, reorder point, consignment stock.
- Artifacts specifics: fragile packing profiles (statues, ceramics, incense holders), provenance / "artesanal" fields, occasional unique pieces (stock = 1).

## C. Brazil commerce infrastructure

**Payments.** Pix (QR / copia-e-cola), boleto, cards with parcelamento. **Pix Automático** live since 16 Jun 2025 (Res. BCB 402; receiver must be PJ) — fits subscriptions. Gateways: Mercado Pago, Asaas, Pagar.me, PagSeguro, Efí, Stripe BR (Pix supported). Split: Asaas splits by walletId, fixed or % of net, unlimited recipients, installment splits. https://docs.asaas.com/docs/split-de-pagamento

**Fiscal.**
- Goods → NF-e (model 55) / NFC-e. Services → NFS-e.
- **NFS-e Nacional**: municipalities from Jan 2026 (LC 214/2025); **Simples Nacional ME/EPP must issue through the national emitter from 1 Nov 2026** (Res. CGSN 191/2026). https://www.legisweb.com.br/noticia/?id=34194
- **Tax reform**: 2026 test year (CBS 0.9% + IBS 0.1% shown for information); CBS in force 2027; ICMS/ISS phased out 2029–2033. Invoice layouts already carry IBS/CBS fields — build for them. https://www.contabeis.com.br/noticias/73889/reforma-tributaria-2026-veja-o-que-muda-na-fase-de-transicao/
- **Photo licensing is ambiguous**: shoots = ISS/NFS-e; licensing/assigning copyright treated by São Paulo rulings as a movable asset outside ISS; STJ (2026) removed ISS from image-rights assignment. → tax treatment must be configurable per product type. https://tagdlaw.com.br/decisao-do-stj-afasta-iss-sobre-cessao-de-direitos-de-imagem/
- **MEI**: "fotógrafo independente" (CNAE 7420-0/01) allowed, cap R$81k/yr; selling digital files not explicitly covered. Religious-goods retail can be MEI (verify). Above the cap → Simples.

**Consumer law.** Decreto 7.962/2013: show legal name, CNPJ, address, contract summary, total price incl. freight, immediate order confirmation, withdrawal channel. CDC art. 49: 7-day withdrawal + immediate chargeback request. **Digital goods**: no settled STJ ruling — collect explicit consent that delivery starts immediately, keep download logs. https://turivius.com/portal/direito-de-arrependimento-no-ambiente-digital/?amp=1

**LGPD.** Legal basis per processing (contract for orders, consent for marketing), DPO contact, privacy notice, data-subject rights flow, retention (fiscal ≈5 years). Face search = biometric = sensitive (art. 11). Religious belief is sensitive too: never profile it from the artifacts shop's purchase history.

## D. ERP for e-commerce (Bling, Tiny/Olist, Omie, ContaAzul)

Order hub (multi-channel) · products + stock (multi-warehouse, kits) · purchasing/suppliers · fiscal (NF-e, NFC-e, NFS-e, SPED export) · finance (AR/AP, cash flow, bank/OFX + gateway settlement reconciliation incl. installments, chart of accounts, DRE) · CRM · shipping labels · reports (margin, ABC curve, turnover).

**AI opportunities**: auto-tag/caption/alt text/IPTC + culling (photos); SEO descriptions with cultural/religious context reviewed by the owner (artifacts); pricing suggestions; WhatsApp bot (order status, freight, catalog); demand/reorder forecast; fraud scoring + reconciliation anomalies; NCM/CFOP auto-fill.

## E. Module classification (the design input)

| Module | Seed core | Digital | Physical | Vertical |
|---|---|---|---|---|
| Auth, customer accounts, addresses, LGPD consent + rights | ✔ | | | |
| Catalog (products, categories, media, SEO), variants | ✔ `product_type` seam | asset + license variants | size/material variants, EAN | Photo: categories/albums · Artifacts: tradition/provenance |
| Pricing (rules, coupons, bundles) | ✔ | license multipliers, packs, credits | freight-inclusive promos | |
| Cart / checkout (Decreto 7.962, withdrawal consent) | ✔ | immediate-delivery consent | freight quote step | |
| Payments adapter + split | ✔ Fake+Real per gateway | | | marketplace split |
| Subscriptions / credits | ✔ | credit wallets | | stock video/music |
| Order lifecycle state machine | ✔ `fulfillment_type` seam | auto-fulfil on payment | pick → pack → ship | |
| Digital delivery (private storage, signed URLs, limits, log) | | ✔ | | |
| Preview / watermark pipeline | | ✔ | | Music: voice tag |
| License management + certificate + verify page | | ✔ | | Music: exclusive retires item |
| Client proofing / private galleries | | | | Photo (later) |
| Print-on-demand lab bridge | | | outsourced physical | Photo (later) |
| Inventory, locations, reservations, WMS-lite | | | ✔ | Artifacts: unique pieces, consignment |
| Shipping (aggregator, packaging, labels, tracking) | | | ✔ | Artifacts: fragile profiles |
| Returns / withdrawal (7 days) | ✔ policy core | revoke access | reverse logistics + restock | |
| Marketplace channel sync | | | ✔ | |
| Fiscal adapter (NF-e/NFC-e, NFS-e Nacional, IBS/CBS, tax per product type) | ✔ configurable regime | NFS-e or license treatment | NF-e + shipping docs | |
| Finance (AR/AP, cash flow, reconciliation, DRE) | ✔ | | | |
| Purchasing / suppliers | | | ✔ | Artifacts: artisans/importers |
| CRM, email/WhatsApp messaging, reviews | ✔ | | | |
| Back-office, roles, audit log, reports | ✔ | download analytics | stock/ABC reports | |
| AI automation layer | ✔ framework | auto-tag/caption, culling | demand forecast | Artifacts: culturally reviewed copy |

**Design takeaways**: product type `{digital, physical, service, print_on_demand}` and fulfillment type are named seams so one order engine serves every market; payments, fiscal, shipping, storage and AI each ship Protocol + Fake + Real + factory; tax treatment per product type is tenant-configurable.
