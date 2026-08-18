"""`trello.contract.*` tools — the point of this connector.

Every tool here is READ, ZERO IO: no network call, no credentials, reads
only the vendored `contract/swagger.v3.json` via `..spec`. They exist so
a design session ("what does Trello actually expose on a card?") gets a
truthful, machine-readable answer instead of a guess, forever, offline.

`CARD_AFFORDANCE_GROUPS` and `CAPABILITY_MAP` are the two module-level
data structures the brief for this connector asked to be kept singular —
`trello.contract.card_surface` and `trello.contract.capability_map` just
render them.
"""
from __future__ import annotations

import re
from typing import Any

from mcp.server import Server
from mcp.types import Tool

from .. import spec
from ..types import (
    CapabilityMapInput,
    CapabilityMapOutput,
    CardSurfaceInput,
    CardSurfaceOutput,
    DescribeModelInput,
    DescribeModelOutput,
    DescribeOperationInput,
    DescribeOperationOutput,
    ListEndpointsInput,
    ListEndpointsOutput,
)

# ── card affordance classification ──────────────────────────────────
#
# Ordered rules over the 42 `/cards/*` operation paths — first match
# wins. Verified against the vendored spec to sum to exactly 42
# (`tests/test_contract_spec_facts.py::test_card_surface_groups_sum_to_42`).

_CARD_AFFORDANCE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("comments_activity", re.compile(r"/actions")),
    ("attachments", re.compile(r"/attachments")),
    ("check_items", re.compile(r"checkItem")),
    ("checklists", re.compile(r"/checklists")),
    ("custom_fields", re.compile(r"[Cc]ustomField")),
    ("labels", re.compile(r"idLabels|/labels")),
    ("votes", re.compile(r"membersVoted")),
    ("members", re.compile(r"idMembers|/members")),
    ("stickers", re.compile(r"stickers")),
]


def _classify_card_affordance(path: str) -> str:
    for group, pattern in _CARD_AFFORDANCE_RULES:
        if pattern.search(path):
            return group
    return "core"


def card_affordance_groups() -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in spec.operations():
        if row["resource"] != "cards":
            continue
        group = _classify_card_affordance(row["path"])
        groups.setdefault(group, []).append(
            {k: row[k] for k in ("method", "path", "operation_id", "summary")}
        )
    return groups


# ── the Trello → lead-card-hub design bridge ────────────────────────
#
# Source of truth for the CONTENT of this table:
# `project-history/roadmaps/lead-card-hub-2026-08.md` § 4 "The Trello →
# domain map". A change there must be reflected here by hand — this is
# a deliberate transcription, not a live read of the roadmap doc (the
# roadmap is prose; this is a queryable structure), so `source` below
# names the exact section to keep the two in sync.

