"""Colocated tests for noctus.dev.deploy_verify (the independent prod
revision-drift witness — 2026-08-13 phantom-deploy hole, refined 2026-08-17
after the first live run against real prod).

Zero real SSH / git / network — `run_remote` (the `vps_exec.exec_cmd` seam,
a full shell-command STRING per call), `run_local` (git: fetch/rev-parse/
cat-file/diff), and `live_products_fn` (the catalog query) are all injected.

Covers the 2026-08-17 refinement: a CATALOG-DRIVEN roster (ativo=true AND
deploy_scope='live' + core; a compose-only roster misses a catalog-live
product with NO container at all) and the BUILD-SCOPE diff predicate (raw
sha inequality is the wrong test — only a diff that touches a product's own
build inputs, or any seed/ / fleet-config path, is actionable drift), plus
the catalog-unreachable fallback to the checked-in build-scope.txt snapshot.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "mcp" / "noctusai"))

from tools.noctus.dev import build_scope as BS  # noqa: E402
from tools.noctus.dev import deploy_verify as DV  # noqa: E402

_CONTAINER_RE = re.compile(r"noctus-([a-z0-9-]+)")

_COMPOSE_YML = """\
services:
  core:
    container_name: noctus-core
    expose:
      - "8000"
  erp-imobiliario:
    container_name: noctus-erp-imobiliario
    expose:
      - "8001"
  igig:
    container_name: noctus-igig
    expose:
      - "8006"
  orbity:
    container_name: noctus-orbity
    expose:
      - "8007"
  seed:
    container_name: noctus-seed
    expose:
      - "8004"
  social-wiring:
    container_name: noctus-social-wiring
    expose:
      - "8005"
  adconnect:
    container_name: noctus-adconnect
    expose:
      - "8008"
  dev-team:
    container_name: noctus-dev-team
    expose:
      - "8009"
