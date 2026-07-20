"""Colocated tests for noctus.dev.deploy_image (C2 atomic image rollback).

Zero real SSH / waiting — run_remote + sleep are injected. The FakeDocker is a
small state machine (tags → ids, a running image, a scripted active-probe
sequence). Covers planned / up_to_date / deployed / rolled_back /
rollback_failed / error, the fail-safe snapshot-verify (refuse to deploy with
no confirmed rollback target), the active health probe, the safe docker+compose
allowlists, and the invariant that a confirmed deploy never emits a destructive
docker token.

Born hardened: an earlier version FALSELY reported `rolled_back` while prod was
left on the broken image (caught by a live validation that took social-wiring
down). These tests pin the fixes — snapshot-verify, rollback-verify,
--force-recreate, and the loud rollback_failed status.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import deploy_image as DI  # noqa: E402


def _now():
    return dt.datetime(2026, 5, 22, 12, 0, 0)


class FakeDocker:
    IMG = "ghcr.io/jraphaelsst/noctus-core"

    def __init__(self, running="G0", latest="NEW", health=("up",), snapshot_sticks=True,
                 pull_rc=0, up_rc=0, container_found=True, image_present=True, port="8000",
                 tunnel_restart_rc=0, revision="ABCDEF123456789012", prod_ancestor=True,
                 fetch_rc=0, prod_ref_rc=0):
        self.running = running
        self.tags = {f"{self.IMG}:latest": latest}
        self.health = list(health)
        self._h = 0
        self.snapshot_sticks = snapshot_sticks
        self.pull_rc, self.up_rc = pull_rc, up_rc
        self.container_found, self.image_present, self.port = container_found, image_present, port
        self.tunnel_restart_rc = tunnel_restart_rc
        # PROD-PIN ancestry guard fakes — default models the SAFE/happy path
        # (a properly-promoted image) so pre-existing tests exercise the full
        # code path unmodified; dedicated tests below flip these to exercise
        # each refusal branch.
        self.revision = revision            # None => no OCI revision label
        self.prod_ancestor = prod_ancestor  # False => revision NOT an ancestor of origin/prod
        self.fetch_rc = fetch_rc            # non-zero => git fetch fails (unverifiable)
        self.prod_ref_rc = prod_ref_rc      # non-zero => origin/prod unresolvable (unverifiable)
        self.calls: list[list[str]] = []

    def _id_of(self, ref_or_id):
        return self.tags.get(ref_or_id, ref_or_id)

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[:2] == ["docker", "inspect"]:
            tmpl = cmd[3]
            if ".Image" in tmpl:
                return (1, "", "No such object") if not self.container_found else (0, self.running + "\n", "")
            if "Labels" in tmpl:  # PROD-PIN revision label lookup
                return (0, (self.revision + "\n") if self.revision else "<no value>\n", "")
            if "Healthcheck" in tmpl:  # _container_port prefers the healthcheck test
                return (0, f'["CMD","curl","-fsS","http://localhost:{self.port}/api/health"]\n'
                        if self.port else "", "")
            if "ExposedPorts" in tmpl:
                return (0, (self.port + "/tcp ") if self.port else "", "")
            return (0, "running\n", "")  # .State.Status
        if cmd[0] == "git":  # PROD-PIN ancestor check: ["git", "-C", repo_dir, <sub>, ...]
            sub = cmd[3] if len(cmd) > 3 else ""
            if sub == "fetch":
                return (self.fetch_rc, "", "" if self.fetch_rc == 0 else "network unreachable")
            if sub == "rev-parse":
                return (self.prod_ref_rc, "" if self.prod_ref_rc else "PRODSHA123\n",
                        "" if self.prod_ref_rc == 0 else "unknown revision")
            if sub == "merge-base":
                return (0 if self.prod_ancestor else 1, "", "")
            return (0, "", "")
        if cmd[:2] == ["docker", "restart"]:  # tunnel restart
            return (self.tunnel_restart_rc, "", "" if self.tunnel_restart_rc == 0 else "no such container")
        if cmd[:2] == ["docker", "commit"]:  # snapshot: commit container → :previous
            if not self.snapshot_sticks:
                return (1, "", "commit failed")
            self.tags[cmd[3]] = "COMMITTED"
            return (0, "", "")
        if cmd[:3] == ["docker", "image", "inspect"]:
            ref = cmd[5]  # docker image inspect -f {{.Id}} <ref>
            tag = ref.rsplit(":", 1)[1]
            if tag == "previous":
                return (0, self.tags[ref] + "\n", "") if ref in self.tags else (1, "", "No such image")
            if tag == "latest" and not self.image_present:
                return (1, "", "No such image")
            return (0, self.tags.get(ref, "") + "\n", "")
        if cmd[:2] == ["docker", "tag"]:
            self.tags[cmd[3]] = self._id_of(cmd[2])
            return (0, "", "")
        if cmd[:2] == ["docker", "exec"]:  # active /api/health probe
            r = self.health[self._h] if self._h < len(self.health) else self.health[-1]
            self._h += 1
            return (0, "", "") if r == "up" else (1, "", "curl: connection refused")
        if cmd[:3] == ["docker", "compose", "-f"]:
            action = cmd[4]
            if action == "pull":
                return (self.pull_rc, "", "" if self.pull_rc == 0 else "manifest unknown")
            if action == "up":
                if self.up_rc != 0:
                    return (self.up_rc, "", "no such image")
                self.running = self.tags.get(f"{self.IMG}:latest", "")  # recreate on :latest
                return (0, "", "")
        return (0, "", "")

    def flat(self):
        return " ".join(" ".join(c) for c in self.calls)

    def count(self, action):
        return sum(1 for c in self.calls if c[:3] == ["docker", "compose", "-f"] and c[4] == action)


def _run(fake, **kw):
    kw.setdefault("startup_grace", 0)  # tests: a failing probe → unhealthy immediately
    kw.setdefault("poll_interval", 5)
    return DI.deploy_image("core", run_remote=fake, sleep=lambda s: None, now=_now, **kw)


# ── status paths ─────────────────────────────────────────────────
def test_dry_run_is_read_only():
    f = FakeDocker()
    r = _run(f, confirm=False)
    assert r["status"] == "planned" and r["current_image_id"] == "G0"
    assert "tag" not in f.flat() and f.count("pull") == 0 and f.count("up") == 0


def test_deployed_when_healthy():
    f = FakeDocker(running="G0", latest="NEW", health=("up",))
    r = _run(f, confirm=True)
    assert r["status"] == "deployed" and r["exit_code"] == 0
    assert r["new_image_id"] == "NEW" and r["health"] == "healthy"
    # snapshot via commit + verified, recreated exactly once (no rollback), force-recreate used
    assert ["docker", "commit", "noctus-core", "ghcr.io/jraphaelsst/noctus-core:previous"] in f.calls
    assert r["snapshot_id"] == "COMMITTED"
    assert f.count("up") == 1 and "--force-recreate" in f.flat()


def test_up_to_date_when_pulled_equals_running():
    f = FakeDocker(running="SAME", latest="SAME")
    r = _run(f, confirm=True)
    assert r["status"] == "up_to_date" and f.count("up") == 0


def test_rolled_back_on_unhealthy_and_verified_restored():
    # new image unhealthy; rollback re-probe healthy + running back on the snapshot
    f = FakeDocker(running="G0", latest="BROKEN", health=("down", "up"))
    r = _run(f, confirm=True)
    assert r["status"] == "rolled_back" and r["exit_code"] == 1
    assert r["health"] == "unhealthy" and r["rollback_health"] == "healthy"
    # rollback retags :latest from the committed :previous, then force-recreates
    assert ["docker", "tag", "ghcr.io/jraphaelsst/noctus-core:previous",
            "ghcr.io/jraphaelsst/noctus-core:latest"] in f.calls
    assert f.count("up") == 2  # deploy + rollback


def test_rollback_failed_is_loud_when_not_restored():
    # rollback re-probe still unhealthy → must NOT claim rolled_back
    f = FakeDocker(running="G0", latest="BROKEN", health=("down", "down"))
    r = _run(f, confirm=True)
    assert r["status"] == "rollback_failed" and r["exit_code"] == 1
    assert "MANUAL RECOVERY" in r["reason"]


def test_snapshot_failsafe_refuses_to_deploy():
    # snapshot tag does not stick (containerd GC class) → REFUSE, container untouched
    f = FakeDocker(snapshot_sticks=False)
    r = _run(f, confirm=True)
    assert r["status"] == "error" and "REFUSING" in r["reason"]
    assert f.count("pull") == 0 and f.count("up") == 0  # nothing deployed


def test_source_local_skips_pull():
    f = FakeDocker(running="G0", latest="LOCALBUILT", health=("up",))
    r = _run(f, confirm=True, source="local")
    assert r["status"] == "deployed" and r["source"] == "local"
    assert f.count("pull") == 0 and f.count("up") == 1


def test_source_local_missing_image_errors():
    f = FakeDocker(image_present=False)
    r = _run(f, confirm=True, source="local")
    assert r["status"] == "error" and "no image" in r["reason"]
    assert f.count("up") == 0


def test_invalid_source_errors():
    r = DI.deploy_image("core", run_remote=FakeDocker(), source="bogus", confirm=True)
    assert r["status"] == "error" and "source" in r["error"]


def test_dry_run_reports_source():
    r = _run(FakeDocker(), confirm=False, source="local")
    assert r["status"] == "planned" and r["source"] == "local"
    assert "locally-built" in r["message"]


def test_error_when_container_not_found():
    f = FakeDocker(container_found=False)
    r = _run(f, confirm=True)
    assert r["status"] == "error" and "not found" in r["error"]
    assert f.count("up") == 0


def test_pull_failure_aborts_without_touching_container():
    f = FakeDocker(pull_rc=1)
    r = _run(f, confirm=True)
    assert r["status"] == "error" and "pull" in r["reason"]
    assert f.count("up") == 0


# ── PROD-PIN ancestry guard (2026-07-20) ──────────────────────────
# Default FakeDocker() already models the SAFE/happy path (revision present +
# an ancestor of origin/prod) — see test_deployed_when_healthy for the
# implicit regression coverage. These tests flip each fake exclusively to
# exercise one refusal branch, or the two documented bypass shapes.

def test_ancestry_guard_default_path_records_source_revision():
    f = FakeDocker(running="G0", latest="NEW", health=("up",))
    r = _run(f, confirm=True)
    assert r["status"] == "deployed"
    assert r["source_revision"] == "ABCDEF123456789012"


def test_ancestry_guard_refuses_when_image_has_no_revision_label():
    f = FakeDocker(running="G0", latest="NEW", health=("up",), revision=None)
    r = _run(f, confirm=True)
    assert r["status"] == "error" and r["exit_code"] == 1
    assert "PROD-PIN GUARD" in r["reason"] and "label" in r["reason"]
    assert f.count("up") == 0  # container untouched — never recreated


def test_ancestry_guard_refuses_when_not_ancestor_of_prod():
    f = FakeDocker(running="G0", latest="NEW", health=("up",), prod_ancestor=False)
    r = _run(f, confirm=True)
    assert r["status"] == "error" and r["exit_code"] == 1
    assert "PROD-PIN GUARD" in r["reason"] and "NOT an ancestor" in r["reason"]
    assert r["source_revision"] == "ABCDEF123456789012"
    assert f.count("up") == 0


def test_ancestry_guard_refuses_fail_closed_when_fetch_unverifiable():
    f = FakeDocker(running="G0", latest="NEW", health=("up",), fetch_rc=1)
    r = _run(f, confirm=True)
    assert r["status"] == "error" and r["exit_code"] == 1
    assert "PROD-PIN GUARD" in r["reason"] and "unverifiable" in r["reason"]
    assert f.count("up") == 0


def test_ancestry_guard_refuses_fail_closed_when_prod_ref_unresolvable():
    f = FakeDocker(running="G0", latest="NEW", health=("up",), prod_ref_rc=1)
    r = _run(f, confirm=True)
    assert r["status"] == "error" and r["exit_code"] == 1
    assert "PROD-PIN GUARD" in r["reason"] and "unverifiable" in r["reason"]
    assert f.count("up") == 0


def test_skip_ancestry_check_overrides_missing_label():
    f = FakeDocker(running="G0", latest="NEW", health=("up",), revision=None)
    r = _run(f, confirm=True, skip_ancestry_check=True)
    assert r["status"] == "deployed"
    assert "source_revision" not in r


def test_skip_ancestry_check_overrides_non_ancestor():
    f = FakeDocker(running="G0", latest="NEW", health=("up",), prod_ancestor=False)
    r = _run(f, confirm=True, skip_ancestry_check=True)
    assert r["status"] == "deployed"


def test_ancestry_guard_skipped_when_source_is_local():
    # source='local' (build-on-VPS) is a deliberate on-box human action —
    # the guard only applies to the risky floating-tag GHCR-pull path.
    f = FakeDocker(running="G0", latest="LOCALBUILT", health=("up",), revision=None)
    r = _run(f, confirm=True, source="local")
    assert r["status"] == "deployed"
    assert "source_revision" not in r


def test_ancestry_guard_skipped_when_tag_is_pinned_sha():
    # A pinned tag=<sha> deploy already carries verifiable identity in the
    # tag itself — no need to consult the OCI label or origin/prod at all.
    f = FakeDocker(running="G0", health=("up",), revision=None)
    f.tags[f"{FakeDocker.IMG}:abc123def456"] = "PINNEDID"
    r = _run(f, confirm=True, tag="abc123def456")
    assert r["status"] == "deployed"
    assert "source_revision" not in r


def test_ancestry_guard_not_consulted_on_up_to_date():
    # Nothing to deploy => the guard (and its git calls) never even runs.
    f = FakeDocker(running="SAME", latest="SAME", revision=None)
    r = _run(f, confirm=True)
    assert r["status"] == "up_to_date"
    assert not any(c[0] == "git" for c in f.calls)


def test_git_allowlist_blocks_off_list_subcommand():
    calls = []
    try:
        DI._git(lambda cmd: calls.append(cmd) or (0, "", ""), "/opt/x", "push", "origin")
        assert False, "expected ValueError for git push"
    except ValueError as e:
        assert "allowlist" in str(e)
    assert calls == []


def test_image_revision_returns_none_on_no_value_placeholder():
    f = FakeDocker(revision=None)
    assert DI._image_revision(f, f"{FakeDocker.IMG}:latest") is None


def test_image_revision_returns_sha_when_labeled():
    f = FakeDocker(revision="DEADBEEF0000")
    assert DI._image_revision(f, f"{FakeDocker.IMG}:latest") == "DEADBEEF0000"


# ── safety invariants ────────────────────────────────────────────
def test_never_emits_destructive_docker_tokens():
    f = FakeDocker(running="G0", latest="BROKEN", health=("down", "up"))
    _run(f, confirm=True)  # full deploy + rollback path
    flat = f.flat()
    for banned in DI._BANNED_TOKENS:
        assert banned not in flat, f"deploy_image emitted a banned token: {banned!r}"


def test_docker_allowlist_blocks_destructive():
    calls = []
    try:
        DI._docker(lambda cmd: calls.append(cmd) or (0, "", ""), "rmi", "x")
        assert False, "expected ValueError for docker rmi"
    except ValueError as e:
        assert "allowlist" in str(e)
    assert calls == []


def test_compose_allowlist_blocks_down():
    calls = []
    try:
        DI._compose(lambda cmd: calls.append(cmd) or (0, "", ""), "cf", "down")
        assert False, "expected ValueError for compose down"
    except ValueError as e:
        assert "allowlist" in str(e)
    assert calls == []


def test_active_probe_waits_through_startup_then_healthy():
    f = FakeDocker(health=("down", "down", "up"))
    naps = []
    status, states = DI._poll_health(f, lambda s: naps.append(s), "noctus-core",
                                     timeout=150, interval=5, port="8000", startup_grace=20)
    assert status == "healthy" and states[-1].startswith("up")
    assert len(naps) == 2  # waited through two 'down' probes within the grace window


def test_active_probe_unhealthy_past_grace():
    f = FakeDocker(health=("down",))
    status, _states = DI._poll_health(f, lambda s: None, "noctus-core",
                                      timeout=150, interval=5, port="8000", startup_grace=0)
    assert status == "unhealthy"  # past grace + still failing → fast rollback


def test_tool_registers_with_dotted_name():
    captured = {}

    class _Srv:
        def tool(self, name, description):
            captured["name"] = name
            return lambda fn: fn

    DI.register(_Srv())
    assert captured["name"] == "noctus.dev.deploy_image"


# ── tunnel-restart + edge-reachability legs ───────────────────────

def test_deployed_restarts_tunnel_on_success():
    """After a healthy deploy, noctus-tunnel must be restarted (leg a)."""
    f = FakeDocker(running="G0", latest="NEW", health=("up",))
    r = _run(f, confirm=True)
    assert r["status"] == "deployed"
    # restart should have been called on noctus-tunnel
    restart_calls = [c for c in f.calls if c[:2] == ["docker", "restart"]]
    assert restart_calls, "docker restart not called after successful deploy"
    assert restart_calls[0] == ["docker", "restart", "noctus-tunnel"]
    assert r["tunnel_restart"] is True
    assert "tunnel_msg" in r


def test_tunnel_restart_not_called_on_dry_run():
    """Dry-run must never restart the tunnel."""
    f = FakeDocker(running="G0", latest="NEW", health=("up",))
    r = _run(f, confirm=False)
    assert r["status"] == "planned"
    restart_calls = [c for c in f.calls if c[:2] == ["docker", "restart"]]
    assert not restart_calls, "docker restart emitted during dry-run"


def test_tunnel_restart_not_called_on_rollback():
    """Failed deploy that triggers rollback must NOT restart the tunnel."""
    f = FakeDocker(running="G0", latest="BROKEN", health=("down", "up"))
    r = _run(f, confirm=True)
    assert r["status"] == "rolled_back"
    restart_calls = [c for c in f.calls if c[:2] == ["docker", "restart"]]
    assert not restart_calls, "docker restart emitted after rolled_back"


def test_tunnel_restart_not_called_on_up_to_date():
    """up_to_date (no recreate) must not restart the tunnel."""
    f = FakeDocker(running="SAME", latest="SAME")
    r = _run(f, confirm=True)
    assert r["status"] == "up_to_date"
    restart_calls = [c for c in f.calls if c[:2] == ["docker", "restart"]]
    assert not restart_calls, "docker restart emitted on up_to_date"


def test_tunnel_restart_failure_surfaces_warning():
    """If the tunnel restart fails, the deploy still reports deployed but
    includes tunnel_warning so the operator knows."""
    f = FakeDocker(running="G0", latest="NEW", health=("up",), tunnel_restart_rc=1)
    r = _run(f, confirm=True)
    assert r["status"] == "deployed"  # deploy itself succeeded
    assert r["tunnel_restart"] is False
    assert "tunnel_warning" in r


def test_edge_check_ok_when_hostname_provided_and_reachable():
    """When edge_hostname is provided and the fake http returns ok=True,
    edge_check is present in the result."""
    f = FakeDocker(running="G0", latest="NEW", health=("up",))

    def _fake_http(hostname):
        assert "https://" in hostname
        return True, "edge reachable: HTTP 200"

    r = DI.deploy_image(
        "core", run_remote=f, sleep=lambda s: None, now=_now,
        confirm=True, startup_grace=0, poll_interval=5,
        edge_hostname="https://core.noctusai.com.br",
        http=_fake_http,
    )
    assert r["status"] == "deployed"
    assert r.get("edge_check") == "edge reachable: HTTP 200"
    assert "edge_warning" not in r


def test_edge_check_surfaces_warning_when_unreachable():
    """When edge_hostname is provided and the fake http returns ok=False,
    edge_warning must be present and contain a manual-fix hint."""
    f = FakeDocker(running="G0", latest="NEW", health=("up",))

    def _fake_http(hostname):
        return False, "edge timeout/unreachable after tunnel restart: timed out"

    r = DI.deploy_image(
        "core", run_remote=f, sleep=lambda s: None, now=_now,
        confirm=True, startup_grace=0, poll_interval=5,
        edge_hostname="https://core.noctusai.com.br",
        http=_fake_http,
    )
    assert r["status"] == "deployed"  # still deployed; warning is advisory
    assert "edge_warning" in r
    assert "docker restart" in r["edge_warning"]
    assert "edge_check" not in r


def test_edge_check_skipped_when_no_hostname():
    """When edge_hostname is not provided, neither edge_check nor edge_warning
    should appear in the result."""
    f = FakeDocker(running="G0", latest="NEW", health=("up",))
    r = _run(f, confirm=True)
    assert r["status"] == "deployed"
    assert "edge_check" not in r
    assert "edge_warning" not in r


def test_restart_in_docker_allowlist():
    """'restart' must be in _DOCKER_ALLOWED so the tunnel restart doesn't raise."""
    assert "restart" in DI._DOCKER_ALLOWED


