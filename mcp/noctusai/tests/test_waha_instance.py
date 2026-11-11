"""noctus.dev.waha_instance + check_waha_instances_render_sync: one WAHA Core container per number, as data."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import waha_instance as wi  # noqa: E402
from tools.noctus.dev.compliance import check_waha_instances_render_sync  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
DATA = """image: devlikeapro/waha:noweb-2026.9.2
platform: linux/amd64
engine: NOWEB
mem_limit: 512m
node_heap_mb: 384
instances:
  - name: monica
    product: monica
    line_policy: {send: enabled, mark_online: true, full_sync: true, auto_repair: true}
  - name: two-b
    product: other
    line_policy: {send: enabled, mark_online: false, full_sync: false, auto_repair: false}
"""
EDGE = DATA + """  - name: probe
    product: assistant-x
    line_policy: {send: disabled, mark_online: false, full_sync: false, auto_repair: false}
    edge_deny_writes: true
    webhook_upstream: http://assistant-x:8030
    dashboard: false
    personal: false
"""


def _tree(tmp_path, data=DATA, compose="render"):
    d = tmp_path / "deploy" / "fleet"
    d.mkdir(parents=True)
    (d / "waha-instances.yml").write_text(data)
    ro = tmp_path / wi.READ_ONLY_REL
    ro.parent.mkdir(parents=True, exist_ok=True)
    ro.write_text(wi.render_read_only_lines(wi.parse_instances(data)))
    if compose == "render":
        (d / "compose.waha.yml").write_text(wi.render_compose(wi.parse_instances(data)))
    elif compose is not None:
        (d / "compose.waha.yml").write_text(compose)
    return tmp_path


class TestRender:
    def test_one_service_volume_and_key_set_per_instance(self):
        out = wi.render_compose(wi.parse_instances(DATA))
        for n, up in (("monica", "MONICA"), ("two-b", "TWO_B")):
            assert f"  waha-{n}:" in out and f"container_name: noctus-waha-{n}" in out
            assert f"${{WAHA_{up}_API_KEY:?" in out and f"${{WAHA_{up}_HMAC_SECRET:?" in out
        assert out.count("expose:") == 2 and "ports:" not in out
        assert "mem_limit: 512m" in out and "healthcheck:" in out and "restart: unless-stopped" in out
        # The NOWEB store is a per-session setting the product sends on start; WAHA has no env for it,
        # and an env-autostarted session would come up without it.
        assert "NOWEB_STORE" not in out and "START_SESSION" not in out

    def test_no_secret_value_is_ever_rendered(self):
        assert "openssl" not in wi.render_compose(wi.parse_instances(DATA))

    @pytest.mark.parametrize("bad", [DATA.replace("noweb-2026.9.2", "latest"), DATA.replace("monica", "Bad Name", 1),
                                     DATA + "  - name: monica\n    product: x\n"])
    def test_invalid_declarations_raise(self, bad):
        with pytest.raises(ValueError):
            wi.parse_instances(bad)


class TestWahaInstancesRenderSync:
    def test_in_sync(self, tmp_path):
        assert check_waha_instances_render_sync(repo_root=_tree(tmp_path)) == []

    def test_hand_edit_is_drift(self, tmp_path):
        root = _tree(tmp_path)
        p = root / "deploy/fleet/compose.waha.yml"
        p.write_text(p.read_text().replace("512m", "9g"))
        assert check_waha_instances_render_sync(repo_root=root)[0]["symbol"] == "waha-instances-render-drift"

    def test_missing_compose_is_drift(self, tmp_path):
        assert check_waha_instances_render_sync(repo_root=_tree(tmp_path, compose=None))

    def test_real_repo_is_in_sync(self):
        assert check_waha_instances_render_sync(repo_root=REPO) == []


class TestActions:
    def test_apply_dry_run_touches_no_ssh(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wi, "run_remote", lambda *a, **k: pytest.fail("ssh in dry-run"))
        r = wi.waha_instance("apply", name="monica", repo_root=str(_tree(tmp_path)))
        assert r["status"] == "planned" and r["env_fleet_keys_to_generate_on_vps"][0] == "WAHA_MONICA_API_KEY"

    def test_apply_blocks_when_keys_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(wi, "run_remote", lambda *a, **k: (
            (0, DATA, "") if "waha-instances.yml" in a[1] else (0, "", "") if "label=noctus.line.personal" in a[1]
        else (3, "MISSING:WAHA_MONICA_API_KEY", "")))
        r = wi.waha_instance("apply", name="monica", confirm=True, repo_root=str(_tree(tmp_path)))
        assert r["status"] == "blocked"

    @staticmethod
    def _clean_vps(monkeypatch):
        monkeypatch.setattr(wi, "run_remote", lambda *a, **k: (0, DATA, "") if "waha-instances.yml" in a[1] else (0, "", ""))

    def test_remove_refuses_working_session(self, tmp_path, monkeypatch):
        self._clean_vps(monkeypatch)
        monkeypatch.setattr(wi, "_session_status", lambda *a: "WORKING")
        r = wi.waha_instance("remove", name="monica", confirm=True, repo_root=str(_tree(tmp_path)))
        assert r["status"] == "blocked"

    def test_remove_dry_run_snapshots_volume_first(self, tmp_path, monkeypatch):
        self._clean_vps(monkeypatch)
        monkeypatch.setattr(wi, "_session_status", lambda *a: "STOPPED")
        r = wi.waha_instance("remove", name="monica", repo_root=str(_tree(tmp_path)))
        assert r["status"] == "planned" and "tar czf" in r["steps"][0]

    def test_unknown_instance_errors(self, tmp_path):
        assert wi.waha_instance("plan", name="nope", repo_root=str(_tree(tmp_path)))["status"] == "error"


class TestLinePolicy:
    def test_policy_is_required_no_default(self):
        with pytest.raises(ValueError, match="line_policy"):
            wi.parse_instances(DATA.replace(
                "    line_policy: {send: enabled, mark_online: true, full_sync: true, auto_repair: true}\n", "", 1))

    @pytest.mark.parametrize("bad", [
        "{send: enabled, mark_online: true, full_sync: true}",
        "{send: maybe, mark_online: true, full_sync: true, auto_repair: true}",
        "{send: enabled, mark_online: yes-please, full_sync: true, auto_repair: true}",
        "{send: enabled, mark_online: true, full_sync: true, auto_repair: true, extra: 1}",
    ])
    def test_malformed_policy_raises(self, bad):
        import re
        with pytest.raises(ValueError):
            wi.parse_instances(re.sub(r"line_policy: \{send: enabled, mark_online: true.*\}", f"line_policy: {bad}", DATA, 1))

    def test_send_disabled_requires_edge_and_no_dashboard(self):
        for broken in (EDGE.replace("    edge_deny_writes: true\n", ""), EDGE.replace("    dashboard: false\n", "")):
            with pytest.raises(ValueError, match="send: disabled"):
                wi.parse_instances(broken)
        with pytest.raises(ValueError, match="contradicts"):
            wi.parse_instances(DATA.replace("product: monica\n", "product: monica\n    edge_deny_writes: true\n", 1))

    def test_env_value_matches_the_seed_as_json_byte_for_byte(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "lp", REPO / "seed/lib/backend/noctusai_lib/integrations/whatsapp/line_policy.py")
        lp = importlib.util.module_from_spec(spec)
        sys.modules["lp"] = lp  # dataclasses resolve the module by name
        spec.loader.exec_module(lp)
        for inst in wi.parse_instances(EDGE)["instances"]:
            assert wi.line_policy_json(inst) == lp.parse_line_policy(wi.line_policy_json(inst)).as_json()

    def test_plan_prints_the_product_env_contract(self):
        plan = wi._plan(wi.parse_instances(EDGE), "probe")
        c = plan["product_env_contract"]
        assert c["ASSISTANT_X_WAHA_LINE_POLICY"] == (
            '{"send":"disabled","mark_online":false,"full_sync":false,"auto_repair":false,'
            '"webhook_relay":"http://waha-probe:3001"}')
        assert c["ASSISTANT_X_WAHA_BASE_URL"] == "http://waha-probe:3000"
        assert plan["services"] == ["waha-probe-core", "waha-probe"]
        assert "WAHA_PROBE_DASHBOARD_PASSWORD" not in plan["env_fleet_keys_to_generate_on_vps"]


class TestEdgeAndDashboard:
    def test_plain_instances_render_unchanged_dashboard_on(self):
        out = wi.render_compose(wi.parse_instances(DATA))
        assert "WAHA_DASHBOARD_PASSWORD" in out and "nginx" not in out and "waha-monica-core" not in out

    def test_edge_instance_renders_proxy_in_front_and_dashboard_off(self):
        import yaml
        d = yaml.safe_load(wi.render_compose(wi.parse_instances(EDGE)))
        sv = d["services"]
        assert set(sv) == {"waha-monica", "waha-two-b", "waha-probe-core", "waha-probe"}
        core, edge = sv["waha-probe-core"], sv["waha-probe"]
        assert core["environment"]["WAHA_DASHBOARD_ENABLED"] == "false"
        assert core["environment"]["WHATSAPP_SWAGGER_ENABLED"] == "false"
        assert not any("PASSWORD" in k for k in core["environment"])
        assert edge["image"].startswith("nginx:") and edge["container_name"] == "noctus-waha-probe"
        assert "waha-probe-core:3000" in edge["environment"]["EDGE_CONF"]
        assert "ports" not in core and "ports" not in edge
        # item 8: the core is on a PRIVATE network only (nothing on noctus-net can skip the edge); the edge bridges both
        assert core["networks"] == ["waha_probe_edge"] and edge["networks"] == ["noctus-net", "waha_probe_edge"]
        assert d["networks"]["waha_probe_edge"] == {"name": "noctus-waha-probe-edge"}
        # what was judged is what is forwarded: the normalised $uri, never the raw request line
        assert "proxy_pass $$up$$uri$$is_args$$args;" in edge["environment"]["EDGE_CONF"]
        assert "set $$hook http://assistant-x:8030;" in edge["environment"]["EDGE_CONF"]

    def test_edge_requires_a_webhook_upstream(self):
        with pytest.raises(ValueError, match="webhook_upstream"):
            wi.parse_instances(EDGE.replace("    webhook_upstream: http://assistant-x:8030\n", ""))

    def test_rendered_edge_decision_table_equals_the_seed_classifier(self):
        """Evaluate the rendered nginx `map` (first regex match wins, `~*` = case-insensitive) over a path matrix and
        compare it with the seed's `is_whatsapp_write` -- the two enforcement layers must not drift."""
        import importlib.util
        import re
        import yaml
        spec = importlib.util.spec_from_file_location(
            "lp2", REPO / "seed/lib/backend/noctusai_lib/integrations/whatsapp/line_policy.py")
        lp = importlib.util.module_from_spec(spec)
        sys.modules["lp2"] = lp
        spec.loader.exec_module(lp)
        conf = yaml.safe_load(wi.render_compose(wi.parse_instances(EDGE)))["services"]["waha-probe"]["environment"][
            "EDGE_CONF"].replace("$$", "$")
        block = re.search(r"map \"[^\"]+\" \$wa_write \{(.*?)\n\}", conf, re.S).group(1)
        rules = re.findall(r'^\s*(default|"~\* (.*?)")\s+(\d);', block, re.M)

        import posixpath
        from urllib.parse import unquote

        def edge_denies(method: str, uri: str) -> bool:
            # nginx's $uri: percent-decoded and dot-resolved BEFORE the map sees it
            subject = f"{method} {posixpath.normpath(unquote(uri))}"
            for key, rx, val in rules:  # nginx `map`: regex keys in order of appearance; `default` is the fallback
                if key != "default" and re.search(rx, subject, re.I):
                    return val == "1"
            return next(val for key, _rx, val in rules if key == "default") == "1"

        matrix = [(m, p) for m in ("GET", "HEAD", "OPTIONS", "POST", "PUT", "DELETE", "PATCH") for p in (
            "/api/sendText", "/api/sendseen", "/API/SENDTEXT", "/api/sendText/", "/api/reaction", "/api/startTyping",
            "/api/default/presence", "/api/default/groups", "/api/default/chats", "/api/default/chats/1/messages/2",
            "/api/contacts/check-exists", "/api/files/x.jpg", "/api/sessions", "/api/sessions/default",
            "/api/sessions/default/start", "/api/sessionsX", "/api/default/auth/qr", "/ping", "/api/unknown",
            "/api/default/status/text", "/api/default/profile/name",
            "/api/default/presence/5511999990001@c.us", "/api/default/presence",
            "/api/sessions/default/logout", "/api/sessions/default/stop", "/api/sessions/default/restart",
            "/api/sessions/../sendText", "/api/default/chats/../../sendText", "/api/sessions/default/start/../../../sendSeen",
            "/api/default/chats/%2e%2e/%2e%2e/sendText", "/api/SESSIONS/default/START",
        )]
        for method, path in matrix:
            assert edge_denies(method, path) is lp.is_whatsapp_write(method, path), (method, path)

    def test_repo_declares_monica_explicitly(self):
        monica = [i for i in wi.load_spec(REPO)["instances"] if i["name"] == "monica"][0]
        assert monica["line_policy"] == {"send": "enabled", "mark_online": True, "full_sync": True, "auto_repair": True}