"""

_SHA = "prodtip0000000000000000000000000000"


class FakeVps:
    """Fakes the `run_remote` seam `vps_exec.exec_cmd` calls with — a single
    shell-command STRING per invocation."""

    def __init__(self, containers: dict[str, dict] | None = None,
                 transport_error: str | None = None,
                 transport_rc: int = 255):
        # slug -> {found, state, health, revision, probe_ok, health_body}
        self.containers = containers or {}
        self.calls: list[str] = []
        # When set, EVERY call fails the way ssh itself fails — rc 255 and a
        # transport message on stderr. Models an unreachable host / an open
        # circuit breaker, where the probe learns nothing about the container.
        self.transport_error = transport_error
        self.transport_rc = transport_rc

    def __call__(self, cmd: str) -> tuple[int, str, str]:
        self.calls.append(cmd)
        if self.transport_error is not None:
            return self.transport_rc, "", self.transport_error
        m = _CONTAINER_RE.search(cmd)
        slug = m.group(1) if m else ""
        info = self.containers.get(slug, {})
        if "curl" in cmd:  # the in-container /api/health active probe
            if info.get("probe_ok", True):
                body = info.get("health_body", {"status": "ok", "startup_hook_error": None})
                return 0, json.dumps(body), ""
            return 1, "", "curl: (7) Failed to connect: Connection refused"
        # docker inspect
        if not info.get("found", True):
            return 1, "", f"Error: No such object: noctus-{slug}"
        parts = [
            info.get("state", "running"),
            info.get("health", "healthy"),
            info.get("revision", ""),
        ]
        return 0, "|".join(parts) + "\n", ""

    def flat(self) -> str:
        return " | ".join(self.calls)


class FakeGit:
    """Fakes `run_local` — git fetch/rev-parse (the prod-tip resolution) and
    git cat-file/diff (the build-scope drift predicate)."""

    def __init__(self, expected_sha=_SHA, fetch_rc=0, rev_rc=0,
                 known_commits: set[str] | None = None,
                 diffs: dict[str, list[str]] | None = None):
        self.expected_sha = expected_sha
        self.fetch_rc, self.rev_rc = fetch_rc, rev_rc
        self.known_commits = known_commits or set()
        self.diffs = diffs or {}  # running_rev -> list[changed files]
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list[str]) -> tuple[int, str, str]:
        self.calls.append(cmd)
        if cmd[:2] == ["git", "fetch"]:
            return (self.fetch_rc, "", "" if self.fetch_rc == 0 else "network unreachable")
        if cmd[:2] == ["git", "rev-parse"]:
            return (self.rev_rc, (self.expected_sha + "\n") if self.rev_rc == 0 else "",
                    "" if self.rev_rc == 0 else "unknown revision")
        if cmd[:2] == ["git", "cat-file"]:
            rev = cmd[3].split("^")[0]
            ok = rev in self.known_commits
            return (0, "", "") if ok else (1, "", "fatal: Not a valid object name")
        if cmd[:2] == ["git", "diff"]:
            rng = cmd[3]  # "<rev>..<expected>"
            rev = rng.split("..", 1)[0]
            files = self.diffs.get(rev, [])
            return (0, "\n".join(files) + ("\n" if files else ""), "")
        return (0, "", "")


def _run(products=None, containers=None, diffs=None, known_commits=None,
         live=("erp-imobiliario", "igig", "orbity", "seed", "social-wiring"),
         **kw):
    vps = FakeVps(containers or {})
    git = FakeGit(known_commits=known_commits or set(), diffs=diffs or {})
    kw.setdefault("repo_root", str(_REPO_ROOT))
    r = DV.deploy_verify(
        products=products, run_remote=vps, run_local=git,
        live_products_fn=(lambda: list(live)),
        **kw,
    )
    return r, vps, git


def _with_compose(tmp_path, **kw):
    (tmp_path / "compose.yml").write_text(_COMPOSE_YML)
    kw.setdefault("repo_root", str(tmp_path))
    kw.setdefault("compose_file", "compose.yml")
    return kw


# ── catalog-driven roster ─────────────────────────────────────────────
def test_verified_when_no_build_relevant_diff_and_inactive_skipped(tmp_path):
    """erp-imobiliario matches exactly; igig is stale but its diff touches
    NOTHING build-relevant (docs only) — both 'ok'. adconnect is running in
    the fleet but NOT catalog-live — reported, never counted."""
    kw = _with_compose(tmp_path)
    r, vps, git = _run(
        containers={
            "erp-imobiliario": {"revision": _SHA},
            "igig": {"revision": "OLDIGIG00000000000000000000000000"},
            "orbity": {"revision": _SHA},
            "seed": {"revision": _SHA},
            "social-wiring": {"revision": _SHA},
            "adconnect": {"revision": "VERYOLDREV0000000000000000000000"},
            "core": {"revision": _SHA},
        },
        known_commits={"OLDIGIG00000000000000000000000000"},
        diffs={"OLDIGIG00000000000000000000000000": ["docs/whatever.md", "README.md"]},
        **kw,
    )
    assert r["status"] == "verified" and r["exit_code"] == 0
    assert r["missing"] == [] and r["drifted"] == [] and r["degraded"] == []
    assert "adconnect" in r["skipped_inactive"]
    adconnect = next(p for p in r["products"] if p["product"] == "adconnect")
    assert adconnect["actionable"] is False and adconnect["revision"] == "VERYOLDREV0000000000000000000000"
    assert adconnect["verdict"] is None  # informational only, no pass/fail computed


def test_drift_when_diff_touches_the_products_own_build_scope(tmp_path):
    kw = _with_compose(tmp_path)
    old = "OLDORBITY000000000000000000000000"
    r, vps, git = _run(
        containers={
            "erp-imobiliario": {"revision": _SHA}, "igig": {"revision": _SHA},
            "orbity": {"revision": old}, "seed": {"revision": _SHA},
            "social-wiring": {"revision": _SHA}, "core": {"revision": _SHA},
        },
        known_commits={old},
        diffs={old: ["products/orbity/backend/app/main.py", "docs/x.md"]},
        **kw,
    )
    assert r["status"] == "drift_detected" and r["exit_code"] == 1
    assert r["drifted"] == ["orbity"]
    orbity = next(p for p in r["products"] if p["product"] == "orbity")
    assert orbity["changed_file_count"] == 2
    assert orbity["fleet_wide_change"] is False
    assert "products/orbity/backend/app/main.py" in orbity["build_relevant_files"]


def test_fleet_wide_seed_change_flags_drift_for_every_actionable_product(tmp_path):
    kw = _with_compose(tmp_path)
    old = "OLDSEEDCHANGE00000000000000000000"
    r, vps, git = _run(
        containers={
            "erp-imobiliario": {"revision": old}, "igig": {"revision": _SHA},
            "orbity": {"revision": _SHA}, "seed": {"revision": _SHA},
            "social-wiring": {"revision": _SHA}, "core": {"revision": _SHA},
        },
        known_commits={old},
        diffs={old: ["seed/lib/backend/noctusai_lib/foo.py"]},
        **kw,
    )
    assert r["status"] == "drift_detected"
    assert r["drifted"] == ["erp-imobiliario"]
    erp = next(p for p in r["products"] if p["product"] == "erp-imobiliario")
    assert erp["fleet_wide_change"] is True


def test_raw_sha_inequality_alone_is_not_drift():
    """The 2026-08-17 fix in one assertion: stale-but-untouched must be ok."""
    old = "STALEBUTSAFEREV00000000000000000"
    r, vps, git = _run(
        products=["igig"],
        containers={"igig": {"revision": old}},
        known_commits={old},
        diffs={old: ["KNOWLEDGE-BASE/whatever.md"]},
    )
    assert r["status"] == "verified"
    igig = r["products"][0]
    assert igig["verdict"] == "ok"
    assert igig["revision"] == old != _SHA
    assert "expected steady state" in igig["note"]


def test_unverifiable_when_running_revision_unresolvable_locally():
    old = "UNKNOWNTOTHISCLONE0000000000000"
    r, vps, git = _run(products=["orbity"], containers={"orbity": {"revision": old}},
                       known_commits=set())  # NOT known
    assert r["status"] == "unverifiable" and r["exit_code"] == 1
    assert r["products"][0]["verdict"] == "unverifiable"
    assert "does not resolve to a known commit" in r["products"][0]["note"]


# ── missing (catalog-live, absent from the fleet entirely) ────────────
def test_missing_when_catalog_live_product_has_no_container_at_all(tmp_path):
    """The p-studio case (2026-08-17): ativo=true+live in the catalog, but
    no service in compose AND no running container — a compose-driven loop
    could never even iterate this slug."""
    kw = _with_compose(tmp_path)
    r, vps, git = _run(
        containers={
            "erp-imobiliario": {"revision": _SHA}, "igig": {"revision": _SHA},
            "orbity": {"revision": _SHA}, "seed": {"revision": _SHA},
            "social-wiring": {"revision": _SHA}, "core": {"revision": _SHA},
            "p-studio": {"found": False},
        },
        live=("erp-imobiliario", "igig", "orbity", "seed", "social-wiring", "p-studio"),
        **kw,
    )
    assert r["status"] == "missing" and r["exit_code"] == 1
    assert r["missing"] == ["p-studio"]
    ps = next(p for p in r["products"] if p["product"] == "p-studio")
    assert ps["container"] == "noctus-p-studio"  # guessed — no compose service to name it
    assert ps["found"] is False and ps["actionable"] is True


def test_missing_takes_priority_over_drift_in_overall_status(tmp_path):
    kw = _with_compose(tmp_path)
    old = "OLDORBITY000000000000000000000000"
    r, vps, git = _run(
        containers={
            "erp-imobiliario": {"revision": _SHA}, "igig": {"revision": _SHA},
            "orbity": {"revision": old}, "seed": {"revision": _SHA},
            "social-wiring": {"revision": _SHA}, "core": {"revision": _SHA},
            "p-studio": {"found": False},
        },
        known_commits={old}, diffs={old: ["products/orbity/backend/x.py"]},
        live=("erp-imobiliario", "igig", "orbity", "seed", "social-wiring", "p-studio"),
        **kw,
    )
    assert r["status"] == "missing"  # not 'drift_detected', even though orbity IS drifted
    assert r["missing"] == ["p-studio"] and r["drifted"] == ["orbity"]


# ── core: always actionable, no catalog row ────────────────────────────
def test_core_is_always_actionable_with_an_empty_catalog(tmp_path):
    kw = _with_compose(tmp_path)
    r, vps, git = _run(containers={"core": {"revision": _SHA}}, live=(), **kw)
    core = next(p for p in r["products"] if p["product"] == "core")
    assert core["actionable"] is True and core["verdict"] == "ok"


# ── health downgrades 'ok', never relabels drift/missing/unverifiable ──
def test_health_problem_downgrades_ok_to_degraded():
    r, vps, git = _run(
        products=["igig"],
        containers={"igig": {"revision": _SHA, "health_body":
                              {"status": "ok", "startup_hook_error": "boom"}}},
    )
    assert r["status"] == "degraded"
    assert r["products"][0]["verdict"] == "degraded"


def test_health_problem_does_not_relabel_a_drifted_product():
    old = "OLDORBITY000000000000000000000000"
    r, vps, git = _run(
        products=["orbity"],
        containers={"orbity": {"revision": old, "probe_ok": False}},
        known_commits={old}, diffs={old: ["products/orbity/backend/x.py"]},
    )
    assert r["products"][0]["verdict"] == "drift"  # stays drift, not degraded
    assert r["status"] == "drift_detected"


# ── skipped_inactive is truly excluded ─────────────────────────────────
def test_skipped_inactive_never_counts_even_if_wildly_behind(tmp_path):
    kw = _with_compose(tmp_path)
    ancient = "ANCIENTREV0000000000000000000000"
    r, vps, git = _run(
        containers={
            "erp-imobiliario": {"revision": _SHA}, "igig": {"revision": _SHA},
            "orbity": {"revision": _SHA}, "seed": {"revision": _SHA},
            "social-wiring": {"revision": _SHA}, "core": {"revision": _SHA},
            "adconnect": {"revision": ancient, "health": "unhealthy"},
        },
        known_commits={ancient}, diffs={ancient: ["seed/anything.py"]},
        **kw,
    )
    assert r["status"] == "verified"  # adconnect's real drift+unhealth never counted
    assert r["drifted"] == [] and r["degraded"] == []
    assert set(r["skipped_inactive"]) == {"adconnect", "dev-team"}
    # the drift call was never even made for a skipped product (no git diff)
    assert not any(c[:2] == ["git", "diff"] for c in git.calls)


# ── products= override bypasses the catalog ─────────────────────────────
def test_products_override_treats_an_inactive_product_as_actionable():
    old = "OLDADCONNECT0000000000000000000"
    r, vps, git = _run(
        products=["adconnect"],
        containers={"adconnect": {"revision": old}},
        known_commits={old}, diffs={old: ["products/adconnect/backend/x.py"]},
        live=(),  # NOT catalog-live — override must not care
    )
    assert r["products"][0]["actionable"] is True
    assert r["status"] == "drift_detected"
    assert r["catalog_source"] == "explicit_override"


# ── expected-sha resolution: fail-closed, never a silent pass ──────────
def test_unresolvable_prod_tip_refuses_to_verify_anything():
    r = DV.deploy_verify(products=["core"], run_remote=FakeVps({"core": {"revision": "X"}}),
                         run_local=FakeGit(rev_rc=1), repo_root=str(_REPO_ROOT))
    assert r["status"] == "error" and r["ok"] is False
    assert "cannot resolve" in r["error"]


def test_git_fetch_failure_also_refuses():
    r = DV.deploy_verify(products=["core"], run_remote=FakeVps({}),
                         run_local=FakeGit(fetch_rc=1), repo_root=str(_REPO_ROOT))
    assert r["status"] == "error"


def test_expected_sha_is_never_the_callers_parameter():
    """No `expected_sha=`/`sha=` kwarg on the public signature — the ONLY
    way to influence it is which prod_branch/remote to resolve, never a
    literal value."""
    import inspect
    sig = inspect.signature(DV.deploy_verify)
    assert "sha" not in sig.parameters and "expected_sha" not in sig.parameters


# ── catalog source: live query vs the derived fallback ─────────────────
def test_catalog_unreachable_falls_back_to_build_scope_txt(tmp_path, monkeypatch):
    scope = tmp_path / "build-scope.txt"
    scope.write_text("# Last refresh: 2026-08-11 — 5 live + 1 platform.\n\ncore\nigig\nseed\n")
    monkeypatch.setattr(BS, "SCOPE_PATH", scope)

    def _boom():
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set")

    kw = _with_compose(tmp_path)
    vps = FakeVps({"igig": {"revision": _SHA}, "seed": {"revision": _SHA}, "core": {"revision": _SHA}})
    r = DV.deploy_verify(run_remote=vps, run_local=FakeGit(), live_products_fn=_boom, **kw)
    assert r["catalog_source"] == "build_scope_fallback"
    assert "2026-08-11" in r["catalog_warning"]
    assert "refresh_build_scope" in r["catalog_warning"]
    assert r["status"] == "verified"


def test_catalog_and_fallback_both_unavailable_is_a_hard_error(tmp_path, monkeypatch):
    monkeypatch.setattr(BS, "SCOPE_PATH", tmp_path / "nope.txt")

    def _boom():
        raise RuntimeError("no creds")

    r = DV.deploy_verify(run_remote=FakeVps({}), run_local=FakeGit(),
                         live_products_fn=_boom, repo_root=str(tmp_path),
                         compose_file="compose.yml")
    assert r["status"] == "error"
    assert "REFUSING to guess" in r["error"]


def test_live_catalog_success_never_touches_build_scope_txt(tmp_path):
    """The primary path doesn't even read the fallback file."""
    kw = _with_compose(tmp_path)
    r, vps, git = _run(containers={"core": {"revision": _SHA}}, live=(), **kw)
    assert r["catalog_source"] == "live_catalog"
    assert r["catalog_warning"] is None


