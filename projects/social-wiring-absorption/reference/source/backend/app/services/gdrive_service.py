"""Google Drive download — link → local file path.

The upload pipeline calls :func:`download_from_drive` with a Drive URL
and gets back a local file path that ``youtube_service.upload_video``
consumes. Two download paths exist because Drive's behavior differs by
file size + sharing config:

1. **Public + small (<100MB)** — direct download via httpx with the
   ``uc?export=download&id={id}`` URL. Fast, no extra dependency.
2. **Large + virus-warning intercept** — Drive injects a confirmation
   page when downloading anything that triggers its scan. ``gdown``
   follows that flow transparently; we fall back to it on any non-binary
   response from the direct path.

Files land under ``tmp/uploads/``; callers are responsible for unlinking
once the YouTube upload completes (or fails). The pipeline does that
cleanup in a try/finally to avoid disk leaks across days of use.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlparse

import httpx

logger = logging.getLogger(__name__)

# YouTube's per-file upload ceiling is 256 GB but a more practical cap
# protects the host disk + bandwidth budget. 8 GB covers any reasonable
# vlog / tutorial / talk; bigger files can be uploaded directly via
# YouTube Studio.
DEFAULT_MAX_BYTES: int = 8 * 1024 * 1024 * 1024  # 8 GB

# Accepted YouTube container formats. Drive may serve files as
# ``application/octet-stream`` (no content sniff at upload time), so an
# unknown content-type is allowed past validation but the file extension
# is still checked against this set.
ACCEPTED_VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpeg", ".mpg", ".wmv",
}


class GoogleDriveError(Exception):
    """All Drive-side failures route through this — routers translate to
    HTTP 4xx/5xx based on whether the cause was caller (bad URL, oversize)
    or transport (network, server)."""


class InvalidDriveURL(GoogleDriveError):
    """URL doesn't match any of the recognised Drive-share URL shapes."""


class DriveFileTooLarge(GoogleDriveError):
    """File exceeds the configured per-upload byte ceiling."""


class UnsupportedVideoFormat(GoogleDriveError):
    """File extension isn't on the YouTube-accepted list."""


@dataclass
class DownloadResult:
    """What :func:`download_from_drive` returns to the upload pipeline."""

    local_path: Path
    file_name: str
    file_size_bytes: int


# ─── URL parsing (pure, network-free) ──────────────────────────────────
_FILE_ID_PATTERNS: tuple[re.Pattern[str], ...] = (
    # /file/d/{id}/...   — the canonical share-link shape
    re.compile(r"/file/d/([a-zA-Z0-9_-]{20,})"),
    # /document/d/{id}/  — Docs export shape (we don't support but parse for clarity)
    re.compile(r"/document/d/([a-zA-Z0-9_-]{20,})"),
    # /open?id={id}      — older share shape
    # /uc?id={id}        — direct-download shape
    # Both handled by query-string parsing below.
)


def parse_file_id(url: str) -> str:
    """Extract the Drive file ID from any of the recognised URL shapes.

    Raises :class:`InvalidDriveURL` for unrecognised inputs — callers
    should validate the host BEFORE calling this (Pydantic schema does so).

    Pure function: no I/O. Tested in isolation."""
    if not url:
        raise InvalidDriveURL("empty URL")

    parsed = urlparse(url)
    # Path-based shapes first — they're the most specific.
    for pattern in _FILE_ID_PATTERNS:
        match = pattern.search(parsed.path)
        if match:
            return match.group(1)

    # Query-string fallback (?id={id} or &id={id}).
    qs = parse_qs(parsed.query)
    if "id" in qs and qs["id"]:
        candidate = qs["id"][0]
        if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", candidate):
            return candidate

    raise InvalidDriveURL(
        f"could not extract file ID from URL: {url!r}. "
        "Expected a Drive share link like https://drive.google.com/file/d/<ID>/view."
    )


def validate_video_filename(name: str) -> None:
    """Reject filenames with unsupported extensions before download.

    Filename comes from Drive's content-disposition header (preferred) or
    the URL path as a fallback; either way it carries the original
    extension."""
    suffix = Path(name).suffix.lower()
    if not suffix:
        raise UnsupportedVideoFormat(
            f"file {name!r} has no extension; cannot determine format. "
            "Rename on Drive (e.g. .mp4) and retry."
        )
    if suffix not in ACCEPTED_VIDEO_EXTENSIONS:
        raise UnsupportedVideoFormat(
            f"file extension {suffix!r} is not a YouTube-accepted video "
            f"format. Accepted: {sorted(ACCEPTED_VIDEO_EXTENSIONS)}."
        )


