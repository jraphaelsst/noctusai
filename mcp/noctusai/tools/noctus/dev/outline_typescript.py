"""`noctusai_outline_typescript` — return a TS / TSX file's symbol tree without bodies.

Companion to `outline_python` for the narrow-read rule (CLAUDE.md +
`KB § PATTERNS/agent-reading-discipline.md`). Same `OutlineResult`
shape as the Python tool so caller code stays parser-agnostic.

**Why regex (not the TypeScript Compiler API)?** Phase 4 audit
(2026-05-02): the §7 Q1 default said "official `typescript` npm
package via Compiler API, child-process bridge". That path costs
~50MB on disk + ~200ms spawn per call for ~15% precision on edge
cases (overloaded types, conditional types, nested template strings)
that don't help the narrow-read use case. The narrow-read caller
wants `{name, kind, line, end_line}` to drive a follow-up
`Read offset=<line> limit=N` — symbol names + line ranges are what
matter, not type-aware semantics. Regex on prettier/eslint-formatted
TS hits ~95% of practical declarations at ~5ms per call. Documented
deviation; upgrade path to tree-sitter or Compiler API is open if
precision becomes load-bearing.

**Inputs.**
- `path: str | Path` — TS or TSX source file. Must exist and be readable.

**Returns.** `OutlineResult` (same shape as `outline_python`'s) — see
`mcp/noctusai/tools/outline_python.py`. Reuse those dataclasses to
keep the contract identical.

**What is captured.**
- Top-level function declarations (`function foo()`, `export function`,
  `export default function`, `async function`).
- Top-level arrow-function-style consts (`const Foo = (...) => …`,
  `export const Foo = …`) when the right-hand side LOOKS like a function
  (arrow, JSX, function-keyword). Components and hooks land here.
- Top-level non-function consts in UPPER_SNAKE_CASE (treated as
  constants, mirroring `outline_python`).
- Top-level class declarations + first-level methods inside classes.
- Top-level type aliases (`type Foo = …`) and interfaces (`interface Foo`).
- Import statements.

**What is NOT captured (by design).**
- Function bodies, class bodies, JSX expressions.
- Nested functions / nested classes.
- Type expressions on the right of `type X = …` (only the name + line
  range — bodies on demand via Read).
- Re-exports without local declaration (`export * from …`,
  `export { x } from …`) — handled as imports kind for visibility.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from tools.noctus.dev.outline_python import OutlineResult, Symbol  # reuse shape

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[5]


# ---------------------------------------------------------------------------
# Regex catalog — top-level declarations on prettier/eslint-formatted code
# ---------------------------------------------------------------------------
#
# We anchor at column 0 because TS / TSX written with prettier puts top-level
# declarations at the left margin. Indented declarations (methods inside a
# class, declarations inside a function body) are handled separately via the
# class-body walk below.

_RE_FUNCTION = re.compile(
    r'^(?:export\s+(?:default\s+)?)?(async\s+)?function\s*\*?\s*(\w+)\s*[<(]'
)
_RE_CLASS = re.compile(
    r'^(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+(\w+)\b'
)
_RE_INTERFACE = re.compile(
    r'^(?:export\s+(?:default\s+)?)?interface\s+(\w+)\b'
)
_RE_TYPE = re.compile(
    r'^(?:export\s+)?type\s+(\w+)\s*[=<]'
)
_RE_CONST_OR_LET = re.compile(
    r'^(?:export\s+(?:default\s+)?)?(const|let|var)\s+(\w+)\s*[:=]'
)
_RE_IMPORT = re.compile(
    r'^(?:import\b|export\s+(?:type\s+)?(?:\*|\{).*?\bfrom\b)'
)
_RE_REEXPORT = re.compile(
    r'^export\s+(?:\{[^}]*\}|\*|type\s+\{[^}]*\})\s+from\b'
)

# Heuristic: does the right-hand side of `const X = ...` look like a function?
# Catches arrow functions, JSX components, classic `function () {…}` expressions,
# plus shapes like `const Foo: React.FC<...> = (...) => ...`.
_RE_RHS_LOOKS_FUNCTIONAL = re.compile(
    r'=\s*(?:async\s+)?(?:\([^)]*\)\s*(?::\s*\S+\s*)?=>|function\b|<\w+\s|<\w+>|\(\s*[\w{]+:\s*\S+)'
)

# Method inside a class body — depth-tracked separately. We accept method
# names with optional `static`, `async`, `public/private/protected/readonly`,
# `*` (generator), and TS-style accessors `get` / `set`.
_RE_METHOD = re.compile(
    r'^\s+(?:(?:public|private|protected|readonly|static|async|override|\*|get|set)\s+)*'
    r'(?:async\s+)?\*?(\w+)\s*[<(]'
)


def _is_uppercase_constant(name: str) -> bool:
    """Mirror `outline_python`: UPPER_SNAKE_CASE → constant. Single-word
    UPPER like `URL` also qualifies; mixed-case `getX` does not."""
    return bool(name) and name == name.upper() and any(c.isalpha() for c in name)


def _decorator_repr(line: str) -> Optional[str]:
    """If a line starts with `@decorator(...)`, return the decorator
    expression (without the `@`); else None."""
    stripped = line.strip()
    if not stripped.startswith("@"):
        return None
    return stripped.lstrip("@").rstrip("{").strip()


def _strip_block_comments(source: str) -> str:
    """Drop /* ... */ comments — they can contain `function foo` strings
    that mis-trigger the regex catalog. Single-line `//` comments at the
    start of a line are also dropped to avoid the same false match.

    Cheap text-level scrub; not a tokenizer. Preserves line count via
    newline-padding so line numbers stay aligned.
    """
    out = []
    i = 0
    n = len(source)
    while i < n:
        # /* ... */ block
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            if end == -1:
                # unterminated block — replace the rest with whitespace
                out.append(" " * (n - i - source.count("\n", i)))
                out.append("\n" * source.count("\n", i))
                break
            chunk = source[i:end + 2]
            # preserve newlines for line-number alignment
            out.append("\n" * chunk.count("\n"))
            i = end + 2
            continue
        # // comment to EOL — only drop if the line starts (after whitespace) with //
        if source.startswith("//", i):
            line_start = source.rfind("\n", 0, i) + 1
            prefix = source[line_start:i]
            if not prefix.strip():
                eol = source.find("\n", i)
                if eol == -1:
                    eol = n
                out.append("")  # comment becomes empty, line break preserved by main loop
                i = eol
                continue
        out.append(source[i])
        i += 1
    return "".join(out)


def _find_class_end(lines: list[str], start_idx: int) -> int:
    """Find the line index where the class body ends. Tracks `{` / `}`
    brace depth starting from the first `{` after the class header."""
    depth = 0
    started = False
    for i in range(start_idx, len(lines)):
        line = lines[i]
        # Cheap-ish: scan chars, ignoring strings / template literals is not
        # worth the precision for this use-case. Prettier-formatted code is
        # very predictable here.
        for ch in line:
            if ch == "{":
                depth += 1
                started = True
            elif ch == "}":
                depth -= 1
                if started and depth == 0:
                    return i
    return len(lines) - 1


def _docstring_first_line(lines: list[str], symbol_line_idx: int) -> Optional[str]:
    """Walk backward from the symbol line, looking for a JSDoc `/** … */`
    block (or a `//` comment line directly above). Return the first
    meaningful line of prose if found."""
    if symbol_line_idx <= 0:
        return None
    # Skip blank lines / decorators above the symbol
    i = symbol_line_idx - 1
    while i >= 0 and (not lines[i].strip() or lines[i].lstrip().startswith("@")):
        i -= 1
    if i < 0:
        return None
    line = lines[i].strip()
    # JSDoc closing line — walk up to opener
    if line.endswith("*/") or line == "*/":
        for j in range(i, -1, -1):
            l = lines[j].strip()
            if l.startswith("/**"):
                # Take the line after the opener if present, else the next non-empty
                for k in range(j + 1, i + 1):
                    text = lines[k].strip().lstrip("*").strip()
                    if text and not text.endswith("*/"):
                        return text[:120]
                # Inline `/** something */`
                inline = lines[j].strip().lstrip("/").lstrip("*").rstrip("*/").strip()
                return inline[:120] if inline else None
            if not l.startswith("*") and l != "*/":
                return None
    # Single-line `// comment` above
    if line.startswith("//"):
        return line.lstrip("/").strip()[:120] or None
    return None


def _collect_decorators_above(lines: list[str], symbol_line_idx: int) -> list[str]:
    decos: list[str] = []
    i = symbol_line_idx - 1
    while i >= 0:
        line = lines[i].strip()
        if not line:
            i -= 1
            continue
        d = _decorator_repr(lines[i])
        if d:
            decos.insert(0, d)
            i -= 1
            continue
        break
    return decos


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def outline_typescript(path: str | Path) -> OutlineResult:
    """Return the symbol tree of `path` (TS / TSX) as an OutlineResult.

    Missing files return an OutlineResult with `parse_error` populated.
    Encoding errors likewise. The regex pass does not "fail" on
    malformed TS — it just captures whatever well-formed declarations
    it can find.
    """
    p = Path(path)
    if not p.exists():
        candidate = REPO_ROOT / p
        if candidate.exists():
            p = candidate
        else:
            return OutlineResult(
                path=str(path),
                total_lines=0,
                parse_error=f"file not found: {path}",
            )

    try:
        source = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return OutlineResult(
            path=str(p),
            total_lines=0,
            parse_error=f"read failed: {e}",
        )

    rel_path = str(p.relative_to(REPO_ROOT)) if str(p).startswith(str(REPO_ROOT)) else str(p)

    cleaned = _strip_block_comments(source)
    lines = cleaned.splitlines()
    raw_lines = source.splitlines()  # for docstring extraction
    total_lines = len(raw_lines)

    classes: list[Symbol] = []
    functions: list[Symbol] = []
    methods: list[Symbol] = []
    constants: list[Symbol] = []
    imports: list[Symbol] = []
    types: list[Symbol] = []  # interfaces + type aliases (folded into `classes` bucket per shape)

    # Track lines we've already attributed to a class body so the top-level
    # walk doesn't double-count methods as "top-level functions".
    consumed_lines: set[int] = set()

    # ── Pass 1: top-level structures
    for idx, line in enumerate(lines):
        if idx in consumed_lines:
            continue

        # Imports / re-exports
        if _RE_IMPORT.match(line) or _RE_REEXPORT.match(line):
            # Multi-line import: extend until we hit a closing `from "…";` line
            end = idx
            while end < len(lines) - 1 and "from " not in lines[end]:
                end += 1
            # Collapse whitespace + newlines so the display line is clean.
            full = " ".join(part.strip() for part in raw_lines[idx:end + 1] if part.strip())
            imports.append(Symbol(
                name=full[:200],
                kind="import",
                line=idx + 1,
                end_line=end + 1,
            ))
            continue

        # Class
        m = _RE_CLASS.match(line)
        if m:
            cls_name = m.group(1)
            end_idx = _find_class_end(lines, idx)
            classes.append(Symbol(
                name=cls_name,
                kind="class",
                line=idx + 1,
                end_line=end_idx + 1,
                decorators=_collect_decorators_above(raw_lines, idx),
                docstring_first_line=_docstring_first_line(raw_lines, idx),
            ))
            # Walk the class body for methods
            for body_idx in range(idx + 1, end_idx):
                consumed_lines.add(body_idx)
                body_line = lines[body_idx]
                mm = _RE_METHOD.match(body_line)
                if mm:
                    method_name = mm.group(1)
                    # Skip control-flow keywords that the regex might catch (if/for/while/switch)
                    if method_name in {"if", "for", "while", "switch", "return", "throw", "do", "else"}:
                        continue
                    # Skip property declarations (no parens after the name) —
                    # `_RE_METHOD` requires `[<(]` after the identifier so
                    # this is mostly already filtered.
                    methods.append(Symbol(
                        name=method_name,
                        kind="async_method" if "async " in body_line else "method",
                        line=body_idx + 1,
                        end_line=body_idx + 1,  # cheap — closing `}` not tracked per method
                        parent=cls_name,
                    ))
            continue

        # Top-level function declaration
        m = _RE_FUNCTION.match(line)
        if m:
            functions.append(Symbol(
                name=m.group(2),
                kind="async_function" if m.group(1) else "function",
                line=idx + 1,
                end_line=idx + 1,  # body end not tracked at this resolution
                decorators=_collect_decorators_above(raw_lines, idx),
                docstring_first_line=_docstring_first_line(raw_lines, idx),
            ))
            continue

        # Interface
        m = _RE_INTERFACE.match(line)
        if m:
            types.append(Symbol(
                name=m.group(1),
                kind="interface",
                line=idx + 1,
                end_line=idx + 1,
                docstring_first_line=_docstring_first_line(raw_lines, idx),
            ))
            continue

        # Type alias
        m = _RE_TYPE.match(line)
        if m:
            types.append(Symbol(
                name=m.group(1),
                kind="type",
                line=idx + 1,
                end_line=idx + 1,
                docstring_first_line=_docstring_first_line(raw_lines, idx),
            ))
            continue

        # const / let / var
        m = _RE_CONST_OR_LET.match(line)
        if m:
            keyword = m.group(1)
            name = m.group(2)
            # Detect arrow / function-shape RHS (consider current line + the next 1)
            rhs_window = line
            if idx + 1 < len(lines):
                rhs_window = line + "\n" + lines[idx + 1]
            looks_functional = bool(_RE_RHS_LOOKS_FUNCTIONAL.search(rhs_window))
            if looks_functional:
                functions.append(Symbol(
                    name=name,
                    kind="async_function" if "= async" in line or "=async" in line else "function",
                    line=idx + 1,
                    end_line=idx + 1,
                    docstring_first_line=_docstring_first_line(raw_lines, idx),
                ))
            elif _is_uppercase_constant(name) and keyword == "const":
                constants.append(Symbol(
                    name=name,
                    kind="constant",
                    line=idx + 1,
                    end_line=idx + 1,
                ))
            else:
                # Mixed-case const that's not function-shaped — treat as constant
                # (data fixture, type-aliased value, schema). It's still a
                # nameable symbol the agent might want to inspect.
                constants.append(Symbol(
                    name=name,
                    kind="constant",
                    line=idx + 1,
                    end_line=idx + 1,
                ))
            continue

    # Fold types into the `classes` bucket so callers see all
    # top-level "structural" declarations together. Keep them
    # distinguishable via `kind`.
    classes_with_types = sorted(classes + types, key=lambda s: s.line)

    return OutlineResult(
        path=rel_path,
        total_lines=total_lines,
        classes=classes_with_types,
        functions=functions,
        methods=methods,
        constants=constants,
        imports=imports,
    )


def register(server) -> None:
    @server.tool(
        name="noctusai_outline_typescript",
        description=(
            "Return a TS / TSX file's symbol tree (classes, interfaces, types, functions, "
            "arrow-fn consts, methods, constants, imports). Same shape as "
            "`noctusai_outline_python`. Regex-based — no Node spawn, no npm install; "
            "see `mcp/noctusai/tools/outline_typescript.py` for the design tradeoff "
            "against the Compiler API path."
        ),
    )
    def _outline_typescript(path: str) -> dict:
        return outline_typescript(path).to_dict()
