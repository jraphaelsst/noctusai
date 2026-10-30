"""PlatformTemplateService against the in-memory repo (twin of the migration-092 invariants)."""
from __future__ import annotations

import json

import pytest

from app.services.brand import tokens as T
from app.services.platform_templates import service as S
from app.services.platform_templates.repository import FakePlatformTemplateRepo, NotFound


@pytest.fixture
def svc():
    return S.PlatformTemplateService(FakePlatformTemplateRepo())


def _create(svc, **over):
    args = dict(product=None, kind="message", key="boas-vindas", title="Boas-vindas", description="",
                fmt="markdown", body="Ola!", user_id="u1")
    args.update(over)
    return svc.create(**args)


def test_create_is_a_draft_v1_then_v2(svc):
    a = _create(svc)
    assert (a["version"], a["status"]) == (1, "draft")
    assert _create(svc)["version"] == 2


def test_scopes_do_not_share_versions(svc):
    assert _create(svc, product="social-wiring")["version"] == 1
    assert _create(svc, product=None)["version"] == 1


def test_draft_edits_in_place(svc):
    a = _create(svc)
    b = svc.update(a["id"], fields={"body": "Novo"}, user_id="u2")
    assert b["id"] == a["id"] and b["body"] == "Novo" and b["updated_by"] == "u2"


def test_editing_active_spawns_new_draft_and_keeps_active_frozen(svc):
    a = svc.activate(_create(svc)["id"], user_id="u1")
    b = svc.update(a["id"], fields={"body": "v2"}, user_id="u1")
    assert b["id"] != a["id"] and b["version"] == 2 and b["status"] == "draft"
    assert svc.get(a["id"])["body"] == "Ola!" and svc.get(a["id"])["status"] == "active"


def test_activate_archives_previous_active(svc):
    a = svc.activate(_create(svc)["id"], user_id="u1")
    b = svc.activate(svc.update(a["id"], fields={"body": "v2"}, user_id="u1")["id"], user_id="u1")
    assert b["status"] == "active" and svc.get(a["id"])["status"] == "archived"
    assert [h["version"] for h in svc.history(b["id"])] == [2, 1]


def test_rollback_by_activating_an_archived_version(svc):
    a = svc.activate(_create(svc)["id"], user_id="u1")
    svc.activate(svc.update(a["id"], fields={"body": "v2"}, user_id="u1")["id"], user_id="u1")
    assert svc.activate(a["id"], user_id="u1")["status"] == "active"


def test_archive_and_unknown_id(svc):
    a = _create(svc)
    assert svc.archive(a["id"], user_id="u1")["status"] == "archived"
    with pytest.raises(NotFound):
        svc.get("nope")


def test_list_groups_versions_and_prefers_active(svc):
    a = svc.activate(_create(svc)["id"], user_id="u1")
    svc.update(a["id"], fields={"body": "v2"}, user_id="u1")
    rows = svc.list()
    assert len(rows) == 1
    assert rows[0]["status"] == "active" and rows[0]["versions"] == 2 and rows[0]["has_draft"] is True


def test_list_filters(svc):
    _create(svc, product="social-wiring", key="a", title="Contrato")
    _create(svc, product=None, key="b", title="Outro")
    _create(svc, kind="document", key="c", title="Doc")
    assert [r["key"] for r in svc.list(product="social-wiring")] == ["a"]
    assert [r["key"] for r in svc.list(product="_platform", kind="message")] == ["b"]
    assert [r["key"] for r in svc.list(q="doc")] == ["c"]


def test_json_must_parse_to_an_object(svc):
    with pytest.raises(S.TemplateInvalid):
        _create(svc, fmt="json", body="{nope")
    with pytest.raises(S.TemplateInvalid):
        _create(svc, fmt="json", body="[1]")
    assert _create(svc, fmt="json", body='{"a": 1}')["version"] == 1


def test_design_system_is_validated_with_brand_token_rules(svc):
    good = json.dumps({"schema": T.SCHEMA_ID, "light": {"primary": "20 80% 45%"}})
    assert _create(svc, kind="design_system", key="ds", fmt="json", body=good)["status"] == "draft"
    bad = json.dumps({"schema": T.SCHEMA_ID, "light": {"primary": "red; background: url(x)"}})
    with pytest.raises(S.TemplateInvalid):
        _create(svc, kind="design_system", key="ds2", fmt="json", body=bad)


def test_body_cap(svc):
    with pytest.raises(S.TemplateInvalid):
        _create(svc, body="x" * (S.MAX_BODY_CHARS + 1))


def test_update_revalidates_merged_result(svc):
    a = _create(svc, fmt="json", body="{}")
    with pytest.raises(S.TemplateInvalid):
        svc.update(a["id"], fields={"body": "oops"}, user_id="u1")
