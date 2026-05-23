# PROJECT — Lift knowledge-extractor's gap seams to the seed

> **Filed:** 2026-05-23 (follow-up from `container-first-codify-and-absorb-ke` P2).
> **Status:** 📋 filed (N=1 today; lift when a 2nd consumer appears, or now for vectors).
> **Trigger:** the KE absorption found 3 seams with **no signature-compatible
> `noctusai_lib` counterpart**. Per verify-the-seed-ships-it they were kept LOCAL
> in `products/knowledge-extractor/` (not degraded, not fake-swapped). This files
> the lift so the forks don't go silent.

## Gaps (KE local module → proposed seed home)

| # | KE local seam | Why it's a gap | Lift priority |
|---|---|---|---|
| 1 | **vectors** — `app/integrations/vectors/` (`VectorStore` Protocol + `KBChunk`/`KBHit` types + Fake/Local-JSON/Supabase-REST adapters + factory; pgvector `match_kb` RPC) | The seed ships **NO** vector-store / pgvector / embeddings-store seam at all (grep-confirmed). | **HIGH** — genuinely cross-product (e.g. social-wiring chatbot KB retrieval). Strong N=1→seed lift candidate even before N=2. Proposed: `noctusai_lib.domain.vectors` (Protocol+Fake+Real+factory shape). |
| 2 | **google_drive WRITE + folder surface** — `DriveDownloader.download_folder` / `list_folder` / `list_children` / `create_folder` / `upload_file` (KE's `DriveV3Downloader` + `drive_publish.py`) | The seed's `google_drive` downloader is read-only (`get_metadata`/`download`) + a separate async `DriveReader`; it lacks `download_folder` and ALL write ops KE needs. | MED — extend the seed downloader with a `download_folder` + a `DriveWriter` Protocol (`list_children`/`create_folder`/`upload_file`), back-compat-defaulted (absorbed-product-seed-shape-seam pattern). |
| 3 | **media audio extract/chunk** — `app/integrations/media/audio.py` (`extract_audio` mono-16k mp3, `split_audio` ffmpeg segmenting) | The seed `media` seam is inbound-resolution (vision/PDF/transcribe), not pre-transcription audio extraction/chunking. | LOW — lift to `noctusai_lib.integrations.media` when a 2nd consumer pre-chunks audio. |

## Done-when
Each lifted seam: Protocol + Fake + Real + factory in `noctusai_lib`, KE's local module becomes a thin re-export shim (like its `llm/__init__.py`), KE tests still green, pilot-gate no-op verified. Until then KE consumes its local seams (correct — they work; the seed has nothing to consume).