# ─── Download (network I/O) ────────────────────────────────────────────
def _build_direct_download_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def _filename_from_response(response: httpx.Response, fallback: str) -> str:
    """Parse the ``Content-Disposition`` header for the attachment filename.

    Drive returns headers like ``Content-Disposition: attachment;
    filename="my video.mp4"`` — we honour that to keep the original
    extension. Falls back to ``fallback`` (typically the file_id) when
    the header is absent or malformed."""
    disposition = response.headers.get("content-disposition", "")
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition)
    if match:
        return match.group(1).strip()
    return fallback


def _is_html(response: httpx.Response) -> bool:
    """Drive returns HTML when the file triggers a virus-scan confirmation
    or requires login. Detecting it is the trigger for the gdown fallback."""
    ctype = response.headers.get("content-type", "").lower()
    return "text/html" in ctype


def download_from_drive(
    *,
    drive_url: str,
    target_dir: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
    httpx_client: httpx.Client | None = None,
) -> DownloadResult:
    """Download a Drive file to ``target_dir``. Returns the local path +
    filename + size.

    The ``httpx_client`` parameter is a test seam — production callers
    don't pass it and a fresh client is built per call (request-scoped,
    short-lived). Tests pass a client wired to a transport mock so no
    real network is touched."""
    file_id = parse_file_id(drive_url)
    target_dir.mkdir(parents=True, exist_ok=True)

    direct_url = _build_direct_download_url(file_id)
    owns_client = httpx_client is None
    client = httpx_client or httpx.Client(timeout=httpx.Timeout(60.0, read=300.0))

    try:
        with client.stream("GET", direct_url, follow_redirects=True) as response:
            response.raise_for_status()

            if _is_html(response):
                # Virus-scan / consent page — fall back to gdown which
                # handles the multi-hop confirmation flow.
                logger.info(
                    "drive direct download returned HTML for file_id=%s; "
                    "falling back to gdown",
                    file_id,
                )
                return _download_via_gdown(
                    file_id=file_id,
                    target_dir=target_dir,
                    max_bytes=max_bytes,
                )

            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > max_bytes:
                raise DriveFileTooLarge(
                    f"Drive file is {int(content_length):,} bytes; ceiling is "
                    f"{max_bytes:,} bytes. Trim or upload directly to YouTube Studio."
                )

            file_name = _filename_from_response(response, fallback=f"{file_id}.mp4")
            validate_video_filename(file_name)
            local_path = target_dir / file_name

            written = _stream_to_file(response.iter_bytes(), local_path, max_bytes)

            return DownloadResult(
                local_path=local_path,
                file_name=file_name,
                file_size_bytes=written,
            )
    except httpx.HTTPError as exc:
        raise GoogleDriveError(f"Drive download failed: {exc}") from exc
    finally:
        if owns_client:
            client.close()


def _stream_to_file(
    chunks: Iterable[bytes],
    path: Path,
    max_bytes: int,
) -> int:
    """Write a byte stream to disk + enforce the size cap mid-stream.

    Streaming-with-cap is critical: a malicious / malformed Drive
    response could omit Content-Length but still send GBs. The mid-stream
    check unlinks the partial file rather than letting it consume disk."""
    written = 0
    with open(path, "wb") as fh:
        for chunk in chunks:
            if not chunk:
                continue
            fh.write(chunk)
            written += len(chunk)
            if written > max_bytes:
                fh.close()
                path.unlink(missing_ok=True)
                raise DriveFileTooLarge(
                    f"Drive file exceeded {max_bytes:,}-byte ceiling mid-download "
                    f"(after {written:,} bytes). Aborted + cleaned up."
                )
    return written