# ── compose-roster parsing (lookup only, never gates actionability) ────
def test_compose_provides_container_and_port_lookup_only(tmp_path):
    kw = _with_compose(tmp_path)
    r, vps, git = _run(containers={"igig": {"revision": _SHA}}, live=("igig",), **kw)
    igig = next(p for p in r["products"] if p["product"] == "igig")
    assert igig["container"] == "noctus-igig" and igig["port"] == "8006"
    assert any("curl" in c for c in vps.calls)  # port resolved -> probe ran


# ── transport failure is NOT evidence of a missing container ───────────
# Regression for 2026-09-01: `deploy_verify` reported social-wiring
# `missing` ("not deployed at all") twice while the container was running
# and healthy — once on "ssh: Network is unreachable", once on the circuit
# breaker's own fast-fail, which explicitly says "no connection attempted".
# `missing` is a rollback-grade claim; asserting it when the probe never
# reached the host invents a fact. `unverifiable` already existed for
# exactly this and was simply never reached.

def test_ssh_transport_failure_is_unverifiable_not_missing():
    vps = FakeVps(transport_error="ssh: connect to host 1.2.3.4 port 22: Network is unreachable")
    r = DV.deploy_verify(products=["core"], run_remote=vps,
                         run_local=FakeGit(), repo_root=str(_REPO_ROOT))
    assert r["missing"] == [], "a host we could not reach must never be reported as not-deployed"
    assert r["unverifiable"] == ["core"]
    assert r["status"] == "unverifiable"
    note = r["products"][0]["note"]
    assert "could not REACH" in note and "UNKNOWN" in note


