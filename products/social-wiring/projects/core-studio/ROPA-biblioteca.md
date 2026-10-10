# ROPA: Biblioteca de virais (record of processing activity)

LGPD Art. 37 record. Companion to the balancing test in `specs/biblioteca-lia.md` (the LIA). Created 2026-10-10.

| Field | Entry |
|---|---|
| Activity | Biblioteca de virais (Social Wiring, Criação de Mídia): monitoring public Instagram profiles registered by a client org, to study the structure of content that performs well |
| Controller | **PENDING OWNER CONFIRMATION (2026-10-10)**: drafted as João Raphael (pessoa física), operator of the Noctus platform; defines purposes and means (platform privacy policy, section 1; the Biblioteca section 18 is HELD unpublished until the owner approves its wording, revert 9a39ca04f). Identity and DPO as published in `seed/framework/frontend/src/content/consent.ts` (`CONSENT_META`) |
| Operators / processors | Client org (registers the profiles and uses the library under the platform's purposes); Supabase (database and storage hosting); Anthropic (US), LLM sub-processor; self-hosted transcriber (no egress, no third party) |
| Purpose | Study the structure (hook, format, attention trigger) of high-performing content to write the org's own original content. Excluded: profiling the creator, republishing, contacting the creator, model training, sharing across orgs |
| Legal basis | Legitimate interest, LGPD Art. 7, IX (with Art. 10); balancing test in `specs/biblioteca-lia.md` |
| Data subjects | Third-party creators who run public Instagram business/creator accounts registered by a client org; people whose speech appears in their Reels |
| Data categories | Handle, display name, profile photo, follower count; per post: caption, permalink, timestamp, likes, comments, media type, thumbnail; transcript of the Reel's speech; LLM classification (niche, profession, format, trigger, hook, structure). Sensitive data is not extracted; it may remain incidentally in a raw transcript (LIA section 4) |
| Source | Instagram Graph API, Business Discovery (public business/creator accounts only), through a Meta (Facebook Login) account connected by the org. Speech transcribed by our self-hosted transcriber; audio deleted right after |
| Recipients | Users of the registering org only (org-scoped, authenticated, never public). Anthropic (US) receives captions and transcripts for classification and generation |
| International transfer | Anthropic, United States: LGPD Art. 33. Safeguards: the provider's contractual clauses and data minimisation (only caption and transcript text is sent). To be confirmed by the owner against the provider's current DPA |
| Retention | Purged 90 days after a profile is paused or referenced by no brand (`biblioteca_retencao_dias`); immediate purge on delete or creator opt-out (across all orgs); orphan-blob sweep; transcription-layer copy kept 7 days |
| Security measures | Org-scoped RLS and read-only member grants; private bucket with 15-minute signed URLs; SSRF-safe media fetch with Instagram CDN allow-list; classifier output validated against source text (stored prompt-injection fix H1); bounded pagination; caps per org (30 profiles, daily sync and classification limits); kill switch `biblioteca_ingestao_habilitada` default OFF, fail-closed; audio never kept; logs carry no transcript text |
| Data subject rights channel | E-mail to the opt-out contact, default `joaoraphaelsst@gmail.com` (config `biblioteca_optout_contato`, platform_settings or env `BIBLIOTECA_OPTOUT_CONTATO`). On request a platform admin registers the handle in `cs_biblioteca_optouts`: purge across all orgs and block re-registration. Other Art. 18 rights via the DPO channel of the privacy policy (sections 14 and 17) |
| Transparency | Privacy policy section 18 (`/consent/privacy-policy`, version 1.1); transparency note in Minha Biblioteca naming the contact |
| Review | With the LIA (its section 7); re-check when the sub-processor, retention or source changes |
