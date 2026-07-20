"""Colocated regression tests for ``check_prod_exposure_consent``.

The gate closes the orbity incident (2026-06-03: a product went prod-
serving the same day it was scaffolded, six weeks before validation, no
consent decision anywhere) — commit 679d0838 registered orbity on three
surfaces simultaneously (deploy/fleet/docker-compose.prod.yml,
deploy/tunnel/ingress.yml, ALL_SLUGS in scripts/infra/build-and-push.sh).

Scenarios (mirrors the brief's three required proofs):
  fire       — reproduces 679d0838's pre-fix shape: HEAD has no orbity on
               any surface + no consent record; working tree adds orbity
               to all three. Keeper fires high on 'orbity'.
  pass       — same registration, but a VALID deploy/consent/orbity.prod.yml
               is already committed at HEAD (consented_by matches the repo's
               configured git author, dev_validated: true, consent_ref
               resolves to a ✅-marked roadmap milestone). Keeper is silent.
  silent     — orbity is ALREADY registered at HEAD (baseline == declared);
               a routine products/orbity/** commit changes an unrelated
               file. Keeper is silent (the set-difference is empty) — this
               is the case that matters most (no false-positive noise on
               ordinary product development).

Plus: non-noc tree silent-skip, isolated-consent-commit enforcement, and
the de-registration-always-allowed case.

Each test uses a REAL temp git repo (subprocess git) so the keeper's HEAD-
vs-working-tree + staged-diff git calls exercise the real code path.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_prod_exposure_consent,
    _resolve_roadmap_milestone,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

AUTHOR_EMAIL = "test@example.com"


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(root)] + list(args),
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    """Minimal git repo with matching local user.email (so `consented_by`
    can be made to match deterministically)."""
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", AUTHOR_EMAIL)
    _git(tmp_path, "config", "user.name", "Test")
    readme = tmp_path / "README.md"
    readme.write_text("hello\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def _compose_yaml(slugs: list[str]) -> str:
    lines = ["services:"]
    for s in slugs:
        lines.append(f"  {s}:")
        lines.append(f"    image: ghcr.io/x/noctus-{s}:latest")
    lines.append("networks:")
    lines.append("  noctus-net:")
    lines.append("    external: true")
    return "\n".join(lines) + "\n"


def _ingress_yaml(slugs: list[str]) -> str:
    lines = ["routes:"]
    for i, s in enumerate(slugs):
        lines.append(f"  - hostname: {s}.noctusai.com")
        lines.append(f"    service: http://{s}:{8000 + i}")
    return "\n".join(lines) + "\n"


def _build_push_sh(slugs: list[str]) -> str:
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"ALL_SLUGS=({' '.join(slugs)})\n"
    )


def _write_surfaces(root: Path, slugs: list[str]) -> None:
    (root / "deploy" / "fleet").mkdir(parents=True, exist_ok=True)
    (root / "deploy" / "tunnel").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "infra").mkdir(parents=True, exist_ok=True)
    (root / "deploy" / "fleet" / "docker-compose.prod.yml").write_text(_compose_yaml(slugs))
    (root / "deploy" / "tunnel" / "ingress.yml").write_text(_ingress_yaml(slugs))
    (root / "scripts" / "infra" / "build-and-push.sh").write_text(_build_push_sh(slugs))


def _commit_surfaces(root: Path, slugs: list[str], message: str) -> None:
    _write_surfaces(root, slugs)
    _git(
        root, "add",
        "deploy/fleet/docker-compose.prod.yml",
        "deploy/tunnel/ingress.yml",
        "scripts/infra/build-and-push.sh",
    )
    _git(root, "commit", "-m", message)


def _write_roadmap_with_milestone(root: Path, slug: str, milestone: str) -> str:
    """Write a roadmap file with `milestone` marked ✅; return the
    consent_ref string pointing at it."""
    rel = f"project-history/roadmaps/{slug}-2026-06.md"
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"# Roadmap — {slug}\n\n"
        "## Milestones\n\n"
        f"- **{milestone}** — dev-validated build, explicit consent. ✅ 2026-07-20\n"
    )
    return f"{rel}#{milestone}"


def _write_consent_record(
    root: Path,
    slug: str,
    *,
    consent_ref: str,
    consented_by: str = AUTHOR_EMAIL,
    dev_validated: bool = True,
    commit: bool = True,
) -> Path:
    consent_dir = root / "deploy" / "consent"
    consent_dir.mkdir(parents=True, exist_ok=True)
    p = consent_dir / f"{slug}.prod.yml"
    p.write_text(
        f"consented_by: {consented_by}\n"
        "consented_on: '2026-07-20'\n"
        f"consent_ref: \"{consent_ref}\"\n"
        f"dev_validated: {'true' if dev_validated else 'false'}\n"
    )
    if commit:
        _git(root, "add", f"deploy/consent/{slug}.prod.yml")
        _git(root, "commit", "-m", f"consent: authorize {slug} for prod exposure")
    return p


# ── The 3 required proofs (one class per `check_detector_has_regression_test`
#    naming convention: `Test<CamelCase(detector)>`) ───────────────────────────


class TestCheckProdExposureConsent:
    """The 3 required proofs — fire / pass / silent — plus the de-
    registration-always-allowed + editing-inside-a-service-block cases.
    """

    def test_fires_high_on_orbity(self, tmp_path):
        root = _init_repo(tmp_path)
        # HEAD: orbity NOT registered anywhere (pre-679d0838 baseline).
        _commit_surfaces(root, ["core"], "baseline: core only")
        # Working tree (about to be committed): orbity added to all 3 surfaces
        # — exactly commit 679d0838's shape. NOT yet committed.
        _write_surfaces(root, ["core", "orbity"])

        issues = check_prod_exposure_consent(repo_root=root)

        assert len(issues) == 1
        assert issues[0]["product"] == "orbity"
        assert issues[0]["severity"] == "high"
        assert issues[0]["symbol"] == "prod-exposure-consent-missing"
        msg = issues[0]["issue"]
        # Self-explanatory message contract.
        assert "orbity" in msg
        assert "docker-compose.prod.yml" in msg
        assert "ingress.yml" in msg
        assert "ALL_SLUGS" in msg
        assert "production-promotion decision" in msg
        assert "NO LATER GATE" in msg
        assert "An agent MUST NOT create the consent record on the user's behalf." in msg
        assert "KB § PATTERNS/devops/prod-exposure-consent.md" in msg


class TestPassWithValidConsent:
    """Same registration, but a valid consent record already exists at HEAD."""

    def test_passes_when_consent_record_valid(self, tmp_path):
        root = _init_repo(tmp_path)
        _commit_surfaces(root, ["core"], "baseline: core only")
        consent_ref = _write_roadmap_with_milestone(
            root, "orbity", "M4: prod promote",
        )
        _write_consent_record(root, "orbity", consent_ref=consent_ref)
        # NOW register orbity on the surfaces — in the WORKING TREE (not yet
        # committed), same as the fire scenario, but the consent record is
        # already safely in HEAD from a PRIOR, isolated commit.
        _write_surfaces(root, ["core", "orbity"])

        issues = check_prod_exposure_consent(repo_root=root)

        assert issues == []

    def test_still_fires_when_dev_validated_false(self, tmp_path):
        root = _init_repo(tmp_path)
        _commit_surfaces(root, ["core"], "baseline: core only")
        consent_ref = _write_roadmap_with_milestone(root, "orbity", "M4: prod promote")
        _write_consent_record(
            root, "orbity", consent_ref=consent_ref, dev_validated=False,
        )
        _write_surfaces(root, ["core", "orbity"])

        issues = check_prod_exposure_consent(repo_root=root)

        assert len(issues) == 1
        assert "dev_validated" in issues[0]["issue"]

    def test_still_fires_when_consented_by_mismatches_author(self, tmp_path):
        root = _init_repo(tmp_path)
        _commit_surfaces(root, ["core"], "baseline: core only")
        consent_ref = _write_roadmap_with_milestone(root, "orbity", "M4: prod promote")
        _write_consent_record(
            root, "orbity", consent_ref=consent_ref, consented_by="someone-else@example.com",
        )
        _write_surfaces(root, ["core", "orbity"])

        issues = check_prod_exposure_consent(repo_root=root)

        assert len(issues) == 1
        assert "consented_by" in issues[0]["issue"]

    def test_still_fires_when_roadmap_milestone_not_checked(self, tmp_path):
        root = _init_repo(tmp_path)
        _commit_surfaces(root, ["core"], "baseline: core only")
        # Roadmap exists but the milestone line has NO ✅.
        rel = "project-history/roadmaps/orbity-2026-06.md"
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# Roadmap\n\n- **M4: prod promote** — not yet.\n")
        _write_consent_record(root, "orbity", consent_ref=f"{rel}#M4: prod promote")
        _write_surfaces(root, ["core", "orbity"])

        issues = check_prod_exposure_consent(repo_root=root)

        assert len(issues) == 1
        assert "consent_ref" in issues[0]["issue"] or "roadmap" in issues[0]["issue"].lower()


class TestSilentAcrossRoutineProductCommit:
    """THE case that matters most — no false-positive noise on ordinary
    product development once a product is already registered."""

    def test_silent_when_orbity_already_registered_and_unrelated_file_changes(self, tmp_path):
        root = _init_repo(tmp_path)
        consent_ref = _write_roadmap_with_milestone(root, "orbity", "M4: prod promote")
        _write_consent_record(root, "orbity", consent_ref=consent_ref)
        # orbity is registered on all 3 surfaces AND committed at HEAD —
        # declared == baseline for orbity going forward.
        _commit_surfaces(root, ["core", "orbity"], "onboard orbity to prod fleet")

        # A routine products/orbity/** commit — NOT touching the 3 surfaces.
        (root / "products").mkdir(parents=True, exist_ok=True)
        (root / "products" / "orbity").mkdir(parents=True, exist_ok=True)
        backend_file = root / "products" / "orbity" / "backend_main.py"
        backend_file.write_text("# routine feature work\n")
        _git(root, "add", "products/orbity/backend_main.py")
        # Deliberately do NOT touch the 3 surfaces in the working tree —
        # they stay byte-identical to HEAD.

        issues = check_prod_exposure_consent(repo_root=root)

        assert issues == []

    def test_silent_when_editing_inside_an_existing_service_block(self, tmp_path):
        root = _init_repo(tmp_path)
        consent_ref = _write_roadmap_with_milestone(root, "orbity", "M4: prod promote")
        _write_consent_record(root, "orbity", consent_ref=consent_ref)
        _commit_surfaces(root, ["core", "orbity"], "onboard orbity to prod fleet")

        # Edit INSIDE an existing service block (e.g. bump a healthcheck
        # interval) — the slug SET is unchanged.
        compose_path = root / "deploy" / "fleet" / "docker-compose.prod.yml"
        text = compose_path.read_text()
        compose_path.write_text(text.replace("latest", "v2"))

        issues = check_prod_exposure_consent(repo_root=root)

        assert issues == []

    def test_deregistration_always_allowed(self, tmp_path):
        root = _init_repo(tmp_path)
        consent_ref = _write_roadmap_with_milestone(root, "orbity", "M4: prod promote")
        _write_consent_record(root, "orbity", consent_ref=consent_ref)
        _commit_surfaces(root, ["core", "orbity"], "onboard orbity to prod fleet")

        # Remove orbity from all 3 surfaces (de-registration).
        _write_surfaces(root, ["core"])

        issues = check_prod_exposure_consent(repo_root=root)

        assert issues == []


# ── Supporting invariants ────────────────────────────────────────────────────


class TestNonNocTreeSilentSkip:
    def test_silent_when_no_deploy_dir(self, tmp_path):
        root = _init_repo(tmp_path)
        # No deploy/ directory at all.
        issues = check_prod_exposure_consent(repo_root=root)
        assert issues == []


class TestConsentCommitMustBeIsolated:
    def test_fires_when_consent_staged_with_other_paths(self, tmp_path):
        root = _init_repo(tmp_path)
        _commit_surfaces(root, ["core"], "baseline: core only")
        consent_ref = _write_roadmap_with_milestone(root, "orbity", "M4: prod promote")
        _write_consent_record(root, "orbity", consent_ref=consent_ref, commit=False)
        # Stage the consent file ALONGSIDE an unrelated feature file — the
        # forbidden shape.
        other = root / "README.md"
        other.write_text("feature work\n")
        _git(root, "add", "deploy/consent/orbity.prod.yml", "README.md")

        issues = check_prod_exposure_consent(repo_root=root)

        isolation_issues = [
            i for i in issues if i.get("symbol") == "prod-exposure-consent-not-isolated"
        ]
        assert len(isolation_issues) == 1
        assert "isolated" in isolation_issues[0]["issue"]

    def test_silent_when_consent_staged_alone(self, tmp_path):
        root = _init_repo(tmp_path)
        _commit_surfaces(root, ["core"], "baseline: core only")
        consent_ref = _write_roadmap_with_milestone(root, "orbity", "M4: prod promote")
        _write_consent_record(root, "orbity", consent_ref=consent_ref, commit=False)
        _git(root, "add", "deploy/consent/orbity.prod.yml")

        issues = check_prod_exposure_consent(repo_root=root)

        isolation_issues = [
            i for i in issues if i.get("symbol") == "prod-exposure-consent-not-isolated"
        ]
        assert isolation_issues == []


class TestResolveRoadmapMilestone:
    def test_resolves_when_anchor_and_checkmark_present(self, tmp_path):
        root = _init_repo(tmp_path)
        consent_ref = _write_roadmap_with_milestone(root, "orbity", "M4: prod promote")
        ok, reason = _resolve_roadmap_milestone(consent_ref, root)
        assert ok is True
        assert reason == ""

    def test_fails_when_no_hash(self, tmp_path):
        root = _init_repo(tmp_path)
        ok, reason = _resolve_roadmap_milestone("project-history/roadmaps/x.md", root)
        assert ok is False
        assert "anchor" in reason

    def test_fails_when_path_escapes_root(self, tmp_path):
        root = _init_repo(tmp_path)
        ok, reason = _resolve_roadmap_milestone("../../etc/passwd#anchor", root)
        assert ok is False

    def test_fails_when_file_missing(self, tmp_path):
        root = _init_repo(tmp_path)
        ok, reason = _resolve_roadmap_milestone(
            "project-history/roadmaps/does-not-exist.md#M1", root,
        )
        assert ok is False
        assert "not found" in reason
