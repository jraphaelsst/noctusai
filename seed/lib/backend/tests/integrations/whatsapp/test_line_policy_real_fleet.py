"""The line policy against the fleet's REAL generated read-only set (deploy/fleet/waha-instances.yml ->
read_only_lines.py), not a table a test made up. KB § INTEGRATIONS/whatsapp.md § 6a."""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.whatsapp import LinePolicy, clear_line_policies, register_line_policy, resolve_line_policy
from noctusai_lib.integrations.whatsapp.line_policy import (
    _generated_read_only,
    _resolvable_hosts,
    set_host_resolver,
)

LEGACY = LinePolicy("enabled", True, True, True)

pytestmark = pytest.mark.skipif(not _generated_read_only(), reason="the fleet declares no read-only line")


@pytest.fixture(autouse=True)
def _star_only():
    clear_line_policies()
    register_line_policy("*", LEGACY)  # what social-wiring has in prod: "*" and nothing else
    yield
    set_host_resolver(None)
    clear_line_policies()


def test_every_declared_read_only_alias_is_refused_whatever_the_star_says():
    for hostport in _generated_read_only():
        assert not resolve_line_policy(f"http://{hostport}", "default").send_enabled, hostport


def test_a_down_read_only_edge_does_not_take_a_resolvable_shared_host_down():
    """Reproduces the S6 fleet-wide-outage hazard: the Assistant edge container is down/restarting, so every alias that
    resolves from the product network is unresolvable; a product sending through an undeclared but RESOLVABLE host (the
    shared `waha`, covered only by "*") must keep sending."""
    resolvable = _resolvable_hosts() or frozenset()
    assert resolvable, "the generated set must say which aliases are edge names"
    set_host_resolver(lambda h: None if h in resolvable or h.endswith("-core") else ["10.0.0.30"])
    assert resolve_line_policy("http://waha:3000", "default").send_enabled
    assert resolve_line_policy("http://waha-monica:3000", "default").send_enabled


def test_a_down_edge_still_fails_closed_for_an_ip_literal_and_an_unresolvable_host():
    set_host_resolver(lambda h: None)
    assert not resolve_line_policy("http://10.0.0.5:3000", "default").send_enabled   # could be the edge
    assert not resolve_line_policy("http://who-knows:3000", "default").send_enabled  # cannot be shown to be anything


def test_an_up_edge_is_still_matched_by_address():
    """A different NAME for the same machine (container id, env-overridden URL) is refused when the edge is up."""
    edge = sorted(_resolvable_hosts() or ())[0]
    set_host_resolver(lambda h: ["10.0.0.5"] if h in (edge, "someone-else") else None)
    assert not resolve_line_policy("http://someone-else:3000", "default").send_enabled
