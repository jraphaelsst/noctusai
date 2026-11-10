"""noctus.dev.scaffold_memory — emit a memory entry with correct
frontmatter + atomically append the MEMORY.md index line.

~12 memory entries were hand-written this session; the frontmatter
shape is fixed and the index-line sync is error-prone by hand. The
agent passes the fields; the tool emits consumable, convention-correct
boilerplate.
"""
from __future__ import annotations

import re
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


# MEMORY.md became a topic ROUTER (KB § PATTERNS/common/memory-index-topic-split.md): pointers
# live in MEMORY-<topic>.md, never in MEMORY.md. Legacy `### section` -> topic file.
_SECTION_TOPIC = {
    "Architecture & seed": "seed-architecture", "DRY / componentization": "code-quality",
    "Foundational principles": "codification", "Code quality / engineering": "code-quality",
    "Testing / detectors": "testing", "Security & compliance": "sso-db-rls",
    "MCP & DB tooling": "mcp-tooling", "Reading discipline": "code-quality",
    "Project execution": "project-execution", "Product hygiene": "product-hygiene",
    "Documentation": "codification",
}


def _append_to_topic_file(root: Path, topic: str, line: str) -> str | None:
    """Insert `line` before the first `- [` pointer of MEMORY-<topic>.md (else at the end).
    Returns the topic file name written, or None when that file does not exist."""
    tf = root / f"MEMORY-{topic}.md"
    if not tf.exists():
        return None
    lines = tf.read_text().splitlines(keepends=True)
    at = next((i for i, l in enumerate(lines) if l.startswith("- [")), len(lines))
    if at == len(lines) and lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    lines.insert(at, line + "\n")
    tf.write_text("".join(lines))
    return tf.name


def scaffold_memory(
    name: str,
    description: str,
    body: str,
    mtype: str = "feedback",
    index_section: str = "Foundational principles",
    index_hook: str | None = None,
    mem_dir: str | None = None,
    topic: str | None = None,
) -> dict:
    """Write `<name>.md` with the canonical frontmatter + body, then add
    a one-line pointer to the index. Router layout (MEMORY.md routes to
    MEMORY-<topic>.md): the pointer goes into the topic file (`topic`, else the
    one mapped from `index_section`). Legacy flat MEMORY.md with a
    `### <index_section>` header: appended there. When neither place exists the
    result says `index_updated: false` loudly — never a quiet no-op.
    `name` = kebab slug (no .md). Refuses to clobber an existing entry."""
    if mtype not in _TYPES:
        return {"ok": False, "error": f"metadata.type must be one of {_TYPES}"}
    if index_section not in _SECTIONS:
        return {"ok": False, "error": f"index_section must be one of {_SECTIONS}"}
    if topic is not None and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", topic):
        return {"ok": False, "error": "topic must be a kebab slug naming MEMORY-<topic>.md"}
    root = Path(mem_dir) if mem_dir else _MEM_DIR
    entry = root / f"{name}.md"
    if entry.exists():
        return {"ok": False, "error": f"{name}.md already exists — edit it, don't duplicate"}

    entry.write_text(
        f"---\nname: {name}\ndescription: {description}\n"
        f"metadata:\n  type: {mtype}\n---\n\n{body.rstrip()}\n"
    )
    idx = root / "MEMORY.md"
    hook = index_hook or description
    line = f"- [{description[:60]}]({name}.md) — {hook}"
    appended = None
    where = None
    if idx.exists():
        text = idx.read_text()
        header = f"### {index_section}"
        if header in text:  # legacy flat layout
            i = text.index(header)
            nl = text.find("\n", i)
            idx.write_text(text[: nl + 1] + line + "\n" + text[nl + 1 :])
            appended, where = line, idx.name
    if appended is None:  # router layout: the pointer lives in the topic file
        tname = _append_to_topic_file(root, topic or _SECTION_TOPIC[index_section], line)
        if tname:
            appended, where = line, tname
    return {
        "ok": True,
        "entry": str(entry),
        "index_updated": appended is not None,
        "index_file": where,
        "index_line": appended,
        "note": None if appended else (
            "INDEX NOT UPDATED: no `### " + index_section + "` header in MEMORY.md and no "
            "MEMORY-" + (topic or _SECTION_TOPIC[index_section]) + ".md topic file — add the pointer "
            "by hand (pass topic=<name> to pick the file)"),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_memory",
        description=(
            "Emit a memory entry with the canonical frontmatter "
            "(name/description/metadata.type) + body, and append the "
            "index pointer (router layout: into MEMORY-<topic>.md; reports index_updated). Refuses to "
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
        topic: str | None = None,
    ) -> dict:
        return scaffold_memory(
            name, description, body, mtype=mtype,
            index_section=index_section, index_hook=index_hook, topic=topic,
        )


__all__ = ["scaffold_memory", "register"]
