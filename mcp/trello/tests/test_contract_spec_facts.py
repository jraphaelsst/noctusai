"""Assertions against the VENDORED spec file itself (not the tool layer).

These are the "so a spec refresh that changes them fails loudly" checks
the brief for this connector asked for. Every number here was verified
by parsing the actual `contract/swagger.v3.json` (see
`contract/PROVENANCE.md`) before this connector was built — a refresh
that changes any of them must be a deliberate, reviewed update to this
file, not something the `trello.contract.*` tools silently start
answering differently.
"""
from __future__ import annotations

import collections

from trello import spec

EXPECTED_TOTAL_OPERATIONS = 261

EXPECTED_PER_RESOURCE = {
    "members": 45,
    "cards": 42,
    "boards": 41,
    "organizations": 26,
    "enterprises": 21,
    "actions": 16,
    "checklists": 12,
    "lists": 11,
    "notifications": 11,
    "customFields": 8,
    "tokens": 8,
    "labels": 5,
    "plugins": 5,
    "webhooks": 5,
    "search": 2,
    "applications": 1,
    "batch": 1,
    "emoji": 1,
}

EXPECTED_CARD_BADGE_FIELDS = {
    "checkItems", "checkItemsChecked", "comments", "attachments",
    "description", "due", "start", "dueComplete", "votes", "location",
    "subscribed",
}

EXPECTED_PUT_CARD_WRITABLE_FIELDS = [
    "name", "desc", "closed", "idMembers", "idAttachmentCover", "idList",
    "idLabels", "idBoard", "pos", "due", "start", "dueComplete",
    "subscribed", "address", "locationName", "coordinates", "cover",
]


def test_total_operation_count():
    assert len(spec.operations()) == EXPECTED_TOTAL_OPERATIONS


def test_per_resource_operation_counts():
    counts = collections.Counter(row["resource"] for row in spec.operations())
    assert dict(counts) == EXPECTED_PER_RESOURCE
    assert sum(counts.values()) == EXPECTED_TOTAL_OPERATIONS


def test_card_schema_exists_and_carries_every_documented_badge_field():
    card = spec.schema("Card")
    assert card is not None
    badges_prop = card["properties"]["badges"]
    assert set(badges_prop["properties"].keys()) >= EXPECTED_CARD_BADGE_FIELDS


def test_put_cards_id_writable_field_list_matches_exactly():
    op = spec.find_operation(method="PUT", path="/cards/{id}")
    assert op is not None
    names = [p["name"] for p in op["parameters"]]
    assert names == EXPECTED_PUT_CARD_WRITABLE_FIELDS


def test_auth_is_key_and_token_query_params():
    security_schemes = spec.load_spec()["components"]["securitySchemes"]
    assert security_schemes["APIKey"] == {"type": "apiKey", "in": "query", "name": "key"}
    assert security_schemes["APIToken"]["in"] == "query"
    assert security_schemes["APIToken"]["name"] == "token"


def test_find_operation_by_operation_id_matches_method_and_path_lookup():
    by_path = spec.find_operation(method="PUT", path="/cards/{id}")
    by_op_id = spec.find_operation(operation_id=by_path["operationId"])
    assert by_op_id is not None
    assert by_op_id["path"] == "/cards/{id}"
    assert by_op_id["method"] == "PUT"


def test_find_operation_returns_none_for_an_unknown_path():
    assert spec.find_operation(method="GET", path="/not/a/real/path") is None


def test_schema_returns_none_for_an_unknown_name():
    assert spec.schema("NotARealSchema") is None
