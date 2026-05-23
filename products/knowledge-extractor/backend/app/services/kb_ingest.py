"""Knowledge-base ingestion pipeline.

Reads methodology markdown files from ``data_dir/methodology/``, chunks them
by heading/section, guards each chunk against the anonymization policy, embeds
clean chunks, and upserts them into a VectorStore.

Entry point: ``ingest_methodology(data_dir, *, store, embed_fn)``

Design notes
------------
- INCLUDE:  module files (e.g. "1 PLANO PARA CRESCER.md"), ESTRUTURAS-DE-POST.md,
            REFERENCIAS.md, ESQUEMA-BASE-DE-CONHECIMENTO.md.
- EXCLUDE:  _FRONT.md, _BACK.md  (assembly wrappers with no clean content).
- NEVER:    read transcripts (``data_dir/transcripts/``).
- Anonymization guard: chunks flagged by ``scan_text`` are SKIPPED + logged;
  clean chunks are embedded + upserted.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Coroutine, Any

from app.integrations.vectors.protocol import VectorStore
from app.integrations.vectors.types import KBChunk
from app.services.anonymization import scan_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

EmbedFn = Callable[[str], Coroutine[Any, Any, list[float]]]

@dataclass
class IngestResult:
    """Summary returned by :func:`ingest_methodology`."""
    documents: int = 0
    chunks_ingested: int = 0
    chunks_skipped: int = 0
    skipped_warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# File selection
# ---------------------------------------------------------------------------

# Names that start with "_" are assembly wrappers — no clean methodology content.
_EXCLUDED_PREFIXES = ("_",)


def _is_included(path: Path) -> bool:
    """Return True if *path* should be ingested."""
    name = path.name
    if any(name.startswith(prefix) for prefix in _EXCLUDED_PREFIXES):
        return False
    if path.suffix.lower() != ".md":
        return False
    return True


def _collect_methodology_files(methodology_dir: Path) -> list[Path]:
    """Return sorted list of methodology .md files to ingest."""
    if not methodology_dir.is_dir():
        raise FileNotFoundError(
            f"Methodology directory not found: {methodology_dir}"
        )
    files = sorted(
        p for p in methodology_dir.iterdir()
        if p.is_file() and _is_included(p)
    )
    return files


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

# Markdown heading — level 1, 2, or 3 (deeper headings stay within section).
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def _module_from_path(path: Path, methodology_dir: Path) -> str:
    """Derive a module slug from the file's name (relative to methodology_dir)."""
    stem = path.stem
    # Normalise: lowercase, spaces and special chars → hyphens.
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug


def _document_id_from_path(path: Path, methodology_dir: Path) -> str:
    """Stable document id = relative path from methodology_dir."""
    return str(path.relative_to(methodology_dir))


def _chunk_markdown(text: str) -> list[str]:
    """Split *text* into sections by top-3 headings.

    Each section includes the heading that opens it.  A leading preamble
    (text before the first heading) is kept as its own chunk if non-empty.

    Strategy:
      - Find all heading positions.
      - Each chunk = from the start of a heading to the start of the next
        heading (or end-of-file).
      - Chunks that are only whitespace / empty are dropped.
    """
    chunks: list[str] = []

    matches = list(_HEADING_RE.finditer(text))

    if not matches:
        # No headings at all — treat the entire file as one chunk.
        stripped = text.strip()
        if stripped:
            chunks.append(stripped)
        return chunks

    # Leading preamble (before first heading)
    preamble = text[: matches[0].start()].strip()
    if preamble:
        chunks.append(preamble)

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end].strip()
        if section:
            chunks.append(section)

    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def ingest_methodology(
    data_dir: Path | str,
    *,
    store: VectorStore,
    embed_fn: EmbedFn,
) -> dict[str, Any]:
    """Ingest all methodology files into *store*.

    Parameters
    ----------
    data_dir:
        Root data directory (``Settings.data_path``).  Methodology files are
        read from ``data_dir/methodology/``.
    store:
        A :class:`~app.integrations.vectors.protocol.VectorStore` (real or fake).
    embed_fn:
        Async callable ``(text: str) -> list[float]``.  Defaults to
        :func:`~app.integrations.llm.embeddings.generate_embedding` when
        called from the CLI.  Injected in tests.

    Returns
    -------
    dict
        ``{"documents": int, "chunks_ingested": int, "chunks_skipped": int}``
    """
    data_dir = Path(data_dir)
    methodology_dir = data_dir / "methodology"

    files = _collect_methodology_files(methodology_dir)
    logger.info("Found %d methodology files to ingest", len(files))

    result = IngestResult()

    for path in files:
        doc_id = _document_id_from_path(path, methodology_dir)
        module = _module_from_path(path, methodology_dir)

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read %s: %s — skipping", path, exc)
            continue

        raw_chunks = _chunk_markdown(text)
        if not raw_chunks:
            logger.warning("No chunks extracted from %s — skipping", path)
            continue

        result.documents += 1

        clean_pairs: list[tuple[KBChunk, list[float]]] = []

        for idx, chunk_text in enumerate(raw_chunks):
            chunk_id = f"{doc_id}-{idx}"

            # ── Anonymization guard ────────────────────────────────────────
            findings = scan_text(chunk_text)
            if findings:
                summary = "; ".join(
                    f"{f.kind}:{f.match!r} (line {f.line})" for f in findings[:3]
                )
                warning = (
                    f"SKIP chunk {chunk_id!r}: {len(findings)} anonymization "
                    f"finding(s) — {summary}"
                )
                logger.warning(warning)
                result.skipped_warnings.append(warning)
                result.chunks_skipped += 1
                continue

            # ── Embed ──────────────────────────────────────────────────────
            embedding = await embed_fn(chunk_text)

            kb_chunk = KBChunk(
                id=chunk_id,
                document_id=doc_id,
                content=chunk_text,
                module=module,
                confidence=1.0,
            )
            clean_pairs.append((kb_chunk, embedding))

        if clean_pairs:
            written = await store.upsert(clean_pairs)
            result.chunks_ingested += written
            logger.info(
                "Ingested %d chunk(s) from %s (skipped %d)",
                written,
                doc_id,
                len(raw_chunks) - len(clean_pairs),
            )

    logger.info(
        "Ingest complete — documents=%d, chunks_ingested=%d, chunks_skipped=%d",
        result.documents,
        result.chunks_ingested,
        result.chunks_skipped,
    )
    return {
        "documents": result.documents,
        "chunks_ingested": result.chunks_ingested,
        "chunks_skipped": result.chunks_skipped,
    }


__all__ = ["ingest_methodology"]