class TestProdComposeCarriesThePolicy:
    def _root(self, tmp_path, prod_env):
        root = _tree(tmp_path)
        (root / "deploy/fleet/docker-compose.prod.yml").write_text(
            "services:\n  monica:\n    environment:\n      MONICA_WAHA_BASE_URL: http://waha-monica:3000\n" + prod_env)
        return root

    def test_missing_policy_env_is_flagged(self, tmp_path):
        out = check_waha_instances_render_sync(repo_root=self._root(tmp_path, ""))
        assert [i["symbol"] for i in out] == ["waha-line-policy-env-drift"]

    def test_wrong_policy_env_is_flagged_and_exact_value_passes(self, tmp_path):
        bad = "      MONICA_WAHA_LINE_POLICY: '{\"send\":\"disabled\",\"mark_online\":true,\"full_sync\":true,\"auto_repair\":true}'\n"
        assert check_waha_instances_render_sync(repo_root=self._root(tmp_path / "a", bad))
        good = "      MONICA_WAHA_LINE_POLICY: '{\"send\":\"enabled\",\"mark_online\":true,\"full_sync\":true,\"auto_repair\":true}'\n"
        assert check_waha_instances_render_sync(repo_root=self._root(tmp_path / "b", good)) == []


class TestActiveProductsDeclarePolicy:
    def _tree(self, tmp_path, svc_env: str):
        root = _tree(tmp_path)
        (root / "deploy/fleet/active-scope.txt").write_text("core\nshop\n")
        app = root / "products/shop/backend/app"
        app.mkdir(parents=True)
        (app / "x.py").write_text("from noctusai_lib.integrations.whatsapp import get_whatsapp_client\n")
        (root / "deploy/fleet/docker-compose.prod.yml").write_text(
            "services:\n  shop:\n    image: x\n    environment:\n      A: b\n" + svc_env + "  other:\n    image: y\n")
        return root

    def test_a_deployed_product_that_builds_waha_clients_without_a_policy_is_flagged(self, tmp_path):
        out = check_waha_instances_render_sync(repo_root=self._tree(tmp_path, ""))
        assert [i["symbol"] for i in out] == ["waha-product-without-line-policy"]

    def test_either_declaration_form_passes(self, tmp_path):
        for n, env in enumerate(("      SHOP_WAHA_LINE_POLICY: '{}'\n", "      WAHA_LINE_POLICIES: '{}'\n")):
            assert check_waha_instances_render_sync(repo_root=self._tree(tmp_path / str(n), env)) == []


