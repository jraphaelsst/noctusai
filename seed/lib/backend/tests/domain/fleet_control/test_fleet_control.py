"""Colocated tests for noctusai_lib.domain.fleet_control.

Zero real docker — the Real controller's `runner` seam is injected, so we
assert the EXACT argv emitted. Covers:
  - FakeContainerController behaviour (status + start/stop/restart mutation).
  - The HARD ALLOWLIST: bad verb / unregistered slug / bad-charset slug all
    raise FleetControlError, in BOTH Fake and Real.
  - Runner-injection: DockerComposeController emits only
    `docker {verb} noctus-<slug>` (verb + constructed name are the only
    non-constant tokens) and `docker ps -a --format ...` for status.
  - The safety invariant: no banned destructive docker token is reachable in
    any emitted argv across status + every allowed action.
"""
from __future__ import annotations

import pytest

from noctusai_lib.domain import fleet_control as FC
from noctusai_lib.domain.fleet_control import (
    ActResult,
    BANNED_TOKENS,
    ContainerStatus,
    DockerComposeController,
    FakeContainerController,
    FleetControlError,
    get_fleet_controller,
    validate_action,
)

# A fixed registered-slug set so these tests don't depend on the live registry.
#
# not-a-product-set — these are SYNTHETIC fixture slugs, deliberately NOT real
# product names. `check_hardcoded_product_slug_set` is right to distrust a
# frozen slug set, but deriving this one from `parse_products_registry()` would
# be the wrong fix: it would couple a unit test to live product data, make it
# drift every time a product is activated or retired, and weaken the very
# assertions it exists for — proving an UNREGISTERED slug is rejected requires
# a known, closed registered set.
#
# They were real slugs until 2026-08-17 ({core, erp-imobiliario, social-wiring,
# therapy-platform}), which is exactly why this comment exists: the set still
# named `therapy-platform` long after it went `ativo=false`, and nobody
# noticed, because for a fixture it never mattered. Real names invite a future
# reader to "helpfully" sync them to the fleet. Synthetic names cannot be
# mistaken for a registry mirror, so there is nothing to sync.
REGISTERED = {"alpha-svc", "beta-svc", "gamma-svc", "delta-svc"}


class RecordingRunner:
    """Injected docker runner — records every argv, returns canned output."""

    def __init__(self, rc: int = 0, ps_out: str = "", action_out: str = "ok"):
        self.rc = rc
        self.ps_out = ps_out
        self.action_out = action_out
        self.calls: list[list[str]] = []

    def __call__(self, cmd):
        self.calls.append(list(cmd))
        if cmd[:2] == ["docker", "ps"]:
            return (self.rc, self.ps_out, "")
        return (self.rc, self.action_out, "")


# ── Fake behaviour ─────────────────────────────────────────────────
def test_fake_status_lists_registered_running():
    c = FakeContainerController(slugs=["alpha-svc", "gamma-svc"], registered_slugs=REGISTERED)
    statuses = c.status()
    assert {s.slug for s in statuses} == {"alpha-svc", "gamma-svc"}
    assert all(isinstance(s, ContainerStatus) for s in statuses)
    assert all(s.running and s.health == "healthy" for s in statuses)
    assert all(s.container == f"noctus-{s.slug}" for s in statuses)


def test_fake_stop_then_start_mutates_state():
    c = FakeContainerController(slugs=["alpha-svc"], registered_slugs=REGISTERED)
    r = c.act("alpha-svc", "stop")
    assert isinstance(r, ActResult) and r.ok and r.verb == "stop"
    assert c.status()[0].running is False and c.status()[0].state == "exited"
    c.act("alpha-svc", "start")
    assert c.status()[0].running is True and c.status()[0].state == "running"


def test_fake_restart_keeps_running():
    c = FakeContainerController(slugs=["alpha-svc"], registered_slugs=REGISTERED)
    r = c.act("alpha-svc", "restart")
    assert r.ok and r.verb == "restart"
    assert c.status()[0].running is True


# ── HARD ALLOWLIST — rejection (the security core) ─────────────────
@pytest.mark.parametrize("verb", ["rm", "rmi", "exec", "down", "run", "kill", "prune", "logs", "STOP", "stop;rm"])
def test_validate_action_rejects_non_allowlisted_verb(verb):
    with pytest.raises(FleetControlError):
        validate_action("alpha-svc", verb, registered_slugs=REGISTERED)


