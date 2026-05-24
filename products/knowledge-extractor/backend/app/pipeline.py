"""Extraction pipeline: download → extract audio → transcribe → summarize → write.

Built with dependency injection so each seam is swappable (real adapters in
production, fakes in tests, `noctusai_lib` seams on absorption). See /CLAUDE.md §3.

Outputs are organized by *module* (the Drive subfolder a lesson lives in):
`data/{transcripts,summaries}/<module>/<lesson>.md`. Runs are resumable — a lesson
whose transcript+summary already exist is skipped — and flat outputs from earlier
(un-organized) runs are reorganized into their module folder on contact.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Optional

from app.config import get_settings
from app.integrations.google_drive import DriveDownloader, DriveFile, make_drive_downloader
from app.integrations.media import extract_audio
from app.logging_config import get_logger
from app.services.summary_service import summarize_transcript
from app.services.text_utils import clean_lesson_title
from app.services.transcription_service import transcribe_file

logger = get_logger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mp4v"}


def is_video(file: DriveFile) -> bool:
    """True if a Drive file is a video — by MIME type OR extension.

    Crucial for this course: many lessons are stored WITHOUT a file extension,
    so extension-only detection would silently skip them. MIME type is authoritative.
    """
    if file.mime_type and file.mime_type.startswith("video/"):
        return True
    return Path(file.name).suffix.lower() in VIDEO_EXTENSIONS


# Seam signatures (kept narrow so fakes/real/seed all satisfy them).
AudioExtractor = Callable[[Path, Path], Path]              # (video, out) -> audio
Transcriber = Callable[[Path, Path], Awaitable[str]]       # (audio, chunk_dir) -> text
Summarizer = Callable[[str, str], Awaitable[str]]          # (title, transcript) -> summary


@dataclass
class VideoResult:
    """Outcome of processing one video."""

    name: str
    video_path: Path
    transcript_path: Path
    summary_path: Path
    transcript_chars: int
    summary_chars: int
    module: Optional[str] = None


@dataclass
class ExtractionPipeline:
    """Orchestrates the flow. Inject seams; defaults wire the real adapters."""

    downloader: DriveDownloader
    audio_extractor: AudioExtractor
    transcriber: Transcriber
    summarizer: Summarizer
    data_dir: Path
    results: list[VideoResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)

    # ── directories ─────────────────────────────────────────────────
    @property
    def downloads_dir(self) -> Path:
        return self.data_dir / "downloads"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def transcripts_dir(self) -> Path:
        return self.data_dir / "transcripts"

    @property
    def summaries_dir(self) -> Path:
        return self.data_dir / "summaries"

    @staticmethod
    def _sub(base: Path, category: Optional[str]) -> Path:
        return base / category if category else base

    # ── steps ───────────────────────────────────────────────────────
    async def process_video(
        self, video_path: Path, *, category: Optional[str] = None
    ) -> VideoResult:
        """Run the full flow for one already-downloaded video file.

        `category` (the module name) nests the outputs under a subfolder.
        """
        title = clean_lesson_title(video_path.stem)
        logger.info("processing: %s%s", f"{category}/" if category else "", title)

        audio_path = self._sub(self.audio_dir, category) / f"{title}.mp3"
        await asyncio.to_thread(self.audio_extractor, video_path, audio_path)

        chunk_dir = self._sub(self.audio_dir, category) / f"{title}_chunks"
        transcript = await self.transcriber(audio_path, chunk_dir)

        transcript_path = self._sub(self.transcripts_dir, category) / f"{title}.md"
        _write(transcript_path, f"# {title}\n\n{transcript}\n")

        summary = await self.summarizer(title, transcript)
        summary_path = self._sub(self.summaries_dir, category) / f"{title}.md"
        _write(summary_path, f"# Resumo — {title}\n\n{summary}\n")

        result = VideoResult(
            name=title,
            video_path=video_path,
            transcript_path=transcript_path,
            summary_path=summary_path,
            transcript_chars=len(transcript),
            summary_chars=len(summary),
            module=category,
        )
        self.results.append(result)
        logger.info(
            "done: %s (%d transcript chars, %d summary chars)",
            title, result.transcript_chars, result.summary_chars,
        )
        return result

    async def run_local(self, video_paths: list[Path]) -> list[VideoResult]:
        """Process local video files (no Drive)."""
        for path in video_paths:
            await self.process_video(path)
        self._write_manifest()
        return self.results

    async def run_from_drive(self, drive_url: str) -> list[VideoResult]:
        """Download a Drive folder/file then process every video found."""
        downloaded = await self.downloader.download_folder(
            drive_url, self.downloads_dir
        )
        videos = [d.path for d in downloaded if is_video(d.file)]
        if not videos:
            logger.warning(
                "no video files found in %s (got %d file(s): %s)",
                drive_url, len(downloaded), [d.path.name for d in downloaded],
            )
        for path in videos:
            await self.process_video(path)
        self._write_manifest()
        return self.results

    async def run_drive_files(self, file_ids: list[str]) -> list[VideoResult]:
        """Download specific Drive files by id, then process each."""
        for fid in file_ids:
            meta = await self.downloader.get_metadata(fid)
            name = (meta.name if meta else fid).replace("/", "_")
            dest = self.downloads_dir / name
            logger.info("downloading drive file %s → %s", fid, dest)
            await self.downloader.download(fid, dest)
            await self.process_video(dest)
        self._write_manifest()
        return self.results

    async def run_module(
        self,
        module_folder_id: str,
        module_name: Optional[str] = None,
        *,
        wait_seconds: int = 5,
    ) -> list[VideoResult]:
        """Process every video in one module folder, one at a time.

        - Outputs organized under `<module_name>/`.
        - Resumable: a lesson already transcribed+summarized is skipped.
        - Flat outputs from earlier runs are reorganized into the module folder.
        - Per-video errors are logged and recorded; the run continues.
        - Waits `wait_seconds` between lessons that actually get transcribed.
        """
        if module_name is None:
            meta = await self.downloader.get_metadata(module_folder_id)
            module_name = (meta.name if meta else module_folder_id).strip()

        files = await self.downloader.list_folder(module_folder_id)
        videos = sorted((f for f in files if is_video(f)), key=lambda f: f.name)
        logger.info("module %r — %d video(s)", module_name, len(videos))

        processed = 0
        for vf in videos:
            title = clean_lesson_title(Path(vf.name).stem)
            self._reorganize_existing(title, module_name)

            tpath = self._sub(self.transcripts_dir, module_name) / f"{title}.md"
            spath = self._sub(self.summaries_dir, module_name) / f"{title}.md"
            if tpath.exists() and spath.exists():
                logger.info("skip (already done): %s / %s", module_name, title)
                self.skipped.append(f"{module_name}/{title}")
                continue

            if processed > 0 and wait_seconds:
                logger.info("waiting %ds before the next lesson…", wait_seconds)
                await asyncio.sleep(wait_seconds)
            processed += 1

            try:
                dest = self._sub(self.downloads_dir, module_name) / vf.name.replace("/", "_")
                logger.info("downloading %s → %s", vf.id, dest)
                await self.downloader.download(vf.id, dest)
                await self.process_video(dest, category=module_name)
            except Exception as e:  # one bad lesson must not sink the batch
                logger.error("FAILED %s / %s: %s", module_name, title, e)
                self.failures.append(
                    {"module": module_name, "title": title, "error": str(e)}
                )

        self._write_manifest()
        return self.results

    async def resummarize(
        self, *, only: Optional[str] = None, wait_seconds: int = 0, overwrite: bool = True
    ) -> list[VideoResult]:
        """Regenerate summaries from EXISTING transcripts (no download/transcribe).

        Used to apply an upgraded summary prompt across the whole corpus. Mirrors
        each transcript's module path. `only` filters by case-insensitive substring.
        """
        transcripts = sorted(self.transcripts_dir.rglob("*.md"))
        processed = 0
        for tpath in transcripts:
            rel = tpath.relative_to(self.transcripts_dir)
            module = rel.parent.as_posix() if rel.parent != Path(".") else None
            title = clean_lesson_title(tpath.stem)
            if only and only.lower() not in title.lower():
                continue
            spath = self._sub(self.summaries_dir, module) / f"{title}.md"
            if spath.exists() and not overwrite:
                self.skipped.append(f"{module or ''}/{title}")
                continue
            if processed > 0 and wait_seconds:
                await asyncio.sleep(wait_seconds)
            processed += 1
            try:
                transcript = tpath.read_text(encoding="utf-8")
                summary = await self.summarizer(title, transcript)
                _write(spath, f"# Resumo — {title}\n\n{summary}\n")
                self.results.append(
                    VideoResult(
                        name=title,
                        video_path=tpath,
                        transcript_path=tpath,
                        summary_path=spath,
                        transcript_chars=len(transcript),
                        summary_chars=len(summary),
                        module=module,
                    )
                )
            except Exception as e:
                logger.error("FAILED resummarize %s/%s: %s", module, title, e)
                self.failures.append({"module": module, "title": title, "error": str(e)})
        self._write_manifest()
        return self.results

    # ── housekeeping ────────────────────────────────────────────────
    def _reorganize_existing(self, title: str, module_name: str) -> None:
        """Move a flat (un-organized) transcript/summary into its module folder.

        Lets earlier runs (e.g. the pilot, written to data/transcripts/<title>.md)
        be recognized as done once we reach their module — no re-transcription.
        """
        for base in (self.transcripts_dir, self.summaries_dir):
            flat = base / f"{title}.md"
            organized = base / module_name / f"{title}.md"
            if flat.exists() and not organized.exists():
                organized.parent.mkdir(parents=True, exist_ok=True)
                flat.rename(organized)
                logger.info("reorganized %s → %s/", flat.name, module_name)

    # ── persistence ─────────────────────────────────────────────────
    def _write_manifest(self) -> None:
        manifest = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "videos": [
                {
                    "name": r.name,
                    "module": r.module,
                    "video": str(r.video_path),
                    "transcript": str(r.transcript_path),
                    "summary": str(r.summary_path),
                    "transcript_chars": r.transcript_chars,
                    "summary_chars": r.summary_chars,
                }
                for r in self.results
            ],
            "skipped": self.skipped,
            "failures": self.failures,
        }
        path = self.data_dir / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        logger.info(
            "manifest → %s (%d done, %d skipped, %d failed)",
            path, len(self.results), len(self.skipped), len(self.failures),
        )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_fake_pipeline() -> ExtractionPipeline:
    """A fully in-memory pipeline: no OpenAI key, no ffmpeg, no network.

    Shared by the CLI (`run --fake`) and the runs API (`POST /api/runs {fake:true}`)
    so the demo path has a single source of truth.
    """
    from app.integrations.google_drive import FakeDriveDownloader

    settings = get_settings()
    drive = FakeDriveDownloader()
    drive.add_fake_file(
        "fake-aula-01",
        "aula-01-introducao.mp4",
        b"FAKE_VIDEO_BYTES",
        mime_type="video/mp4",
    )

    def fake_extract(video: Path, out: Path) -> Path:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(video, out)
        return out

    async def fake_transcribe(audio: Path, chunk_dir: Path) -> str:
        return (
            "Bem-vindos à primeira aula do curso de social media. "
            "Hoje vamos falar sobre planejamento de conteúdo e a regra dos "
            "três pilares: educar, engajar e converter."
        )

    async def fake_summarize(title: str, transcript: str) -> str:
        return (
            "## Resumo\nAula introdutória sobre planejamento de conteúdo.\n\n"
            "## Pontos-chave\n- Três pilares: educar, engajar, converter.\n\n"
            "## Metodologia / passo a passo\n- Planejar conteúdo pelos pilares.\n"
        )

    return ExtractionPipeline(
        downloader=drive,
        audio_extractor=fake_extract,
        transcriber=fake_transcribe,
        summarizer=fake_summarize,
        data_dir=settings.data_path,
    )


def build_default_pipeline(*, use_fake_drive: bool = False) -> ExtractionPipeline:
    """Wire the real adapters (Drive v3 + ffmpeg + OpenAI)."""
    settings = get_settings()

    async def _transcriber(audio: Path, chunk_dir: Path) -> str:
        return await transcribe_file(audio, chunk_dir=chunk_dir)

    return ExtractionPipeline(
        downloader=make_drive_downloader(use_fake=use_fake_drive),
        audio_extractor=extract_audio,
        transcriber=_transcriber,
        summarizer=summarize_transcript,
        data_dir=settings.data_path,
    )


__all__ = [
    "ExtractionPipeline",
    "VideoResult",
    "build_default_pipeline",
    "build_fake_pipeline",
    "is_video",
]