class TestRound2Edge:
    def _conf(self):
        import yaml
        d = yaml.safe_load(wi.render_compose(wi.parse_instances(EDGE)))
        return d["services"]["waha-probe"]["environment"]["EDGE_CONF"].replace("$$", "$")

    def test_smuggling_spellings_are_rejected_with_400_on_both_ports_and_the_seed_agrees(self):
        import importlib.util
        import re
        spec = importlib.util.spec_from_file_location(
            "lp3", REPO / "seed/lib/backend/noctusai_lib/integrations/whatsapp/line_policy.py")
        lp = importlib.util.module_from_spec(spec)
        sys.modules["lp3"] = lp
        spec.loader.exec_module(lp)
        conf = self._conf()
        rxs = re.findall(r'if \(\$request_uri ~\* "(.*?)"\) \{ return 400; \}', conf)
        assert len(rxs) == 2 and rxs[0] == rxs[1]  # API server AND the webhook relay
        rx = rxs[0]
        bad = ["/api/sessions/logout%3F/start", "/api/sessions/default/start%3f", "/api/sessions/default%0D%0A/start",
               "/api/sessions/default%0a", "/api/sessions/a%5Cb/start", "/api/sessions/a%5cb", "/api/sessions/a%2Fb/start",
               "/api/sessions/a%23b/start", "/api/sessions/%00", "/api/sessions/%7f", "/api/sessions/%25", "/x\\y"]
        for uri in bad:
            assert re.search(rx, uri, re.I), uri
            assert lp.is_whatsapp_write("post", uri.replace("\\", "\\")), uri
        for good in ("/api/default/auth/qr?format=image", "/api/sessions/default/start", "/api/default/chats",
                     "/api/sessions/%2e%2e/x", "/hooks/abc",
                     # N6: the QUERY is not judged (the seed judges the path only) -- %20 %26 %2F there are legitimate
                     "/api/default/chats?search=a%20b", "/api/contacts?x=a%26b", "/api/files?path=%2Ftmp%2Fx",
                     "/api/default/auth/qr?format=image&n=%0d"):
            assert not re.search(rx, good, re.I), good

    def test_method_override_headers_are_stripped_on_both_servers(self):
        conf = self._conf()
        for h in ("X-HTTP-Method-Override", "X-HTTP-Method", "X-Method-Override"):
            assert conf.count(f'proxy_set_header {h} "";') == 2

    def test_the_relay_url_is_part_of_the_policy_and_the_read_only_set_covers_every_alias(self):
        import json
        spec = wi.parse_instances(EDGE)
        probe = [i for i in spec["instances"] if i["name"] == "probe"][0]
        assert json.loads(wi.line_policy_json(probe))["webhook_relay"] == "http://waha-probe:3001"
        text = wi.render_read_only_lines(spec)
        ns: dict = {}
        exec(text, ns)  # noqa: S102 - the generated module, under test
        rows = ns["READ_ONLY_LINES"]
        for host in ("waha-probe", "noctus-waha-probe", "waha-probe-core", "noctus-waha-probe-core"):
            for port in (3000, 3001):
                assert rows[f"{host}:{port}"]["send"] == "disabled", (host, port)
        assert not any(k.startswith(("waha-monica", "noctus-waha-monica")) for k in rows)  # enabled lines are not listed
        assert "READ_ONLY_LINES: dict[str, dict] = {}" in wi.render_read_only_lines(wi.parse_instances(DATA))

    def test_the_repo_read_only_module_is_the_render(self):
        assert (REPO / wi.READ_ONLY_REL).read_text() == wi.render_read_only_lines(wi.load_spec(REPO))

    def test_provision_script_runs_for_real_against_a_waha_shaped_server(self, tmp_path):
        """Executes the exact JS `provision` runs inside the core, against a local server with WAHA's semantics
        (404 until created; /start ignores its body; markOnline defaults true)."""
        import json
        import shutil
        import subprocess
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        if not shutil.which("node"):
            pytest.skip("node not available")
        state: dict = {"s": None, "calls": []}

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                raw = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n) or b"{}")

            def do_GET(self):
                state["calls"].append(("GET", self.path, self.headers.get("X-Api-Key")))
                self._send(404 if state["s"] is None else 200, state["s"] or {})

            def do_POST(self):
                b = self._body()
                state["calls"].append(("POST", self.path, b.get("start")))
                state["s"] = {"name": b["name"], "config": b["config"]}
                self._send(201, state["s"])

            def do_PUT(self):
                b = self._body()
                state["calls"].append(("PUT", self.path, None))
                state["s"]["config"] = b["config"]
                self._send(200, state["s"])

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        inst = wi.parse_instances(EDGE)["instances"][2]
        want = wi.policy_noweb(inst)
        env = {"PATH": "/usr/bin:/bin:/opt/homebrew/bin", "WHATSAPP_API_KEY": "k", "POLICY_SESSION": "default",
               "POLICY_NOWEB": json.dumps(want), "POLICY_BASE": f"http://127.0.0.1:{srv.server_port}"}
        assert "'" not in wi._PROVISION_JS
        outs = [subprocess.run([shutil.which("node"), "-e", wi._PROVISION_JS], env=env, capture_output=True, text=True,
                               timeout=60) for _ in range(2)]  # twice: create, then idempotent PUT
        srv.shutdown()
        assert [o.returncode for o in outs] == [0, 0], [o.stdout + o.stderr for o in outs]
        assert wi._noweb_matches(json.loads(outs[1].stdout.strip().splitlines()[-1])['noweb'], want)
        posts = [c for c in state["calls"] if c[0] == "POST"]
        assert len(posts) == 1 and posts[0][2] is False and all(c[2] in ("k", False, None) for c in state["calls"])
        assert any(c[0] == "PUT" for c in state["calls"])


