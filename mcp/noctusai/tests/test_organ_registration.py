"""Tests for organ registration (W4, seed-organs-cache).

Covers:
- test_register_organ_writes_yaml_sidecar: organ.yaml files exist for all 5 organs
- test_register_organ_embeds_chunk: mock embed → verify cache write (chunk_kind=organ)
- test_re_register_is_idempotent: same content → same source_sha → no re-embed
- test_organ_yaml_has_8_knowledge_fields: every organ.yaml carries all 8 fields
- test_shelfware_not_in_canonical: shelfware items not in canonical organs list
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import yaml

# Insert mcp/ package root so tool modules resolve.
_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))

from tools.noctus.dev.find_reusable_component import (
    CANONICAL_ORGANS,
    PHASE_2_ORGANS,
    PHASE_2_HOOKS_AND_HELPERS,
    ORGAN_CHUNK_KIND,
    SHELFWARE_ORGANS,
    _find_organ_yaml,
    _load_organ_yaml,
    _organ_source_sha,
    register_organ,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

# Resolve the repo root via settings (the same path REPO_ROOT uses at runtime).
# The test file lives at mcp/noctusai/tests/ inside the worktree, so
# parents[3] is the worktree root in a worktree checkout; in the primary
# checkout it could vary. Use settings.REPO_ROOT when available, else fall back.
try:
    import settings as _settings
    _REPO_ROOT: Path = _settings.REPO_ROOT
except Exception:
    # Fallback: climb from test file to mcp/ parent (3 levels) = repo root.
    _REPO_ROOT = Path(__file__).resolve().parents[3]


def _find_organ_yaml_in_repo(name: str) -> Path | None:
    """Search for <Name>.organ.yaml in the worktree (for existence tests)."""
    return _find_organ_yaml(name, _REPO_ROOT)


# ── Tests: sidecar existence ───────────────────────────────────────────────────


class TestOrganYamlSidecarsExist:
    """All 5 canonical organs must have a .organ.yaml sidecar committed."""

    @pytest.mark.parametrize("name", CANONICAL_ORGANS)
    def test_organ_yaml_exists(self, name):
        p = _find_organ_yaml(name, _REPO_ROOT)
        assert p is not None, (
            f"{name}.organ.yaml not found. "
            f"Searched under {_REPO_ROOT / 'seed' / 'lib' / 'frontend' / 'src'}. "
            "W4 must commit a sidecar for each canonical organ."
        )
        assert p.exists(), f"{name}.organ.yaml path {p} does not exist"


class TestOrganYamlHas8KnowledgeFields:
    """Every organ.yaml must carry all 8 knowledge fields (§3a)."""

    REQUIRED_FIELDS = [
        "known_facts",
        "errors_encountered",
        "drifts_surfaced",
        "alternatives_considered",
        "manual_validation_log",
        "integration_test_status",
        "e2e_test",
        "bugs_fixed_during_dev",
    ]

    @pytest.mark.parametrize("name", CANONICAL_ORGANS)
    def test_all_8_fields_present(self, name):
        p = _find_organ_yaml(name, _REPO_ROOT)
        if p is None:
            pytest.skip(f"{name}.organ.yaml not found — sidecar existence tested separately")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        missing = [f for f in self.REQUIRED_FIELDS if f not in data]
        assert not missing, (
            f"{name}.organ.yaml missing fields: {missing}. "
            "All 8 knowledge fields required per PROJECT.md §3a."
        )

    @pytest.mark.parametrize("name", CANONICAL_ORGANS)
    def test_known_facts_has_at_least_2_entries(self, name):
        p = _find_organ_yaml(name, _REPO_ROOT)
        if p is None:
            pytest.skip(f"{name}.organ.yaml not found")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        facts = data.get("known_facts", [])
        assert isinstance(facts, list), f"{name}: known_facts must be a list"
        assert len(facts) >= 2, (
            f"{name}: known_facts has {len(facts)} entries; minimum 2 required per W4 brief."
        )

    @pytest.mark.parametrize("name", CANONICAL_ORGANS)
    def test_required_structural_fields(self, name):
        """name, path, phase, registered_at must be present."""
        p = _find_organ_yaml(name, _REPO_ROOT)
        if p is None:
            pytest.skip(f"{name}.organ.yaml not found")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for field in ("name", "path", "phase", "registered_at"):
            assert field in data, f"{name}.organ.yaml missing structural field: {field!r}"


# ── Tests: register_organ (mock embed) ────────────────────────────────────────


class TestRegisterOrganEmbedsChunk:
    """register_organ must write a row with chunk_kind='organ' into the cache."""

    def _make_temp_db(self, tmp_path: Path) -> Path:
        cache_path = tmp_path / "code-embeddings.sqlite"
        conn = sqlite3.connect(str(cache_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cache_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS code_chunks (
              rowid_alias INTEGER PRIMARY KEY AUTOINCREMENT,
              path TEXT NOT NULL, chunk_idx INTEGER NOT NULL,
              symbol_name TEXT NOT NULL, kind TEXT NOT NULL,
              chunk_text TEXT NOT NULL, source_sha TEXT NOT NULL, cached_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS code_embeddings_json (
              chunk_rowid INTEGER PRIMARY KEY, embedding TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()
        return cache_path

    def test_register_organ_writes_row(self, tmp_path):
        """register_organ writes a code_chunks row with kind='organ'."""
        cache_path = self._make_temp_db(tmp_path)

        # Fake embed vector
        fake_vec = [0.1] * 1536

        # Build a minimal bundle mock
        fake_bundle = MagicMock()
        fake_bundle.source = "// ResourceManager source"
        fake_bundle.types = ["export interface ResourceColumn<T>"]
        fake_bundle.tests = "// test source"
        fake_bundle.wiring_snippet = "<ResourceManager />"

        import tools.noctus.dev.find_reusable_component as _frc_mod
        # bundle_component is imported inside _build_organ_chunk; patch at source module
        import tools.noctus.dev.component_bundle as _cb_mod
        original_cache = _frc_mod.CACHE_PATH
        original_bundle = _cb_mod.bundle_component
        try:
            _frc_mod.CACHE_PATH = cache_path
            _cb_mod.bundle_component = lambda *a, **kw: fake_bundle
            # Patch embed_sync only — vector_costs is imported inside the function
            # body so we let it run (it writes to a file; harmless in tests).
            with patch("tools.noctus.dev.find_reusable_component._ec.embed_sync",
                       return_value=fake_vec):
                result = register_organ("ResourceManager", repo_root=tmp_path)
        finally:
            _frc_mod.CACHE_PATH = original_cache
            _cb_mod.bundle_component = original_bundle

        assert result["ok"] is True, f"Expected ok=True, got: {result}"
        assert result["rows_written"] == 1
        assert result["name"] == "ResourceManager"

        # Verify DB row
        conn = sqlite3.connect(str(cache_path))
        row = conn.execute(
            "SELECT kind, symbol_name FROM code_chunks WHERE kind=?",
            (ORGAN_CHUNK_KIND,),
        ).fetchone()
        conn.close()
        assert row is not None, "No organ row found in DB"
        assert row[0] == ORGAN_CHUNK_KIND
        assert row[1] == "ResourceManager"


class TestRegisterOrganWorktreePathScoping:
    """Regression test for the 2026-07-16 bug (closed 2026-07-20):
    `register_organ`/`find_reusable_component` without `worktree_path`
    silently scanned the PRIMARY tree — an engineer's worktree-only organ
    returned 'bundle-not-found' even though it existed in their own tree."""

    def _make_temp_db(self, tmp_path: Path) -> Path:
        cache_path = tmp_path / "code-embeddings.sqlite"
        conn = sqlite3.connect(str(cache_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cache_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS code_chunks (
              rowid_alias INTEGER PRIMARY KEY AUTOINCREMENT,
              path TEXT NOT NULL, chunk_idx INTEGER NOT NULL,
              symbol_name TEXT NOT NULL, kind TEXT NOT NULL,
              chunk_text TEXT NOT NULL, source_sha TEXT NOT NULL, cached_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS code_embeddings_json (
              chunk_rowid INTEGER PRIMARY KEY, embedding TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()
        return cache_path

    def _make_fake_worktree(self, tmp_path: Path) -> Path:
        # `resolve_caller_root` only checks EXISTENCE of `.git` + the marker
        # file — no real git init needed.
        wt = tmp_path / "wt"
        wt.mkdir()
        (wt / ".git").write_text("gitdir: /nowhere\n")
        (wt / ".noctusai-workspace").write_text("test\n")
        return wt

    def test_register_organ_resolves_worktree_root(self, tmp_path):
        wt = self._make_fake_worktree(tmp_path)
        cache_path = self._make_temp_db(tmp_path)
        fake_bundle = MagicMock()
        fake_bundle.source = "// ResourceManager source"
        fake_bundle.types = ["export interface ResourceColumn<T>"]
        fake_bundle.tests = "// test source"
        fake_bundle.wiring_snippet = "<ResourceManager />"

        import tools.noctus.dev.find_reusable_component as _frc_mod
        import tools.noctus.dev.component_bundle as _cb_mod
        original_cache = _frc_mod.CACHE_PATH
        original_bundle = _cb_mod.bundle_component
        captured_roots = []
        try:
            _frc_mod.CACHE_PATH = cache_path

            def _fake_bundle_component(name, *a, repo_root=None, **kw):
                captured_roots.append(repo_root)
                return fake_bundle
            _cb_mod.bundle_component = _fake_bundle_component
            with patch("tools.noctus.dev.find_reusable_component._ec.embed_sync",
                       return_value=[0.1] * 1536):
                result = register_organ("ResourceManager", worktree_path=str(wt))
        finally:
            _frc_mod.CACHE_PATH = original_cache
            _cb_mod.bundle_component = original_bundle

        assert result["ok"] is True
        assert result["resolved_root"] == str(wt)
        # bundle_component (and therefore the organ source scan) was called
        # against the WORKTREE, never the primary.
        assert captured_roots == [wt]

    def test_register_organ_repo_root_wins_over_worktree_path(self, tmp_path):
        # explicit repo_root (test/back-compat override) takes priority over
        # worktree_path — never silently overridden.
        wt = self._make_fake_worktree(tmp_path)
        explicit = tmp_path / "explicit-root"
        explicit.mkdir()
        cache_path = self._make_temp_db(tmp_path)
        fake_bundle = MagicMock()
        fake_bundle.source = "// x"
        fake_bundle.types = []
        fake_bundle.tests = ""
        fake_bundle.wiring_snippet = ""

        import tools.noctus.dev.find_reusable_component as _frc_mod
        import tools.noctus.dev.component_bundle as _cb_mod
        original_cache = _frc_mod.CACHE_PATH
        original_bundle = _cb_mod.bundle_component
        try:
            _frc_mod.CACHE_PATH = cache_path
            _cb_mod.bundle_component = lambda *a, **kw: fake_bundle
            with patch("tools.noctus.dev.find_reusable_component._ec.embed_sync",
                       return_value=[0.1] * 1536):
                result = register_organ(
                    "ResourceManager", repo_root=explicit, worktree_path=str(wt),
                )
        finally:
            _frc_mod.CACHE_PATH = original_cache
            _cb_mod.bundle_component = original_bundle

        assert result["resolved_root"] == str(explicit)

    def test_register_organ_worktree_path_rejects_non_worktree_dir(self, tmp_path):
        bogus = tmp_path / "not-a-worktree"
        bogus.mkdir()
        with pytest.raises(ValueError):
            register_organ("ResourceManager", worktree_path=str(bogus))

    def test_resolve_root_shared_by_find_reusable_component(self, tmp_path):
        # `_resolve_root` is the SAME helper `find_reusable_component` uses —
        # unit-test it directly so both public entrypoints stay covered
        # without duplicating the embedding-search mock machinery.
        from tools.noctus.dev.find_reusable_component import _resolve_root
        from settings import REPO_ROOT

        wt = self._make_fake_worktree(tmp_path)
        assert _resolve_root(None, None) == REPO_ROOT          # neither given → primary
        assert _resolve_root(None, str(wt)) == wt               # worktree_path → resolved
        explicit = tmp_path / "explicit"
        explicit.mkdir()
        assert _resolve_root(explicit, str(wt)) == explicit    # repo_root wins


class TestReRegisterIsIdempotent:
    """Re-registering with the same content must skip the embed (source_sha match)."""

    def _make_temp_db_with_row(self, tmp_path: Path, sha: str) -> Path:
        cache_path = tmp_path / "code-embeddings.sqlite"
        conn = sqlite3.connect(str(cache_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cache_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS code_chunks (
              rowid_alias INTEGER PRIMARY KEY AUTOINCREMENT,
              path TEXT NOT NULL, chunk_idx INTEGER NOT NULL,
              symbol_name TEXT NOT NULL, kind TEXT NOT NULL,
              chunk_text TEXT NOT NULL, source_sha TEXT NOT NULL, cached_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS code_embeddings_json (
              chunk_rowid INTEGER PRIMARY KEY, embedding TEXT NOT NULL
            );
        """)
        conn.execute(
            "INSERT INTO code_chunks(path,chunk_idx,symbol_name,kind,chunk_text,source_sha,cached_at) "
            "VALUES (?,?,?,?,?,?,?)",
            ("seed/.../ResourceManager.tsx", 0, "ResourceManager", ORGAN_CHUNK_KIND, "chunk", sha, "2026-05-29"),
        )
        conn.commit()
        conn.close()
        return cache_path

    def test_idempotent_skip(self, tmp_path):
        """When source_sha matches, register_organ skips embed and returns status=already-current."""
        fake_bundle = MagicMock()
        fake_bundle.source = "// ResourceManager source"
        fake_bundle.types = ["export interface ResourceColumn<T>"]
        fake_bundle.tests = "// test source"
        fake_bundle.wiring_snippet = "<ResourceManager />"

        embed_call_count = []

        import tools.noctus.dev.find_reusable_component as _frc_mod
        import tools.noctus.dev.component_bundle as _cb_mod
        original_bundle = _cb_mod.bundle_component
        original_yaml = _frc_mod._find_organ_yaml

        # First, compute the sha that would be generated with the fake bundle
        try:
            _cb_mod.bundle_component = lambda *a, **kw: fake_bundle
            _frc_mod._find_organ_yaml = lambda *a, **kw: None
            chunk = _frc_mod._build_organ_chunk("ResourceManager", tmp_path)
        finally:
            _cb_mod.bundle_component = original_bundle
            _frc_mod._find_organ_yaml = original_yaml

        if chunk is None:
            pytest.skip("Could not build organ chunk — bundle_component patching needs adjustment")

        sha = _organ_source_sha(chunk)
        cache_path = self._make_temp_db_with_row(tmp_path, sha)

        original_cache = _frc_mod.CACHE_PATH
        try:
            _frc_mod.CACHE_PATH = cache_path
            _cb_mod.bundle_component = lambda *a, **kw: fake_bundle
            _frc_mod._find_organ_yaml = lambda *a, **kw: None
            with patch("tools.noctus.dev.find_reusable_component._ec.embed_sync",
                       side_effect=lambda _: embed_call_count.append(1) or [0.0] * 1536):
                result = register_organ("ResourceManager", force=False, repo_root=tmp_path)
        finally:
            _frc_mod.CACHE_PATH = original_cache
            _cb_mod.bundle_component = original_bundle
            _frc_mod._find_organ_yaml = original_yaml

        assert result["status"] == "already-current", f"Expected already-current, got: {result['status']}"
        assert result["rows_written"] == 0
        assert len(embed_call_count) == 0, "embed_sync should NOT be called when sha matches"


