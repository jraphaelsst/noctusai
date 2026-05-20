"""``noctus.graph.explain`` — full node detail + grouped neighbors + cluster."""

from __future__ import annotations

from ._loader import load_index


def explain(node_id: str) -> dict:
    return load_index().explain(node_id)


def register(server) -> None:
    @server.tool(
        name="noctus.graph.explain",
        description=(
            "Return full detail on one node: metadata, out/in neighbors "
            "grouped by edge kind, and up to 40 cluster members. The "
            "single-tool replacement for the ad-hoc compose of `refs` + "
            "`outline` + manual KB lookup."
        ),
    )
    def _explain(node_id: str) -> dict:
        return explain(node_id)
