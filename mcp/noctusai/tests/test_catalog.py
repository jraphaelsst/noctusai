"""Tests for the shared-library catalog tool."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.catalog import (
    build_catalog,
    build_reexport_map,
    scan_lib_symbols,
    scan_importers,
    scan_duplicate_candidates,
    LIB_ROOTS,
)


class TestLibRoots:
    def test_lib_roots_exist(self):
        for prefix, root in LIB_ROOTS.items():
            assert root.exists(), f"Lib root for {prefix} not found at {root}"


class TestSymbolScanner:
    def test_scans_source_symbols(self):
        symbols = scan_lib_symbols()
        assert len(symbols) > 0
        # No re-export entries should leak in — those are handled by the reexport map.
        assert not any(s.kind == "reexport" for s in symbols)
        # Every symbol must carry at least module + name + kind + location.
        for s in symbols:
            assert s.name and s.module and s.kind and s.location

    def test_known_public_symbols_present(self):
        """Sanity check: several canonical lib symbols must appear.

        Paths reflect the layered layout adopted 2026-04-30 — see
        `KB § PATTERNS/seed-lib-layout.md`. Old top-level paths like
        `noctusai_lib.api.auth.*` and `noctusai_lib.primitives.responses.*` are still
        importable via transitional shims, but the catalog scanner
        emits the canonical (post-move) module path.
        """
        names = {s.qualified_name for s in scan_lib_symbols()}
        for expected in (
            "noctusai_lib.api.auth.resolve_sso_role",
            "noctusai_lib.api.auth.first_or_none",
            "noctusai_lib.primitives.responses.success_response",
            "noctusai_seed.app.create_product_app",
        ):
            assert expected in names, f"Missing expected symbol: {expected}"

    def test_skips_private_symbols(self):
        names = {s.qualified_name for s in scan_lib_symbols()}
        assert not any(
            n.rsplit(".", 1)[-1].startswith("_") for n in names
        ), "Private (_-prefixed) symbols must not be in the catalog"

    def test_skips_typevars(self):
        """`T = TypeVar("T")` must not be emitted as a const."""
        names = {s.qualified_name for s in scan_lib_symbols()}
        # Single-letter uppercase names like `T` are excluded by length filter.
        assert "noctusai_lib.primitives.responses.T" not in names


class TestReexportMap:
    def test_returns_dict(self):
        rmap = build_reexport_map()
        assert isinstance(rmap, dict)

    def test_testing_reexports_resolved(self):
        """`noctusai_lib.testing.MockSupabaseClient` must forward to the source."""
        rmap = build_reexport_map()
        key = "noctusai_lib.testing.MockSupabaseClient"
        if key in rmap:
            assert rmap[key].endswith(".MockSupabaseClient")
            assert "mocks" in rmap[key] or "clients" in rmap[key]


class TestImportScanner:
    def test_create_product_app_has_many_consumers(self):
        """create_product_app is the framework entry point — every product imports it."""
        rmap = build_reexport_map()
        imports = scan_importers(rmap)
        qn = "noctusai_seed.app.create_product_app"
        assert qn in imports, f"No imports found for {qn}"
        consumers = set(imports[qn].keys())
        # At least 5 of the 7 products should consume it (we don't hard-code
        # the full list because products may be added/removed).
        product_consumers = {c for c in consumers if not c.startswith("lib:")}
        assert len(product_consumers) >= 5

    def test_reexport_credits_source(self):
        """A `from noctusai_lib.testing import MockSupabaseClient` import
        must credit the source definition, not a reexport alias."""
        rmap = build_reexport_map()
        imports = scan_importers(rmap)
        # Any consumer of MockSupabaseClient should appear under a source path,
        # not under `noctusai_lib.testing.MockSupabaseClient` (unless the
        # source itself lives there).
        testing_alias = "noctusai_lib.testing.MockSupabaseClient"
        if testing_alias in rmap:
            # The alias key should never accumulate counts — counts go to the source.
            assert testing_alias not in imports or not imports[testing_alias]


class TestDuplicateCandidates:
    def test_returns_list(self):
        symbols = scan_lib_symbols()
        dups = scan_duplicate_candidates(symbols)
        assert isinstance(dups, list)

    def test_ignores_generic_names(self):
        """Names like `router`, `settings`, `main` must never be flagged."""
        symbols = scan_lib_symbols()
        dups = scan_duplicate_candidates(symbols)
        flagged = {d.name for d in dups}
        for generic in ("router", "settings", "main", "startup", "shutdown"):
            assert generic not in flagged

    def test_excludes_lib_names(self):
        """A name that already exists in lib must not be a duplicate candidate."""
        symbols = scan_lib_symbols()
        lib_names = {s.name for s in symbols}
        dups = scan_duplicate_candidates(symbols)
        for d in dups:
            assert d.name not in lib_names


class TestReport:
    def test_report_shape(self):
        report = build_catalog()
        d = report.to_dict()
        for key in ("lib_roots", "products_scanned", "symbols", "orphans",
                    "single_consumer", "duplicates", "summary"):
            assert key in d
        s = d["summary"]
        assert s["total_symbols"] == len(d["symbols"])
        assert s["orphans"] == len(d["orphans"])
        assert s["duplicate_candidates"] == len(d["duplicates"])

    def test_every_importer_appears_in_products_scanned_or_is_lib(self):
        report = build_catalog()
        valid = set(report.products_scanned) | {f"lib:{k}" for k in LIB_ROOTS}
        for s in report.symbols:
            for importer in s.importers:
                assert importer in valid, f"Unexpected importer label: {importer}"
