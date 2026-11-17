"""Regression locks for the security-infra hardening (audit 2026-10-19, re-derived 2026-11-15).

Each assertion pins one hole that was open on the VPS: floating infra images, a
public WAHA, a password-less services/legacy Redis, legacy on the product network,
unauthenticated registry pulls. Static (YAML / text) checks on the committed
files + the pure halves of the keeper and the predeploy leg; the live half is the
runbook. KB § GUIDES/security-infra-hardening-runbook.md
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    _supply_chain_image_violation,
    check_supply_chain_pin,
)
from tools.noctus.dev.predeploy_check import audit_ghcr_access, audit_ghcr_login  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]


def _compose(rel: str) -> dict:
    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


# ── keeper: check_supply_chain_pin ─────────────────────────────────────────
class TestSupplyChainPin:
    def test_real_tree_is_clean(self):
        """CI backstop: the committed prod surface + workflows are fully pinned."""
        assert check_supply_chain_pin() == []

    def test_image_rules(self):
        bad = ["redis:latest", "redis", "redis:7-alpine", "pgvector/pgvector:pg16", "cloudflare/cloudflared:latest",
               "${WAHA_IMAGE:-devlikeapro/waha:latest}", "devlikeapro/waha:arm"]
        good = ["redis:7.4.6-alpine@sha256:" + "a" * 64, "n8nio/n8n:latest@sha256:" + "b" * 64, "devlikeapro/waha:noweb-2026.9.2",
                "${WAHA_IMAGE:-devlikeapro/waha:noweb-2026.9.2}", "ghcr.io/jraphaelsst/noctus-core:latest",
                "${POSTGRES_IMAGE:?set it}"]
        for ref in bad:
            assert _supply_chain_image_violation(ref), ref
        for ref in good:
            assert _supply_chain_image_violation(ref) is None, ref

    def test_flags_unpinned_image_and_action_and_honours_pin_ok(self, tmp_path):
        (tmp_path / "deploy/services").mkdir(parents=True)
        (tmp_path / ".github/workflows").mkdir(parents=True)
        (tmp_path / "deploy/services/compose.x.yml").write_text(
            "services:\n  a:\n    image: redis:latest\n  b:\n    # pin-ok: built locally\n    image: foo:latest\n",
            encoding="utf-8")
        (tmp_path / ".github/workflows/w.yml").write_text(
            "jobs:\n  j:\n    steps:\n      - uses: actions/checkout@v4\n"
            f"      - uses: actions/setup-node@{'b' * 40}  # v4\n      - uses: ./.github/actions/x\n",
            encoding="utf-8")
        issues = check_supply_chain_pin(repo_root=tmp_path)
        files = sorted(i["file"] for i in issues)
        assert files == [".github/workflows/w.yml", "deploy/services/compose.x.yml"], issues
        assert all(i["severity"] == "high" for i in issues)

    def test_paths_scope_limits_the_scan(self, tmp_path):
        (tmp_path / "deploy/tunnel").mkdir(parents=True)
        (tmp_path / "deploy/tunnel/compose.t.yml").write_text("services:\n  a:\n    image: x:latest\n", encoding="utf-8")
        assert check_supply_chain_pin(paths=[Path("deploy/other.yml")], repo_root=tmp_path) == []
        assert len(check_supply_chain_pin(paths=[Path("deploy/tunnel/compose.t.yml")], repo_root=tmp_path)) == 1


# ── predeploy leg: ghcr_login (pure verdicts) ──────────────────────────────
class TestGhcrLoginAudit:
    def test_logged_in_via_redacted_auth(self):
        ok, msg = audit_ghcr_login(json.dumps({"auths": {"ghcr.io": {"auth": "<redacted>"}}}))
        assert ok, msg

    def test_empty_auth_is_logged_out(self):
        ok, msg = audit_ghcr_login(json.dumps({"auths": {"ghcr.io": {"auth": ""}}}))
        assert not ok and "BLOCKED" in msg

    def test_cred_helper_counts(self):
        assert audit_ghcr_login(json.dumps({"credHelpers": {"ghcr.io": "pass"}}))[0]
        assert audit_ghcr_login(json.dumps({"credsStore": "pass"}))[0]

    def test_unparseable_or_missing_blocks(self):
        assert not audit_ghcr_login("")[0]
        assert not audit_ghcr_login("[]")[0]
        assert not audit_ghcr_login("{}")[0]

    def test_message_names_the_tool_and_never_echoes_a_credential(self):
        _, msg = audit_ghcr_login(json.dumps({"auths": {"ghcr.io": {"auth": ""}}}))
        assert "ghp_" not in msg and "ghcr_access" in msg

    def test_leg_is_registered(self):
        from tools.noctus.dev import predeploy_check as pc

        assert "ghcr_login" in pc.DEFAULT_CHECKS


class TestGhcrLoginFollowsReality:
    """The leg is a net, not a gate that fails in the normal flow: public => ok without a login."""

    def test_public_packages_need_no_login(self):
        ok, msg = audit_ghcr_access("public", None)
        assert ok and "public" in msg

    def test_private_packages_require_the_login(self):
        assert not audit_ghcr_access("private", "{}")[0]
        assert audit_ghcr_access("private", json.dumps({"auths": {"ghcr.io": {"auth": "<redacted>"}}}))[0]

    def test_unmeasurable_visibility_blocks(self):
        assert not audit_ghcr_access("unknown", None)[0]


# ── compose: n8n / WAHA / Redis / legacy ───────────────────────────────────
def test_n8n_is_digest_pinned_and_blocks_env_access_in_nodes():
    n8n = _compose("deploy/services/compose.services.yml")["services"]["n8n"]
    assert re.fullmatch(r"n8nio/n8n:latest@sha256:[0-9a-f]{64}", n8n["image"]), n8n["image"]
    assert n8n["environment"]["N8N_BLOCK_ENV_ACCESS_IN_NODE"] == "true"


# The digests PROD IS RUNNING (read from the VPS 2026-11-15): pinning them makes the deploy a no-op recreate.
RUNNING_PINS = {
    ("deploy/services/compose.services.yml", "postgres"): "postgres:16@sha256:f992505e18f114c1e5102ac4dcf00f791b44462f6a423d899320f0bbf80e386f",
    ("deploy/services/compose.services.yml", "redis"): "redis:latest@sha256:4d25e2fe601f7ffaeb4437cb6ced3518bc36edf34ebe98863c80836943d94529",
    ("deploy/services/compose.services.yml", "n8n"): "n8nio/n8n:latest@sha256:b4ce485c070c95efae9f42fa39918623f821d70ea255cdf6467b02865db3a00e",
    ("deploy/tunnel/compose.tunnel.yml", "cloudflared"): "cloudflare/cloudflared:latest@sha256:59bab8d3aceec09bf6bdb07d6beca0225ca5cd7ab79436a87ea97978fe1dc4f9",
    ("deploy/fleet/compose.infra.prod.yml", "redis"): "redis:7-alpine@sha256:ee64a64eaab618d88051c3ade8f6352d11531fcf79d9a4818b9b183d8c1d18ba",
    ("deploy/fleet/compose.infra.prod.yml", "cache-pg"): "pgvector/pgvector:pg16@sha256:00ba258a66dac104fd5171074a0084462a64a1369d8513f3d0a634e2f24d15bc",
}


def test_images_are_pinned_to_the_digests_prod_is_running():
    for (rel, svc), want in RUNNING_PINS.items():
        assert _compose(rel)["services"][svc]["image"] == want, (rel, svc)


def test_no_escape_markers_left_for_the_images_that_can_be_pinned():
    for rel in ("deploy/services/compose.services.yml", "deploy/fleet/compose.infra.prod.yml", "deploy/tunnel/compose.tunnel.yml"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "pin-ok" not in text and "image-pin-" not in text, rel


def test_waha_services_pinned_internal_hook_and_username_is_a_plain_default():
    env = _compose("deploy/services/compose.services.yml")["services"]["waha"]["environment"]
    for key in ("WAHA_DASHBOARD_USERNAME", "WHATSAPP_SWAGGER_USERNAME"):
        assert env[key] == "${WAHA_DASHBOARD_USERNAME:-noc-admin}", key  # not a secret: committed default, overridable
    assert env["WHATSAPP_HOOK_URL"].startswith("http://n8n:5678/")
    assert "@sha256:" in _compose("deploy/services/compose.services.yml")["services"]["waha"]["image"]
    infra = _compose("deploy/fleet/compose.infra.prod.yml")["services"]["waha"]["image"]
    assert "latest" not in infra


def test_waha_public_route_is_kept_until_the_owner_chooses_an_access_model():
    ingress = yaml.safe_load((ROOT / "deploy/tunnel/ingress.yml").read_text(encoding="utf-8"))
    assert "waha.noctusai.com" in [r.get("hostname") for r in ingress["routes"]]
    assert "waha.noctusai.com" not in ingress["retired"]


def test_no_deploy_consumer_reaches_waha_via_the_public_hostname():
    """Derived, not hand-listed: every tracked deploy/ + env-example file must use the internal name
    (the route declarations themselves, ingress.yml + its config template, are the one legitimate mention)."""
    offenders = []
    for f in sorted((ROOT / "deploy").rglob("*")):
        if not f.is_file() or f.suffix not in {".yml", ".yaml", ".example", ".env", ".template", ""}:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if "waha.noctusai.com" in line and not line.lstrip().startswith("#") and f.name not in {"ingress.yml", "config.yml.template"}:
                offenders.append(f"{f.relative_to(ROOT)}:{n}")
    assert not offenders, offenders


def _requirepass_services():
    for rel in ("deploy/services/compose.services.yml", "deploy/legacy/compose.legacy.yml"):
        for name, svc in _compose(rel)["services"].items():
            if "--requirepass" in " ".join(svc.get("command") or []):
                yield rel, name, svc


def test_services_and_legacy_redis_derive_a_password_and_the_healthcheck_authenticates():
    found = list(_requirepass_services())
    assert {n for _, n, _ in found} == {"redis", "legacy-redis"}
    for rel, name, svc in found:
        assert "@sha256:" in svc["image"], (rel, name)
        assert "REDISCLI_AUTH" in " ".join(svc["healthcheck"]["test"]), f"{rel}:{name} healthcheck would fail under requirepass"
        # The password is DERIVED into a gitignored env file; never a `:?` the operator must hand-supply.
        envf = svc["env_file"]
        assert envf and envf[0]["required"] is False and "redis-auth/" in envf[0]["path"], (rel, name)
        assert ":?" not in json.dumps(svc), (rel, name)


# What the services compose REQUIRED before this change (read from origin/dev). Adding to this set is what would make
# a merge block a deploy: every new knob must be derived or defaulted instead.
PROD_REQUIRED_SERVICES_VARS = {"POSTGRES_PASSWORD", "WHATSAPP_API_KEY", "WAHA_DASHBOARD_PASSWORD"}


def test_merging_requires_no_new_secret_anywhere():
    """A compose render with ONLY today's prod env keys must succeed: no `${VAR:?}` beyond what prod already has."""
    req = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*):\?")
    for rel, allowed in (("deploy/services/compose.services.yml", PROD_REQUIRED_SERVICES_VARS),
                         ("deploy/legacy/compose.legacy.yml", set()),
                         ("deploy/tunnel/compose.tunnel.yml", set())):
        needed = set(req.findall((ROOT / rel).read_text(encoding="utf-8")))
        assert needed <= allowed, f"{rel} newly requires {sorted(needed - allowed)}"
    # Fleet: every interpolated name is in the manifest, and the manifest gained no GHCR/Redis-password keys.
    keys = {l.strip() for l in (ROOT / "deploy/fleet/env.fleet.keys").read_text().splitlines()
            if l.strip() and not l.lstrip().startswith("#")}
    assert not {"GHCR_READ_USER", "GHCR_READ_TOKEN", "SERVICES_REDIS_PASSWORD", "LEGACY_REDIS_PASSWORD"} & keys


