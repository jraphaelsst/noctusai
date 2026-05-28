"""Schema — Node / Edge / Graph dataclasses + open enums.

Open taxonomy: new kinds extend the enums; non-fitting instance ⇒ add the
class, never force-fit. Confidence ≡ source provenance (no LLM inference
in v1, so ``EXTRACTED=1.0`` is the only confidence used by current
extractors; the type stays for future ``MINED`` edges from
``hound.scan``).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class NodeKind(str, Enum):
    """Node taxonomy. Open — extend when a new instance doesn't fit."""

    # L1 — code
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    ROUTE = "route"
    MCP_TOOL = "mcp_tool"
    COMPONENT = "component"
    HOOK = "hook"
    MIGRATION = "migration"
    # L2 — knowledge (authored prose)
    KB_PATTERN = "kb_pattern"
    KB_GUIDE = "kb_guide"
    KB_INTEGRATION = "kb_integration"
    KB_BACKEND_SPEC = "kb_backend_spec"
    KB_FRONTEND_SPEC = "kb_frontend_spec"
    KB_CHAPTER = "kb_chapter"               # 0X-NAME.md top-level chapters
    MEMORY = "memory"
    MEMORY_INDEX = "memory_index"            # MEMORY.md root
    MASTER_PROMPT_SECTION = "master_prompt_section"
    FINDING = "finding"
    PROJECT = "project"
    PROPOSAL = "proposal"
    LANDSCAPE_DOC = "landscape_doc"          # CLAUDE.md + CLAUDE/*.md + CONTEXTUALIZE.md + CHANGELOG.md
    HARNESS_AGENT = "harness_agent"          # .claude/agents/<name>.md
    HARNESS_SKILL = "harness_skill"          # .claude/skills/<name>/SKILL.md
    HARNESS_COMMAND = "harness_command"      # .claude/commands/<name>.md
    AUTO_IMPROVEMENT_EVENT = "auto_improvement_event"  # one ndjson entry
    KEEPER_RULE = "keeper_rule"              # check_* function in compliance.py
    HOOK_SCRIPT = "hook_script"              # scripts/hooks/*
    CLI_FLAG = "cli_flag"                    # mcp/noctusai/cli.py --flag
    # L0 — anchor
    PRODUCT = "product"
    SEED = "seed"


class EdgeKind(str, Enum):
    """Edge taxonomy. Open."""

    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    DECORATES = "decorates"
    MOUNTS = "mounts"
    CONSUMES_SEED = "consumes_seed"
    EXPORTS = "exports"
    KB_POINTER = "kb_pointer"
    MEMORY_LINK = "memory_link"
    DOCUMENTS = "documents"
    DEFINED_IN = "defined_in"
    BELONGS_TO = "belongs_to"
    CONTAINS = "contains"  # product → module, kb file → kb section
    # Methodology fabric — agents/skills/commands/CLAUDE.md routing
    AUTO_TRIGGERS = "auto_triggers"          # skill/command → trigger phrase or event
    OWNS_KB = "owns_kb"                      # agent → kb_pattern (frontmatter owns_kb:)
    INVOKES_SKILL = "invokes_skill"          # CLAUDE.md / agent → skill
    INVOKES_AGENT = "invokes_agent"          # CLAUDE.md / orchestration → agent
    EXPOSES_TOOL = "exposes_tool"            # module → mcp_tool
    EXPOSES_FLAG = "exposes_flag"            # cli.py module → cli_flag
    GUARDED_BY = "guarded_by"                # code/path → keeper_rule
    REFERENCED_BY_EVENT = "referenced_by_event"  # auto-improvement event → node
    MIRRORS = "mirrors"                      # cache → source surface
    # Mined / semantic — confidence < 1.0
    MINED_RECURRENCE = "mined_recurrence"    # hound/scan_cross_product/scan_fusions
    SEMANTIC_NEIGHBOR = "semantic_neighbor"  # embedding-cosine sibling


class Confidence(float, Enum):
    """Provenance-derived confidence. Free-form floats also allowed (mined edges)."""

    EXTRACTED = 1.0
    AUTHORED = 1.0   # alias: durable prose pointer (KB §, [[name]]) — also lossless
    EXTRACTED_LOW = 0.75  # regex-anchored extraction (TS top-level, FastAPI route decorator)
    MINED_HIGH = 0.9
    MINED_MEDIUM = 0.6
    MINED_LOW = 0.3


@dataclass(frozen=True)
class Node:
    """One graph node. ``id`` is stable across rebuilds."""

    id: str
    label: str
    kind: NodeKind
    path: str | None = None
    line: int | None = None
    end_line: int | None = None
    product: str | None = None
    cluster: int | None = None
    confidence: float = 1.0
    meta: tuple[tuple[str, Any], ...] = ()  # tuple-of-pairs for hashability

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "kind": self.kind.value,
            "confidence": self.confidence,
        }
        if self.path is not None:
            d["path"] = self.path
        if self.line is not None:
            d["line"] = self.line
        if self.end_line is not None:
            d["end_line"] = self.end_line
        if self.product is not None:
            d["product"] = self.product
        if self.cluster is not None:
            d["cluster"] = self.cluster
        if self.meta:
            d["meta"] = dict(self.meta)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Node":
        meta = data.get("meta") or {}
        return cls(
            id=data["id"],
            label=data["label"],
            kind=NodeKind(data["kind"]),
            path=data.get("path"),
            line=data.get("line"),
            end_line=data.get("end_line"),
            product=data.get("product"),
            cluster=data.get("cluster"),
            confidence=float(data.get("confidence", 1.0)),
            meta=tuple(sorted(meta.items())),
        )


@dataclass(frozen=True)
class Edge:
    """Directed edge. ``confidence`` is the source's quality signal."""

    source: str
    target: str
    kind: EdgeKind
    confidence: float = 1.0
    weight: float = 1.0
    meta: tuple[tuple[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "source": self.source,
            "target": self.target,
            "kind": self.kind.value,
            "confidence": self.confidence,
            "weight": self.weight,
        }
        if self.meta:
            d["meta"] = dict(self.meta)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Edge":
        meta = data.get("meta") or {}
        return cls(
            source=data["source"],
            target=data["target"],
            kind=EdgeKind(data["kind"]),
            confidence=float(data.get("confidence", 1.0)),
            weight=float(data.get("weight", 1.0)),
            meta=tuple(sorted(meta.items())),
        )


SCHEMA_VERSION: int = 1


@dataclass
class Graph:
    """Whole graph. ``meta`` carries build-time provenance."""

    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        self.nodes.append(node)

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    def node_index(self) -> dict[str, Node]:
        return {n.id: n for n in self.nodes}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "meta": self.meta,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def to_json(self, *, indent: int | None = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Graph":
        return cls(
            nodes=[Node.from_dict(n) for n in data.get("nodes", [])],
            edges=[Edge.from_dict(e) for e in data.get("edges", [])],
            meta=data.get("meta", {}),
        )

    @classmethod
    def from_json(cls, payload: str) -> "Graph":
        return cls.from_dict(json.loads(payload))
