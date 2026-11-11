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
from noctusai_lib.integrations.whatsapp.line_policy import set_generated_read_only, set_host_resolver
from noctusai_lib.integrations.whatsapp.client import WahaClient, _merged_session_config, _session_config

SHADOW = LinePolicy("disabled", False, False, False)
SHADOW_R = LinePolicy("disabled", False, False, False, webhook_relay="http://waha-x:3001")
RELAY_URL = "http://waha-x:3001/api/whatsapp/webhook/tok"
PROVISIONED = {"name": "default", "status": "SCAN_QR_CODE",
               "config": {"noweb": {"markOnline": False, "store": {"enabled": True, "fullSync": False}}}}
LEGACY = LinePolicy("enabled", True, True, True)


@pytest.fixture(autouse=True)
def _no_legacy_wildcard():
    clear_line_policies()  # overrides the package autouse: these tests start from an EMPTY registry (fail-closed)
    set_host_resolver(None)  # ... and from the real DNS view, not the hermetic one the pytest plugin installs
    set_generated_read_only({})  # ... and an EMPTY generated set: they declare their own read-only lines at runtime
    yield
    clear_line_policies()
    set_host_resolver(None)


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
    waha = Waha(PROVISIONED)
    c = waha.client(SHADOW)
    run(c.get_session()); run(c.list_chats()); run(c.start_session()); run(c.get_qr())
    assert {m for m, _, _ in waha.calls} == {"GET", "POST"} and len(waha.calls) == 5  # get_qr reads the session back first


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
    run(waha.client(SHADOW_R).set_webhook(RELAY_URL, ["message"]))
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
    run(f.provision_session())
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
    assert not run(f.verify_line_policy()).ok  # nothing reported, not a pass
    run(f.start_session())  # WAHA's /start takes NO body: it never becomes the config
    assert not run(f.verify_line_policy()).ok
    assert run(f.provision_session()).ok and run(f.verify_line_policy()).ok
    f.session_noweb["markOnline"] = True  # drift on the "server"
    assert not run(f.verify_line_policy()).ok


def test_undeclared_line_start_writes_the_all_off_flags_not_wahas_defaults():
    waha = Waha()
    run(waha.client(UNDECLARED).start_session())
    noweb = waha.calls[0][2]["config"]["noweb"]
    assert noweb["markOnline"] is False and noweb["store"]["fullSync"] is False
    f = FakeWahaClient(line_policy=UNDECLARED)
    run(f.start_session())
    assert f.last_start_payload["config"]["noweb"]["markOnline"] is False


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
    waha, sink = Waha(PROVISIONED), InMemoryLineEventSink()
    c = waha.client(SHADOW, sink)
    run(c.get_session()); run(c.start_session()); run(c.get_qr())
    for m, path in (("put", "/api/sessions/default"), ("post", "/api/sessions/default/stop"),
                    ("delete", "/api/sessions/default"), ("post", "/api/sessions/default/restart")):
        with pytest.raises(LineWriteRefused):
            run(c._request(m, path, timeout=5, json={"config": {"noweb": {"markOnline": True}}}))
    with pytest.raises(LineRepairRefused):
        run(c.logout_session())
    assert [m for m, _, _ in waha.calls] == ["GET", "POST", "GET", "GET"]


def test_the_only_config_write_on_a_disabled_line_is_the_policy_derived_one():
    waha = Waha({"name": "default", "config": {"noweb": {"markOnline": True}}})
    run(waha.client(SHADOW_R).set_webhook(RELAY_URL, ["message"]))
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


# --- round 2: WAHA takes config only on create/PUT, smuggling spellings, sticky read-only, webhook relay -------------------

from noctusai_lib.integrations.whatsapp import LinePolicyDrift  # noqa: E402


