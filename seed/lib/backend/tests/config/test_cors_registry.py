"""Unit tests for `noctusai_lib.config.cors_registry`.

Exercises:

- :func:`parse_products_registry` against fixture ``start.sh`` snippets.
- :func:`derive_cors_origins` in every documented mode.
- :class:`BaseAppSettings.cors_origins_list` sentinel resolution.

The fixture ``start.sh`` snippets are written to a temp dir per test so
the suite never depends on the live repo's ``start.sh`` (which would
make the test brittle to fleet changes).
"""

from __future__ import annotations

import textwrap
import os
from pathlib import Path

import pytest

from noctusai_lib.config.cors_registry import (
    LOCALHOST_ALT_PORTS,
    derive_cors_origins,
    parse_products_registry,
)
from noctusai_lib.config.settings import BaseAppSettings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_start_sh(tmp_path: Path, body: str) -> Path:
    """Write `body` to a temp ``start.sh`` and return the path."""
    p = tmp_path / "start.sh"
    p.write_text(textwrap.dedent(body))
    return p


CANONICAL_REGISTRY = """
#!/bin/bash
# preamble
# BEGIN_PRODUCTS_REGISTRY
PRODUCTS=(
    "core:Core:8000:5173"
    "erp-imobiliario:ERP Imobiliario:8001:8080"
    "personal-finance:Personal Finance:8002:8090"
)
# END_PRODUCTS_REGISTRY
# trailing
"""


# ---------------------------------------------------------------------------
# parse_products_registry
# ---------------------------------------------------------------------------


def test_parse_canonical_three_products(tmp_path: Path) -> None:
    start_sh = _write_start_sh(tmp_path, CANONICAL_REGISTRY)
    entries = parse_products_registry(start_sh)

    assert len(entries) == 3
    assert entries[0] == {
        "slug": "core",
        "display": "Core",
        "backend_port": 8000,
        "frontend_port": 5173,
    }
    assert entries[1]["slug"] == "erp-imobiliario"
    assert entries[1]["display"] == "ERP Imobiliario"
    assert entries[2]["frontend_port"] == 8090


def test_parse_missing_file_returns_empty(tmp_path: Path) -> None:
    """Missing start.sh must not crash — return [] so callers can fall back."""
    missing = tmp_path / "nope.sh"
    assert parse_products_registry(missing) == []


def test_parse_missing_sentinels_returns_empty(tmp_path: Path) -> None:
    """No BEGIN/END sentinels → empty list (defensive, not a crash)."""
    start_sh = _write_start_sh(
        tmp_path,
        """
        #!/bin/bash
        PRODUCTS=(
            "core:Core:8000:5173"
        )
        """,
    )
    assert parse_products_registry(start_sh) == []


def test_parse_skips_malformed_rows(tmp_path: Path) -> None:
    """Malformed rows are silently skipped; well-shaped rows still parse."""
    start_sh = _write_start_sh(
        tmp_path,
        """
        # BEGIN_PRODUCTS_REGISTRY
        PRODUCTS=(
            "core:Core:8000:5173"
            "broken-no-ports"
            "also:broken:notanumber:5173"
            "good:Good:8001:8080"
        )
        # END_PRODUCTS_REGISTRY
        """,
    )
    entries = parse_products_registry(start_sh)
    slugs = [e["slug"] for e in entries]
    assert slugs == ["core", "good"]


def test_parse_default_path_resolves_when_repo_layout_present() -> None:
    """Default lookup (no arg) finds the live `start.sh` in this repo.

    This is the smoke test that the four-parents-up heuristic still works
    after any directory-shape reshuffling. If this test fails, the
    `_default_start_sh()` arithmetic needs updating.
    """
    entries = parse_products_registry()
    # In this repo the fleet has ≥ 8 products (9 as of 2026-05-16, after
    # `social-wiring-absorption` Wave 4 retired media-scheduling /
    # youtube-crawler / mailing / imobi-scheduling into social-wiring).
    # Threshold keeps headroom for further fleet shrinkage without making
    # the smoke-test brittle; it asserts the four-parents-up heuristic
    # still finds a populated start.sh, not an exact fleet size.
    assert len(entries) >= 8
    slugs = {e["slug"] for e in entries}
    assert "core" in slugs


# ---------------------------------------------------------------------------
# derive_cors_origins
# ---------------------------------------------------------------------------


