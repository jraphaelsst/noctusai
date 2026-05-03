"""`noctusai_outline_python` — return a Python file's symbol tree without bodies.

The narrow-read rule (CLAUDE.md + `KB § PATTERNS/agent-reading-discipline.md`)
asks the agent to read structure before bodies. This tool makes that
ergonomic: one call returns every top-level class, function, method,
top-level constant, and import, with line ranges, so the agent can
decide which bodies to fetch without reading the file whole.

**Why stdlib `ast`.** Python ships it. The MCP toolkit already uses it
in `tools/{catalog,compliance,recurrence}.py`. No new dependency, no
parser drift, no install ritual.

**Inputs.**
- `path: str | Path` — Python source file. Must exist and be readable.
  Non-`.py` files are accepted but parsed as Python (caller's choice).

**Returns.** `OutlineResult` — see schema in the dataclasses below.
On parse failure, `parse_error` is populated with the SyntaxError
message + line; partial output (whatever AST could be obtained
before the error) is NOT returned to keep the contract simple.

**What is captured.**
- Module-level `class`, `def`, `async def` definitions (kind:
  `class` / `function` / `async_function`).
- Class methods (kind: `method` / `async_method`), with `parent`
  set to the enclosing class name.
- Module-level constant assignments where the target is a single
  Name in `UPPER_SNAKE_CASE` (kind: `constant`).
- `import …` and `from … import …` lines, rendered as the original
  source slice (kind: `import`).

**What is NOT captured (by design).**
- Function bodies, class bodies, expression bodies — the whole
  point is to leave them out.
- Nested functions / closures — they're rare and noisy; surface
  only top-level + first-level methods.
- Type aliases (`X = SomeType`) — captured as constants only when
  the target name is UPPER_SNAKE_CASE.

**Anti-pattern guard.** Don't use this tool to render the WHOLE
file's content. The point is the structure summary; if you need
bodies, follow up with a targeted `Read offset=<line> limit=N`.
"""
from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class Symbol:
    """One symbol in the outline. `kind` distinguishes class / function /
    method / constant / import. `line` and `end_line` are 1-indexed."""
    name: str
    kind: str  # "class" | "function" | "async_function" | "method" | "async_method" | "constant" | "import"
    line: int
    end_line: int
    parent: Optional[str] = None  # parent class name for methods
    decorators: list[str] = field(default_factory=list)
    docstring_first_line: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "kind": self.kind,
            "line": self.line,
            "end_line": self.end_line,
        }
        if self.parent:
            d["parent"] = self.parent
        if self.decorators:
            d["decorators"] = self.decorators
        if self.docstring_first_line:
            d["docstring_first_line"] = self.docstring_first_line
        return d


@dataclass
class OutlineResult:
    """Outline of one Python file (or TS / TSX file via `outline_typescript`,
    which reuses this dataclass).

    Versioning
    ----------
    `schema_version` is the contract version of this dataclass + its
    `to_dict()` payload. Bumped ONLY on backward-INCOMPATIBLE shape
    changes:

    - **Major bump (1 → 2):** removing a field, renaming a field,
      changing a field's type, or changing the semantics of a field.
      Downstream MCP host consumers built against the old shape will
      break.
    - **No bump (1.x = 1):** adding a new field with a sensible
      default, adding a new `Symbol.kind` value, adding a new method.
      Downstream consumers that ignore unknown fields keep working.

    MCP host consumers should accept any `schema_version == 1`.
    A `schema_version == 2` payload requires explicit migration.
    """
    path: str
    total_lines: int
    schema_version: int = 1
    parse_error: Optional[str] = None
    classes: list[Symbol] = field(default_factory=list)
    functions: list[Symbol] = field(default_factory=list)
    methods: list[Symbol] = field(default_factory=list)
    constants: list[Symbol] = field(default_factory=list)
    imports: list[Symbol] = field(default_factory=list)

    @property
    def symbol_count(self) -> int:
        return (
            len(self.classes)
            + len(self.functions)
            + len(self.methods)
            + len(self.constants)
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "path": self.path,
            "total_lines": self.total_lines,
            "parse_error": self.parse_error,
            "classes": [s.to_dict() for s in self.classes],
            "functions": [s.to_dict() for s in self.functions],
            "methods": [s.to_dict() for s in self.methods],
            "constants": [s.to_dict() for s in self.constants],
            "imports": [s.to_dict() for s in self.imports],
            "symbol_count": self.symbol_count,
        }


