"""release_steward: lease, outbox (request/inbox/ack), the one decision, the hook, the tool backstop.

No monkeypatching of the guard under test: the store takes its clock / pid probe /
head resolver as seams, `decide*` take `store` + `env`, and the hook is run as a real
subprocess with the lease directory pointed at tmp via NOCTUS_STEWARD_DIR.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TOOL = REPO / "mcp/noctusai/tools/noctus/dev/release_steward.py"
HOOK = REPO / "scripts/hooks/claude-guard-release-steward.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rs = _load("release_steward_under_test", TOOL)

STEWARD, PEER = "11111111-aaaa", "22222222-bbbb"


class Clock:
    def __init__(self) -> None:
        self.t = 1_800_000_000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def alive():
    """pid -> alive map the store consults (a seam, not a patch)."""
    pids: dict[int, bool] = {}
    return pids


@pytest.fixture
def store(tmp_path, clock, alive):
    return rs.StewardStore(tmp_path, clock=clock, pid_alive=lambda pid: alive.get(pid, True),
                           resolve_head=lambda branch: None, default_ttl_s=7200)


def _bash(cmd, sid=PEER, **extra):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "session_id": sid, **extra}


def _mcp(tool, args, sid=PEER, **extra):
    return {"tool_name": f"mcp__noctusai__noctus_dev_{tool}", "tool_input": args, "session_id": sid, **extra}


# -- lease --------------------------------------------------------------------

class TestLease:
    def test_claim_when_free(self, store):
        r = store.claim(STEWARD, "noctusai-51", "ships", claude_pid=100)
        assert r["ok"] and r["status"] == "claimed"
        assert store.public_holder()["session_name"] == "noctusai-51"
        assert "ANNOUNCE" in r["next"]
        assert [json.loads(x)["event"] for x in store.audit_path.read_text().splitlines()] == ["claimed"]

    def test_second_live_claim_refused_and_names_holder(self, store):
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        r = store.claim(PEER, "noctusai-52", claude_pid=200)
        assert not r["ok"] and r["status"] == "refused_steward_exists"
        assert "noctusai-51" in r["error"] and "ListAgents" in r["error"]
        assert store.public_holder()["session_id"] == STEWARD

    def test_reclaim_by_same_session_keeps_claimed_at(self, store, clock):
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        first = store.public_holder()["claimed_at"]
        clock.t += 60
        r = store.claim(STEWARD, claude_pid=100)
        assert r["status"] == "already_steward"
        assert store.public_holder()["claimed_at"] == first
        assert store.public_holder()["session_name"] == "noctusai-51"

    def test_stale_by_ttl_is_taken_over(self, store, clock):
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        clock.t += 7200 + 1
        assert store.holder()[1] == "stale"
        r = store.claim(PEER, "noctusai-52", claude_pid=200)
        assert r["status"] == "took_over_stale"
        assert store.public_holder()["session_id"] == PEER

    def test_not_stale_inside_ttl(self, store, clock):
        store.claim(STEWARD, claude_pid=100)
        clock.t += 7200 - 1
        assert store.holder()[1] == "live"

    def test_dead_process_is_stale_immediately(self, store, alive):
        store.claim(STEWARD, claude_pid=100)
        alive[100] = False
        assert store.holder()[1] == "stale"
        assert store.claim(PEER, claude_pid=200)["status"] == "took_over_stale"

    def test_per_lease_ttl_is_honoured(self, store, clock):
        store.claim(STEWARD, claude_pid=100, ttl_s=600)
        clock.t += 601
        assert store.holder()[1] == "stale"

    def test_heartbeat_extends_life(self, store, clock):
        store.claim(STEWARD, claude_pid=100, ttl_s=600)
        clock.t += 500
        assert store.heartbeat(STEWARD)["ok"]
        clock.t += 500
        assert store.holder()[1] == "live"

    def test_heartbeat_by_non_holder_refused(self, store):
        store.claim(STEWARD, claude_pid=100)
        assert store.heartbeat(PEER)["status"] == "refused_not_steward"

    def test_same_process_new_session_id_reclaims(self, store):
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        r = store.claim("33333333-cccc", "noctusai-51", claude_pid=100)  # /clear: new id, same claude
        assert r["status"] == "reclaimed_same_process"
        assert store.public_holder()["session_id"] == "33333333-cccc"

    def test_release_by_holder_frees_lane(self, store):
        store.claim(STEWARD, claude_pid=100)
        assert store.release(STEWARD)["status"] == "released"
        assert store.holder()[1] == "none"

    def test_release_by_non_holder_refused_unless_stale(self, store, clock):
        store.claim(STEWARD, claude_pid=100)
        assert store.release(PEER)["status"] == "refused_not_steward"
        clock.t += 7300
        assert store.release(PEER)["status"] == "released"

    def test_handoff_to_session_id_is_immediate(self, store):
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        r = store.handoff(STEWARD, to_session_id=PEER, to_name="noctusai-52")
        assert r["status"] == "handed_off"
        assert store.public_holder()["session_id"] == PEER
        assert store.holder()[1] == "live"

    def test_handoff_by_name_is_an_offer_the_target_accepts(self, store):
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        r = store.handoff(STEWARD, to_name="noctusai-52")
        assert r["status"] == "handoff_offered"
        assert store.public_holder()["session_id"] == STEWARD  # still steward until accepted
        assert store.claim("3333", "someone-else", claude_pid=300)["status"] == "refused_steward_exists"
        acc = store.claim(PEER, "noctusai-52", claude_pid=200)
        assert acc["status"] == "accepted_handoff"
        assert store.public_holder()["session_id"] == PEER and store.public_holder()["handoff_to"] is None

    def test_handoff_needs_target_and_holder(self, store):
        store.claim(STEWARD, claude_pid=100)
        assert not store.handoff(STEWARD)["ok"]
        assert store.handoff(PEER, to_name="x")["status"] == "refused_not_steward"

    def test_claim_without_identity_is_an_error(self, store):
        r = store.claim("")
        assert not r["ok"] and "identity" in r["error"]

    def test_corrupt_lease_does_not_wedge_the_lane(self, store):
        store.lease_path.write_text("{not json")
        assert store.holder()[1] == "stale"
        assert store.claim(PEER, claude_pid=200)["ok"]

    def test_subagent_claim_is_flagged(self, store):
        r = store.claim(STEWARD, claude_pid=100, child_session=True)
        assert "dispatched subagent" in r["warning"]

    def test_lease_write_is_atomic_under_concurrent_claims(self, tmp_path, clock):
        results: list[dict] = []

        def go(i: int) -> None:
            s = rs.StewardStore(tmp_path, clock=clock, pid_alive=lambda p: True)
            results.append(s.claim(f"sess-{i}", f"n{i}", claude_pid=1000 + i))

        threads = [threading.Thread(target=go, args=(i,)) for i in range(12)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert sum(1 for r in results if r["ok"]) == 1
        assert sum(1 for r in results if r.get("status") == "refused_steward_exists") == 11
        doc = json.loads((tmp_path / "release-steward.json").read_text())  # whole, never torn
        assert doc["session_id"].startswith("sess-")
        assert not list(tmp_path.glob("*.tmp"))


# -- outbox: request / inbox / ack / mine -------------------------------------

class TestOutbox:
    def test_request_is_non_blocking_even_without_a_steward(self, store):
        r = store.request(PEER, "alpha", name="noctusai-52", head_sha="aaa1111", products=["agents"],
                          migrations=True, notes="n")
        assert r["status"] == "queued_for_steward" and r["steward"] is None
        assert "KEEP BUILDING" in r["next"] and "do not wait" in r["next"] and "hint" in r
        req = r["request"]
        assert (req["slug"], req["branch"], req["head_sha"], req["migrations"]) == ("alpha", "feat/alpha", "aaa1111", True)
        assert req["requester"] == {"session_id": PEER, "name": "noctusai-52"} and req["products"] == ["agents"]

    def test_rerequest_same_slug_latest_head_wins(self, store, clock):
        store.request(PEER, "alpha", head_sha="aaa1111")
        clock.t += 30
        r = store.request(PEER, "alpha", head_sha="bbb2222", notes="more commits")
        assert r["updated_head"] is True
        reqs = store.requests()
        assert list(reqs) == ["alpha"] and reqs["alpha"]["head_sha"] == "bbb2222"
        assert reqs["alpha"]["revision"] == 2 and reqs["alpha"]["notes"] == "more commits"
        assert store.inbox()["pending"] == 1

    def test_head_resolved_from_branch_when_omitted(self, tmp_path, clock):
        s = rs.StewardStore(tmp_path, clock=clock, resolve_head=lambda b: "cafe123" if b == "feat/alpha" else None)
        assert s.request(PEER, "alpha")["request"]["head_sha"] == "cafe123"
        r = s.request(PEER, "beta")
        assert r["request"]["head_sha"] is None and "could not resolve" in r["warnings"][0]

    @pytest.mark.parametrize("slug", ["", "  ", "a b", "x;rm", None])
    def test_bad_slug_refused(self, store, slug):
        assert not store.request(PEER, slug)["ok"]

    def test_inbox_groups_by_requester_and_lists_the_batched_drain(self, store):
        store.request(PEER, "alpha", name="noctusai-52", head_sha="a1")
        store.request(PEER, "beta", name="noctusai-52", head_sha="b1")
        store.request("4444", "gamma", name="noctusai-53", head_sha="c1")
        box = store.inbox()
        assert box["pending"] == 3
        assert box["by_requester"] == {"noctusai-52": ["alpha", "beta"], "noctusai-53": ["gamma"]}
        assert box["drain"] == [f"task_branch action=enqueue slug={s} confirm=True" for s in ("alpha", "beta", "gamma")]
        assert "ONE pass" in box["next"] or "one pass" in box["next"]

    def test_ack_is_steward_only(self, store):
        store.request(PEER, "alpha", head_sha="a1")
        assert store.ack(PEER, "alpha", "landed")["status"] == "refused_not_steward"  # no steward
        store.claim(STEWARD, claude_pid=100)
        assert store.ack(PEER, "alpha", "landed")["status"] == "refused_not_steward"
        assert store.requests()["alpha"]["status"] == "queued_for_steward"

    def test_ack_lifecycle_and_requester_sees_it_via_mine(self, store):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", name="noctusai-52", head_sha="a1")
        assert store.ack(STEWARD, "alpha", "enqueued")["status"] == "acked_enqueued"
        assert store.inbox()["pending"] == 0
        r = store.ack(STEWARD, "alpha", "landed", dev_sha="d3adbee")
        assert r["request"]["dev_sha"] == "d3adbee" and "LANDED d3adbee" in r["next"]
        mine = store.mine(PEER)["requests"]
        assert [(m["slug"], m["status"], m["dev_sha"]) for m in mine] == [("alpha", "landed", "d3adbee")]
        assert store.mine(STEWARD)["requests"] == []
        assert store.status(PEER)["mine"][0]["status"] == "landed"
        store.ack(STEWARD, "alpha", "deployed")
        assert store.mine(PEER)["requests"] == [] and len(store.mine(PEER, include_done=True)["requests"]) == 1

    def test_ejected_carries_reason(self, store):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        r = store.ack(STEWARD, "alpha", "ejected", note="conflict in seed/lib")
        assert r["request"]["status"] == "ejected" and "EJECTED conflict in seed/lib" in r["next"]

    def test_new_commits_after_enqueue_requeue_the_slug(self, store):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        store.ack(STEWARD, "alpha", "enqueued")
        r = store.request(PEER, "alpha", head_sha="a2")
        assert r["status"] == "queued_for_steward" and r["request"]["requeued"] is True
        assert store.inbox()["pending"] == 1

    def test_rerequest_same_head_after_landing_is_a_noop(self, store):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        store.ack(STEWARD, "alpha", "landed", dev_sha="d1")
        r = store.request(PEER, "alpha", head_sha="a1")
        assert r["status"] == "landed" and r["unchanged"] is True
        assert store.inbox()["pending"] == 0

    def test_ack_unknown_slug_and_bad_outcome(self, store):
        store.claim(STEWARD, claude_pid=100)
        assert "no request" in store.ack(STEWARD, "nope", "landed")["error"]
        store.request(PEER, "alpha", head_sha="a1")
        assert "outcome must be" in store.ack(STEWARD, "alpha", "wat")["error"]

    def test_concurrent_requests_all_land(self, tmp_path, clock):
        def go(i: int) -> None:
            rs.StewardStore(tmp_path, clock=clock, resolve_head=lambda b: None).request(f"s{i}", f"slug-{i}", head_sha=f"h{i}")

        threads = [threading.Thread(target=go, args=(i,)) for i in range(16)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert len(rs.StewardStore(tmp_path).requests()) == 16

    def test_status_reports_who_and_whether_me(self, store):
        assert store.status(PEER)["state"] == "none" and store.status(PEER)["i_am_steward"] is False
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        assert store.status(STEWARD)["i_am_steward"] is True
        s = store.status(PEER)
        assert s["i_am_steward"] is False and s["steward"]["session_name"] == "noctusai-51"


# -- classification -----------------------------------------------------------

GATED_BASH = [
    ("git push origin dev", "dev"),
    ("git push origin HEAD:dev", "dev"),
    ("git push origin HEAD:refs/heads/main", "main"),
    ("git push origin +abc123:prod", "prod"),
    ("git push --force-with-lease origin HEAD:dev", "dev"),
    ("git -C /some/wt push origin HEAD:dev", "dev"),
    ("git push origin HEAD:mq/my-slug--abc1234", "mq/"),
    ("git push origin :dev", "dev"),
    ("git push --all origin", "--all"),
    ("cd x && git push origin feat/x:dev", "dev"),
    ("python mcp/noctusai/cli.py --task-branch enqueue --task-branch-slug x --task-branch-confirm", "enqueue"),
    ("python mcp/noctusai/cli.py --task-branch=integrate --task-branch-slug=x --task-branch-confirm", "integrate"),
    ("python mcp/noctusai/cli.py --release bless --release-confirm", "bless"),
    ("python mcp/noctusai/cli.py --release promote --release-confirm", "promote"),
    ("python mcp/noctusai/cli.py --release backmerge --release-confirm", "backmerge"),
    ("python mcp/noctusai/cli.py --deploy-pull --deploy-confirm", "deploy_pull"),
    ("python mcp/noctusai/cli.py --deploy-image agents --deploy-image-confirm", "deploy_image"),
    ("python mcp/noctusai/cli.py --migrate-product social-wiring --migrate-product-confirm", "migrate_product"),
    ("bash -c 'git push origin HEAD:dev'", "dev"),
    ("FOO=1 git push origin HEAD:dev", "dev"),
]

OPEN_BASH = [
    "git push origin feat/x",
    "git push -u origin feat/release-steward",
    "git push",
    "git push origin",
    "git push origin HEAD",
    "git push --dry-run origin HEAD:dev",
    "git push -n origin dev",
    "git push origin feat/dev-tools",           # 'dev' only as a substring
    "git push origin feat/x:feat/prod-thing",
    "git fetch origin dev",
    "git log origin/dev --oneline",
    "git status",
    "echo git push origin dev",
    "grep 'git push origin dev' notes.md",
    "git commit -m 'git push origin dev'",
    "python mcp/noctusai/cli.py --task-branch status",
    "python mcp/noctusai/cli.py --task-branch enqueue --task-branch-slug x",       # dry-run
    "python mcp/noctusai/cli.py --task-branch start --task-branch-slug x --task-branch-confirm",
    "python mcp/noctusai/cli.py --task-branch cleanup --task-branch-slug x --task-branch-confirm",
    "python mcp/noctusai/cli.py --release status",
    "python mcp/noctusai/cli.py --release bless",                                 # dry-run
    "python mcp/noctusai/cli.py --deploy-image agents",                           # dry-run
    "python mcp/noctusai/cli.py --release-steward claim --steward-name a",
    "python mcp/noctusai/cli.py --release-steward request --steward-slug x",
    "grep -- --release-confirm cli.py",
    "cat <<'EOF' > note.txt\ngit push origin dev\nEOF",
    "",
]


class TestClassifyBash:
    @pytest.mark.parametrize("cmd,needle", GATED_BASH)
    def test_gated(self, cmd, needle):
        hit = rs.classify_bash(cmd)
        assert hit is not None, cmd
        assert needle in hit.kind, (cmd, hit)

    @pytest.mark.parametrize("cmd", OPEN_BASH)
    def test_open(self, cmd):
        assert rs.classify_bash(cmd) is None, cmd

    def test_heredoc_fed_to_a_shell_is_scanned(self):
        assert rs.classify_bash("bash <<'EOF'\ngit push origin HEAD:dev\nEOF") is not None

    # F11b P1-3: the breaker's CLI path. The action rides in its own flag; status and plans stay open.
    @pytest.mark.parametrize("cmd", [
        "python mcp/noctusai/cli.py --supabase-breaker --supabase-breaker-action=trip --supabase-breaker-source=fleet "
        "--supabase-breaker-reason=x --supabase-breaker-confirm",
        "python mcp/noctusai/cli.py --supabase-breaker --supabase-breaker-action rearm --supabase-breaker-source fleet "
        "--supabase-breaker-reason x --supabase-breaker-confirm",
    ])
    def test_supabase_breaker_cli_writes_are_gated(self, cmd):
        hit = rs.classify_bash(cmd)
        assert hit is not None and "supabase_breaker" in hit.kind, cmd

    @pytest.mark.parametrize("cmd", [
        "python mcp/noctusai/cli.py --supabase-breaker",
        "python mcp/noctusai/cli.py --supabase-breaker --supabase-breaker-confirm",            # action defaults to status
        "python mcp/noctusai/cli.py --supabase-breaker --supabase-breaker-action=trip --supabase-breaker-reason=x",
    ])
    def test_supabase_breaker_cli_status_and_plans_stay_open(self, cmd):
        assert rs.classify_bash(cmd) is None, cmd

    # 2026-11-10: argparse accepted unambiguous prefixes, so `--deploy-image-conf` ran as --deploy-image-confirm while
    # the gate matched exact flags only. cli.py now refuses abbreviations; the gate backstops an older cli.py.
    @pytest.mark.parametrize("cmd,needle", [
        ("python mcp/noctusai/cli.py --deploy-image agents --deploy-image-conf", "deploy_image"),
        ("python mcp/noctusai/cli.py --task-branch enqueue --task-branch-conf --task-branch-slug x", "task_branch enqueue"),
        ("python mcp/noctusai/cli.py --supabase-breaker --supabase-breaker-act=trip --supabase-breaker-c", "supabase_breaker"),
    ])
    def test_an_abbreviated_gate_flag_is_judged_as_the_flag(self, cmd, needle):
        hit = rs.classify_bash(cmd)
        assert hit is not None and needle in hit.kind, cmd


#: gates installed AHEAD of their cli.py flags: the gate lands first so the CLI is never ungated for a moment.
#: Drop the entry in the branch that adds the flags (merge order guard -> cli-gate-hardening -> feat/supabase-breaker).
_GATE_AHEAD_OF_CLI = {"--supabase-breaker": "feat/supabase-breaker"}


@__import__("functools").lru_cache(maxsize=1)
def _cli_option_strings() -> frozenset[str]:
    """Every `--long` option the REAL parser declares (its --help), incl. flags built in loops/f-strings."""
    import re
    r = subprocess.run([sys.executable, str(REPO / "mcp/noctusai/cli.py"), "--help"],
                       capture_output=True, text=True, timeout=120, cwd=str(REPO))
    assert r.returncode == 0, r.stderr[-400:]
    return frozenset(re.findall(r"(?<![\w-])--[a-z0-9][a-z0-9-]*", r.stdout))


def _shortest_unambiguous_prefix(flag: str, options: set[str]) -> str:
    """The shortest prefix argparse (allow_abbrev=True) would resolve to `flag` alone; `flag` when none is shorter."""
    for n in range(4, len(flag)):
        if [o for o in options if o.startswith(flag[:n])] == [flag]:
            return flag[:n]
    return flag


def _gate_cases():
    """One case per (gate, spelling), GENERATED from _CLI_GATES so a new gate is covered without editing this file."""
    for flag, (allowed, confirm, label) in sorted(rs._CLI_GATES.items()):
        value = sorted(allowed)[0] if allowed else "agents"
        value_flag = rs._CLI_GATE_VALUE_FLAG.get(flag)
        for form in ("eq", "prefix"):
            yield pytest.param(flag, value, value_flag, confirm, label, form, id=f"{flag}-{form}")


@pytest.mark.parametrize("flag,value,value_flag,confirm,label,form", list(_gate_cases()))
def test_every_cli_gate_holds_for_the_eq_form_and_the_shortest_prefix(flag, value, value_flag, confirm, label, form):
    options = _cli_option_strings()
    if flag not in options and flag in _GATE_AHEAD_OF_CLI:
        pytest.skip(f"{flag} is gated ahead of its CLI flags, which arrive with {_GATE_AHEAD_OF_CLI[flag]}")
    for f in (flag, confirm, *([value_flag] if value_flag else [])):
        assert f in options, f"{f} is gated but cli.py declares no such option - the gate table drifted"
    spell = (lambda f: f) if form == "eq" else (lambda f: _shortest_unambiguous_prefix(f, options))
    if value_flag:
        words = [spell(flag), f"{spell(value_flag)}={value}"]
    else:
        words = [f"{spell(flag)}={value}"]
    cmd = " ".join(["python mcp/noctusai/cli.py", *words, spell(confirm)])
    hit = rs.classify_bash(cmd)
    assert hit is not None and hit.kind.startswith(label), cmd


def test_cli_refuses_abbreviated_flags():
    """The root of the bypass: cli.py must not resolve `--task-branch-conf` to --task-branch-confirm."""
    import subprocess
    r = subprocess.run([sys.executable, str(REPO / "mcp/noctusai/cli.py"), "--task-branch", "status", "--task-branch-conf"],
                       capture_output=True, text=True, timeout=120, cwd=str(REPO))
    assert r.returncode == 2 and "unrecognized arguments: --task-branch-conf" in r.stderr, r.stderr[-400:]


class TestClassifyTool:
    def test_task_branch_matrix(self):
        c = rs.classify_tool
        for action in ("enqueue", "integrate", "landed"):
            assert c("mcp__noctusai__noctus_dev_task_branch", {"action": action, "confirm": True, "slug": "x"})
            assert c("mcp__noctusai__noctus_dev_task_branch", {"action": action, "confirm": False}) is None
        for action in ("status", "start", "cleanup", "train", "sync_primary"):
            assert c("mcp__noctusai__noctus_dev_task_branch", {"action": action, "confirm": True}) is None
        assert c("mcp__noctusai__noctus_dev_task_branch", {}) is None

    def test_release_matrix(self):
        c = rs.classify_tool
        for stage in ("bless", "promote", "backmerge"):
            assert c("mcp__noctusai__noctus_dev_release", {"stage": stage, "confirm": True})
            assert c("mcp__noctusai__noctus_dev_release", {"stage": stage}) is None
        for stage in ("status", "manifest"):
            assert c("mcp__noctusai__noctus_dev_release", {"stage": stage, "confirm": True}) is None

    @pytest.mark.parametrize("tool", ["noctus_dev_deploy_pull", "noctus_dev_deploy_image",
                                      "noctus_dev_migrate_product", "noctus_vps_recreate"])
    def test_confirm_gated_tools(self, tool):
        assert rs.classify_tool(f"mcp__noctusai__{tool}", {"confirm": True})
        assert rs.classify_tool(f"mcp__noctusai__{tool}", {"confirm": False}) is None
        assert rs.classify_tool(f"mcp__noctusai__{tool}", {}) is None

    @pytest.mark.parametrize("action", ["rearm", "trip"])
    def test_supabase_breaker_writes_are_guardian_only(self, action):
        """F11b: re-arming or tripping the prod Supabase breaker (incl. the fleet key that stops every product's
        background workers) is a prod mutation - guardian-only when applied; plans and status stay open."""
        tool = "mcp__noctusai__noctus_dev_supabase_breaker"
        gated = rs.classify_tool(tool, {"action": action, "source": "fleet", "reason": "r", "confirm": True})
        assert gated and action in gated.kind
        assert rs.classify_tool(tool, {"action": action, "source": "fleet", "reason": "r", "confirm": False}) is None
        assert rs.classify_tool(tool, {"action": action, "source": "fleet", "reason": "r"}) is None

    def test_supabase_breaker_status_is_never_gated(self):
        assert rs.classify_tool("mcp__noctusai__noctus_dev_supabase_breaker", {"action": "status", "confirm": True}) is None
        assert rs.classify_tool("mcp__noctusai__noctus_dev_supabase_breaker", {}) is None

    def test_record_applied_migrations_always_gated(self):
        assert rs.classify_tool("mcp__noctusai__noctus_dev_record_applied_migrations", {"product": "x"})

    def test_release_steward_itself_and_unrelated_never_gated(self):
        assert rs.classify_tool("mcp__noctusai__noctus_dev_release_steward", {"action": "claim", "confirm": True}) is None
        assert rs.classify_tool("mcp__noctusai__noctus_dev_pytest", {"confirm": True}) is None
        assert rs.classify_tool("Read", {"file_path": "x"}) is None

    def test_dotted_names_are_accepted_for_the_tool_backstop(self):
        assert rs.classify_tool("noctus.dev.release", {"stage": "bless", "confirm": True})


# -- the decision -------------------------------------------------------------

class TestDecide:
    def test_steward_passes_and_heartbeat_is_touched(self, store, clock):
        store.claim(STEWARD, claude_pid=100)
        clock.t += 3000
        assert rs.decide(_bash("git push origin HEAD:dev", sid=STEWARD), store=store, env={}) is None
        assert store.public_holder()["heartbeat_at"] == rs._iso(clock.t)

    def test_steward_subagent_acts_under_the_lease(self, store):
        store.claim(STEWARD, claude_pid=100)
        p = _mcp("task_branch", {"action": "enqueue", "confirm": True, "slug": "x"}, sid=STEWARD, agent_id="sub-1")
        assert rs.decide(p, store=store, env={}) is None

    def test_non_steward_denied_naming_steward_and_the_request_path(self, store):
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        v = rs.decide(_mcp("task_branch", {"action": "enqueue", "confirm": True, "slug": "alpha"}), store=store, env={})
        assert v and v["status"] == "refused_not_steward"
        assert "noctusai-51" in v["reason"]
        assert "queue it with release_steward action=request slug=alpha and keep building — do not wait" in v["reason"]
        assert v["steward"]["session_name"] == "noctusai-51"
        assert "NOC_STEWARD_OVERRIDE" in v["reason"]

    def test_deny_never_tells_the_session_to_wait(self, store):
        for cmd in ("git push origin HEAD:dev", "python mcp/noctusai/cli.py --release bless --release-confirm"):
            for state in ("live", "none", "stale"):
                s = store
                if state != "none":
                    s.claim(STEWARD, "noctusai-51", claude_pid=100)
                if state == "stale":
                    s.clock.t += 99999
                v = rs.decide(_bash(cmd), store=s, env={})
                text = v["reason"].replace("do not wait", "")
                assert "wait" not in text.lower(), text
                s._write_lease(None)

    def test_no_steward_elected_tells_to_check_agents_then_claim_or_queue(self, store):
        v = rs.decide(_bash("git push origin HEAD:dev"), store=store, env={})
        assert "no release steward is elected" in v["reason"]
        assert "ListAgents" in v["reason"] and "release_steward action=claim" in v["reason"]
        assert "LEADER" in v["reason"] and "do not wait" in v["reason"]
        assert v["steward"] is None

    def test_stale_steward_is_treated_as_none(self, store, clock):
        store.claim(STEWARD, claude_pid=100)
        clock.t += 7201
        v = rs.decide(_bash("git push origin HEAD:dev", sid=STEWARD), store=store, env={})
        assert v and "stale" in v["reason"]  # even the old steward must re-claim

    def test_missing_session_id_is_denied(self, store):
        store.claim(STEWARD, claude_pid=100)
        p = _bash("git push origin HEAD:dev")
        del p["session_id"]
        assert rs.decide(p, store=store, env={})

    def test_reads_and_feature_pushes_and_steward_tool_stay_open(self, store):
        store.claim(STEWARD, claude_pid=100)
        for p in (_bash("git push origin feat/x"), _bash("git status"),
                  _mcp("task_branch", {"action": "status"}), _mcp("task_branch", {"action": "enqueue"}),
                  _mcp("release", {"stage": "bless"}), _mcp("release_steward", {"action": "request", "slug": "x"}),
                  _mcp("release_steward", {"action": "claim"}), {"tool_name": "Read", "tool_input": {}}):
            assert rs.decide(p, store=store, env={}) is None, p

    def test_non_dict_tool_input_is_ignored(self, store):
        assert rs.decide({"tool_name": "Bash", "tool_input": "x"}, store=store, env={}) is None

    def test_subagent_cannot_claim(self, store):
        v = rs.decide(_mcp("release_steward", {"action": "claim"}, agent_id="sub-1"), store=store, env={})
        assert v and v["status"] == "refused_subagent_claim" and "LEADER" in v["reason"]
        v = rs.decide(_bash("python mcp/noctusai/cli.py --release-steward claim", agent_id="sub-1"), store=store, env={})
        assert v and v["status"] == "refused_subagent_claim"
        assert rs.decide(_mcp("release_steward", {"action": "claim"}), store=store, env={}) is None  # a leader may

    def test_subagent_request_is_allowed(self, store):
        assert rs.decide(_mcp("release_steward", {"action": "request", "slug": "x"}, agent_id="sub-1"),
                         store=store, env={}) is None


class TestOverride:
    def test_inline_override_with_reason_allows_and_is_audited(self, store, capfd):
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        cmd = "NOC_STEWARD_OVERRIDE='steward unreachable, owner approved' git push origin HEAD:dev"
        assert rs.decide(_bash(cmd), store=store, env={}) is None
        rows = [json.loads(x) for x in store.audit_path.read_text().splitlines()]
        ov = [r for r in rows if r["event"] == "override"]
        assert len(ov) == 1 and ov[0]["reason"] == "steward unreachable, owner approved"
        assert ov[0]["session_id"] == PEER and ov[0]["steward"]["session_id"] == STEWARD
        assert "override accepted" in capfd.readouterr().err

    def test_env_override_allows_mcp_calls(self, store):
        env = {"NOC_STEWARD_OVERRIDE": "recovering a wedged queue entry"}
        assert rs.decide(_mcp("release", {"stage": "bless", "confirm": True}), store=store, env=env) is None
        assert [json.loads(x)["event"] for x in store.audit_path.read_text().splitlines()] == ["override"]

    @pytest.mark.parametrize("reason", ["short", "123456789", "   "])
    def test_short_or_empty_reason_is_denied(self, store, reason):
        env = {"NOC_STEWARD_OVERRIDE": reason}
        v = rs.decide(_bash("git push origin HEAD:dev"), store=store, env=env)
        assert v is not None
        assert not store.audit_path.exists()
        if reason.strip():
            assert "at least 10 chars" in v["reason"]


# -- tool-layer backstop ------------------------------------------------------

class TestToolRefusal:
    def test_non_steward_refused_with_status(self, store):
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        r = rs.tool_refusal("noctus.dev.release", {"stage": "promote", "confirm": True}, store=store,
                            env={rs.SESSION_ENV: PEER})
        assert r["ok"] is False and r["status"] == "refused_not_steward" and r["exit_code"] == 1
        assert "noctusai-51" in r["error"] and r["steward"]["session_id"] == STEWARD

    def test_steward_allowed(self, store):
        store.claim(STEWARD, claude_pid=100)
        assert rs.tool_refusal("noctus.dev.task_branch", {"action": "enqueue", "confirm": True}, store=store,
                               env={rs.SESSION_ENV: STEWARD}) is None

    def test_reads_never_refused(self, store):
        assert rs.tool_refusal("noctus.dev.task_branch", {"action": "status"}, store=store,
                               env={rs.SESSION_ENV: PEER}) is None
        assert rs.tool_refusal("noctus.dev.deploy_image", {"confirm": False}, store=store,
                               env={rs.SESSION_ENV: PEER}) is None

    def test_no_steward_refuses_too(self, store):
        r = rs.tool_refusal("noctus.dev.deploy_pull", {"confirm": True}, store=store, env={rs.SESSION_ENV: PEER})
        assert r["status"] == "refused_not_steward" and "no release steward is elected" in r["error"]

    def test_unattributed_caller_is_allowed_but_audited(self, store):
        assert rs.tool_refusal("noctus.dev.deploy_pull", {"confirm": True}, store=store, env={}) is None
        assert json.loads(store.audit_path.read_text().splitlines()[0])["event"] == "unattributed"

    def test_env_override_works_at_the_tool_layer(self, store):
        env = {rs.SESSION_ENV: PEER, "NOC_STEWARD_OVERRIDE": "ops script during the incident"}
        assert rs.tool_refusal("noctus.vps.recreate", {"confirm": True}, store=store, env=env) is None


# -- run_action dispatch (MCP / CLI shared) ------------------------------------

class TestRoles:
    def test_any_session_sets_its_own_role_and_roles_lists_it(self, store, alive):
        r = store.role_set(PEER, "agents", name="noctusai-e4", claude_pid=77)
        assert r["ok"] and r["role"]["session_id"] == PEER
        listed = store.roles()
        assert listed["roles"]["agents"]["name"] == "noctusai-e4"
        assert listed["roles"]["agents"]["state"] == "live"

    def test_dead_session_role_is_flagged_stale(self, store, alive):
        store.role_set(PEER, "products/sw", name="e1", claude_pid=88)
        alive[88] = False
        assert store.roles()["roles"]["products/sw"]["state"] == "stale"
        assert "products/sw" in store.roles()["stale_roles"]

    def test_stale_by_ttl_without_pid(self, store, clock):
        store.role_set(PEER, "assistant", name="a")
        clock.t += 7201
        assert store.roles()["roles"]["assistant"]["state"] == "stale"

    def test_setting_another_sessions_role_is_steward_only(self, store):
        refused = store.role_set(PEER, "agents", name="x", to_session_id="33333333-cccc")
        assert refused["status"] == "refused_not_steward"
        store.claim(STEWARD, name="dev")
        ok = store.role_set(STEWARD, "agents", name="x", to_session_id="33333333-cccc")
        assert ok["ok"] and store.roles()["roles"]["agents"]["session_id"] == "33333333-cccc"

    def test_dev_steward_is_derived_from_the_lease_and_not_settable(self, store):
        assert store.role_set(PEER, "dev-steward", name="n")["ok"] is False
        store.claim(STEWARD, name="noctusai-b5")
        ds = store.roles()["roles"]["dev-steward"]
        assert ds["session_id"] == STEWARD and ds["derived"] is True

    def test_branch_steward_role_kind(self, store):
        assert store.role_set(PEER, "branch-steward:feat/assistant-chatbot", name="22")["ok"]
        assert "branch-steward:feat/assistant-chatbot" in store.roles()["roles"]
        assert store.role_set(PEER, "branch-steward:", name="22")["ok"] is False

    def test_status_carries_roles_and_claim_next_says_remap(self, store):
        store.role_set(PEER, "agents", name="e4")
        assert "agents" in store.status(PEER)["roles"]
        assert "role" in store.claim(STEWARD, name="d")["next"].lower()

    def test_role_changes_are_audited(self, store):
        store.role_set(PEER, "agents", name="e4")
        rows = [json.loads(x) for x in store.audit_path.read_text().splitlines()]
        assert any(r["event"] == "role_set" and r.get("role") == "agents" for r in rows)

    def test_role_actions_via_run_action(self, store):
        r = rs.run_action("role", PEER, store=store, claude_pid=5, role="agents", name="e4")
        assert r["ok"]
        assert rs.run_action("roles", PEER, store=store)["roles"]["agents"]["name"] == "e4"


def _checker(table):
    def check(branch, head_sha):
        return table.get(branch, {"state": "pending"})
    return check


class TestReconcile:
    def _req(self, store, slug, **kw):
        store.request(PEER, slug, head_sha="abc1234", **kw)

    def test_landed_request_goes_to_already_landed_not_drain(self, store):
        store.landed_check = _checker({"feat/a": {"state": "landed", "dev_sha": "dev111"}})
        self._req(store, "a")
        self._req(store, "b")
        box = store.inbox()
        assert [r["slug"] for r in box["already_landed"]] == ["a"]
        assert box["already_landed"][0]["landed_detected"] == "dev111"
        assert box["drain"] == ["task_branch action=enqueue slug=b confirm=True"]
        assert box["pending"] == 1

    def test_unresolvable_is_flagged_never_dropped(self, store):
        store.landed_check = _checker({"feat/a": {"state": "unresolvable"}})
        self._req(store, "a")
        box = store.inbox()
        assert [r["slug"] for r in box["unresolvable"]] == ["a"]
        assert box["drain"] == ["task_branch action=enqueue slug=a confirm=True"]

    def test_status_counts_already_landed(self, store):
        store.landed_check = _checker({"feat/a": {"state": "landed", "dev_sha": "d"}})
        self._req(store, "a")
        assert store.status(PEER)["outbox"]["already_landed"] == 1

    def test_reconcile_requires_confirm_and_steward(self, store):
        store.landed_check = _checker({"feat/a": {"state": "landed", "dev_sha": "dev111"}})
        self._req(store, "a")
        assert store.reconcile(PEER, confirm=True)["status"] == "refused_not_steward"
        store.claim(STEWARD, name="d")
        plan = store.reconcile(STEWARD, confirm=False)
        assert plan["status"] == "planned" and plan["would_ack"] == ["a"]
        assert store.requests()["a"]["status"] == "queued_for_steward"
        done = store.reconcile(STEWARD, confirm=True)
        assert done["acked"] == ["a"]
        r = store.requests()["a"]
        assert r["status"] == "landed" and r["dev_sha"] == "dev111"

    @pytest.mark.parametrize("left_at", ["enqueued", "ejected", "needs_resync"])
    def test_reconcile_acks_rows_left_at_any_open_status(self, store, left_at):
        """2026-11-10: rows left at `enqueued` (queue-acked, never landed-acked) or `ejected` (later landed by another
        path) were never reconciled, because only queued_for_steward was considered; 3 of 22's rows went stale."""
        store.landed_check = _checker({"feat/a": {"state": "landed", "dev_sha": "dev222", "method": "range_diff"}})
        self._req(store, "a")
        store.claim(STEWARD, name="d")
        store.ack(STEWARD, "a", left_at, note="queue said so")
        assert store.inbox()["pending"] == 0  # an open-but-advanced row is never re-drained
        assert [r["slug"] for r in store.inbox()["already_landed"]] == ["a"]
        assert store.status(PEER)["outbox"]["already_landed"] == 1
        assert store.reconcile(STEWARD, confirm=True)["acked"] == ["a"]
        r = store.requests()["a"]
        assert r["status"] == "landed" and r["dev_sha"] == "dev222"

    @pytest.mark.parametrize("closed", ["landed", "deployed", "withdrawn"])
    def test_reconcile_never_touches_a_closed_row(self, store, closed):
        store.landed_check = _checker({"feat/a": {"state": "landed", "dev_sha": "dev333"}})
        self._req(store, "a")
        store.claim(STEWARD, name="d")
        store.ack(STEWARD, "a", closed, dev_sha="dev000", note="closed")
        assert store.reconcile(STEWARD, confirm=True)["acked"] == []
        assert store.requests()["a"]["status"] == closed

    def test_reconcile_is_audited(self, store):
        store.landed_check = _checker({"feat/a": {"state": "landed", "dev_sha": "d"}})
        self._req(store, "a")
        store.claim(STEWARD, name="d")
        store.reconcile(STEWARD, confirm=True)
        rows = [json.loads(x) for x in store.audit_path.read_text().splitlines()]
        assert any(r["event"] == "reconcile" and r["slugs"] == ["a"] for r in rows)

    def test_multi_branch_landed_only_when_all_landed(self, store):
        store.landed_check = _checker({"feat/a-be": {"state": "landed", "dev_sha": "d"}})
        store.request(PEER, "a", head_sha="x", branches=["feat/a-be", "feat/a-fe"])
        assert store.inbox()["already_landed"] == []

    def test_git_checker_on_real_repo(self, tmp_path):
        def g(*a):
            subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True,
                           env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
        g("init", "-q", "-b", "dev")
        (tmp_path / "f").write_text("1"); g("add", "f"); g("commit", "-qm", "base")
        g("update-ref", "refs/remotes/origin/dev", "HEAD")
        g("checkout", "-qb", "feat/x")
        (tmp_path / "g").write_text("2"); g("add", "g"); g("commit", "-qm", "x")
        sha = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        chk = rs.git_landed_check(cwd=tmp_path)
        assert chk("feat/x", sha)["state"] == "pending"
        g("update-ref", "refs/remotes/origin/dev", "HEAD")  # now dev contains it
        res = chk("feat/x", sha)
        assert res["state"] == "landed" and res["dev_sha"] == sha
        assert chk("feat/ghost", None)["state"] == "unresolvable"
        assert chk("feat/ghost", sha)["state"] == "landed"  # falls back to head_sha


