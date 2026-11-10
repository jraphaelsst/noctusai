"""Line policy v1: fail-closed write refusal at the seed choke point, session config from policy, auto-repair gate,
read-back, Fake parity. KB § INTEGRATIONS/whatsapp.md § 6a."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from noctusai_lib.integrations.whatsapp import (
    UNDECLARED,
    FakeWahaClient,
    InMemoryLineEventSink,
    LinePolicy,
    LinePolicyError,
    LineRepairRefused,
    LineWriteRefused,
    clear_line_policies,
    get_whatsapp_client,
    is_whatsapp_write,
    load_line_policies_from_env,
    parse_line_policy,
    register_line_policy,
    resolve_line_policy,
)
from noctusai_lib.integrations.whatsapp.client import WahaClient, _merged_session_config, _session_config

SHADOW = LinePolicy("disabled", False, False, False)
LEGACY = LinePolicy("enabled", True, True, True)


@pytest.fixture(autouse=True)
def _no_legacy_wildcard():
    clear_line_policies()  # overrides the package autouse: these tests start from an EMPTY registry (fail-closed)
    yield
    clear_line_policies()


class Waha:
    def __init__(self, session_body=None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.session_body = session_body or {"name": "default", "status": "SCAN_QR_CODE", "config": {}}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        if request.method == "GET" and request.url.path.startswith("/api/sessions/"):
            return httpx.Response(200, json=self.session_body)
        return httpx.Response(200, json={"ok": True})

    def client(self, policy, sink=None):
        return WahaClient("http://waha.test", "k", "default", transport=httpx.MockTransport(self),
                          line_policy=policy, line_event_sink=sink)


def run(c):
    return asyncio.run(c)


# --- parsing ----------------------------------------------------------------------------------------------------------


def test_parse_is_strict():
    ok = parse_line_policy('{"send":"disabled","mark_online":false,"full_sync":false,"auto_repair":false}')
    assert ok == SHADOW and ok.as_json().startswith('{"send":"disabled"')
    for bad in ('{"send":"on","mark_online":false,"full_sync":false,"auto_repair":false}',
                '{"send":"enabled"}',
                '{"send":"enabled","mark_online":"no","full_sync":false,"auto_repair":false}',
                '{"send":"enabled","mark_online":true,"full_sync":true,"auto_repair":true,"x":1}',
                "[]", "not json"):
        with pytest.raises(LinePolicyError):
            parse_line_policy(bad)


def test_missing_policy_resolves_fail_closed_and_wildcard_is_not_config_authority():
    assert resolve_line_policy("http://nobody:3000", "default") is UNDECLARED
    register_line_policy("*", LEGACY)
    assert resolve_line_policy("http://nobody:3000").send_enabled
    assert resolve_line_policy("http://nobody:3000").config_authority is False
    register_line_policy("http://waha-assistant:3000/", SHADOW)
    assert resolve_line_policy("http://waha-assistant:3000", "default") == SHADOW


def test_registry_loads_from_env_and_rejects_bad_json():
    n = load_line_policies_from_env({"WAHA_LINE_POLICIES": '{"http://w:3000":' + SHADOW.as_json() + "}"})
    assert n == 1 and resolve_line_policy("http://w:3000") == SHADOW
    with pytest.raises(LinePolicyError):
        load_line_policies_from_env({"WAHA_LINE_POLICIES": "{oops"})


# --- the write classifier ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("method,path,expected", [
    ("post", "/api/sendText", True), ("post", "/api/sendSeen", True), ("get", "/api/sendText", True),
    ("post", "/api/reaction", True), ("put", "/api/reaction", True), ("post", "/api/startTyping", True),
    ("post", "/api/default/presence", True), ("post", "/api/default/groups", True),
    ("delete", "/api/default/chats/55119@c.us/messages/abc", True),
    ("post", "/api/default/status/text", True), ("post", "/api/somethingNew", True),
    ("get", "/api/default/chats", False), ("get", "/api/contacts/check-exists", False),
    ("get", "https://waha.test/api/files/x.jpg", False),
    ("post", "/api/sessions/default/start", False), ("put", "/api/sessions/default", False),
    ("post", "/api/sessions/default/logout", False), ("get", "/api/default/auth/qr", False),
])
def test_classifier(method, path, expected):
    assert is_whatsapp_write(method, path) is expected


# --- the choke point --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("policy", [SHADOW, UNDECLARED])
def test_disabled_line_refuses_every_write_loudly_and_records_an_event(policy):
    sink, waha = InMemoryLineEventSink(), Waha()
    c = waha.client(policy, sink)
    for coro in (c.send_text("5511999990001@c.us", "hi"), c.send_seen("5511999990001@c.us"),
                 c.create_group("g", []), c.delete_message("a@c.us", "m1"), c.leave_group("g@g.us")):
        with pytest.raises(LineWriteRefused) as e:
            run(coro)
        assert e.value.reason == ("send_disabled" if policy.declared else "no_line_policy")
    assert waha.calls == []  # nothing left the process
    assert [ev.event for ev in sink.events] == ["whatsapp.line.write_refused"] * 5
    assert "5511999990001" not in repr(list(sink.events))  # no phone numbers in events


def test_sync_path_is_guarded_too():
    waha = Waha()
    with pytest.raises(LineWriteRefused):
        waha.client(SHADOW).send_text_sync("5511999990001@c.us", "hi")
    assert waha.calls == []


def test_disabled_line_still_reads_and_runs_the_session_lifecycle():
    waha = Waha()
    c = waha.client(SHADOW)
    run(c.get_session()); run(c.list_chats()); run(c.start_session()); run(c.get_qr())
    assert {m for m, _, _ in waha.calls} == {"GET", "POST"} and len(waha.calls) == 4


def test_enabled_line_sends():
    waha = Waha()
    run(waha.client(LEGACY).send_text("5511999990001@c.us", "hi"))
    assert waha.calls[0][1] == "/api/sendText"


def test_factory_threads_policy_and_unregistered_real_line_is_fail_closed():
    real = get_whatsapp_client(base_url="http://waha.test", api_key="k")
    assert isinstance(real, WahaClient) and real.line_policy is UNDECLARED
    register_line_policy("http://waha.test", LEGACY)
    assert get_whatsapp_client(base_url="http://waha.test", api_key="k").line_policy == LEGACY
    explicit = get_whatsapp_client(base_url="http://waha.test", api_key="k", line_policy=SHADOW)
    assert explicit.line_policy == SHADOW


# --- session config is policy -----------------------------------------------------------------------------------------


def test_start_session_writes_policy_wire_keys():
    waha = Waha()
    run(waha.client(SHADOW).start_session())
    noweb = waha.calls[0][2]["config"]["noweb"]
    assert noweb["markOnline"] is False and noweb["store"] == {"enabled": True, "fullSync": False}


def test_merge_overrides_existing_with_policy_but_wildcard_keeps_them():
    existing = {"noweb": {"markOnline": True, "store": {"enabled": True, "fullSync": True}}}
    forced = _merged_session_config(existing, [], SHADOW)["config"]["noweb"]
    assert forced["markOnline"] is False and forced["store"]["fullSync"] is False
    kept = _merged_session_config(existing, [], None)["config"]["noweb"]
    assert kept["markOnline"] is True and kept["store"]["fullSync"] is True
    assert _session_config()["config"]["noweb"]["store"]["fullSync"] is True  # legacy default untouched


def test_set_webhook_on_a_policy_line_pins_presence_off():
    waha = Waha({"name": "default", "config": {"noweb": {"markOnline": True}}})
    run(waha.client(SHADOW).set_webhook("https://p.example/wh/t", ["message"]))
    put = [b for m, _, b in waha.calls if m == "PUT"][0]["config"]
    assert put["noweb"]["markOnline"] is False and put["noweb"]["store"]["fullSync"] is False


# --- auto repair ------------------------------------------------------------------------------------------------------


def test_auto_repair_false_refuses_restart_and_recover_but_not_start():
    sink, waha = InMemoryLineEventSink(), Waha()
    c = waha.client(SHADOW, sink)
    for coro in (c.restart_session(), c.recover_session()):
        with pytest.raises(LineRepairRefused):
            run(coro)
    assert waha.calls == [] and [e.event for e in sink.events] == ["whatsapp.line.repair_refused"] * 2
    run(c.start_session())  # a human-driven first pairing still works


def test_auto_repair_true_recovers():
    waha = Waha({"name": "default", "status": "WORKING", "config": {}})
    assert run(waha.client(LEGACY).recover_session())["stage"] == "already_working"


# --- read-back --------------------------------------------------------------------------------------------------------


def test_readback_flags_every_divergence_and_unreported_keys():
    good = {"status": "SCAN_QR_CODE", "config": {"noweb": {"markOnline": False, "store": {"enabled": True, "fullSync": False}}}}
    assert run(Waha(good).client(SHADOW).verify_line_policy()).ok
    bad = {"status": "SCAN_QR_CODE", "config": {"noweb": {"markOnline": True, "store": {"enabled": True}}}}
    rb = run(Waha(bad).client(SHADOW).verify_line_policy())
    assert not rb.ok and len(rb.mismatches) == 2 and "markOnline" in rb.mismatches[0]
    assert not run(Waha({"name": "default"}).client(SHADOW).verify_line_policy()).ok  # silence is not a pass


# --- Fake parity ------------------------------------------------------------------------------------------------------


def test_fake_honours_the_same_policy():
    sink = InMemoryLineEventSink()
    f = FakeWahaClient(line_policy=SHADOW, line_event_sink=sink)
    for coro in (f.send_text("a@c.us", "x"), f.send_seen("a@c.us"), f.create_group("g", []),
                 f.delete_message("a@c.us", "m"), f.leave_group("g@g.us")):
        with pytest.raises(LineWriteRefused):
            run(coro)
    with pytest.raises(LineWriteRefused):
        f.send_text_sync("a@c.us", "x")
    with pytest.raises(LineRepairRefused):
        run(f.recover_session())
    assert f.sent_messages == [] and f.seen_calls == [] and len(sink.events) == 7
    assert run(f.verify_line_policy()).ok


def test_fake_without_a_policy_stays_open_for_dev_and_fake_undeclared_is_closed():
    assert run(FakeWahaClient().send_text("a@c.us", "x"))["text"] == "x"
    with pytest.raises(LineWriteRefused):
        run(FakeWahaClient(line_policy=UNDECLARED).send_text("a@c.us", "x"))
