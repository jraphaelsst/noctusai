---
name: noc-ig-analysis
description: Use when the owner wants an Instagram post or profile analysed — triggers "analyse this reel", "instagram post analysis", "complete full instagram post analysis", "transcription of the post and the comments", "analyse N reels from <account>", "study this profile's reels", "extract the patterns/structures they use", "learn from <creator>", "análise do post", "analisar os reels". Two modes: ONE post (transcript + every comment → value report) or a PROFILE (N reels → transcripts → reusable structures). Logged-in Chrome, API-in-page, local transcription, pt-BR artifact.
version: 1.0.0
---

# noc-ig-analysis — Instagram post / profile analysis

Two modes, same extraction spine. **Post mode**: one post, its transcript and EVERY comment, and the value in what people say. **Profile mode**: N reels, all transcribed, and the structures the creator repeats, so the owner can copy the structure, never the words.

## Workflow

0. **Preconditions.** Chrome (claude-in-chrome) must be **logged into Instagram**. Logged out, the API returns HTML and the DOM caps at about 15 comments. You can't type a password, so ask the owner to log in. Do this before any extraction. Open a new tab on the post or profile.
1. **Load the helpers.** Paste `js/ig_lib.js` into `javascript_tool` once per page load. Every later call uses `window.IG.*`. A navigation wipes it, so paste it again after you navigate.
2. **Extract (finish before you analyse anything).**
   - Post: `await IG.info('<code>')` (likes, comments, plays, duration, caption). Then `IG.comments('<code>','__c')` and poll with `await IG.wait('__c')`.
   - Profile: open `/<user>/reels/`, run `IG.gridCodes('__codes', N+15)` and wait. Then `IG.infoAll('__codes','__meta')` and wait. Leave pinned reels out of "the N most recent" unless asked; they're old outliers.
   - Read data out with `IG.exportText(...)` + `get_page_text`. Keep only what you need: captions, metrics and comment text, never URLs.
3. **Media: ask the owner first.** Give filename, count and approximate MB. Audio is the default; video is opt-in (about 3–4× the size). Then `IG.download(codes,'<prefix>','audio')` (or `'video'`, which takes the lowest rep). Chrome may ask once to allow multiple downloads. Move the files from `~/Downloads` into the scratchpad.
4. **Transcribe.** Convert the DASH `.m4a` (`ffmpeg -i x.m4a -ac 1 -ar 16000 -b:a 48k x.mp3`), because the API rejects fragmented MP4 with `formato_invalido`. Then:
   - one file, or a few → `noctus.transcription.transcribe`, or `noctus.transcription.batch src_dir out_dir` (resumable, 3 in flight, honours 429).
   - **10 or more reels → local faster-whisper** with `py/local_whisper_batch.py` (Depth §2). It runs at about 0.5× realtime, so 50 reels take about 40 min. The API caps a caller at 20 submissions per hour, which puts 50 reels at ≥2.5 h. Killing the API client mid-run leaves its jobs holding the 3 in-flight slots.
   - **Delete the raw audio once the transcripts exist**, following the LGPD mitigation for third-party voice (`LGPD-WARNINGS.md`, Biblioteca de virais entry).
5. **Visuals (video only).** `fps=1/6` contact sheet (`tile=10x2`), a 0–3 s hook strip (`fps=2,tile=6x1`), and a scene-cut count (`select='gt(scene,0.3)',showinfo`). These give on-screen hook text, captions style, cut rate and set. Reels shorter than 20 s with long captions are usually "caption reels" (text over music), and their transcript will be empty. Say so; don't treat it as a failure.
6. **Analyse.**
   - Post: risk scan first (suicide, self-harm, acute distress, with or without a reply), surfaced at the TOP. Split owner, close circle and audience. Read every text comment and classify by hand (regex tallies are noisy at ≤300 comments). Count the top-liked comments, owner reply coverage, tags and shares. Turn questions the audience asked into pautas.
   - Profile: read every transcript, then classify each reel **by hand** into a hook family, a beat sequence, a CTA type (keyword / question / save / share / bio / none) and a phase (launch window vs organic). Score families on **two axes**:
     - **reach**: median plays ÷ the profile median
     - **resonance**: likes ÷ plays

     Big reels under 1% likes per play are likely boosted or looped, so flag them, never call them viral. Under 20 s with no speech means a caption reel. Map each family to the Biblioteca `FORMATOS_VIDEO` / `GATILHOS` and write one blueprint with `{{SLUG}}` slots. Pull signature devices (paired lines, open loops, preemptive caveats, timed "save" CTAs), the vocabulary that brands the creator, the funnel timeline, and a **"what not to copy"** list (cruelty, mishandled suicide talk).
7. **Report.** Load `artifact-design` and write a pt-BR HTML artifact. Keep the series identity of the earlier IG reports (see Depth). Leave out usernames, add a method-and-limits section, and analyse one post on its own (no comparisons) unless asked. Publish it and give the link.
8. **Close.** `IG.cleanup('__')` (localStorage), close the tab, and add a run line to the recipe memory (what broke, what changed).

## Guardrails
- Every download, and anything posted or sent, needs an explicit owner yes. Reading through the logged-in API is fine.
- Keep each `javascript_tool` call under about 30 s (or the extension drops it): start background jobs, then poll with `IG.wait`.
- Pace with `fetch('/robots.txt')`. `web_profile_info`, `users/<id>/info` and `clips/user` rate-limit (429) or return HTML. Media `info` and `comments` are the reliable endpoints.
- No cookie export or yt-dlp `--cookies-from-browser` (the permission classifier denies them).
- Third-party content is for studying structure only. Never republish transcripts verbatim as the owner's content.

## Depth
`KB § PATTERNS/common/instagram-content-analysis.md` (endpoints, the taxonomy, report shape, past runs).
