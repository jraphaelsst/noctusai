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
    register_line_policy("http://waha-assistant:3000/", SHADOW, allow_memory_sink=True)
    assert resolve_line_policy("http://waha-assistant:3000", "default") == SHADOW


def test_registry_loads_from_env_and_rejects_bad_json():
    n = load_line_policies_from_env(
        {"WAHA_LINE_POLICIES": '{"http://w:3000":' + SHADOW.as_json() + "}"}, allow_memory_sink=True)
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
    ("post", "/api/sessions/default/start", False), ("put", "/api/sessions/default", True),
    ("post", "/api/sessions/default/logout", True), ("get", "/api/default/auth/qr", False),
    ("get", "/api/sessions/default", False),
    # dot-segment smuggling: judged on the raw AND the normalised path
    ("post", "/api/sessions/../sendText", True), ("get", "/api/default/chats/../../sendText", True),
    ("post", "/api/sessions/default/start/../../../sendSeen", True),
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
    run(f.start_session())
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


def test_fake_resolves_through_the_same_registry_and_is_fail_closed():
    with pytest.raises(LineWriteRefused):
        run(FakeWahaClient().send_text("a@c.us", "x"))
    assert isinstance(get_whatsapp_client(), FakeWahaClient)
    register_line_policy("*", LEGACY)
    assert run(FakeWahaClient().send_text("a@c.us", "x"))["text"] == "x"
    assert run(get_whatsapp_client().send_text("a@c.us", "y"))["text"] == "y"


def test_fake_readback_reflects_what_start_actually_wrote_and_can_fail():
    f = FakeWahaClient(line_policy=SHADOW)
    assert not run(f.verify_line_policy()).ok  # never started: nothing reported, not a pass
    run(f.start_session())
    assert run(f.verify_line_policy()).ok
    f.session_noweb["markOnline"] = True  # drift on the "server"
    assert not run(f.verify_line_policy()).ok


def test_undeclared_line_start_writes_the_all_off_flags_not_wahas_defaults():
    waha = Waha()
    run(waha.client(UNDECLARED).start_session())
    noweb = waha.calls[0][2]["config"]["noweb"]
    assert noweb["markOnline"] is False and noweb["store"]["fullSync"] is False
    f = FakeWahaClient(line_policy=UNDECLARED)
    run(f.start_session())
    assert f.session_noweb["markOnline"] is False


# --- compliance-review fixes ------------------------------------------------------------------------------------------


class Spy(Waha):
    """A transport that records the path that ACTUALLY reached the wire."""

    def __call__(self, request):
        self.calls.append((request.method, request.url.raw_path.decode(), None))
        return httpx.Response(200, json={"name": "default", "status": "WORKING", "config": {}})


@pytest.mark.parametrize("coro_of", [
    lambda c: c.leave_group("../../sendText"),
    lambda c: c.delete_message("x", ".."),
    lambda c: c.fetch_chat_messages("../../sendText"),
])
def test_path_segments_are_percent_encoded_so_nothing_can_reroute(coro_of):
    waha = Spy()
    c = waha.client(LEGACY)
    try:
        run(coro_of(c))
    except LineWriteRefused:
        pytest.fail("enabled line must not refuse")
    assert waha.calls and all(".." not in p and "/sendText" not in p for _, p, _ in waha.calls)


def test_final_url_hook_refuses_a_path_that_only_becomes_a_write_after_httpx_normalises_it():
    """The pre-check sees an innocuous string; the request that would leave is /api/sendText. The hook judges the
    FINAL url on the real client (no patching): nothing reaches the transport."""
    waha, sink = Spy(), InMemoryLineEventSink()
    c = waha.client(SHADOW, sink)
    with pytest.raises(LineWriteRefused):
        run(c._request("get", "/api/default/chats/%2e%2e/%2e%2e/sendText", timeout=5))
    with pytest.raises(LineWriteRefused):
        run(c._request("post", "/api/sessions/default/start/../../../sendSeen", timeout=5))
    with pytest.raises(LineWriteRefused):
        c._request_sync("post", "/api/sessions/../sendText", timeout=5)
    assert waha.calls == [] and len(sink.events) == 3


def test_a_disabled_line_allows_only_sessions_get_start_and_qr():
    waha, sink = Waha(), InMemoryLineEventSink()
    c = waha.client(SHADOW, sink)
    run(c.get_session()); run(c.start_session()); run(c.get_qr())
    for m, path in (("put", "/api/sessions/default"), ("post", "/api/sessions/default/stop"),
                    ("delete", "/api/sessions/default"), ("post", "/api/sessions/default/restart")):
        with pytest.raises(LineWriteRefused):
            run(c._request(m, path, timeout=5, json={"config": {"noweb": {"markOnline": True}}}))
    with pytest.raises(LineRepairRefused):
        run(c.logout_session())
    assert [m for m, _, _ in waha.calls] == ["GET", "POST", "GET"]


def test_the_only_config_write_on_a_disabled_line_is_the_policy_derived_one():
    waha = Waha({"name": "default", "config": {"noweb": {"markOnline": True}}})
    run(waha.client(SHADOW).set_webhook("https://p.example/wh/t", ["message"]))
    assert [m for m, _, _ in waha.calls].count("PUT") == 1


# --- registry atomicity -----------------------------------------------------------------------------------------------


def test_bad_env_registers_nothing_and_keeps_failing_loudly_never_silent_undeclared(monkeypatch):
    bad = '{"http://good:3000":' + LEGACY.as_json() + ',"http://bad:3000":{"send":"enabled"}}'
    with pytest.raises(LinePolicyError):
        load_line_policies_from_env({"WAHA_LINE_POLICIES": bad})
    assert resolve_line_policy("http://good:3000") is UNDECLARED  # partial parse registered nothing
    monkeypatch.setenv("WAHA_LINE_POLICIES", bad)
    clear_line_policies()
    for _ in range(2):  # not "raises once, then silently UNDECLARED"
        with pytest.raises(LinePolicyError):
            resolve_line_policy("http://good:3000")


def test_star_cannot_carry_a_session():
    with pytest.raises(LinePolicyError):
        load_line_policies_from_env({"WAHA_LINE_POLICIES": '{"*#default":' + LEGACY.as_json() + "}"})
    with pytest.raises(LinePolicyError):
        register_line_policy("*", LEGACY, session="default")


def test_a_disabled_line_needs_a_persistent_sink_unless_a_test_says_otherwise():
    from noctusai_lib.integrations.whatsapp import set_default_line_event_sink
    from noctusai_lib.integrations.whatsapp.line_policy import get_default_line_event_sink

    with pytest.raises(LinePolicyError, match="in-memory"):
        register_line_policy("http://w:3000", SHADOW)
    register_line_policy("http://w:3000", LEGACY)  # enabled lines are not gated by this
    saved = get_default_line_event_sink()

    class Persistent:
        def record(self, event):  # a non-memory sink
            pass

    set_default_line_event_sink(Persistent())
    try:
        register_line_policy("http://w2:3000", SHADOW)
        assert resolve_line_policy("http://w2:3000") == SHADOW
    finally:
        set_default_line_event_sink(saved)