def test_open_circuit_breaker_is_unverifiable_not_missing():
    """The breaker's fast-fail path returns rc 255 and says so in words."""
    vps = FakeVps(transport_error=(
        "ssh circuit OPEN for noctus-vps — FAST FAIL, no connection attempted: "
        "2 consecutive connection failures; cooling down for 435s more."
    ))
    r = DV.deploy_verify(products=["core"], run_remote=vps,
                         run_local=FakeGit(), repo_root=str(_REPO_ROOT))
    assert r["missing"] == []
    assert r["unverifiable"] == ["core"]


def test_transport_detected_from_stderr_even_without_rc_255():
    """A runner that collapses exit codes must still not yield `missing`."""
    vps = FakeVps(transport_error="ssh: Could not resolve hostname noctus-vps",
                  transport_rc=1)
    r = DV.deploy_verify(products=["core"], run_remote=vps,
                         run_local=FakeGit(), repo_root=str(_REPO_ROOT))
    assert r["missing"] == [] and r["unverifiable"] == ["core"]


def test_genuinely_absent_container_is_still_missing():
    """The other side of the proof — the real finding must survive the fix.
    `docker inspect` on an absent container exits 1 with 'No such object'."""
    r = DV.deploy_verify(products=["core"], run_remote=FakeVps({"core": {"found": False}}),
                         run_local=FakeGit(), repo_root=str(_REPO_ROOT))
    assert r["missing"] == ["core"]
    assert r["status"] == "missing"
    assert "not deployed at all" in r["products"][0]["note"]