class RealisticWaha:
    """WAHA's real session-config semantics: POST /start takes NO body and never touches config; NOWEB's markOnline
    defaults to TRUE; config is set only by POST /api/sessions (create) or PUT /api/sessions/{s}."""

    DEFAULT = {"noweb": {"markOnline": True, "store": {"enabled": False, "fullSync": False}}}

    def __init__(self):
        self.state = None
        self.calls: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        import json

        m, p = request.method, request.url.path
        body = json.loads(request.content) if request.content else {}
        self.calls.append((m, p))
        if m == "GET" and p == "/api/sessions/default":
            return httpx.Response(404, json={}) if self.state is None else httpx.Response(200, json=self.state)
        if m == "POST" and p == "/api/sessions":
            self.state = {"name": body["name"], "status": "STOPPED", "config": body.get("config", {})}
        elif m == "PUT" and p == "/api/sessions/default":
            self.state["config"] = body["config"]
        elif m == "POST" and p == "/api/sessions/default/start":
            if self.state is None:
                self.state = {"name": "default", "status": "SCAN_QR_CODE", "config": dict(self.DEFAULT)}
            self.state["status"] = "SCAN_QR_CODE"  # body IGNORED
        elif m == "GET" and p == "/api/default/auth/qr":
            return httpx.Response(200, content=b"PNG")
        return httpx.Response(200, json=self.state or {})

    def client(self, policy):
        return WahaClient("http://waha.test", "k", "default", transport=httpx.MockTransport(self), line_policy=policy)


def test_start_alone_leaves_markonline_true_and_pairing_is_refused_until_provisioned():
    w = RealisticWaha()
    c = w.client(SHADOW_R)
    run(c.start_session())
    assert w.state["config"]["noweb"]["markOnline"] is True  # what WAHA really does
    with pytest.raises(LinePolicyDrift) as e:
        run(c.get_qr())
    assert "markOnline" in str(e.value)
    assert ("GET", "/api/default/auth/qr") not in w.calls  # the QR was never even requested


def test_provision_creates_with_start_false_then_pairing_is_allowed():
    w = RealisticWaha()
    c = w.client(SHADOW_R)
    rb = run(c.provision_session())
    assert rb.ok and w.state["config"]["noweb"]["markOnline"] is False
    run(c.start_session())
    assert run(c.get_qr()) == b"PNG"
    assert w.state["config"]["noweb"] == {"markOnline": False, "store": {"enabled": True, "fullSync": False}}


def test_provision_is_idempotent_and_repairs_an_existing_session():
    w = RealisticWaha()
    w.state = {"name": "default", "status": "STOPPED", "config": dict(RealisticWaha.DEFAULT)}
    c = w.client(SHADOW_R)
    assert run(c.provision_session()).ok and run(c.provision_session()).ok
    assert [x for x in w.calls if x[0] == "POST" and x[1] == "/api/sessions"] == []  # exists -> PUT, never a 2nd create
    assert w.state["config"]["noweb"]["markOnline"] is False


def test_provision_needs_a_declared_config_authoritative_line():
    with pytest.raises(LineRepairRefused):
        run(RealisticWaha().client(UNDECLARED).provision_session())


def test_the_edge_class_config_calls_are_still_refused_for_everyone_else():
    w = RealisticWaha()
    c = w.client(SHADOW_R)
    for m, path in (("post", "/api/sessions"), ("put", "/api/sessions/default")):
        with pytest.raises(LineWriteRefused):
            run(c._request(m, path, timeout=5, json={"config": {}}))
    assert w.calls == []


@pytest.mark.parametrize("path", [
    "/api/sessions/logout%3F/start", "/api/sessions/default/start%3F", "/api/sessions/default%0D%0A/start",
    "/api/sessions/default%5Cstart", "/api/sessions/a%2Fb/start", "/api/sessions/default%23/start",
    "/api/sessions/default%00/start", "/api/sessions/default%7F/start", "/api/sessions/default%25/start",
    "/api/sessions/a\\b/start",
])
def test_smuggling_spellings_are_writes_whatever_they_decode_to(path):
    assert is_whatsapp_write("post", path) is True
    waha = Waha()
    with pytest.raises(LineWriteRefused):
        run(waha.client(SHADOW)._request("post", path, timeout=5))
    assert waha.calls == []


