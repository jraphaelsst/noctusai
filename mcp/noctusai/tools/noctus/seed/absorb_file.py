"""``noctus.seed.absorb_file`` — mutation companion to ``scan_repetition``.

Lifts a duplicated file from products into the seed framework, deleting
the duplicate copies and (optionally) rewriting product-side imports.
Codifies Strategy 2 (move + re-export) from
``KB § PATTERNS/seed-absorption.md`` — the most common absorption shape
seen in rounds A-D (textarea + 19 shadcn UI components + 3 trivial frontend
configs).

**Safety contract.** absorb_file refuses to act when:
- The source product's copy doesn't exist.
- The other products' copies aren't byte-identical to the source (would
  silently destroy diverged content).
- The seed destination already exists and isn't byte-identical (would
  silently overwrite).

Each refusal is loud — surfaced in the return ``error`` field; nothing
on disk changes when the function refuses.

**Inverse semantics.** absorb_file is the inverse of "scaffold copies
template into product." When the template ships an absorption-ready
re-export shim, scaffolded products inherit cleanly. When the template
still ships the raw file, run ``noctus.seed.audit_drift`` after
absorption to surface the template push-forward gap.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from settings import PRODUCTS_DIR, REPO_ROOT
from workspace import resolve_caller_root

from ._filewalk import walk_files

logger = logging.getLogger(__name__)


def _read_bytes_or_none(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _find_products_with_path(
    products_dir: Path, rel_path: str,
) -> list[str]:
    """Return sorted slugs of products that have ``rel_path`` as a regular file."""
    if not products_dir.is_dir():
        return []
    out: list[str] = []
    for product_root in sorted(products_dir.iterdir()):
        if not product_root.is_dir():
            continue
        if (product_root / rel_path).is_file():
            out.append(product_root.name)
    return out


def absorb_file(
    rel_path: str,
    seed_dest: str,
    *,
    source_product: str | None = None,
    delete_other_products: bool = True,
    rewrite_imports: list[tuple[str, str]] | None = None,
    worktree_path: str | Path | None = None,
    products_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict:
    """Lift a duplicated file from products into the seed framework.

    Args:
        rel_path: Path relative to a product root (e.g.
            ``"frontend/src/components/ui/textarea.tsx"``). Must exist
            in ``source_product`` (or in the auto-detected first product
            with the path).
        seed_dest: Destination relative to the repo root (e.g.
            ``"seed/framework/frontend/src/components/ui/textarea.tsx"``).
        source_product: Slug of the product whose copy moves to seed.
            Defaults to the first product (alphabetical) that has
            ``rel_path``. The other products' copies are byte-compared to
            this one before deletion.
        delete_other_products: When True (default), remove the duplicate
            copies in every other product. Set False to keep them
            (useful when the absorption is paired with a re-export shim
            the caller writes separately).
        rewrite_imports: List of ``(old_pattern, new_path)`` string
            substitutions to apply across every product's source. Each
            tuple is a literal ``str.replace`` (no regex). Run AFTER
            the move + delete pass. None / [] skips the rewrite.
        worktree_path: **Caller-aware path resolution.** When set, both
            the source ``products/`` scan and the seed destination land
            under the caller's worktree instead of the MCP server's
            startup workspace. Engineers calling from inside a
            ``git worktree add`` MUST pass their worktree root. See
            ``resolve_caller_root`` for the contract.
        products_dir / repo_root: Test seams. When either is set, it
            wins over the corresponding ``worktree_path`` slot.

    3-tier priority per slot: explicit seam > ``worktree_path`` >
    module default.

    Returns:
        ``{
          "moved": str,                           # absolute path of seed dest
          "source_product": str,                  # slug whose copy was promoted
          "deleted_from": [slug, ...],
          "imports_rewritten": {file: int, ...},  # count of substitutions per file
          "next_steps": [...],
        }``
        OR ``{"error": "<reason>"}`` when refused; nothing changes on disk.

    Raises:
        ValueError: ``worktree_path`` is given but does not look like a
        valid worktree root (per ``resolve_caller_root`` contract).
    """
    # Resolve caller's worktree root once; reused for whichever of
    # products_dir / repo_root is not explicitly seamed.
    caller_root: Path | None = None
    if worktree_path is not None:
        caller_root = resolve_caller_root(worktree_path)

    if products_dir is not None:
        base_products_dir = products_dir
    elif caller_root is not None:
        base_products_dir = caller_root / "products"
    else:
        base_products_dir = PRODUCTS_DIR

    if repo_root is not None:
        base_repo_root = repo_root
    elif caller_root is not None:
        base_repo_root = caller_root
    else:
        base_repo_root = REPO_ROOT

    if not base_products_dir.is_dir():
        return {"error": f"products_dir not found: {base_products_dir}"}

    # Find every product that has the file. Caller may have specified the
    # source; otherwise default to the first one alphabetical.
    products_with_path = _find_products_with_path(base_products_dir, rel_path)
    if not products_with_path:
        return {"error": f"no product has '{rel_path}'"}

    if source_product is None:
        source_product = products_with_path[0]
    elif source_product not in products_with_path:
        return {
            "error": (
                f"source_product '{source_product}' does not have '{rel_path}'. "
                f"Products that do: {products_with_path}"
            )
        }

    source_path = base_products_dir / source_product / rel_path
    source_bytes = _read_bytes_or_none(source_path)
    if source_bytes is None:
        return {"error": f"OSError reading source {source_path}"}

    # Validate every other product's copy is byte-identical (refuse if not).
    other_products = [p for p in products_with_path if p != source_product]
    diverging: list[str] = []
    for other_slug in other_products:
        other_bytes = _read_bytes_or_none(base_products_dir / other_slug / rel_path)
        if other_bytes is None:
            return {
                "error": (
                    f"OSError reading {base_products_dir / other_slug / rel_path} — "
                    "refusing to proceed without verification"
                )
            }
        if other_bytes != source_bytes:
            diverging.append(other_slug)
    if diverging:
        return {
            "error": (
                f"refusing to absorb: copies in {diverging} are NOT byte-identical "
                f"to source ({source_product}). Reconcile them first, or pick a "
                "different source_product."
            )
        }

    # Validate seed destination — refuse to overwrite something that's
    # already there with different content.
    seed_dest_path = base_repo_root / seed_dest
    if seed_dest_path.exists():
        existing_bytes = _read_bytes_or_none(seed_dest_path)
        if existing_bytes != source_bytes:
            return {
                "error": (
                    f"refusing to absorb: {seed_dest_path} already exists with "
                    "different content. Move or delete it first."
                )
            }
        # Existing file is identical — treat as already-moved, just delete sources.

    # ─── Mutations begin (validations passed) ────────────────────────────
    seed_dest_path.parent.mkdir(parents=True, exist_ok=True)
    if not seed_dest_path.exists():
        try:
            shutil.move(str(source_path), str(seed_dest_path))
        except OSError as exc:
            return {"error": f"OSError moving {source_path} → {seed_dest_path}: {exc}"}
    else:
        # Already-identical seed file — just remove the source copy.
        try:
            source_path.unlink()
        except OSError as exc:
            return {"error": f"OSError removing source {source_path}: {exc}"}

    deleted_from: list[str] = []
    if delete_other_products:
        for other_slug in other_products:
            other_path = base_products_dir / other_slug / rel_path
            try:
                other_path.unlink()
                deleted_from.append(other_slug)
            except OSError as exc:
                logger.warning(
                    "absorb_file: could not delete %s: %s", other_path, exc
                )

    imports_rewritten: dict[str, int] = {}
    if rewrite_imports:
        for product_root in sorted(base_products_dir.iterdir()):
            if not product_root.is_dir():
                continue
            for src_file in walk_files(product_root):
                # Only attempt rewrites on source-code files (cheap heuristic
                # — avoids reading every config / image / etc.).
                if src_file.suffix.lower() not in {
                    ".ts", ".tsx", ".js", ".jsx", ".py", ".css",
                }:
                    continue
                try:
                    text = src_file.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                new_text = text
                local_count = 0
                for old, new in rewrite_imports:
                    if old in new_text:
                        before = new_text.count(old)
                        new_text = new_text.replace(old, new)
                        local_count += before
                if local_count and new_text != text:
                    try:
                        src_file.write_text(new_text, encoding="utf-8")
                    except OSError as exc:
                        logger.warning(
                            "absorb_file: could not rewrite %s: %s", src_file, exc
                        )
                        continue
                    rel_str = src_file.relative_to(base_products_dir).as_posix()
                    imports_rewritten[rel_str] = local_count

    next_steps: list[str] = []
    if other_products and not delete_other_products:
        next_steps.append(
            f"delete_other_products=False — {len(other_products)} duplicate "
            f"copies still on disk: {other_products}. Either delete them or "
            "leave as re-export shims (the caller's responsibility to write)."
        )
    if not rewrite_imports and other_products:
        next_steps.append(
            "rewrite_imports was empty/None — product code may still import "
            "the old per-product path. Run scaffold_validate or vite build "
            "to confirm."
        )
    next_steps.append(
        f"Run `noctus.seed.audit_drift` to confirm the template still ships "
        f"the original at {rel_path} — if so, push the template forward to "
        "match the absorbed shape (re-export wrapper or factory call) so "
        "future scaffolds inherit the absorbed shape."
    )

    return {
        "moved": str(seed_dest_path),
        "source_product": source_product,
        "deleted_from": deleted_from,
        "imports_rewritten": imports_rewritten,
        "next_steps": next_steps,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.seed.absorb_file",
        description=(
            "Mutation companion to scan_repetition: lift a duplicated file "
            "from products into the seed framework. Refuses unless every "
            "product's copy is byte-identical to the source. Supports "
            "literal-string import-rewrite across all product source files. "
            "Always pair with audit_drift afterwards to push the template "
            "forward — the absorbed shape (re-export shim / factory call) "
            "should become the new template canonical so future scaffolds "
            "inherit it. Pass `worktree_path` when called from inside a "
            "git worktree so the source scan + seed write land in the "
            "worktree, NOT the MCP server's startup workspace. See "
            "KB § PATTERNS/mcp-tool-conventions.md."
        ),
    )
    def _absorb(
        rel_path: str,
        seed_dest: str,
        source_product: str | None = None,
        delete_other_products: bool = True,
        rewrite_imports: list[list[str]] | None = None,
        worktree_path: str | None = None,
    ) -> dict:
        # MCP serializes tuples as lists; normalize back to tuple-pairs.
        normalized: list[tuple[str, str]] | None = None
        if rewrite_imports:
            normalized = [(pair[0], pair[1]) for pair in rewrite_imports if len(pair) == 2]
        return absorb_file(
            rel_path,
            seed_dest,
            source_product=source_product,
            delete_other_products=delete_other_products,
            rewrite_imports=normalized,
            worktree_path=worktree_path,
        )
