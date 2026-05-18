"""noctus.dev.findings — reliably curate the canonical findings.md.

Engineers return findings AS TEXT (the N=5 return-as-text pattern,
because the project dir isn't in their worktree); the architect
hand-transcribes — fragmented across worktrees this session. This tool
appends a categorized + provenance-tagged entry to the ONE canonical
findings.md under the right of the five standard sections.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT

_CATEGORIES = ("Slips", "Errors", "Mistakes", "Lessons", "Interesting findings")


def _locate(project_slug: str) -> Path | None:
    for cand in (
        REPO_ROOT / "projects" / project_slug / "findings.md",
        *REPO_ROOT.glob(f"products/*/projects/{project_slug}/findings.md"),
        *REPO_ROOT.glob(f"core/projects/{project_slug}/findings.md"),
    ):
        if cand.exists():
            return cand
    return None


def findings_append(
    project_slug: str, category: str, entry: str, provenance: str | None = None
) -> dict:
    """Append `entry` under `## <category>` in the project's findings.md.
    `category` must be one of the five standard sections. `provenance`
    (e.g. 'W2-META-S1' / 'architect') is bolded as the entry lead."""
    if category not in _CATEGORIES:
        return {"ok": False, "error": f"category must be one of {_CATEGORIES}"}
    path = _locate(project_slug)
    if path is None:
        return {
            "ok": False,
            "error": f"no findings.md for project {project_slug!r} "
            f"(searched projects/ + products/*/projects/ + core/projects/)",
        }

    text = path.read_text()
    line = f"- **{provenance}** — {entry}" if provenance else f"- {entry}"
    header = f"## {category}"
    if header in text:
        idx = text.index(header)
        nxt = text.find("\n## ", idx + len(header))
        cut = nxt if nxt != -1 else len(text)
        block = text[idx:cut].rstrip()
        # drop a lone "_(none)_" placeholder if present
        block = "\n".join(
            ln for ln in block.splitlines()
            if ln.strip().lower() not in ("- _(none)_", "- _(none yet)_")
        )
        new = block + "\n" + line + "\n\n"
        text = text[:idx] + new + text[cut:].lstrip("\n")
        if not text.endswith("\n"):
            text += "\n"
    else:
        text = text.rstrip() + f"\n\n{header}\n{line}\n"
    path.write_text(text)
    return {"ok": True, "path": str(path.relative_to(REPO_ROOT)), "category": category, "appended": line}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.findings",
        description=(
            "Append a categorized + provenance-tagged entry to a "
            "project's canonical findings.md (one of the 5 sections: "
            "Slips/Errors/Mistakes/Lessons/Interesting findings). "
            "Replaces hand-transcription of engineers' returned-as-text "
            "findings; drops the _(none)_ placeholder on first real "
            "entry. Resolves slug across projects/ + products/*/projects/ "
            "+ core/projects/."
        ),
    )
    def _findings(
        project_slug: str, category: str, entry: str, provenance: str | None = None
    ) -> dict:
        return findings_append(project_slug, category, entry, provenance=provenance)


__all__ = ["findings_append", "register"]