def test_presence_subscribe_on_get_is_a_write():
    assert is_whatsapp_write("get", "/api/default/presence/5511999990001@c.us") is True
    assert is_whatsapp_write("get", "/api/default/chats") is False


# --- sticky read-only ------------------------------------------------------------------------------------------------


def test_a_read_only_host_stays_read_only_whatever_star_explicit_or_spelling_say():
    set_host_resolver(lambda h: {"other": ["10.0.0.9"], "waha-x": ["10.0.0.5"]}.get(h))
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    register_line_policy("*", LEGACY)
    for spelling in ("http://waha-x:3000", "http://WAHA-X:3000/", "waha-x:3000", "http://waha-x:3000/api/x"):
        assert not resolve_line_policy(spelling, "default").send_enabled, spelling
        assert not resolve_line_policy(spelling, "default", explicit=LEGACY).send_enabled  # explicit cannot loosen
    assert resolve_line_policy("http://other:3000").send_enabled  # "*" still serves everybody else
    c = get_whatsapp_client(base_url="http://WAHA-X:3000/", api_key="k", line_policy=LEGACY)
    assert not c.line_policy.send_enabled


def test_re_registering_a_read_only_host_with_a_looser_policy_is_refused_but_tightening_is_fine():
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    for loose in (LEGACY, LinePolicy("disabled", True, False, False)):
        with pytest.raises(LinePolicyError, match="sticky|loosen"):
            register_line_policy("http://waha-x:3000", loose, allow_memory_sink=True)
    with pytest.raises(LinePolicyError):
        register_line_policy("WAHA-X:3000", LEGACY)  # another spelling of the same host
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)  # identical is fine
    assert not resolve_line_policy("http://waha-x:3000").auto_repair


def test_strictest_is_the_and_of_every_flag():
    from noctusai_lib.integrations.whatsapp import strictest

    s = strictest(LEGACY, LinePolicy("enabled", False, True, False))
    assert (s.send, s.mark_online, s.full_sync, s.auto_repair) == ("enabled", False, True, False)
    assert strictest(LEGACY, SHADOW_R).webhook_relay == "http://waha-x:3001"


def test_the_generated_read_only_host_set_is_loadable():
    from noctusai_lib.integrations.whatsapp import read_only_lines

    assert isinstance(read_only_lines.READ_ONLY_LINES, dict)
    for spec in read_only_lines.READ_ONLY_LINES.values():
        assert parse_line_policy(spec).send_enabled is False


# --- webhooks on a disabled line -------------------------------------------------------------------------------------


@pytest.mark.parametrize("policy,url", [
    (SHADOW_R, "https://evil.example/wh"), (SHADOW_R, "http://waha-x:3001.evil.example/a"),
    (SHADOW_R, "http://waha-x:3000/api/x"), (SHADOW, RELAY_URL), (UNDECLARED, RELAY_URL),
])
def test_set_and_remove_webhook_on_a_disabled_line_only_accept_the_declared_relay(policy, url):
    waha, sink = Waha({"name": "default", "config": {}}), InMemoryLineEventSink()
    c = waha.client(policy, sink)
    with pytest.raises(LineWriteRefused):
        run(c.set_webhook(url, ["message"]))
    with pytest.raises(LineWriteRefused):
        run(c.remove_webhook(url))
    assert waha.calls == [] and len(sink.events) == 2
    f = FakeWahaClient(line_policy=policy)
    with pytest.raises(LineWriteRefused):
        run(f.set_webhook(url, ["message"]))
    with pytest.raises(LineWriteRefused):
        run(f.remove_webhook(url))