class TestMultiBranch:
    def test_request_stores_ordered_branches(self, store):
        r = store.request(PEER, "roteiro", head_sha="x", branches=["feat/r-be", "feat/r-fe"])
        assert r["request"]["branches"] == ["feat/r-be", "feat/r-fe"]

    def test_drain_is_one_train_then_one_enqueue(self, store):
        store.request(PEER, "roteiro", head_sha="x", branches=["feat/r-be", "feat/r-fe"])
        store.request(PEER, "solo", head_sha="y")
        drain = store.inbox()["drain"]
        assert drain[0] == "task_branch action=train slug=train-roteiro slugs=[r-be,r-fe] confirm=True"
        assert drain[1] == "task_branch action=enqueue slug=train-roteiro confirm=True"
        assert "task_branch action=enqueue slug=solo confirm=True" in drain
        assert not any("slug=r-be" in d and "enqueue" in d for d in drain)

    def test_warns_when_notes_say_together_without_branches(self, store):
        r = store.request(PEER, "r-be", head_sha="x", notes="deploy TOGETHER with the fe")
        assert any("branches=" in w for w in r["warnings"])

    def test_warns_on_second_feat_name_in_notes(self, store):
        r = store.request(PEER, "r-be", head_sha="x", notes="needs feat/r-fe too")
        assert any("branches=" in w for w in r["warnings"])

    def test_no_warning_when_branches_given_or_plain_notes(self, store):
        ok = store.request(PEER, "r", head_sha="x", branches=["feat/a", "feat/b"], notes="deploy together")
        assert not any("branches=" in w for w in ok.get("warnings", []))
        plain = store.request(PEER, "p", head_sha="x", notes="feat/p adds a button")
        assert not any("branches=" in w for w in plain.get("warnings", []))

    def test_train_drain_is_audited(self, store):
        store.request(PEER, "roteiro", head_sha="x", branches=["feat/r-be", "feat/r-fe"])
        store.inbox()
        rows = [json.loads(x) for x in store.audit_path.read_text().splitlines()]
        assert any(r["event"] == "train_drain" and r["slug"] == "roteiro" for r in rows)