def test_curl_edge_returns_true_on_http_error_response():
    """_curl_edge returns ok=True for any HTTP status (including 4xx/5xx) —
    that proves CF forwarded to the origin. Only a connection error → ok=False."""
    import urllib.error
    import urllib.response
    import io

    # Simulate HTTP 403 (CF WAF block, but edge reached origin) — ok=True
    class _FakeSocket:
        def read(self, *a): return b""
        def readinto(self, buf): return 0
        def readline(self, *a): return b""

    # We test the exception branch directly via a fake HTTPError
    exc = urllib.error.HTTPError(
        url="https://core.example.com", code=403, msg="Forbidden",
        hdrs={}, fp=io.BytesIO(b""),
    )

    def _fake_urlopen(req, timeout):
        raise exc

    # Monkey-patch urllib.request.urlopen for this narrow test
    orig = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen
    try:
        ok, detail = DI._curl_edge("https://core.example.com")
        assert ok is True
        assert "403" in detail
    finally:
        urllib.request.urlopen = orig


def test_curl_edge_returns_false_on_timeout():
    """_curl_edge returns ok=False for a connection timeout."""
    import urllib.request

    def _fake_urlopen(req, timeout):
        raise TimeoutError("timed out")

    orig = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen
    try:
        ok, detail = DI._curl_edge("https://core.example.com")
        assert ok is False
        assert "unreachable" in detail
    finally:
        urllib.request.urlopen = orig