@pytest.mark.parametrize(
    "slug",
    ["unknown-product", "alpha-svc; rm -rf /", "../etc", "alpha-svc x", "", "Alpha-Svc", "alpha-svc$(id)"],
)
def test_validate_action_rejects_unregistered_or_bad_slug(slug):
    with pytest.raises(FleetControlError):
        validate_action(slug, "start", registered_slugs=REGISTERED)


def test_validate_action_returns_safe_container_name():
    assert validate_action("alpha-svc", "restart", registered_slugs=REGISTERED) == "noctus-alpha-svc"


def test_fake_act_also_enforces_allowlist():
    c = FakeContainerController(slugs=["alpha-svc"], registered_slugs=REGISTERED)
    with pytest.raises(FleetControlError):
        c.act("alpha-svc", "rm")
    with pytest.raises(FleetControlError):
        c.act("not-a-product", "start")


def test_real_act_rejects_before_shelling():
    r = RecordingRunner()
    c = DockerComposeController(runner=r, registered_slugs=REGISTERED)
    with pytest.raises(FleetControlError):
        c.act("alpha-svc", "exec")
    with pytest.raises(FleetControlError):
        c.act("evil; rm -rf /", "start")
    # NOTHING was shelled — the allowlist short-circuits before the runner.
    assert r.calls == []


# ── Runner-injection: exact argv ───────────────────────────────────
def test_real_act_emits_only_docker_verb_container():
    r = RecordingRunner()
    c = DockerComposeController(runner=r, registered_slugs=REGISTERED)
    res = c.act("gamma-svc", "restart")
    assert res.ok and res.container == "noctus-gamma-svc"
    assert r.calls == [["docker", "restart", "noctus-gamma-svc"]]


def test_real_status_emits_ps_and_parses():
    ps_out = (
        "noctus-alpha-svc\trunning\tUp 2 hours (healthy)\n"
        "noctus-gamma-svc\texited\tExited (0) 5 minutes ago\n"
        "some-other\trunning\tUp 1 hour\n"           # non-noctus → filtered
        "noctus-not-registered\trunning\tUp 1 hour\n"  # noctus- but not registered → filtered
    )
    r = RecordingRunner(ps_out=ps_out)
    c = DockerComposeController(runner=r, registered_slugs=REGISTERED)
    statuses = {s.slug: s for s in c.status()}
    # Every registered slug appears (absent ones show state="absent").
    assert set(statuses) == REGISTERED
    assert statuses["alpha-svc"].running and statuses["alpha-svc"].health == "healthy"
    assert not statuses["gamma-svc"].running and statuses["gamma-svc"].state == "exited"
    assert statuses["delta-svc"].state == "absent"
    assert r.calls[0] == ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}\t{{.Status}}"]


def test_real_act_failure_returns_not_ok():
    r = RecordingRunner(rc=1, action_out="No such container")
    c = DockerComposeController(runner=r, registered_slugs=REGISTERED)
    res = c.act("alpha-svc", "stop")
    assert res.ok is False and "No such container" in res.message


# ── Safety invariant: no banned token reachable in any argv ─────────
def test_no_banned_token_emitted_token_exact():
    """Across status + every ALLOWED action, no emitted argv TOKEN equals a
    banned destructive docker subcommand. Token-exact (not substring) because
    e.g. '--format' legitimately contains 'rm'."""
    r = RecordingRunner(ps_out="noctus-alpha-svc\trunning\tUp (healthy)\n")
    c = DockerComposeController(runner=r, registered_slugs=REGISTERED)
    c.status()
    for verb in FC.ALLOWED_VERBS:
        c.act("alpha-svc", verb)
    emitted_tokens = {tok for call in r.calls for tok in call}
    for banned in BANNED_TOKENS:
        assert banned not in emitted_tokens, (
            f"fleet_control emitted a banned token {banned!r} in {r.calls!r}"
        )
    # And the only verbs ever in position 1 are the allowlisted ones (+ ps).
    verbs_emitted = {call[1] for call in r.calls if len(call) > 1}
    assert verbs_emitted <= set(FC.ALLOWED_VERBS) | {"ps"}


# ── Factory ────────────────────────────────────────────────────────
def test_factory_use_real_false_returns_fake():
    c = get_fleet_controller(use_real=False, registered_slugs=REGISTERED)
    assert isinstance(c, FakeContainerController)


def test_factory_runner_forces_real():
    r = RecordingRunner()
    c = get_fleet_controller(runner=r, registered_slugs=REGISTERED)
    assert isinstance(c, DockerComposeController)
