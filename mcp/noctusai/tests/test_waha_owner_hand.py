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
HELPER = ("/Applications/Antigravity IDE.app/Contents/Frameworks/Antigravity IDE Helper.app/Contents/MacOS/"
          "Antigravity IDE Helper --type=utility --utility-sub-type=node.mojom.NodeService --lang=en-US")
ANTIGRAVITY = ("-zsh -il", HELPER, "/Applications/Antigravity IDE.app/Contents/MacOS/Electron")


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

    __noc_test_fake__ = True

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
    def __init__(self, *, env=None, tty=(True, True), devtty=True, chain=ANTIGRAVITY,
                 answers=("shadow", "CONFIRMO"), sh="default"):
        self._env = env or {"HOME": "/Users/owner", "TERM": "xterm"}
        self._tty, self._devtty, self._chain = tty, devtty, chain
        self.tty = FakeTTY(answers)
        self.sh = FakeVps() if sh == "default" else sh
        self.grants = []

    def observe_grant(self, grant):
        self.grants.append(grant)

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
    (row,) = _rows(root)
    assert row["outcome"] == "refused" and row["policy_hash"] and row["policy_hash"] in shown
    assert "shadow" in shown and "send=disabled" in shown and "markOnline=false" in shown and "fullSync=false" in shown
    assert "personal=true" in shown and "target host : vps" in shown


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


# --- review round 1 (agents-security on cb639e012) ------------------------------------------------------------------------

TERMINAL = ("-zsh", "login -pf owner", "/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal")
ITERM = ("-zsh", "/usr/bin/login -fpl owner /Applications/iTerm.app/Contents/MacOS/ShellLauncher --launch_shell",
         "/Applications/iTerm.app/Contents/MacOS/iTermServer-3.5.4 /Users/owner/Library/iTerm2/iterm2-daemon-1.socket")
VSCODE = ("/bin/zsh -il", "/Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper.app/Contents/MacOS/"
          "Code Helper --type=utility --utility-sub-type=node.mojom.NodeService",
          "/Applications/Visual Studio Code.app/Contents/MacOS/Electron")


@pytest.mark.parametrize("chain", [ANTIGRAVITY, TERMINAL, ITERM, VSCODE])
def test_a_known_terminal_emulator_ancestor_passes_the_gate(chain):
    assert oh.human_gate(FakeIO(chain=chain)) is None


@pytest.mark.parametrize("chain", [
    # P1-a: env -i + a pty + a reparented subshell: the chain reaches launchd with no emulator at all
    ("script -q /dev/null python mcp/noctusai/cli.py --waha-instance-owner-hand apply shadow",),
    ("/usr/bin/expect -f answers.exp",),
    ("tmux new-session -d -s x",),
    ("SCREEN -dmS x",),
    ("/opt/homebrew/bin/unbuffer python cli.py",),
    ("socat - EXEC:python,pty",),
    ("python3 -c import pty; pty.spawn('/bin/zsh')",),
    ("-zsh",),
    (),
    # a denied wrapper anywhere, even under an allowed emulator
    ("-zsh", "script -q /dev/null zsh") + ANTIGRAVITY,
    ("-zsh", "tmux: server (/private/tmp/tmux-501/default)") + TERMINAL,
    ("-zsh", "screen -S x") + ITERM,
    ("-zsh", "nohup zsh") + VSCODE,
    ("-zsh", "setsid zsh") + ANTIGRAVITY,
    ("-zsh", "/usr/bin/expect -f x") + ANTIGRAVITY,
    ("-zsh", "unbuffer zsh") + ANTIGRAVITY,
    ("-zsh", "socat - EXEC:zsh,pty") + ANTIGRAVITY,
    ("-zsh", "/usr/bin/python3 -c import pty;pty.spawn('zsh')") + ANTIGRAVITY,
    ("/bin/zsh -c x", "claude") + ANTIGRAVITY,
    ("-zsh", "/Applications/Antigravity IDE.app/Contents/Resources/app/extensions/antigravity/bin/language_server_macos_arm",
     "/Applications/Antigravity IDE.app/Contents/Frameworks/Antigravity IDE Helper (Plugin).app/Contents/MacOS/"
     "Antigravity IDE Helper (Plugin) --type=utility"),
    # an extension host is not a terminal
    ("-zsh", "/Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper (Plugin).app/Contents/MacOS/"
             "Code Helper (Plugin) --type=utility"),
])
def test_the_parent_chain_is_an_allowlist_and_every_wrapper_shape_is_refused(tmp_path, chain):
    io = FakeIO(chain=chain)
    out, root = _run(tmp_path, io)
    assert out["status"] == "refused" and io.sh.cmds == [] and io.tty.out == []
    assert _rows(root)[0]["outcome"] == "refused"


def test_the_allowlist_and_denylist_are_data_documented_in_the_kb():
    kb = (MCP.parents[1] / "KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/whatsapp.md").read_text()
    labels = [lab for lab, _ in oh.TERMINAL_ALLOWLIST]
    assert {"macOS Terminal", "iTerm2", "Antigravity IDE", "VS Code"} <= set(labels)
    for lab, _ in oh.TERMINAL_ALLOWLIST + oh.CHAIN_DENYLIST:
        assert lab in kb, lab


@pytest.mark.parametrize("sh", [None, "real", "unmarked"])
def test_a_test_io_must_carry_an_explicitly_marked_fake_runner(tmp_path, sh):
    fake = FakeVps()
    runner = {None: None, "real": wi._sh, "unmarked": lambda host, cmd, timeout=90: fake(host, cmd, timeout)}[sh]
    io = FakeIO(sh=runner)
    root = _root(tmp_path)
    out = oh.owner_hand("apply", "shadow", "invalid.invalid", str(root), _test_io=io)
    assert out["status"] == "refused" and "test" in out["error"].lower()
    assert fake.cmds == [] and io.tty.out == [] and io.grants == []