# --- round 3: provision is tighten-only, owner-consented for personal lines ---------------------------------------------

PERSONAL = EDGE.replace("    personal: false\n", "    personal: true\n", 1)


class FakeVps:
    """The VPS as seen through `_sh` (DI): its own checkout of waha-instances.yml + the running core."""

    def __init__(self, vps_yml: str, running: dict):
        self.vps_yml, self.running, self.cmds = vps_yml, running, []

    def __call__(self, host, cmd, timeout=90):
        self.cmds.append(cmd)
        if cmd.startswith("cat ") and "waha-instances.yml" in cmd:
            return 0, self.vps_yml, ""
        if "node -e" in cmd and "POLICY_NOWEB" not in cmd:
            return 0, json.dumps(self.running), ""
        if "POLICY_NOWEB" in cmd:
            relay = "http://waha-probe:3001"
            return 0, json.dumps({"noweb": {"markOnline": False, "store": {"enabled": True, "fullSync": False}},
                                  "webhooks": [f"{relay}/hook"]}), ""
        return 1, "", "unexpected"

    @property
    def wrote(self):
        return any("POLICY_NOWEB" in c for c in self.cmds)


import json  # noqa: E402

EXISTING = {"exists": True, "noweb": {"markOnline": True, "store": {"enabled": False, "fullSync": False}}, "webhooks": []}