def test_relay_url_is_accepted_and_fake_logout_is_guarded():
    f = FakeWahaClient(line_policy=SHADOW_R)
    run(f.set_webhook(RELAY_URL, ["message"]))
    with pytest.raises(LineRepairRefused):
        run(f.logout_session())
    with pytest.raises(LinePolicyDrift):
        run(f.get_qr())  # the Fake gates pairing on the read-back too
    run(f.provision_session())
    run(f.get_qr()) if f.session_status == "SCAN_QR_CODE" else None


# --- no phone numbers in logs ----------------------------------------------------------------------------------------


def test_no_run_of_eight_digits_reaches_a_whatsapp_log_line(caplog):
    import logging
    import re

    from noctusai_lib.integrations.whatsapp.log_safety import mask_chat_id

    assert mask_chat_id("5511999990001@c.us") == "…0001@c.us" and mask_chat_id("abc") == "abc"

    def handler(request):
        if request.url.path.endswith("check-exists"):
            raise httpx.ConnectError("boom for " + str(request.url))  # the URL (with the phone) is in the message
        return httpx.Response(500, json={}, request=request)

    c = WahaClient("http://waha.test", "k", "default", transport=httpx.MockTransport(handler), line_policy=LEGACY)
    with caplog.at_level(logging.DEBUG):
        try:
            c.send_text_to_phone_sync("5511999990001", "hi")
        except Exception:  # noqa: BLE001 - every variant fails on purpose; the logs are what is under test
            pass
        logging.getLogger("noctusai_lib.integrations.whatsapp.identity").warning(
            "x lid=%s", "5511999990001@lid", exc_info=(ValueError, ValueError("GET /api/contacts?id=5511999990001@c.us"), None))
    assert caplog.records, "the failure paths must have logged"
    assert not re.search(r"\d{8,}", caplog.text), caplog.text


# --- round 3: address-level aliases, relay ceiling, missing ceiling -----------------------------------------------------

DNS = {"waha-x": ["10.0.0.5"], "waha-x-core": ["10.0.0.6"], "noctus-waha-x": ["10.0.0.5"],
       "social": ["10.0.0.20"], "abc123def456": ["10.0.0.6"], "ip6": ["fd00::5"]}


def _declare_shadow():
    set_host_resolver(lambda h: DNS.get(h))
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    register_line_policy("http://waha-x-core:3000", SHADOW_R, allow_memory_sink=True)
    register_line_policy("*", LEGACY)


@pytest.mark.parametrize("url", [
    "http://waha-x.:3000",            # trailing dot
    "http://WAHA-X.:3000/",
    "http://10.0.0.5:3000",           # the edge's container IP
    "http://10.0.0.6:3000",           # the core's container IP
    "http://abc123def456:3000",       # container id (docker DNS) resolving to the core
    "http://noctus-waha-x:3000",      # container_name alias
])
def test_every_alias_of_a_read_only_machine_stays_read_only_even_with_a_star(url):
    _declare_shadow()
    assert not resolve_line_policy(url, "default").send_enabled, url
    assert not get_whatsapp_client(base_url=url, api_key="k").line_policy.send_enabled


def test_an_unrelated_resolvable_host_still_gets_the_star():
    _declare_shadow()
    assert resolve_line_policy("http://social:3000").send_enabled


def test_an_unresolvable_host_fails_closed_unless_positively_known_send_enabled():
    _declare_shadow()
    assert not resolve_line_policy("http://nowhere.invalid:3000").send_enabled  # "*" alone is not "positively known"
    register_line_policy("http://nowhere.invalid:3000", LEGACY)  # an explicit, non-star, enabled declaration is
    assert resolve_line_policy("http://nowhere.invalid:3000").send_enabled


def test_a_process_with_no_read_only_line_does_no_dns_at_all():
    def boom(h):
        raise AssertionError("no DNS expected")

    set_host_resolver(boom)
    register_line_policy("*", LEGACY)
    assert resolve_line_policy("http://anything.invalid:3000").send_enabled


def test_ipv6_literals_and_brackets_are_normalised():
    _declare_shadow()
    register_line_policy("http://ip6:3000", SHADOW_R, allow_memory_sink=True)
    assert not resolve_line_policy("http://[fd00::5]:3000").send_enabled


