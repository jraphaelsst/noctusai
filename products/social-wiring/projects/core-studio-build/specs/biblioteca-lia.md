# Biblioteca de virais: legitimate interest assessment (LIA) — v2 DRAFT

> **v2 is an UNSIGNED DRAFT (2026-11-15).** It re-states the balancing test for the platform-wide library (migration 351, owner decisions of 2026-11-15). It is **not in force** until the controller / DPO signs the block at the end of this document. v1 (2026-10-10, org-scoped library) stays the last signed assessment until then; do not read v2 as signed.

**Decision (owner, 2026-10-10; scope re-decided 2026-11-15):** the Biblioteca de virais processes third-party creators' public Instagram content on the legal basis of **legitimate interest** (LGPD Art. 7, IX, with Art. 10). This document is the balancing test that basis requires (Art. 10 §3, and the ANPD guidance on legitimate interest). It covers the processing as built in `specs/geracao-contract.md` §2.3, §3.3 and §3.4 and in `specs/estruturas-contract.md` (platform-wide library, Estruturas).

**What changed from v1.** The library is no longer owned by each client org: it is ONE platform-wide library written only by platform administrators. Client orgs and brands only choose which library profiles and Estruturas they use. The library now also holds **Estruturas** (a headline formula, a format, objectives and an ordered list of typed blocks per video or imported entry). Client orgs see a creator as **handle + display name only**.

## 1. What is processed

| Data | Source | Kept |
|---|---|---|
| Handle and display name of a **library profile** (a platform row: no client org owns it) | Public Instagram posts read by Apify scraping of the PUBLIC profile (owner decision 2026-11-04, transitional until Meta verification) or, when `biblioteca_fonte=business_discovery`, Instagram Graph API Business Discovery (public business/creator accounts only); or an **imported dataset of structures** loaded by a platform administrator (handle + display name + structure data) | While referenced; see §5 retention |
| Profile photo and follower count | Same public sources (a profile that is only imported has neither) | Visible to platform administrators only; **dropped** when the profile is retained only for its Estruturas (§5) |
| Per post: caption, permalink (canonical Instagram post URL), timestamp, likes, comments, media type, thumbnail | Same public posts | Same as the profile; thumbnails in a private bucket |
| Transcript of a Reel's speech | Our self-hosted transcriber (audio deleted right after transcription) | Transcript on the viral row: same as above. Copy in the transcription layer: 7 days, and erased through the transcription organ on purge, including a job still processing |
| Classification (niche, profession, format, attention trigger, hook, structure blueprint) | LLM (Anthropic) over caption + transcript | Same as the viral |
| **Estruturas** (headline formula, format, objectives, typed blocks with name / time / instruction / a note describing the original video, per-field provenance) | Derived by platform administrators, by the importer, or by an AI draft from an analysed video; an auto-draft is invisible to members until an administrator publishes it | While `ativa` and used; **24 months unused ⇒ flagged for administrator review** (§5) |
| Content-free audit events (who / when / what) | Our own system | Append-only; **carry no handle**: the profile id only, so a purged profile's history does not say who it was |

Not processed: private accounts, stories, comments' authors, DMs, follower lists, or anything about people appearing in a video beyond the speech in the transcript.

## 2. Purpose test

**Legitimate purpose:** client orgs use a platform library of script **structures** (hook, format, attention trigger, block order) derived from public content that performs well, to write their **own** original content. That is a normal commercial interest in competitive and market analysis, and it is lawful.

**Specific and explicit:** structure analysis for content creation only. Explicitly excluded:
- profiling the creator as a person;
- republishing their content;
- contacting them;
- using their data to train models;
- showing a creator's photo, follower count, monitoring status or inclusion origin to client orgs.