def test_run_action_roundtrip(store):
    assert rs.run_action("claim", STEWARD, store=store, claude_pid=100, name="n51")["ok"]
    assert rs.run_action("request", PEER, store=store, slug="alpha", head_sha="a1", products=["agents"])["ok"]
    assert rs.run_action("inbox", STEWARD, store=store)["pending"] == 1
    assert rs.run_action("ack", STEWARD, store=store, slug="alpha", outcome="landed", dev_sha="d1")["ok"]
    assert rs.run_action("mine", PEER, store=store)["requests"][0]["dev_sha"] == "d1"
    assert rs.run_action("handoff", STEWARD, store=store, to_session_id=PEER)["status"] == "handed_off"
    assert rs.run_action("release", PEER, store=store)["status"] == "released"
    assert not rs.run_action("nope", PEER, store=store)["ok"]


# -- the hook, as the harness runs it (real subprocess, JSON in / JSON out) ----

def _hook(payload: dict, steward_dir: Path, extra_env: dict | None = None) -> dict | None:
    env = {k: v for k, v in os.environ.items() if k != "NOC_STEWARD_OVERRIDE"}
    env.update({"NOCTUS_STEWARD_DIR": str(steward_dir), "NOCTUS_GUARD_EVENT_LOG": str(steward_dir / "events.ndjson"),
                **(extra_env or {})})
    out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True,
                         text=True, env=env, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout) if out.stdout.strip() else None