def test_derive_all_frontends_includes_localhost_alts_and_registry(
    tmp_path: Path,
) -> None:
    start_sh = _write_start_sh(tmp_path, CANONICAL_REGISTRY)
    out = derive_cors_origins(start_sh=start_sh, include_all_frontends=True)

    # Localhost alts first, then registry HOUSE origins (backend ports — what
    # the single-container house model serves / the browser sends as Origin).
    assert "http://localhost:5173" in out  # localhost alt
    assert "http://localhost:3000" in out  # localhost alt
    assert "http://localhost:8000" in out  # core's house port
    assert "http://localhost:8001" in out  # erp-imobiliario house port
    assert "http://localhost:8002" in out  # personal-finance house port
    # No duplicates.
    assert len(out) == len(set(out))


def test_derive_own_slug_only_includes_own_frontend(tmp_path: Path) -> None:
    start_sh = _write_start_sh(tmp_path, CANONICAL_REGISTRY)
    out = derive_cors_origins(
        start_sh=start_sh,
        include_all_frontends=False,
        own_slug="erp-imobiliario",
    )

    assert "http://localhost:5173" in out  # localhost alt
    assert "http://localhost:3000" in out  # localhost alt
    assert "http://localhost:8001" in out  # erp's house port
    # Other products' house origins are excluded.
    assert "http://localhost:8002" not in out  # personal-finance house port


def test_derive_unknown_own_slug_falls_back_to_alts_only(tmp_path: Path) -> None:
    start_sh = _write_start_sh(tmp_path, CANONICAL_REGISTRY)
    out = derive_cors_origins(
        start_sh=start_sh,
        include_all_frontends=False,
        own_slug="nonexistent-product",
    )
    assert out == [f"http://localhost:{p}" for p in LOCALHOST_ALT_PORTS]


def test_derive_without_localhost_alts_yields_only_registry(tmp_path: Path) -> None:
    start_sh = _write_start_sh(tmp_path, CANONICAL_REGISTRY)
    out = derive_cors_origins(
        start_sh=start_sh,
        include_localhost_alts=False,
        include_all_frontends=True,
    )
    # Three registry entries' HOUSE ports: core (8000), erp (8001), pf (8002).
    assert sorted(out) == [
        "http://localhost:8000",
        "http://localhost:8001",
        "http://localhost:8002",
    ]


def test_derive_missing_start_sh_returns_just_alts(tmp_path: Path) -> None:
    """Missing start.sh + include_localhost_alts=True → localhost alts only."""
    missing = tmp_path / "nope.sh"
    out = derive_cors_origins(start_sh=missing, include_all_frontends=True)
    assert out == [f"http://localhost:{p}" for p in LOCALHOST_ALT_PORTS]


def test_derive_missing_start_sh_and_no_alts_returns_empty(tmp_path: Path) -> None:
    """Missing start.sh + alts disabled → genuinely empty."""
    missing = tmp_path / "nope.sh"
    out = derive_cors_origins(
        start_sh=missing,
        include_localhost_alts=False,
        include_all_frontends=True,
    )
    assert out == []


def test_derive_dedupes_overlapping_ports(tmp_path: Path) -> None:
    """When a registered HOUSE port collides with a localhost alt, no duplicate.

    A product whose backend (house) port is 3000 overlaps the alt `3000` —
    the dedup seen-set must collapse them to a single entry. (Post house-port
    fix the canonical fleet's house ports no longer collide with an alt, so the
    dedup path is exercised with a purpose-built registry here.)
    """
    start_sh = _write_start_sh(
        tmp_path,
        """
        # BEGIN_PRODUCTS_REGISTRY
        PRODUCTS=(
            "dup:Dup:3000:9999"
        )
        # END_PRODUCTS_REGISTRY
        """,
    )
    out = derive_cors_origins(start_sh=start_sh, include_all_frontends=True)
    assert out.count("http://localhost:3000") == 1


# ---------------------------------------------------------------------------
# derive_cors_origins — deploy-aware prod origins (PRODUCT_URL_* scheme)
# ---------------------------------------------------------------------------


