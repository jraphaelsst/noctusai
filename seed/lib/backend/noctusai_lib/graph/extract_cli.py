"""L2 CLI extractor — every `--flag` registered in `mcp/noctusai/cli.py`.

Surfaces the MCP toolkit's user-facing CLI surface as CLI_FLAG nodes,
each connected back to its `cli.py` module via EXPOSES_FLAG. Lets the
graph answer "which flag refreshes the noc-graph cache?" without
grepping a 1000-line cli.py.

Strict regex match on `parser.add_argument("--flag-name", …, help="…")` —
sound on the always-outline-able cli.py shape.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .schema import Confidence, Edge, EdgeKind, Graph, Node, NodeKind

logger = logging.getLogger(__name__)


_ADD_ARGUMENT_RE = re.compile(
    r'parser\.add_argument\(\s*["\'](--[a-z0-9\-]+)["\'](.*?)\)',
    re.DOTALL,
)
_HELP_RE = re.compile(r'help\s*=\s*["\'](.+?)["\']', re.DOTALL)


def cli_flag_id(flag: str) -> str:
    return f"cli:{flag}"


def walk_cli(graph: Graph, cli_path: Path, *, repo_root: Path) -> None:
    """Index every --flag declared in mcp/noctusai/cli.py."""
    if not cli_path.exists():
        return
    try:
        source = cli_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    module_id = f"code:{cli_path.relative_to(repo_root).as_posix()}"

    for match in _ADD_ARGUMENT_RE.finditer(source):
        flag = match.group(1)
        rest = match.group(2)
        help_match = _HELP_RE.search(rest)
        help_text = help_match.group(1)[:200] if help_match else ""

        flag_node_id = cli_flag_id(flag)
        line_no = source[: match.start()].count("\n") + 1

        graph.add_node(Node(
            id=flag_node_id,
            label=flag,
            kind=NodeKind.CLI_FLAG,
            path=str(cli_path.relative_to(repo_root).as_posix()),
            line=line_no,
            confidence=Confidence.EXTRACTED.value,
            meta=(("help", help_text),) if help_text else (),
        ))
        graph.add_edge(Edge(
            source=module_id,
            target=flag_node_id,
            kind=EdgeKind.EXPOSES_FLAG,
            confidence=Confidence.EXTRACTED.value,
        ))
