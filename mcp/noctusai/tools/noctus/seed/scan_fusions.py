"""``noctus.seed.scan_fusions`` — detect MCP-tool fusion opportunities.

Scans every tool registered under ``mcp/noctusai/tools/noctus/**/*.py``
and surfaces pairs where a unifying rollup tool would unlock leverage —
the same shape that motivated ``noctus.seed.report`` (which fused
``scan_repetition`` + ``audit_drift``).

Signals scored per pair:

- **namespace_prefix** — both tools share a 3-segment prefix (e.g. both
  ``noctus.dev.*``). Cross-namespace fusions are rare and usually wrong.
- **param_overlap** — Jaccard of input parameter names. High overlap
  means callers feed the same arguments — a rollup call site eliminates
  duplication.
- **return_keys_overlap** — Jaccard of top-level keys parsed from each
  tool's docstring ``Returns:`` block. High overlap means findings are
  keyed by the same domain entity (slug, rel_path, phase_id, …) and can
  be cross-referenced row-by-row.
- **description_noun_overlap** — count of shared content nouns in the
  ``description=`` blurb (stopwords filtered). Confirms domain overlap
  beyond the structural signals.

A weighted sum of the four becomes ``score`` ∈ [0.0, 1.0]. Only pairs
above ``min_score`` surface, ranked desc. The mutation tool implied by
this scan is **build a `noctus.<ns>.<rollup>` tool composing the pair**
— same role ``absorb_file`` plays for ``scan_repetition``.

Read-only; no files written. The agent uses the output as a triage
queue for "what rollup tool should I build next?".
"""

from __future__ import annotations

import ast
import logging
import re
from itertools import combinations
from pathlib import Path

from settings import REPO_ROOT

logger = logging.getLogger(__name__)


# Stopword list for description-noun overlap. Curated to drop generic
# verbs / connectives without dropping domain nouns. Lowercased.
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "and", "any", "are", "as", "at", "be", "based", "but", "by",
    "call", "called", "can", "context", "data", "default", "do", "does", "each",
    "every", "for", "from", "get", "given", "has", "have", "i", "if", "in",
    "into", "is", "it", "its", "just", "list", "lists", "long", "made", "make",
    "may", "more", "must", "no", "non", "not", "of", "on", "one", "only", "or",
    "out", "over", "per", "pure", "raw", "read", "result", "results", "return",
    "returns", "run", "runs", "set", "sets", "so", "than", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "those", "to", "tool",
    "tools", "two", "up", "use", "used", "uses", "via", "want", "was", "we",
    "what", "when", "where", "which", "while", "will", "with", "without", "yet",
    "you", "all", "also", "always", "before", "after", "into", "through",
    "based", "shape", "shapes", "kind", "kinds", "way", "ways", "field", "fields",
    "value", "values", "key", "keys", "row", "rows", "block", "blocks", "info",
    "string", "int", "bool", "true", "false", "none", "name", "names", "type",
    "types", "args", "arg", "arguments", "argument", "param", "params", "parameter",
    "parameters", "kwarg", "kwargs",
})

_RETURNS_BLOCK_RE = re.compile(
    r"Returns?:?\s*\n(.*?)(?:\n\n|\n\s{0,4}(?:Args|Raises|Note|Example|Yields):|\Z)",
    re.DOTALL,
)

# Verb forms that signal a mutation tool. Word-boundary matched with
# case-insensitive flag — bare nouns like "absorption" / "modification"
# don't trip this. Edit cautiously: each addition risks a false-positive
# that hides a legitimate fusion candidate.
_MUTATION_VERB_RE = re.compile(
    r"\b("
    r"writes|writing|modifies|modifying|applies|applying|"
    r"moves|moving|deletes|deleting|removes|removing|"
    r"registers|registering|creates|creating|updates|updating|"
    r"absorbs|absorbing|scaffolds|scaffolding|promotes|promoting|"
    r"archives|archiving|emits|emitting|inserts|inserting|"
    r"mutates|mutating|lift|lifts|lifting"
    r")\b",
    re.IGNORECASE,
)
# Match top-level dict keys in a Returns block: lines like `"slug": str,` or
# `"items": [...]`. We only want the literal-string keys at any indent.
_KEY_RE = re.compile(r'"([a-zA-Z_][a-zA-Z0-9_]*)"\s*:')

