"""`noctus.dev.count_tokens` — count tokens for a file, directory, or glob.

Used by:
- Methodology / context-budget work — measure per-turn token cost reduction
  precisely (originating project `methodology-extraction` closed 2026-05-02
  + folder deleted; see git history).
- `projects/project-history-ledger/` (deferred) — token-count column for
  every closed/deleted project entry.

**Tokenizer cascade.** The function tries tokenizers in order and falls
back; the result reports which one ran:

1. `tiktoken` (cl100k_base / o200k_base) — offline, ~5-10% off Claude's
   BPE but practically close. Optional dependency; installed if
   `pip install tiktoken` ran. *Recommended default for honest numbers.*
2. **char/word approximation** — `tokens ≈ chars / 4` (English-markdown
   rule-of-thumb). Always available, never wrong by more than ~25%.

The tool is intentionally **offline-only**. Anthropic's
`messages.count_tokens` API is the most accurate but requires a
network call + API key + costs per invocation; an MCP tool that runs
every project close shouldn't hit a network. If precision matters more
than offline ergonomics for a specific use-case, call the API directly.

**Inputs.**
- `path: str | Path | None` — file, directory, or glob pattern
  - file: count just that file
  - directory: walk recursively, include `*.md` files by default
    (configurable via `extensions=`)
  - glob (contains `*` or `?`): expand via `Path.glob`
- `text: str | None` — count an inline string (skip filesystem)
- `extensions: tuple[str, ...]` — file extensions to include when
  walking a directory. Default `(".md",)`. Use `("*",)` to include all.

**Returns.** `TokenCountResult` with `total` summary and `per_file`
breakdown. `tokenizer_used` is set on every result so callers can
record which precision applied.

**Anti-pattern guard.** Don't confuse `tokens` with `words` or `chars`.
Always read `tokenizer_used` if you're recording the result anywhere
(e.g. `project-history-ledger`); two ledger rows with the same
`tokens` but different `tokenizer_used` are NOT comparable.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

from settings import REPO_ROOT  # noqa: E402  (path constant)

# Shared tokenizer helper — N=2 absorption with `noctus.dev.history_record`
# (`project-history-ledger` Phase 1, 2026-05-10). The encoder + fallback
# cascade live in `mcp/noctusai/tools/_tokens.py`; this module wraps with
# the per-file aggregation logic.
from tools._tokens import (  # noqa: E402
    DEFAULT_TIKTOKEN_ENCODING,
    get_default_encoder as _try_tiktoken_encoding,
    count_tokens_in_text as _shared_count_tokens_in_text,
)

DEFAULT_EXTENSIONS: tuple[str, ...] = (".md",)

# Skip the same vendored / generated dirs the rest of the toolkit skips.
SKIP_DIRS = {
    "node_modules", ".venv", "venv", "dist", "build",
    "__pycache__", ".git", ".next", ".turbo",
}


@dataclass
class FileTokenCount:
    """Per-file count. `tokenizer` is the one that ran for THIS file."""
    path: str
    tokens: int
    chars: int
    words: int
    lines: int
    tokenizer: str

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "tokens": self.tokens,
            "chars": self.chars,
            "words": self.words,
            "lines": self.lines,
            "tokenizer": self.tokenizer,
        }


@dataclass
class TokenCountResult:
    """Aggregate of one or more file counts plus inline text."""
    total_tokens: int
    total_chars: int
    total_words: int
    total_lines: int
    file_count: int
    tokenizer_used: str
    per_file: list[FileTokenCount] = field(default_factory=list)
    inline_text_tokens: int = 0

    def to_dict(self) -> dict:
        return {
            "total_tokens": self.total_tokens,
            "total_chars": self.total_chars,
            "total_words": self.total_words,
            "total_lines": self.total_lines,
            "file_count": self.file_count,
            "tokenizer_used": self.tokenizer_used,
            "inline_text_tokens": self.inline_text_tokens,
            "per_file": [f.to_dict() for f in self.per_file],
        }


# ---------------------------------------------------------------------------
# Tokenizer cascade — delegates to the shared helper at
# `mcp/noctusai/tools/_tokens.py`. Re-exported as module-level names so
# existing consumers / tests that import `count_tokens_in_text` keep
# working without rewiring.
# ---------------------------------------------------------------------------


def count_tokens_in_text(text: str, encoder=None) -> tuple[int, str]:
    """Count tokens in `text`. Returns `(tokens, tokenizer_used)`.

    `encoder` may be a pre-loaded tiktoken Encoding (for batch reuse).
    Delegates to the shared `tools._tokens.count_tokens_in_text` helper —
    the encoder + fallback cascade live in one place across MCP tools.
    """
    return _shared_count_tokens_in_text(text, encoder=encoder)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _resolve_paths(
    path: Optional[str | Path],
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
) -> list[Path]:
    """Expand `path` into a concrete list of files to count."""
    if path is None:
        return []
    p = Path(path)
    # Glob form
    if any(c in str(path) for c in "*?["):
        # Glob may be relative to cwd or repo root; try both.
        matches = list(Path.cwd().glob(str(path)))
        if not matches:
            matches = list(REPO_ROOT.glob(str(path)))
        return [m for m in sorted(matches) if m.is_file()]
    if not p.exists():
        # Could be a relative path from repo root.
        candidate = REPO_ROOT / p
        if candidate.exists():
            p = candidate
        else:
            return []
    if p.is_file():
        return [p]
    if p.is_dir():
        out: list[Path] = []
        for child in sorted(p.rglob("*")):
            if not child.is_file():
                continue
            if any(part in SKIP_DIRS for part in child.parts):
                continue
            if extensions == ("*",) or child.suffix in extensions:
                out.append(child)
        return out
    return []


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def count_tokens(
    path: Optional[str | Path] = None,
    *,
    text: Optional[str] = None,
    extensions: tuple[str, ...] = DEFAULT_EXTENSIONS,
) -> TokenCountResult:
    """Count tokens for a file/dir/glob `path`, an inline `text`, or both.

    Either `path` or `text` (or both) must be provided.
    """
    if path is None and text is None:
        raise ValueError("count_tokens requires `path`, `text`, or both")

    encoder = _try_tiktoken_encoding()
    tokenizer_label = f"tiktoken-{encoder.name}" if encoder else "approximate-chars-per-4"

    per_file: list[FileTokenCount] = []
    total_tokens = 0
    total_chars = 0
    total_words = 0
    total_lines = 0

    files = _resolve_paths(path, extensions=extensions)
    for f in files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("count_tokens: skip %s (%s)", f, e)
            continue
        chars = len(content)
        words = len(content.split())
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        tokens, used = count_tokens_in_text(content, encoder=encoder)
        per_file.append(FileTokenCount(
            path=str(f.relative_to(REPO_ROOT)) if str(f).startswith(str(REPO_ROOT)) else str(f),
            tokens=tokens,
            chars=chars,
            words=words,
            lines=lines,
            tokenizer=used,
        ))
        total_tokens += tokens
        total_chars += chars
        total_words += words
        total_lines += lines

    inline_tokens = 0
    if text is not None:
        chars = len(text)
        words = len(text.split())
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        tokens, used = count_tokens_in_text(text, encoder=encoder)
        inline_tokens = tokens
        total_tokens += tokens
        total_chars += chars
        total_words += words
        total_lines += lines

    return TokenCountResult(
        total_tokens=total_tokens,
        total_chars=total_chars,
        total_words=total_words,
        total_lines=total_lines,
        file_count=len(per_file),
        tokenizer_used=tokenizer_label,
        per_file=per_file,
        inline_text_tokens=inline_tokens,
    )


def register(server) -> None:
    @server.tool(
        name="noctus.dev.count_tokens",
        description=(
            "Count tokens for a file, directory, or glob (offline). Tokenizer cascade: "
            "tiktoken (if installed in the venv — ~5-10% off Claude) → chars/4 "
            "approximation. Returns total + per-file breakdown + the tokenizer that ran. "
            "Used to measure per-turn auto-load cost (CLAUDE.md, MEMORY.md) precisely "
            "and to stamp token counts onto closed-project ledger entries. Either "
            "`path` or `text` (or both) must be set."
        ),
    )
    def _count_tokens(
        path: str | None = None,
        text: str | None = None,
        extensions: list[str] | None = None,
    ) -> dict:
        ext_tuple = tuple(extensions) if extensions is not None else (".md",)
        return count_tokens(path=path, text=text, extensions=ext_tuple).to_dict()
