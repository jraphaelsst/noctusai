"""noctus.dev.scaffold_memory — emit a memory entry with correct
frontmatter + atomically append the MEMORY.md index line.

~12 memory entries were hand-written this session; the frontmatter
shape is fixed and the index-line sync is error-prone by hand. The
agent passes the fields; the tool emits consumable, convention-correct
boilerplate.
"""
from __future__ import annotations

from pathlib import Path

_MEM_DIR = Path(
    "/Users/rapha/.claude/projects/"
    "-Users-rapha-Documents-repository-NoctusAI-noctusai/memory"
)
_TYPES = ("user", "feedback", "project", "reference")
_SECTIONS = (
    "Architecture & seed", "DRY / componentization", "Foundational principles",
    "Code quality / engineering", "Testing / detectors",
    "Security & compliance", "MCP & DB tooling", "Reading discipline",
    "Project execution", "Product hygiene", "Documentation",
)


def scaffold_memory(
    name: str,
    description: str,
    body: str,
    mtype: str = "feedback",
    index_section: str = "Foundational principles",
    index_hook: str | None = None,
    mem_dir: str | None = None,
) -> dict:
    """Write `<name>.md` with the canonical frontmatter + body, then add
    a one-line pointer to MEMORY.md under `## ... ### <index_section>`.
    `name` = kebab slug (no .md). Refuses to clobber an existing entry."""
    if mtype not in _TYPES:
        return {"ok": False, "error": f"metadata.type must be one of {_TYPES}"}
    if index_section not in _SECTIONS:
        return {"ok": False, "error": f"index_section must be one of {_SECTIONS}"}
    root = Path(mem_dir) if mem_dir else _MEM_DIR
    entry = root / f"{name}.md"
    if entry.exists():
        return {"ok": False, "error": f"{name}.md already exists — edit it, don't duplicate"}

    entry.write_text(
        f"---\nname: {name}\ndescription: {description}\n"
        f"metadata:\n  type: {mtype}\n---\n\n{body.rstrip()}\n"
    )
    idx = root / "MEMORY.md"
    appended = None
    if idx.exists():
        hook = index_hook or description
        line = f"- [{description[:60]}]({name}.md) — {hook}"
        text = idx.read_text()
        header = f"### {index_section}"
        if header in text:
            i = text.index(header)
            nl = text.find("\n", i)
            text = text[: nl + 1] + line + "\n" + text[nl + 1 :]
            idx.write_text(text)
            appended = line
    return {
        "ok": True,
        "entry": str(entry),
        "index_line": appended,
        "note": None if appended else "MEMORY.md not updated (file/section absent) — add the index line by hand",
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_memory",
        description=(
            "Emit a memory entry with the canonical frontmatter "
            "(name/description/metadata.type) + body, and append the "
            "MEMORY.md index pointer under the given section. Refuses to "
            "clobber an existing slug. Replaces hand-writing the rigid "
            "frontmatter + error-prone index-sync."
        ),
    )
    def _scaffold_memory(
        name: str,
        description: str,
        body: str,
        mtype: str = "feedback",
        index_section: str = "Foundational principles",
        index_hook: str | None = None,
    ) -> dict:
        return scaffold_memory(
            name, description, body, mtype=mtype,
            index_section=index_section, index_hook=index_hook,
        )


__all__ = ["scaffold_memory", "register"]
