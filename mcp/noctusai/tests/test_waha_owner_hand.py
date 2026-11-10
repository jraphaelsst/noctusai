"""The owner-by-hand path for a PERSONAL WAHA line (D49): CLI-only, human-gated, audited; the MCP surface still refuses."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import waha_instance as wi  # noqa: E402
from tools.noctus.dev import waha_owner_hand as oh  # noqa: E402

MCP = Path(__file__).resolve().parents[1]
YML = """image: devlikeapro/waha:noweb-2026.9.2
platform: linux/amd64
engine: NOWEB
mem_limit: 512m
node_heap_mb: 384
instances:
  - name: monica
    product: monica
    line_policy: {send: enabled, mark_online: true, full_sync: true, auto_repair: true}
  - name: shadow
    product: assistant-x
    line_policy: {send: disabled, mark_online: false, full_sync: false, auto_repair: false}
    edge_deny_writes: true
    webhook_upstream: http://assistant-x:8030
    dashboard: false
    personal: true
"""
RUNNING = {"exists": False}


class FakeTTY:
    def __init__(self, answers):
        self.answers, self.out, self.closed = list(answers), [], False

    def write(self, s):
        self.out.append(s)

    def flush(self):
        pass

    def readline(self):
        return (self.answers.pop(0) + "\n") if self.answers else ""

    def close(self):
        self.closed = True


class FakeVps:
    """The VPS through the remote runner: its checkout (yml + rendered compose) and the WAHA core."""

    def __init__(self, vps_yml=YML, compose=None, labels="true"):
        self.vps_yml = vps_yml
        self.compose = compose if compose is not None else wi.render_compose(wi.parse_instances(vps_yml))
        self.labels, self.cmds = labels, []

    def __call__(self, host, cmd, timeout=90):
        self.cmds.append(cmd)
        if cmd.startswith("cat ") and cmd.endswith("waha-instances.yml"):
            return 0, self.vps_yml, ""
        if cmd.startswith("cat ") and cmd.endswith("compose.waha.yml"):
            return 0, self.compose, ""
        if "label=noctus.line.personal" in cmd:
            return 0, "noctus-waha-shadow-core\nnoctus-waha-shadow\n", ""
        if ".env.fleet" in cmd:
            return 0, "", ""
        if "compose -f compose.waha.yml up" in cmd:
            return 0, "started", ""
        if cmd.startswith("docker inspect -f"):
            return 0, self.labels + "\n", ""
        if "POLICY_NOWEB" in cmd:
            return 0, json.dumps({"noweb": {"markOnline": False, "store": {"enabled": True, "fullSync": False}},
                                  "webhooks": ["http://waha-shadow:3001/hook"]}), ""
        if "node -e" in cmd:
            return 0, json.dumps(RUNNING), ""
        return 1, "", "unexpected: " + cmd

    @property
    def touched(self):
        return any("POLICY_NOWEB" in c or " up -d " in c for c in self.cmds)


class FakeIO:
    def __init__(self, *, env=None, tty=(True, True), devtty=True, chain=("-zsh", "login -pf owner"),
                 answers=("shadow", "CONFIRMO"), sh=None):
        self._env = env or {"HOME": "/Users/owner", "TERM": "xterm"}
        self._tty, self._devtty, self._chain = tty, devtty, chain
        self.tty = FakeTTY(answers)
        self.sh = sh if sh is not None else FakeVps()

    def env(self):
        return dict(self._env)

    def isatty(self, fd):
        return self._tty[0] if fd == 0 else self._tty[1]

    def open_tty(self):
        if not self._devtty:
            raise OSError("no tty")
        return self.tty

    def parent_commands(self):
        return None if self._chain is None else list(self._chain)

    def git_email(self):
        return "owner@example.com"

    def os_user(self):
        return "owner"


def _root(tmp_path, yml=YML):
    d = tmp_path / "deploy" / "fleet"
    d.mkdir(parents=True)
    (d / "waha-instances.yml").write_text(yml)
    return tmp_path


def _rows(root):
    p = root / oh.LEDGER_REL
    return [json.loads(ln) for ln in p.read_text().splitlines()] if p.exists() else []


def _run(tmp_path, io, action="apply", name="shadow", yml=YML):
    root = _root(tmp_path, yml)
    return oh.owner_hand(action, name, "vps", str(root), _test_io=io), root


# --- the human gate -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("tty", [(False, True), (True, False), (False, False)])
def test_refuses_without_a_tty_on_stdin_and_stdout_touching_nothing_and_audits(tmp_path, tty):
    io = FakeIO(tty=tty)
    out, root = _run(tmp_path, io)
    assert out["status"] == "refused" and "terminal" in out["error"]
    assert io.sh.cmds == [] and io.tty.out == []
    (row,) = _rows(root)
    assert row["outcome"] == "refused" and row["line"] == "shadow" and row["action"] == "apply"
    assert row["who"] == {"git_email": "owner@example.com", "os_user": "owner"} and row["host"] == "vps"


@pytest.mark.parametrize("var", ["CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_ANYTHING"])
def test_refuses_inside_an_agent_harness_for_any_claude_code_env(tmp_path, var):
    io = FakeIO(env={"HOME": "/h", var: "1"})
    out, root = _run(tmp_path, io)
    assert out["status"] == "refused" and var in out["error"] and io.sh.cmds == []
    assert _rows(root)[0]["outcome"] == "refused"


def test_refuses_when_dev_tty_cannot_be_opened(tmp_path):
    out, _ = _run(tmp_path, FakeIO(devtty=False))
    assert out["status"] == "refused" and "/dev/tty" in out["error"]


@pytest.mark.parametrize("chain", [("-zsh", "/usr/local/bin/claude --resume"),
                                   ("node /opt/lib/node_modules/@anthropic-ai/claude-code/cli.js",), None])
def test_refuses_with_claude_in_the_parent_chain_or_an_unreadable_chain(tmp_path, chain):
    io = FakeIO(chain=chain)
    out, _ = _run(tmp_path, io)
    assert out["status"] == "refused" and io.sh.cmds == []


def test_the_real_io_refuses_under_the_test_runner(tmp_path):
    # no injection: whatever this process is (pytest under a harness, captured fds), it is not a human at a TTY
    out = oh.owner_hand("apply", "shadow", "vps", str(tmp_path))
    assert out["status"] == "refused"


# --- the typed confirmation ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("answers", [("shadow-x", "CONFIRMO"), ("", "CONFIRMO"), ("shadow", "confirmo"),
                                     ("shadow", "yes"), ("shadow",)])
def test_a_wrong_typed_name_or_word_does_nothing_and_is_audited(tmp_path, answers):
    io = FakeIO(answers=answers)
    out, root = _run(tmp_path, io)
    assert out["status"] == "refused" and not io.sh.touched and io.tty.closed
    shown = "".join(io.tty.out)
    assert "shadow" in shown and oh.policy_hash(wi._inst(wi.parse_instances(YML), "shadow")) in shown
    assert "send=disabled" in shown and "markOnline=false" in shown and "fullSync=false" in shown
    assert "personal=true" in shown and "target host : vps" in shown
    (row,) = _rows(root)
    assert row["outcome"] == "refused" and row["policy_hash"]


def test_apply_runs_core_provision_edge_and_audits_confirmed_then_outcome(tmp_path):
    io = FakeIO()
    out, root = _run(tmp_path, io)
    assert out["ok"] is True and out["status"] == "applied" and out["owner_hand"] is True
    ups = [c for c in io.sh.cmds if " up -d " in c]
    assert ups[0].endswith("waha-shadow-core") and ups[1].endswith("waha-shadow") and len(ups) == 2
    i_core, i_prov, i_edge = (io.sh.cmds.index(ups[0]),
                              next(i for i, c in enumerate(io.sh.cmds) if "POLICY_NOWEB" in c),
                              io.sh.cmds.index(ups[1]))
    assert i_core < i_prov < i_edge
    prov = next(c for c in io.sh.cmds if "POLICY_NOWEB" in c)
    assert '"markOnline":false' in prov and '"fullSync":false' in prov
    rows = _rows(root)
    assert [r["outcome"] for r in rows] == ["confirmed", "applied"]
    assert all(r["policy_hash"] == out["policy_hash"] for r in rows)
    assert not any(ch.isdigit() and len(ch) > 6 for r in rows for ch in json.dumps(r).split('"'))  # no phone-like runs


def test_provision_only(tmp_path):
    io = FakeIO()
    out, root = _run(tmp_path, io, action="provision")
    assert out["status"] == "verified" and not any(" up -d " in c for c in io.sh.cmds)
    assert [r["outcome"] for r in _rows(root)] == ["confirmed", "verified"]


def test_apply_reports_label_drift_when_the_live_containers_lack_the_label(tmp_path):
    io = FakeIO(sh=FakeVps(labels="<no value>"))
    out, root = _run(tmp_path, io)
    assert out["ok"] is False and out["status"] == "label_drift"
    assert _rows(root)[-1]["outcome"] == "label_drift"


# --- every other safety check stays -------------------------------------------------------------------------------------


def test_the_vps_checkout_must_declare_the_identical_policy(tmp_path):
    vps = FakeVps(vps_yml=YML.replace("auto_repair: false}\n    edge", "auto_repair: true}\n    edge"))
    io = FakeIO(sh=vps)
    out, _ = _run(tmp_path, io)
    assert out["status"] == "refused" and "deploy_pull" in out["error"] and io.tty.out == [] and not vps.touched


def test_the_vps_compose_must_label_core_and_edge_and_keep_the_core_off_noctus_net(tmp_path):
    bad = FakeVps().compose.replace('      noctus.line.personal: "true"\n', "", 1)
    io = FakeIO(sh=FakeVps(compose=bad))
    out, _ = _run(tmp_path, io)
    assert out["status"] == "refused" and "label" in out["error"] and not io.sh.touched


@pytest.mark.parametrize("edit", [("personal: true", "personal: false"),
                                  ("mark_online: false, full_sync: false, auto_repair: false}\n    edge",
                                   "mark_online: false, full_sync: true, auto_repair: false}\n    edge")])
def test_only_the_strict_personal_shadow_shape_is_accepted(tmp_path, edit):
    yml = YML.replace(*edit)
    io = FakeIO(sh=FakeVps(vps_yml=yml))
    out, _ = _run(tmp_path, io, yml=yml)
    assert out["status"] == "refused" and "strict read-only personal line" in out["error"] and not io.sh.touched


def test_unknown_action_and_remove_are_refused(tmp_path):
    out, _ = _run(tmp_path, FakeIO(), action="remove")
    assert out["status"] == "refused" and "provision|apply" in out["error"]


# --- the grant, the MCP surface, the registry ---------------------------------------------------------------------------


def test_a_grant_cannot_be_built_outside_the_gate_and_covers_only_its_line_host_and_hash():
    with pytest.raises(PermissionError):
        oh.OwnerHandGrant(line="shadow", policy_hash="x", host="vps")
    inst = wi._inst(wi.parse_instances(YML), "shadow")
    g = oh.OwnerHandGrant(line="shadow", policy_hash=oh.policy_hash(inst), host="vps", _key=oh._MINT)
    assert oh.grant_covers(g, inst, "vps") and not oh.grant_covers(g, inst, "other-host")
    looser = dict(inst, line_policy=dict(inst["line_policy"], auto_repair=True))
    assert not oh.grant_covers(g, looser, "vps") and not oh.grant_covers(g, inst, "vps", looser)


def test_the_mcp_surface_still_refuses_a_personal_line(tmp_path):
    root = _root(tmp_path)
    for action in ("provision", "apply"):
        out = wi.waha_instance(action=action, name="shadow", ssh_host="vps", confirm=True, repo_root=str(root))
        assert out["status"] == "refused" and out["error"] == wi.PERSONAL_REFUSAL
    assert "--waha-instance-owner-hand" in wi.PERSONAL_REFUSAL
    import inspect
    assert "_owner_grant" not in inspect.signature(wi.waha_instance).parameters


class _RecordingServer:
    def __init__(self):
        self.names, self.handlers = [], []

    def tool(self, *, name, description="", **_kw):
        def deco(fn):
            self.names.append(name)
            self.handlers.append(fn)
            return fn
        return deco

    def __getattr__(self, attr):  # any other server hook the registrars touch is a no-op here
        return lambda *a, **k: (lambda fn: fn)


def test_the_owner_hand_entry_is_not_in_the_mcp_tool_registry():
    from tools.noctus import register_all
    srv = _RecordingServer()
    register_all(srv)
    assert "noctus.dev.waha_instance" in srv.names and len(srv.names) > 100
    assert not [n for n in srv.names if "owner" in n.lower() and "hand" in n.lower()]
    assert not any(getattr(h, "__module__", "").endswith("waha_owner_hand") for h in srv.handlers)
    assert not hasattr(oh, "register")
    assert "waha_owner_hand" not in (MCP / "tools/noctus/dev/__init__.py").read_text()


def test_the_cli_never_passes_the_test_injection():
    src = (MCP / "cli.py").read_text()
    start = src.index("elif args.waha_instance_owner_hand:")
    branch = src[start:src.index("elif args.", start + 10)]
    assert "_owner_hand(" in branch and "_test_io" not in branch and "_test_sh" not in branch
