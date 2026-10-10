"""`check_stand_in_conformance` — regression coverage for the three
same-day production failures (2026-09-22) the detector exists to catch. See
`tools/noctus/dev/stand_in_conformance.py`'s module docstring for the full
account of each failure:

  1. `imovel_dados` — an unencodable `datetime.date` write payload the mock
     accepted and the real PostgREST client could not. LEG B(iii) below.
  2. `_SchemaPinnedAdminClient` — a `__slots__` wrapper missing
     `__weakref__`, breaking every `WeakKeyDictionary`-keyed cache the
     moment it ran against real dependency resolution. LEG A / B(i) / B(ii)
     below.
  3. `atendimento_contrato_versoes` — a cross-column CHECK constraint
     `CheckManifest`'s single-column shape cannot express, silently
     unenforced by the mock. LEG B(iv) below.

Each class below builds a SCRATCH tree reproducing (BEFORE) and repairing
(AFTER) one failure shape and asserts the detector's verdict flips — the
before/after proof, pinned as a regression suite instead of a one-off
manual run. A handful of tests also run the same legs against the REAL
repo tree to pin that the shipped fixes stay clean.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.stand_in_conformance import (  # noqa: E402
    _leg_a_check_product,
    _leg_b_iii_mock_write_validator_wired,
    _leg_b_iv_check_constraint_coverage,
    _resolve_product_venv_python,
    check_stand_in_conformance,
)


def _write(root: Path, rel_path: str, content: str) -> Path:
    p = root / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# LEG B(iii) — `MockRequestBuilder.insert/update/upsert` must still call
# `_validate_json_serializable`. Reproduces failure #1 (`imovel_dados`).
# ---------------------------------------------------------------------------

def _mocks_py(*, wired: bool) -> str:
    if wired:
        insert_body = '        _validate_json_serializable(None, payload, "insert")\n'
        update_body = '        _validate_json_serializable(None, payload, "update")\n'
        upsert_body = '        _validate_json_serializable(None, payload, "upsert")\n'
    else:
        # THE BROKEN SHAPE: the call is dropped — exactly what would let
        # a bare `datetime.date` slip through the mock again.
        insert_body = update_body = upsert_body = "        pass\n"
    return (
        "def _validate_json_serializable(table, payload, operation):\n"
        "    pass\n"
        "\n"
        "\n"
        "class MockRequestBuilder:\n"
        "    def insert(self, payload):\n"
        + insert_body
        + "        return self\n"
        "\n"
        "    def update(self, payload):\n"
        + update_body
        + "        return self\n"
        "\n"
        "    def upsert(self, payload):\n"
        + upsert_body
        + "        return self\n"
    )


class TestCheckStandInConformanceLegBiii:
    def test_flags_when_the_validator_call_is_dropped(self, tmp_path):
        """BEFORE — reproduces the `imovel_dados` shape: the mock's write
        path stops calling `_validate_json_serializable`."""
        _write(
            tmp_path,
            "seed/lib/backend/noctusai_lib/testing/mocks.py",
            _mocks_py(wired=False),
        )
        issues = _leg_b_iii_mock_write_validator_wired(tmp_path)
        assert issues, "expected a finding once insert/update/upsert stop calling the validator"
        assert all(i["leg"] == "B(iii)" for i in issues)
        assert issues[0]["severity"] == "high"

    def test_clean_when_the_validator_call_is_present(self, tmp_path):
        """AFTER — the call is wired; no finding."""
        _write(
            tmp_path,
            "seed/lib/backend/noctusai_lib/testing/mocks.py",
            _mocks_py(wired=True),
        )
        assert _leg_b_iii_mock_write_validator_wired(tmp_path) == []

    def test_the_real_repo_is_currently_clean(self):
        from settings import REPO_ROOT

        issues = _leg_b_iii_mock_write_validator_wired(REPO_ROOT)
        assert issues == [], issues


# ---------------------------------------------------------------------------
# LEG B(iv) — since 2026-10-10 the mock ENFORCES every migration-declared
# cross-column CHECK `noctusai_lib.testing.sql_check` can compile, so those
# are covered by construction. A finding is a cross-column CHECK the mock
# CANNOT model that no `ConditionalPresenceManifest` covers and nobody named
# in `_KNOWN_UNENFORCEABLE_CROSS_COLUMN_CHECKS`. Failure #3
# (`atendimento_contrato_versoes`) is the class.
# ---------------------------------------------------------------------------

_MIGRATION_WITH_CROSS_COLUMN_CHECK = """\
CREATE TABLE IF NOT EXISTS widget.contrato_versoes (
    id UUID PRIMARY KEY,
    origem TEXT NOT NULL,
    docx_storage_path TEXT,
    docx_tamanho_bytes BIGINT
);

