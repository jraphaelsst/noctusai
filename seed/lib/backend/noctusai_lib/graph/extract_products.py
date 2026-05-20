"""L0 product anchor extractor — parse the `02-LANDSCAPE.md ## Products` table.

Each row becomes a ``PRODUCT`` node. The code extractor's ``CONTAINS``
edges (``product:<slug> → code:...``) connect into these anchors.

Also emits a single synthetic ``seed:noctusai_lib`` node so seed-resident
modules have an anchor too.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .schema import Confidence, Graph, Node, NodeKind

logger = logging.getLogger(__name__)


_PRODUCTS_TABLE_HEADER_RE = re.compile(r"^##\s+Products\s*$", re.MULTILINE)
# Match either a slug in the first column (`foo`), OR the path in any column
# (`products/foo/`). The two-shape regex tolerates both KB layouts.
_TABLE_ROW_FIRST_COL_RE = re.compile(r"^\|\s*`([a-z0-9\-_]+)`\s*\|", re.MULTILINE)
_TABLE_ROW_PATH_RE = re.compile(r"`products/([a-z0-9\-_]+)/?`")


def walk_products(graph: Graph, landscape_md: Path) -> None:
    """Parse `KNOWLEDGE-BASE/02-LANDSCAPE.md` and emit product anchors."""
    if not landscape_md.exists():
        logger.warning("graph.extract_products: %s missing", landscape_md)
        return

    body = landscape_md.read_text(encoding="utf-8")
    header_match = _PRODUCTS_TABLE_HEADER_RE.search(body)
    if not header_match:
        # Fallback: parse `products/*/` directory listing instead.
        _emit_from_filesystem(graph, landscape_md.parent.parent / "products")
        return

    # Table starts a few lines after the header; collect until next blank or new header.
    after = body[header_match.end():]
    table_section: list[str] = []
    for line in after.splitlines():
        if line.startswith("## "):
            break
        table_section.append(line)
    section_text = "\n".join(table_section)

    seen: set[str] = set()
    # First-column slug shape (`foo`)
    for match in _TABLE_ROW_FIRST_COL_RE.finditer(section_text):
        slug = match.group(1)
        if slug in {"slug", "product", "----", "---"}:
            continue
        seen.add(slug)
    # Path-column shape (`products/foo/`) — captures KB layouts where the
    # first column is the friendly name (e.g. `**Core**`).
    for match in _TABLE_ROW_PATH_RE.finditer(section_text):
        seen.add(match.group(1))

    for slug in sorted(seen):
        graph.add_node(Node(
            id=f"product:{slug}",
            label=slug,
            kind=NodeKind.PRODUCT,
            product=slug,
            confidence=Confidence.AUTHORED.value,
        ))

    # Always emit the seed anchor.
    graph.add_node(Node(
        id="seed:noctusai_lib",
        label="noctusai_lib (seed)",
        kind=NodeKind.SEED,
        confidence=Confidence.AUTHORED.value,
    ))


def _emit_from_filesystem(graph: Graph, products_dir: Path) -> None:
    """Fallback when 02-LANDSCAPE isn't parseable: list `products/*/`."""
    if not products_dir.exists():
        return
    for child in products_dir.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            graph.add_node(Node(
                id=f"product:{child.name}",
                label=child.name,
                kind=NodeKind.PRODUCT,
                product=child.name,
                confidence=Confidence.AUTHORED.value,
            ))
    graph.add_node(Node(
        id="seed:noctusai_lib",
        label="noctusai_lib (seed)",
        kind=NodeKind.SEED,
        confidence=Confidence.AUTHORED.value,
    ))
