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


SELF, TDEV, SELF_START = 7, 0x1000000F, 10_000.0
SAFE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"


class FakeIO:
    def __init__(self, *, env=None, tty=(True, True), devtty=True, chain=TERMINAL, sigs=None, bundles=None,
                 answers=("shadow", "CONFIRMO"), sh="default", on_read=None, starts=None, tty_extra=(), tdev=TDEV,
                 platform="darwin"):
        self._platform = platform
        self._env = env if env is not None else {"HOME": "/Users/owner", "TERM": "xterm", "PATH": SAFE_PATH}
        self._starts, self._tty_extra, self._tdev = dict(starts or {}), list(tty_extra), tdev
        self._tty, self._devtty = tty, devtty
        self._chain = None if chain is None else list(chain)
        self._sigs = {**SIGS, **(sigs or {})}
        self._bundles = {**BUNDLES, **(bundles or {})}
        self.tty = FakeTTY(answers, on_read)
        self.sh = FakeVps() if sh == "default" else sh
        self.grants = []

    def observe_grant(self, grant):
        self.grants.append(grant)

    def platform(self):
        return self._platform

    def env(self):
        return dict(self._env)

    def isatty(self, fd):
        return self._tty[0] if fd == 0 else self._tty[1]

    def open_tty(self):
        if not self._devtty:
            raise OSError("no tty")
        return self.tty

    def self_proc(self):
        return SELF, SELF_START, self._tdev

    def ancestors(self):
        """(pid, real image, start time) from the parent up to the process launchd (pid 1) started; None = unreadable.
        Start times default to strictly older going up; `starts` overrides one pid's."""
        if self._chain is None:
            return None
        return [(pid, img, self._starts.get(pid, SELF_START - 10 * (k + 1)))
                for k, (pid, img, _argv) in enumerate(self._chain)]

    def tty_pids(self, tdev):
        if tdev != self._tdev:
            return []
        shells = [pid for pid, img, _ in (self._chain or []) if img in oh.SHELL_IMAGES]
        return [SELF] + shells + self._tty_extra

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


def test_the_owner_terminal_passes_the_gate():
    assert oh.human_gate(FakeIO()) is None


