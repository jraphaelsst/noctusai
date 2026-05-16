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
    # In this repo the fleet has ≥ 10 products. Threshold gives some
    # headroom for fleet shrinkage without making the assertion brittle.
    assert len(entries) >= 10
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

    # Localhost alts first, then registry frontends. 5173 shows up only
    # once because the core product also pins 5173 — dedup wins.
    assert "http://localhost:5173" in out
    assert "http://localhost:3000" in out
    assert "http://localhost:8080" in out  # erp-imobiliario
    assert "http://localhost:8090" in out  # personal-finance
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
    assert "http://localhost:8080" in out  # erp's frontend
    # Other products' frontends are excluded.
    assert "http://localhost:8090" not in out


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
    # Three registry entries: core (5173), erp (8080), pf (8090).
    assert sorted(out) == [
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:8090",
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
    """When a registered frontend collides with a localhost alt, no duplicate.

    `core:5173` overlaps with the alt `5173` — must appear once.
    """
    start_sh = _write_start_sh(tmp_path, CANONICAL_REGISTRY)
    out = derive_cors_origins(start_sh=start_sh, include_all_frontends=True)
    assert out.count("http://localhost:5173") == 1


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
    """`@registry:own:core` returns just core's frontend + localhost alts."""
    s = BaseAppSettings(cors_origins="@registry:own:core")
    origins = s.cors_origins_list
    assert "http://localhost:5173" in origins  # core's frontend AND localhost alt
    assert "http://localhost:3000" in origins
    # Other products' frontend ports MUST NOT be included.
    # erp-imobiliario frontend = 8080 — explicit exclusion check.
    assert "http://localhost:8080" not in origins


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
        expected.add(f"http://localhost:{entry['frontend_port']}")

    # Every live registry origin (+ localhost alts) must be allowed.
    missing = expected - resolved
    assert not missing, f"Sentinel dropped live-registry origins: {sorted(missing)}"
    # And the sentinel must not invent origins beyond the registry + alts.
    extra = resolved - expected
    assert not extra, f"Sentinel produced non-registry origins: {sorted(extra)}"