CAPABILITY_MAP: list[dict[str, str]] = [
    {
        "trello_affordance": "Título",
        "card_hub_equivalent": "nome da pessoa",
        "status": "exists",
        "substrate": "✓ exists",
        "trello_schema_ref": "Card.name",
    },
    {
        "trello_affordance": "Etiquetas",
        "card_hub_equivalent": "tags, colour + name (D6)",
        "status": "build-new",
        "substrate": "build new",
        "trello_schema_ref": "Card.idLabels / Card.labels / Label",
    },
    {
        "trello_affordance": "Descrição",
        "card_hub_equivalent": "observações",
        "status": "exists",
        "substrate": "`leads.observacoes` ✓",
        "trello_schema_ref": "Card.desc",
    },
    {
        "trello_affordance": "Datas + lembrete",
        "card_hub_equivalent": "follow-up date + reminder",
        "status": "build-new",
        "substrate": "`leads.follow_up_data` / `follow_up_nota` ✓ — no "
        "reminder mechanism anywhere (the date half exists; the reminder "
        "half does not)",
        "trello_schema_ref": "Card.due / Card.dueReminder / Card.start",
    },
    {
        "trello_affordance": "Anexo",
        "card_hub_equivalent": "documentos, LGPD (D5)",
        "status": "build-new",
        "substrate": "build new",
        "trello_schema_ref": "Card.attachments (via /cards/{id}/attachments) / Attachment",
    },
    {
        "trello_affordance": "Comentários e atividade",
        "card_hub_equivalent": "unified timeline (D9)",
        "status": "build-new",
        "substrate": "`pipeline_movimentos` records every stage move and "
        "is rendered nowhere (the data exists; there is no surface)",
        "trello_schema_ref": "Action (via /cards/{id}/actions)",
    },
    {
        "trello_affordance": "Membros",
        "card_hub_equivalent": "corretor responsável (D10)",
        "status": "build-new",
        "substrate": "`lead_corretores` = (nome, nome_norm, cor, ativo) "
        "— no `user_id`",
        "trello_schema_ref": "Card.idMembers / Member",
    },
    {
        "trello_affordance": "Checklist",
        "card_hub_equivalent": "stage requirements + ad-hoc (D11)",
        "status": "build-new",
        "substrate": "build new",
        "trello_schema_ref": "Card.idChecklists / Checklist / CheckItem",
    },
    {
        "trello_affordance": "Card-face badges",
        "card_hub_equivalent": "due date, description, attachment count, "
        "checklist progress, comment count, temperature",
        "status": "build-new",
        "substrate": "build new",
        "trello_schema_ref": "Card.badges",
    },
]

CAPABILITY_MAP_SOURCE = (
    "project-history/roadmaps/lead-card-hub-2026-08.md § 4 "
    '"The Trello → domain map"'
)


# ── tool handlers ────────────────────────────────────────────────────


async def list_endpoints(args: dict) -> dict:
    inp = ListEndpointsInput(**args)
    rows = spec.operations()
    if inp.resource:
        rows = [r for r in rows if r["resource"] == inp.resource]
    if inp.method:
        rows = [r for r in rows if r["method"] == inp.method.upper()]
    if inp.q:
        needle = inp.q.lower()
        rows = [
            r for r in rows
            if needle in r["path"].lower() or needle in r["summary"].lower()
        ]
    endpoints = [
        {k: r[k] for k in ("method", "path", "resource", "operation_id", "summary")}
        for r in rows
    ]
    return ListEndpointsOutput(endpoints=endpoints, count=len(endpoints)).model_dump()


async def describe_operation(args: dict) -> dict:
    inp = DescribeOperationInput(**args)
    if not inp.operation_id and not (inp.method and inp.path):
        return DescribeOperationOutput(
            error={
                "error_class": "ValueError",
                "message": "Provide either operation_id, or both method and path.",
                "status": None,
            }
        ).model_dump()

    op = spec.find_operation(method=inp.method, path=inp.path, operation_id=inp.operation_id)
    if op is None:
        return DescribeOperationOutput(
            error={
                "error_class": "NotFoundError",
                "message": f"No operation matched "
                f"(operation_id={inp.operation_id!r}, method={inp.method!r}, path={inp.path!r}).",
                "status": 404,
            }
        ).model_dump()

    parameters = [
        {
            "name": p.get("name"),
            "in": p.get("in"),
            "type": (p.get("schema") or {}).get("type"),
            "required": p.get("required", False),
            "description": p.get("description"),
        }
        for p in op.get("parameters", [])
    ]
    request_body = None
    if "requestBody" in op:
        request_body = (
            op["requestBody"].get("content", {}).get("application/json", {}).get("schema")
        )
    return DescribeOperationOutput(
        operation={
            "method": op["method"],
            "path": op["path"],
            "operation_id": op.get("operationId"),
            "summary": op.get("summary", ""),
            "description": op.get("description", ""),
            "parameters": parameters,
            "request_body": request_body,
            "response_schema_ref": spec.response_schema_ref(op),
        }
    ).model_dump()


