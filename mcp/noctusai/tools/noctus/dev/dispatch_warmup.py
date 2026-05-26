"""dispatch_warmup — pre-dispatch context-warmup bundle for a brief.

Why this exists
    A dispatched engineer comes in cold. Its first turn(s) read CLAUDE.md
    + a few KB docs to bootstrap. Those reads cost tokens + wall-clock
    BEFORE the engineer does any real work. If the architect already
    KNOWS what context is relevant (target files, the agent's owns_kb,
    similar past auto-improvement entries), feeding that into the brief
    means the engineer arrives pre-warmed.

What it returns
    Given target_files + agent_name + (optional) brief description,
    returns a compact bundle:
      - The agent's bundle (frontmatter + body + owned-KB compact extracts).
      - Auto-improvement entries semantically related to the target.
      - Top kb_search hits for the brief description.
      - Top code_search hits for the target files (cross-product reference).

    Output is ALREADY-formatted markdown the architect can paste into
    the brief's "## Context warmup" section.

Why not auto-inject
    The architect is the curator. This tool RETURNS the warmup; the
    architect decides what to keep. Auto-inject would bloat briefs +
    introduce stale-content drift.

Status: opt-in compose-time tool. `engineer_brief_compose` does NOT call
this automatically (yet); callers invoke it before drafting.

KB § CONTEXT/PATTERNS/common/dispatch-warmup.md.
"""
from __future__ import annotations

from typing import Any


def warmup(
    agent_name: str,
    description: str | None = None,
    target_files: list[str] | None = None,
    kb_top_k: int = 3,
    code_top_k: int = 3,
    ai_top_k: int = 3,
) -> dict[str, Any]:
    """Build a pre-dispatch context warmup bundle.

    Args:
      agent_name: specialist name (e.g. "backend-engineer").
      description: optional brief description (anchor for semantic search).
      target_files: optional file paths the brief touches.
      kb_top_k: hits to pull from kb-embeddings (default 3).
      code_top_k: hits to pull from code-embeddings (default 3).
      ai_top_k: hits to pull from auto-improvement (default 3).

    Returns:
      {
        ok: bool,
        agent_name: str,
        bundle_summary: str | None,    # agent body excerpt + owned-kb names
        kb_hits: [...],
        code_hits: [...],
        auto_improvement_hits: [...],
        markdown: str,                 # formatted "## Context warmup" block
      }
    """
    out: dict[str, Any] = {
        "ok": True,
        "agent_name": agent_name,
        "bundle_summary": None,
        "kb_hits": [],
        "code_hits": [],
        "auto_improvement_hits": [],
        "markdown": "",
    }

    # 1. Agent bundle.
    try:
        from . import agent_context_cache as acc
        bundle = acc.lookup(agent_name)
        if bundle.get("ok"):
            body_excerpt = (bundle.get("body") or "")[:600]
            owned = bundle.get("owned_kb", [])
            owned_names = [d.get("path", "") for d in owned[:10]]
            out["bundle_summary"] = (
                f"{body_excerpt}\n\n_Owned KB territory_: "
                + ", ".join(owned_names)
            )
    except Exception:  # noqa: BLE001
        pass

    # Build the anchor string for semantic searches.
    anchor = description or ""
    if target_files:
        anchor = (anchor + "\n" + "\n".join(target_files)).strip()
    if not anchor:
        anchor = agent_name  # last-resort anchor

    # 2. kb_search hits.
    try:
        from . import kb_embeddings as kbe
        kb_hits = kbe.search(anchor, top_k=kb_top_k)
        out["kb_hits"] = kb_hits
    except Exception:  # noqa: BLE001
        pass

    # 3. code_search hits.
    try:
        from . import code_embeddings as ce
        code_hits = ce.search(anchor, top_k=code_top_k)
        out["code_hits"] = code_hits
    except Exception:  # noqa: BLE001
        pass

    # 4. auto-improvement via kb_recurrence_radar.
    try:
        from . import kb_recurrence_radar as krr
        radar = krr.consult(text=anchor, top_k=ai_top_k)
        if radar.get("ok"):
            out["auto_improvement_hits"] = radar.get("hits", [])
    except Exception:  # noqa: BLE001
        pass

    # 5. Format as paste-ready markdown.
    parts: list[str] = ["## Context warmup", ""]
    if out["bundle_summary"]:
        parts.append(f"### Agent: `{agent_name}`")
        parts.append("")
        parts.append(out["bundle_summary"])
        parts.append("")
    if out["kb_hits"]:
        parts.append("### Relevant KB chunks")
        for h in out["kb_hits"]:
            preview = (h.get("chunk_text") or "").splitlines()[0][:100]
            parts.append(f"- [{h['score']:.3f}] `{h['path']}#chunk{h['chunk_idx']}` — {preview}")
        parts.append("")
    if out["code_hits"]:
        parts.append("### Relevant code symbols")
        for h in out["code_hits"]:
            sn = h.get("symbol_name") or "(file)"
            parts.append(f"- [{h['score']:.3f}] `{h['path']}` :: `{sn}` ({h.get('kind', '?')})")
        parts.append("")
    if out["auto_improvement_hits"]:
        parts.append("### Related auto-improvement entries")
        for h in out["auto_improvement_hits"]:
            entry = h.get("entry") or {}
            target = (entry.get("target") or "?")[:80]
            parts.append(f"- [{h['score']:.3f}] [{entry.get('status', '?')}] {target}")
        parts.append("")
    out["markdown"] = "\n".join(parts).rstrip() + "\n"
    return out


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.dispatch_warmup",
        description=(
            "Build a pre-dispatch context warmup bundle: target agent's "
            "compact body + top kb_search + code_search + auto-improvement "
            "hits semantically related to the brief description / target "
            "files. Returns formatted markdown the architect can paste "
            "into the brief's '## Context warmup' section. Opt-in by "
            "design — the architect curates; this tool surfaces. "
            "KB § CONTEXT/PATTERNS/common/dispatch-warmup.md."
        ),
    )
    def _warmup(agent_name: str, description: str | None = None,
                target_files: list[str] | None = None,
                kb_top_k: int = 3, code_top_k: int = 3,
                ai_top_k: int = 3) -> dict:
        return warmup(agent_name, description=description,
                      target_files=target_files,
                      kb_top_k=kb_top_k, code_top_k=code_top_k,
                      ai_top_k=ai_top_k)


__all__ = ["warmup", "register"]