REFUSED_CHAINS = {
    # review round 2, attack 1: `exec -a <Terminal path> script ...` -- argv says Terminal, the image is script
    "exec-a-terminal-argv-over-script": dict(chain=[(201, "/usr/bin/script", TERM + " -q /dev/null env -i python cli.py")]),
    # attack 2: an emulator path as an ARGUMENT of a shell
    "argv-substring": dict(chain=[(202, "/bin/sh", "sh -c true " + TERM)]),
    # attack 3: a renamed copy of script / a python pty.spawn
    "renamed-script": dict(chain=[(203, "/tmp/Terminal", TERM)]),
    "python-pty-spawn": dict(chain=[ZSH, (204, PY, "python3 /tmp/x.py " + TERM)]),
    # an emulator image at a path that is not the pinned one (a copy into a user-writable /Applications)
    "terminal-copy-in-applications": dict(chain=[ZSH, LOGIN, (205, "/Applications/Terminal.app/Contents/MacOS/Terminal",
                                                               TERM)]),
    # the pinned path, but the running pid does not satisfy the signing requirement
    "terminal-bad-signature": dict(chain=TERMINAL, sigs={500: None}),
    # the emulator was not started by launchd (an agent ran it): something sits above it
    "terminal-under-claude": dict(chain=TERMINAL + [(206, CLAUDE, "claude")]),
    "terminal-not-a-registered-app": dict(chain=TERMINAL, bundles={500: "com.example.other"}),
    # review round 4, N3: Terminal.app ONLY -- an IDE terminal shares its signed pty host with IDE-hosted agents
    "antigravity-ide-terminal": dict(chain=ANTIGRAVITY),
    "vscode-terminal": dict(chain=VSCODE),
    "ide-extension-host": dict(chain=[ZSH, (209, AG_PLUGIN, AG_PLUGIN), (699, AG_MAIN, AG_MAIN)]),
    # anything but a real shell / login between the process and the emulator
    "claude-between": dict(chain=[ZSH, (206, CLAUDE, "claude"), (110, "/bin/zsh", "-zsh -il")] + TERMINAL[1:]),
    "tmux-server": dict(chain=[ZSH, (210, "/opt/homebrew/bin/tmux", "tmux: server " + TERM)]),
    "script-under-terminal": dict(chain=[ZSH, (211, "/usr/bin/script", "script -q /dev/null"), (112, "/bin/zsh", "-zsh"),
                                         LOGIN, (500, TERM, TERM)]),
    "homebrew-zsh-is-not-a-system-shell": dict(chain=[(212, "/opt/homebrew/bin/zsh", "-zsh")] + TERMINAL[1:]),
    "iterm2-not-pinned": dict(chain=[ZSH, LOGIN, (213, "/Applications/iTerm.app/Contents/MacOS/iTermServer-3.5.4",
                                                  "iTermServer")]),
    # N5: a reused pid -- an "ancestor" that started AFTER its child is not that child's parent
    "terminal-pid-reused": dict(starts={500: SELF_START + 5}),
    "login-pid-reused": dict(starts={102: SELF_START - 5}),
    # unreadable means refuse
    "image-unreadable": dict(chain=[(101, None, "-zsh")] + TERMINAL[1:]),
    "chain-unreadable": dict(chain=None),
    "reparented-to-launchd": dict(chain=[]),
    "shells-only-to-launchd": dict(chain=[ZSH, LOGIN]),
    # N4: another process has our tty as its controlling terminal (TIOCSTI typist / second reader)
    "another-process-on-the-tty": dict(tty_extra=[4242]),
    "no-controlling-tty": dict(tdev=0xFFFFFFFF),
    # N1: code-injection env and a PATH with anything ahead of the system tools
    "pythonpath": dict(env={"PATH": SAFE_PATH, "PYTHONPATH": "/tmp/x"}),
    "pythonstartup": dict(env={"PATH": SAFE_PATH, "PYTHONSTARTUP": "/tmp/x.py"}),
    "pythonhome": dict(env={"PATH": SAFE_PATH, "PYTHONHOME": "/tmp"}),
    "pythonuserbase": dict(env={"PATH": SAFE_PATH, "PYTHONUSERBASE": "/tmp"}),
    "pythoninspect": dict(env={"PATH": SAFE_PATH, "PYTHONINSPECT": "1"}),
    "dyld-insert": dict(env={"PATH": SAFE_PATH, "DYLD_INSERT_LIBRARIES": "/tmp/x.dylib"}),
    "dyld-anything": dict(env={"PATH": SAFE_PATH, "DYLD_LIBRARY_PATH": "/tmp"}),
    "path-fakebin-first": dict(env={"PATH": "/tmp/fakebin:/usr/bin:/bin"}),
    "path-homebrew-first": dict(env={"PATH": "/opt/homebrew/bin:/usr/bin:/bin"}),
    "path-usr-bin-only": dict(env={"PATH": "/usr/bin"}),
    "path-missing": dict(env={"HOME": "/h"}),
    # round 5, P3: /usr/bin/git is the xcrun shim (toolchain selectors), and GIT_* can redirect the audit row
    "developer-dir": dict(env={"PATH": SAFE_PATH, "DEVELOPER_DIR": "/tmp/xcode"}),
    "sdkroot": dict(env={"PATH": SAFE_PATH, "SDKROOT": "/tmp/sdk"}),
    "toolchains": dict(env={"PATH": SAFE_PATH, "TOOLCHAINS": "x"}),
    "git-dir": dict(env={"PATH": SAFE_PATH, "GIT_DIR": "/tmp/elsewhere.git"}),
    "git-ssh-command": dict(env={"PATH": SAFE_PATH, "GIT_SSH_COMMAND": "/tmp/fake-ssh"}),
    "git-config-count": dict(env={"PATH": SAFE_PATH, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "remote.origin.url"}),
}


@pytest.mark.parametrize("case", sorted(REFUSED_CHAINS))
def test_every_non_terminal_chain_shape_is_refused(tmp_path, case):
    io = FakeIO(**REFUSED_CHAINS[case])
    out, root = _run(tmp_path, io)
    assert out["status"] == "refused" and io.sh.cmds == [] and io.tty.out == [] and io.grants == [], case
    assert _rows(root)[0]["outcome"] == "refused"


def test_a_chain_refusal_tells_the_owner_to_open_terminal_app():
    why = oh.human_gate(FakeIO(chain=ANTIGRAVITY))
    assert "Abra o Terminal.app (Aplicativos › Utilitários) e rode o comando lá" in why


def test_a_process_joining_the_tty_between_the_prompts_refuses_before_the_next_prompt(tmp_path):
    io = FakeIO()
    io.tty.on_read = lambda: io._tty_extra.append(4242)
    out, _ = _run(tmp_path, io)
    assert out["status"] == "refused" and "4242" in out["error"] and not io.sh.touched and io.grants == []
    assert sum("Type " in w for w in io.tty.out) == 1