ALTER TABLE widget.contrato_versoes
    ADD CONSTRAINT contrato_versoes_docx_por_origem
    CHECK (
        (origem = 'gerado' AND docx_storage_path IS NOT NULL AND docx_tamanho_bytes IS NOT NULL)
        OR (origem = 'upload' AND docx_storage_path IS NULL AND docx_tamanho_bytes IS NULL)
    ) NOT VALID;
"""

#: Same table, a CHECK the mock can't model (`LIKE`).
_MIGRATION_WITH_UNMODELLED_CHECK = _MIGRATION_WITH_CROSS_COLUMN_CHECK.replace(
    "docx_storage_path IS NOT NULL AND docx_tamanho_bytes IS NOT NULL",
    "docx_storage_path LIKE 'contratos/%' AND docx_tamanho_bytes IS NOT NULL",
)

_SINGLE_COLUMN_CHECK_MIGRATION = (
    "ALTER TABLE widget.x ADD COLUMN y BIGINT CHECK (y IS NULL OR y >= 0);\n"
)


def _b_iv(tmp_path):
    return _leg_b_iv_check_constraint_coverage(tmp_path, [tmp_path / "products" / "widget"])


class TestCheckStandInConformanceLegBiv:
    def test_a_compilable_cross_column_check_is_covered_by_construction(self, tmp_path):
        """The `atendimento_contrato_versoes` shape: the mock now enforces it
        straight from the migration — no manifest, no finding."""
        _write(tmp_path, "products/widget/backend/migrations/001_contrato.sql",
               _MIGRATION_WITH_CROSS_COLUMN_CHECK)

        assert _b_iv(tmp_path) == []

    def test_flags_a_cross_column_check_the_mock_cannot_model(self, tmp_path):
        _write(tmp_path, "products/widget/backend/migrations/001_contrato.sql",
               _MIGRATION_WITH_UNMODELLED_CHECK)

        issues = _b_iv(tmp_path)

        assert len(issues) == 1, issues
        assert issues[0]["leg"] == "B(iv)" and issues[0]["severity"] == "high"
        assert "contrato_versoes_docx_por_origem" in issues[0]["file"]
        assert "LIKE" in issues[0]["issue"]

    def test_an_unmodelled_check_covered_by_a_presence_manifest_is_clean(self, tmp_path):
        _write(tmp_path, "products/widget/backend/migrations/001_contrato.sql",
               _MIGRATION_WITH_UNMODELLED_CHECK)
        _write(
            tmp_path,
            "products/widget/backend/tests/conftest.py",
            'CONTRATO_VERSOES_PRESENCE_MANIFEST = {\n'
            '    "contrato_versoes": [("origem", "gerado", {"docx_storage_path": True})],\n'
            "}\n",
        )

        assert _b_iv(tmp_path) == []

    def test_a_dropped_check_is_not_reported(self, tmp_path):
        _write(tmp_path, "products/widget/backend/migrations/001_contrato.sql",
               _MIGRATION_WITH_UNMODELLED_CHECK)
        _write(tmp_path, "products/widget/backend/migrations/002_drop.sql",
               "ALTER TABLE widget.contrato_versoes DROP CONSTRAINT contrato_versoes_docx_por_origem;\n")

        assert _b_iv(tmp_path) == []

    def test_single_column_check_is_not_flagged(self, tmp_path):
        """`CheckManifest`'s single-column shape — not this leg's."""
        _write(tmp_path, "products/widget/backend/migrations/001_x.sql",
               _SINGLE_COLUMN_CHECK_MIGRATION.replace("y >= 0", "y::text LIKE '1%'"))

        assert _b_iv(tmp_path) == []

    def test_the_real_fleet_is_clean(self):
        """The 75-finding backlog (2026-10-10) closed by construction: every
        cross-column CHECK in an active product either compiles (the mock
        enforces it) or is covered/named."""
        from settings import REPO_ROOT

        from tools.noctus.dev.stand_in_conformance import _active_product_dirs

        assert _leg_b_iv_check_constraint_coverage(REPO_ROOT, _active_product_dirs(REPO_ROOT)) == []


# ---------------------------------------------------------------------------
# LEG A / B(i) / B(ii) — dependency resolution against a REAL client
# object; the resolved object must be weak-referenceable and identity-
# stable across calls. Reproduces failure #2 (`_SchemaPinnedAdminClient`).
# ---------------------------------------------------------------------------

_DEPENDENCIES_PY_BROKEN = """\
class _BadPinnedClient:
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


