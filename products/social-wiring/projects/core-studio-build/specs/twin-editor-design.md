# Twin video editor — our design (draft v0, 2026-11-04)

Status: **design draft for the owner interview. Nothing is decided and nothing is built.** It derives from the private study `[private study: twin/specs/twin-operations.md]` and `[private study: twin/specs/editor-analysis.md]`, read for structure and data flow only. No vendor code, copy or assets come here.

## 0 · The principle: the AI edits, you adjust (owner, 2026-11-04)

> "the most automated video is what i want, so we can produce them in batches. 10 automated reels, 100
> … i want the editing power, but i dont want to create nothing."

- **The AI makes every editing decision.** It splits the video into scenes; for each scene it picks the clip (or none), the time window, the layout, the caption pages, the caption style, the music, the volume and the pace. The decisions come from a **workspace editing preset** (§ 0.2), so 100 reels look like one brand, not 100 random edits.
- **The editor is for adjusting, never for building.** Every control in § 5 stays, but each one opens already filled by the AI, marked as an AI choice, with "outra opção" (ask the AI for an alternative) next to the manual override. A reel that needs no change is approved without opening the editor.
- **The unit of work is the batch, not the video.** You give it N scripts and a Twin, and get N edited reels back, ready to review. The flow: create batch → generate (avatar) → AI edit → **review queue** → approve (one at a time or in bulk) → bulk export → publish or schedule.
- **Nothing blocks on a human.** No step waits for a manual choice. The human gate is only "approve" (and it can be switched off per workspace: auto-approve when every AI check passes, § 0.3).

### 0.1 Batch flow

```
CoreStudio sources only: Roteiros · Headlines favoritas (the AI writes the roteiro in CoreStudio) · Esteira cards "Pronto para vídeo"
  +  Twin profile  +  Editing preset
        │ POST /batches {source, ids[], profile_id, preset_id}
        ▼
 per item, in parallel (bounded by the provider's concurrency):
   avatar render (provider) → analysis → AI edit (preset) → AI self-check → render preview
        │ item.status: queued → generating → editing → ready_for_review | needs_attention | failed
        ▼
 REVIEW QUEUE: a grid of reels with play-in-place, and the AI's flags ("clip may contain text", "low relevance", "caption word uncertain")
   ✓ approve · ✎ adjust (opens the editor in review mode, "Aprovar e próximo") · ↻ redo with AI · ✕ discard
        │ approved
        ▼
 BULK EXPORT (server render for batches, see § 6) → BULK PUBLISH/SCHEDULE (spread across days and times)
```

### 0.1b Where it lives, and where its inputs come from (owner, 2026-11-04)