class TestHook:
    def test_denies_non_steward_with_marker_and_names_the_request_path(self, tmp_path):
        s = rs.StewardStore(tmp_path)
        s.claim(STEWARD, "noctusai-51", claude_pid=os.getpid())
        out = _hook(_bash("git push origin HEAD:dev"), tmp_path)
        hso = out["hookSpecificOutput"]
        assert hso["permissionDecision"] == "deny"
        assert hso["permissionDecisionReason"].startswith("[noc-guard:release-steward] ")
        assert "noctusai-51" in hso["permissionDecisionReason"]
        assert "queue it with release_steward action=request slug=<slug> and keep building — do not wait" in hso["permissionDecisionReason"]

    def test_allows_the_steward_and_open_calls(self, tmp_path):
        s = rs.StewardStore(tmp_path)
        s.claim(STEWARD, "noctusai-51", claude_pid=os.getpid())
        assert _hook(_bash("git push origin HEAD:dev", sid=STEWARD), tmp_path) is None
        assert _hook(_bash("git push origin feat/x"), tmp_path) is None
        assert _hook(_mcp("release_steward", {"action": "request", "slug": "x"}), tmp_path) is None

    def test_no_steward_elected_denies_but_the_claim_is_allowed(self, tmp_path):
        out = _hook(_mcp("release", {"stage": "bless", "confirm": True}), tmp_path)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert _hook(_bash("python mcp/noctusai/cli.py --release-steward claim --steward-name n51"), tmp_path) is None
        assert _hook(_mcp("release_steward", {"action": "claim", "name": "n51"}), tmp_path) is None

    def test_override_via_hook_environment(self, tmp_path):
        out = _hook(_bash("git push origin HEAD:dev"), tmp_path,
                    {"NOC_STEWARD_OVERRIDE": "owner asked for a manual push"})
        assert out is None
        assert "override" in (tmp_path / "release-steward.ndjson").read_text()

    def test_fails_closed_on_garbage_stdin(self, tmp_path):
        env = {**os.environ, "NOCTUS_STEWARD_DIR": str(tmp_path), "NOCTUS_GUARD_EVENT_LOG": str(tmp_path / "e")}
        out = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, env=env)
        assert "[noc-guard:release-steward]" in json.loads(out.stdout)["hookSpecificOutput"]["permissionDecisionReason"]