_cache = None


def get_admin_client():
    global _cache
    if _cache is None:
        _cache = _BadPinnedClient("admin")
    return _cache
"""

_DEPENDENCIES_PY_FIXED = _DEPENDENCIES_PY_BROKEN.replace(
    '__slots__ = ("value",)', '__slots__ = ("value", "__weakref__")',
)

_DEPENDENCIES_PY_FRESH_EACH_CALL = """\
class _FreshClient:
    def __init__(self, value):
        self.value = value


# B(ii) is scoped to SEED-provided stand-ins (`noctusai_seed`/
# `noctusai_lib`) to avoid flooding on deliberately-fresh product
# factories — spoof the module the real `_SchemaPinnedAdminClient` lives
# in so this scratch class exercises that scope.
_FreshClient.__module__ = "noctusai_seed.database"


def get_admin_client():
    return _FreshClient("admin")
"""

_ROUTER_PY = """\
from fastapi import APIRouter, Depends

from app.dependencies import get_admin_client

router = APIRouter()


@router.get("/widget")
def route(admin=Depends(get_admin_client)):
    return {"ok": True}
"""


def _scratch_product(tmp_path: Path, deps_source: str) -> Path:
    _write(tmp_path, "products/widget/backend/app/__init__.py", "")
    _write(tmp_path, "products/widget/backend/app/dependencies.py", deps_source)
    _write(tmp_path, "products/widget/backend/app/routers/__init__.py", "")
    _write(tmp_path, "products/widget/backend/app/routers/widget_router.py", _ROUTER_PY)
    return tmp_path / "products" / "widget"


class TestCheckStandInConformanceLegA:
    def test_flags_a_non_weak_referenceable_dependency(self, tmp_path):
        """BEFORE — `_BadPinnedClient` reproduces `_SchemaPinnedAdminClient`
        missing `__weakref__`: resolving the real `Depends(get_admin_client)`
        target must raise, not silently succeed."""
        product_dir = _scratch_product(tmp_path, _DEPENDENCIES_PY_BROKEN)
        issues = _leg_a_check_product("widget", product_dir, tmp_path, Path(sys.executable))
        legs = {i["leg"] for i in issues}
        assert "B(i)" in legs, issues
        assert any(i["severity"] == "high" for i in issues), issues

    def test_clean_once_weak_referenceable(self, tmp_path):
        """AFTER — `__weakref__` restored to `__slots__`; no finding."""
        product_dir = _scratch_product(tmp_path, _DEPENDENCIES_PY_FIXED)
        issues = _leg_a_check_product("widget", product_dir, tmp_path, Path(sys.executable))
        assert issues == [], issues

    def test_flags_identity_instability(self, tmp_path):
        """A dependency returning a FRESH object every call would silently
        never hit a `WeakKeyDictionary` cache keyed on it — B(ii)."""
        product_dir = _scratch_product(tmp_path, _DEPENDENCIES_PY_FRESH_EACH_CALL)
        issues = _leg_a_check_product("widget", product_dir, tmp_path, Path(sys.executable))
        assert any(i["leg"] == "B(ii)" for i in issues), issues

    def test_resolve_product_venv_python_finds_the_primary_venv(self, tmp_path):
        """Hermetic (CI has no repo-root venv/): a root carrying
        venv/bin/python resolves to it."""
        py = tmp_path / "venv" / "bin" / "python"
        py.parent.mkdir(parents=True)
        py.write_text("#!/bin/sh\n")
        python_exe = _resolve_product_venv_python(tmp_path)
        assert python_exe == py
        assert python_exe.is_file()

    def test_resolve_product_venv_python_is_inconclusive_not_crashing_outside_a_repo(self, tmp_path):
        # tmp_path is not a git repo and has no venv/ — must return None,
        # never raise, so the caller can report `inconclusive`.
        assert _resolve_product_venv_python(tmp_path) is None

    def test_the_real_social_wiring_admin_client_dependency_is_currently_clean(self):
        """AFTER — the shipped `_SchemaPinnedAdminClient` fix: resolving
        social-wiring's real `get_admin_client`/`get_scoped_admin_client`
        chain against a real client must raise nothing and stay identity-
        stable. Tolerates `inconclusive` (e.g. no venv in this CI runner)
        but must NEVER silently pass as `ok` while reporting nothing —
        so a `high`-severity finding is what we assert against."""
        from settings import REPO_ROOT

        python_exe = _resolve_product_venv_python(REPO_ROOT)
        if python_exe is None:
            return  # inconclusive path already covered by the dedicated test above
        product_dir = REPO_ROOT / "products" / "social-wiring"
        if not (product_dir / "backend" / "app").is_dir():
            return
        issues = _leg_a_check_product("social-wiring", product_dir, REPO_ROOT, python_exe)
        high = [i for i in issues if i["severity"] == "high"]
        assert high == [], high


# ---------------------------------------------------------------------------
# Full composition — smoke-tests the entry point end to end.
# ---------------------------------------------------------------------------

class TestCheckStandInConformance:
    def test_the_real_repo_legs_a_and_biii_are_currently_clean(self):
        """Composition smoke test: legs A/B(i)/B(ii)/B(iii) against the
        real (already-fixed) tree must report zero findings.

        Leg B(iv) is included since 2026-10-10: the mock enforces every
        cross-column CHECK it can compile, which closed the pre-existing
        backlog that used to be excluded here."""
        from settings import REPO_ROOT

        issues = check_stand_in_conformance(REPO_ROOT)
        findings = [i for i in issues if i.get("status") == "finding"]
        assert findings == [], findings


# ---------------------------------------------------------------------------
# LEG A — fail-closed "not configured" integrations + Optional-None deps
# (2026-10-10). A config-less subprocess makes every correctly fail-closed
# integration raise; recognised BY TYPE via the seed marker, through a
# wrapping re-raise — never by message text, never by a per-site allowlist.
# ---------------------------------------------------------------------------

_MARKER_SRC = (Path(__file__).resolve().parents[3]
               / "seed/lib/backend/noctusai_lib/primitives/not_configured.py")


def _scratch_with_marker(tmp_path: Path, deps_source: str) -> Path:
    for pkg in ("noctusai_lib", "noctusai_lib/primitives"):
        _write(tmp_path, f"seed/lib/backend/{pkg}/__init__.py", "")
    _write(tmp_path, "seed/lib/backend/noctusai_lib/primitives/not_configured.py", _MARKER_SRC.read_text())
    return _scratch_product(tmp_path, deps_source)


_DEPS_NOT_CONFIGURED_WRAPPED = """\
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured


