"""Path guards for files the connector writes (audio) or reads (clone samples).

Rule: a path inside a git work tree is refused unless git ignores it
(`git check-ignore`) — generated audio and voice samples (biometric data)
must never land on a tracked / committable path. Paths outside any git
tree (the default `~/.noctusai/private/elevenlabs/...`) always pass.
Must be absolute (no cwd-dependent surprises); `..` is resolved first.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .api import RefusedError

_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str, fallback: str = "audio", max_len: int = 40) -> str:
    s = _SLUG.sub("-", text.lower()).strip("-")[:max_len].strip("-")
    return s or fallback


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=10)


def _nearest_existing(p: Path) -> Path:
    while not p.exists() and p != p.parent:
        p = p.parent
    return p


def ensure_not_committable(raw: str, *, what: str) -> Path:
    """Return the resolved absolute path, or raise `RefusedError`."""
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise RefusedError(f"{what} must be an absolute path, got {raw!r}.")
    p = p.resolve()
    probe = _nearest_existing(p)
    probe = probe if probe.is_dir() else probe.parent
    try:
        top = _git(["rev-parse", "--show-toplevel"], probe)
    except (OSError, subprocess.SubprocessError) as e:
        raise RefusedError(f"cannot verify {what} is outside git (git unavailable: {e}).") from e
    if top.returncode != 0:
        return p  # not inside a git work tree
    ign = _git(["check-ignore", "-q", "--", str(p)], Path(top.stdout.strip()))
    if ign.returncode == 0:
        return p  # inside a repo but git-ignored: cannot be committed by accident
    raise RefusedError(
        f"{what} {str(p)!r} is inside a git work tree and is not git-ignored. Use a path "
        "outside the repo (default: ~/.noctusai/private/elevenlabs/) or a git-ignored one."
    )


__all__ = ["ensure_not_committable", "slugify"]