def test_settings_registers_the_hook_for_bash_and_the_steward_class_tools():
    settings = json.loads((REPO / ".claude/settings.json").read_text())
    entries = [e for e in settings["hooks"]["PreToolUse"]
               if any("claude-guard-release-steward.py" in h["command"] for h in e["hooks"])]
    assert len(entries) == 1
    import re
    matcher = re.compile(f"^(?:{entries[0]['matcher']})$")
    # DERIVED from the classifier's own name table: a tool added to _MCP_NAMES without its matcher entry would be
    # classified but never reach the guard (the hook never fires), a silent hole.
    for name in ("Bash", *rs._MCP_NAMES):
        assert matcher.match(name), name
    assert not matcher.match("mcp__noctusai__noctus_dev_pytest")


def test_every_wired_tool_name_is_a_registered_steward_class_name():
    """The hook's name table, the classifier and the wrappers' keys must agree."""
    src = {p.name: p.read_text() for p in (REPO / "mcp/noctusai/tools/noctus/dev").glob("*.py")}
    for key, fn in (("noctus.dev.task_branch", "task_branch.py"), ("noctus.dev.release", "release.py"),
                    ("noctus.dev.deploy_pull", "deploy_pull.py"), ("noctus.dev.deploy_image", "deploy_image.py"),
                    ("noctus.dev.migrate_product", "migrate_product.py"),
                    ("noctus.dev.record_applied_migrations", "record_applied_migrations.py"),
                    ("noctus.vps.recreate", "vps.py"),
                    ("noctus.dev.supabase_breaker", "supabase_breaker.py")):
        assert f'_steward.tool_refusal("{key}"' in src[fn], (key, fn)
        assert key in rs._MCP_NAMES.values()


