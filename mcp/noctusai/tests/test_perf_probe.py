"""`noctus.dev.perf_probe` — client-view perf analysis. Fixture captures only; no network."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import perf_probe as pp  # noqa: E402

UUID = "3f2b8c1e-9a4d-4e6f-8b1a-0c2d3e4f5a6b"
HEX = "a1b2c3d4e5f60718"
OPAQUE = "V1StGXR8Z5jdHi6B"


def _call(where, start, dur, app=None, size=1000, status=200, ttfb=None):
    return [where, start, dur, ttfb if ttfb is not None else dur / 2, app, size, status]


def _cap(pages, host="orbity.noctusai.com"):
    return {"v": 1, "host": host, "ua": "x", "pages": pages}


def _page(path, api):
    return {"path": path, "at": "2026-10-22T10:00:00Z", "nav": {"ttfb": 50, "dcl": 200, "load": 300, "bytes": 5000},
            "api": api, "assets": {"script": {"n": 3, "bytes": 1000, "end": 200}}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(pp, "live_slugs", lambda: {"orbity"})
    return tmp_path / "store"


def _write(tmp_path, cap, name="cap.json"):
    f = tmp_path / name
    f.write_text(json.dumps(cap))
    return str(f)


def test_templating():
    assert pp.template_path(f"/api/clientes/{UUID}/notas") == "/api/clientes/{id}/notas"
    assert pp.template_path("/api/clientes/12345") == "/api/clientes/{id}"
    assert pp.template_path(f"/x/{HEX}") == "/x/{id}"
    assert pp.template_path(f"/x/{OPAQUE}") == "/x/{id}"
    assert pp.template_path("/api/notificacoes") == "/api/notificacoes"
    assert pp.template_where(f"/api/items/{UUID}?page&sort") == "/api/items/{id}?page&sort"
    assert pp.template_where("api.stripe.com/v1/charges/98765?expand") == "api.stripe.com/v1/charges/{id}?expand"


def test_chain_depth_and_parallel():
    assert pp.chain_depth([(0, 100), (0, 100), (10, 50)]) == 1
    assert pp.chain_depth([(0, 100), (100, 50), (150, 20)]) == 3
    assert pp.chain_depth([]) == 0


def test_ingest_summary_duplicates_and_no_raw_ids(env, tmp_path):
    pg = _page(f"/clientes/{UUID}", [
        _call("/api/me", 0, 100, app=20), _call(f"/api/clientes/{UUID}", 110, 200, app=50),
        _call("/api/notas?page", 120, 80), _call("/api/notas?page", 130, 90)])
    r = pp.perf_probe("ingest", scope="orbity", label="a", capture=_write(tmp_path, _cap([pg])), store=str(env))
    assert r["ok"], r
    raw = Path(r["path"]).read_text()
    assert UUID not in raw
    s = json.loads(raw)
    p = s["pages"][0]
    assert p["path"] == "/clientes/{id}"
    assert p["duplicates"] == {"/api/notas?page": 2}
    assert p["data_ready_ms"] == 310 and p["chain_depth"] == 2
    ep = s["endpoints"]["/api/clientes/{id}"]
    assert ep["network_p50_ms"] == 150 and ep["app_p50_ms"] == 50


def test_refusals(env, tmp_path):
    ok = _cap([_page("/a", [_call("/api/x", 0, 10)])])
    bad_v = dict(ok, v=2)
    for cap, scope, frag in [(bad_v, "orbity", "version"), (dict(ok, pages=[]), "orbity", "no pages"),
                             (ok, "other.example.com", "disagrees"), (ok, "nosuchslug", "neither")]:
        r = pp.perf_probe("ingest", scope=scope, label="a", capture=_write(tmp_path, cap), store=str(env))
        assert r["status"] == "error" and frag in r["error"], r
    r = pp.perf_probe("ingest", scope="orbity", label="../x", capture=_write(tmp_path, ok), store=str(env))
    assert r["status"] == "error"


def test_overwrite_refused(env, tmp_path):
    c = _write(tmp_path, _cap([_page("/a", [_call("/api/x", 0, 10)])]))
    assert pp.perf_probe("ingest", scope="orbity", label="a", capture=c, store=str(env))["ok"]
    assert "exists" in pp.perf_probe("ingest", scope="orbity", label="a", capture=c, store=str(env))["error"]
    assert pp.perf_probe("ingest", scope="orbity", label="a", capture=c, store=str(env), overwrite=True)["ok"]


def _load_many(env, tmp_path, label, durs, scope="orbity", host="orbity.noctusai.com", route="/api/items", app=None):
    pages = [_page("/p", [_call(route, 0, d, app=app)]) for d in durs]
    r = pp.perf_probe("ingest", scope=scope, label=label, capture=_write(tmp_path, _cap(pages, host), label + ".json"),
                      store=str(env))
    assert r["ok"], r


def test_report_budget_over_and_ok_and_inconclusive(env, tmp_path):
    _load_many(env, tmp_path, "slow", [400] * 6)
    r = pp.perf_probe("report", scope="orbity", label="slow", store=str(env))
    assert r["status"] == "over_budget" and r["budget"]["over_budget"][0]["class"] == "read"
    _load_many(env, tmp_path, "fast", [100] * 6)
    assert pp.perf_probe("report", scope="orbity", label="fast", store=str(env))["status"] == "ok"
    _load_many(env, tmp_path, "thin", [900, 900])
    assert pp.perf_probe("report", scope="orbity", label="thin", store=str(env))["status"] == "inconclusive"
    _load_many(env, tmp_path, "shell", [200] * 6, route="/api/me")
    assert pp.perf_probe("report", scope="orbity", label="shell", store=str(env))["status"] == "over_budget"


def test_report_network_vs_app_and_external(env, tmp_path):
    _load_many(env, tmp_path, "net", [500] * 6, app=40)
    r = pp.perf_probe("report", scope="orbity", label="net", store=str(env))
    assert r["findings"]["edge_bound"] and r["budget"]["over_budget"][0]["basis"] == "network"
    _load_many(env, tmp_path, "ext", [500] * 6, scope="app.vendor.io", host="app.vendor.io")
    e = pp.perf_probe("report", scope="app.vendor.io", label="ext", store=str(env))
    assert e["kind"] == "external" and e["status"] == "ok" and "budget" not in e


def test_report_filters(env, tmp_path):
    pages = [_page("/a", [_call("/api/x", 0, 50)] * 1), _page("/b", [_call("/api/y", 0, 900)])]
    pp.perf_probe("ingest", scope="orbity", label="f", capture=_write(tmp_path, _cap(pages)), store=str(env))
    r = pp.perf_probe("report", scope="orbity", label="f", store=str(env), pages=["/a"])
    assert [p["page"] for p in r["findings"]["slowest_pages"]] == ["/a"]
    assert [e["endpoint"] for e in r["findings"]["slowest_endpoints"]] == ["/api/x"]


def test_compare_noise_floor_and_verdicts(env, tmp_path):
    def cap(rows):
        return _cap([_page("/p", [_call(r, 0, d) for r, d in rows])])
    before = [("/api/a", 400), ("/api/b", 100), ("/api/c", 200), ("/api/d", 100), ("/api/gone", 50)]
    after = [("/api/a", 200), ("/api/b", 120), ("/api/c", 400), ("/api/d", 105), ("/api/new", 50)]
    for lab, rows in (("b", before), ("a", after)):
        pp.perf_probe("ingest", scope="orbity", label=lab, capture=_write(tmp_path, cap(rows), lab), store=str(env))
    r = pp.perf_probe("compare", scope="orbity", before="b", after="a", store=str(env))
    v = {x["endpoint"]: x["verdict"] for x in r["endpoints"]}
    assert v == {"/api/a": "improved", "/api/b": "unchanged", "/api/c": "regressed", "/api/d": "unchanged",
                 "/api/gone": "gone", "/api/new": "new"}
    assert r["status"] == "regressed"
    only = pp.perf_probe("compare", scope="orbity", before="b", after="a", store=str(env), endpoints=["/api/a"])
    assert only["status"] == "improved"


def test_compare_missing_label_and_list(env, tmp_path):
    assert pp.perf_probe("compare", scope="orbity", before="x", after="y", store=str(env))["status"] == "error"
    _load_many(env, tmp_path, "one", [10])
    assert pp.perf_probe("list", store=str(env))["scopes"] == {"orbity": ["one"]}


def test_snippets():
    assert "__noc_perf" in pp.snippet("append")["js"]
    r = pp.snippet("read", offset=2000, size=500)["js"]
    assert "2000" in r and "500" in r and "__OFFSET__" not in r
    assert "removeItem" in pp.snippet("clear")["js"]
    assert pp.perf_probe("snippet", kind="nope")["status"] == "error"


def test_edge_floor_is_reported_never_budgeted(env, tmp_path):
    # Cloudflare's RUM beacon is answered by the edge, never the origin: it is the network floor,
    # not an app endpoint -- a slow beacon must not turn the product verdict over_budget.
    pages = [_page("/x", [_call("/cdn-cgi/rum", 10, 900, size=300, status=204),
                          _call("/api/items", 10, 120, app=60)]) for _ in range(6)]
    pp.perf_probe("ingest", scope="orbity", label="edge", capture=_write(tmp_path, _cap(pages)), store=str(env))
    r = pp.perf_probe("report", scope="orbity", label="edge", store=str(env))
    assert r["findings"]["edge_floor"] == [{"endpoint": "/cdn-cgi/rum", "count": 6, "p50_ms": 900, "p95_ms": 900}]
    assert all(row["endpoint"] != "/cdn-cgi/rum" for row in r["budget"]["routes"])
    assert r["status"] == "ok"


# --------------------------------------------------------------------------- concurrency metrics (2026-10-23)
def _xcall(where, dur, app, x):
    c = _call(where, 0, dur, app=app)
    c.append(x)
    return c


def test_concurrency_metrics_kept_and_omitted_when_absent(env, tmp_path):
    x = lambda i: {"inflight": i, "inflight_peak": i + 2, "blkq": i * 10.0}
    pg = _page("/", [_xcall("/api/me/access", 200, 150, x(i)) for i in range(1, 6)]
               + [_call("/api/old", 0, 50, app=20)] * 5)
    pp.perf_probe("ingest", scope="orbity", label="a", capture=_write(tmp_path, _cap([pg])), store=str(env))
    s = json.loads((env / "orbity" / "a.json").read_text())
    ep = s["endpoints"]["/api/me/access"]
    assert ep["inflight_peak_p50"] == 5 and ep["blkq_p95"] == 50.0 and "lag_p50" not in ep
    assert "inflight_p50" not in s["endpoints"]["/api/old"]  # old-style tuple: nothing invented
    rep = pp.perf_probe("report", scope="orbity", label="a", store=str(env))
    assert [r["endpoint"] for r in rep["findings"]["concurrency"]] == ["/api/me/access"]


def test_compare_surfaces_concurrency_extras(env, tmp_path):
    def cap(peak):
        return _cap([_page("/", [_xcall("/api/me/access", 200, 150, {"inflight_peak": peak}) for _ in range(5)])])
    pp.perf_probe("ingest", scope="orbity", label="b", capture=_write(tmp_path, cap(1), "b.json"), store=str(env))
    pp.perf_probe("ingest", scope="orbity", label="c", capture=_write(tmp_path, cap(6), "c.json"), store=str(env))
    r = pp.perf_probe("compare", scope="orbity", before="b", after="c", store=str(env))
    row = r["endpoints"][0]
    assert row["inflight_peak_p50"] == [1.0, 6.0] and "blkq_p50" not in row
