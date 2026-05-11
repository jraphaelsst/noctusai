"""libcst codemod — swap pydantic.BaseModel → noctusai_lib.api.StrictHttpModel.

For each target file:
  1. Rewrite `from pydantic import BaseModel[, ...]` to drop BaseModel and add
     `from noctusai_lib.api import StrictHttpModel` (preserving siblings like
     Field, ConfigDict, EmailStr, model_validator).
  2. Rewrite every `class X(BaseModel)` → `class X(StrictHttpModel)`.

Usage:
    python projects/strict-http-wave-2/migrate.py <file1.py> [<file2.py> ...]

Idempotent — safe to re-run.
"""
from __future__ import annotations

import sys
from pathlib import Path

import libcst as cst


class BaseModelToStrictHttpModel(cst.CSTTransformer):
    def __init__(self) -> None:
        super().__init__()
        self.had_basemodel_import = False
        self.had_strict_import = False

    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.BaseSmallStatement | cst.FlattenSentinel | cst.RemovalSentinel:
        module = updated_node.module
        if isinstance(module, cst.Name) and module.value == "pydantic":
            # Drop BaseModel from the import list
            if isinstance(updated_node.names, cst.ImportStar):
                return updated_node
            new_names = []
            for alias in updated_node.names:
                if isinstance(alias.name, cst.Name) and alias.name.value == "BaseModel":
                    self.had_basemodel_import = True
                    continue
                new_names.append(alias)
            if not new_names:
                # Entire `from pydantic import BaseModel` — build a proper
                # `from noctusai_lib.api import StrictHttpModel` node directly.
                self.had_strict_import = True
                return cst.ImportFrom(
                    module=cst.Attribute(
                        value=cst.Name("noctusai_lib"),
                        attr=cst.Name("api"),
                    ),
                    names=[cst.ImportAlias(name=cst.Name("StrictHttpModel"))],
                )
            # Strip trailing comma on the last name (libcst quirk)
            last = new_names[-1]
            if last.comma != cst.MaybeSentinel.DEFAULT:
                new_names[-1] = last.with_changes(comma=cst.MaybeSentinel.DEFAULT)
            return updated_node.with_changes(names=new_names)
        if (
            isinstance(module, cst.Attribute)
            and isinstance(module.value, cst.Name)
            and module.value.value == "noctusai_lib"
            and isinstance(module.attr, cst.Name)
            and module.attr.value == "api"
        ):
            # Detect existing `from noctusai_lib.api import StrictHttpModel`
            if not isinstance(updated_node.names, cst.ImportStar):
                for alias in updated_node.names:
                    if isinstance(alias.name, cst.Name) and alias.name.value == "StrictHttpModel":
                        self.had_strict_import = True
        return updated_node

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        new_bases = []
        changed = False
        for arg in updated_node.bases:
            if isinstance(arg.value, cst.Name) and arg.value.value == "BaseModel":
                new_bases.append(arg.with_changes(value=cst.Name("StrictHttpModel")))
                changed = True
            else:
                new_bases.append(arg)
        if changed:
            return updated_node.with_changes(bases=new_bases)
        return updated_node


def migrate_file(path: Path) -> bool:
    """Migrate a single schema file. Returns True if rewritten."""
    source = path.read_text()
    tree = cst.parse_module(source)
    transformer = BaseModelToStrictHttpModel()
    new_tree = tree.visit(transformer)

    if not transformer.had_basemodel_import:
        # Nothing to migrate
        return False

    new_source = new_tree.code

    # If BaseModel was solo-imported, the transformer left a malformed Attribute placeholder.
    # Rebuild by string-level replacement of the placeholder.
    # Easier path: post-process to add `from noctusai_lib.api import StrictHttpModel` after
    # the (modified) pydantic import block when needed.
    if not transformer.had_strict_import and "StrictHttpModel" in new_source:
        # Check whether the import line is already present (from the solo-import branch)
        if "from noctusai_lib.api import StrictHttpModel" not in new_source:
            # Insert after the last `from pydantic` line, OR after the first import block
            lines = new_source.split("\n")
            insert_at = None
            for i, line in enumerate(lines):
                if line.startswith("from pydantic"):
                    insert_at = i + 1
            if insert_at is None:
                # find the last import line near the top
                for i, line in enumerate(lines):
                    if line.startswith(("from ", "import ")):
                        insert_at = i + 1
                    elif insert_at is not None and line.strip() and not line.startswith(("from ", "import ", "#")):
                        break
            if insert_at is None:
                insert_at = 0
            lines.insert(insert_at, "from noctusai_lib.api import StrictHttpModel")
            new_source = "\n".join(lines)

    # Handle the solo-import malformed Attribute case: rewrite the broken line
    if "noctusai_lib.api." in new_source and "from noctusai_lib.api. import" in new_source:
        new_source = new_source.replace(
            "from noctusai_lib.api. import StrictHttpModel",
            "from noctusai_lib.api import StrictHttpModel",
        )

    path.write_text(new_source)
    return True


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: migrate.py <file.py> [<file.py> ...]", file=sys.stderr)
        sys.exit(2)
    rewritten = 0
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            continue
        if migrate_file(path):
            rewritten += 1
            print(f"rewrote {path}")
        else:
            print(f"skipped (no BaseModel import) {path}")
    print(f"\n{rewritten} file(s) rewritten")


if __name__ == "__main__":
    main()