class VendorConfigError(RuntimeError, IntegrationNotConfigured):
    pass


class HTTPError503(Exception):
    pass


def get_admin_client():
    try:
        raise VendorConfigError("VENDOR_BASE_URL is empty")
    except VendorConfigError as exc:
        raise HTTPError503("vendor_nao_configurado") from exc
"""

_DEPS_UNMARKED_FAILURE = """\
def get_admin_client():
    raise RuntimeError("VENDOR_BASE_URL is empty")  # same text, no marker
"""

_DEPS_OPTIONAL_NONE = """\
def get_admin_client():
    return None
"""


class TestCheckStandInConformanceNotConfigured:
    def test_marked_not_configured_through_a_wrapper_is_skipped(self, tmp_path):
        product_dir = _scratch_with_marker(tmp_path, _DEPS_NOT_CONFIGURED_WRAPPED)
        assert _leg_a_check_product("widget", product_dir, tmp_path, Path(sys.executable)) == []

    def test_unmarked_failure_is_still_a_finding(self, tmp_path):
        product_dir = _scratch_with_marker(tmp_path, _DEPS_UNMARKED_FAILURE)
        issues = _leg_a_check_product("widget", product_dir, tmp_path, Path(sys.executable))
        assert [i["leg"] for i in issues] == ["A"], issues
        assert issues[0]["severity"] == "high"

    def test_optional_dependency_resolving_to_none_is_not_a_weakref_finding(self, tmp_path):
        product_dir = _scratch_with_marker(tmp_path, _DEPS_OPTIONAL_NONE)
        assert _leg_a_check_product("widget", product_dir, tmp_path, Path(sys.executable)) == []