**Recipients are now all client orgs of the platform** (v1 excluded sharing across orgs; v2 accepts it because the shared object is the structure plus handle + display name, not the creator's picture or audience, and because the safeguards of §5 apply platform-wide). The library is never public.

## 3. Necessity test

- The purpose cannot be met without reading the posts. We only take what the public profile already shows, plus the speech transcript, because the hook is usually spoken.
- **Minimisation (built):**
  - only public business/creator accounts; only platform administrators register or import profiles (max 1000 library profiles);
  - **client orgs receive handle + display name only** (owner decision 2026-11-15): no photo, no follower count, no status, no monitoring flag, no inclusion origin;
  - **a profile retained only because an Estrutura references it drops its photo and follower count**;
  - classifier output is validated against the source text (H1 fix);
  - audio is never stored after transcription;
  - per-reel limit of 3 minutes;
  - daily caps on transcription minutes, syncs and classifications.
- A less intrusive alternative (captions only, no transcripts) was considered. It is kept as a fallback: transcription can be turned off independently, through the shared `transcricao_habilitada` and the library lane's own caps.

## 4. Balancing test

**Data subject's reasonable expectations:** the creators run public business/creator accounts and publish to be seen and studied. Analysis of public posts by other professionals in the same market is within what they can reasonably expect (Art. 7 §4: data made manifestly public, used in line with that publication). Speech in a public Reel is part of the published content. Expectation is weaker where the creator's pattern is kept for a long time or shown to many organisations: the retention and recipient-minimisation safeguards below answer exactly that.

**Impact on the creator:** low.
- Nothing is republished or attributed to them outside the platform's authenticated workspace.
- Nothing is used to decide anything about them.
- Client orgs see only handle + display name next to the structure; the picture, audience size and the fact that we monitor them are not shown.
- The data stays behind authentication, with no browser grant on the library tables (the API is the only door). Thumbnails are in a private bucket with signed URLs (15 min).

**Sensitive data:** a creator may say sensitive things in a Reel (health, religion). We don't extract or tag such data; the classifier only outputs content-structure fields. Residual risk: it can remain in the raw transcript. Mitigated by retention, the opt-out and the purge.

**Third parties in the video:** only their speech, if any, ends up in the transcript. Same mitigations.

**Open point for the controller / DPO:** whether keeping Estruturas after the source video's media has expired is covered by this balancing (they hold the structural pattern and short notes about the video, not its media or voice). The 24-month review (§5) is the control proposed for it.

**Conclusion (draft):** the platform's interest prevails, provided the safeguards in §5 stay in place. Not yet signed.

## 5. Safeguards (all required for the basis to hold)

1. **Opt-out ⇒ purge.** A creator can ask, through the contact in §6, to stop being monitored. A platform administrator registers the handle in the opt-out list. That purges everything about it across the whole platform at once — profile, videos, blobs, transcripts (through the transcription organ, including jobs still processing) AND its Estruturas, in one transaction, leaving only content-free events — and blocks it from being registered, imported, synced or processed again. The block is checked inside the profile-creation transaction and re-checked at import time and at the start of every per-video job. This also covers the Meta Platform Terms' "delete on request".
2. **Retention:**
   - 90 days after a profile is paused or referenced by no brand, then purged (`biblioteca_retencao_dias`); a profile is exempt only while a non-archived Estrutura or a brand selection references it;
   - **a retained profile is minimised**: photo and follower count dropped, with a `minimizado` event;
   - its videos' media, transcripts and thumbnails still expire by age, except the videos a brand selected;
   - **24 months unused ⇒ administrator review**: an `ativa` Estrutura with no use, edit or publication in 24 months is flagged (event `revisao_por_desuso_sinalizada`, once per window) for a platform administrator to keep, archive or delete; nothing is archived automatically;
   - immediate purge on delete or opt-out; orphan-blob sweep; uploaded load documents deleted after the run and swept if stranded; transcription-layer copy kept 7 days.
3. **Transparency.**
   - Minha Biblioteca tells the org that only public accounts are in the library, and that creators can opt out through the contact in §6.
   - The platform privacy notice, section 18, version 1.2 (2026-11-15), describes the platform-wide library, the recipients and the retention.
4. **Security:** the review fixes are H1 (stored prompt injection), M1 (bounded pagination), M2 (retention), M3 (grants), L1–L4, and the 2026-11-15 platform review: the migration refuses to apply over legacy org-owned rows; worker errors carry only the exception class name; the add-by-link permalink is stored canonical and validated; the toolkit loader only talks to `https`. Media is fetched only through the SSRF-safe `safe_fetch`, from the Instagram CDN allow-list. Known deferred item: the service role still holds table-level writes on the library tables (destination EST-RO, `NOC-REMEDIATE[cs-service-role-writes]`).
5. **Sub-processor and international transfer (Art. 33):** captions and transcripts are sent to Anthropic (US) for classification and generation. Recorded in the ROPA and in the sub-processor list.
6. **Kill switch:** `biblioteca_ingestao_habilitada` defaults OFF and fails closed, so processing can be stopped at once.

## 6. Owner / controller actions

- [x] (2026-10-10) **Opt-out contact:** `joaoraphaelsst@gmail.com`, configurable via `biblioteca_optout_contato`.
- [x] (2026-10-10) **Privacy notice v1.1** (section 18) and **ROPA** entry.
- [x] (2026-11-15) **Privacy notice v1.2** (section 18, platform-wide library) written; ROPA amended.
- [ ] **Review of this v2 draft by `legal-advisor` / the DPO, then signature below.** Until signed, v1 governs.

## 7. Review

Re-assess if:
- the purpose changes (e.g. training, publishing, contacting creators);
- a new data source is added (TikTok, YouTube) — **triggered 2026-11-04: Apify public-profile scraping added as the transitional source (Apify = sub-processor, see ROPA); owner decision, re-assess when Meta verification lands and Business Discovery becomes the default again**;
- the recipients widen beyond the platform's client orgs, or the minimised view (handle + name) grows;
- complaints or opt-outs show expectations were misjudged.

Otherwise re-assess every 12 months. Next review after signature: 12 months later.

## Assinatura

**Assinatura do controlador / encarregado: ____ (pendente)**

Data: ____ (pendente)

Status: **RASCUNHO v2, NÃO ASSINADO.**
