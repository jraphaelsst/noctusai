"""Auth-boundary false-green predicate — stdlib-only leaf, ONE definition.

Shared by TWO enforcement points (same shape as `self_patch_predicate`):

  * `compliance.check_auth_boundary_false_green` — commit/CI-time keeper;
  * `test_seam_guard.decide`                     — PreToolUse write-time guard.

`status_code in (401, 404|422)` passes via the mask branch even when auth never
fired. Stdlib-only is a CONSTRAINT: the write-time guard runs under the hook's
bare `python3` (no pydantic), see `self_patch_predicate`'s docstring.
KB § PATTERNS/compliance/auth-boundary-false-green.md.
"""
from __future__ import annotations

import ast
from collections.abc import Iterator

# 404 = route absent; 422 = body validation fires before the auth dep.
# 403 is deliberately EXCLUDED (a second legitimate auth outcome).
_AUTH_FALSE_GREEN_MASKABLE = frozenset({404, 422})


def _is_false_green_compare(node: ast.Compare) -> int | None:
    """The offending maskable code if `node` is `<expr> in (401, <mask>, ...)`; else None.

    Prefers 404 in the message when both appear (clearest exemplar).
    """
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.In):
        return None
    comparator = node.comparators[0]
    if not isinstance(comparator, (ast.Tuple, ast.Set, ast.List)):
        return None
    constants = {
        elt.value
        for elt in comparator.elts
        if isinstance(elt, ast.Constant) and isinstance(elt.value, int)
    }
    if 401 not in constants:
        return None
    masks = constants & _AUTH_FALSE_GREEN_MASKABLE
    if 404 in masks:
        return 404
    if 422 in masks:
        return 422
    return None


def iter_false_green_compares(tree: ast.AST) -> Iterator[tuple[ast.Compare, int]]:
    """Yield `(compare_node, mask_code)` for every false-green comparison in `tree`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            mask = _is_false_green_compare(node)
            if mask is not None:
                yield node, mask
