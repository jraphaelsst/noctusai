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
    _human_authored_transcript_texts,
    _resolve_roadmap_milestone,
    _validate_prod_consent_record,
    _verify_authorization_phrase,
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
        # The agent boundary is still stated, in the post-2026-08-09 wording:
        # an agent may transcribe a decision, never manufacture one. The
        # message must also teach the verified path, not just forbid.
        assert "An agent may RECORD the user's decision; it must never invent one." in msg
        assert "I authorize orbity to be published to production." in msg
        assert "action=challenge" in msg
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


# ── Agent-recorded consent (redesigned 2026-08-09) ───────────────────────────
#
# The gate used to require the USER to hand-type the YAML. For a user who
# works entirely through agents that is pure friction, and worse, it was
# UNVERIFIABLE: nothing stopped an agent from writing the file and asserting
# the user approved — which is exactly what was attempted twice on
# 2026-08-09. The redesign keeps the decision the user's but makes the proof
# mechanical: a canonical sentence, matched against the harness-written
# session transcript, which the agent does not author.


def _write_transcript(home: Path, session_id: str, records: list[dict]) -> Path:
    import json
    d = home / ".claude" / "projects" / "-some-project"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{session_id}.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return p


def _typed(text: str) -> dict:
    return {"type": "user", "promptSource": "typed",
            "message": {"content": text}}


PHRASE = "I authorize demo to be published to production."


class TestHumanAuthoredTranscriptTexts:
    """Only what the HUMAN wrote counts as evidence."""

    def test_typed_prompt_counts(self, tmp_path):
        _write_transcript(tmp_path, "s1", [_typed("hello there")])
        texts, detail = _human_authored_transcript_texts("s1", home=tmp_path)
        assert detail == ""
        assert texts == ["hello there"]

    def test_mid_turn_queued_message_counts(self, tmp_path):
        """The regression that motivated reading BOTH shapes: a real
        mid-turn authorization appeared ONLY as a queue-operation."""
        _write_transcript(tmp_path, "s2", [
            {"type": "queue-operation", "operation": "enqueue",
             "content": "sent while you were working"},
            {"type": "queue-operation", "operation": "remove",
             "content": "sent while you were working"},
        ])
        texts, _ = _human_authored_transcript_texts("s2", home=tmp_path)
        assert texts == ["sent while you were working"]

    def test_tool_results_and_meta_and_sidechain_excluded(self, tmp_path):
        _write_transcript(tmp_path, "s3", [
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "content": PHRASE}]}},
            {"type": "user", "promptSource": "typed", "isMeta": True,
             "message": {"content": PHRASE}},
            {"type": "user", "promptSource": "typed", "isSidechain": True,
             "message": {"content": PHRASE}},
            {"type": "assistant", "message": {"content": PHRASE}},
        ])
        texts, _ = _human_authored_transcript_texts("s3", home=tmp_path)
        assert texts == [], "agent-side records must never count as authorization"

    def test_absent_transcript_is_a_loud_failure_not_an_empty_pass(self, tmp_path):
        texts, detail = _human_authored_transcript_texts("nope", home=tmp_path)
        assert texts == []
        assert "no transcript found" in detail


class TestVerifyAuthorizationPhrase:
    def test_verified_when_user_typed_it(self, tmp_path):
        _write_transcript(tmp_path, "s", [_typed(f"ok fine. {PHRASE}")])
        ok, reason = _verify_authorization_phrase(
            "demo", {"phrase": PHRASE, "session_id": "s"}, home=tmp_path)
        assert ok, reason

    def test_refused_when_user_never_typed_it(self, tmp_path):
        _write_transcript(tmp_path, "s", [_typed("just ship it already")])
        ok, reason = _verify_authorization_phrase(
            "demo", {"phrase": PHRASE, "session_id": "s"}, home=tmp_path)
        assert not ok
        assert "NOT found" in reason

    def test_refused_when_phrase_is_not_canonical(self, tmp_path):
        """A cherry-picked "yes go ahead" must not authorize a product —
        the sentence has to name the slug."""
        _write_transcript(tmp_path, "s", [_typed("yes go ahead")])
        ok, reason = _verify_authorization_phrase(
            "demo", {"phrase": "yes go ahead", "session_id": "s"}, home=tmp_path)
        assert not ok
        assert "canonical" in reason

    def test_refused_when_phrase_authorizes_a_DIFFERENT_slug(self, tmp_path):
        _write_transcript(tmp_path, "s", [
            _typed("I authorize otherproduct to be published to production.")])
        ok, _ = _verify_authorization_phrase(
            "demo", {"phrase": PHRASE, "session_id": "s"}, home=tmp_path)
        assert not ok

    @pytest.mark.parametrize("auth", [None, "a string", {}, {"phrase": PHRASE}])
    def test_refused_on_malformed_authorization_block(self, auth, tmp_path):
        ok, _ = _verify_authorization_phrase("demo", auth, home=tmp_path)
        assert not ok


