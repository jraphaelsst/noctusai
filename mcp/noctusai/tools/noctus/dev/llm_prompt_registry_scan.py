"""Scanner behind ``check_llm_prompt_from_registry`` (owner rule 2026-11-08).

"Agents are built consuming 100% of the prompt straight from the database, to protect our prompts from
malicious users; never from code." The sanctioned path is ``noctusai_lib.integrations.prompt_registry``
(``chamar_ia`` / ``chamar_ia_visao`` / ``transcrever_ia`` / ``prompt_e_modelo``). This module finds every
call through the seed LLM seam or a vendor SDK that is NOT fed by the registry, plus prompt-shaped constants
and repo ``.md`` files loaded as a system prompt.

AST only (CLAUDE.md AST-first). Pure functions, no I/O beyond reading source files; the keeper wrapper in
``compliance.py`` owns the ratchet baseline and the issue shape.
KB § PATTERNS/ai/prompts-from-registry.md.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

#: Seed LLM seam entry points that take a prompt (inventory: seam ``noctusai_lib/integrations/llm``).
SEAM_CALLS = frozenset({
    "chat_completion", "chat_completion_with_usage", "chat_completion_stream", "chat_with_tools",
    "run_tool_loop", "run_tool_loop_sync",
    "analyze_image", "analyze_images", "analyze_image_with_refusal_retry",
})
#: ``digest.narrative`` and the help-chat router (built-in knowledge file as system prompt).
NARRATIVE_CALL = "narrative"
HELP_CHAT_CALL = "create_help_chat_router"
#: Vendor SDK call chains (dotted suffix of the callee).
SDK_CHAINS = (
    "messages.create", "chat.completions.create", "responses.create", "images.edit",
)
SDK_CLASSES = frozenset({"ClaudeSDKClient"})

#: Names whose presence in the enclosing function marks the call as registry-fed.
REGISTRY_FEEDERS = frozenset({
    "prompt_e_modelo", "chamar_ia", "chamar_ia_visao", "transcrever_ia",
})

_PROMPT_CONST_RE = re.compile(r"(?:^|_)(?:[A-Z0-9]*SYSTEM[A-Z0-9_]*|[A-Z0-9_]*PROMPT[A-Z0-9_]*)$")

#: Path fragments (repo-relative, posix) that are exempt, each with the reason.
EXEMPT_PREFIXES: dict[str, str] = {
    "seed/lib/backend/noctusai_lib/integrations/llm/": "the seam's own provider modules",
    "seed/lib/backend/noctusai_lib/integrations/image_edit/": "vendor image-edit adapter (the seam itself)",
    "seed/lib/backend/noctusai_lib/integrations/prompt_registry/": "the sanctioned path itself",
    "mcp/openai_mcp/tools/": "pass-through tools: the prompt is the caller's input",
    "mcp/noctusai/tools/llm/": "pass-through tools: the prompt is the caller's input",
}
EXEMPT_FILES: dict[str, str] = {
    "products/agents/backend/app/runtime/llm_runtime.py": "agents runtime running the DB-compiled spec",
    "products/agents/backend/app/runtime/eval_driver_live.py": "agents runtime running the DB-compiled spec",
    "products/agents/backend/app/studio/geracao.py": "agents runtime running the DB-compiled spec",
}

SCAN_ROOTS = ("products", "seed/lib/backend", "seed/framework/backend", "mcp")
_SKIP_PARTS = frozenset({
    "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".git", "tests", "migrations",
})


def exemption(rel: str) -> str | None:
    """Reason a repo-relative path is exempt, else ``None``."""
    if rel in EXEMPT_FILES:
        return EXEMPT_FILES[rel]
    for prefix, why in EXEMPT_PREFIXES.items():
        if rel.startswith(prefix):
            return why
    name = rel.rsplit("/", 1)[-1]
    if name.startswith("test_") or name == "conftest.py" or name.endswith("_test.py"):
        return "tests"
    return None


def _chain(node: ast.AST) -> str:
    """Dotted name of an attribute/name chain (``a.b.c``); '' when it is not a plain chain."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _seam_aliases(tree: ast.Module) -> tuple[dict[str, str], set[str]]:
    """``(local name -> canonical seam function, local names bound to the seam MODULE)``.

    Only names imported from an ``llm``-ish seam module count, so a product's own ``chat_completion``
    method or an unrelated ``narrative`` is not mistaken for the seam. Aliases (``chat_completion as
    text_fn``) and function-level imports are resolved, because the site is the REFERENCE, not only the call.
    """
    names: dict[str, str] = {}
    modules: set[str] = set()
    interesting = SEAM_CALLS | {NARRATIVE_CALL, HELP_CHAT_CALL}
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            seamish = ("integrations.llm" in mod or mod.endswith(".llm") or mod == "llm"
                       or "domain.digest" in mod or mod.endswith("digest") or "help_chat" in mod
                       or bool(n.level and mod.split(".")[0] in {"llm", "digest", "narrative", "help_chat"}))
            for a in n.names:
                if seamish and a.name in interesting:
                    names[a.asname or a.name] = "digest.narrative" if a.name == NARRATIVE_CALL else a.name
                elif a.name == "llm" and "integrations" in mod:
                    modules.add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if "integrations.llm" in a.name or a.name.endswith(".llm"):
                    modules.add(a.asname or a.name.split(".")[0])
    return names, modules


