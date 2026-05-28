"""L2 history extractor — `project-history/auto-improvement.ndjson` events.

Each ndjson entry is a methodology-evolution event (s1/s2/s3/s4 stage; a
slip/drift/codification surface). For the graph, we DO NOT emit one node
per event — that would dwarf the codebase (thousands of events). Instead:

- We aggregate per-target into a single decoration: each touched node gains
  meta `ai_events: count`, `ai_last_stage: s4`, `ai_last_ts: …`. This
  surfaces "drift-prone" nodes in the HTML viz (larger halo for higher count)
  without inflating the node count.

- A single AUTO_IMPROVEMENT_EVENT *aggregate* node per (target, top-stage)
  is emitted when count ≥ 3 — these are the "this surface keeps drifting"
  signals worth pulling into orientation.

Light on memory (single pass through ndjson); resilient (malformed lines
skipped).
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

from .schema import Confidence, Edge, EdgeKind, Graph, Node, NodeKind

logger = logging.getLogger(__name__)


_STAGE_ORDER = {"s1": 1, "s2": 2, "s3": 3, "s4": 4}
_HOT_THRESHOLD = 3  # events ≥ this on the same target ⇒ emit aggregate node


def walk_auto_improvement(graph: Graph, ndjson_path: Path) -> None:
    """Aggregate auto-improvement.ndjson into per-target decorations."""
    if not ndjson_path.exists():
        logger.info("graph.extract_history: %s missing — skipping", ndjson_path)
        return

    # target_path → {count, last_stage, last_ts, stages_seen}
    by_target: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "last_stage": None, "last_ts": "", "stages_seen": set(),
    })

    try:
        with ndjson_path.open(encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw or raw.startswith("#"):
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                target = rec.get("target") or rec.get("path") or rec.get("source_ref")
                if not target:
                    continue
                stage = rec.get("stage") or rec.get("s_stage")
                ts = rec.get("ts") or rec.get("timestamp") or ""
                bucket = by_target[target]
                bucket["count"] += 1
                if stage:
                    bucket["stages_seen"].add(stage)
                    if not bucket["last_stage"] or _STAGE_ORDER.get(stage, 0) >= _STAGE_ORDER.get(bucket["last_stage"], 0):
                        bucket["last_stage"] = stage
                if ts and ts > bucket["last_ts"]:
                    bucket["last_ts"] = ts
    except OSError:
        return

    node_index = {n.id: i for i, n in enumerate(graph.nodes)}

    for target, info in by_target.items():
        # Resolve target → graph node id (best-effort).
        node_id = _resolve_target_to_node_id(target, node_index)

        # Decorate the existing node when present.
        if node_id and node_id in node_index:
            idx = node_index[node_id]
            existing = graph.nodes[idx]
            new_meta = dict(existing.meta) if existing.meta else {}
            new_meta.update({
                "ai_events": info["count"],
                "ai_last_stage": info["last_stage"] or "",
                "ai_last_ts": info["last_ts"][:24],
                "ai_stages_seen": ",".join(sorted(info["stages_seen"])),
            })
            graph.nodes[idx] = replace(
                existing,
                meta=tuple(sorted(new_meta.items())),
            )

        # Hot-target aggregate node (≥ HOT_THRESHOLD events).
        if info["count"] >= _HOT_THRESHOLD:
            agg_id = f"ai:{target}"
            graph.add_node(Node(
                id=agg_id,
                label=f"AI events × {info['count']} → {target}",
                kind=NodeKind.AUTO_IMPROVEMENT_EVENT,
                path=str(ndjson_path.name),
                confidence=Confidence.AUTHORED.value,
                meta=tuple(sorted({
                    "target": target,
                    "count": info["count"],
                    "last_stage": info["last_stage"] or "",
                    "last_ts": info["last_ts"][:24],
                    "stages_seen": ",".join(sorted(info["stages_seen"])),
                }.items())),
            ))
            if node_id and node_id in node_index:
                graph.add_edge(Edge(
                    source=agg_id,
                    target=node_id,
                    kind=EdgeKind.REFERENCED_BY_EVENT,
                    confidence=Confidence.AUTHORED.value,
                    weight=float(info["count"]),
                ))


def _resolve_target_to_node_id(target: str, node_index: dict[str, int]) -> str | None:
    """Map an auto-improvement target string to a graph node id."""
    # Direct shapes commonly used in ndjson.
    candidates = [
        target,
        f"code:{target}",
        f"kb:{target}",
        f"agent:{target}",
        f"skill:{target}",
        f"command:{target}",
        f"mem:{target}",
        f"landscape:{target}",
    ]
    if target.startswith("KNOWLEDGE-BASE/"):
        candidates.append(f"kb:{target.removeprefix('KNOWLEDGE-BASE/')}")
    for c in candidates:
        if c in node_index:
            return c
    return None
