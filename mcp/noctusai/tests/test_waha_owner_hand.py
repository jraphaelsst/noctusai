"""The owner-by-hand path for a PERSONAL WAHA line (D49): CLI-only, human-gated, audited; the MCP surface still refuses."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import waha_instance as wi  # noqa: E402
from tools.noctus.dev import waha_owner_hand as oh  # noqa: E402

MCP = Path(__file__).resolve().parents[1]
H = "noc-test.invalid"  # the reserved test host: a test IO may target nothing else
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

# --- process images and the signing requirements pinned on the owner's machine (codesign -dv, 2026-11-10) -------------
AG_HELPER = ("/Applications/Antigravity IDE.app/Contents/Frameworks/Antigravity IDE Helper.app/Contents/MacOS/"
             "Antigravity IDE Helper")
AG_PLUGIN = ("/Applications/Antigravity IDE.app/Contents/Frameworks/Antigravity IDE Helper (Plugin).app/Contents/MacOS/"
             "Antigravity IDE Helper (Plugin)")
AG_MAIN = "/Applications/Antigravity IDE.app/Contents/MacOS/Electron"
TERM = "/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal"
VSC_HELPER = "/Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper.app/Contents/MacOS/Code Helper"
VSC_MAIN = "/Applications/Visual Studio Code.app/Contents/MacOS/Code"
CLAUDE = "/Users/owner/.local/share/claude/versions/2.1.322"
PY = "/opt/homebrew/Cellar/python@3.11/3.11.6_1/Frameworks/Python.framework/Versions/3.11/Resources/Python.app/Contents/MacOS/Python"
REQ_TERM = 'anchor apple and identifier "com.apple.Terminal"'
REQ_AG_HELPER = ('anchor apple generic and identifier "com.google.antigravity-ide.helper" and '
                 'certificate leaf[subject.OU] = "EQHXZ8M8AV"')
REQ_AG_MAIN = 'anchor apple generic and identifier "com.google.antigravity-ide" and certificate leaf[subject.OU] = "EQHXZ8M8AV"'
REQ_VSC_HELPER = ('anchor apple generic and identifier "com.microsoft.VSCode.helper" and '
                  'certificate leaf[subject.OU] = "UBF8T346G9"')
REQ_VSC_MAIN = 'anchor apple generic and identifier "com.microsoft.VSCode" and certificate leaf[subject.OU] = "UBF8T346G9"'
SIGS = {1097: REQ_AG_HELPER, 699: REQ_AG_MAIN, 500: REQ_TERM, 800: REQ_VSC_HELPER, 801: REQ_VSC_MAIN}
BUNDLES = {699: "com.google.antigravity-ide", 500: "com.apple.Terminal", 801: "com.microsoft.VSCode"}

# (pid, real image, argv as the process presents it). The gate must judge the IMAGE, never the argv.
ZSH = (101, "/bin/zsh", "-zsh -il")
LOGIN = (102, "/usr/bin/login", "login -pf owner")
ANTIGRAVITY = [ZSH, (1097, AG_HELPER, AG_HELPER + " --type=utility --utility-sub-type=node.mojom.NodeService"),
               (699, AG_MAIN, AG_MAIN)]
TERMINAL = [ZSH, LOGIN, (500, TERM, TERM)]
VSCODE = [(101, "/bin/bash", "-bash"), (800, VSC_HELPER, VSC_HELPER + " --type=utility"), (801, VSC_MAIN, VSC_MAIN)]


class FakeTTY:
    def __init__(self, answers, on_read=None):
        self.answers, self.out, self.closed, self.on_read = list(answers), [], False, on_read

    def write(self, s):
        self.out.append(s)

    def flush(self):
        pass

    def readline(self):
        if self.on_read:
            self.on_read()
        return (self.answers.pop(0) + "\n") if self.answers else ""

    def close(self):
        self.closed = True


class FakeVps:
    """The VPS through the remote runner: its checkout (yml + rendered compose) and the WAHA core."""

    __noc_test_fake__ = True

    def __init__(self, vps_yml=YML, compose=None, labels="true"):
        self.vps_yml = vps_yml
        self.compose = compose if compose is not None else wi.render_compose(wi.parse_instances(vps_yml))
        self.labels, self.cmds, self.hosts = labels, [], []

    def __call__(self, host, cmd, timeout=90):
        self.cmds.append(cmd)
        self.hosts.append(host)
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
    def __init__(self, *, env=None, tty=(True, True), devtty=True, chain=ANTIGRAVITY, sigs=None, bundles=None,
                 answers=("shadow", "CONFIRMO"), sh="default", on_read=None):
        self._env = env or {"HOME": "/Users/owner", "TERM": "xterm"}
        self._tty, self._devtty = tty, devtty
        self._chain = None if chain is None else list(chain)
        self._sigs = {**SIGS, **(sigs or {})}
        self._bundles = {**BUNDLES, **(bundles or {})}
        self.tty = FakeTTY(answers, on_read)
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

    def ancestors(self):
        """(pid, real image path) from the parent up to the process launchd (pid 1) started; None = unreadable."""
        return None if self._chain is None else [(pid, img) for pid, img, _argv in self._chain]

    def parent_commands(self):  # what argv-reading code sees (attacker-controlled)
        return None if self._chain is None else [argv for _pid, _img, argv in self._chain]

    def signature_ok(self, pid, requirement):
        return self._sigs.get(pid) == requirement

    def app_bundle(self, pid):
        return self._bundles.get(pid)

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


def _run(tmp_path, io, action="apply", name="shadow", yml=YML, host=H):
    root = _root(tmp_path, yml)
    return oh.owner_hand(action, name, host, str(root), _test_io=io), root


# --- the human gate -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("tty", [(False, True), (True, False), (False, False)])
def test_refuses_without_a_tty_on_stdin_and_stdout_touching_nothing_and_audits(tmp_path, tty):
    io = FakeIO(tty=tty)
    out, root = _run(tmp_path, io)
    assert out["status"] == "refused" and "terminal" in out["error"]
    assert io.sh.cmds == [] and io.tty.out == []
    (row,) = _rows(root)
    assert row["outcome"] == "refused" and row["line"] == "shadow" and row["action"] == "apply"
    assert row["who"] == {"git_email": "owner@example.com", "os_user": "owner"} and row["host"] == H


@pytest.mark.parametrize("var", ["CLAUDECODE", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_ANYTHING"])
def test_refuses_inside_an_agent_harness_for_any_claude_code_env(tmp_path, var):
    io = FakeIO(env={"HOME": "/h", var: "1"})
    out, root = _run(tmp_path, io)
    assert out["status"] == "refused" and var in out["error"] and io.sh.cmds == []
    assert _rows(root)[0]["outcome"] == "refused"


def test_refuses_when_dev_tty_cannot_be_opened(tmp_path):
    out, _ = _run(tmp_path, FakeIO(devtty=False))
    assert out["status"] == "refused" and "/dev/tty" in out["error"]


def test_the_real_io_refuses_under_the_test_runner(tmp_path):
    # no injection: whatever this process is (pytest under a harness, captured fds), it is not a human at a TTY
    out = oh.owner_hand("apply", "shadow", "vps", str(tmp_path))
    assert out["status"] == "refused"


# --- the parent chain: real image paths, signatures, structure ---------------------------------------------------------


@pytest.mark.parametrize("chain", [ANTIGRAVITY, TERMINAL, VSCODE], ids=["antigravity", "terminal", "vscode"])
def test_the_owner_terminals_pass_the_gate(chain):
    assert oh.human_gate(FakeIO(chain=chain)) is None


REFUSED_CHAINS = {
    # review round 2, attack 1: `exec -a <Terminal path> script ...` -- argv says Terminal, the image is script
    "exec-a-terminal-argv-over-script": dict(chain=[(201, "/usr/bin/script", TERM + " -q /dev/null env -i python cli.py")]),
    # attack 2: an emulator path as an ARGUMENT of a shell
    "argv-substring": dict(chain=[(202, "/bin/sh", "sh -c true " + TERM)]),
    # attack 3: a renamed copy of script / a python pty.spawn
    "renamed-script": dict(chain=[(203, "/tmp/Terminal", TERM)]),
    "python-pty-spawn": dict(chain=[ZSH, (204, PY, "python3 /tmp/x.py " + AG_HELPER)]),
    # an emulator image at a path that is not the pinned one (a copy into a user-writable /Applications)
    "terminal-copy-in-applications": dict(chain=[ZSH, LOGIN, (205, "/Applications/Terminal.app/Contents/MacOS/Terminal",
                                                               TERM)]),
    # the pinned path, but the running pid does not satisfy the signing requirement
    "terminal-bad-signature": dict(chain=TERMINAL, sigs={500: None}),
    "antigravity-helper-bad-signature": dict(chain=ANTIGRAVITY, sigs={1097: REQ_VSC_HELPER}),
    "antigravity-main-bad-signature": dict(chain=ANTIGRAVITY, sigs={699: None}),
    # the emulator was not started by launchd (an agent ran it): something sits above it
    "terminal-under-claude": dict(chain=TERMINAL + [(206, CLAUDE, "claude")]),
    "helper-launched-by-an-agent": dict(chain=[ZSH, (1097, AG_HELPER, AG_HELPER), (207, "/bin/zsh", "zsh"),
                                               (206, CLAUDE, "claude")]),
    # the main app is not a LaunchServices-registered application (ELECTRON_RUN_AS_NODE, reparented)
    "antigravity-main-not-a-registered-app": dict(chain=ANTIGRAVITY, bundles={699: None}),
    "terminal-not-a-registered-app": dict(chain=TERMINAL, bundles={500: "com.example.other"}),
    # an IDE extension host is not a terminal
    "ide-extension-host": dict(chain=[ZSH, (209, AG_PLUGIN, AG_PLUGIN), (699, AG_MAIN, AG_MAIN)]),
    # anything but a real shell / login between the process and the emulator
    "claude-between": dict(chain=[ZSH, (206, CLAUDE, "claude"), (110, "/bin/zsh", "-zsh -il")] + ANTIGRAVITY[1:]),
    "tmux-server": dict(chain=[ZSH, (210, "/opt/homebrew/bin/tmux", "tmux: server " + TERM)]),
    "script-under-terminal": dict(chain=[ZSH, (211, "/usr/bin/script", "script -q /dev/null"), (112, "/bin/zsh", "-zsh"),
                                         LOGIN, (500, TERM, TERM)]),
    "homebrew-zsh-is-not-a-system-shell": dict(chain=[(212, "/opt/homebrew/bin/zsh", "-zsh")] + ANTIGRAVITY[1:]),
    # iTerm2 is not installed on the owner's machine: no team id was read, so nothing is pinned for it
    "iterm2-not-pinned": dict(chain=[ZSH, LOGIN, (213, "/Applications/iTerm.app/Contents/MacOS/iTermServer-3.5.4",
                                                  "iTermServer")]),
    # unreadable means refuse
    "image-unreadable": dict(chain=[(101, None, "-zsh")] + ANTIGRAVITY[1:]),
    "chain-unreadable": dict(chain=None),
    "reparented-to-launchd": dict(chain=[]),
    "shells-only-to-launchd": dict(chain=[ZSH, LOGIN]),
}


@pytest.mark.parametrize("case", sorted(REFUSED_CHAINS))
def test_every_non_terminal_chain_shape_is_refused(tmp_path, case):
    io = FakeIO(**REFUSED_CHAINS[case])
    out, root = _run(tmp_path, io)
    assert out["status"] == "refused" and io.sh.cmds == [] and io.tty.out == [] and io.grants == [], case
    assert _rows(root)[0]["outcome"] == "refused"


def test_the_terminal_allowlist_is_data_pinned_and_documented_in_the_kb():
    kb = (MCP.parents[1] / "KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/whatsapp.md").read_text()
    by_label = {e["label"]: e for e in oh.EMULATORS}
    assert set(by_label) == {"macOS Terminal", "Antigravity IDE", "VS Code"}
    assert by_label["macOS Terminal"]["entry_requirement"] == REQ_TERM and by_label["macOS Terminal"]["app"] is None
    assert by_label["Antigravity IDE"]["entry_requirement"] == REQ_AG_HELPER
    assert by_label["Antigravity IDE"]["app"]["requirement"] == REQ_AG_MAIN
    assert by_label["VS Code"]["entry_requirement"] == REQ_VSC_HELPER
    assert by_label["VS Code"]["app"]["requirement"] == REQ_VSC_MAIN
    for e in oh.EMULATORS:
        assert all(p.startswith(("/Applications/", "/System/Applications/")) for p in e["entry_images"])
        assert e["label"] in kb and e["bundle_id"] in kb
    assert oh.SHELL_IMAGES == ("/bin/zsh", "/bin/bash", "/bin/sh", "/usr/bin/login")
    for team in ("EQHXZ8M8AV", "UBF8T346G9"):
        assert team in kb


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
    assert "personal=true" in shown and f"target host : {H}" in shown


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
    assert set(io.sh.hosts) == {H}
    rows = _rows(root)
    assert [r["outcome"] for r in rows] == ["confirmed", "applied"]
    assert all(r["policy_hash"] == out["policy_hash"] for r in rows)


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


def test_compose_drift_outside_the_policy_is_refused(tmp_path):
    for old, new in (("devlikeapro/waha:noweb-2026.9.2", "devlikeapro/waha:noweb-2026.9.3"),
                     ("WHATSAPP_HOOK_HMAC_KEY", "WHATSAPP_HOOK_HMAC_KEY_X"),
                     ("/app/.sessions", "/app/.sessions2"),
                     ("nginx:1.27-alpine", "nginx:1.28-alpine")):
        compose = FakeVps().compose.replace(old, new)
        assert compose != FakeVps().compose
        io = FakeIO(sh=FakeVps(compose=compose))
        out = oh.owner_hand("apply", "shadow", H, str(_root(tmp_path / old.replace("/", "_"))), _test_io=io)
        assert out["status"] == "refused" and "compose" in out["error"] and not io.sh.touched and io.tty.out == []


# --- the test seam is not a bypass --------------------------------------------------------------------------------------


@pytest.mark.parametrize("sh", [None, "real", "unmarked"])
def test_a_test_io_must_carry_an_explicitly_marked_fake_runner(tmp_path, sh):
    fake = FakeVps()
    runner = {None: None, "real": wi._sh, "unmarked": lambda host, cmd, timeout=90: fake(host, cmd, timeout)}[sh]
    io = FakeIO(sh=runner)
    out, _ = _run(tmp_path, io)
    assert out["status"] == "refused" and "test" in out["error"].lower()
    assert fake.cmds == [] and io.tty.out == [] and io.grants == []


def test_a_test_io_outside_a_pytest_test_is_refused(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    io = FakeIO()
    out, _ = _run(tmp_path, io)
    assert out["status"] == "refused" and io.sh.cmds == [] and io.grants == []


def test_a_marked_wrapper_around_the_real_runner_cannot_reach_a_real_host(tmp_path):
    calls = []

    def wrapper(host, cmd, timeout=90):  # a marked fake that would forward to the real runner
        calls.append(host)
        return wi._sh(host, cmd, timeout)

    wrapper.__noc_test_fake__ = True
    io = FakeIO(sh=wrapper)
    out, _ = _run(tmp_path, io, host="noctus-vps")
    assert out["status"] == "refused" and H in out["error"] and calls == [] and io.grants == []


def test_a_test_io_needs_its_ledger_root_under_the_temp_dir(tmp_path, monkeypatch):
    other = tmp_path / "not-the-temp-dir"
    other.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(other))
    io = FakeIO()
    out = oh.owner_hand("apply", "shadow", H, str(_root(tmp_path / "root")), _test_io=io)
    assert out["status"] == "refused" and "temp" in out["error"] and io.sh.cmds == [] and io.grants == []


def test_a_test_io_needs_the_fake_ledger_store(tmp_path, ledger_repo):
    io = FakeIO()  # ledger_repo switched THIS test to the real (git) store on a temp bare repo
    out, _ = _run(tmp_path, io)
    assert out["status"] == "refused" and "fake" in out["error"].lower() and io.sh.cmds == [] and io.grants == []


def test_the_minter_re_checks_the_test_seam(tmp_path, ledger_repo, monkeypatch):
    monkeypatch.setenv("NOCTUS_LEDGER_STORE", "fake")  # starts on the fake store (so the seam check passes) ...

    def flip():  # ... and the store becomes the real one while the human is typing
        os.environ["NOCTUS_LEDGER_STORE"] = "git"

    io = FakeIO(on_read=flip)
    out, _ = _run(tmp_path, io)
    assert out["status"] == "refused" and io.grants == [] and not io.sh.touched


# --- the grant ----------------------------------------------------------------------------------------------------------


def test_a_forged_grant_with_the_private_key_but_no_confirmed_audit_row_is_refused(tmp_path):
    spec = wi.parse_instances(YML)
    inst = wi._inst(spec, "shadow")
    g = oh.OwnerHandGrant(line="shadow", policy_hash=oh.policy_hash(inst), host=H, _key=oh._MINT)
    vps = FakeVps()
    out = wi._apply(spec, "shadow", H, True, _test_sh=vps, _owner_grant=g)
    assert out["status"] == "refused" and out["error"] == wi.PERSONAL_REFUSAL and not vps.touched
    prov = wi._provision(spec, "shadow", H, True, _test_sh=vps, _owner_grant=g)
    assert prov["status"] == "refused" and not vps.touched


def test_a_real_grant_is_single_use(tmp_path):
    io = FakeIO()
    out, root = _run(tmp_path, io)
    assert out["status"] == "applied" and len(io.grants) == 1
    again = FakeVps()
    reuse = wi._apply(wi.load_spec(root), "shadow", H, True, _test_sh=again, _owner_grant=io.grants[0])
    assert reuse["status"] == "refused" and not again.touched


def _confirmed_row(root, *, nonce, age_s, line="shadow", host=H, phash=None):
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


def _mk(tmp_path, inst, **kw):
    base = {"line": "shadow", "policy_hash": oh.policy_hash(inst), "host": H, "nonce": "n-fresh",
            "ledger_root": str(tmp_path), "test": True, "_key": oh._MINT}
    return oh.OwnerHandGrant(**dict(base, **kw))


def test_a_grant_needs_a_fresh_matching_confirmed_row_bound_to_its_secret_nonce(tmp_path):
    inst = _confirmed_row(tmp_path, nonce="n-fresh", age_s=10)
    assert oh.grant_covers(_mk(tmp_path, inst), inst, H)
    assert not oh.grant_covers(_mk(tmp_path, inst, nonce="n-guess"), inst, H)   # the ledger holds only a digest
    assert not oh.grant_covers(_mk(tmp_path, inst), inst, "other-host")
    looser = dict(inst, line_policy=dict(inst["line_policy"], auto_repair=True))
    assert not oh.grant_covers(_mk(tmp_path, inst), looser, H)
    assert not oh.grant_covers(_mk(tmp_path, inst), inst, H, looser)
    _confirmed_row(tmp_path, nonce="n-old", age_s=6 * 60)
    assert not oh.grant_covers(_mk(tmp_path, inst, nonce="n-old"), inst, H)     # older than 5 minutes
    with pytest.raises(PermissionError):
        oh.OwnerHandGrant(line="shadow", policy_hash="x", host=H)


def test_a_non_test_grant_is_never_honoured_off_the_real_store(tmp_path):
    # a forged `confirmed` row that lives only in a fake/local file must not back a production grant
    inst = _confirmed_row(tmp_path, nonce="n-fresh", age_s=10, host="noctus-vps")
    g = _mk(tmp_path, inst, host="noctus-vps", test=False)
    assert not oh.grant_covers(g, inst, "noctus-vps")


def test_a_test_grant_only_covers_the_reserved_test_host_and_a_temp_ledger(tmp_path):
    inst = _confirmed_row(tmp_path, nonce="n-fresh", age_s=10, host="noctus-vps")
    assert not oh.grant_covers(_mk(tmp_path, inst, host="noctus-vps"), inst, "noctus-vps")


# --- the audit row ------------------------------------------------------------------------------------------------------


def test_a_spooled_audit_must_read_back_or_the_action_is_refused(tmp_path):
    assert oh._audit_durable(tmp_path, {"ok": True, "status": "written"}, "abc") is None
    err = oh._audit_durable(tmp_path, {"ok": False, "status": "pending"}, "abc")
    assert err and "read back" in err
    p = tmp_path / oh.LEDGER_REL
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"id": "abc", "outcome": "confirmed"}) + "\n")
    assert oh._audit_durable(tmp_path, {"ok": False, "status": "pending"}, "abc") is None
    assert oh._audit_durable(tmp_path, {"ok": False, "status": "error", "error": "x"}, "abc")


def test_offline_the_row_is_spooled_read_back_from_the_real_spool_and_shown_by_id(tmp_path, ledger_repo):
    import subprocess as sp

    from tools.noctus.dev import _ledger_store as ls
    _bare, clone, _show = ledger_repo
    sp.run(["git", "remote", "set-url", "origin", str(tmp_path / "gone.git")], cwd=clone, check=True)
    row = {"id": "rowabc", "ts": "2026-11-10T00:00:00+00:00", "tool": "waha_owner_hand", "action": "apply",
           "line": "shadow", "host": H, "outcome": "confirmed"}
    res = oh._audit(tmp_path, row)
    assert res["status"] == "pending"
    assert oh._audit_durable(tmp_path, res, "rowabc") is None
    notice = oh._audit_notice("rowabc", res)
    assert "rowabc" in notice and "spooled" in notice
    (ls.GitLedgerStore(repo_root=clone).pending_dir() / oh.LEDGER_NAME).unlink()  # the spool vanishes before publish
    assert "read back" in oh._audit_durable(tmp_path, res, "rowabc")


# --- the MCP surface, the registry, the CLI -----------------------------------------------------------------------------


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


def test_the_accessibility_residual_has_a_named_destination():
    src = (MCP / "tools/noctus/dev/waha_owner_hand.py").read_text()
    assert "NOC-REMEDIATE[owner-hand-accessibility-injection]" in src