def test_derive_no_prod_env_is_localhost_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Back-compat: with no PRODUCT_URL_* set, output stays localhost-only."""
    for var in (
        "PRODUCT_URL_PATTERN",
        "PRODUCT_URL_CORE",
        "PRODUCT_URL_ERP_IMOBILIARIO",
        "PRODUCT_URL_PERSONAL_FINANCE",
    ):
        monkeypatch.delenv(var, raising=False)
    start_sh = _write_start_sh(tmp_path, CANONICAL_REGISTRY)
    out = derive_cors_origins(start_sh=start_sh, include_all_frontends=True)
    assert not any(o.startswith("https://") for o in out)


def test_derive_pattern_adds_prod_origin_per_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRODUCT_URL_PATTERN → every registry product gets its {slug} prod origin."""
    monkeypatch.setenv("PRODUCT_URL_PATTERN", "https://{slug}.noctusai.com")
    start_sh = _write_start_sh(tmp_path, CANONICAL_REGISTRY)
    out = derive_cors_origins(start_sh=start_sh, include_all_frontends=True)
    assert "https://core.noctusai.com" in out
    assert "https://erp-imobiliario.noctusai.com" in out
    assert "https://personal-finance.noctusai.com" in out
    # Deploy-aware ADDS, doesn't replace — localhost set still present.
    assert "http://localhost:5173" in out
    assert len(out) == len(set(out))  # dedup preserved


def test_derive_per_product_override_beats_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PRODUCT_URL_<SLUG> is the CANONICAL url — but the allowlist keeps both.

    Amended 2026-08-19. This test used to assert the pattern origin was
    *suppressed* when an override existed, mirroring `resolve_product_url`,
    whose job is to name the ONE url to link to. For an allowlist that is the
    wrong contract: `deploy/tunnel/ingress.yml` routes BOTH `erp.` and
    `erp-imobiliario.` to the same container, so both are origins a browser can
    genuinely send, and allowing only one left the other answering 400 with no
    allow-origin — measured against live core the same day.
    """
    monkeypatch.setenv("PRODUCT_URL_PATTERN", "https://{slug}.noctusai.com")
    monkeypatch.setenv("PRODUCT_URL_ERP_IMOBILIARIO", "https://erp.noctusai.com")
    start_sh = _write_start_sh(tmp_path, CANONICAL_REGISTRY)
    out = derive_cors_origins(start_sh=start_sh, include_all_frontends=True)
    assert "https://erp.noctusai.com" in out           # the override
    assert "https://erp-imobiliario.noctusai.com" in out  # AND the pattern
    assert "https://core.noctusai.com" in out          # others take the pattern
    assert out.count("https://erp.noctusai.com") == 1  # still deduped


def test_derive_own_slug_adds_only_its_prod_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """own_slug mode emits only that product's prod origin, not the fleet's."""
    monkeypatch.setenv("PRODUCT_URL_PATTERN", "https://{slug}.noctusai.com")
    start_sh = _write_start_sh(tmp_path, CANONICAL_REGISTRY)
    out = derive_cors_origins(
        start_sh=start_sh, include_all_frontends=False, own_slug="erp-imobiliario"
    )
    assert "https://erp-imobiliario.noctusai.com" in out
    assert "https://core.noctusai.com" not in out
    assert "https://personal-finance.noctusai.com" not in out


def test_derive_include_prod_origins_false_forces_localhost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """include_prod_origins=False suppresses prod origins even when env is set."""
    monkeypatch.setenv("PRODUCT_URL_PATTERN", "https://{slug}.noctusai.com")
    start_sh = _write_start_sh(tmp_path, CANONICAL_REGISTRY)
    out = derive_cors_origins(
        start_sh=start_sh, include_all_frontends=True, include_prod_origins=False
    )
    assert not any(o.startswith("https://") for o in out)


def test_derive_prod_origins_from_env_without_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Container case: NO start.sh (registry empty) but PRODUCT_URL_<SLUG> env
    set → @registry:all STILL emits those prod origins.

    Regression-pin for the 2026-05-22 cutover failure: the slim prod image
    ships no start.sh, so registry-only derivation collapsed to localhost-only
    and the apex login was CORS-blocked. The PRODUCT_URL_<SLUG> env vars must be
    a sufficient source on their own.
    """
    monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
    monkeypatch.setenv("PRODUCT_URL_CORE", "https://noctusai.com")
    monkeypatch.setenv("PRODUCT_URL_ERP_IMOBILIARIO", "https://erp.noctusai.com")
    missing = tmp_path / "no-start.sh"  # registry unreachable, like the prod image
    out = derive_cors_origins(start_sh=missing, include_all_frontends=True)
    assert "https://noctusai.com" in out  # apex login origin
    assert "https://erp.noctusai.com" in out  # a deployed product
    assert out == list(dict.fromkeys(out))  # still deduped