def _download_via_gdown(
    *,
    file_id: str,
    target_dir: Path,
    max_bytes: int,
) -> DownloadResult:
    """Fallback path for files that need the consent-page hop.

    ``gdown`` is imported lazily so the test suite (which only exercises
    the direct path + URL parsing) doesn't need to install it for the
    happy-path tests to pass."""
    try:
        import gdown
    except ImportError as exc:
        raise GoogleDriveError(
            "Drive returned a consent page (large or shared file) but "
            "gdown isn't installed. `pip install gdown` and retry."
        ) from exc

    output_template = str(target_dir / f"{file_id}.tmp")
    try:
        result_path_str = gdown.download(
            id=file_id,
            output=output_template,
            quiet=True,
            fuzzy=True,
        )
    except Exception as exc:
        raise GoogleDriveError(f"gdown fallback failed: {exc}") from exc

    if not result_path_str:
        raise GoogleDriveError(
            f"gdown returned no path for file_id={file_id} — usually a "
            "permissions issue (not publicly shared)."
        )

    result_path = Path(result_path_str)
    if not result_path.exists():
        raise GoogleDriveError(
            f"gdown reported success but file not present at {result_path}."
        )

    size = result_path.stat().st_size
    if size > max_bytes:
        result_path.unlink(missing_ok=True)
        raise DriveFileTooLarge(
            f"gdown-downloaded file is {size:,} bytes; ceiling is "
            f"{max_bytes:,} bytes. Aborted + cleaned up."
        )

    file_name = result_path.name
    validate_video_filename(file_name)

    return DownloadResult(
        local_path=result_path,
        file_name=file_name,
        file_size_bytes=size,
    )


def cleanup(path: Path) -> None:
    """Best-effort unlink for the upload pipeline's finally block.

    Logs but never raises — a leaked tmp file is preferable to a 500 on
    the upload endpoint when the OS denies the unlink for some transient
    reason (file locked by AV scanner, etc.)."""
    try:
        if path.exists():
            os.unlink(path)
    except OSError as exc:
        logger.warning("failed to unlink upload tmp file %s: %s", path, exc)


# ─── Folder support (Phase 5) ─────────────────────────────────────────

_FOLDER_ID_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"/(?:drive/)?folders/([a-zA-Z0-9_-]{20,})"),
)


def is_folder_url(url: str) -> bool:
    """Return True if the URL looks like a Drive folder (vs single file)."""
    if not url:
        return False
    return "/folders/" in url


def parse_folder_id(url: str) -> str:
    """Extract the folder ID from a Drive folder URL.

    Raises :class:`InvalidDriveURL` if no folder ID is found."""
    if not url:
        raise InvalidDriveURL("empty URL")
    parsed = urlparse(url)
    for pattern in _FOLDER_ID_PATTERNS:
        match = pattern.search(parsed.path)
        if match:
            return match.group(1)
    raise InvalidDriveURL(
        f"could not extract folder ID from URL: {url!r}. "
        "Expected a Drive folder link like "
        "https://drive.google.com/drive/folders/<ID>"
    )


# ─── Video format classification ──────────────────────────────────────

# Filename convention patterns (case-insensitive substring match)
_YT_NAME_HINTS = {"yt", "youtube", "16x9", "landscape", "horizontal"}
_REELS_NAME_HINTS = {"reel", "reels", "9x16", "vertical", "portrait", "shorts"}


def classify_video_format(file_path: Path) -> str:
    """Classify a video file as ``"youtube"``, ``"reels"``, or ``"unknown"``.

    Priority:
    1. Filename/parent folder name convention (substring match)
    2. Aspect ratio via ffprobe (16:9+ → youtube, 9:16- → reels)
    3. "unknown" fallback
    """
    name_lower = file_path.name.lower()
    parent_lower = file_path.parent.name.lower()
    search_text = f"{name_lower} {parent_lower}"

    # Check filename/folder name conventions
    for hint in _YT_NAME_HINTS:
        if hint in search_text:
            logger.debug("classified %s as youtube (name hint: %s)", file_path.name, hint)
            return "youtube"
    for hint in _REELS_NAME_HINTS:
        if hint in search_text:
            logger.debug("classified %s as reels (name hint: %s)", file_path.name, hint)
            return "reels"

    # Fall back to aspect ratio via ffprobe
    ratio = _get_aspect_ratio(file_path)
    if ratio is not None:
        if ratio >= 1.5:
            logger.debug(
                "classified %s as youtube (aspect ratio: %.2f)", file_path.name, ratio
            )
            return "youtube"
        if ratio <= 0.75:
            logger.debug(
                "classified %s as reels (aspect ratio: %.2f)", file_path.name, ratio
            )
            return "reels"

    logger.debug("classified %s as unknown", file_path.name)
    return "unknown"