def test_the_declared_relay_is_authoritative_and_a_different_one_is_refused():
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    other = LinePolicy("disabled", False, False, False, webhook_relay="http://evil:3001")
    with pytest.raises(LinePolicyError):
        register_line_policy("http://waha-x:3000", other, allow_memory_sink=True)
    with pytest.raises(LinePolicyError):
        register_line_policy("http://waha-x:3000", SHADOW, allow_memory_sink=True)  # dropping the relay is a change too
    # an explicit policy naming another relay cannot redirect webhooks either
    got = resolve_line_policy("http://waha-x:3000", explicit=other)
    assert got.webhook_relay is None or got.webhook_relay == "http://waha-x:3001"
    c = get_whatsapp_client(base_url="http://waha-x:3000", api_key="k", line_policy=other)
    with pytest.raises(LineWriteRefused):
        run(c.set_webhook("http://evil:3001/hook", ["message"]))


def test_a_missing_generated_ceiling_raises_instead_of_meaning_none():
    from noctusai_lib.integrations.whatsapp.line_policy import _generated_read_only

    with pytest.raises(LinePolicyError, match="missing"):
        _generated_read_only("noctusai_lib.integrations.whatsapp.no_such_generated_module")


# --- no phone number in an exception message or a log record (owner-line pass) ----------------------------------------------


def test_exception_messages_and_logs_never_carry_a_phone_on_5xx_then_404(caplog):
    import logging
    import re

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path.endswith("check-exists"):
            return httpx.Response(503, json={}, request=request)  # the check endpoint is down: 5xx
        return httpx.Response(404, json={"error": "no"}, request=request)  # then every send variant: 404

    c = WahaClient("http://waha.test", "k", "default", transport=httpx.MockTransport(handler), line_policy=LEGACY)
    caught: list[BaseException] = []
    with caplog.at_level(logging.DEBUG):
        for call in (lambda: c.send_text_to_phone_sync("5511999990001", "hi"),
                     lambda: run(c.send_text_to_phone("5511999990001", "hi")),
                     lambda: run(c.check_exists("5511999990001")),
                     lambda: run(c.resolve_chat_id("5511999990001"))):
            try:
                call()
            except Exception as exc:  # noqa: BLE001 - every variant fails on purpose; the messages are under test
                caught.append(exc)
    assert caught and caplog.records
    phone = re.compile(r"\+?\d{10,}")
    for rec in caplog.records:
        assert not phone.search(rec.getMessage()), rec.getMessage()
        assert not phone.search(rec.exc_text or ""), rec.exc_text
    for exc in caught:
        chain = [exc, exc.__cause__, exc.__context__]
        for e in filter(None, chain):
            assert not phone.search(str(e)), (type(e).__name__, str(e))
    from noctusai_lib.integrations.whatsapp import WahaNumberCheckError, WahaNumberNotOnWhatsApp

    e1 = WahaNumberCheckError("5511999990001", 503, "GET /x?phone=5511999990001")
    e2 = WahaNumberNotOnWhatsApp(["5511999990001", "551199990001"])
    assert not phone.search(str(e1)) and not phone.search(str(e2)) and not phone.search(repr(e2.tried))
    assert e1._phone == "5511999990001" and e2._tried == ["5511999990001", "551199990001"]  # raw kept privately


def test_me_is_a_public_read_allowed_on_a_read_only_line():
    waha = Waha({"id": "5511999990001@c.us", "pushName": "Owner"})
    c = waha.client(SHADOW)
    assert run(c.me())["pushName"] == "Owner" and c.me_sync()["pushName"] == "Owner"
    assert [m for m, _, _ in waha.calls] == ["GET", "GET"] and all(p.endswith("/me") for _, p, _ in waha.calls)
    assert is_whatsapp_write("get", "/api/sessions/default/me") is False
    f = FakeWahaClient(line_policy=SHADOW)
    assert run(f.me()) == {}
    f.simulate_pair(phone="5511999990001")
    assert run(f.me())["id"] == "5511999990001@c.us"


