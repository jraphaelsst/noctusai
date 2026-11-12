"""D49 superseded (2026-11-12): an AGENT may apply/provision a `personal: true` WAHA line through the MCP tool.

Every safety check of the owner-hand path stays: the strict shadow shape, the policy hash against the VPS checkout (yml +
rendered compose), the `noctus.line.personal=true` label on core AND edge, the core off noctus-net, edge-before-QR, and
an audit row per agent apply/provision (who, line, policy hash) written BEFORE anything touches the VPS. The QR scan with
the owner's phone stays the human consent step. `remove` of a personal line stays refused for agents."""
from __future__ import annotations

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tools.noctus.dev import waha_instance as wi  # noqa: E402
from tools.noctus.dev import waha_owner_hand as oh  # noqa: E402
from test_waha_owner_hand import YML, H, FakeVps, _root  # noqa: E402


def _agent_rows(root):
    text = oh._ledger_text(root)
    import json
    rows = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    return [r for r in rows if r.get("caller") == "agent"]


def _apply(root, vps, yml=YML, host=H):
    return wi._apply(wi.parse_instances(yml), "shadow", host, True, _test_sh=vps, root=root)


def test_an_agent_apply_on_a_personal_line_proceeds_core_then_provision_then_edge(tmp_path):
    root, vps = _root(tmp_path), FakeVps()
    out = _apply(root, vps)
    assert out["ok"] is True and out["status"] == "applied", out
    ups = [c for c in vps.cmds if " up -d " in c or "POLICY_NOWEB" in c]
    assert "waha-shadow-core" in ups[0] and "POLICY_NOWEB" in ups[1] and ups[2].rstrip().endswith("waha-shadow")


def test_an_agent_apply_writes_its_audit_row_before_touching_the_vps(tmp_path):
    root, vps = _root(tmp_path), FakeVps()
    out = _apply(root, vps)
    rows = _agent_rows(root)
    started = [r for r in rows if r["outcome"] == "agent_started"]
    assert len(started) == 1 and started[0]["action"] == "apply" and started[0]["line"] == "shadow"
    assert started[0]["policy_hash"] == out["policy_hash"] and started[0]["host"] == H
    assert set(started[0]["who"]) >= {"git_email", "os_user", "session"}
    assert [r["outcome"] for r in rows] == ["agent_started", "applied"]  # nested provision adds no second run


def test_an_agent_provision_on_a_personal_line_proceeds_and_is_audited(tmp_path):
    root, vps = _root(tmp_path), FakeVps()
    out = wi._provision(wi.parse_instances(YML), "shadow", H, True, _test_sh=vps, root=root)
    assert out["status"] == "verified" and vps.touched, out
    assert [r["outcome"] for r in _agent_rows(root)] == ["agent_started", "verified"]


def test_a_dry_run_writes_no_audit_row(tmp_path):
    root = _root(tmp_path)
    out = wi._provision(wi.parse_instances(YML), "shadow", H, False, _test_sh=FakeVps(), root=root)
    assert out["status"] == "planned" and _agent_rows(root) == []


def test_a_malformed_shadow_shape_is_still_refused(tmp_path):
    loose = YML.replace("    dashboard: false\n    personal: true\n", "    dashboard: true\n    personal: true\n")
    loose = loose.replace("{send: disabled, mark_online: false, full_sync: false",
                          "{send: enabled, mark_online: false, full_sync: false").replace(
        "    edge_deny_writes: true\n    webhook_upstream: http://assistant-x:8030\n", "")
    root, vps = _root(tmp_path, loose), FakeVps(vps_yml=loose)
    out = _apply(root, vps, yml=loose)
    assert out["status"] == "refused" and "allowed personal line shape" in out["error"] and not vps.touched, out
    assert _agent_rows(root) == []


def test_a_vps_policy_hash_drift_is_still_refused(tmp_path):
    vps_yml = YML.replace("http://assistant-x:8030", "http://assistant-x:8031")
    root, vps = _root(tmp_path), FakeVps(vps_yml=vps_yml)
    out = _apply(root, vps)
    assert out["status"] == "refused" and "deploy_pull" in out["error"] and not vps.touched


def test_a_vps_compose_without_the_personal_label_or_with_the_core_on_noctus_net_is_refused(tmp_path):
    import yaml
    svcs = yaml.safe_load(wi.render_compose(wi.parse_instances(YML)))
    svcs["services"]["waha-shadow"].pop("labels")
    svcs["services"]["waha-shadow-core"].setdefault("networks", []).append("noctus-net")
    root, vps = _root(tmp_path), FakeVps(compose=yaml.safe_dump(svcs))
    out = _apply(root, vps)
    assert out["status"] == "refused" and "noctus.line.personal" in out["error"] and "noctus-net" in out["error"]
    assert not vps.touched


def test_a_live_label_drift_after_apply_is_reported(tmp_path):
    root, vps = _root(tmp_path), FakeVps(labels="false")
    out = _apply(root, vps)
    assert out["ok"] is False and out["status"] == "label_drift"
    assert [r["outcome"] for r in _agent_rows(root)] == ["agent_started", "label_drift"]