def _get_aspect_ratio(file_path: Path) -> float | None:
    """Probe the video's width:height ratio via ffprobe.

    Returns None when ffprobe isn't available or the file isn't a
    valid video — callers should fall back to "unknown" classification.
    """
    import subprocess
    import json as _json

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.debug("ffprobe failed for %s: %s", file_path.name, result.stderr[:200])
            return None

        data = _json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            return None

        width = int(streams[0].get("width", 0))
        height = int(streams[0].get("height", 0))
        if width <= 0 or height <= 0:
            return None

        return width / height
    except FileNotFoundError:
        logger.debug("ffprobe not found — aspect ratio classification unavailable")
        return None
    except Exception as exc:
        logger.debug("ffprobe error for %s: %s", file_path.name, exc)
        return None


# ─── Folder download + pick ───────────────────────────────────────────

def download_folder_contents(
    *,
    folder_url: str,
    target_dir: Path,
) -> list[Path]:
    """Download all files from a Drive folder to target_dir.

    Uses gdown.download_folder() which handles public/shared folders
    without needing a service account. Returns a list of local file paths.
    """
    try:
        import gdown
    except ImportError as exc:
        raise GoogleDriveError(
            "gdown isn't installed. `pip install gdown` and retry."
        ) from exc

    folder_id = parse_folder_id(folder_url)
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        downloaded = gdown.download_folder(
            id=folder_id,
            output=str(target_dir),
            quiet=True,
        )
    except Exception as exc:
        raise GoogleDriveError(f"folder download failed: {exc}") from exc

    if not downloaded:
        raise GoogleDriveError(
            f"gdown returned no files for folder_id={folder_id} — "
            "usually a permissions issue (not publicly shared)."
        )

    # Collect all video files from the downloaded tree
    video_files = []
    for path_str in downloaded:
        path = Path(path_str)
        if path.exists() and path.suffix.lower() in ACCEPTED_VIDEO_EXTENSIONS:
            video_files.append(path)

    return video_files


@dataclass
class FolderPickResult:
    """Result of pick_youtube_video — the chosen file + classification."""

    local_path: Path
    file_name: str
    file_size_bytes: int
    format: str  # "youtube", "reels", "unknown"
    all_files: list[str]  # all video filenames found in the folder


@dataclass
class VideoCandidate:
    """One candidate from ``list_youtube_candidates``.

    ``duration_seconds`` is best-effort (depends on ffprobe); ``None``
    when the probe fails. The intake's choice prompt formats it as
    mm:ss when available.
    """

    local_path: Path
    file_name: str
    file_size_bytes: int
    format: str  # "youtube" / "reels" / "unknown"
    duration_seconds: float | None = None


@dataclass
class OversizedFile:
    """A file that was dropped from candidates because it exceeded
    ``max_bytes``. Returned so the intake can surface a "⚠️ N arquivos
    acima do limite foram ignorados" warning instead of silently
    omitting them."""

    file_name: str
    file_size_bytes: int


@dataclass
class CandidateListResult:
    """Result of ``list_youtube_candidates`` — both the usable
    candidates and the files that got dropped (oversized) so the
    consumer can choose what to surface to the user."""

    candidates: list[VideoCandidate]
    oversized: list[OversizedFile]