# --- round 4: address cache TTL, re-resolve at request time, unresolvable alias, mapped IPv6 ------------------------------


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_the_address_cache_expires_so_a_recreated_container_cannot_hide_behind_an_old_ip():
    clock, dns = Clock(), {"waha-x": ["10.0.0.5"], "social": ["10.0.0.20"]}
    set_host_resolver(lambda h: dns.get(h), _test_clock=clock)
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    register_line_policy("*", LEGACY)
    assert resolve_line_policy("http://social:3000").send_enabled            # cached: social -> 10.0.0.20
    dns["social"] = ["10.0.0.5"]                                              # the container is recreated onto waha-x's IP
    assert resolve_line_policy("http://social:3000").send_enabled            # still inside the TTL
    clock.t += 61
    assert not resolve_line_policy("http://social:3000").send_enabled        # re-resolved: it IS the read-only machine now


def test_a_live_client_re_resolves_in_the_final_url_hook_before_the_request_leaves():
    clock, dns = Clock(), {"waha-x": ["10.0.0.5"], "social": ["10.0.0.20"]}
    set_host_resolver(lambda h: dns.get(h), _test_clock=clock)
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    register_line_policy("*", LEGACY)
    seen: list[str] = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={})

    c = WahaClient("http://social:3000", "k", "default", transport=httpx.MockTransport(handler))
    assert c.line_policy.send_enabled
    run(c.send_text("a@c.us", "ok"))
    dns["social"] = ["10.0.0.5"]
    clock.t += 61
    with pytest.raises(LineWriteRefused):
        run(c.send_text("a@c.us", "now refused"))
    assert seen == ["/api/sendText"]  # only the first one left


def test_an_unresolvable_read_only_alias_fails_closed_for_ip_literals_and_unknown_hosts():
    set_host_resolver(lambda h: {"social": ["10.0.0.20"]}.get(h))      # waha-x does NOT resolve here
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    register_line_policy("*", LEGACY)
    assert not resolve_line_policy("http://10.0.0.5:3000").send_enabled   # could be waha-x: closed
    assert not resolve_line_policy("http://who-knows:3000").send_enabled  # unresolvable host: closed (N2)
    register_line_policy("http://social:3000", LEGACY)                    # positively known send-enabled
    assert resolve_line_policy("http://social:3000").send_enabled


def test_a_down_read_only_edge_does_not_take_every_resolvable_sender_down_with_it():
    """The edge container being down/restarting makes its alias unresolvable. A product whose host RESOLVES (a different
    machine) and is covered by "*" must keep sending: the read-only alias cannot be that host (if the edge were up, its
    name would resolve; if it is down, nothing answers there). IP literals stay closed (previous test)."""
    set_host_resolver(lambda h: {"social": ["10.0.0.20"], "waha": ["10.0.0.30"]}.get(h))   # waha-x is DOWN
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    register_line_policy("*", LEGACY)                                    # the only entry a shared-host sender has
    assert resolve_line_policy("http://social:3000").send_enabled
    assert resolve_line_policy("http://waha:3000", "default").send_enabled
    assert not resolve_line_policy("http://waha-x:3000").send_enabled    # the read-only line itself: still closed, by name
    assert not resolve_line_policy("http://10.0.0.5:3000").send_enabled  # an IP literal could be it: still closed
    assert not resolve_line_policy("http://who-knows:3000").send_enabled # unresolvable request host: still closed


def test_ipv4_mapped_ipv6_is_the_ipv4_address():
    set_host_resolver(lambda h: {"waha-x": ["10.0.0.5"]}.get(h))
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    register_line_policy("*", LEGACY)
    assert not resolve_line_policy("http://[::ffff:10.0.0.5]:3000").send_enabled
    assert not resolve_line_policy("http://[::ffff:a00:5]:3000").send_enabled