class TestShelfwareNotInCanonical:
    """Shelfware items must NOT appear in CANONICAL_ORGANS."""

    def test_shelfware_disjoint_from_canonical(self):
        overlap = set(CANONICAL_ORGANS) & set(SHELFWARE_ORGANS)
        assert not overlap, f"Overlap between canonical and shelfware: {overlap}"

    def test_shelfware_count_is_4(self):
        assert len(SHELFWARE_ORGANS) == 4


# ── Tests: Phase 2 organs (W2.3) ─────────────────────────────────────────────


class TestPhase2OrganSidecarsExist:
    """All 15 Phase-2 organs must have an .organ.yaml sidecar (W2.3)."""

    @pytest.mark.parametrize("name", PHASE_2_ORGANS)
    def test_organ_yaml_exists(self, name):
        p = _find_organ_yaml(name, _REPO_ROOT)
        assert p is not None, (
            f"{name}.organ.yaml not found under seed/lib/frontend/src. "
            "W2.3 must commit a sidecar for each Phase-2 organ."
        )
        assert p.exists(), f"{name}.organ.yaml path {p} does not exist"


class TestPhase2OrganYamlFields:
    """Phase-2 organ sidecars must carry all 8 knowledge fields + organ_version."""

    REQUIRED_8_FIELDS = [
        "known_facts",
        "errors_encountered",
        "drifts_surfaced",
        "alternatives_considered",
        "manual_validation_log",
        "integration_test_status",
        "e2e_test",
        "bugs_fixed_during_dev",
    ]

    @pytest.mark.parametrize("name", PHASE_2_ORGANS)
    def test_all_8_fields_present(self, name):
        p = _find_organ_yaml(name, _REPO_ROOT)
        if p is None:
            pytest.skip(f"{name}.organ.yaml not found")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        missing = [f for f in self.REQUIRED_8_FIELDS if f not in data]
        assert not missing, f"{name}.organ.yaml missing fields: {missing}"

    @pytest.mark.parametrize("name", PHASE_2_ORGANS)
    def test_organ_version_present(self, name):
        """W2.3 introduces organ_version — all Phase-2 sidecars must carry it,
        as a `MAJOR.MINOR` string.

        🔴 THIS USED TO ASSERT `== "1.0"` (fixed 2026-08-27).

        `KB § PATTERNS/architect/products-consume-canonical-organs.md` defines
        the field as `organ_version: MAJOR.MINOR` — "semver-lite". A field
        whose only legal value is its introduction value is not a version; it
        is a constant, and the first organ whose contract actually changed
        would turn its own correct bump into a CI failure.

        That is exactly what happened: `AppShell` and `Sidebar` went to `1.1`
        when the sidebar became a hover rail (new `railMode` prop, new
        `useSidebarRail` export, changed layout behaviour) and this test went
        red on the bump rather than on anything wrong.

        So the assertion now enforces what the contract actually says — present,
        and shaped `MAJOR.MINOR` — instead of freezing the value. Relaxing it to
        "any string" would have been the monkey-patch; the SHAPE is the part
        worth gating, because a sidecar carrying `organ_version: yes` (YAML's
        favourite booby-trap) or `1.0.0` is a real defect this still catches.
        """
        p = _find_organ_yaml(name, _REPO_ROOT)
        if p is None:
            pytest.skip(f"{name}.organ.yaml not found")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        assert "organ_version" in data, (
            f"{name}.organ.yaml missing organ_version field (W2.3 contract)."
        )
        version = data["organ_version"]
        assert isinstance(version, str), (
            f"{name}.organ.yaml organ_version must be a QUOTED string, got "
            f"{version!r} ({type(version).__name__}). Unquoted 1.10 parses as a "
            f"float and silently becomes 1.1."
        )
        assert re.fullmatch(r"\d+\.\d+", version), (
            f"{name}.organ.yaml organ_version must be MAJOR.MINOR (semver-lite, "
            f"KB § PATTERNS/architect/products-consume-canonical-organs.md), got "
            f"{version!r}"
        )

    @pytest.mark.parametrize("name", PHASE_2_ORGANS)
    def test_known_facts_has_at_least_2_entries(self, name):
        p = _find_organ_yaml(name, _REPO_ROOT)
        if p is None:
            pytest.skip(f"{name}.organ.yaml not found")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        facts = data.get("known_facts", [])
        assert isinstance(facts, list), f"{name}: known_facts must be a list"
        assert len(facts) >= 2, (
            f"{name}: known_facts has {len(facts)} entries; minimum 2 required."
        )

    @pytest.mark.parametrize("name", PHASE_2_HOOKS_AND_HELPERS)
    def test_hooks_and_helpers_carry_kind_field(self, name):
        """Hooks and helpers must carry kind='hook' or kind='helper' (W2.3 extension)."""
        p = _find_organ_yaml(name, _REPO_ROOT)
        if p is None:
            pytest.skip(f"{name}.organ.yaml not found")
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        assert "kind" in data, (
            f"{name}.organ.yaml missing kind field. "
            "Hooks must have kind='hook'; helpers must have kind='helper'."
        )
        assert data["kind"] in ("hook", "helper"), (
            f"{name}.organ.yaml kind={data['kind']!r}; expected 'hook' or 'helper'."
        )

    def test_phase2_count_is_15(self):
        """PHASE_2_ORGANS should list exactly 15 items."""
        assert len(PHASE_2_ORGANS) == 15, (
            f"Expected 15 Phase-2 organs, got {len(PHASE_2_ORGANS)}: {PHASE_2_ORGANS}"
        )

    def test_hooks_helpers_count_is_3(self):
        """PHASE_2_HOOKS_AND_HELPERS should list exactly 3 items."""
        assert len(PHASE_2_HOOKS_AND_HELPERS) == 3