def test_derive_own_slug_prod_origin_without_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """own_slug shape resolves its prod origin from env alone (no registry)."""
    monkeypatch.delenv("PRODUCT_URL_PATTERN", raising=False)
    monkeypatch.setenv("PRODUCT_URL_ERP_IMOBILIARIO", "https://erp.noctusai.com")
    missing = tmp_path / "no-start.sh"
    out = derive_cors_origins(
        start_sh=missing, include_all_frontends=False, own_slug="erp-imobiliario"
    )
    assert "https://erp.noctusai.com" in out


# ---------------------------------------------------------------------------
# BaseAppSettings sentinel resolution
# ---------------------------------------------------------------------------


def test_settings_plain_string_unchanged() -> None:
    """Plain enumerated string keeps the existing split-on-comma behavior."""
    s = BaseAppSettings(cors_origins="http://foo,http://bar, http://baz ")
    assert s.cors_origins_list == ["http://foo", "http://bar", "http://baz"]


def test_settings_wildcard_unchanged() -> None:
    s = BaseAppSettings(cors_origins="*")
    assert s.cors_origins_list == ["*"]


def test_settings_registry_all_sentinel_returns_union() -> None:
    """`@registry:all` reads the live `start.sh` and returns every frontend."""
    s = BaseAppSettings(cors_origins="@registry:all")
    origins = s.cors_origins_list
    assert "http://localhost:5173" in origins
    assert "http://localhost:3000" in origins
    # At least 10 products in this fleet → ≥ 10 origins beyond alts.
    assert len(origins) >= 10


def test_settings_registry_own_slug_returns_own_plus_alts() -> None:
    """`@registry:own:core` returns just core's HOUSE origin + localhost alts.

    Derived from the live registry (not hardcoded ports) so a fleet port
    change can't re-stale it — mirrors `..._core_migration...` below.
    """
    s = BaseAppSettings(cors_origins="@registry:own:core")
    origins = set(s.cors_origins_list)
    assert "http://localhost:5173" in origins  # localhost alt
    assert "http://localhost:3000" in origins  # localhost alt
    by_slug = {e["slug"]: e for e in parse_products_registry()}
    # core's own HOUSE port (backend — what the container serves) is included...
    assert f"http://localhost:{by_slug['core']['backend_port']}" in origins
    # ...but no OTHER product's house port is.
    for slug, e in by_slug.items():
        if slug != "core":
            assert f"http://localhost:{e['backend_port']}" not in origins, slug


def test_settings_registry_unknown_sentinel_returns_alts() -> None:
    """Unknown `@registry:*` form falls back to localhost alts (no crash)."""
    s = BaseAppSettings(cors_origins="@registry:bogus-mode")
    assert s.cors_origins_list == [f"http://localhost:{p}" for p in LOCALHOST_ALT_PORTS]


def test_settings_registry_own_missing_slug_falls_back_to_alts() -> None:
    """`@registry:own:` with no slug → no crash, alts only."""
    s = BaseAppSettings(cors_origins="@registry:own:")
    assert s.cors_origins_list == [f"http://localhost:{p}" for p in LOCALHOST_ALT_PORTS]


def test_settings_core_migration_resolves_to_the_live_product_origin_set() -> None:
    """`@registry:all` must allow every live-product frontend origin.

    Regression-pin: before this seam, `products/core/backend/app/config.py`
    hardcoded a 13-origin string covering 5173, 3000, and 11 frontend ports.
    Migrating to `@registry:all` must produce the same set (order doesn't
    matter — CORSMiddleware compares membership, not order).

    The expected set is NOT a frozen 13-port literal: it is *derived from
    the live `start.sh PRODUCTS` registry* (the same source `@registry:all`
    reads). Hardcoding the literal is exactly what made this test go stale —
    `http://localhost:8140` belonged to `media-scheduling`, which commit
    `b91043f` (ms-merge) consolidated into `imobi-scheduling` and removed
    from the registry. The old literal kept asserting a port no live product
    serves, so the test failed for a *correct* product-set change. Driving
    the expected set off the registry (mirroring the production resolution
    path) means future fleet add/remove can't re-stale this assertion — the
    invariant is "every registered frontend + the localhost alts is
    allowed", not "exactly these N ports forever".
    """
    s = BaseAppSettings(cors_origins="@registry:all")
    resolved = set(s.cors_origins_list)

    expected = {f"http://localhost:{p}" for p in LOCALHOST_ALT_PORTS}
    for entry in parse_products_registry():
        # HOUSE port (backend) — what the single-container model serves and
        # what `derive_cors_origins` now emits (was frontend_port pre-fix).
        expected.add(f"http://localhost:{entry['backend_port']}")

    # Every live registry origin (+ localhost alts) must be allowed.
    missing = expected - resolved
    assert not missing, f"Sentinel dropped live-registry origins: {sorted(missing)}"
    # And the sentinel must not invent origins beyond the registry + alts.
    extra = resolved - expected
    assert not extra, f"Sentinel produced non-registry origins: {sorted(extra)}"