def _site_label(node: ast.AST, names: dict[str, str], modules: set[str]) -> str | None:
    """Flagged-site label for one AST node, or ``None``. Reference-based for the seam (a DI default or an
    alias is a site too), call-based for vendor SDKs."""
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        return names.get(node.id)
    if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
        last = node.attr
        chain = _chain(node)
        base = chain.split(".", 1)[0] if chain else ""
        if last in SEAM_CALLS or last == HELP_CHAT_CALL:
            return last
        if last == NARRATIVE_CALL and (base in modules or "digest" in chain.lower()):
            return "digest.narrative"
        return None
    if isinstance(node, ast.Call):
        chain = _chain(node.func)
        if chain:
            for sdk in SDK_CHAINS:
                if chain.endswith("." + sdk) or chain == sdk:
                    return sdk
            if chain.rsplit(".", 1)[-1] in SDK_CLASSES:
                return chain.rsplit(".", 1)[-1]
    return None


def _enclosing_function(tree: ast.Module) -> dict[int, ast.AST | None]:
    """Map ``id(node)`` -> outermost enclosing function (None at module level)."""
    owner: dict[int, ast.AST | None] = {}

    def visit(node: ast.AST, top_fn: ast.AST | None) -> None:
        for child in ast.iter_child_nodes(node):
            nxt = top_fn
            if top_fn is None and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nxt = child
            owner[id(child)] = top_fn
            visit(child, nxt)

    visit(tree, None)
    return owner


def _references_feeder(scope: ast.AST) -> bool:
    for n in ast.walk(scope):
        if isinstance(n, ast.Name) and n.id in REGISTRY_FEEDERS:
            return True
        if isinstance(n, ast.Attribute) and n.attr in REGISTRY_FEEDERS:
            return True
    return False


def _md_prompt_loads(tree: ast.Module) -> list[tuple[int, str]]:
    """``.read_text()`` / ``open()`` of a path built from a ``*.md`` string literal."""
    out: list[tuple[int, str]] = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        fn = n.func
        is_read = isinstance(fn, ast.Attribute) and fn.attr in {"read_text", "read_bytes"}
        is_open = isinstance(fn, ast.Name) and fn.id == "open"
        if not (is_read or is_open):
            continue
        scope = fn.value if is_read else (n.args[0] if n.args else None)
        if scope is None:
            continue
        for c in ast.walk(scope):
            if isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value.endswith(".md"):
                out.append((n.lineno, c.value))
                break
    return out


def scan_source(source: str, rel: str) -> list[dict]:
    """Findings for one file: ``{kind, symbol, line}``; ``kind`` in call | prompt-const | md-prompt."""
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        return []
    names, modules = _seam_aliases(tree)
    owner = _enclosing_function(tree)
    findings: list[dict] = []
    flagged_calls: list[ast.AST] = []
    in_attr: set[int] = set()  # Name nodes that are the base of a flagged Attribute (avoid double count)
    for n in ast.walk(tree):
        label = _site_label(n, names, modules)
        if label is None:
            continue
        if isinstance(n, ast.Attribute):
            for c in ast.walk(n.value):
                in_attr.add(id(c))
        elif id(n) in in_attr:
            continue
        scope = owner.get(id(n))
        if scope is not None and _references_feeder(scope):
            continue  # fed by the registry
        flagged_calls.append(n)
        findings.append({"kind": "call", "symbol": label, "line": getattr(n, "lineno", 0)})
    if not flagged_calls:
        return findings
    seen_consts: set[str] = set()
    for site in flagged_calls:
        # a prompt-shaped constant passed into the call (for a bare reference: into its enclosing function)
        scope = site if isinstance(site, ast.Call) else (owner.get(id(site)) or tree)
        for c in ast.walk(scope):
            if isinstance(c, ast.Name) and isinstance(c.ctx, ast.Load) and _PROMPT_CONST_RE.search(c.id) and "VERSION" not in c.id \
                    and c.id not in seen_consts:
                seen_consts.add(c.id)
                findings.append({"kind": "prompt-const", "symbol": c.id, "line": c.lineno})
    for line, md in _md_prompt_loads(tree):
        findings.append({"kind": "md-prompt", "symbol": md, "line": line})
    return findings