# ---------------------------------------------------------------------------
# AST → Symbol helpers
# ---------------------------------------------------------------------------


def _decorator_repr(node: ast.expr) -> str:
    """Render a decorator AST as a short string (no bodies)."""
    try:
        return ast.unparse(node)
    except Exception:
        return ast.dump(node)[:60]


def _docstring_first_line(node: ast.AST) -> Optional[str]:
    if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    doc = ast.get_docstring(node)
    if not doc:
        return None
    first = doc.strip().split("\n", 1)[0].strip()
    return first or None


def _is_module_constant_target(node: ast.AST) -> Optional[str]:
    """Return the name if `node` is a module-level UPPER_SNAKE_CASE
    assignment target, else None."""
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id.isupper():
            return target.id
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id.isupper():
        return node.target.id
    return None


def _import_source_slice(node: ast.AST, source_lines: list[str]) -> str:
    """Render an Import / ImportFrom as its original source slice."""
    try:
        end_line = node.end_lineno or node.lineno
        slice_ = source_lines[node.lineno - 1:end_line]
        return "\n".join(slice_).strip()
    except (AttributeError, IndexError):
        try:
            return ast.unparse(node)
        except Exception:
            return ""


def _function_kind(node: ast.AST, *, is_method: bool) -> str:
    if isinstance(node, ast.AsyncFunctionDef):
        return "async_method" if is_method else "async_function"
    return "method" if is_method else "function"


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def outline_python(path: str | Path) -> OutlineResult:
    """Return the symbol tree of `path` as an OutlineResult.

    `path` may be relative; it's resolved against repo root if needed.
    Missing files return an empty result with `parse_error` populated.
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

    source_lines = source.splitlines()
    total_lines = len(source_lines)

    rel_path = str(p.relative_to(REPO_ROOT)) if str(p).startswith(str(REPO_ROOT)) else str(p)

    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError as e:
        return OutlineResult(
            path=rel_path,
            total_lines=total_lines,
            parse_error=f"SyntaxError at line {e.lineno}: {e.msg}",
        )

    classes: list[Symbol] = []
    functions: list[Symbol] = []
    methods: list[Symbol] = []
    constants: list[Symbol] = []
    imports: list[Symbol] = []

    for node in tree.body:
        # Module-level class
        if isinstance(node, ast.ClassDef):
            cls_sym = Symbol(
                name=node.name,
                kind="class",
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                decorators=[_decorator_repr(d) for d in node.decorator_list],
                docstring_first_line=_docstring_first_line(node),
            )
            classes.append(cls_sym)
            # First-level methods inside the class
            for body_node in node.body:
                if isinstance(body_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(Symbol(
                        name=body_node.name,
                        kind=_function_kind(body_node, is_method=True),
                        line=body_node.lineno,
                        end_line=body_node.end_lineno or body_node.lineno,
                        parent=node.name,
                        decorators=[_decorator_repr(d) for d in body_node.decorator_list],
                        docstring_first_line=_docstring_first_line(body_node),
                    ))

        # Module-level function (sync or async)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(Symbol(
                name=node.name,
                kind=_function_kind(node, is_method=False),
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                decorators=[_decorator_repr(d) for d in node.decorator_list],
                docstring_first_line=_docstring_first_line(node),
            ))

        # Imports
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append(Symbol(
                name=_import_source_slice(node, source_lines),
                kind="import",
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
            ))

        # Module-level constants (UPPER_SNAKE_CASE)
        else:
            const_name = _is_module_constant_target(node)
            if const_name:
                constants.append(Symbol(
                    name=const_name,
                    kind="constant",
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                ))

    return OutlineResult(
        path=rel_path,
        total_lines=total_lines,
        classes=classes,
        functions=functions,
        methods=methods,
        constants=constants,
        imports=imports,
    )


def register(server) -> None:
    @server.tool(
        name="noctusai_outline_python",
        description=(
            "Return a Python file's symbol tree (classes / functions / methods / "
            "constants / imports) without bodies. Makes the narrow-read rule ergonomic: "
            "structure first, fetch bodies on demand. Stdlib `ast`, no extra deps. "
            "Output includes line ranges for each symbol so a follow-up "
            "`Read offset=<line> limit=N` is one call away."
        ),
    )
    def _outline_python(path: str) -> dict:
        return outline_python(path).to_dict()