# --- round 5: unrelated "*" lines keep working, failures cached, DNS off the loop, resolver only ADDS -------------------


def test_declaring_a_disabled_line_leaves_an_unrelated_star_line_sending():
    """The `-core` names never resolve from the product network; they must not poison every other host."""
    from noctusai_lib.integrations.whatsapp.line_policy import address_alias_candidates

    set_host_resolver(lambda h: {"waha-x": ["10.0.0.5"], "social": ["10.0.0.20"], "wahahost": ["10.0.0.30"]}.get(h))
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    register_line_policy("*", LEGACY)
    assert resolve_line_policy("http://social:3000").send_enabled
    # the generated-set model: -core aliases are listed but NOT resolvable from noctus-net -> excluded from the address check
    all_ro = {"waha-x:3000": SHADOW_R, "waha-x-core:3000": SHADOW_R, "noctus-waha-x-core:3001": SHADOW_R}
    kept = address_alias_candidates(all_ro, all_ro, frozenset({"waha-x"}))
    assert set(kept) == {"waha-x:3000"}
    # a runtime-registered alias is always compared; a generated one only when it is declared resolvable
    assert set(address_alias_candidates({**all_ro, "late:3000": SHADOW_R}, all_ro, frozenset({"waha-x"}))) == {"waha-x:3000", "late:3000"}


def test_lookup_failures_are_cached_for_the_ttl():
    calls: list[str] = []
    clock = Clock()

    def resolver(h):
        calls.append(h)
        return None

    set_host_resolver(resolver, _test_clock=clock)
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    for _ in range(5):
        resolve_line_policy("http://ghost.invalid:3000")
    assert calls.count("ghost.invalid") == 1          # five requests, one lookup
    clock.t += 61
    resolve_line_policy("http://ghost.invalid:3000")
    assert calls.count("ghost.invalid") == 2          # re-tried after the TTL


def test_an_injected_resolver_only_adds_matches_it_cannot_hide_a_real_address():
    # `localhost` really resolves to loopback; an injected resolver that claims a different address cannot replace that
    set_host_resolver(lambda h: ["10.9.9.9"] if h == "localhost" else None)
    from noctusai_lib.integrations.whatsapp.line_policy import _addrs

    got = _addrs("localhost")
    assert "10.9.9.9" in got and ("127.0.0.1" in got or "::1" in got)


def test_the_async_hook_resolves_in_a_worker_thread_not_on_the_event_loop():
    import threading

    clock, dns = Clock(), {"waha-x": ["10.0.0.5"], "social": ["10.0.0.20"]}
    where: list[str] = []

    def resolver(h):
        where.append(threading.current_thread().name)
        return dns.get(h)

    set_host_resolver(resolver, _test_clock=clock)
    register_line_policy("http://waha-x:3000", SHADOW_R, allow_memory_sink=True)
    register_line_policy("*", LEGACY)
    c = WahaClient("http://social:3000", "k", "default",
                   transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    where.clear()
    clock.t += 61                                      # force a fresh lookup inside the request
    main = threading.current_thread().name

    async def go():
        await c.send_text("a@c.us", "x")

    asyncio.run(go())
    assert where and all(w != main for w in where), where


def test_stricter_host_policy_is_not_shadowed_by_a_looser_session_entry():
    """Security re-check 2026-11-10: resolution used `session entry or host entry`, so a looser session entry hid a
    stricter (still send-enabled) host policy. Both are consulted now and the strictest wins."""
    quiet = LinePolicy("enabled", False, False, False)
    # Order matters: registering the host first already refuses the looser session entry at write time; the exposure
    # was a session entry declared FIRST and a stricter host policy declared later.
    register_line_policy("http://waha-x:3000#default", LEGACY)
    register_line_policy("http://waha-x:3000", quiet)
    got = resolve_line_policy("http://waha-x:3000", "default")
    assert got.send_enabled
    assert got.mark_online is False and got.full_sync is False and got.auto_repair is False