def _prov(caller_yml, vps, **kw):
    return wi._provision(wi.parse_instances(caller_yml), "probe", "h", kw.pop("confirm", True), _test_sh=vps, **kw)


def test_a_branch_that_loosens_markonline_cannot_be_written_onto_the_core():
    loose = EDGE.replace("{send: disabled, mark_online: false,", "{send: disabled, mark_online: true,")
    vps = FakeVps(EDGE, EXISTING)
    out = _prov_loose = wi._provision(wi.parse_instances(loose.replace("send: disabled, mark_online: true", "send: disabled, mark_online: true")),
                                      "probe", "h", True, _test_sh=vps)
    assert out["status"] == "refused" and "markOnline" in out["error"] and "VPS" in out["error"]
    assert not vps.wrote


def test_loosening_vs_the_running_session_is_refused_naming_the_field():
    vps = FakeVps(EDGE, {"exists": True, "noweb": {"markOnline": False, "store": {"enabled": True, "fullSync": False}},
                         "webhooks": []})
    loose = EDGE.replace("full_sync: false,", "full_sync: true,")
    vps.vps_yml = loose  # the VPS agrees with the caller: only the RUNNING session is tighter
    out = wi._provision(wi.parse_instances(loose), "probe", "h", True, _test_sh=vps)
    assert out["status"] == "refused" and "store.fullSync" in out["error"] and "running" in out["error"]
    assert not vps.wrote


