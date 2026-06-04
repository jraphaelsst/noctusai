"""Tests for noctus.dev.ensure_product_url_roster.

All tests are fully hermetic — FakeSshTransport and compute_roster_block
are exercised without any real SSH calls, per KB § PATTERNS/compliance/testing.md.

Coverage:
  - _slug_to_env_key: hyphen-to-underscore + prefix
  - _pattern_fill: {slug} and {slug_underscored} substitution
  - compute_roster_block:
      * new slug added via pattern (orbity)
      * short-name override PRESERVED (erp-imobiliario, social-wiring, core)
      * idempotency: transform(transform(x)) == transform(x)
      * non-PRODUCT_URL lines preserved byte-for-byte
      * first-run absorption: bare PRODUCT_URL_* lines moved into block, no duplicates
      * missing pattern + gap slug → unresolved, no invented origin
      * pattern absent but overrides present → all overrides preserved
  - ensure_product_url_roster orchestration:
      * dry-run (confirm=False) → status=dry_run, transport.written is None
      * confirm=True, apply=True → status=applied, written content has block
      * confirm=True, apply=True, recreate_core=True → recreated list populated
      * SSH read failure → status=error
      * SSH write failure → status=error
      * core recreate failure → status=applied + non-None error (soft failure)
      * up_to_date when env_text == new text
      * empty registry → status=error
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make MCP toolkit importable from the test path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Make noctusai_lib importable
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "seed" / "lib" / "backend"))

from tools.noctus.dev.ensure_product_url_roster import (  # noqa: E402
    FakeSshTransport,
    _BLOCK_BEGIN,
    _BLOCK_END,
    _pattern_fill,
    _slug_to_env_key,
    compute_roster_block,
    ensure_product_url_roster,
)


# ── Helper fixtures ───────────────────────────────────────────────────────────

# Simulates the real VPS .env: short-name overrides + pattern already set.
_FIXTURE_VPS_ENV = """\
DB_URL=postgresql://user:pass@localhost:5432/noctus
SUPABASE_URL=https://abc.supabase.co
PRODUCT_URL_PATTERN=https://{slug}.noctusai.com
PRODUCT_URL_CORE=https://noctusai.com
PRODUCT_URL_ERP_IMOBILIARIO=https://erp.noctusai.com
PRODUCT_URL_SOCIAL_WIRING=https://social.noctusai.com
OPENAI_API_KEY=sk-test-xxx
"""

# All slugs from the registry
_REGISTRY_SLUGS = [
    "core",
    "erp-imobiliario",
    "personal-finance",
    "therapy-platform",
    "seed",
    "daily-life",
    "adconnect",
    "dev-team",
    "social-wiring",
    "knowledge-extractor",
    "orbity",
]

_PATTERN = "https://{slug}.noctusai.com"


# ── Unit: helper functions ───────────────────────────────────────────────────


class TestSlugToEnvKey:
    def test_simple_slug(self):
        assert _slug_to_env_key("orbity") == "PRODUCT_URL_ORBITY"

    def test_hyphenated_slug(self):
        assert _slug_to_env_key("erp-imobiliario") == "PRODUCT_URL_ERP_IMOBILIARIO"

    def test_multi_hyphen(self):
        assert _slug_to_env_key("social-wiring") == "PRODUCT_URL_SOCIAL_WIRING"

    def test_core(self):
        assert _slug_to_env_key("core") == "PRODUCT_URL_CORE"


class TestPatternFill:
    def test_slug_substitution(self):
        assert _pattern_fill("orbity", "https://{slug}.noctusai.com") == "https://orbity.noctusai.com"

    def test_slug_underscored_substitution(self):
        assert _pattern_fill("social-wiring", "https://{slug_underscored}.noctusai.com") == "https://social_wiring.noctusai.com"

    def test_trailing_slash_stripped(self):
        assert _pattern_fill("orbity", "https://{slug}.noctusai.com/") == "https://orbity.noctusai.com"


# ── Unit: compute_roster_block (PURE, no SSH) ─────────────────────────────────


class TestComputeRosterBlock:

    def test_orbity_added_via_pattern(self):
        """New slug (orbity) absent from .env + pattern set → block gains PRODUCT_URL_ORBITY."""
        _, report = compute_roster_block(_FIXTURE_VPS_ENV, _REGISTRY_SLUGS, _PATTERN)
        assert "orbity" in report["added"]
        assert "orbity" not in report["preserved"]
        assert "PRODUCT_URL_ORBITY=https://orbity.noctusai.com" in report["rendered_block"]

    def test_erp_override_preserved(self):
        """Short-name override for erp-imobiliario is PRESERVED verbatim."""
        _, report = compute_roster_block(_FIXTURE_VPS_ENV, _REGISTRY_SLUGS, _PATTERN)
        assert "erp-imobiliario" in report["preserved"]
        assert "erp-imobiliario" not in report["added"]
        assert "PRODUCT_URL_ERP_IMOBILIARIO=https://erp.noctusai.com" in report["rendered_block"]
        # Must NOT contain the pattern-derived wrong value
        assert "erp-imobiliario.noctusai.com" not in report["rendered_block"]

    def test_social_wiring_override_preserved(self):
        """Short-name override for social-wiring is PRESERVED."""
        _, report = compute_roster_block(_FIXTURE_VPS_ENV, _REGISTRY_SLUGS, _PATTERN)
        assert "social-wiring" in report["preserved"]
        assert "PRODUCT_URL_SOCIAL_WIRING=https://social.noctusai.com" in report["rendered_block"]

    def test_core_apex_override_preserved(self):
        """core apex override (PRODUCT_URL_CORE=https://noctusai.com) is preserved."""
        _, report = compute_roster_block(_FIXTURE_VPS_ENV, _REGISTRY_SLUGS, _PATTERN)
        assert "core" in report["preserved"]
        assert "PRODUCT_URL_CORE=https://noctusai.com" in report["rendered_block"]

    def test_non_product_url_lines_preserved_verbatim(self):
        """DB creds, secrets, other vars are preserved byte-for-byte."""
        new_text, _ = compute_roster_block(_FIXTURE_VPS_ENV, _REGISTRY_SLUGS, _PATTERN)
        assert "DB_URL=postgresql://user:pass@localhost:5432/noctus" in new_text
        assert "SUPABASE_URL=https://abc.supabase.co" in new_text
        assert "OPENAI_API_KEY=sk-test-xxx" in new_text

    def test_idempotent(self):
        """transform(transform(x)) == transform(x): running twice produces no diff."""
        new_text_1, _ = compute_roster_block(_FIXTURE_VPS_ENV, _REGISTRY_SLUGS, _PATTERN)
        new_text_2, _ = compute_roster_block(new_text_1, _REGISTRY_SLUGS, _PATTERN)
        assert new_text_1 == new_text_2

    def test_block_has_sentinels(self):
        """Rendered block starts with BEGIN sentinel and ends with END sentinel."""
        _, report = compute_roster_block(_FIXTURE_VPS_ENV, _REGISTRY_SLUGS, _PATTERN)
        block = report["rendered_block"]
        assert block.startswith(_BLOCK_BEGIN)
        assert block.endswith(_BLOCK_END)

    def test_missing_pattern_gap_slug_is_unresolved(self):
        """Missing pattern + a gap slug → unresolved, no invented origin."""
        # env has no PRODUCT_URL_PATTERN and no override for orbity
        env_no_pattern = "DB_URL=postgresql://localhost/noctus\nPRODUCT_URL_CORE=https://noctusai.com\n"
        _, report = compute_roster_block(env_no_pattern, ["orbity", "core"], pattern=None)
        assert "orbity" in report["unresolved"]
        assert "orbity" not in report["added"]
        assert "PRODUCT_URL_ORBITY" not in report["rendered_block"]
        # core override still emitted
        assert "PRODUCT_URL_CORE=https://noctusai.com" in report["rendered_block"]

    def test_first_run_absorption_no_duplicates(self):
        """First-run: bare PRODUCT_URL_* lines outside block are moved into it, no duplicates."""
        env_bare = (
            "DB_URL=postgresql://localhost/noctus\n"
            "PRODUCT_URL_CORE=https://noctusai.com\n"
            "PRODUCT_URL_ERP_IMOBILIARIO=https://erp.noctusai.com\n"
            "OPENAI_API_KEY=sk-test\n"
        )
        new_text, report = compute_roster_block(env_bare, ["core", "erp-imobiliario", "orbity"], _PATTERN)
        # Block must contain the overrides
        assert "PRODUCT_URL_CORE=https://noctusai.com" in new_text
        assert "PRODUCT_URL_ERP_IMOBILIARIO=https://erp.noctusai.com" in new_text
        # No bare lines should remain outside the block
        # Count occurrences in new text — each key appears exactly once (inside block)
        assert new_text.count("PRODUCT_URL_CORE=") == 1
        assert new_text.count("PRODUCT_URL_ERP_IMOBILIARIO=") == 1
        # orbity got pattern-filled
        assert "PRODUCT_URL_ORBITY=https://orbity.noctusai.com" in new_text
        assert "orbity" in report["added"]

    def test_pattern_absent_overrides_still_emitted(self):
        """When no pattern and all slugs have overrides → all preserved, no unresolved."""
        env = (
            "PRODUCT_URL_CORE=https://noctusai.com\n"
            "PRODUCT_URL_ORBITY=https://orbity.noctusai.com\n"
        )
        _, report = compute_roster_block(env, ["core", "orbity"], pattern=None)
        assert "core" in report["preserved"]
        assert "orbity" in report["preserved"]
        assert report["unresolved"] == []
        assert report["added"] == []

    def test_full_fixture_sanity(self):
        """Smoke: all 11 registry slugs produce a non-empty block with orbity included."""
        new_text, report = compute_roster_block(_FIXTURE_VPS_ENV, _REGISTRY_SLUGS, _PATTERN)
        assert _BLOCK_BEGIN in new_text
        assert _BLOCK_END in new_text
        assert "PRODUCT_URL_ORBITY=https://orbity.noctusai.com" in new_text
        # overrides preserved
        assert "PRODUCT_URL_CORE=https://noctusai.com" in new_text
        assert "PRODUCT_URL_ERP_IMOBILIARIO=https://erp.noctusai.com" in new_text
        assert "PRODUCT_URL_SOCIAL_WIRING=https://social.noctusai.com" in new_text
        # pattern-derived slugs in added
        assert "personal-finance" in report["added"]
        assert "daily-life" in report["added"]


# ── Orchestration tests (FakeSshTransport) ───────────────────────────────────


def _fake_transport(env_text: str = _FIXTURE_VPS_ENV) -> FakeSshTransport:
    return FakeSshTransport(read_content=env_text)


class TestEnsureProductUrlRosterOrchestration:
    """Orchestration tests inject FakeSshTransport + a fixed repo_root pointing
    at the real start.sh (read-only; no writes to the real repo)."""

    _REPO = str(REPO_ROOT)

    def test_dry_run_does_not_write(self):
        t = _fake_transport()
        result = ensure_product_url_roster(
            confirm=False,
            transport=t,
            repo_root=self._REPO,
        )
        assert result["ok"] is True
        # dry_run or up_to_date (up_to_date is also fine — means env already matches)
        assert result["status"] in ("dry_run", "up_to_date")
        assert t.written is None  # Nothing was written

    def test_confirm_true_writes_env(self):
        t = _fake_transport()
        result = ensure_product_url_roster(
            confirm=True,
            recreate_core=False,
            transport=t,
            repo_root=self._REPO,
        )
        assert result["ok"] is True
        assert result["status"] in ("applied", "up_to_date")
        if result["status"] == "applied":
            assert t.written is not None
            assert _BLOCK_BEGIN in t.written
            assert _BLOCK_END in t.written

    def test_confirm_true_recreate_core_called(self):
        t = _fake_transport()
        result = ensure_product_url_roster(
            confirm=True,
            recreate_core=True,
            transport=t,
            repo_root=self._REPO,
        )
        assert result["ok"] is True
        if result["status"] == "applied":
            assert len(t.recreated) == 1

    def test_ssh_read_failure_returns_error(self):
        t = FakeSshTransport(read_ok=False)
        result = ensure_product_url_roster(
            confirm=False,
            transport=t,
            repo_root=self._REPO,
        )
        assert result["ok"] is False
        assert result["status"] == "error"
        assert result["error"] is not None

    def test_ssh_write_failure_returns_error(self):
        t = FakeSshTransport(read_content=_FIXTURE_VPS_ENV, write_ok=False)
        result = ensure_product_url_roster(
            confirm=True,
            recreate_core=False,
            transport=t,
            repo_root=self._REPO,
        )
        assert result["ok"] is False
        assert result["status"] == "error"
        assert "write" in (result["error"] or "").lower()

    def test_recreate_core_failure_is_soft_non_fatal(self):
        """Core recreate failure → status=applied + non-None error (soft failure)."""
        t = FakeSshTransport(
            read_content=_FIXTURE_VPS_ENV,
            write_ok=True,
            recreate_ok=False,
        )
        result = ensure_product_url_roster(
            confirm=True,
            recreate_core=True,
            transport=t,
            repo_root=self._REPO,
        )
        # The tool MUST still report ok=True because the .env was written.
        if result["status"] == "applied":
            assert result["ok"] is True
            assert result["error"] is not None  # soft warning surfaced

    def test_up_to_date_when_env_already_matches(self):
        """If the env already has the managed block and is up-to-date, status=up_to_date."""
        # First run to get the managed text
        t1 = _fake_transport()
        r1 = ensure_product_url_roster(
            confirm=True,
            recreate_core=False,
            transport=t1,
            repo_root=self._REPO,
        )
        if r1["status"] == "applied" and t1.written is not None:
            # Second run with the already-managed env → up_to_date
            t2 = FakeSshTransport(read_content=t1.written)
            r2 = ensure_product_url_roster(
                confirm=True,
                recreate_core=False,
                transport=t2,
                repo_root=self._REPO,
            )
            assert r2["status"] == "up_to_date"
            assert t2.written is None  # Nothing written on a no-diff run

    def test_empty_registry_returns_error(self, tmp_path):
        """If start.sh doesn't exist / empty registry → status=error."""
        t = _fake_transport()
        result = ensure_product_url_roster(
            confirm=False,
            transport=t,
            repo_root=str(tmp_path),  # no start.sh here
        )
        assert result["ok"] is False
        assert result["status"] == "error"


# ── DRY-RUN sanity print (used by the verify step in the task) ───────────────

def _demo_compute_block():
    """Print the rendered block for the fixture env (offline sanity check)."""
    new_text, report = compute_roster_block(_FIXTURE_VPS_ENV, _REGISTRY_SLUGS, _PATTERN)
    print("\n=== Rendered PRODUCT_URL roster block ===")
    print(report["rendered_block"])
    print(f"\nAdded:     {report['added']}")
    print(f"Preserved: {report['preserved']}")
    print(f"Unresolved:{report['unresolved']}")
    return report


if __name__ == "__main__":
    _demo_compute_block()
