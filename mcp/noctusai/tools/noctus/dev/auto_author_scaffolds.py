"""auto_author_scaffolds — starting-point template fillers for codification.

What this is (and what it ISN'T)
    NOT: an AI ghostwriter that produces finished memory entries / KB
    pattern docs / keeper code. That requires judgment the original
    diagnostic correctly flagged as not-codifiable.

    IS: a STARTING POINT generator. Takes a surface (description + a
    handful of related entries from the codebase) and emits a SCAFFOLD —
    a template with placeholders + vector-matched references — that the
    human refines into the finished artifact.

    The scaffold removes "blank-page friction." The human still does
    the judgment work.

Three scaffolds shipped
    1. `memory_entry(name, description, target?)` — produces a draft
       feedback_*.md memory entry.
    2. `kb_pattern(name, description)` — produces a draft KB pattern
       doc with sections (Why / What / API / Composes-with / Anti-patterns).
    3. `keeper(name, description)` — produces a draft `check_<name>`
       function skeleton with the predicate + the issue-dict shape.

Each one:
    - Fills the structural skeleton.
    - Vector-matches against existing artifacts of the same kind and
      lists them as "see also" / "similar existing patterns" references.
    - Marks every placeholder with `<TODO>` so the human knows what to
      fill in.

Status: scaffolds-only. The human reads + refines + commits. Skipping
the scaffold and writing from scratch is still always valid; this is
a starting-point convenience.

KB § CONTEXT/PATTERNS/common/auto-author-scaffolds.md.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _kb_search(text: str, top_k: int = 5) -> list[dict]:
    """Best-effort kb_search; empty list on failure."""
    try:
        from . import kb_embeddings as kbe
        return kbe.search(text, top_k=top_k)
    except Exception:  # noqa: BLE001
        return []


def memory_entry(
    name: str,
    description: str,
    target: str | None = None,
) -> dict[str, Any]:
    """Draft a memory entry (`feedback_<name>.md` style).

    Args:
      name: short identifier (used in filename + frontmatter `name:`).
      description: one-sentence summary.
      target: optional load-bearing surface (path / module / rule).

    Returns:
      {ok, filename_suggestion, content, similar_existing: [...]}
    """
    similar = _kb_search(description, top_k=3)
    similar_refs = [f"`{h.get('path', '?')}`" for h in similar]
    similar_block = (
        "\n".join(f"- {ref}" for ref in similar_refs)
        if similar_refs
        else "- (none found via kb_search)"
    )
    content = f"""---
name: {name}
description: {description}
metadata:
  type: feedback
---

**The rule.** <TODO: state the rule in one sentence>

**Why.** <TODO: the WHY clause — what bit, when, how often>

**How to apply.** <TODO: when does this rule fire? What's the diagnostic
the architect/agent runs at the moment of decision?>

**Composes with**: <TODO: link to related rules / patterns>

**History**: surfaced {_now_date()} from {target or '<surface>'}.

## Similar existing entries (consult before authoring)
{similar_block}
"""
    return {
        "ok": True,
        "filename_suggestion": f"feedback_{name}.md",
        "content": content,
        "similar_existing": [
            {"path": h.get("path"), "score": h.get("score")} for h in similar
        ],
    }


def kb_pattern(name: str, description: str) -> dict[str, Any]:
    """Draft a KB pattern doc (`KB § CONTEXT/PATTERNS/<owner>/<name>.md`).

    Args:
      name: kebab-case pattern name (used as filename slug + H1).
      description: one-sentence summary.

    Returns:
      {ok, filename_suggestion, content, similar_existing: [...]}
    """
    similar = _kb_search(description, top_k=5)
    similar_refs = [f"`{h.get('path', '?')}`" for h in similar]
    similar_block = (
        "\n".join(f"- {ref}" for ref in similar_refs)
        if similar_refs
        else "- (none found via kb_search)"
    )
    title = name.replace("-", " ").title()
    content = f"""# {title} — {description}

**What it is.** <TODO: 1-2 sentences. What does this pattern codify?>

**Status**: born {_now_date()}.

## Why

<TODO: the problem. What was happening before this pattern? Concrete
evidence (N=? recurrence; specific incident).>