def test_an_unknown_vps_ceiling_refuses():
    vps = FakeVps(DATA, EXISTING)  # the VPS does not declare `probe`
    out = _prov(EDGE, vps)
    assert out["status"] == "refused" and "deploy_pull" in out["error"] and not vps.wrote


def test_tightening_an_untouched_default_session_writes_and_verifies_the_relay_webhooks():
    vps = FakeVps(EDGE, EXISTING)
    out = _prov(EDGE, vps)
    assert out["status"] == "verified" and out["foreign_webhooks"] == [] and vps.wrote
    dry = _prov(EDGE, FakeVps(EDGE, EXISTING), confirm=False)
    assert dry["status"] == "planned"


def test_a_foreign_webhook_surviving_the_write_is_drift():
    class Evil(FakeVps):
        def __call__(self, host, cmd, timeout=90):
            rc, out, err = super().__call__(host, cmd, timeout)
            if "POLICY_NOWEB" in cmd:
                d = json.loads(out); d["webhooks"].append("https://evil.example/h"); out = json.dumps(d)
            return rc, out, err

    out = _prov(EDGE, Evil(EDGE, EXISTING))
    assert out["status"] == "drift" and out["foreign_webhooks"] == ["https://evil.example/h"]


def test_a_personal_line_is_refused_outright_whatever_the_flags_or_any_transcript_say():
    vps = FakeVps(PERSONAL, EXISTING)
    for confirm in (True, False):
        out = _prov(PERSONAL, FakeVps(PERSONAL, EXISTING), confirm=confirm)
        assert out["status"] == "refused" and out["error"] == wi.PERSONAL_REFUSAL and out["needs_owner_by_hand"] is True
    assert not vps.wrote and vps.cmds == []  # refused BEFORE any ssh: not even a read
    assert wi.PERSONAL_REFUSAL.startswith("personal line: refused for every agent and tool caller")
    assert "--waha-instance-owner-hand <provision|apply> <line>" in wi.PERSONAL_REFUSAL
    # no transcript path remains at all: the helper and the parameter are gone
    assert not hasattr(wi, "_owner_consent") and "consent_session_id" not in wi.waha_instance.__code__.co_varnames