def iter_files(root: Path):
    for sub in SCAN_ROOTS:
        base = root / sub
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            if any(part in _SKIP_PARTS for part in p.relative_to(root).parts):
                continue
            yield p


def scan_tree(root: Path, only: set[str] | None = None) -> dict[str, list[dict]]:
    """``{repo-relative path: findings}`` for every non-exempt file with at least one finding."""
    out: dict[str, list[dict]] = {}
    for p in iter_files(root):
        rel = p.relative_to(root).as_posix()
        if only is not None and rel not in only:
            continue
        if exemption(rel):
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not any(k in src for k in (*SEAM_CALLS, NARRATIVE_CALL, HELP_CHAT_CALL, "create(", ".edit(", "ClaudeSDKClient")):
            continue
        f = scan_source(src, rel)
        if f:
            out[rel] = f
    return out


def counts(found: dict[str, list[dict]]) -> dict[str, int]:
    return {rel: len(f) for rel, f in found.items()}


def load_baseline(path: Path) -> dict[str, int]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): int(v) for k, v in dict(data.get("files", {})).items()}


def shrink_baseline(root: Path, path: Path) -> dict[str, int]:
    """First run records the current sites; afterwards only SHRINKS (min(current, recorded); a file that
    no longer exists or no longer has a site drops out). A new site can never be ratified through this."""
    current = counts(scan_tree(root))
    if path.exists():
        old = load_baseline(path)
        new = {p: min(c, old[p]) for p, c in current.items() if p in old}
    else:
        new = current
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"files": dict(sorted(new.items()))}, indent=2) + "\n", encoding="utf-8")
    return new


PATTERN_DOC = "KB § PATTERNS/ai/prompts-from-registry.md"
BASELINE_REL = ("mcp", "noctusai", "tests", "llm_prompt_from_registry_baseline.json")
SHADOW_SINCE = "2026-11-08"


def file_clean(root: Path, rel: str) -> bool:
    """True when ``rel`` no longer exists or holds no un-baselined-or-baselined site (auto-closing predicate
    ``llm_prompt_registry_clean:<rel>`` for the drift rows)."""
    p = root / rel
    if not p.is_file() or exemption(rel):
        return True
    return not scan_tree(root, only={rel})


def over_baseline(root: Path, baseline: dict[str, int], only: set[str] | None = None) -> list[dict]:
    """Files whose site count exceeds the ratchet baseline (a NEW file has baseline 0)."""
    out: list[dict] = []
    for rel, f in scan_tree(root, only=only).items():
        allowed = baseline.get(rel, 0)
        if len(f) > allowed:
            out.append({"file": rel, "count": len(f), "allowed": allowed, "findings": f})
    return out


def stale_baseline(root: Path, baseline: dict[str, int]) -> list[str]:
    """Baseline entries that can shrink (file gone, exempt, or fewer sites now) - drop them via the refresh flag."""
    cur = counts(scan_tree(root))
    return sorted(p for p, n in baseline.items() if cur.get(p, 0) < n)


def log_telemetry(rows: list[dict]) -> dict[str, list[str]]:
    """One open auto-improvement drift row per file that grew past the baseline (deduped; self-closing)."""
    from tools.noctus.dev import auto_improvement as ai

    logged: list[str] = []
    errors: list[str] = []
    for r in rows:
        target = f"llm_prompt_not_from_registry:{r['file']}"
        if any(e.get("target") == target for e in ai.query(target=target, kind="drift", open_only=True,
                                                           skip_reconcile=True)):
            continue
        out = ai.log_entry(
            scope="scoped", kind="drift", target=target, agent="tooling-engineer",
            description=(f"{r['file']}: {r['count']} LLM call site(s) not fed by the prompt registry "
                         f"(baseline {r['allowed']}). Use noctusai_lib.integrations.prompt_registry "
                         f"(chamar_ia / prompt_e_modelo). {PATTERN_DOC}"),
            resolve_when=f"llm_prompt_registry_clean:{r['file']}", source_ref="check_llm_prompt_from_registry",
        )
        (logged if out.get("ok") else errors).append(r["file"] if out.get("ok") else f"{r['file']}: {out.get('error')}")
    return {"logged": logged, "errors": errors}
