"""Reusable libcst helpers — formatting-preserving append into a list/set literal.

> Companion to `KB § PATTERNS/ast.md`. AST-first: code edits go through
> libcst, never regex/sed. This is the canonical home for the recurring
> "append a symbol to ``__all__`` (or a named set/list literal) without
> formatting drift" operation.

Why this exists
----------------
Appending a symbol to ``__all__`` / a set-literal by hand-rolled libcst
transformers repeatedly leaked a 2-step pain: the naive
``elements + [Element(...)]`` insertion produces a trailing blank-line
element / quote-style mismatch / lost trailing-comma convention, forcing a
follow-up whitespace pass. That recurred N=3 in one session (two
``__init__.py`` ``__all__`` merges + one test set-literal). This module
removes the follow-up pass entirely.

Guarantees
----------
- **Formatting-preserved**: the inserted element clones the surrounding
  element's quote style (``"`` vs ``'``), comma whitespace (single-line
  ``, `` vs multi-line ``,\\n    ``), and trailing-comma convention. No
  spurious blank-line elements, no quote drift.
- **Idempotent**: a symbol already present (same string value) is a no-op.
- **Pure libcst**: no regex on source. Round-trips untouched files byte
  for byte (``parse_module(src).code == src``).

Public API
----------
- ``append_to_all(file_path, symbols)`` — insert into the module-level
  ``__all__`` assignment's list/tuple/set literal.
- ``append_to_named_literal(file_path, target, symbols)`` — insert into the
  list/set/tuple literal bound to a module-level ``<target> = [...]``.
- ``append_symbols_to_literal(source, *, target, symbols)`` — pure
  string→string transform (testable without disk IO).

CLI
---
    python scripts/codemods/literal_append.py <file.py> --all SYM [SYM ...]
    python scripts/codemods/literal_append.py <file.py> --target NAME SYM [SYM ...]

Exit 0 on success (including idempotent no-op); 2 on error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

import libcst as cst

__all__ = [
    "append_symbols_to_literal",
    "append_to_all",
    "append_to_named_literal",
]


# ---------------------------------------------------------------------------
# Core transformer
# ---------------------------------------------------------------------------


_SEQ_LITERALS = (cst.List, cst.Tuple, cst.Set)


def _string_value(node: cst.BaseExpression) -> str | None:
    """Return the Python string value if ``node`` is a plain string literal.

    Handles ``SimpleString`` (the only shape that occurs in ``__all__`` /
    name set-literals). Concatenated / f-strings return None (we never
    dedupe against those — safer to skip than to guess).
    """
    if isinstance(node, cst.SimpleString):
        try:
            return node.evaluated_value
        except Exception:
            return None
    return None


def _quote_char(elements: Sequence[cst.BaseElement]) -> str:
    """Infer the dominant quote char from existing string elements (default ``"``)."""
    for el in elements:
        if isinstance(el.value, cst.SimpleString):
            raw = el.value.value
            # strip any prefix (r, b, u, f) — not expected in __all__ but safe
            i = 0
            while i < len(raw) and raw[i] not in ("'", '"'):
                i += 1
            if i < len(raw):
                return raw[i]
    return '"'


class _AppendTransformer(cst.CSTTransformer):
    """Append missing string symbols to the targeted module-level literal.

    ``target`` is the assignment target name (``"__all__"`` or any other).
    Only the *first* module-level ``<target> = <seq-literal>`` assignment is
    mutated (matching how ``__all__`` is conventionally declared once).
    """

    def __init__(self, target: str, symbols: Sequence[str]) -> None:
        self.target = target
        self.symbols = list(symbols)
        self.done = False
        self.matched = False
        self.added: list[str] = []

    def leave_Assign(
        self, original_node: cst.Assign, updated_node: cst.Assign
    ) -> cst.BaseSmallStatement:
        if self.done:
            return updated_node
        # match `<target> = ...` (single simple target)
        if len(updated_node.targets) != 1:
            return updated_node
        tgt = updated_node.targets[0].target
        if not (isinstance(tgt, cst.Name) and tgt.value == self.target):
            return updated_node
        value = updated_node.value
        if not isinstance(value, _SEQ_LITERALS):
            return updated_node

        self.matched = True
        self.done = True
        new_value = self._extend_literal(value)
        return updated_node.with_changes(value=new_value)

    # ------------------------------------------------------------------

    def _extend_literal(self, lit: cst.BaseExpression) -> cst.BaseExpression:
        elements = list(lit.elements)

        existing = {
            v
            for el in elements
            if (v := _string_value(el.value)) is not None
        }
        to_add = [s for s in self.symbols if s not in existing]
        if not to_add:
            return lit  # idempotent no-op — byte-identical

        quote = _quote_char(elements)

        if elements:
            # Two distinct comma roles must be reproduced:
            #   * SEPARATOR — the comma after an element that is followed by
            #     another. In a multi-line literal its ``whitespace_after``
            #     carries ``\n    `` (newline + indent). The genuine sample
            #     is a NON-last element's comma; cloning the last element's
            #     comma is wrong (its whitespace is the pre-bracket shape).
            #   * TRAILING — the comma (or its absence) on the final element.
            #     Preserves the file's trailing-comma convention and the
            #     pre-closing-bracket whitespace.
            last = elements[-1]
            orig_last_comma = last.comma  # Comma | MaybeSentinel

            # Derive the inter-element SEPARATOR whitespace. Priority:
            #   1. A genuine non-last element's comma (≥2 elems, multi-line
            #      or single-line — exact reproduction).
            #   2. The opening bracket's trailing whitespace when it is a
            #      ParenthesizedWhitespace (multi-line literal with a SINGLE
            #      element — the per-line newline+indent lives there, NOT on
            #      the lone element's pre-bracket comma).
            #   3. Single-line fallback ``", "``.
            if len(elements) >= 2 and isinstance(
                elements[-2].comma, cst.Comma
            ):
                sep_template = elements[-2].comma
            else:
                # List/Tuple expose ``lbracket``; Set exposes ``lbrace``.
                open_node = getattr(lit, "lbracket", None) or getattr(
                    lit, "lbrace", None
                )
                lb_ws = (
                    open_node.whitespace_after
                    if open_node is not None
                    else None
                )
                if isinstance(lb_ws, cst.ParenthesizedWhitespace):
                    sep_template = cst.Comma(whitespace_after=lb_ws)
                else:
                    sep_template = cst.Comma(
                        whitespace_after=cst.SimpleWhitespace(" ")
                    )

            # Prior last element is no longer last → it needs a separator.
            elements[-1] = last.with_changes(comma=sep_template)

            n = len(to_add)
            for i, sym in enumerate(to_add):
                is_last_new = i == n - 1
                comma = orig_last_comma if is_last_new else sep_template
                elements.append(
                    cst.Element(
                        value=cst.SimpleString(f"{quote}{sym}{quote}"),
                        comma=comma,
                    )
                )
        else:
            # Empty literal — emit a minimal single-line sequence.
            n = len(to_add)
            for i, sym in enumerate(to_add):
                comma = (
                    cst.MaybeSentinel.DEFAULT
                    if i == n - 1
                    else cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
                )
                elements.append(
                    cst.Element(
                        value=cst.SimpleString(f"{quote}{sym}{quote}"),
                        comma=comma,
                    )
                )

        self.added = to_add
        return lit.with_changes(elements=elements)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def append_symbols_to_literal(
    source: str, *, target: str, symbols: Sequence[str]
) -> tuple[str, list[str]]:
    """Return ``(new_source, added_symbols)`` — pure string transform.

    Inserts each symbol in ``symbols`` not already present into the
    module-level ``<target> = <list|set|tuple literal>``. Idempotent
    (already-present symbols skipped). Raises ``LookupError`` if no
    matching assignment to a sequence literal exists.
    """
    module = cst.parse_module(source)
    tr = _AppendTransformer(target, symbols)
    new_module = module.visit(tr)
    if not tr.matched:
        raise LookupError(
            f"no module-level `{target} = [list|set|tuple literal]` found"
        )
    return new_module.code, tr.added


def _apply_to_file(
    file_path: str | Path, *, target: str, symbols: Sequence[str]
) -> list[str]:
    path = Path(file_path)
    src = path.read_text(encoding="utf-8")
    new_src, added = append_symbols_to_literal(
        src, target=target, symbols=symbols
    )
    if new_src != src:
        path.write_text(new_src, encoding="utf-8")
    return added


def append_to_all(
    file_path: str | Path, symbols: Sequence[str]
) -> list[str]:
    """Append ``symbols`` to the module-level ``__all__`` literal in-place.

    Returns the list of symbols actually added (empty ⇒ idempotent no-op).
    """
    return _apply_to_file(file_path, target="__all__", symbols=symbols)


def append_to_named_literal(
    file_path: str | Path, target: str, symbols: Sequence[str]
) -> list[str]:
    """Append ``symbols`` to the module-level ``<target> = [...]`` literal.

    Works for list / set / tuple literals (e.g. a test's
    ``EXPECTED = {"a", "b"}`` set-literal). Returns symbols added.
    """
    return _apply_to_file(file_path, target=target, symbols=symbols)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="literal_append",
        description=(
            "Formatting-preserving libcst append into a module-level "
            "__all__ / named set|list|tuple literal."
        ),
    )
    parser.add_argument("file", help="path to the .py file to edit")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        nargs="+",
        metavar="SYM",
        help="append SYM... into the module-level __all__",
    )
    group.add_argument(
        "--target",
        nargs="+",
        metavar=("NAME", "SYM"),
        help="append SYM... into module-level NAME = [...] (first arg = NAME)",
    )
    args = parser.parse_args(argv)

    try:
        if args.all is not None:
            added = append_to_all(args.file, args.all)
        else:
            name, *syms = args.target
            if not syms:
                parser.error("--target requires NAME followed by ≥1 SYM")
            added = append_to_named_literal(args.file, name, syms)
    except (LookupError, FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if added:
        print(f"added {len(added)} symbol(s): {', '.join(added)}")
    else:
        print("no change (all symbols already present)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