def test_the_terminal_allowlist_is_data_pinned_and_documented_in_the_kb():
    kb = (MCP.parents[1] / "KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/whatsapp.md").read_text()
    (term,) = oh.EMULATORS  # Terminal.app ONLY (N3)
    assert term["label"] == "macOS Terminal" and term["bundle_id"] == "com.apple.Terminal" and term["app"] is None
    assert term["entry_images"] == (TERM,) and term["entry_requirement"] == REQ_TERM
    assert oh.SHELL_IMAGES == ("/bin/zsh", "/bin/bash", "/bin/sh", "/usr/bin/login")
    assert "com.apple.Terminal" in kb and REQ_TERM in kb and "accepted risk" in kb
    for gone in ("EQHXZ8M8AV", "UBF8T346G9"):  # the IDE rows are gone from the code and the pinned table
        assert gone not in (MCP / "tools/noctus/dev/waha_owner_hand.py").read_text()


# --- N1: the chain is read from the kernel, never through PATH ----------------------------------------------------------

FAKE_PS = """#!/bin/sh
# fake ps (review probe): skips every non-shell hop below the first pinned-emulator ancestor
p=$(/bin/ps -o ppid= -p "$4" | tr -d ' ')
while :; do c=$(/bin/ps -o comm= -p "$p"); case "$c" in /bin/zsh|/bin/bash|/bin/sh|*Helper|*Electron|*Terminal|"") break;; esac; p=$(/bin/ps -o ppid= -p "$p" | tr -d ' '); done
echo "$p"
"""


