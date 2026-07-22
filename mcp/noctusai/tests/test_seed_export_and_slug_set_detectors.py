"""Regression tests for the social-wiring-absorption Stage-4 codification
pair — W5.7a + W5.9a (2026-05-16).

Two detectors promoting Stage-3 methodology rules to Stage-4 keeper
detectors. Each gets a focused `Test<CamelCase>` class with
positive-fires + negative-doesn't-fire + edge-case tests. Tests are
file-system-scoped (`tmp_path` fixture) per the seed test pattern; no
monkey-patching of our own code.

Detectors covered:
  - `check_seed_export_membership`     (W5.7a; N=2: lid_auth + FE WA hooks)
  - `check_hardcoded_product_slug_set` (W5.9a; N=2: cors_registry + sentinel)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.compliance import (  # noqa: E402
    check_hardcoded_fleet_size_literal,
    check_hardcoded_product_slug_set,
    check_product_source_build_dep_pip_seam,
    check_seed_export_membership,
)


# ---------------------------------------------------------------------------
# check_seed_export_membership
# ---------------------------------------------------------------------------


class TestCheckSeedExportMembership:
    """A symbol a product imports from the seed surface must be in that
    package's public `__all__` (backend) / `index.ts` re-exports (frontend).
    """

    def _mk_whatsapp_pkg(self, tmp_path: Path, dunder_all: str) -> None:
        """Write the `noctusai_lib.integrations.whatsapp` PACKAGE
        `__init__.py` with the given `__all__` literal — the lid_auth
        half-ship shape (package surface that omits a consumed symbol).
        """
        pkg = (
            tmp_path / "seed" / "lib" / "backend" / "noctusai_lib"
            / "integrations" / "whatsapp"
        )
        pkg.mkdir(parents=True)
        (pkg / "__init__.py").write_text(f"__all__ = {dunder_all}\n")
        (pkg / "lid_auth.py").write_text("def resolve_canonical_session():\n    ...\n")

    def _mk_product_backend(self, tmp_path: Path, py: str) -> None:
        app = tmp_path / "products" / "p1" / "backend" / "app"
        app.mkdir(parents=True)
        (app / "service.py").write_text(py)

    def test_flags_backend_symbol_absent_from_package_all(self, tmp_path):
        # lid_auth-shape half-ship: imported FROM THE PACKAGE but the
        # package `__all__` omits it.
        self._mk_whatsapp_pkg(tmp_path, '["WahaClient"]')
        self._mk_product_backend(
            tmp_path,
            "from noctusai_lib.integrations.whatsapp import resolve_canonical_session\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "resolve_canonical_session" in issues[0]["issue"]
        assert "__all__" in issues[0]["issue"]
        assert issues[0]["product"] == "p1"

    def test_does_not_flag_backend_symbol_in_package_all(self, tmp_path):
        self._mk_whatsapp_pkg(tmp_path, '["WahaClient", "resolve_canonical_session"]')
        self._mk_product_backend(
            tmp_path,
            "from noctusai_lib.integrations.whatsapp import resolve_canonical_session\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_plain_module_deep_import(self, tmp_path):
        """`from noctusai_lib.api.auth import make_get_current_user_org`
        where `auth` is a plain module (`auth.py`, no package `__init__`)
        is a LEGITIMATE deep import — not the half-ship rule.
        """
        api = tmp_path / "seed" / "lib" / "backend" / "noctusai_lib" / "api"
        api.mkdir(parents=True)
        (api / "auth.py").write_text("def make_get_current_user_org():\n    ...\n")
        self._mk_product_backend(
            tmp_path,
            "from noctusai_lib.api.auth import make_get_current_user_org\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_submodule_import(self, tmp_path):
        """`from noctusai_lib.api import scheduler` where `scheduler` is the
        submodule `noctusai_lib/api/scheduler.py` is a MODULE import, not a
        symbol re-export — `__all__` does not govern it. (N=4 live FP class:
        therapy/PF/mailing/social-wiring all do this.)
        """
        api = tmp_path / "seed" / "lib" / "backend" / "noctusai_lib" / "api"
        api.mkdir(parents=True)
        (api / "__init__.py").write_text('__all__ = ["StrictHttpModel"]\n')
        (api / "scheduler.py").write_text("def run():\n    ...\n")
        self._mk_product_backend(
            tmp_path,
            "from noctusai_lib.api import scheduler as seed_scheduler\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_flags_real_symbol_half_ship_not_submodule(self, tmp_path):
        """A symbol that is NOT a submodule and NOT in `__all__` still
        fires (proves the submodule guard is narrow, not a blanket mute).
        """
        api = tmp_path / "seed" / "lib" / "backend" / "noctusai_lib" / "api"
        api.mkdir(parents=True)
        (api / "__init__.py").write_text(
            '__all__ = ["StrictHttpModel"]\n'
            "def make_thing():\n    ...\n"  # defined but not in __all__
        )
        self._mk_product_backend(
            tmp_path, "from noctusai_lib.api import make_thing\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert len(issues) == 1, issues
        assert "make_thing" in issues[0]["issue"]

    def test_skips_when_package_all_non_literal(self, tmp_path):
        # Computed __all__ → conservatively skip (false negatives over noise).
        self._mk_whatsapp_pkg(tmp_path, "_BASE + ['x']")
        self._mk_product_backend(
            tmp_path,
            "from noctusai_lib.integrations.whatsapp import resolve_canonical_session\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_flags_frontend_symbol_absent_from_index(self, tmp_path):
        # createWhatsAppConnectionHooks-shape half-ship (W2.4/DEP-B).
        fe_index = tmp_path / "seed" / "lib" / "frontend" / "src"
        fe_index.mkdir(parents=True)
        (fe_index / "index.ts").write_text(
            "export { createApiClient } from './api';\n"
        )
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "useWA.ts").write_text(
            "import { createWhatsAppConnectionHooks } from '@noctusai/lib';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert len(issues) == 1, issues
        assert "createWhatsAppConnectionHooks" in issues[0]["issue"]
        assert "index.ts" in issues[0]["issue"]

    def test_does_not_flag_frontend_symbol_reexported(self, tmp_path):
        fe_index = tmp_path / "seed" / "lib" / "frontend" / "src"
        fe_index.mkdir(parents=True)
        (fe_index / "index.ts").write_text(
            "export { createWhatsAppConnectionHooks } from './whatsapp';\n"
        )
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "useWA.ts").write_text(
            "import { createWhatsAppConnectionHooks } from '@noctusai/lib';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_frontend_aliased_reexport_satisfies(self, tmp_path):
        """`export { internal as createWhatsAppConnectionHooks }` exposes the
        aliased (right-hand) name.
        """
        fe_index = tmp_path / "seed" / "lib" / "frontend" / "src"
        fe_index.mkdir(parents=True)
        (fe_index / "index.ts").write_text(
            "export { _internal as createWhatsAppConnectionHooks } from './wa';\n"
        )
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "useWA.ts").write_text(
            "import { createWhatsAppConnectionHooks } from '@noctusai/lib';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_frontend_export_star_skips(self, tmp_path):
        # Non-enumerable surface → conservatively skip.
        fe_index = tmp_path / "seed" / "lib" / "frontend" / "src"
        fe_index.mkdir(parents=True)
        (fe_index / "index.ts").write_text("export * from './everything';\n")
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "useWA.ts").write_text(
            "import { whatever } from '@noctusai/lib';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_framework_specifier_checked_against_framework_index(self, tmp_path):
        """`@noctusai/seed` resolves to the FRAMEWORK frontend index, not
        the lib index — `createProductApp` published there must NOT flag.
        """
        lib_idx = tmp_path / "seed" / "lib" / "frontend" / "src"
        lib_idx.mkdir(parents=True)
        (lib_idx / "index.ts").write_text("export { cn } from './utils';\n")
        fw_idx = tmp_path / "seed" / "framework" / "frontend" / "src"
        fw_idx.mkdir(parents=True)
        (fw_idx / "index.ts").write_text(
            "export { createProductApp } from './factory';\n"
        )
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "App.tsx").write_text(
            "import { createProductApp } from '@noctusai/seed';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_framework_specifier_flags_when_absent_from_framework_index(self, tmp_path):
        lib_idx = tmp_path / "seed" / "lib" / "frontend" / "src"
        lib_idx.mkdir(parents=True)
        # Even though lib index lists it, the framework specifier must be
        # checked against the FRAMEWORK index (which omits it).
        (lib_idx / "index.ts").write_text(
            "export { createProductApp } from './x';\n"
        )
        fw_idx = tmp_path / "seed" / "framework" / "frontend" / "src"
        fw_idx.mkdir(parents=True)
        (fw_idx / "index.ts").write_text("export { other } from './o';\n")
        src = tmp_path / "products" / "p1" / "frontend" / "src"
        src.mkdir(parents=True)
        (src / "App.tsx").write_text(
            "import { createProductApp } from '@noctusai/seed';\n"
        )
        issues = check_seed_export_membership(tmp_path)
        assert len(issues) == 1, issues
        assert "createProductApp" in issues[0]["issue"]
        assert "seed/framework/frontend/src/index.ts" in issues[0]["issue"]

    def test_non_seed_import_ignored(self, tmp_path):
        self._mk_whatsapp_pkg(tmp_path, '["WahaClient"]')
        self._mk_product_backend(
            tmp_path,
            "from fastapi import FastAPI\nfrom app.models import Thing\n",
        )
        issues = check_seed_export_membership(tmp_path)
        assert issues == [], issues

    def test_missing_repo_root_no_error(self, tmp_path):
        issues = check_seed_export_membership(tmp_path / "nope")
        assert issues == []


# ---------------------------------------------------------------------------
# check_hardcoded_product_slug_set
# ---------------------------------------------------------------------------


class TestCheckHardcodedProductSlugSet:
    """Seed tests must derive product sets from `parse_products_registry()`,
    never freeze a product-slug literal.
    """

    def _mk_fleet(self, tmp_path: Path, slugs: list[str]) -> None:
        for s in slugs:
            (tmp_path / "products" / s).mkdir(parents=True)

    def _mk_seed_test(self, tmp_path: Path, py: str, *, name: str = "test_x.py") -> None:
        td = tmp_path / "seed" / "lib" / "backend" / "tests" / "config"
        td.mkdir(parents=True, exist_ok=True)
        (td / name).write_text(py)

    def test_flags_frozen_slug_tuple(self, tmp_path):
        # The per_product_cors_sentinel shape (W3.5 evidence).
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform", "adconnect"])
        self._mk_seed_test(
            tmp_path,
            'PRODUCT_SLUGS = (\n'
            '    "core",\n'
            '    "erp-imobiliario",\n'
            '    "therapy-platform",\n'
            '    "adconnect",\n'
            ')\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert "parse_products_registry" in issues[0]["issue"]
        assert issues[0]["product"] == "<seed-tests>"

    def test_flags_frozen_slug_set_annassign(self, tmp_path):
        self._mk_fleet(tmp_path, ["core", "personal-finance", "daily-life"])
        self._mk_seed_test(
            tmp_path,
            'SLUGS: set[str] = {"core", "personal-finance", "daily-life"}\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert len(issues) == 1, issues

    def test_does_not_flag_below_threshold(self, tmp_path):
        # 2 slugs < _SLUG_LITERAL_MIN_HITS (3) — not a product-set marker.
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        self._mk_seed_test(
            tmp_path, 'PAIR = ("core", "erp-imobiliario")\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_registry_derived(self, tmp_path):
        # The W3.5 root-fix shape: derived, no frozen literal.
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        self._mk_seed_test(
            tmp_path,
            "from noctusai_lib.config.cors_registry import parse_products_registry\n"
            "SLUGS = {e['slug'] for e in parse_products_registry()}\n",
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == [], issues

    def test_rationale_keyword_opts_out(self, tmp_path):
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        self._mk_seed_test(
            tmp_path,
            "# slug-literal-ok: this maps slug->schema, not a product set\n"
            'SCHEMA_BY_SLUG = ("core", "erp-imobiliario", "therapy-platform")\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == [], issues

    def test_non_slug_string_collection_ignored(self, tmp_path):
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        self._mk_seed_test(
            tmp_path,
            'HEADERS = ("Content-Type", "Authorization", "X-Trace-Id")\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == [], issues

    def test_no_seed_tests_dir_no_error(self, tmp_path):
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == []

    def test_no_fleet_no_error(self, tmp_path):
        self._mk_seed_test(
            tmp_path, 'X = ("core", "erp-imobiliario", "therapy-platform")\n',
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == []

    # -- surface 2: scripts/infra/*.sh bash-array literals (N=3, 2026-07-22
    # build-and-push.sh fleet-build outage) --------------------------------

    def _mk_infra_script(self, tmp_path: Path, sh: str, *, name: str = "build-and-push.sh") -> None:
        d = tmp_path / "scripts" / "infra"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(sh)

    def test_flags_frozen_bash_array_in_infra_script(self, tmp_path):
        # The actual ALL_SLUGS=(...) shape that aborted the fleet build.
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform", "adconnect"])
        self._mk_infra_script(
            tmp_path,
            "#!/usr/bin/env bash\n"
            "ALL_SLUGS=(core erp-imobiliario therapy-platform adconnect)\n",
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert issues[0]["product"] == "<infra-scripts>"
        assert "docker-compose.prod.yml" in issues[0]["issue"]

    def test_does_not_flag_derived_bash_array(self, tmp_path):
        # The root-fix shape: array populated at run time, no frozen literal.
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        self._mk_infra_script(
            tmp_path,
            "#!/usr/bin/env bash\n"
            "ALL_SLUGS=()\n"
            "while IFS= read -r slug; do ALL_SLUGS+=(\"$slug\"); done < <(true)\n",
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == [], issues

    def test_bash_array_rationale_keyword_opts_out(self, tmp_path):
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        self._mk_infra_script(
            tmp_path,
            "#!/usr/bin/env bash\n"
            "# slug-literal-ok: fixture, not the deployable set\n"
            "SAMPLE=(core erp-imobiliario therapy-platform)\n",
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == [], issues

    def test_bash_array_below_threshold_not_flagged(self, tmp_path):
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        self._mk_infra_script(
            tmp_path, "#!/usr/bin/env bash\nPAIR=(core erp-imobiliario)\n",
        )
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == [], issues

    def test_no_infra_scripts_dir_no_error(self, tmp_path):
        self._mk_fleet(tmp_path, ["core", "erp-imobiliario", "therapy-platform"])
        issues = check_hardcoded_product_slug_set(tmp_path)
        assert issues == []


# ---------------------------------------------------------------------------
# check_hardcoded_fleet_size_literal
# ---------------------------------------------------------------------------


class TestCheckHardcodedFleetSizeLiteral:
    """Seed tests must not assert a frozen fleet-size numeric literal —
    the numeric-axis twin of `check_hardcoded_product_slug_set`.
    """

    def _mk_seed_test(self, tmp_path: Path, py: str, *, name: str = "test_x.py") -> None:
        td = tmp_path / "seed" / "lib" / "backend" / "tests" / "config"
        td.mkdir(parents=True, exist_ok=True)
        (td / name).write_text(py)

    def test_flags_len_gte_fleet_floor(self, tmp_path):
        # The test_cors_registry.py:130 shape (`assert len(entries) >= 8`),
        # enclosing function is fleet-semantic (mentions products_registry).
        self._mk_seed_test(
            tmp_path,
            "def test_products_registry_populated():\n"
            "    entries = load_products_registry_entries()\n"
            "    assert len(entries) >= 8\n",
        )
        issues = check_hardcoded_fleet_size_literal(tmp_path)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "warning"
        assert issues[0]["product"] == "<seed-tests>"
        assert "parse_products_registry" in issues[0]["issue"]

    def test_flags_len_eq_and_gt(self, tmp_path):
        # `>= 10` (cors_origins) and `== 12` (fleet) — both frozen counts.
        self._mk_seed_test(
            tmp_path,
            "def test_a():\n"
            "    # cors_origins for every product\n"
            "    assert len(origins) >= 10\n"
            "def test_b():\n"
            "    # fleet size\n"
            "    assert len(products) == 12\n",
        )
        issues = check_hardcoded_fleet_size_literal(tmp_path)
        assert len(issues) == 2, issues

    def test_flags_const_on_left(self, tmp_path):
        # `8 <= len(x)` — len() on the right side; fleet-semantic function.
        self._mk_seed_test(
            tmp_path,
            "def test_fleet_floor():\n    assert 8 <= len(slugs)\n",
        )
        issues = check_hardcoded_fleet_size_literal(tmp_path)
        assert len(issues) == 1, issues

    def test_does_not_flag_below_floor(self, tmp_path):
        # `len(headers) == 3` — far below the fleet floor (5); an unrelated
        # bound, not a fleet count.
        self._mk_seed_test(
            tmp_path,
            "def test_h():\n"
            "    # cors_origins header check\n"
            "    assert len(headers) == 3\n",
        )
        issues = check_hardcoded_fleet_size_literal(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_non_fleet_count(self, tmp_path):
        # The W5.9a calibration FP: `len(token_data) == 280` is a token
        # count, not a fleet literal — no fleet-semantic token nearby.
        self._mk_seed_test(
            tmp_path,
            "def test_ai_output_shape():\n"
            "    tokens = call_model()\n"
            "    assert len(tokens) == 280\n",
        )
        issues = check_hardcoded_fleet_size_literal(tmp_path)
        assert issues == [], issues

    def test_does_not_flag_registry_derived(self, tmp_path):
        # The W3.5 root-fix shape: the count is computed from the registry
        # in the same function → not frozen → does not stale.
        self._mk_seed_test(
            tmp_path,
            "from noctusai_lib.config.cors_registry import parse_products_registry\n"
            "def test_derived():\n"
            "    entries = parse_products_registry()\n"
            "    assert len(entries) >= len(entries)\n",
        )
        issues = check_hardcoded_fleet_size_literal(tmp_path)
        assert issues == [], issues

    def test_rationale_keyword_opts_out(self, tmp_path):
        # Fleet-semantic (mentions products_registry) but rationale-tagged:
        # a legitimate non-fleet count that happens to live near fleet code.
        self._mk_seed_test(
            tmp_path,
            "# fleet-size-ok: 7 is the retry-cap, not a product count\n"
            "def test_products_registry_retry():\n"
            "    assert len(attempts) <= 7\n",
        )
        issues = check_hardcoded_fleet_size_literal(tmp_path)
        assert issues == [], issues

    def test_non_len_comparison_ignored(self, tmp_path):
        # A plain numeric assert with no `len()` is not a fleet-size claim.
        self._mk_seed_test(
            tmp_path,
            "def test_n():\n    assert status_code == 200\n",
        )
        issues = check_hardcoded_fleet_size_literal(tmp_path)
        assert issues == [], issues

    def test_no_seed_tests_dir_no_error(self, tmp_path):
        (tmp_path / "products" / "core").mkdir(parents=True)
        issues = check_hardcoded_fleet_size_literal(tmp_path)
        assert issues == []

    def test_missing_repo_root_no_error(self, tmp_path):
        issues = check_hardcoded_fleet_size_literal(tmp_path / "nope")
        assert issues == []


# ---------------------------------------------------------------------------
# check_product_source_build_dep_pip_seam
# ---------------------------------------------------------------------------


class TestCheckProductSourceBuildDepPipSeam:
    """A product whose backend requirements pull a source-only (no
    arm64-wheel) dep MUST have a per-slug PIP_RUN seam in
    propagate-dockerfiles.sh — Stage-4 codification of
    KB § PATTERNS/devops/containerization.md §3.2a.
    """

    def _scaffold(
        self, tmp_path: Path, *, slug: str, reqs: str, seam_slugs: list[str]
    ) -> Path:
        prop = tmp_path / "scripts" / "propagate-dockerfiles.sh"
        prop.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(f'    "{s}": (\n        "RUN ..."\n    ),\n'
                        for s in seam_slugs)
        prop.write_text(
            "SEED_PIP_RUN = (\n    \"RUN pip install\"\n)\n"
            f"PIP_RUN = {{\n{body}}}\n"
        )
        req = tmp_path / "products" / slug / "backend" / "requirements.txt"
        req.parent.mkdir(parents=True, exist_ok=True)
        req.write_text(reqs)
        return tmp_path

    def test_flags_source_only_dep_without_seam(self, tmp_path):
        # erp-shape: xhtml2pdf present, slug NOT a PIP_RUN key → high.
        root = self._scaffold(
            tmp_path, slug="erp-imobiliario",
            reqs="fastapi==0.115.5\nxhtml2pdf>=0.2.0\nopenai>=1.50.0\n",
            seam_slugs=[],
        )
        issues = check_product_source_build_dep_pip_seam(root)
        assert len(issues) == 1, issues
        assert issues[0]["severity"] == "high"
        assert issues[0]["product"] == "erp-imobiliario"
        assert "xhtml2pdf" in issues[0]["issue"]
        assert "§3.2a" in issues[0]["issue"]

    def test_no_flag_when_seam_present(self, tmp_path):
        # Same product + dep, but slug IS a PIP_RUN key → handled, 0.
        root = self._scaffold(
            tmp_path, slug="erp-imobiliario",
            reqs="xhtml2pdf>=0.2.0\n",
            seam_slugs=["erp-imobiliario"],
        )
        assert check_product_source_build_dep_pip_seam(root) == []

    def test_no_flag_when_no_source_only_dep(self, tmp_path):
        # All-wheel deps → no seam needed, 0.
        root = self._scaffold(
            tmp_path, slug="core",
            reqs="fastapi==0.115.5\nPyJWT==2.12.0\nopenai>=1.50.0\n",
            seam_slugs=[],
        )
        assert check_product_source_build_dep_pip_seam(root) == []

    def test_pycairo_direct_also_flagged(self, tmp_path):
        root = self._scaffold(
            tmp_path, slug="daily-life",
            reqs="pycairo>=1.20.0\n", seam_slugs=[],
        )
        issues = check_product_source_build_dep_pip_seam(root)
        assert len(issues) == 1 and issues[0]["product"] == "daily-life", issues

    def test_missing_propagate_script_no_error(self, tmp_path):
        # Product tree exists but no propagate script → graceful 0.
        req = tmp_path / "products" / "x" / "backend" / "requirements.txt"
        req.parent.mkdir(parents=True, exist_ok=True)
        req.write_text("xhtml2pdf>=0.2.0\n")
        assert check_product_source_build_dep_pip_seam(tmp_path) == []

    def test_real_repo_is_green(self):
        # The live tree must pass: erp has the seam; no other product
        # carries a source-only root. Guards the 2026-05-18 fix + future.
        root = Path(__file__).resolve().parents[3]
        assert check_product_source_build_dep_pip_seam(root) == []