class TestValidateRecordRecordedByAgent:
    def test_grandfathered_record_without_recorded_by_still_valid(self, tmp_path):
        """Purely additive: every pre-2026-08-09 record stays valid."""
        root = _init_repo(tmp_path)
        ref = _write_roadmap_with_milestone(root, "demo", "M1: prod promote")
        _git(root, "add", "-A"); _git(root, "commit", "-m", "roadmap")
        _write_consent_record(root, "demo", consent_ref=ref)
        assert _validate_prod_consent_record("demo", root)["status"] == "valid"

    def test_recorded_by_agent_without_authorization_is_invalid(self, tmp_path):
        root = _init_repo(tmp_path)
        ref = _write_roadmap_with_milestone(root, "demo", "M1: prod promote")
        _git(root, "add", "-A"); _git(root, "commit", "-m", "roadmap")
        p = root / "deploy" / "consent" / "demo.prod.yml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"consented_by: {AUTHOR_EMAIL}\nconsented_on: '2026-08-09'\n"
            f"consent_ref: \"{ref}\"\ndev_validated: true\nrecorded_by: agent\n"
        )
        _git(root, "add", "-A"); _git(root, "commit", "-m", "consent")
        result = _validate_prod_consent_record("demo", root, home=tmp_path / "home")
        assert result["status"] == "invalid"
        assert "unverified" in result["detail"]

    def test_recorded_by_agent_with_verified_phrase_is_valid(self, tmp_path):
        root = _init_repo(tmp_path)
        home = tmp_path / "home"
        _write_transcript(home, "sess-1", [_typed(PHRASE)])
        ref = _write_roadmap_with_milestone(root, "demo", "M1: prod promote")
        _git(root, "add", "-A"); _git(root, "commit", "-m", "roadmap")
        p = root / "deploy" / "consent" / "demo.prod.yml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"consented_by: {AUTHOR_EMAIL}\nconsented_on: '2026-08-09'\n"
            f"consent_ref: \"{ref}\"\ndev_validated: true\nrecorded_by: agent\n"
            f"authorization:\n  phrase: \"{PHRASE}\"\n  session_id: sess-1\n"
        )
        _git(root, "add", "-A"); _git(root, "commit", "-m", "consent")
        result = _validate_prod_consent_record("demo", root, home=home)
        assert result["status"] == "valid", result["detail"]

    def test_unknown_recorded_by_is_invalid(self, tmp_path):
        root = _init_repo(tmp_path)
        ref = _write_roadmap_with_milestone(root, "demo", "M1: prod promote")
        _git(root, "add", "-A"); _git(root, "commit", "-m", "roadmap")
        p = root / "deploy" / "consent" / "demo.prod.yml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            f"consented_by: {AUTHOR_EMAIL}\nconsented_on: '2026-08-09'\n"
            f"consent_ref: \"{ref}\"\ndev_validated: true\nrecorded_by: nobody\n"
        )
        _git(root, "add", "-A"); _git(root, "commit", "-m", "consent")
        assert _validate_prod_consent_record("demo", root)["status"] == "invalid"


class TestConsentRefQuotingFalseNegative:
    """The template shipped `consent_ref` UNQUOTED from 2026-07-20. A
    milestone anchor contains ': ', so the value was a YAML ScannerError —
    every record authored faithfully from the documented template failed at
    the PARSE step, presenting as "the gate rejected my consent"."""

    def test_unquoted_consent_ref_containing_colon_space_fails_to_parse(self):
        import yaml
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(
                "consented_by: a@b.com\nconsented_on: '2026-08-09'\n"
                "consent_ref: roadmaps/x.md#M5: prod promote\ndev_validated: true\n"
            )

    def test_quoted_consent_ref_parses(self):
        import yaml
        d = yaml.safe_load(
            "consented_by: a@b.com\nconsented_on: '2026-08-09'\n"
            "consent_ref: 'roadmaps/x.md#M5: prod promote'\ndev_validated: true\n"
        )
        assert d["consent_ref"] == "roadmaps/x.md#M5: prod promote"

    def test_shipped_template_is_quoted(self):
        from tools.noctus.dev.prod_consent import _TEMPLATE
        assert "consent_ref: '" in _TEMPLATE
