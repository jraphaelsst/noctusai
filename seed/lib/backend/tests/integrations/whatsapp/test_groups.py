"""WhatsApp group operations — `WahaClient` + `FakeWahaClient` parity.

`WahaClient`'s half exercises the REAL `_request` path via an
`httpx.MockTransport` injected through the constructor (`transport=`) —
no monkey-patching of `httpx.AsyncClient`/`httpx.Client` (the shape
`test_client.py`/`test_client_identity.py` use for the pre-existing
send/identity methods stays as-is; this file uses the newer
constructor-seam shape, matching `HttpxMailchimpClient`'s `_transport`
pattern). `FakeWahaClient`'s half exercises the deterministic in-memory
mirror. Both satisfy `WhatsAppGroupClient`; `MetaCloudClient` does not.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from noctusai_lib.integrations import rate_limit
from noctusai_lib.integrations.whatsapp import (
    FakeMetaCloudClient,
    FakeWahaClient,
    ParticipantChangeResult,
    WahaClient,
    WahaGroupError,
    WhatsAppGroupClient,
)


# ---- Protocol conformance ---------------------------------------------------


def test_waha_client_satisfies_group_protocol() -> None:
    client = WahaClient(base_url="https://waha.test", api_key="k")
    assert isinstance(client, WhatsAppGroupClient)


def test_fake_waha_client_satisfies_group_protocol() -> None:
    assert isinstance(FakeWahaClient(), WhatsAppGroupClient)


def test_meta_cloud_client_does_not_implement_group_protocol() -> None:
    """The Meta Cloud API has no group-management surface — the fake
    must NOT accidentally satisfy `WhatsAppGroupClient` (would silently
    mask a caller using it against the wrong backend)."""
    assert not isinstance(FakeMetaCloudClient(), WhatsAppGroupClient)


# ---- Real client: httpx.MockTransport handler -------------------------------


def _handler(request: httpx.Request) -> httpx.Response:
    method = request.method
    path = request.url.path
    body = json.loads(request.content) if request.content else {}

    if path == "/api/default/groups" and method == "POST":
        participants = [
            {"id": p["id"], "isAdmin": False} for p in body["participants"]
        ]
        return httpx.Response(
            201,
            json={"id": "120363-new@g.us", "name": body["name"], "participants": participants},
        )

    if path == "/api/default/groups" and method == "GET":
        assert request.url.params["limit"] == "20"
        assert request.url.params["offset"] == "5"
        return httpx.Response(
            200,
            json=[
                {"id": "111@g.us", "name": "Alpha", "participants": []},
                {"id": "222@g.us", "name": "Beta", "participants": []},
            ],
        )

    if path == "/api/default/groups/missing-group@g.us":
        return httpx.Response(404, json={"error": "group not found"})

    if path == "/api/default/groups/111@g.us" and method == "GET":
        return httpx.Response(
            200,
            json={
                "id": "111@g.us",
                "name": "Alpha",
                "participants": [
                    {"id": "5511900000001@c.us", "isSuperAdmin": True},
                    {"id": "5511900000002@c.us", "isAdmin": True},
                    {"id": "5511900000003@c.us"},
                ],
                "owner": "5511900000001@c.us",
                "description": "Test group",
            },
        )

    if path == "/api/default/groups/111@g.us/participants" and method == "GET":
        return httpx.Response(
            200,
            json=[
                {"id": "5511900000001@c.us", "isSuperAdmin": True},
                {"id": {"_serialized": "5511900000002@c.us"}, "isAdmin": True},
            ],
        )

    if path == "/api/default/groups/111@g.us/participants/add" and method == "POST":
        results = []
        for p in body["participants"]:
            pid = p["id"]
            if "restricted" in pid:
                results.append({"id": pid, "status": 403})
            else:
                results.append({"id": pid, "status": 200})
        return httpx.Response(200, json=results)

    if path == "/api/default/groups/111@g.us/participants/remove" and method == "POST":
        return httpx.Response(
            200,
            json=[{"id": p["id"], "status": 200} for p in body["participants"]],
        )

    if path == "/api/default/groups/222@g.us/participants/add" and method == "POST":
        # WAHA answered 2xx with no per-participant breakdown at all.
        return httpx.Response(200, json=[])

    if path == "/api/default/groups/111@g.us/admin/promote" and method == "POST":
        assert body == {"participants": [{"id": "5511900000003@c.us"}]}
        return httpx.Response(200, json={})

    if path == "/api/default/groups/111@g.us/admin/demote" and method == "POST":
        assert body == {"participants": [{"id": "5511900000001@c.us"}]}
        return httpx.Response(200, json={})

    if path == "/api/default/groups/111@g.us/invite-code" and method == "GET":
        return httpx.Response(200, json={"inviteCode": "ABCDEF1234"})

    if path == "/api/default/groups/111@g.us/invite-code/revoke" and method == "POST":
        return httpx.Response(200, json={"inviteCode": "NEWCODE5678"})

    if (
        path == "/api/default/groups/111@g.us/settings/security/messages-admin-only"
        and method == "PUT"
    ):
        assert body == {"value": True}
        return httpx.Response(200, json={})

    if path == "/api/default/chats/111@g.us/messages/msg-1" and method == "DELETE":
        return httpx.Response(200, json={})

    if path == "/api/default/groups/111@g.us/leave" and method == "POST":
        return httpx.Response(200, json={})

    if path == "/api/default/groups/500-group@g.us" and method == "GET":
        return httpx.Response(500, json={"error": "boom"})

    raise AssertionError(f"unhandled mock request: {method} {path}")


def _client() -> WahaClient:
    return WahaClient(
        base_url="https://waha.test",
        api_key="k",
        session="default",
        transport=httpx.MockTransport(_handler),
    )


# ---- create_group / list_groups / get_group ---------------------------------


def test_create_group_posts_name_and_participants_returns_group_info() -> None:
    client = _client()
    group = asyncio.run(
        client.create_group("Wave 0 pilots", ["5511900000001@c.us", "5511900000002@c.us"])
    )

    assert group.id == "120363-new@g.us"
    assert group.name == "Wave 0 pilots"
    assert [p.id for p in group.participants] == [
        "5511900000001@c.us",
        "5511900000002@c.us",
    ]


def test_list_groups_forwards_limit_and_offset() -> None:
    client = _client()
    groups = asyncio.run(client.list_groups(limit=20, offset=5))

    assert [g.id for g in groups] == ["111@g.us", "222@g.us"]
    assert [g.name for g in groups] == ["Alpha", "Beta"]


def test_get_group_parses_participants_and_roles() -> None:
    client = _client()
    group = asyncio.run(client.get_group("111@g.us"))

    assert group.name == "Alpha"
    assert group.owner == "5511900000001@c.us"
    assert group.description == "Test group"
    roles = {p.id: p.role for p in group.participants}
    assert roles["5511900000001@c.us"] == "superadmin"
    assert roles["5511900000002@c.us"] == "admin"
    assert roles["5511900000003@c.us"] == "participant"


def test_get_group_raises_waha_group_error_on_404() -> None:
    client = _client()
    with pytest.raises(WahaGroupError) as exc_info:
        asyncio.run(client.get_group("missing-group@g.us"))
    assert exc_info.value.op == "get_group"
    assert exc_info.value.status == 404


def test_get_group_raises_waha_group_error_on_5xx() -> None:
    """Not just 404 — a genuine server error also surfaces as the typed
    `WahaGroupError`, not a bare unlabeled `httpx.HTTPStatusError`."""
    client = _client()
    with pytest.raises(WahaGroupError) as exc_info:
        asyncio.run(client.get_group("500-group@g.us"))
    assert exc_info.value.status == 500
    # the original httpx error is preserved, not swallowed
    assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)


# ---- list_participants -------------------------------------------------------


def test_list_participants_normalizes_serialized_id_shape() -> None:
    client = _client()
    participants = asyncio.run(client.list_participants("111@g.us"))

    assert [p.id for p in participants] == [
        "5511900000001@c.us",
        "5511900000002@c.us",
    ]
    assert [p.role for p in participants] == ["superadmin", "admin"]


# ---- add_participants / remove_participants -----------------------------------


def test_add_participants_maps_privacy_refusal_to_invite_required() -> None:
    client = _client()
    results = asyncio.run(
        client.add_participants(
            "111@g.us", ["5511900000009@c.us", "5511900000010-restricted@c.us"]
        )
    )

    by_id = {r.id: r for r in results}
    assert by_id["5511900000009@c.us"].outcome == "added"
    assert by_id["5511900000009@c.us"].code == 200
    assert by_id["5511900000010-restricted@c.us"].outcome == "invite_required"
    assert by_id["5511900000010-restricted@c.us"].code == 403


def test_remove_participants_returns_removed_outcome() -> None:
    client = _client()
    results = asyncio.run(client.remove_participants("111@g.us", ["5511900000009@c.us"]))

    assert results == [
        ParticipantChangeResult(id="5511900000009@c.us", outcome="removed", code=200)
    ]


def test_add_participants_assumes_success_when_waha_answers_no_breakdown() -> None:
    """No-silent-errors: a bare 2xx with an empty body still returns one
    outcome per requested id (assumed succeeded) rather than an empty
    list that would look like "nothing happened"."""
    client = _client()
    results = asyncio.run(client.add_participants("222@g.us", ["a@c.us", "b@c.us"]))

    assert results == [
        ParticipantChangeResult(id="a@c.us", outcome="added", code=None),
        ParticipantChangeResult(id="b@c.us", outcome="added", code=None),
    ]


# ---- promote_admins / demote_admins -------------------------------------------


def test_promote_and_demote_admins_post_expected_body() -> None:
    client = _client()
    asyncio.run(client.promote_admins("111@g.us", ["5511900000003@c.us"]))
    asyncio.run(client.demote_admins("111@g.us", ["5511900000001@c.us"]))
    # assertions live inside `_handler` (body shape pinned there)


# ---- invite link -------------------------------------------------------------


def test_get_invite_link_wraps_code_into_full_link() -> None:
    client = _client()
    link = asyncio.run(client.get_invite_link("111@g.us"))
    assert link == "https://chat.whatsapp.com/ABCDEF1234"


def test_revoke_invite_link_returns_new_link() -> None:
    client = _client()
    link = asyncio.run(client.revoke_invite_link("111@g.us"))
    assert link == "https://chat.whatsapp.com/NEWCODE5678"


# ---- settings / delete_message / leave_group ----------------------------------


def test_set_messages_admin_only_puts_value_body() -> None:
    client = _client()
    asyncio.run(client.set_messages_admin_only("111@g.us", True))
    # body shape pinned inside `_handler`


def test_delete_message_issues_delete_on_chat_message_path() -> None:
    client = _client()
    asyncio.run(client.delete_message("111@g.us", "msg-1"))


def test_leave_group_posts_leave_endpoint() -> None:
    client = _client()
    asyncio.run(client.leave_group("111@g.us"))


# ---- Rate-limit pacing (NOC-REMEDIATE[rate-limit] closure) --------------------


def test_group_call_consumes_a_token_from_the_shared_whatsapp_bucket() -> None:
    """Every group op routes through async `_request`, which paces via
    `rate_limit.acquire_async("whatsapp")` before the call — assert the
    ASYNC registry's bucket (the one `acquire_async` actually reads —
    distinct from `rate_limit.limiter`'s sync-path bucket) drops by one
    token, proving the pacing is wired (not just documented)."""
    bucket = rate_limit._async_registry.bucket("whatsapp")
    tokens_before = bucket._tokens

    client = _client()
    asyncio.run(client.get_group("111@g.us"))

    assert bucket._tokens == pytest.approx(tokens_before - 1)


# ---- FakeWahaClient parity ----------------------------------------------------


def test_fake_create_list_get_group() -> None:
    client = FakeWahaClient()
    created = asyncio.run(client.create_group("Fake group", ["a@c.us", "b@c.us"]))

    listed = asyncio.run(client.list_groups())
    assert listed == [created]

    fetched = asyncio.run(client.get_group(created.id))
    assert fetched == created


def test_fake_get_group_raises_waha_group_error_when_unknown() -> None:
    client = FakeWahaClient()
    with pytest.raises(WahaGroupError):
        asyncio.run(client.get_group("nope@g.us"))


def test_fake_add_participants_privacy_restricted_seam() -> None:
    client = FakeWahaClient()
    group = asyncio.run(client.create_group("G", ["a@c.us"]))
    client.privacy_restricted_ids.add("blocked@c.us")

    results = asyncio.run(client.add_participants(group.id, ["b@c.us", "blocked@c.us"]))

    by_id = {r.id: r for r in results}
    assert by_id["b@c.us"].outcome == "added"
    assert by_id["blocked@c.us"].outcome == "invite_required"

    participants = asyncio.run(client.list_participants(group.id))
    assert {p.id for p in participants} == {"a@c.us", "b@c.us"}


def test_fake_remove_participants_reports_failed_for_unknown_id() -> None:
    client = FakeWahaClient()
    group = asyncio.run(client.create_group("G", ["a@c.us"]))

    results = asyncio.run(client.remove_participants(group.id, ["a@c.us", "ghost@c.us"]))

    by_id = {r.id: r for r in results}
    assert by_id["a@c.us"].outcome == "removed"
    assert by_id["ghost@c.us"].outcome == "failed"


def test_fake_promote_then_demote_admin() -> None:
    client = FakeWahaClient()
    group = asyncio.run(client.create_group("G", ["a@c.us"]))

    asyncio.run(client.promote_admins(group.id, ["a@c.us"]))
    participants = asyncio.run(client.list_participants(group.id))
    assert participants[0].role == "admin"

    asyncio.run(client.demote_admins(group.id, ["a@c.us"]))
    participants = asyncio.run(client.list_participants(group.id))
    assert participants[0].role == "participant"


def test_fake_invite_link_get_and_revoke() -> None:
    client = FakeWahaClient()
    group = asyncio.run(client.create_group("G", []))

    link1 = asyncio.run(client.get_invite_link(group.id))
    link2 = asyncio.run(client.get_invite_link(group.id))
    assert link1 == link2  # stable until revoked

    revoked = asyncio.run(client.revoke_invite_link(group.id))
    assert revoked != link1


def test_fake_set_messages_admin_only_records_state() -> None:
    client = FakeWahaClient()
    group = asyncio.run(client.create_group("G", []))

    asyncio.run(client.set_messages_admin_only(group.id, True))
    assert client.messages_admin_only[group.id] is True


def test_fake_delete_message_and_leave_group() -> None:
    client = FakeWahaClient()
    group = asyncio.run(client.create_group("G", []))

    asyncio.run(client.delete_message(group.id, "msg-1"))
    assert client.deleted_messages == [{"chatId": group.id, "messageId": "msg-1"}]

    asyncio.run(client.leave_group(group.id))
    assert group.id in client.left_groups
    with pytest.raises(WahaGroupError):
        asyncio.run(client.get_group(group.id))


def test_fake_clear_resets_group_state() -> None:
    client = FakeWahaClient()
    asyncio.run(client.create_group("G", ["a@c.us"]))
    client.privacy_restricted_ids.add("x@c.us")

    client.clear()

    assert client.fake_groups == {}
    assert client.privacy_restricted_ids == set()