def test_services_redis_has_no_unauthenticated_clients():
    """The client list is DERIVED: any deploy/ file addressing the services Redis (host `redis`) must carry creds.
    Today there are none (n8n is SQLite; legacy moved to its own Redis), so adding one without a password fails here."""
    bare = re.compile(r"redis://(?![^/\s@]*@)redis(?::\d+)?\b")
    offenders = []
    for f in sorted((ROOT / "deploy").rglob("*")):
        if not f.is_file() or f.suffix not in {".yml", ".yaml", ".example", ".env", ".template", ""}:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if not line.lstrip().startswith("#") and bare.search(line):
                offenders.append(f"{f.relative_to(ROOT)}:{n}")
    assert not offenders, offenders


def test_legacy_is_off_the_product_network_and_the_tunnel_bridges_both():
    legacy = _compose("deploy/legacy/compose.legacy.yml")
    assert "noctus-net" not in legacy["networks"]
    for name, svc in legacy["services"].items():
        assert "noctus-net" not in svc["networks"], name
    tunnel = _compose("deploy/tunnel/compose.tunnel.yml")["services"]["cloudflared"]["networks"]
    assert {"noctus-net", "legacy-net"} <= set(tunnel)


# ── Redis passwords are DERIVED from the one master ────────────────────────
MASTER = "ab" * 32