def test_a_test_io_outside_a_pytest_test_is_refused(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    io = FakeIO()
    out, _ = _run(tmp_path, io)
    assert out["status"] == "refused" and io.sh.cmds == [] and io.grants == []


def test_a_forged_grant_with_the_private_key_but_no_confirmed_audit_row_is_refused(tmp_path):
    spec = wi.parse_instances(YML)
    inst = wi._inst(spec, "shadow")
    g = oh.OwnerHandGrant(line="shadow", policy_hash=oh.policy_hash(inst), host="vps", _key=oh._MINT)
    vps = FakeVps()
    out = wi._apply(spec, "shadow", "vps", True, _test_sh=vps, _owner_grant=g)
    assert out["status"] == "refused" and out["error"] == wi.PERSONAL_REFUSAL and not vps.touched
    prov = wi._provision(spec, "shadow", "vps", True, _test_sh=vps, _owner_grant=g)
    assert prov["status"] == "refused" and not vps.touched


def test_a_real_grant_is_single_use(tmp_path):
    io = FakeIO()
    out, root = _run(tmp_path, io)
    assert out["status"] == "applied" and len(io.grants) == 1
    again = FakeVps()
    reuse = wi._apply(wi.load_spec(root), "shadow", "vps", True, _test_sh=again, _owner_grant=io.grants[0])
    assert reuse["status"] == "refused" and not again.touched


def _confirmed_row(root, *, nonce, age_s, line="shadow", host="vps", phash=None):
    import datetime as dt
    inst = wi._inst(wi.parse_instances(YML), "shadow")
    ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=age_s)).replace(microsecond=0).isoformat()
    row = {"id": "t" + nonce, "ts": ts, "tool": "waha_owner_hand", "action": "apply", "line": line, "host": host,
           "policy_hash": phash or oh.policy_hash(inst), "outcome": "confirmed", "grant_digest": oh._digest(nonce),
           "who": {"git_email": "owner@example.com", "os_user": "owner"}}
    p = root / oh.LEDGER_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    return inst


def test_a_grant_needs_a_fresh_matching_confirmed_row_bound_to_its_secret_nonce(tmp_path):
    inst = _confirmed_row(tmp_path, nonce="n-fresh", age_s=10)
    mk = lambda **kw: oh.OwnerHandGrant(**{"line": "shadow", "policy_hash": oh.policy_hash(inst), "host": "vps",  # noqa: E731
                                           "nonce": "n-fresh", "ledger_root": str(tmp_path), "_key": oh._MINT, **kw})
    assert oh.grant_covers(mk(), inst, "vps")
    assert not oh.grant_covers(mk(nonce="n-guess"), inst, "vps")          # the ledger holds only a digest
    assert not oh.grant_covers(mk(), inst, "other-host")
    looser = dict(inst, line_policy=dict(inst["line_policy"], auto_repair=True))
    assert not oh.grant_covers(mk(), looser, "vps") and not oh.grant_covers(mk(), inst, "vps", looser)
    _confirmed_row(tmp_path, nonce="n-old", age_s=6 * 60)
    assert not oh.grant_covers(mk(nonce="n-old"), inst, "vps")            # older than 5 minutes
    with pytest.raises(PermissionError):
        oh.OwnerHandGrant(line="shadow", policy_hash="x", host="vps")


def test_a_spooled_audit_must_read_back_or_the_action_is_refused(tmp_path):
    assert oh._audit_durable(tmp_path, {"ok": True, "status": "written"}, "abc") is None
    err = oh._audit_durable(tmp_path, {"ok": False, "status": "pending"}, "abc")
    assert err and "read back" in err
    p = tmp_path / oh.LEDGER_REL
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"id": "abc", "outcome": "confirmed"}) + "\n")
    assert oh._audit_durable(tmp_path, {"ok": False, "status": "pending"}, "abc") is None
    assert oh._audit_durable(tmp_path, {"ok": False, "status": "error", "error": "x"}, "abc")


def test_offline_the_confirmed_row_is_spooled_read_back_and_its_id_shown_on_the_terminal(tmp_path, ledger_repo):
    import subprocess as sp
    _bare, clone, _show = ledger_repo
    sp.run(["git", "remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=clone, check=True)
    io = FakeIO()
    out = oh.owner_hand("provision", "shadow", "vps", str(_root(tmp_path / "w")), _test_io=io)
    assert out["status"] == "verified", out
    shown = "".join(io.tty.out)
    assert out["audit"]["confirmed"]["status"] == "pending"
    assert out["audit_row_id"] in shown and "spooled" in shown


def test_compose_drift_outside_the_policy_is_refused(tmp_path):
    for old, new in (("devlikeapro/waha:noweb-2026.9.2", "devlikeapro/waha:noweb-2026.9.3"),
                     ("WHATSAPP_HOOK_HMAC_KEY", "WHATSAPP_HOOK_HMAC_KEY_X"),
                     ("/app/.sessions", "/app/.sessions2"),
                     ("nginx:1.27-alpine", "nginx:1.28-alpine")):
        compose = FakeVps().compose.replace(old, new)
        assert compose != FakeVps().compose
        io = FakeIO(sh=FakeVps(compose=compose))
        out = oh.owner_hand("apply", "shadow", "vps", str(_root(tmp_path / old.replace("/", "_"))), _test_io=io)
        assert out["status"] == "refused" and "compose" in out["error"] and not io.sh.touched and io.tty.out == []
