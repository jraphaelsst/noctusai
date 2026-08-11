"""`check_override_is_range` — an exact npm `overrides` entry is a fleet freeze.

WHY (2026-08-11, N=3 in one day). `postcss "8.5.10"`, `ws "8.20.1"` and
`react-router "6.30.4"` were each frozen by an EXACT version in the seed's npm
`overrides`, and all three were added by a *security* cleanup — the CVE fix created
the freeze. An exact override wins over every peer range and direct dep, can never be
moved by `npm install`, and is invisible in the dependency list, yet buys NOTHING:
`package-lock.json` already pins the resolution for `npm ci`. react-router's froze the
fleet on v6 while Dependabot pushed v7, producing a PR that contradicted the repo and
could never go green.

Both directions are pinned here. A detector that has only ever seen a clean tree is
unproven — the fleet is clean right now precisely because it was just fixed.
→ KB § PATTERNS/devops/product-lockfile-and-slug-drift.md § Fourth axis
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import check_override_is_range  # noqa: E402

REPO = Path(__file__).resolve().parents[3]


def _manifest(tmp_path: Path, rel: str, overrides: dict, extra: str = "") -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    body = {"name": "x", "version": "1.0.0", "overrides": overrides}
    text = json.dumps(body, indent=2)
    if extra:
        text = extra + "\n" + text
    p.write_text(text)
    return p


class TestDetectsExactPins:
    def test_exact_version_is_flagged(self, tmp_path):
        _manifest(tmp_path, "seed/lib/frontend/package.json", {"postcss": "8.5.10"})
        issues = check_override_is_range(repo_root=tmp_path)
        assert len(issues) == 1
        assert issues[0]["severity"] == "high"
        assert "postcss" in issues[0]["issue"]

    def test_message_proposes_the_caret_fix(self, tmp_path):
        """The fix must be in the message — a gate that only says 'no' is noise."""
        _manifest(tmp_path, "seed/lib/frontend/package.json", {"ws": "8.20.1"})
        assert '"ws": "^8.20.1"' in check_override_is_range(repo_root=tmp_path)[0]["issue"]

    def test_reports_a_line_number(self, tmp_path):
        _manifest(tmp_path, "seed/lib/frontend/package.json", {"yaml": "2.8.3"})
        issue = check_override_is_range(repo_root=tmp_path)[0]["issue"]
        assert "package.json:" in issue

    def test_products_are_attributed_by_slug(self, tmp_path):
        _manifest(tmp_path, "products/orbity/frontend/package.json", {"undici": "7.24.0"})
        assert check_override_is_range(repo_root=tmp_path)[0]["product"] == "orbity"

    def test_every_exact_entry_is_reported_not_just_the_first(self, tmp_path):
        _manifest(tmp_path, "seed/lib/frontend/package.json",
                  {"postcss": "8.5.10", "ws": "8.20.1", "yaml": "2.8.3"})
        assert len(check_override_is_range(repo_root=tmp_path)) == 3

    def test_scans_the_whole_fleet_not_one_file(self, tmp_path):
        _manifest(tmp_path, "seed/lib/frontend/package.json", {"a": "1.0.0"})
        _manifest(tmp_path, "products/core/frontend/package.json", {"b": "2.0.0"})
        _manifest(tmp_path, "templates/product-seed/frontend/package.json", {"c": "3.0.0"})
        assert len(check_override_is_range(repo_root=tmp_path)) == 3


class TestAcceptsLegitimateSpecifiers:
    @pytest.mark.parametrize("spec", ["^8.5.18", "~2.1.0", ">=4.0.0", "*", "8.x"])
    def test_ranges_are_clean(self, tmp_path, spec):
        _manifest(tmp_path, "seed/lib/frontend/package.json", {"pkg": spec})
        assert check_override_is_range(repo_root=tmp_path) == []

    @pytest.mark.parametrize("spec", [
        "npm:string-width@^4.2.0",   # alias
        "file:../local",             # local path
        "git+https://x/y.git",       # git
        "$typescript",               # reference to a sibling dep
    ])
    def test_non_version_specifiers_are_not_exact_pins(self, tmp_path, spec):
        _manifest(tmp_path, "seed/lib/frontend/package.json", {"pkg": spec})
        assert check_override_is_range(repo_root=tmp_path) == []

    def test_no_overrides_block_is_clean(self, tmp_path):
        p = tmp_path / "seed/lib/frontend/package.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"name": "x", "dependencies": {"react": "18.3.1"}}))
        assert check_override_is_range(repo_root=tmp_path) == []

    def test_exact_version_in_DEPENDENCIES_is_not_this_keeper(self, tmp_path):
        """A product pinning its OWN dependency is the sanctioned escape hatch —
        scoped to one product and visible where reviewers look. Only `overrides`
        (which silently wins fleet-wide) is the freeze this keeper is about."""
        p = tmp_path / "products/orbity/frontend/package.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"name": "x", "dependencies": {"react-router-dom": "7.18.2"}}))
        assert check_override_is_range(repo_root=tmp_path) == []


class TestOptOut:
    def test_pin_ok_rationale_suppresses(self, tmp_path):
        _manifest(tmp_path, "seed/lib/frontend/package.json", {"pkg": "1.2.3"},
                  extra="// pin-ok: next patch is known-broken upstream")
        assert check_override_is_range(repo_root=tmp_path) == []

    def test_deliberate_freeze_keyword_also_works(self, tmp_path):
        _manifest(tmp_path, "seed/lib/frontend/package.json", {"pkg": "1.2.3"},
                  extra="// deliberate-freeze: vendor requires this exact build")
        assert check_override_is_range(repo_root=tmp_path) == []

    def test_unrelated_comment_does_NOT_suppress(self, tmp_path):
        """The opt-out must be a deliberate keyword, not any nearby prose."""
        _manifest(tmp_path, "seed/lib/frontend/package.json", {"pkg": "1.2.3"},
                  extra="// bumped for a CVE")
        assert len(check_override_is_range(repo_root=tmp_path)) == 1


class TestCheckOverrideIsRange:
    """Named for `check_override_is_range` so `check_detector_has_regression_test`
    can discover it — that meta-keeper matches `class Test<DetectorName>`."""

    def test_fleet_has_no_exact_overrides(self):
        """The regression guard: this is what the 2026-08-11 unfreeze achieved."""
        issues = check_override_is_range()
        assert issues == [], (
            "exact override(s) reintroduced:\n  "
            + "\n  ".join(f"{i['file']}: {i['issue'][:110]}" for i in issues)
        )

    def test_the_three_historical_offenders_are_ranges_now(self):
        """postcss / ws / react-router each froze the fleet once."""
        for rel in ("seed/lib/frontend/package.json", "seed/framework/frontend/package.json"):
            ov = json.loads((REPO / rel).read_text()).get("overrides", {})
            for pkg in ("postcss", "ws", "react-router"):
                if pkg in ov:
                    assert ov[pkg].startswith("^"), f"{rel}: {pkg}={ov[pkg]} is not a range"