async def describe_model(args: dict) -> dict:
    inp = DescribeModelInput(**args)
    schema_obj = spec.schema(inp.name)
    if schema_obj is None:
        return DescribeModelOutput(
            error={
                "error_class": "NotFoundError",
                "message": f"No schema named {inp.name!r} in the vendored spec. "
                "Names are case-sensitive (e.g. 'TrelloList', not 'List').",
                "status": 404,
            }
        ).model_dump()
    return DescribeModelOutput(
        model={
            "name": inp.name,
            "properties": spec.flatten_properties(schema_obj),
            "required": schema_obj.get("required", []),
        }
    ).model_dump()


async def card_surface(args: dict) -> dict:
    CardSurfaceInput(**args)
    groups = card_affordance_groups()
    card_schema_obj = spec.schema("Card") or {}
    put_op = spec.find_operation(method="PUT", path="/cards/{id}") or {}
    put_writable = [p.get("name") for p in put_op.get("parameters", [])]
    operation_count = sum(len(v) for v in groups.values())
    return CardSurfaceOutput(
        groups=groups,
        operation_count=operation_count,
        card_schema={
            "name": "Card",
            "properties": spec.flatten_properties(card_schema_obj),
            "required": card_schema_obj.get("required", []),
        },
        put_writable_fields=put_writable,
    ).model_dump()


async def capability_map(args: dict) -> dict:
    CapabilityMapInput(**args)
    return CapabilityMapOutput(
        mappings=CAPABILITY_MAP, source=CAPABILITY_MAP_SOURCE
    ).model_dump()


HANDLERS = {
    "trello.contract.list_endpoints": list_endpoints,
    "trello.contract.describe_operation": describe_operation,
    "trello.contract.describe_model": describe_model,
    "trello.contract.card_surface": card_surface,
    "trello.contract.capability_map": capability_map,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="trello.contract.list_endpoints",
            description="List Trello API operations from the vendored spec. "
            "READ, ZERO IO — no network call, no credentials. Filters: "
            "resource ('cards'/'boards'/...), method, q (substring).",
            inputSchema=ListEndpointsInput.model_json_schema(),
        ),
        Tool(
            name="trello.contract.describe_operation",
            description="Full detail on one Trello operation (params, "
            "request body, response schema ref). READ, ZERO IO. Identify "
            "by operation_id OR by method+path.",
            inputSchema=DescribeOperationInput.model_json_schema(),
        ),
        Tool(
            name="trello.contract.describe_model",
            description="A named Trello schema (Card, Checklist, CheckItem, "
            "Label, Attachment, Action, CustomField, Member, Board, "
            "TrelloList, ...) with properties flattened one level (object/"
            "$ref properties expose their own nested_properties). READ, "
            "ZERO IO.",
            inputSchema=DescribeModelInput.model_json_schema(),
        ),
        Tool(
            name="trello.contract.card_surface",
            description="The curated answer to 'everything a Trello CARD "
            "can do': the 42 /cards/* operations grouped by affordance "
            "(core, comments_activity, attachments, checklists, "
            "check_items, labels, members, votes, stickers, custom_fields) "
            "plus the Card schema (badges.* flattened) and the exact PUT "
            "/cards/{id} writable-field list. READ, ZERO IO. Call this "
            "first when designing against a Trello card.",
            inputSchema=CardSurfaceInput.model_json_schema(),
        ),
        Tool(
            name="trello.contract.capability_map",
            description="The design bridge: each Trello card affordance → "
            "its status (exists/build-new/no-equivalent) in our lead-card-"
            "hub domain, sourced from "
            "project-history/roadmaps/lead-card-hub-2026-08.md § 4. READ, "
            "ZERO IO.",
            inputSchema=CapabilityMapInput.model_json_schema(),
        ),
    ]


__all__ = [
    "CAPABILITY_MAP",
    "CAPABILITY_MAP_SOURCE",
    "HANDLERS",
    "card_affordance_groups",
    "register",
    "tool_descriptors",
]
