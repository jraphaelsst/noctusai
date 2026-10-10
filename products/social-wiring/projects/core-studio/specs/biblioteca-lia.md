# Biblioteca de virais: legitimate interest assessment (LIA)

**Decision (owner, 2026-10-10):** the Biblioteca de virais processes third-party creators' public Instagram content on the legal basis of **legitimate interest** (LGPD Art. 7, IX, with Art. 10). This document is the balancing test that basis requires (Art. 10 §3, and the ANPD guidance on legitimate interest). It covers the processing as built in `specs/geracao-contract.md` §2.3, §3.3 and §3.4, and the security review fixes (commit 470ce7235).

**Status:** assessment written by the tech lead from the owner's decision. It needs the owner's (or the DPO's) sign-off on the three items under "Owner actions" before `biblioteca_ingestao_habilitada` is switched on.

## 1. What is processed

| Data | Source | Kept |
|---|---|---|
| Handle, display name, profile photo, follower count of a **monitored profile** | Instagram Graph API Business Discovery (public business/creator accounts only) | While monitored; purged 90 days after the profile is paused or referenced by no marca; at once when deleted or opted out |
| Per post: caption, permalink, timestamp, likes, comments, media type, thumbnail | Same | Same |
| Transcript of a Reel's speech | Our self-hosted transcriber (audio deleted right after transcription) | Transcript on the viral row: same as above. Copy in the transcription layer: 7 days |
| Classification (niche, profession, format, attention trigger, hook, structure blueprint) | LLM (Anthropic) over caption + transcript | Same as the viral |

Not processed: private accounts, stories, comments' authors, DMs, follower lists, or anything about people appearing in a video beyond the speech in the transcript.

## 2. Purpose test

**Legitimate purpose:** each client org studies the **structure** (hook, format, attention trigger) of content that performs well among creators it chooses, to write its **own** original content. That is a normal commercial interest in competitive and market analysis, and it is lawful.

**Specific and explicit:** structure analysis for content creation only. Explicitly excluded:
- profiling the creator as a person;
- republishing their content;
- contacting them;
- using their data to train models;
- sharing it with other orgs. The library is org-scoped and never public.

## 3. Necessity test

- The purpose cannot be met without reading the posts. We only take what Business Discovery already returns publicly, plus the speech transcript, because the hook is usually spoken.
- **Minimisation (built):**
  - only accounts the org registers (max 30 per org);
  - only public business/creator accounts;
  - classifier output is validated against the source text (H1 fix);
  - audio is never stored after transcription;
  - per-reel limit of 3 minutes;
  - daily caps on transcription minutes and on syncs.
- A less intrusive alternative (captions only, no transcripts) was considered. It is kept as a fallback: transcription can be turned off independently, through the shared `transcricao_habilitada` and the library lane's own caps.

## 4. Balancing test

**Data subject's reasonable expectations:** the creators run public business/creator accounts and publish to be seen and studied. Analysis of public posts by other professionals in the same market is within what they can reasonably expect (Art. 7 §4: data made manifestly public, used in line with that publication). Speech in a public Reel is part of the published content.

**Impact on the creator:** low.
- Nothing is republished or attributed to them outside the org's private workspace.
- Nothing is used to decide anything about them.
- The data stays org-scoped, behind authentication, with read-only database grants for members (M3 fix). Thumbnails are in a private bucket with signed URLs (15 min).

**Sensitive data:** a creator may say sensitive things in a Reel (health, religion). We don't extract or tag such data; the classifier only outputs content-structure fields. Residual risk: it can remain in the raw transcript. Mitigated by retention, org scoping and the opt-out.

**Third parties in the video:** only their speech, if any, ends up in the transcript. Same mitigations.

**Conclusion:** the org's interest prevails, provided the safeguards in §5 stay in place.

## 5. Safeguards (all required for the basis to hold)

1. **Opt-out and deletion on request.** A creator can ask, through the contact in §6, to stop being monitored. The platform admin registers the handle in the opt-out list. That purges everything about it across **all** orgs at once, and blocks it from being registered or synced again. This also covers the Meta Platform Terms' "delete on request". (Built in the BE-OPTOUT slice: `cs_biblioteca_optouts` and the admin endpoints.)
2. **Retention:**
   - 90 days after a profile is paused or unused, then purged (`biblioteca_retencao_dias`);
   - immediate purge on delete or opt-out;
   - orphan-blob sweep;
   - transcription-layer copy kept 7 days.
3. **Transparency.**
   - Minha Biblioteca tells the org that only public accounts may be monitored, and that creators can opt out through the contact in §6.
   - The platform privacy notice gets a section describing this processing and the opt-out (owner action).
4. **Security:** the review fixes are H1 (stored prompt injection), M1 (bounded pagination), M2 (retention), M3 (grants) and L1–L4. Media is fetched only through the SSRF-safe `safe_fetch`, from the Instagram CDN allow-list.
5. **Sub-processor and international transfer (Art. 33):** captions and transcripts are sent to Anthropic (US) for classification and generation. Record it in the ROPA and in the sub-processor list (owner action).
6. **Kill switch:** `biblioteca_ingestao_habilitada` defaults OFF and fails closed, so processing can be stopped at once.

## 6. Owner actions before the switch goes ON

- [x] (2026-10-10) **Opt-out contact:** the e-mail or DPO channel creators use (shown in Minha Biblioteca and the privacy notice). Done: `joaoraphaelsst@gmail.com`, configurable via `biblioteca_optout_contato`.
- [x] (2026-10-10) **Privacy notice:** add the Biblioteca section (what, why, basis, retention, opt-out, Anthropic as sub-processor). Done: privacy policy section 18, version 1.1.
- [x] (2026-10-10) **ROPA:** add this processing activity and the Anthropic sub-processor entry. Done: `ROPA-biblioteca.md`.

## 7. Review

Re-assess if:
- the purpose changes (e.g. sharing across orgs, training);
- a new data source is added (TikTok, YouTube);
- complaints or opt-outs show expectations were misjudged.

Otherwise re-assess every 12 months. Next review: 2027-10-10.
