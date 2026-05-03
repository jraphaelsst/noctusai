# AST-first Code Editing

> The toolchain and recipes for AST-driven code edits. Companion to `01-PHILOSOPHY.md § AST-first` (the rule); this file is the operational reference.

Every code change in this repo goes through an AST tool. Regex / sed is for prose, search, and log inspection — never for editing code. This file lists the tools, the recipes, the anti-patterns, and the boundary cases.

---

## Toolchain

### Python

- **`libcst`** — Concrete Syntax Tree (preserves formatting, comments, whitespace). The default for **all Python edits**. Provides `Visitor` and `Transformer` classes; codemods apply via `cst.MetadataWrapper`. Round-trips: `cst.parse_module(src).code == src` (modulo minor normalisations).
- **`ast`** (stdlib) — Pure abstract syntax tree, **read-only / analysis-only**. Use for find-callers, find-pattern, name-resolution. Loses formatting, so don't write it back.
- **`tree-sitter`** — Cross-language parser; useful when an analysis spans Python + TypeScript + SQL together. Read-only.

### TypeScript / JavaScript

- **`ts-morph`** — High-level wrapper around the TypeScript Compiler API. The default for **all TypeScript edits**. Preserves formatting via `Project#save()`. Provides scope-aware rename, find-references, and codemod APIs.
- **`@babel/parser` + `@babel/traverse`** — Lower-level parse / traverse for cases ts-morph doesn't cover (rare). Used by AST utilities when ts-morph's TypeScript-only API is insufficient.
- **`tree-sitter-typescript`** — Cross-language analysis (paired with the Python tree-sitter binding).

### Other

- **SQL** — `sqlglot` parses SQL across dialects; the keeper's migration-pattern scans use it. Editing migrations is rare (migrations are append-only); when needed, write a new migration file rather than mutate.
- **YAML / TOML** — `ruamel.yaml` and `tomlkit` preserve comments + structure. Use them rather than `yaml.safe_dump` (which strips comments).
- **Shell** — bash AST is uncommon; for repo edits use a templating approach (jinja or similar) rather than regex. Tests assert produced shape.

---

## Recipes

### Rename in scope (Python)

```python
import libcst as cst
from libcst.codemod import VisitorBasedCodemodCommand
from libcst.metadata import ScopeProvider

class RenameInScope(VisitorBasedCodemodCommand):
    METADATA_DEPENDENCIES = (ScopeProvider,)

    def __init__(self, context, old_name: str, new_name: str):
        super().__init__(context)
        self.old = old_name
        self.new = new_name

    def leave_Name(self, orig: cst.Name, updated: cst.Name) -> cst.Name:
        scope = self.get_metadata(ScopeProvider, orig, default=None)
        if scope and orig.value == self.old:
            return updated.with_changes(value=self.new)
        return updated
```

### Rename in scope (TypeScript)

```ts
import { Project } from "ts-morph";

const project = new Project({ tsConfigFilePath: "tsconfig.json" });
const symbol = project
  .getSourceFileOrThrow("src/foo.ts")
  .getVariableDeclarationOrThrow("oldName");
symbol.rename("newName");
project.saveSync();
```

### Find callers (Python — read-only)

```python
import ast

def find_callers(file_path: str, callee: str) -> list[tuple[int, str]]:
    tree = ast.parse(open(file_path).read())
    callers = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == callee):
            callers.append((node.lineno, ast.unparse(node)))
    return callers
```

For cross-file find-references, prefer `libcst` with `ScopeProvider` or `ts-morph`'s `getReferencingNodes()`.

### Find pattern (Python — read-only)

```python
import libcst as cst

class FindTryExceptPass(cst.CSTVisitor):
    def __init__(self):
        self.findings: list[tuple[int, str]] = []

    def visit_Try(self, node: cst.Try) -> None:
        for handler in node.handlers:
            if (isinstance(handler.body, cst.IndentedBlock)
                and len(handler.body.body) == 1
                and isinstance(handler.body.body[0], cst.SimpleStatementLine)
                and isinstance(handler.body.body[0].body[0], cst.Pass)):
                self.findings.append(
                    (handler.start_position.line,
                     cst.Module([]).code_for_node(node))
                )
```

This is the shape any future `check_silent_errors` keeper detector would use.

### Apply codemod (Python — across many files)

```python
from libcst.codemod import CodemodContext, parallel_exec_transform_with_prettyprint
from my_codemods import MyCodemod

context = CodemodContext()
files = list_python_files("products/foo")
parallel_exec_transform_with_prettyprint(
    MyCodemod, files=files, jobs=4, repo_root="...", context=context,
)
```

