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
    for name in ("Bash", "mcp__noctusai__noctus_dev_task_branch", "mcp__noctusai__noctus_dev_release",
                 "mcp__noctusai__noctus_dev_release_steward", "mcp__noctusai__noctus_dev_deploy_pull",
                 "mcp__noctusai__noctus_dev_deploy_image", "mcp__noctusai__noctus_dev_migrate_product",
                 "mcp__noctusai__noctus_dev_record_applied_migrations", "mcp__noctusai__noctus_vps_recreate"):
        assert matcher.match(name), name
    assert not matcher.match("mcp__noctusai__noctus_dev_pytest")


def test_every_wired_tool_name_is_a_registered_steward_class_name():
    """The hook's name table, the classifier and the wrappers' keys must agree."""
    src = {p.name: p.read_text() for p in (REPO / "mcp/noctusai/tools/noctus/dev").glob("*.py")}
    for key, fn in (("noctus.dev.task_branch", "task_branch.py"), ("noctus.dev.release", "release.py"),
                    ("noctus.dev.deploy_pull", "deploy_pull.py"), ("noctus.dev.deploy_image", "deploy_image.py"),
                    ("noctus.dev.migrate_product", "migrate_product.py"),
                    ("noctus.dev.record_applied_migrations", "record_applied_migrations.py"),
                    ("noctus.vps.recreate", "vps.py")):
        assert f'_steward.tool_refusal("{key}"' in src[fn], (key, fn)
        assert key in rs._MCP_NAMES.values()