## What it does (mechanics)

<TODO: the predicate. Step-by-step or rule statement. Use a table if
multiple cases.>

## When to apply

<TODO: trigger conditions. When does an agent / architect REACH for
this pattern?>

## API / surface

```
<TODO: function signature or MCP tool name + args>
```

## Anti-patterns

- **DON'T** <TODO>
- **DON'T** <TODO>

## Composes with

<TODO: link to related patterns:>
{similar_block}

## History

- {_now_date()}: pattern authored from a recurring observation. <TODO:
  cite the N>=3 evidence.>
"""
    return {
        "ok": True,
        "filename_suggestion": f"{name}.md",
        "content": content,
        "similar_existing": [
            {"path": h.get("path"), "score": h.get("score")} for h in similar
        ],
    }


def keeper(name: str, description: str) -> dict[str, Any]:
    """Draft a `check_<name>` keeper skeleton.

    Args:
      name: snake-case keeper name suffix (no `check_` prefix).
      description: what the keeper enforces.

    Returns: {ok, code, kb_doc_pointer_suggestion}
    """
    fn_name = f"check_{name}" if not name.startswith("check_") else name
    code = f'''def {fn_name}(repo_root: Path | None = None) -> list[dict]:
    """Stage-4 keeper ({_now_date()}): {description}

    <TODO: full docstring — what predicate, why severity, silent-skip
    conditions, remediation command.>

    Severity: <TODO: 'high' | 'warning'>.

    KB § CONTEXT/PATTERNS/common/<TODO>.md.
    """
    issues: list[dict] = []
    root = repo_root or REPO_ROOT
    # <TODO: silent-skip guard — non-noc tree should not error>
    # if not (root / "<surface>").exists():
    #     return issues

    # <TODO: predicate. Read the surface, compute the violation, emit
    # issue dicts.>

    # Example issue shape:
    # issues.append({{
    #     "product": "<harness>", "file": "<path>",
    #     "issue": "<one-line description>",
    #     "severity": "high",
    #     "symbol": "<surface>-<class>",
    # }})

    return issues
'''
    return {
        "ok": True,
        "code": code,
        "kb_doc_pointer_suggestion": f"KB § CONTEXT/PATTERNS/common/{name.replace('_', '-')}.md",
        "next_steps": [
            f"Author the KB pattern doc at the suggested path.",
            f"Wire {fn_name} into the dispatcher in compliance.py (check_all_products).",
            f"Add CLI flag `--{name.replace('_', '-')}` in cli.py.",
            f"Add allowlist entry in _AGENT_KB_UNOWNED_ALLOWLIST if it's a common pattern.",
            f"Write tests in mcp/noctusai/tests/test_{name}.py.",
        ],
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.scaffold_memory_entry",
        description=(
            "Draft a `feedback_<name>.md` memory entry SCAFFOLD with "
            "<TODO> placeholders + similar-existing references from "
            "kb_search. Starting point only; the human refines + commits. "
            "Removes blank-page friction without ghostwriting the judgment. "
            "KB § CONTEXT/PATTERNS/common/auto-author-scaffolds.md."
        ),
    )
    def _mem(name: str, description: str, target: str | None = None) -> dict:
        return memory_entry(name, description, target=target)

    @server.tool(
        name="noctus.dev.scaffold_kb_pattern_draft",
        description=(
            "Draft a KB pattern doc SCAFFOLD: H1 + Why / What / When / API "
            "/ Anti-patterns / Composes-with sections, all with <TODO> "
            "placeholders. Lists similar-existing patterns via kb_search "
            "so the human consults before re-inventing."
        ),
    )
    def _kb(name: str, description: str) -> dict:
        return kb_pattern(name, description)

    @server.tool(
        name="noctus.dev.scaffold_keeper_function",
        description=(
            "Draft a `check_<name>` keeper function SCAFFOLD with docstring "
            "placeholder + standard issue-dict shape + a next-steps "
            "checklist (CLI flag wiring, dispatcher registration, "
            "allowlist, test file)."
        ),
    )
    def _k(name: str, description: str) -> dict:
        return keeper(name, description)


__all__ = ["memory_entry", "kb_pattern", "keeper", "register"]