# These tests FAIL until feat/guard-supabase-breaker lands the `_MCP_NAMES` entry + `classify_tool` branch (release_steward.py
# is guardian-protected): the train ships guard first. A skip would hide exactly the hole they pin.


class TestSupabaseBreakerBackstop:
    """rearm|trip with confirm=True is steward-class: a non-steward session is refused INSIDE the tool; status and
    dry-runs never are."""

    @pytest.mark.parametrize("action", ["rearm", "trip"])
    def test_confirm_write_from_a_non_steward_is_refused_in_tool(self, store, action):
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        r = rs.tool_refusal("noctus.dev.supabase_breaker", {"action": action, "confirm": True}, store=store,
                            env={rs.SESSION_ENV: PEER})
        assert r["ok"] is False and r["status"] == "refused_not_steward"

    def test_the_steward_is_allowed(self, store):
        store.claim(STEWARD, claude_pid=100)
        assert rs.tool_refusal("noctus.dev.supabase_breaker", {"action": "rearm", "confirm": True}, store=store,
                               env={rs.SESSION_ENV: STEWARD}) is None

    @pytest.mark.parametrize("args", [{"action": "status", "confirm": True}, {"action": "rearm", "confirm": False},
                                      {"action": "trip", "confirm": False}, {"action": "status"}])
    def test_status_and_dry_runs_are_never_refused(self, store, args):
        # the same tool with confirm=True IS steward-class (so this test can fail if the guard is not registered)
        assert rs.classify_tool("noctus.dev.supabase_breaker", {"action": "rearm", "confirm": True}) is not None
        store.claim(STEWARD, "noctusai-51", claude_pid=100)
        assert rs.tool_refusal("noctus.dev.supabase_breaker", args, store=store,
                               env={rs.SESSION_ENV: PEER}) is None