def test_personal_on_the_vps_checkout_alone_also_refuses():
    # caller's checkout says non-personal, the VPS says personal
    out = _prov(EDGE, FakeVps(PERSONAL, EXISTING))
    assert out["status"] == "refused" and out["needs_owner_by_hand"] is True


def test_apply_on_a_personal_line_starts_nothing_and_is_refused():
    out = wi._apply(wi.parse_instances(PERSONAL), "probe", "h", True)
    assert out["status"] == "refused" and out["error"] == wi.PERSONAL_REFUSAL


def test_a_send_disabled_line_must_declare_personal_explicitly():
    with pytest.raises(ValueError, match="personal"):
        wi.parse_instances(EDGE.replace("    personal: false\n", ""))
    wi.parse_instances(EDGE)  # declared false: fine
    wi.parse_instances(PERSONAL)  # declared true: parses (provisioning is what is refused)
    wi.parse_instances(DATA)      # enabled lines need not declare it


def test_the_test_only_runner_is_absent_from_the_public_function_and_the_tool_schema():
    import inspect
    assert "_test_sh" not in inspect.signature(wi.waha_instance).parameters
    assert "_test_sh" in inspect.signature(wi._provision).parameters and "TEST-ONLY" in wi._provision.__doc__


# --- round 5: label stamp, apply reads the VPS first, resolvable aliases ----------------------------------------------------


def test_a_personal_line_stamps_the_live_container_label_on_core_and_edge_and_others_do_not():
    import yaml
    d = yaml.safe_load(wi.render_compose(wi.parse_instances(PERSONAL)))["services"]
    for svc in ("waha-probe-core", "waha-probe"):
        assert d[svc]["labels"] == {"noctus.line.personal": "true"}, svc
    plain = yaml.safe_load(wi.render_compose(wi.parse_instances(EDGE)))["services"]
    assert all("labels" not in v for v in plain.values())