def list_youtube_candidates(
    *,
    folder_url: str,
    target_dir: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> CandidateListResult:
    """Return every YT-format video in a Drive folder, no silent pick.

    Mirrors ``pick_youtube_video`` for the download + classify steps,
    but does NOT pick the first match — returns the full list so the
    intake state machine can present a menu when N≥2.

    Behavior:

      - Downloads all files in the folder.
      - Classifies each.
      - Filters out reels (vertical-format).
      - Returns an empty candidates list when no horizontal videos
        were found.
      - Drops candidates that exceed ``max_bytes`` (cleans up their
        local file) — they couldn't be uploaded anyway. Dropped files
        appear in ``result.oversized`` so the intake can warn the user.

    Caller is responsible for cleanup of the local files (the candidates
    are kept on disk until the intake state machine resolves the user's
    choice, then ``cleanup(candidate.local_path)`` is called per
    discarded entry).
    """
    video_files = download_folder_contents(
        folder_url=folder_url,
        target_dir=target_dir,
    )
    if not video_files:
        raise GoogleDriveError(
            "No video files found in the Drive folder. "
            f"Accepted formats: {sorted(ACCEPTED_VIDEO_EXTENSIONS)}"
        )

    candidates: list[VideoCandidate] = []
    oversized: list[OversizedFile] = []
    for vf in video_files:
        fmt = classify_video_format(vf)
        size = vf.stat().st_size
        if fmt == "reels":
            # Reels are wrong-aspect for YouTube long-form; drop early
            # so the menu doesn't list them.
            cleanup(vf)
            continue
        if size > max_bytes:
            logger.info("dropping oversized candidate %s (%d bytes)", vf.name, size)
            oversized.append(OversizedFile(file_name=vf.name, file_size_bytes=size))
            cleanup(vf)
            continue
        duration = _get_duration_seconds(vf)
        candidates.append(
            VideoCandidate(
                local_path=vf,
                file_name=vf.name,
                file_size_bytes=size,
                format=fmt,
                duration_seconds=duration,
            )
        )

    return CandidateListResult(candidates=candidates, oversized=oversized)


def _get_duration_seconds(file_path: Path) -> float | None:
    """Probe video duration via ffprobe. Returns None on any failure.

    Used by the multi-video choice menu so the operator sees "4:32" /
    "1:54" next to each candidate. Best-effort — a missing duration
    just renders as an empty field, no error.
    """
    import subprocess
    import json as _json

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        data = _json.loads(result.stdout)
        duration_str = data.get("format", {}).get("duration")
        return float(duration_str) if duration_str else None
    except Exception:
        return None


def pick_youtube_video(
    *,
    folder_url: str,
    target_dir: Path,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> FolderPickResult:
    """Download a Drive folder, classify each video, return the YT one.

    Strategy:
    1. Download all files from the folder
    2. Classify each video file
    3. Return the first "youtube" match
    4. If no "youtube" found, return the first "unknown" (single-file fallback)
    5. Clean up non-selected files

    Raises :class:`GoogleDriveError` if no suitable video is found.
    """
    video_files = download_folder_contents(
        folder_url=folder_url,
        target_dir=target_dir,
    )

    if not video_files:
        raise GoogleDriveError(
            "No video files found in the Drive folder. "
            f"Accepted formats: {sorted(ACCEPTED_VIDEO_EXTENSIONS)}"
        )

    all_names = [f.name for f in video_files]

    # Classify each file
    classifications: list[tuple[Path, str]] = []
    for vf in video_files:
        fmt = classify_video_format(vf)
        classifications.append((vf, fmt))

    # Pick the best match
    youtube_files = [(p, f) for p, f in classifications if f == "youtube"]
    unknown_files = [(p, f) for p, f in classifications if f == "unknown"]

    chosen_path: Path | None = None
    chosen_format: str = "unknown"

    if youtube_files:
        chosen_path = youtube_files[0][0]
        chosen_format = "youtube"
    elif len(video_files) == 1:
        # Single file fallback — use it regardless of classification
        chosen_path = video_files[0]
        chosen_format = classifications[0][1]
    elif unknown_files:
        chosen_path = unknown_files[0][0]
        chosen_format = "unknown"

    if chosen_path is None:
        # All files are REELS — no YouTube video found
        cleanup_list = [f.name for f in video_files]
        for vf in video_files:
            cleanup(vf)
        raise GoogleDriveError(
            f"No YouTube-format video (16:9) found in folder. "
            f"All files appear to be REELS format. "
            f"Files found: {cleanup_list}"
        )

    # Size check
    size = chosen_path.stat().st_size
    if size > max_bytes:
        cleanup(chosen_path)
        raise DriveFileTooLarge(
            f"Selected video is {size:,} bytes; ceiling is "
            f"{max_bytes:,} bytes."
        )

    # Clean up non-selected files
    for vf in video_files:
        if vf != chosen_path:
            cleanup(vf)

    return FolderPickResult(
        local_path=chosen_path,
        file_name=chosen_path.name,
        file_size_bytes=size,
        format=chosen_format,
        all_files=all_names,
    )