def test_the_agent_path_on_the_fake_store_never_reaches_the_real_runner_or_a_real_host(tmp_path):
    root = _root(tmp_path)
    out = wi._apply(wi.parse_instances(YML), "shadow", H, True, root=root)  # no fake runner: the real `_sh`
    assert out["status"] == "refused" and "fake" in out["error"]
    vps = FakeVps()
    out = _apply(root, vps, host="noctus-vps")
    assert out["status"] == "refused" and "reserved host" in out["error"] and vps.cmds == []  # refused before any read


def test_remove_of_a_personal_line_stays_refused_for_agents(tmp_path):
    out = wi._remove(wi.parse_instances(YML), "shadow", H, True, False, _test_sh=FakeVps())
    assert out["status"] == "refused" and out["error"] == wi.PERSONAL_REFUSAL


def test_the_mcp_surface_now_routes_a_personal_line_through_the_agent_gate(tmp_path):
    root = _root(tmp_path)
    for action in ("provision", "apply"):
        out = wi.waha_instance(action=action, name="shadow", ssh_host=H, confirm=True, repo_root=str(root))
        # real runner under the fake store: refused by the agent gate's store check, never PERSONAL_REFUSAL
        assert out["status"] == "refused" and out["error"] != wi.PERSONAL_REFUSAL and "fake" in out["error"]


# --- personal LIVE shape (owner decision 2026-11-12): send enabled, no edge, presence + history still off ---------------
LIVE = YML.replace(
    "    line_policy: {send: disabled, mark_online: false, full_sync: false, auto_repair: false}\n"
    "    edge_deny_writes: true\n    webhook_upstream: http://assistant-x:8030\n", 
    "    line_policy: {send: enabled, mark_online: false, full_sync: false, auto_repair: false}\n")
assert "send: enabled, mark_online: false, full_sync: false, auto_repair: false}\n    dashboard: false" in LIVE


def test_personal_live_apply_via_the_agent_gate_proceeds_audited_and_provisioned(tmp_path):
    root, vps = _root(tmp_path, LIVE), FakeVps(vps_yml=LIVE)
    out = _apply(root, vps, yml=LIVE)
    assert out["ok"] is True and out["status"] == "applied", out
    ups = [c for c in vps.cmds if " up -d " in c or "POLICY_NOWEB" in c]
    assert ups[0].rstrip().endswith("waha-shadow") and "POLICY_NOWEB" in ups[1]  # one service, then markOnline/fullSync pinned
    assert [r["outcome"] for r in _agent_rows(root)] == ["agent_started", "applied"]


def test_personal_live_has_no_edge_the_core_is_on_noctus_net_and_labelled(tmp_path):
    import yaml
    svcs = yaml.safe_load(wi.render_compose(wi.parse_instances(LIVE)))["services"]
    assert "waha-shadow-core" not in svcs
    assert "noctus-net" in svcs["waha-shadow"]["networks"] and svcs["waha-shadow"]["labels"]["noctus.line.personal"] == "true"


def test_personal_live_refuses_a_vps_compose_off_noctus_net_or_publishing_ports(tmp_path):
    import yaml
    for mutate in (lambda s: s.__setitem__("networks", []), lambda s: s.__setitem__("ports", ["3000:3000"])):
        svcs = yaml.safe_load(wi.render_compose(wi.parse_instances(LIVE)))
        mutate(svcs["services"]["waha-shadow"])
        root, vps = _root(tmp_path / str(id(mutate)), LIVE), FakeVps(vps_yml=LIVE, compose=yaml.safe_dump(svcs))
        out = _apply(root, vps, yml=LIVE)
        assert out["status"] == "refused" and not vps.touched, out


@pytest.mark.parametrize("old,new,needle", [
    ("mark_online: false", "mark_online: true", "mark_online"),
    ("full_sync: false", "full_sync: true", "full_sync"),
    ("auto_repair: false", "auto_repair: true", "auto_repair"),
    ("dashboard: false", "dashboard: true", "dashboard"),
])
def test_personal_live_with_presence_history_repair_or_dashboard_on_is_refused(tmp_path, old, new, needle):
    # the monica line (a non-personal one) also carries `mark_online: true` etc.: only the personal block is mutated
    head, tail = LIVE.split("  - name: shadow\n")
    bad = head + "  - name: shadow\n" + tail.replace(old, new)
    root, vps = _root(tmp_path, bad), FakeVps(vps_yml=bad)
    out = _apply(root, vps, yml=bad)
    assert out["status"] == "refused" and needle in out["error"] and not vps.touched, out
    assert _agent_rows(root) == []


def test_personal_live_with_an_edge_or_send_disabled_without_one_is_refused():
    inst = wi.parse_instances(LIVE)["instances"][1]
    assert oh.personal_shape_problems(inst) == []
    assert any("edge_deny_writes" in p for p in oh.personal_shape_problems({**inst, "edge_deny_writes": True}))
    shadow = wi.parse_instances(YML)["instances"][1]
    assert oh.personal_shape_problems(shadow) == []
    assert any("edge_deny_writes" in p for p in oh.personal_shape_problems({**shadow, "edge_deny_writes": False}))
    assert oh.personal_shape_problems({**inst, "personal": False})


def test_remove_of_the_personal_live_line_stays_refused_for_agents():
    out = wi._remove(wi.parse_instances(LIVE), "shadow", H, True, False, _test_sh=FakeVps(vps_yml=LIVE))
    assert out["status"] == "refused" and out["error"] == wi.PERSONAL_REFUSAL