class TestDerivedRedisPasswords:
    def test_services_env_is_the_hmac_of_the_master(self):
        from tools.noctus.dev import redis_acl as ra

        pw = ra.derive_password(MASTER, "services-redis", "1")
        assert ra.render_services_redis_env(MASTER) == f"REDIS_PASSWORD={pw}\n"
        assert re.fullmatch(r"[0-9a-f]{64}", pw)

    def test_legacy_env_carries_the_password_and_both_celery_urls(self):
        from tools.noctus.dev import redis_acl as ra

        pw = ra.derive_password(MASTER, "legacy-redis", "1")
        text = ra.render_legacy_redis_env(MASTER)
        assert f"LEGACY_REDIS_PASSWORD={pw}" in text
        assert f"CELERY_BROKER_URL=redis://:{pw}@legacy-redis:6379/0" in text
        assert f"CELERY_RESULT_BACKEND=redis://:{pw}@legacy-redis:6379/1" in text

    def test_users_get_distinct_passwords_and_rotate_with_the_generation(self):
        from tools.noctus.dev import redis_acl as ra

        a, b = (ra.derive_password(MASTER, u, "1") for u in ("services-redis", "legacy-redis"))
        assert a != b and ra.derive_password(MASTER, "services-redis", "2") != a

    def test_render_write_produces_both_files_0600_and_check_reports_them(self, tmp_path):
        from tools.noctus.dev import redis_acl as ra

        for rel in (ra.COMPOSE_REL, ra.SCOPE_REL):
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text((ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
        before = ra.redis_acl("check", repo_root=str(tmp_path))
        assert before["derived_env"] == {ra.SERVICES_ENV_REL: False, ra.LEGACY_ENV_REL: False}
        r = ra.redis_acl("render", write=True, repo_root=str(tmp_path), env={ra.MASTER_ENV: MASTER})
        assert r["ok"], r
        for rel in (ra.SERVICES_ENV_REL, ra.LEGACY_ENV_REL):
            f = tmp_path / rel
            assert f.is_file() and (f.stat().st_mode & 0o777) == 0o600, rel
        assert ra.derive_password(MASTER, "services-redis") in (tmp_path / ra.SERVICES_ENV_REL).read_text()
        assert all(ra.redis_acl("check", repo_root=str(tmp_path))["derived_env"].values())

    def test_outputs_are_gitignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        assert all(f"deploy/{d}/redis-auth/" in ignore for d in ("fleet", "services", "legacy"))


# ── ghcr_access: the install order is the tool's, the token is never exposed ─
class _Ssh:
    """Records every remote call; the `stdin_text` carries the secret and must never come back in a result."""

    def __init__(self, login_rc=0, write_rc=0, manifest_rc=0, config='{"auths": {"ghcr.io": {"auth": "<redacted>"}}}'):
        self.calls: list[tuple[str, str | None]] = []
        self.rcs = {"write": write_rc, "login": login_rc, "manifest": manifest_rc}
        self.config = config

    def __call__(self, cmd, stdin_text=None, **_kw):
        self.calls.append((cmd, stdin_text))
        if stdin_text is not None:
            return self.rcs["write"], "", f"oops {stdin_text.strip()}" if self.rcs["write"] else ""
        if "docker login" in cmd:
            return self.rcs["login"], "", "denied" if self.rcs["login"] else ""
        if "manifest inspect" in cmd:
            return self.rcs["manifest"], "", ""
        return 0, self.config, ""


TOKEN = "ghp_" + "A1b2C3d4" * 5


def _fetch(public: bool):
    def fetch(url, headers):
        if "/token" in url:
            return 200, json.dumps({"token": "anon"})
        return (200, "") if public else (401, "")
    return fetch


class TestGhcrAccess:
    def _call(self, ssh, public=True, confirm=True, token=TOKEN):
        from tools.noctus.dev.ghcr_access import ghcr_access

        return ghcr_access("install", confirm=confirm, repo_root=str(ROOT), env={}, token=token,
                           run_remote=ssh, fetch=_fetch(public))

    def test_owner_is_derived_from_the_compose_image_refs(self):
        from tools.noctus.dev import ghcr_access as g

        assert g.derive_owner((ROOT / g.COMPOSE_REL).read_text(encoding="utf-8")) == "jraphaelsst"
        assert "noctus-core" in g.derive_packages((ROOT / g.SCOPE_REL).read_text(encoding="utf-8"))

    def test_plan_without_confirm_touches_nothing(self):
        ssh = _Ssh()
        r = self._call(ssh, confirm=False)
        assert r["status"] == "planned" and r["ok"] and ssh.calls == []

    def test_install_order_write_then_login_then_verify_then_owner_step(self):
        ssh = _Ssh()
        r = self._call(ssh, public=True)
        assert r["ok"] and r["status"] == "installed"
        kinds = ["write" if s is not None else ("login" if "docker login" in c else ("manifest" if "manifest" in c else "read"))
                 for c, s in ssh.calls]
        assert kinds.index("write") < kinds.index("login") < kinds.index("manifest")
        assert "settings" in r["owner_step"]  # the flip URLs only appear AFTER a verified login

    def test_token_only_ever_rides_stdin(self):
        ssh = _Ssh()
        r = self._call(ssh)
        assert [c for c, s in ssh.calls if s is not None] and all(TOKEN not in c for c, _ in ssh.calls)
        assert TOKEN not in json.dumps(r)

    def test_a_rejected_login_stops_before_the_owner_step_and_leaks_nothing(self):
        r = self._call(_Ssh(login_rc=1))
        assert not r["ok"] and r["step"] == "docker_login" and "owner_step" not in r and TOKEN not in json.dumps(r)

    def test_a_failed_write_never_leaks_the_token_from_stderr(self):
        r = self._call(_Ssh(write_rc=1))
        assert not r["ok"] and r["step"] == "write_env" and TOKEN not in json.dumps(r)

    def test_bad_tokens_are_refused_without_quoting_them(self):
        from tools.noctus.dev.ghcr_access import validate_token

        assert validate_token(None)
        assert "fine-grained" in validate_token("github_pat_" + "x" * 40)
        assert validate_token("hello") and "hello" not in validate_token("hello")
        assert validate_token(TOKEN) is None

    def test_visibility_is_measured_not_flagged(self):
        from tools.noctus.dev.ghcr_access import classify_visibility, probe_visibility

        assert classify_visibility(200, 200) == "public"
        assert classify_visibility(200, 401) == "private" and classify_visibility(403, None) == "private"
        assert classify_visibility(0, None) == "unknown"
        assert probe_visibility("o", "p", _fetch(True)) == "public"
        assert probe_visibility("o", "p", _fetch(False)) == "private"

    def test_status_requires_login_only_once_private(self):
        from tools.noctus.dev.ghcr_access import ghcr_access

        out = ghcr_access("status", repo_root=str(ROOT), run_remote=_Ssh(config="{}"), fetch=_fetch(True))
        assert out["ok"] and not out["login_required"]
        out = ghcr_access("status", repo_root=str(ROOT), run_remote=_Ssh(config="{}"), fetch=_fetch(False))
        assert not out["ok"] and out["login_required"] and "ghcr_access" in out["fix"]


def test_run_remote_passes_stdin_to_the_runner_only_when_set():
    from tools.noctus.dev import _vps_ssh

    seen = []

    def runner(host, cmd, ct, to, *extra):
        seen.append(extra)
        return 0, "", ""

    state = {"_state_path": None}
    import tempfile, os

    with tempfile.TemporaryDirectory() as d:
        kw = dict(_runner=runner, _state_path=os.path.join(d, "s.json"), _sleep=lambda s: None, force=True)
        _vps_ssh.run_remote("h", "true", **kw)
        _vps_ssh.run_remote("h", "cat", stdin_text="x\n", **kw)
    assert seen == [(), ("x\n",)]


# ── image_pin: the construction half ───────────────────────────────────────
DIGEST = "sha256:" + "c" * 64


def _head(status=200, digest=DIGEST):
    def head(url, headers):
        if "token" in url:
            return 200, {"_body": json.dumps({"token": "t"})}
        return status, {"docker-content-digest": digest}
    return head


class TestImagePin:
    def test_split_and_pin_forms(self):
        from tools.noctus.dev import image_pin as ip

        assert ip.split_ref("redis")[:3] == ("docker.io", "library/redis", "latest")
        assert ip.split_ref("pgvector/pgvector:pg16")[:3] == ("docker.io", "pgvector/pgvector", "pg16")
        assert ip.split_ref("ghcr.io/o/p:1")[:3] == ("ghcr.io", "o/p", "1")
        assert ip.pinned("redis", DIGEST) == f"redis:latest@{DIGEST}"
        assert ip.pinned("redis:7@sha256:" + "d" * 64, DIGEST, "8") == f"redis:8@{DIGEST}"
        assert ip.pin_line("    image: ${W:-dev/waha:1.2}\n", DIGEST) == f"    image: ${{W:-dev/waha:1.2@{DIGEST}}}\n"

    def test_pin_writes_a_digest_that_satisfies_the_keeper(self, tmp_path):
        from tools.noctus.dev.image_pin import image_pin

        f = tmp_path / "deploy/services/compose.x.yml"
        f.parent.mkdir(parents=True)
        f.write_text("services:\n  a:\n    image: redis:latest\n  b:\n    # pin-ok: built locally\n    image: foo:latest\n", encoding="utf-8")
        assert not image_pin("check", repo_root=str(tmp_path))["ok"]
        plan = image_pin("pin", repo_root=str(tmp_path), head=_head())
        assert plan["status"] == "planned" and len(plan["changes"]) == 1
        assert image_pin("pin", write=True, repo_root=str(tmp_path), head=_head())["status"] == "written"
        assert f"image: redis:latest@{DIGEST}" in f.read_text() and "foo:latest\n" in f.read_text()
        assert check_supply_chain_pin(repo_root=tmp_path) == []
        assert image_pin("check", repo_root=str(tmp_path))["ok"]

    def test_unresolvable_image_is_reported_not_written(self, tmp_path):
        from tools.noctus.dev.image_pin import image_pin

        f = tmp_path / "deploy/tunnel/compose.t.yml"
        f.parent.mkdir(parents=True)
        f.write_text("services:\n  a:\n    image: x/y:latest\n", encoding="utf-8")
        r = image_pin("pin", write=True, repo_root=str(tmp_path), head=_head(status=404, digest=""))
        assert not r["ok"] and r["errors"] and "x/y" in f.read_text() and "@sha256" not in f.read_text()

    def test_bump_moves_the_tag_and_digest(self, tmp_path):
        from tools.noctus.dev.image_pin import image_pin

        f = tmp_path / "deploy/services/compose.x.yml"
        f.parent.mkdir(parents=True)
        f.write_text("services:\n  n:\n    image: n8nio/n8n:1.0.0@sha256:" + "e" * 64 + "\n", encoding="utf-8")
        r = image_pin("bump", write=True, image="n8nio/n8n", tag="2.1.0", repo_root=str(tmp_path), head=_head())
        assert r["ok"] and f"image: n8nio/n8n:2.1.0@{DIGEST}" in f.read_text()

    def test_real_tree_has_nothing_left_to_pin(self):
        from tools.noctus.dev.image_pin import image_pin

        assert image_pin("check", repo_root=str(ROOT))["ok"]

    def test_dependabot_moves_the_pins(self):
        text = (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")
        for d in ("fleet", "services", "legacy", "tunnel"):
            assert re.search(rf'package-ecosystem: "docker-compose"\n    directory: "/deploy/{d}"', text), d