**Codemods must ship with regression tests** (per `PATTERNS/testing.md § Regression-test-the-detector`).

### Apply codemod (TypeScript — across many files)

```ts
import { Project } from "ts-morph";

const project = new Project({ tsConfigFilePath: "tsconfig.json" });
project.getSourceFiles().forEach(sf => {
  // mutation logic here — use sf.getDescendants(), sf.getClasses(), etc.
});
project.saveSync();
```

---

## Anti-patterns (the regex traps)

| Anti-pattern | What goes wrong |
|---|---|
| `sed -i 's/old_name/new_name/g'` across `.py` | Renames `old_name` inside docstrings, comments, string literals, unrelated identifiers (`old_name_2`, `do_old_name_thing`). Even with `\b` word boundaries, the inside-string / inside-comment hits remain. |
| Multi-line regex with `\n` | Whitespace variation (tabs vs. spaces, trailing whitespace, blank lines) breaks the match. |
| `grep ... \| xargs sed` for "fix the indentation" | Indentation is structural; sed doesn't know which line is inside which block. |
| AWK over Python source | Same as sed — no structure awareness. |
| Hand-edit then "find and replace" inside the editor for a multi-file change | Same trap as sed; just slower. The editor's "find in scope" is only language-aware when it's running an LSP — and LSP renaming IS an AST operation, just exposed differently. |
| `regex.sub(...)` to "fix imports across products" | Imports cross module boundaries; only AST tools resolve names correctly. |

---

## When regex IS the right tool

- **Search-only** — `grep` / `rg` for finding occurrences before deciding what to edit. The keeper's `noctusai_scan_*` recurrence scans use regex internally on string-line shape, intentionally.
- **Editing prose** — `*.md`, `README.md`, `CHANGELOG.md`. No syntactic structure to violate.
- **Inspecting log output** — `grep ERROR app.log` is correct. Logs are unstructured text; pattern-matching is the only tool.
- **One-shot text replacement** in a single non-code file — fine if you've eyeballed the matches.
- **Sanity-checking that an AST-driven edit landed where you expected** — `git diff | grep new_name` after a rename is a fine spot-check.

---

## The boundary rule

> **If the file you're editing is parsed by a compiler / interpreter / type-checker, use the AST tool. If it's parsed by humans only, regex is fine.**

Code: AST. Prose: regex. The rule survives the inevitable edge cases — JSON config files (parsed by a linter? use AST. Eyeballed by a human? regex is fine for one-shots).

---

## Tools available in our MCP

The MCP toolkit at `mcp/noctusai/` already ships AST-based tools and is the home of more AST tooling per `projects/mcp-server-expansion/PROJECT.md`:

- **`mcp/noctusai/tools/outline_python.py`** — libcst-based structural outline (top-level symbols, signatures) for narrow-read-first discipline (`KB § PATTERNS/agent-reading-discipline.md`).
- **`mcp/noctusai/tools/outline_typescript.py`** — ts-morph-based structural outline.
- **`noctusai_*` recurrence scans** (`refs`, `recurrence`, `service_line_recurrence`, `cross_product_helpers`) — these are intentionally string-line-based per `KB § 06-AGENTS.md`; the AST counterparts for code edits land in the broaden project.

When you need to do a rename / find-callers / codemod across the repo, prefer:

1. The MCP tool if it exists for the action (`outline_*` for read; future `ast_python` / `ast_typescript` rename/codemod for write — to be added per `projects/mcp-server-expansion/`).
2. Direct libcst / ts-morph from a one-shot script in `scripts/codemods/` if no MCP tool yet covers your action.
3. Never sed/regex/awk on `.py` / `.ts` / `.tsx` source.

---

## When this rule was added

This principle was absorbed into NoctusAI from the methodology lab on 2026-05-03 as part of the absorption-mapping batch (six projects total — see `projects/whatsapp-seed-absorption/`, `projects/mcp-server-expansion/`, `projects/llm-tool-call-audit/`, `projects/scheduling-engine-seed/`, `projects/imobi-scheduling-bot-creation/`, `projects/agno-dev-team-future-direction/`). The user's framing: *"Any code change goes through an AST tool (libcst / ts-morph / tree-sitter); regex/sed only for prose, search, log inspection."* The principle threads through every code-writing path; the keeper's existing AST tools (`outline_python`, `outline_typescript`) are the first-class examples.