THIRD = "33333333-cccc"


class TestWithdrawAndKinds:
    def test_requester_withdraws_own_request(self, store):
        store.request(PEER, "alpha", head_sha="a1")
        r = store.withdraw(PEER, "alpha", "superseded")
        assert r["ok"] and r["request"]["status"] == "withdrawn" and r["request"]["ack_note"] == "superseded"
        assert store.inbox()["pending"] == 0 and store.inbox()["drain"] == []
        assert store.mine(PEER)["requests"] == []
        assert [m["status"] for m in store.mine(PEER, include_done=True)["requests"]] == ["withdrawn"]
        assert [x["slug"] for x in store.inbox(include_done=True)["requests"]] == ["alpha"]
        rows = [json.loads(line) for line in store.audit_path.read_text().splitlines()]
        assert any(x["event"] == "withdraw" and x["slug"] == "alpha" and x["by"] == PEER for x in rows)

    def test_steward_withdraws_via_ack_with_required_note(self, store):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        assert "notes" in store.ack(STEWARD, "alpha", "withdrawn")["error"]
        assert store.requests()["alpha"]["status"] == "queued_for_steward"
        r = store.ack(STEWARD, "alpha", "withdrawn", note="requester asked")
        assert r["status"] == "acked_withdrawn" and store.inbox()["drain"] == []

    def test_third_session_cannot_withdraw(self, store):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        r = store.withdraw(THIRD, "alpha", "mine now")
        assert not r["ok"] and r["status"] == "refused_not_requester"
        assert store.requests()["alpha"]["status"] == "queued_for_steward"
        assert store.withdraw(STEWARD, "alpha", "steward may")["ok"]

    def test_withdraw_unknown_slug(self, store):
        assert "no request" in store.withdraw(PEER, "nope")["error"]

    def test_rerequest_reopens_withdrawn_as_new_revision(self, store):
        store.request(PEER, "alpha", head_sha="a1")
        store.withdraw(PEER, "alpha")
        r = store.request(PEER, "alpha", head_sha="a1")
        assert r["status"] == "queued_for_steward" and r["request"]["revision"] == 2
        assert store.inbox()["drain"] == ["task_branch action=enqueue slug=alpha confirm=True"]

    def test_request_rows_carry_kind_request(self, store):
        assert store.request(PEER, "alpha", head_sha="a1")["request"]["kind"] == "request"

    def test_needs_info_round_trip(self, store, clock):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        ask = store.ask(STEWARD, "alpha", "is the migration idempotent?")
        assert ask["ok"] and ask["needs_info"]["addressed_to"]["session_id"] == PEER
        assert ask["needs_info"]["owner_fallback"] is True
        assert ask["needs_info"]["deadline_ts"].startswith("2027-01-15T08:30")  # now + 30 min
        item = store.mine(PEER)["needs_info"][0]
        assert item["question"] == "is the migration idempotent?" and item["state"] == "open"
        assert store.mine(THIRD)["needs_info"] == []
        assert store.inbox()["needs_info"] == []  # still open: nothing to read yet
        ans = store.position(PEER, "alpha", "yes, IF NOT EXISTS everywhere", ref=item["id"])
        assert ans["ok"]
        assert store.mine(PEER)["needs_info"] == []
        box = store.inbox()
        assert [(n["id"], n["state"]) for n in box["needs_info"]] == [(item["id"], "answered")]
        assert box["needs_info"][0]["answer"] == "yes, IF NOT EXISTS everywhere"
        assert box["escalate_to_owner"] == []

    def test_needs_info_addressed_to_registered_role(self, store):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        store.role_set(THIRD, "agents", claude_pid=300)
        ask = store.ask(STEWARD, "alpha", "who owns this?", addressed_to="agents")
        assert ask["needs_info"]["addressed_to"] == {"role": "agents", "session_id": THIRD}
        assert store.mine(THIRD)["needs_info"][0]["slug"] == "alpha"

    def test_needs_info_is_steward_only(self, store):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        assert store.ask(PEER, "alpha", "q?")["status"] == "refused_not_steward"

    def test_expired_needs_info_without_position_escalates(self, store, clock):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        ni = store.ask(STEWARD, "alpha", "still alive?")["needs_info"]
        clock.t += 31 * 60
        store.heartbeat(STEWARD)
        box = store.inbox()
        assert [(n["id"], n["state"]) for n in box["needs_info"]] == [(ni["id"], "expired")]
        assert [e["id"] for e in box["escalate_to_owner"]] == [ni["id"]]
        assert "escalate_to_owner" in box["next"]
        assert store.mine(PEER)["needs_info"][0]["state"] == "expired"

    def test_late_position_after_expiry_still_answers(self, store, clock):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        ni = store.ask(STEWARD, "alpha", "q?")["needs_info"]
        clock.t += 31 * 60
        store.position(PEER, "alpha", "late", ref=ni["id"])
        box = store.inbox()
        assert box["needs_info"][0]["state"] == "answered" and box["escalate_to_owner"] == []

    def test_decision_recorded_steward_only_and_clears_thread(self, store):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        ni = store.ask(STEWARD, "alpha", "q?")["needs_info"]
        store.position(PEER, "alpha", "a", ref=ni["id"])
        assert store.decide(PEER, "alpha", "ship it")["status"] == "refused_not_steward"
        d = store.decide(STEWARD, "alpha", "ship it")
        assert d["ok"] and d["decision"]["kind"] == "decision"
        assert store.decisions("alpha")[0]["text"] == "ship it"
        assert store.inbox()["needs_info"] == []
        assert store.requests()["alpha"]["status"] == "queued_for_steward"

    def test_history_is_append_only(self, store):
        store.claim(STEWARD, claude_pid=100)
        store.request(PEER, "alpha", head_sha="a1")
        before = store.outbox_path.read_text()
        store.ask(STEWARD, "alpha", "q?")
        store.withdraw(PEER, "alpha")
        assert store.outbox_path.read_text().startswith(before)