def test_settings_registry_all_includes_prod_origins_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: `@registry:all` + PRODUCT_URL_* → prod origins allowed.

    This is the seam that fixes prod login/SSO: with the deploy's
    PRODUCT_URL_* scheme set, core's SSO-bridge allowlist auto-includes every
    product's https origin (+ the apex), so no hand-maintained CORS_ORIGINS is
    needed. Dev (no env) keeps the localhost-only shape — see the strict
    `..._resolves_to_the_live_product_origin_set` regression-pin above.
    """
    monkeypatch.setenv("PRODUCT_URL_PATTERN", "https://{slug}.noctusai.com")
    monkeypatch.setenv("PRODUCT_URL_CORE", "https://noctusai.com")
    s = BaseAppSettings(cors_origins="@registry:all")
    origins = s.cors_origins_list
    assert "https://noctusai.com" in origins  # apex (PRODUCT_URL_CORE override)
    assert "https://erp-imobiliario.noctusai.com" in origins  # {slug} pattern
    assert "http://localhost:5173" in origins  # localhost set still present


# ── both live hostnames, not just the canonical one ──────────────────────
#
# Measured against live core on 2026-08-19, minutes after shipping the registry
# into the image. `p-studio.` and `igig.` — pattern-only products — came back
# 200 with an allow-origin. `social-wiring.` and `erp-imobiliario.` still came
# back 400 with none, because each has an explicit `PRODUCT_URL_<SLUG>` naming
# its SHORT hostname, and `resolve_product_url` short-circuits on the override.
#
# `deploy/tunnel/ingress.yml` routes BOTH names to the same container, so both
# are real origins a browser can send. An allowlist is a set of what we serve,
# not a preference order — the override is the canonical link, not the only door.

def _prod_env(monkeypatch):
    monkeypatch.setenv("PRODUCT_URL_PATTERN", "https://{slug}.noctusai.com")
    monkeypatch.setenv("PRODUCT_URL_SOCIAL_WIRING", "https://social.noctusai.com")
    monkeypatch.setenv("PRODUCT_URL_ERP_IMOBILIARIO", "https://erp.noctusai.com")
    monkeypatch.setenv("PRODUCT_URL_CORE", "https://noctusai.com")


def test_an_override_does_not_hide_the_pattern_derived_origin(monkeypatch):
    """🔴 THE gap. Both hostnames serve social-wiring; both must be allowed."""
    _prod_env(monkeypatch)
    origins = derive_cors_origins()
    assert "https://social.noctusai.com" in origins          # the override
    assert "https://social-wiring.noctusai.com" in origins   # the pattern
    assert "https://erp.noctusai.com" in origins
    assert "https://erp-imobiliario.noctusai.com" in origins


def test_a_pattern_only_product_still_resolves_exactly_once(monkeypatch):
    _prod_env(monkeypatch)
    origins = derive_cors_origins()
    assert origins.count("https://p-studio.noctusai.com") == 1
    assert origins.count("https://igig.noctusai.com") == 1


def test_no_pattern_configured_is_a_no_op_not_a_crash(monkeypatch):
    """Plain dev: no PRODUCT_URL_* at all ⇒ the historical localhost-only list."""
    for key in list(os.environ):
        if key.startswith("PRODUCT_URL_"):
            monkeypatch.delenv(key, raising=False)
    origins = derive_cors_origins()
    assert origins
    assert not [o for o in origins if o.startswith("https://")]