def test_apply_reads_the_vps_yml_before_any_compose_up_and_the_strictest_wins():
    calls = []

    def sh_personal_on_vps(host, cmd, timeout=90):
        calls.append(cmd)
        return (0, PERSONAL, "") if cmd.startswith("cat ") else (0, "", "")

    out = wi._apply(wi.parse_instances(EDGE), "probe", "h", True, _test_sh=sh_personal_on_vps)
    assert out["status"] == "refused" and out["error"] == wi.PERSONAL_REFUSAL
    assert len(calls) == 1 and calls[0].startswith("cat ")  # nothing was started

    calls.clear()

    def sh_unreadable(host, cmd, timeout=90):
        calls.append(cmd)
        return (1, "", "no such file")

    out = wi._apply(wi.parse_instances(EDGE), "probe", "h", True, _test_sh=sh_unreadable)
    assert out["status"] == "refused" and "ceiling is unknown" in out["error"]
    assert all("compose" not in c for c in calls)


def test_only_edge_names_are_declared_resolvable_from_the_product_network():
    ns: dict = {}
    exec(wi.render_read_only_lines(wi.parse_instances(EDGE)), ns)  # noqa: S102 - the generated module under test
    assert ns["RESOLVABLE_FROM_PRODUCT_NETWORK"] == ("noctus-waha-probe", "waha-probe")
    assert "waha-probe-core:3000" in ns["READ_ONLY_LINES"]  # the core is still matched BY NAME


def test_apply_refuses_when_only_the_live_label_says_personal_and_when_the_label_lookup_fails():
    calls = []

    def sh_label(host, cmd, timeout=90):
        calls.append(cmd)
        if cmd.startswith("cat "):
            return 0, EDGE, ""                      # the VPS yml says NOT personal
        if "label=noctus.line.personal=true" in cmd:
            return 0, "noctus-waha-probe-core\n", ""  # the live core is stamped personal
        return 0, "", ""

    out = wi._apply(wi.parse_instances(EDGE), "probe", "h", True, _test_sh=sh_label)
    assert out["status"] == "refused" and out["error"] == wi.PERSONAL_REFUSAL
    assert all("compose" not in c for c in calls)

    def sh_label_down(host, cmd, timeout=90):
        if cmd.startswith("cat "):
            return 0, EDGE, ""
        return (1, "", "daemon down") if "label=" in cmd else (0, "", "")

    out = wi._apply(wi.parse_instances(EDGE), "probe", "h", True, _test_sh=sh_label_down)
    assert out["status"] == "refused" and "fail closed" in out["error"]


def _remove_sh(calls, vps_yml=EDGE, label_rc=0, label_out=""):
    def sh(host, cmd, timeout=90):
        calls.append(cmd)
        if cmd.startswith("cat "):
            return (0, vps_yml, "") if vps_yml is not None else (1, "", "no such file")
        if "label=noctus.line.personal" in cmd:
            return label_rc, label_out, "denied" if label_rc else ""
        return 0, "", ""
    return sh


@pytest.mark.parametrize("confirm,force", [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize("source", ["local", "vps", "label", "unreadable_vps", "unreadable_label"])
def test_remove_refuses_a_personal_line_before_any_stop_or_tar(source, confirm, force, monkeypatch):
    monkeypatch.setattr(wi, "_session_status", lambda *a: pytest.fail("session looked up before the personal check"))
    calls: list = []
    kw = {"vps_yml": PERSONAL if source == "vps" else None if source == "unreadable_vps" else EDGE}
    if source == "label":
        kw.update(label_out="noctus-waha-probe-core\n")
    if source == "unreadable_label":
        kw.update(label_rc=1)
    local = PERSONAL if source == "local" else EDGE
    out = wi._remove(wi.parse_instances(local), "probe", "h", confirm, force, _test_sh=_remove_sh(calls, **kw))
    assert out["status"] == "refused" and out["action"] == "remove", out
    assert all("tar czf" not in c and "rm -sf" not in c for c in calls)


def test_remove_of_a_non_personal_line_still_plans_and_runs(monkeypatch):
    monkeypatch.setattr(wi, "_session_status", lambda *a: "STOPPED")
    calls: list = []
    out = wi._remove(wi.parse_instances(EDGE), "probe", "h", True, False, _test_sh=_remove_sh(calls))
    assert out["status"] == "removed" and any("tar czf" in c for c in calls)