class TestSessionState:
    """`dead` is the claim that lets another session's worktree be removed (P2-5, adversarial review): a stale pid
    alone must never read as dead, and every action refreshes the caller's pid (a /clear or restart changes it)."""

    def test_a_stale_pid_with_a_fresh_heartbeat_is_live_not_dead(self, store, alive, clock):
        store.role_set(PEER, "agents", name="e4", claude_pid=77)
        alive[77] = False  # the recorded pid is gone ...
        clock.t += 60      # ... but the session was active a minute ago
        assert store.session_state(PEER) == "live"

    def test_every_action_refreshes_the_callers_pid(self, store, alive, clock):
        store.role_set(PEER, "agents", name="e4", claude_pid=77)
        alive[77], alive[78] = False, True
        clock.t += 60
        store.role_touch(PEER, claude_pid=78)  # run_action does this for every action
        assert store.roles()["roles"]["agents"]["claude_pid"] == 78
        clock.t += 10_000  # long past the TTL: only the (refreshed, alive) pid keeps it live
        assert store.session_state(PEER) == "live"

    def test_dead_needs_the_pid_dead_AND_the_heartbeat_older_than_the_ttl(self, store, alive, clock):
        store.role_set(PEER, "agents", name="e4", claude_pid=77)
        alive[77] = False
        clock.t += 7200 + 1
        assert store.session_state(PEER) == "dead"

    def test_a_stale_heartbeat_with_no_known_pid_is_unknown_never_dead(self, store, clock):
        store.role_set(PEER, "agents", name="e4", claude_pid=None)
        clock.t += 100_000
        assert store.session_state(PEER) == "unknown"

    def test_no_record_is_unknown(self, store):
        assert store.session_state("never-seen") == "unknown"

    def test_run_action_passes_the_callers_pid_to_role_touch(self, store, alive, clock):
        store.role_set(PEER, "agents", name="e4", claude_pid=77)
        alive[77], alive[99] = False, True
        rs.run_action("mine", PEER, store=store, claude_pid=99)
        assert store.roles()["roles"]["agents"]["claude_pid"] == 99