# Words that look like dict keys but are also Python kw / generic noise we
# want to exclude from "domain key" overlap. (Keys that don't reveal the
# domain — every tool returns "summary" or "error".)
_GENERIC_RETURN_KEYS: frozenset[str] = frozenset({
    "summary", "error", "ok", "status", "data", "result", "results", "count",
    "total", "details", "next_steps", "next_step",
})


class ToolMeta:
    """Lightweight container for one MCP tool's parsed metadata."""

    __slots__ = ("name", "namespace", "description", "params", "return_keys",
                 "description_nouns", "source_file", "is_read_only",
                 "module_imports", "impl_loc")

    def __init__(
        self, *,
        name: str,
        namespace: str,
        description: str,
        params: frozenset[str],
        return_keys: frozenset[str],
        description_nouns: frozenset[str],
        source_file: str,
        is_read_only: bool,
        module_imports: frozenset[str],
        impl_loc: int,
    ) -> None:
        self.name = name
        self.namespace = namespace
        self.description = description
        self.params = params
        self.return_keys = return_keys
        self.description_nouns = description_nouns
        self.source_file = source_file
        self.is_read_only = is_read_only
        self.module_imports = module_imports
        self.impl_loc = impl_loc

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "namespace": self.namespace,
            "description": self.description,
            "params": sorted(self.params),
            "return_keys": sorted(self.return_keys),
            "source_file": self.source_file,
            "is_read_only": self.is_read_only,
        }


# ─── Parsers ───────────────────────────────────────────────────────────────


