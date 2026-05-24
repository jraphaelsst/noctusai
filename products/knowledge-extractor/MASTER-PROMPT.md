# CLAUDE.md · knowledge-extractor

> **What this repo is.** A standalone automation that ingests recorded course
> classes from a Google Drive shared link, transcribes their audio with
> OpenAI, and produces summaries — the first step toward extracting a social-
> media course's methodology and turning it into an automated media-creation
> platform.
>
> **What this repo IS, structurally.** A **noc product in waiting.** It is
> shaped like a single NoctusAI product (`products/<slug>/`) so that when noc
> absorbs it, absorption is a *move + seam-swap*, not a rewrite. Every external
> dependency (Drive, transcription, summarization) lives behind a **named seam**
> whose local adapter maps 1:1 onto an existing `noctusai_lib` seam — see §3.
>
> **Auto-loaded every session.** Read §0–§1 every turn; open §3 / §6 when
> touching the pipeline or planning absorption.

---

## 0 · Goal & roadmap

**Prime directive:** build this the way noc builds products, so noc can absorb
it into `products/knowledge-extractor/` with minimal friction. When in doubt,
ask "how would the seed do this?" and mirror the seam.

**The flow (step 1 — what we're building now):**

```
Drive shared link → download videos → extract audio (ffmpeg)
  → transcribe (OpenAI) → summarize (OpenAI) → write transcript + summary
```

**Roadmap (step by step — do NOT build ahead of the current step):**

| Step | Goal | State |
|---|---|---|
| **1** | Drive → transcribe → summarize. Eternalize raw class content. | ⏳ building |
| **2** | Extract the course's *methodology* + content knowledge into structured, reusable form. | 📋 next |
| **3** | Turn that knowledge into an automated media-creation platform. | 📋 future |

---

## 1 · Inherited methodology (from noc)

This repo follows NoctusAI's working methodology. The authoritative source is the
sibling repo: **`../noctusai/CLAUDE.md`** (universal rules) + **`../noctusai/KNOWLEDGE-BASE/`**
(depth). Read those when a rule here is too terse. The rules below are the subset
that bites most often here — inlined so they survive absorption (a durable doc
must not depend on a path that may move → noc § *Durable docs are self-contained*).

- **Seed first / named seams.** Every external dependency flows through a NAMED
  seam (a `Protocol` + `Fake` + `Real` + `factory`), never an inline SDK call in
  business logic. A dependency NOT behind a seam = a structural fork. Our seams
  deliberately mirror `noctusai_lib` so absorption swaps the adapter, not the caller.
- **No silent errors.** No `except: pass`, no silent degraded fallback, no
  deferred item without a named destination, no "✓" when the output was red.
  Ambiguity is a silent error — ask.
- **No workarounds / no monkey-patching our own code — including in tests.** Use
  the real API/SDK. In tests: seed real data + inject fakes via dependency
  injection. `unittest.mock.patch` is allowed ONLY for *external* services
  (OpenAI, network) — never to disable our own guards.
- **Codebase is source of truth.** Docs / memory / another agent's report are
  derived and drift. Verify against the tree (`Read`/`git diff`/`pytest`) before
  acting on any claim. Doc disagrees with code → code wins; fix the doc same change.
- **DRY — recurrence rule.** N=2 → triage (formalize / refactor / accept-with-
  rationale). N=3 → MUST extract to a shared module. Don't ship the 3rd copy.
- **AST-first, never regex on code.** Code edits go through proper edits, never
  `sed`/`awk` on source. Regex is for prose, search, logs.
- **MCP-first scripts.** New automation is an exposable capability — prefer a
  tool over a bare `scripts/*.sh` one-off. (Pre-absorption we have no MCP server
  yet; the CLI in `backend/app/cli.py` is the temporary entry point and is the
  thing that becomes routers + an MCP tool on absorption.)
- **Finish the session — verify, don't assume.** Before "done": `cd backend &&
  pytest` must be green. Never mark a change complete on a red run. Quote the
  command + result.
- **Never auto-commit or push.** Commit only when asked, only your own work;
  `git status` first; explicit-path `git add` (never `git add .`/`-A`).
- **🔒 `main` is PROTECTED — never push to / merge into `main` without the user's
  explicit, per-action consent.** `main` holds the *preserved original* (course
  extraction + baseline methodology). All methodology development happens on the
  **`methodology-dev`** branch. Committing locally on `methodology-dev` when asked
  is fine; but pushing `main`, merging into `main`, or fast-forwarding `main` each
  require a fresh explicit "yes" from the user — approval for one such action never
  carries to the next. When in doubt about which branch you're on, `git branch`
  first. This rule overrides any general "commit when asked" latitude above.
- **Reading discipline.** Narrow-read large/unknown files (outline first, bodies
  for what you'll edit). Delegate broad multi-file discovery to the Explore agent.
- **Branching-dispatch** (parallel multi-agent dev). When the user says "dispatch
  / branch agents or a task", "run in parallel", or "branching-dispatch": follow
  **`doc/branching-dispatch.md`** — decompose into disjoint subtasks, one agent per
  isolated `feat/*` worktree branch off `methodology-dev`, then evaluate, detect
  collisions, reconcile, and land the result on `methodology-dev` (never `main`).
- **Docs live in `doc/`.** Durable instructions, workflows, decisions, and
  assessments go in `doc/` (the "guide manual"). Course knowledge stays in
  `data/methodology/`. `.docx` are generated artifacts (gitignored) — regenerate
  via `app.services.docx_export`, never hand-edit or version them.

---

## 2 · Tech stack

Mirrors noc so absorption is drop-in. Standalone uses `>=` floors (the user's
Python is 3.14); **absorption re-pins to noc's exact versions** (`pydantic==2.9.0`,
`fastapi==0.115.5`, …) and installs the seed editable libs.

- **Language/runtime:** Python 3.x.
- **Config:** `pydantic` v2 + `pydantic-settings` (mirrors `ProductSettings`).
- **AI:** `openai` SDK (transcription + chat). Lazy-imported (noc § *lazy SDK import*).
- **Drive:** Google Drive v3 API (`google-api-python-client`) — primary, supports
  API-key (public links) **and** OAuth (private/third-party shares). `gdown` kept
  as a no-key fallback. Both sit behind the Drive seam; routed by `DRIVE_BACKEND`.
- **Media:** `ffmpeg` (system binary) for audio extraction + chunking.
- **HTTP / tests:** `httpx`, `pytest`, `pytest-asyncio`.
- **API layer (later):** FastAPI — added when step 1 needs an HTTP surface;
  on absorption `backend/app/main.py` becomes `create_product_app(...)`.
- **Storage (later):** filesystem now (`data/`); on absorption → Supabase schema
  `knowledge_extractor` + `backend/migrations/`.

---

## 3 · Architecture — the flow + the absorption seam map

The pipeline (`backend/app/pipeline.py`) is built with **dependency injection**:
the orchestrator receives a downloader, an audio extractor, a transcriber and a
summarizer. Default wiring builds the real adapters; tests inject fakes. Each
seam's local module mirrors the signature of its `noctusai_lib` counterpart, so
**absorption = delete the local adapter, import the seed one** (the caller is unchanged).

> **ABSORBED 2026-05-23 — seam status** (project `container-first-codify-and-absorb-ke`):
> - **LLM — SWAPPED ✅.** `transcribe_audio` / `chat_completion` / `generate_embedding`
>   now come from `noctusai_lib.integrations.llm` (re-exported by
>   `app/integrations/llm/__init__.py`; the local OpenAI adapters were deleted;
>   `create_product_app` auto-wires credential + provider resolution).
> - **google_drive / media / vectors — GAPS, kept local ⏳.** The seed ships no
>   signature-compatible counterpart (Drive: no `download_folder`/write surface;
>   media: no audio extract/chunk; vectors: no pgvector store at all). Per
>   verify-the-seed-ships-it these stay local + a seed-lift is filed:
>   `projects/seed-lift-ke-gap-seams/` (vectors/pgvector is the high-value
>   cross-product lift). Do NOT degrade them to force a swap.

| Pipeline stage | Local module (now) | noc seam (on absorption) |
|---|---|---|
| Resolve link / list folder | `app/integrations/google_drive/` (`parse_drive_url`, `DriveV3Downloader._walk_sync` recursive `files.list`) | `noctusai_lib.integrations.google_drive` (`parse_drive_url`, `make_drive_downloader`, `DriveReader`) |
| Download video bytes | `DriveV3Downloader.download_folder()` (API key or OAuth; gdown fallback) | `make_drive_downloader(api_key=… \| oauth_credentials=…).download()` per file |
| Extract / chunk audio | `app/integrations/media/audio.py` (ffmpeg) | `noctusai_lib.integrations.media` (multimodal media seam) |
| Transcribe audio | `app/integrations/llm/audio.py::transcribe_audio` | `noctusai_lib.integrations.llm.transcribe_audio` (auto-wired by `create_product_app` lifespan) |
| Summarize transcript | `app/integrations/llm/chat.py::chat_completion` | `noctusai_lib.integrations.llm.chat_completion` |
| Persist results | `data/` files | Supabase schema `knowledge_extractor` |

**Rule:** keep local seam signatures matching the noc ones above. If you must
diverge, document it here as an absorption note — never silently drift.

**Absorption note — Drive WRITE surface (divergence).** The noc Drive seam is
download-oriented; we added a small write surface to publish generated docx back
into Drive: `DriveDownloader.list_children` / `create_folder` / `upload_file`
(real impl in `DriveV3Downloader`, in-memory in `FakeDriveDownloader`, gdown
raises `NotImplementedError`). It's driven by `app/services/drive_publish.py`
(`publish_docx_tree`, idempotent by filename) and the `cli upload-docx` command.
OAuth gained `WRITE_SCOPES = drive.readonly + drive.file` (least privilege — the
app only manages files IT creates); requesting it re-runs consent once and the
broadened token is cached. On absorption, map these onto the seed's Drive write
API (or a storage seam) — callers (`drive_publish`) stay unchanged.

---

## 4 · Directory shape (mirrors `products/<slug>/`)

```
knowledge-extractor/
  CLAUDE.md                  ← this file (product agent guide; auto-loaded)
  README.md                  ← human quickstart
  doc/                       ← guide manual (dev docs): branching-dispatch, assessments, decisions
  .env.example               ← config contract (copy to .env; .env gitignored)
  .gitignore
  requirements.txt           → backend/requirements.txt (canonical)
  backend/
    app/
      config.py              ← Settings (pydantic-settings); mirrors ProductSettings
      pipeline.py            ← DI orchestrator: download → audio → transcribe → summarize
      cli.py                 ← temporary entry point (→ routers + MCP tool on absorption)
      logging_config.py
      integrations/
        google_drive/        ← Drive seam (Protocol + Fake + gdown Real + factory)
        media/               ← ffmpeg audio extract + chunk
        llm/                 ← transcribe_audio + chat_completion (OpenAI), lazy import
      services/              ← transcription (chunk+stitch) + summary services
    migrations/              ← future Supabase schema knowledge_extractor
    tests/                   ← pytest (fake-driven; no network)
    requirements.txt
    pytest.ini
  data/                      ← gitignored outputs: downloads/ transcripts/ summaries/
```

---

## 5 · Build · test · run

```bash
# one-time
python3 -m venv backend/.venv && source backend/.venv/bin/activate
pip install -r backend/requirements.txt          # ffmpeg must already be on PATH
cp .env.example .env                              # then fill OPENAI_API_KEY

# verify (always green before "done")
cd backend && pytest                              # fake-driven, no network/keys needed

# run the flow
cd backend
python -m app.cli run --drive-url "<google-drive-folder-share-link>"
python -m app.cli run --video /path/to/local.mp4   # process a local file (no Drive)
python -m app.cli run --fake                        # demo with sample data, no keys
```

Outputs land in `data/transcripts/<video>.md`, `data/summaries/<video>.md`, and a
`data/manifest.json` index.

**Methodology automations** (knowledge-base maintenance):

```bash
cd backend
python -m app.cli build-manual      # assemble data/METHODOLOGY.md from per-module files (deterministic, no LLM)
python -m app.cli check-anon        # scan methodology+doc for anonymization-policy leaks (exit 1 on findings)
python -m app.cli audit-coverage    # transcript→methodology coverage audit → doc/analysis/ (needs OPENAI_API_KEY)
```

Anonymization is also enforced at commit time: `git config core.hooksPath .githooks`
installs a pre-commit hook running `check-anon --staged` (blocks leaky commits).
NOTE: `cli methodology` (LLM re-synthesis) depends on `data/summaries/`, which has
been removed — use `build-manual` to rebuild the manual from the per-module files.

---

## 6 · Absorption checklist (when noc absorbs us)

> **Status (2026-05-23): ABSORBED + frontend-bearing.** P1–P3 absorbed + containerized (backend); **P4** added the HTTP API (`app/routers/{catalog,methodology,kb,runs}_router.py` — the CLI pipeline over HTTP) + the full house SPA (`frontend/`, `createProductApp` nav, single-container `serve_spa`). Items 1 & 4 below are DONE; the CLI (`app/cli.py`) is retained for local/batch use. See `projects/container-first-codify-and-absorb-ke/` §6 (P4).

1. Move repo contents → `products/knowledge-extractor/` (backend/ + frontend/). ✅
2. `backend/app/main.py` → `create_product_app("Knowledge Extractor", "knowledge_extractor", settings, …)`.
3. Swap each local seam for its `noctusai_lib` counterpart per §3 (callers unchanged).
4. `cli.py` flow → product routers + a `noctus.*` MCP tool (MCP-first).
5. Persistence → Supabase schema `knowledge_extractor` + `backend/migrations/001_*.sql`.
6. Re-pin `requirements.txt` to noc exact versions + `-e seed/lib/backend` / `-e seed/framework/backend`.
7. Closest existing relative is `products/social-wiring/` (already does Drive + `transcribe_audio` + multimodal media for social content) — reuse its patterns.

---

## 7 · MCP / skills keep-list

Inherited from noc: **`noctusai` · `supabase` · `n8n` · `waha`** (anything else needs
explicit user approval). Skills: `update-config` · `loop` · `schedule` · `security-review`.
The `Google_Drive` MCP may be used for *browsing/inspecting* the user's Drive when
helping interactively — but the pipeline itself must go through the Drive seam (§3),
not an MCP call, so it stays absorbable.