def _truth_chain():
    """Every ancestor pid of this process up to launchd, read with the absolute /bin/ps (the test's own oracle)."""
    import subprocess as sp
    out, pid = [], os.getppid()
    while pid > 1:
        out.append(pid)
        pid = int(sp.run(["/bin/ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True).stdout.strip())
    return out


_DARWIN_ONLY = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="reads the real macOS kernel (sysctl KERN_PROC / libproc); off darwin the gate refuses outright, which "
           "test_a_non_macos_host_is_refused_before_any_kernel_read pins",
)


def test_a_non_macos_host_is_refused_before_any_kernel_read():
    why = oh.human_gate(FakeIO(platform="linux"))
    assert why and "only on the owner's Mac" in why


def test_the_real_io_reports_this_hosts_platform():
    assert oh._RealIO().platform() == sys.platform


@_DARWIN_ONLY
def test_a_fake_ps_first_on_path_cannot_rewrite_the_parent_chain(tmp_path, monkeypatch):
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    (fakebin / "ps").write_text(FAKE_PS)
    (fakebin / "ps").chmod(0o755)
    for tool in ("codesign", "lsappinfo", "git"):  # any PATH-resolved helper would lie too
        (fakebin / tool).write_text("#!/bin/sh\nexit 0\n")
        (fakebin / tool).chmod(0o755)
    truth = _truth_chain()
    monkeypatch.setenv("PATH", f"{fakebin}:{os.environ.get('PATH', '')}")
    seen = oh._RealIO().ancestors()
    assert seen is not None and [c[0] for c in seen] == truth
    assert all(c[1] for c in seen) and all(isinstance(c[2], float) for c in seen)


@_DARWIN_ONLY
def test_the_real_io_reads_start_times_that_never_precede_the_parent():
    io = oh._RealIO()
    me, chain = io.self_proc(), io.ancestors()
    starts = [me[1]] + [c[2] for c in chain]
    assert all(starts[k] >= starts[k + 1] for k in range(len(starts) - 1))


def test_the_live_chain_of_an_agent_session_is_refused():
    why = oh.human_gate(oh._RealIO())
    assert why and "Terminal.app" in why


# --- N2: the real /dev/tty open and read work on a real pty -------------------------------------------------------------

_PTY_CHILD = r"""
import fcntl, os, sys, termios, time
sys.path.insert(0, sys.argv[1])
fcntl.ioctl(0, termios.TIOCSCTTY, 0)
from tools.noctus.dev import waha_owner_hand as oh
t = oh._RealIO().open_tty()
t.write("ready\n")
time.sleep(0.6)  # the parent types junk now: it must be flushed before the prompt
a = oh._ask(t, "line? ")
b = oh._ask(t, "word? ")
t.close()
open(sys.argv[2], "w").write(repr((a, b)))
"""


def test_the_real_tty_open_and_read_work_on_a_real_pty_and_drop_pre_typed_input(tmp_path):
    import select
    import subprocess as sp
    master, slave = os.openpty()
    res = tmp_path / "res"
    child = sp.Popen([sys.executable, "-c", _PTY_CHILD, str(MCP), str(res)], stdin=slave, stdout=slave, stderr=slave,
                     start_new_session=True, close_fds=True)
    os.close(slave)
    seen = b""

    def until(token, timeout=20):
        nonlocal seen
        import time as _t
        end = _t.time() + timeout
        while token not in seen and _t.time() < end:
            r, _, _ = select.select([master], [], [], 0.2)
            if r:
                try:
                    seen += os.read(master, 4096)
                except OSError:
                    break
        assert token in seen, seen

    try:
        until(b"ready")
        os.write(master, b"junk\n")
        until(b"line? ")
        os.write(master, b"shadow\n")
        until(b"word? ")
        os.write(master, b"CONFIRMO\n")
        import time as _t
        end = _t.time() + 20
        while child.poll() is None and _t.time() < end:  # keep draining: a tty close waits for its output to drain
            r, _, _ = select.select([master], [], [], 0.2)
            if r:
                try:
                    seen += os.read(master, 4096)
                except OSError:
                    break
        assert child.wait(timeout=5) == 0, seen
    finally:
        if child.poll() is None:
            child.kill()
        os.close(master)
    assert res.read_text() == repr(("shadow", "CONFIRMO"))


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


@pytest.mark.parametrize("target", ["waha_instance._sh", "_vps_ssh.run_remote"])
def test_a_marked_runner_forwarding_to_the_real_ssh_is_refused_at_the_chokepoint(tmp_path, target):
    # P1-b round 4: `noc-test.invalid` can be aliased in ~/.ssh/config, so the host check alone is not the control --
    # under a test IO the real runner itself refuses, before any subprocess
    from tools.noctus.dev import _vps_ssh
    real = wi._sh if target == "waha_instance._sh" else (lambda h, c, timeout=90: _vps_ssh.run_remote(h, c, timeout=timeout))
    results = []

    def wrapper(host, cmd, timeout=90):
        results.append(real(host, cmd, timeout))
        return results[-1]

    wrapper.__noc_test_fake__ = True
    io = FakeIO(sh=wrapper)
    out, _ = _run(tmp_path, io)
    assert out["status"] == "refused" and results and io.grants == []
    assert all(r == (1, "", wi.OWNER_HAND_RUNNER_REFUSAL) for r in results), results


def test_a_test_grant_never_opens_the_real_runner_and_neither_does_a_grant_off_the_git_store(tmp_path):
    from tools.noctus.dev import _vps_ssh
    inst = _confirmed_row(tmp_path, nonce="n-fresh", age_s=10)
    for g in (_mk(tmp_path, inst), _mk(tmp_path, inst, test=False)):  # the suite runs on the fake store
        with wi._GrantScope(g):
            assert wi._sh(H, "true") == (1, "", wi.OWNER_HAND_RUNNER_REFUSAL)
            assert _vps_ssh.run_remote(H, "true") == (1, "", wi.OWNER_HAND_RUNNER_REFUSAL)
    assert wi._OWNER_HAND_SCOPE.get() is None


def test_inside_owner_hand_ssh_and_git_run_by_absolute_path_and_every_other_caller_is_unchanged():
    from tools.noctus.dev import _ledger_store as ls
    from tools.noctus.dev import _vps_ssh
    assert _vps_ssh._ssh_program() == "ssh" and ls._git_program() == "git"  # outside: PATH, as before
    for scope in (wi.OWNER_HAND_LIVE_SCOPE, wi.OWNER_HAND_TEST_SCOPE):
        token = wi._OWNER_HAND_SCOPE.set(scope)
        try:
            assert _vps_ssh._ssh_program() == "/usr/bin/ssh" and ls._git_program() == "/usr/bin/git"
        finally:
            wi._OWNER_HAND_SCOPE.reset(token)
    token = wi._OWNER_HAND_SCOPE.set(wi.OWNER_HAND_LIVE_SCOPE)
    try:  # the live owner's pre-grant reads of the VPS checkout are not refused
        assert wi._owner_scope_problem() is None
    finally:
        wi._OWNER_HAND_SCOPE.reset(token)
    assert wi._OWNER_HAND_SCOPE.get() is None


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


def test_the_mcp_surface_never_takes_an_owner_grant_and_routes_personal_lines_to_the_agent_gate(tmp_path):
    # D49 superseded 2026-11-12: agents may provision/apply a personal line (tests/test_waha_personal_agent.py); the
    # MCP surface still can never pass an owner grant, and on the fake store the real runner is refused before any read.
    root = _root(tmp_path)
    for action in ("provision", "apply"):
        out = wi.waha_instance(action=action, name="shadow", ssh_host="vps", confirm=True, repo_root=str(root))
        assert out["status"] == "refused" and "fake" in out["error"]
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