def _string_value(node: ast.AST) -> str | None:
    """Resolve a Constant or implicitly-concatenated string-tuple. Returns
    None when the node isn't a literal string we can inline-resolve."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        # f-string — bail; the values aren't literal at parse time.
        return None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_value(node.left)
        right = _string_value(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.Tuple):
        # `("foo " "bar ")` parses as a Tuple of Constants — but FastMCP's
        # parenthesized concatenation is actually one Constant after Python
        # collapses it. Defensive fallback.
        parts: list[str] = []
        for elt in node.elts:
            v = _string_value(elt)
            if v is None:
                return None
            parts.append(v)
        return "".join(parts)
    return None


def _extract_returns_keys(docstring: str | None) -> frozenset[str]:
    """Pull top-level dict keys out of a docstring Returns: block."""
    if not docstring:
        return frozenset()
    match = _RETURNS_BLOCK_RE.search(docstring)
    if not match:
        return frozenset()
    block = match.group(1)
    keys = {k for k in _KEY_RE.findall(block) if k not in _GENERIC_RETURN_KEYS}
    return frozenset(keys)


def _extract_description_nouns(description: str) -> frozenset[str]:
    """Tokenize a tool description and keep content nouns."""
    # Lowercase + split on non-word; keep alpha-only tokens of length ≥ 4
    # (drops single letters + 3-letter prepositions; keeps "scan", "drift",
    # "product", "phase", etc.).
    tokens = re.findall(r"[A-Za-z][A-Za-z_]+", description.lower())
    return frozenset(
        t for t in tokens
        if len(t) >= 4 and t not in _STOPWORDS
    )


def _module_import_names(tree: ast.Module) -> set[str]:
    """Pull every imported module name + every from-import name out of a
    parsed module. Used to detect existing fusions (rollup tool already
    imports its components — pair shouldn't surface as a new opportunity).
    """
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name.split(".")[-1])
                out.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            out.add(mod.split(".")[-1])
            out.add(mod)
            for alias in node.names:
                out.add(alias.name)
    return out


def _impl_targets_from_body(func: ast.FunctionDef) -> list[str]:
    """Walk a decorated tool-shim function's body and pull the names of
    callables it delegates to. Lets us find the IMPLEMENTATION function's
    docstring (where the Returns: block usually lives)."""
    targets: list[str] = []
    for sub in ast.walk(func):
        if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Call):
            call = sub.value
            if isinstance(call.func, ast.Name):
                targets.append(call.func.id)
            elif isinstance(call.func, ast.Attribute):
                targets.append(call.func.attr)
    return targets


def _func_loc(node: ast.FunctionDef) -> int:
    """Return the line span of a FunctionDef. Used to estimate the LoC
    cost of merging two tools — the merge floor approximates max(a, b)
    + small glue."""
    if not node.body:
        return node.end_lineno - node.lineno + 1 if node.end_lineno else 1
    end = node.end_lineno or node.body[-1].lineno
    return max(end - node.lineno + 1, 1)


def _impl_loc_for_shim(
    shim: ast.FunctionDef, tree: ast.Module, impl_targets: list[str],
) -> int:
    """Best-effort LoC of the IMPLEMENTATION function the decorated shim
    delegates to. Falls back to the shim's own LoC when the impl can't
    be located in the same module (e.g. cross-module facade calls)."""
    if not impl_targets:
        return _func_loc(shim)
    impl_locs: list[int] = []
    for impl_name in impl_targets:
        for sibling in ast.walk(tree):
            if (
                isinstance(sibling, ast.FunctionDef)
                and sibling.name == impl_name
                and sibling is not shim
            ):
                impl_locs.append(_func_loc(sibling))
                break
    if not impl_locs:
        return _func_loc(shim)
    # Sum impl LoCs (multiple delegate calls are unusual but additive).
    return sum(impl_locs)


def _parse_tool_file(path: Path) -> list[ToolMeta]:
    """Parse one tool module. Return zero or more ToolMeta instances."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    module_imports = _module_import_names(tree)
    out: list[ToolMeta] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        # Look for @server.tool(name="...", description="...") decorators.
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            func = deco.func
            # Match `server.tool(...)` or `<anything>.tool(...)` shape.
            if not (isinstance(func, ast.Attribute) and func.attr == "tool"):
                continue
            kwargs: dict[str, str | None] = {}
            for kw in deco.keywords:
                if kw.arg in {"name", "description"}:
                    kwargs[kw.arg] = _string_value(kw.value)
            tool_name = kwargs.get("name") or ""
            description = kwargs.get("description") or ""
            if not tool_name:
                continue

            # Pull params from the decorated function (skip `self`).
            params = frozenset(
                a.arg for a in node.args.args if a.arg not in {"self"}
            )

            # The decorated function is a thin shim that calls the real
            # implementation. The Returns: block typically lives on the
            # IMPLEMENTATION function in the same module — find it by
            # walking the decorated body for the `return <impl>(...)` call.
            impl_names = _impl_targets_from_body(node)
            return_keys = _extract_returns_keys(ast.get_docstring(node))
            if not return_keys:
                for impl_name in impl_names:
                    for sibling in ast.walk(tree):
                        if (
                            isinstance(sibling, ast.FunctionDef)
                            and sibling.name == impl_name
                            and sibling is not node
                        ):
                            return_keys = _extract_returns_keys(
                                ast.get_docstring(sibling)
                            )
                            if return_keys:
                                break
                    if return_keys:
                        break

            # Compute LoC of the IMPL function (or fallback to shim) — used
            # for merge-cost / savings estimates downstream.
            impl_loc = _impl_loc_for_shim(node, tree, impl_names)

            description_nouns = _extract_description_nouns(description)

            # Heuristic: classify as mutation when the description contains
            # any of the action-verb FORMS below as a standalone word (word
            # boundaries). Bare nouns like "absorption" / "modification"
            # don't trip this. Tilts conservative — false-positive only
            # over-surfaces a pair, doesn't break anything.
            is_read_only = not _MUTATION_VERB_RE.search(description)

            namespace = ".".join(tool_name.split(".")[:2])  # "noctus.dev"

            out.append(ToolMeta(
                name=tool_name,
                namespace=namespace,
                description=description,
                params=params,
                return_keys=return_keys,
                description_nouns=description_nouns,
                source_file=str(path),
                is_read_only=is_read_only,
                module_imports=frozenset(module_imports),
                impl_loc=impl_loc,
            ))

    return out


def _walk_tool_files(tools_dir: Path) -> list[Path]:
    """Yield every tool .py file under ``tools_dir`` (skipping __init__ +
    private helpers prefixed with ``_``)."""
    if not tools_dir.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(tools_dir.rglob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        out.append(path)
    return out


# ─── Scoring ───────────────────────────────────────────────────────────────


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _score_pair(a: ToolMeta, b: ToolMeta) -> tuple[float, dict]:
    """Score a fusion candidate pair. Returns (score, signals_dict).

    The signal blend weights return-key overlap with BOTH Jaccard (penalises
    breadth-mismatch) AND a saturation curve on absolute count (rewards
    tools that share ≥3 keys regardless of breadth — the canonical
    `scan_repetition` + `audit_drift` shape). Same hybrid for noun overlap.
    """
    same_namespace = a.namespace == b.namespace
    param_overlap = _jaccard(a.params, b.params)

    return_key_jaccard = _jaccard(a.return_keys, b.return_keys)
    return_key_count = len(a.return_keys & b.return_keys)
    # Saturation: 1 shared key = 0.33, 3+ keys = 1.0.
    return_key_saturation = min(return_key_count / 3.0, 1.0)
    return_key_signal = max(return_key_jaccard, return_key_saturation)

    noun_overlap_count = len(a.description_nouns & b.description_nouns)
    noun_jaccard = _jaccard(a.description_nouns, b.description_nouns)
    noun_saturation = min(noun_overlap_count / 4.0, 1.0)
    noun_signal = max(noun_jaccard, noun_saturation)

    # Weighted sum. Return-key overlap is the strongest structural signal
    # (matches the canonical-fusion mental model from `noctus.seed.report`).
    score = (
        (0.20 if same_namespace else 0.0)
        + 0.20 * param_overlap
        + 0.35 * return_key_signal
        + 0.25 * noun_signal
    )

    signals = {
        "same_namespace": same_namespace,
        "param_overlap": round(param_overlap, 3),
        "param_intersection": sorted(a.params & b.params),
        "return_keys_jaccard": round(return_key_jaccard, 3),
        "return_keys_count": return_key_count,
        "return_keys_intersection": sorted(a.return_keys & b.return_keys),
        "description_noun_overlap_count": noun_overlap_count,
        "description_nouns_intersection": sorted(a.description_nouns & b.description_nouns),
        "both_read_only": a.is_read_only and b.is_read_only,
    }
    return score, signals


def _build_rationale(a: ToolMeta, b: ToolMeta, signals: dict) -> str:
    """Plain-English explanation of why this pair is a fusion candidate."""
    pieces: list[str] = []
    keys = signals["return_keys_intersection"][:3]
    if keys:
        pieces.append(
            f"Both return findings keyed by {', '.join(repr(k) for k in keys)} "
            "→ findings can be cross-referenced row-by-row."
        )
    if signals["param_intersection"]:
        params = signals["param_intersection"][:3]
        pieces.append(
            f"Both take {', '.join(repr(p) for p in params)} → callers feed "
            "the same arguments; rollup eliminates duplication."
        )
    if signals["description_nouns_intersection"]:
        nouns = signals["description_nouns_intersection"][:5]
        pieces.append(
            f"Shared domain vocabulary: {', '.join(nouns)}."
        )
    if not signals["both_read_only"]:
        pieces.append(
            "WARNING: at least one tool appears to be a mutation — read-only "
            "rollups fuse cleanest; verify before composing."
        )
    if not pieces:
        return "Weak signals — only cross-cutting structural similarity."
    return " ".join(pieces)


# ─── Public API ────────────────────────────────────────────────────────────


_DEFAULT_TOOLS_DIR = REPO_ROOT / "mcp" / "noctusai" / "tools" / "noctus"


_VALID_SCOPES: frozenset[str] = frozenset({"cross_file", "same_file", "all"})


def _estimate_loc_savings(a: ToolMeta, b: ToolMeta, score: float) -> dict:
    """Heuristic LoC-savings estimate if the pair were merged.

    Calibrated against the 2026-05-10 in-place collapse pass: an
    optimistic ``min(a, b) × 0.6`` heuristic overstated real savings by
    ~12×. Real merges add mode-dispatch + validation + extended
    parameter signatures + longer descriptions, which eat the
    theoretical savings. Conservative replacement:

    - **subsume** (same-file or score ≥ 0.6, AND ≥3 tools in cluster):
      ``savings ≈ min(a, b) × 0.15`` per pair. Caller should aggregate
      per-cluster, not naively sum per-pair.
    - **subsume** (N=2 collapse): ``savings ≈ 0`` — usually
      net-neutral after mode-dispatch overhead (sometimes negative).
    - **compose** (cross-file): ``savings = 0`` — rollup adds glue.

    Returns ``{merge_kind, estimated_savings_loc, merge_floor_loc,
    a_impl_loc, b_impl_loc, rationale}``.
    """
    a_loc = a.impl_loc
    b_loc = b.impl_loc
    same_file = a.source_file == b.source_file

    if same_file or score >= 0.6:
        # Subsumption regime — but be honest about the merge-floor cost.
        # See `feedback_tool_collapse_loc_lesson.md` for the calibration.
        savings = int(min(a_loc, b_loc) * 0.15)
        floor = max(a_loc, b_loc) + 18  # mode dispatch + validation + descr
        kind = "subsume"
        rationale = (
            f"Subsume regime: same_file={same_file}, score≥0.6={score >= 0.6}. "
            f"CONSERVATIVE estimate (calibrated 2026-05-10): savings ≈ "
            f"min({a_loc}, {b_loc}) × 0.15 = {savings} LoC. Mode dispatch "
            f"+ validation eat most of the theoretical savings. Per-pair "
            "estimate; aggregate per-cluster, not naively per-pair."
        )
    else:
        savings = 0
        floor = 30  # Typical rollup glue body.
        kind = "compose"
        rationale = (
            "Compose regime: cross-file with weak structural overlap. "
            "Rollup ADDS ~30 LoC of glue; components stay; LoC savings "
            "= 0. Win is at the agent call-site (fewer round-trips), "
            "not in toolkit code."
        )

    return {
        "merge_kind": kind,
        "estimated_savings_loc": savings,
        "merge_floor_loc": floor,
        "a_impl_loc": a_loc,
        "b_impl_loc": b_loc,
        "rationale": rationale,
    }


def scan_fusions(
    *,
    tools_dir: Path | None = None,
    min_score: float = 0.30,
    max_pairs: int = 30,
    namespace_filter: str | None = None,
    require_both_read_only: bool = True,
    scope: str = "cross_file",
) -> dict:
    """Detect MCP-tool fusion opportunities by static analysis.

    Args:
        tools_dir: Override (test seam). Defaults to
            ``REPO_ROOT/mcp/noctusai/tools/noctus``.
        min_score: Pair score threshold (0.0–1.0). Default 0.30 surfaces
            the strong candidates without too much noise.
        max_pairs: Cap on returned pairs. Default 30.
        namespace_filter: Optional 2-segment prefix (e.g. ``"noctus.dev"``)
            to restrict pairs to a single namespace. None = all.
        require_both_read_only: When True (default), only surface pairs
            where BOTH tools are read-only. Set False to also include
            read+mutation pairs (e.g. ``scan_repetition`` + ``absorb_file``,
            which are companions even though one mutates).

    Returns:
        ``{
          "scanned_files": int,
          "tools_indexed": int,
          "pairs": [
            {
              "tool_a": str,
              "tool_b": str,
              "score": float,            # 0.0–1.0
              "signals": {...},
              "rationale": str,
              "suggested_rollup_name": str,
              "both_read_only": bool,
            },
            ...
          ],
          "summary": {
            "pairs_above_threshold": int,
            "pairs_returned": int,
            "namespace_filter": str | None,
            "score_distribution": {           # bucket -> count
              "0.30-0.40": int, "0.40-0.50": int, ...
            },
          },
        }``
    """
    base = tools_dir if tools_dir is not None else _DEFAULT_TOOLS_DIR
    files = _walk_tool_files(base)

    tools: list[ToolMeta] = []
    for f in files:
        tools.extend(_parse_tool_file(f))

    if namespace_filter:
        tools = [t for t in tools if t.namespace == namespace_filter]

    # Pre-index every (a_module, b_module) pair that's jointly imported by
    # some third tool. Lets us filter pairs where a rollup tool ALREADY
    # composes them (e.g. `report.py` imports both `scan_repetition` and
    # `audit_drift` — that pair is a completed fusion, not an opportunity).
    jointly_consumed: set[frozenset[str]] = set()
    for tool in tools:
        # Tool's own imports include all the components it composes.
        # Tool-module names live under `tools.noctus.<ns>.<file>` so we
        # match by the bare file stem.
        own_stem = Path(tool.source_file).stem
        candidate_components = {
            imp for imp in tool.module_imports
            if imp != own_stem  # don't pair tool with its own stem
        }
        if len(candidate_components) >= 2:
            for x, y in combinations(sorted(candidate_components), 2):
                jointly_consumed.add(frozenset({x, y}))

    if scope not in _VALID_SCOPES:
        return {
            "scanned_files": len(files),
            "tools_indexed": len(tools),
            "pairs": [],
            "summary": {
                "pairs_above_threshold": 0,
                "pairs_returned": 0,
                "namespace_filter": namespace_filter,
                "scope": scope,
                "existing_fusions_skipped": 0,
                "score_distribution": {},
                "error": f"invalid scope {scope!r}; valid: {sorted(_VALID_SCOPES)}",
            },
        }

    pairs_out: list[dict] = []
    existing_fusions = 0
    out_of_scope = 0
    for a, b in combinations(tools, 2):
        if require_both_read_only and not (a.is_read_only and b.is_read_only):
            continue
        a_module = Path(a.source_file).stem
        b_module = Path(b.source_file).stem
        same_file = a.source_file == b.source_file
        # Scope gate: caller picks which axis of fusions to surface.
        if scope == "cross_file" and same_file:
            out_of_scope += 1
            continue
        if scope == "same_file" and not same_file:
            out_of_scope += 1
            continue
        # Filter 1: direct import (one tool imports the other's module).
        # Doesn't apply to same-file pairs (they share a module).
        if not same_file and (
            a_module in b.module_imports or b_module in a.module_imports
        ):
            existing_fusions += 1
            continue
        # Filter 2: jointly consumed by a third rollup tool (transitive).
        # Same-file pairs aren't filtered here — the rollup that consumes
        # them sits at a different altitude than the merge they could do.
        if not same_file and frozenset({a_module, b_module}) in jointly_consumed:
            existing_fusions += 1
            continue
        score, signals = _score_pair(a, b)
        if score < min_score:
            continue
        rationale = _build_rationale(a, b, signals)
        # Suggest a rollup name. Heuristic: same namespace → use the
        # shared prefix + a generic verb; different namespaces → "rollup".
        if a.namespace == b.namespace:
            suggested = f"{a.namespace}.<rollup_name>  # composes "\
                f"{a.name.split('.')[-1]} + {b.name.split('.')[-1]}"
        else:
            suggested = (
                f"<choose namespace>.<rollup_name>  # cross-namespace fusion: "
                f"{a.name} + {b.name}"
            )
        loc_estimate = _estimate_loc_savings(a, b, score)
        pairs_out.append({
            "tool_a": a.name,
            "tool_b": b.name,
            "score": round(score, 3),
            "signals": signals,
            "rationale": rationale,
            "suggested_rollup_name": suggested,
            "both_read_only": a.is_read_only and b.is_read_only,
            "same_file": same_file,
            "loc_estimate": loc_estimate,
        })

    pairs_out.sort(key=lambda p: -p["score"])
    pairs_above_threshold = len(pairs_out)
    if max_pairs > 0:
        pairs_out = pairs_out[:max_pairs]

    # Build score distribution histogram.
    buckets: dict[str, int] = {}
    for p in pairs_out:
        s = p["score"]
        lo = int(s * 10) / 10
        key = f"{lo:.2f}-{lo + 0.1:.2f}"
        buckets[key] = buckets.get(key, 0) + 1

    return {
        "scanned_files": len(files),
        "tools_indexed": len(tools),
        "pairs": pairs_out,
        "summary": {
            "pairs_above_threshold": pairs_above_threshold,
            "pairs_returned": len(pairs_out),
            "namespace_filter": namespace_filter,
            "scope": scope,
            "existing_fusions_skipped": existing_fusions,
            "out_of_scope_pairs_skipped": out_of_scope,
            "estimated_savings_loc_total": sum(
                p["loc_estimate"]["estimated_savings_loc"] for p in pairs_out
            ),
            "subsume_candidates_count": sum(
                1 for p in pairs_out
                if p["loc_estimate"]["merge_kind"] == "subsume"
            ),
            "compose_candidates_count": sum(
                1 for p in pairs_out
                if p["loc_estimate"]["merge_kind"] == "compose"
            ),
            "score_distribution": buckets,
        },
    }


def register(server) -> None:
    @server.tool(
        name="noctus.seed.scan_fusions",
        description=(
            "Detect MCP-tool fusion opportunities — pairs of tools where "
            "a unifying rollup tool would unlock leverage (the shape that "
            "motivated `noctus.seed.report` fusing `scan_repetition` + "
            "`audit_drift`). Scores by namespace co-prefix, parameter "
            "overlap, return-key overlap (Jaccard), and description-noun "
            "overlap. Two regimes per pair: COMPOSE (cross-file rollup "
            "that adds glue without removing components → LoC savings = 0; "
            "win is at agent call-site) vs SUBSUME (same-file or strong "
            "overlap → merge into one parameterized tool; LoC savings ≈ "
            "min(a, b) × 0.6). `scope` switches detection axis: "
            "'cross_file' (default), 'same_file' (intra-file merge "
            "candidates), or 'all'. Read-only."
        ),
    )
    def _scan_fusions(
        min_score: float = 0.30,
        max_pairs: int = 30,
        namespace_filter: str | None = None,
        require_both_read_only: bool = True,
        scope: str = "cross_file",
    ) -> dict:
        return scan_fusions(
            min_score=min_score,
            max_pairs=max_pairs,
            namespace_filter=namespace_filter,
            require_both_read_only=require_both_read_only,
            scope=scope,
        )
