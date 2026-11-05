"""noctus.dev.cloudflare_dns — pure-function + seam tests (no network, no SSH)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import cloudflare_dns as cd  # noqa: E402
from tools.noctus.dev.cloudflare_dns import (  # noqa: E402
    classify_route_output, cloudflare_dns, in_zone, missing_diff, route_command,
)

INGRESS = """routes:
  - hostname: noctusai.com
    service: http://core:8000
  - hostname: igig.noctusai.com
    service: http://igig:8013
  - hostname: orbity.noctusai.com
    service: http://orbity:8020
"""


def _root(tmp_path):
    d = tmp_path / "deploy" / "tunnel"
    d.mkdir(parents=True)
    (d / "ingress.yml").write_text(INGRESS)
    return str(tmp_path)


class FakeSsh:
    def __init__(self, rc=0, out="INF Added CNAME x which will route to this tunnel", err=""):
        self.calls, self.rc, self.out, self.err = [], rc, out, err

    def __call__(self, host, cmd):
        self.calls.append((host, cmd))
        return self.rc, self.out, self.err


def test_command_rendering():
    c = route_command("igig.noctusai.com")
    assert "--origincert /etc/cloudflared/cert.pem route dns " + cd.TUNNEL_ID + " igig.noctusai.com" in c
    assert "--user 0" in c and ":ro" in c


def test_command_rejects_injection():
    import pytest
    with pytest.raises(ValueError):
        route_command("a.noctusai.com; rm -rf /")


def test_zone_and_diff_and_classify():
    assert in_zone("noctusai.com") and in_zone("a.noctusai.com")
    assert not in_zone("evilnoctusai.com") and not in_zone("a.example.com")
    assert missing_diff(["a", "b"], {"a": True}) == ["b"]
    assert classify_route_output(0, "INF Added CNAME", "") == "created"
    assert classify_route_output(1, "", "record with that host already exists") == "exists"
    assert classify_route_output(1, "", "boom") == "error"


def test_check_in_sync_and_missing(tmp_path):
    root = _root(tmp_path)
    r = cloudflare_dns("check", repo_root=root, resolver=lambda h: True)
    assert r["status"] == "in_sync" and r["checked"] == 3
    r = cloudflare_dns("check", repo_root=root, hosts=["x.noctusai.com"],
                       resolver=lambda h: h != "orbity.noctusai.com")
    assert r["status"] == "missing" and r["missing"] == ["orbity.noctusai.com"]


def test_check_resolver_error_is_unverified_not_missing(tmp_path):
    def boom(h):
        raise OSError("net down")
    r = cloudflare_dns("check", repo_root=_root(tmp_path), resolver=boom)
    assert r["status"] == "unverified" and r["ok"] is False and r["missing"] == []


def test_route_dry_run_does_not_ssh(tmp_path):
    ssh = FakeSsh()
    r = cloudflare_dns("route", hosts=["igig.noctusai.com"], repo_root=_root(tmp_path), ssh=ssh)
    assert r["status"] == "planned" and not ssh.calls


def test_route_confirm_runs_and_is_idempotent(tmp_path):
    ssh = FakeSsh(rc=1, out="", err="An A, AAAA, or CNAME record with that host already exists")
    r = cloudflare_dns("route", hosts=["igig.noctusai.com"], confirm=True,
                       repo_root=_root(tmp_path), ssh=ssh)
    assert r["ok"] and r["results"]["igig.noctusai.com"]["result"] == "exists"
    assert len(ssh.calls) == 1


def test_route_refusals(tmp_path):
    root = _root(tmp_path)
    ssh = FakeSsh()
    r = cloudflare_dns("route", hosts=["nope.noctusai.com", "x.example.com"], confirm=True,
                       repo_root=root, ssh=ssh)
    assert r["status"] == "refused" and not ssh.calls
    assert "ingress.yml" in r["refused"]["nope.noctusai.com"]
    assert "outside zone" in r["refused"]["x.example.com"]
    r = cloudflare_dns("route", hosts=["nope.noctusai.com"], allow_undeclared=True,
                       repo_root=root, ssh=ssh)
    assert r["status"] == "planned"
    r = cloudflare_dns("route", hosts=["x.example.com"], allow_undeclared=True, confirm=True,
                       repo_root=root, ssh=ssh)
    assert r["status"] == "refused"


def test_route_all_missing_and_failure_status(tmp_path):
    ssh = FakeSsh(rc=2, out="", err="denied")
    r = cloudflare_dns("route", all_missing=True, confirm=True, repo_root=_root(tmp_path),
                       resolver=lambda h: h == "noctusai.com", ssh=ssh)
    assert r["status"] == "error" and len(ssh.calls) == 2


def test_list_not_configured_and_configured(monkeypatch):
    monkeypatch.setattr(cd, "_resolve_token_hook", lambda: "")
    r = cloudflare_dns("list")
    assert r["status"] == "not_configured" and "CLOUDFLARE_API_TOKEN" in r["instruction"]
    monkeypatch.setattr(cd, "_resolve_token_hook", lambda: "tok")

    def http(url, hdr):
        if "zones?name" in url:
            return 200, {"result": [{"id": "z1"}]}
        return 200, {"result": [{"name": "a.noctusai.com", "type": "CNAME", "content": "t", "proxied": True}],
                     "result_info": {"total_pages": 1}}
    r = cloudflare_dns("list", http_get=http)
    assert r["status"] == "listed" and r["count"] == 1


def test_unknown_action():
    assert cloudflare_dns("zap")["ok"] is False