- **Inside our CoreStudio** (social-wiring's `media-creation` nav group). It is one sidebar item, **Twin** (`/media-creation/twin`), between Carrosséis and Biblioteca. Its sections are **in-page subtabs**: Lotes · Revisar · Presets de edição · Perfis · Créditos. There are no new sidebar groups (the MENUS.md rule: in-page tabs stay in-page).
- **Every input comes from CoreStudio context, never from outside it.** Scripts are CoreStudio Roteiros. Headlines favoritas get their roteiro written by CoreStudio's own generation (Meu Perfil + Segundo Cérebro + Branding). Esteira cards come from the "Pronto para vídeo" column. There is no paste box, no CSV upload, and no free-text theme that bypasses CoreStudio.
- **CoreStudio context also drives the edit:** caption styles come from **Branding**, the clip library from **Minha Biblioteca**, and the tone (which picks the music) from the roteiro and Meu Perfil. A finished reel goes back to the Esteira card and the Biblioteca, so the pipeline stays one loop: headline → roteiro → Twin reel → publish.

### 0.2 Editing preset (per workspace, versioned)

The brief the AI edits to. It is set once and reused by every batch. It replaces choosing a caption style or a song per video.

```ts
interface EditPreset {
  id: string; name: string; version: number;
  captions: { styleId: string /* from branding */; positionPct: number; maxWordsPerPage: 2|3|4; emphasis: 'keywords'|'every_word'|'none' };
  broll: { density: 'low'|'medium'|'high' /* share of the speech covered */; maxSeconds: number; sources: ('stock'|'library'|'ai_image'|'ai_video')[]; layout: 'auto'|'full'|'split'; avoid: string[] /* topics or visuals */ };
  music: { mode: 'auto_by_mood'|'fixed'|'none'; trackIds?: string[]; volume: number; duck: boolean };
  pace: { speed: number; trimSilences: boolean; cutFlash: boolean };
  approval: 'always_review'|'auto_approve_when_clean';
}
```

### 0.3 AI self-check (what puts a reel in "needs attention")

A reel is flagged instead of going straight to "ready" when:
- a clip fails the frame audit (on-screen text, a logo, a face that isn't licensed);
- relevance to the spoken words is below a threshold;
- an ASR word has low confidence (shown as an uncertain caption word);
- the music mood conflicts with the script tone;
- the reel's length goes past the platform limit.

The flags are what the reviewer sees first. Everything else is presumed fine.

## 1 · What the editor is for

A talking-head video of the customer's digital twin, already generated by an avatar provider, gets the finishing pass that makes it a Reel:
- synced captions;
- cut-away clips or images (b-roll) over chosen moments;
- background music;
- a pace adjustment;

then it is exported as a 9:16 MP4 and handed to publishing.

What the reference teaches (our reading):

| They did | Keep / change | Why |
|---|---|---|
| Server **analysis** first: transcript with **word timings**, cut into scenes, a "visual idea" per scene | **Keep** | It is what makes editing a 60 s video take minutes. The user reviews suggestions instead of building a timeline. |
| A **fixed scene list**, at most one b-roll per scene, capped at 4 s | **Loosen** | Allow up to N overlays per scene, with the cap set per workspace (default 4 s). The scene stays the unit of work. |
| A **4-step wizard** (captions → clips → music → finish) | **Change** | One screen with a scene strip and side tabs. The steps were free to jump between anyway, so a wizard only adds clicks. A first-run guided path can keep the order. |
| **One compositor** drawing the preview and the export, so the export matches the preview | **Keep, the core idea** | A canvas compositor shared by the preview and a WebCodecs encoder, with a server ffmpeg fallback. |
| The whole state **autosaved** with no indicator, errors ignored, no undo | **Fix** | A versioned document, a visible saved/unsaved state, undo/redo, and conflict detection. |
| Caption text **not editable** | **Fix** | ASR errors are inevitable. Allow editing word text and merging/splitting caption pages. |
| b-roll **scraped from TikTok** | **Do not copy** | Copyright and platform-terms risk. Use licensed stock (Pexels/Pixabay APIs), the workspace's own media library, and AI images. |
| 3 fixed caption styles and 6 bundled music tracks | **Change** | Caption styles come from the workspace **branding** (our design-system tokens). Music is a licensed library plus the workspace's own tracks. |
| Linked pages and features that aren't there (publishing, scheduling, "from a Reel") | **Don't repeat** | Show a feature only when it works. |

## 2 · Data flow

```
 Avatar video (provider output, stored in our bucket)
        │ POST /edit-projects {video_id}
        ▼
 ANALYSIS job (server, async; the progress stage is shown on the loading screen)
   1 transcribe with word timestamps        ← transcription organ (needs words[], see §7)
   2 segment into scenes (pauses + sentence boundaries + LLM pass)
   3 per scene: visual idea + search terms   ← LLM
   4 pre-fetch candidates per scene           ← stock providers (licensed), library, AI image
        │ project.status = ready
        ▼
 EDITOR (browser)
   load project → EditDoc (the user's choices, versioned)
   preview = compositor(t, EditDoc, media)   ← media resolved through the server proxy/cache
   each change → command (undo stack) → debounced PATCH (If-Match: version)
   asset prep: when a choice needs a trimmed/proxied clip → POST prepare → poll
        │ Export
        ▼
 RENDER
   browser path: compositor + WebCodecs (H.264/AAC, 30 fps) → upload → output
   server path:  same EditDoc → ffmpeg render job (fallback / mobile / old browsers)
        │ output_url, video.is_edited = true
        ▼
 PUBLISH (our Instagram publishing in social-wiring) · download
```

Rules:
- **The server owns the analysis and the assets. The client owns the choices.** The EditDoc is the only thing the client writes, apart from explicit jobs.
- **Every job is fire-and-poll with a visible stage** (server-state rule: a queued job hands off to polling; never fake progress).
- **Media come through our proxy with CORS**, because the canvas must stay untainted for export. A clip that isn't prepared yet shows a "preparing" overlay in the preview. Never a silent placeholder.

## 3 · Data model

```ts
// server-produced, read-only to the client
interface Analysis {
  duration: number;                       // s
  words: Word[];                          // whole-video word timeline
  captionPages: CaptionPage[];            // suggested grouping (2–4 words, ≤ 2 lines)
  scenes: Scene[];
}
interface Word { i: number; text: string; start: number; end: number }
interface CaptionPage { id: string; wordIdx: [number, number] }      // inclusive range into words
interface Scene {
  id: string; index: number; t0: number; t1: number;
  layout: 'full' | 'split';               // split = overlay in the top band, host below
  idea: string; searchTerms: string[];
  candidates: Candidate[];
}
interface Candidate {
  id: string;
  kind: 'video' | 'image';
  source: 'stock' | 'library' | 'ai_image' | 'ai_video';
  provider?: 'pexels' | 'pixabay' | string;
  license: { id: string; attribution?: string };   // stored for every asset we render
  thumbUrl: string; previewUrl?: string; duration?: number;
  score?: number;                         // relevance 0..1 (+ "why" for the tooltip)
}

// client-owned document (PATCHed, versioned)
interface EditDoc {
  version: number;                        // optimistic concurrency (If-Match)
  captions: {
    enabled: boolean;
    styleId: string;                      // from the workspace branding caption styles
    positionPct: number;                  // 20..85
    textOverrides: Record<number, string>;   // word index → corrected text
    pageOverrides?: CaptionPage[];        // when the user regroups pages
  };
  scenes: Record<SceneId, SceneEdit>;
  audio: { musicTrackId: string | null; musicVolume: number /*0..1*/; duckUnderVoice: boolean };
  transitions: { cutFlash: boolean };
  output: { speed: number /*1..1.25*/; aspect: '9:16' };
}
interface SceneEdit {
  layout?: 'full' | 'split';              // user may override the suggestion
  overlays: Overlay[];                    // 0..maxOverlaysPerScene
  host: { zoom: number; x: number; y: number };   // framing of the twin in split layout
}
interface Overlay {
  id: string; candidateId: string;
  at: [number, number];                   // window inside the scene, snapped to word boundaries, ≤ capSeconds
  clipIn: number;                         // in-point inside the source clip
  fx: { kenBurns?: boolean; fadeToGray?: boolean; frame?: { zoom: number; x: number; y: number } };
}

interface EditProject {
  id: string; videoId: string;
  status: 'analyzing' | 'ready' | 'rendering' | 'done' | 'failed';
  stage?: 'preparing' | 'transcribing' | 'segmenting' | 'searching' | 'curating' | 'finishing';
  analysis?: Analysis; doc: EditDoc;
  assets: Record<string /*candidateId:clipIn*/, { status: 'pending' | 'ready' | 'failed'; url?: string }>;
  render?: { status: 'idle' | 'running' | 'done' | 'failed'; progress?: number; path?: 'browser' | 'server'; outputUrl?: string; error?: string };
}
```

## 4 · API contract (draft, for `noc-contract-first`)

Base: `/api/twin/edit-projects`. Tenant-scoped by workspace, and every route requires auth (strict 401).

| Method + path | Purpose | Notes |
|---|---|---|
| POST `/` `{video_id, restart?}` | Create or resume the project and start analysis | Idempotent per video unless `restart` |
| GET `/{id}` | Project with analysis, doc, assets and render | The single poll endpoint, with ETag |
| PATCH `/{id}/doc` `If-Match: version` | Save the EditDoc | 409 → client shows the conflict and offers reload/merge |
| POST `/{id}/scenes/{sid}/search` `{query, provider?}` | New candidates for a scene | Rate-limited |
| POST `/{id}/scenes/{sid}/images` `{hint?}` | Generate an AI image | Spends credits if we meter it |
| POST `/{id}/assets/prepare` `{candidate_id, clip_in}` | Download, trim and proxy one clip | Job; poll GET |
| POST `/{id}/render` `{path:'server'}` | Server render | Job; poll GET |
| POST `/{id}/render/upload` (multipart) | Store a browser render | Sets the output and `video.is_edited` |
| GET `/{id}/download` | 302 to a signed URL | Same-origin download |
| — | Music library | `GET /api/media/music?workspace=…` (shared organ, §7) |
| POST `/api/twin/batches` `{profile_id, preset_id, source:'roteiros'\|'headlines'\|'esteira', ids:[...]}` | Create a batch; fans out one job per item (headlines first go through CoreStudio roteiro generation) | Credits are estimated and reserved up front; ids must belong to the workspace's CoreStudio |
| GET `/api/twin/batches/{id}` | Batch with items (status, flags, preview, project id) | Poll (or SSE) while running |
| POST `/api/twin/batches/{id}/approve` `{item_ids}` | Bulk approve | |
| POST `/api/twin/batches/{id}/items/{iid}/redo` `{scope:'all'\|'scene', scene_id?}` | Ask the AI to edit again | |
| POST `/api/twin/batches/{id}/export` `{item_ids}` | Bulk server render | Job |
| POST `/api/twin/batches/{id}/schedule` `{item_ids, plan:{start, per_day, times[]}}` | Spread the approved reels across the calendar | Uses our Instagram publishing |
| GET/PUT `/api/twin/presets[/{id}]` | Editing presets | Versioned; a batch pins the preset version |
| POST `/{id}/scenes/{sid}/alternative` `{what:'clip'\|'layout'\|'window'}` | "outra opção": the AI's next-best choice for one decision | Keeps the edit AI-made |

## 5 · UI

**Visual language: the noc pattern only** (owner, 2026-11-04). The app shell and the seed tokens (`@noctusai/lib/design-system/tokens.css`), seed/lib components, light and dark themes. Nothing of the reference's look (colours, shapes, motion) is reused. Clickable prototype: https://claude.ai/artifact/K6eFja24ckb2Qtsu1nzDam

### 5.1 Layout (desktop ≥ 1100 px)

```
┌ Header: ← Vídeos · "Editar — {título}" ········ [saved ✓ / salvando… / não salvo] [↶][↷] [Exportar ▸] ┐
├───────────────────────────────┬──────────────────────────────────────────────────────────────────────┤
│  PREVIEW 9:16 (canvas)        │  TABS:  Cenas · Legenda · Áudio · Saída                               │
│  overlays: "preparando clipe"  │  ─────────────────────────────────────────────────────────────────── │
│  ▶ ⟲ -5s +5s   0:12 / 0:58  🔇 │  [Cenas] focused scene: what is said (clickable words = the overlay   │
│                               │   window), layout full/split, overlay list (add/remove/trim/in-point), │
│                               │   candidate grid (Estoque · Biblioteca · Imagem IA), search box        │
│                               │  [Legenda] style cards (from branding), position, edit words/pages    │
│                               │  [Áudio] music list with preview, volume, ducking                     │
│                               │  [Saída] speed, summary, render progress, download, publish           │
├───────────────────────────────┴──────────────────────────────────────────────────────────────────────┤
│ SCENE STRIP: [1 ▣ 0:00–0:06] [2 ▢ 0:06–0:11] [3 ▣ …] …  ← thumbnails, overlay marks, active scene     │
│ WORD RULER under the strip: words as ticks; drag the edges of an overlay window to trim               │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
- **Tablet and mobile (< 1100 px):** the preview is sticky on top, the tabs sit below it, and the scene strip scrolls horizontally. Export defaults to the server path on mobile.
- **Loading (analysis):** a named stage list with elapsed time and "you can leave this tab". After 15 min it offers "keep waiting / restart analysis". Never an indefinite spinner.
- **Error:** the server message plus "back to videos" and "try again", and "resume" when the job is still alive.

### 5.2 Components (candidates for `@noctusai/lib` when another product needs them)

| Component | Notes |
|---|---|
| `VideoCompositor` (pure, no React) | `draw(ctx, t, doc, analysis, media)`. Used by both the preview and the export. Unit-testable frame by frame with golden snapshots. |
| `PreviewPlayer` | Hidden `<video>` as the clock and audio, canvas on top; seek/toggle handle; reports the active scene. |
| `SceneStrip` + `WordRuler` | Scene thumbnails, overlay windows as draggable ranges that snap to word edges. |
| `CandidateGrid` / `CandidateCard` | Sources as tabs, quick preview on hover or click, an "in use" badge, license info on hover. |
| `ClipInPointTrimmer` | A filmstrip of N frames with a fixed-length window to drag. |
| `CaptionStylePicker` | Live sample rendered by the compositor's caption routine, so it always matches. |
| `MusicPicker` | One preview at a time, with a volume slider. |
| `RenderPanel` | Phases (preparing → loading media → encoding → uploading, or server), progress, cancel, result actions. |
| `SaveIndicator` | Saved, saving, unsaved or conflict (server-state rule: a draft says it is unsaved). |

### 5.3 Interactions
- **Command stack:** every edit is a command (`setOverlayWindow`, `pickCandidate`, `setCaptionStyle`, …) with undo/redo. Shortcuts: Space play/pause, ←/→ ±1 s (Shift ±5 s), J/K previous/next scene, ⌘Z / ⇧⌘Z.
- **Picking a candidate** seeks the preview to the scene and starts `assets/prepare` when needed. The preview shows "preparando clipe" on that window only; the rest keeps playing.
- **Overlay window:** click a word to set the start or end, or drag in the word ruler. It is clamped to the scene and to the cap.
- **Caption fixes:** double-click a word in the Legenda tab to edit it. Pages can be split or merged.
- **Autosave:** debounced PATCH 800 ms with If-Match. On failure the indicator shows "não salvo" with retry; it never fails silently. A `beforeunload` guard warns while there are unsaved changes.

## 6 · Render

- **Browser path:** feature-detect WebCodecs (H.264 1080×1920 @ 8 Mbps, AAC 48 kHz). Fetch prepared assets through the proxy. Audio is the host narration (time-stretched server-side to `speed`, so the pitch stays) plus music mixed in an OfflineAudioContext, with optional ducking. Mux to MP4 with a library: mediabunny is a candidate (check its licence) or mp4-muxer. Then upload.
- **Server path:** the same EditDoc is interpreted by an ffmpeg job (seed media-base image). The canvas compositor and the ffmpeg filtergraph must be **checked against each other with golden frames**, or the two paths will drift.
- Output: store it, set `video.output_url` and `is_edited`, and keep the previous output.

## 7 · Seed-first mapping (to verify with `noc-verify-seed` before any build)

| Need | What we have | Gap |
|---|---|---|
| Transcription with **word timings** | Transcription organ (`specs/transcription-contract.md`) returns optional segments | **Word-level timestamps** are needed (whisper `word_timestamps`). A seed change, consumer #1. |
| ffmpeg in containers | social-wiring `media_service` (ffmpeg via the seed media-base image) | A render job runner |
| Branding → caption styles | `design-systems/branding-template` tokens | A "caption style" token group in the branding template |
| Instagram publishing | social-wiring Instagram integration (`specs/instagram-insights-api.md`) | A publishing (Reels upload) contract, if it isn't there yet |
| Stock media, music library | — | New shared organ (provider adapters with Fake+Real+factory) |
| Avatar generation (upstream of the editor) | — | Provider choice (HeyGen or others); out of this doc's scope |
| Credits and metering | — | Only if AI images or renders are charged |

Render note for batches: 100 reels can't depend on a browser tab staying open, so **batch export is a server render** (ffmpeg jobs through the hardware/queue limits). The browser path stays for a single re-export from the editor.

## 8 · Open questions for the owner (options, not decisions)

Settled 2026-11-04: automation-first plus batches (§ 0), the noc pattern for visuals, and a mockup before any UI. One screen versus a wizard no longer matters, because the editor is a review tool, so it is one screen.

1. **Approval:** always review each reel, or auto-approve the reels with no flags?
2. **b-roll sources:** stock (Pexels/Pixabay, free with attribution) + workspace library + AI image? Is AI video in v1?
3. **Overlays per scene:** one (simpler, like the reference) or several?
4. **Render:** browser first with a server fallback (cheap, fast) or server only (simpler, costs CPU on our boxes)?
5. **Music:** which licensed library? Do we allow the customer's own tracks?
6. **Avatar provider** for the twin itself: HeyGen (what the reference uses) or an alternative? This sets cost per minute and the consent flow.
7. **Where it lives:** inside social-wiring (Criação de Mídia), or a product of its own?
