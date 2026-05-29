"""Tests for noctus.dev.find_reusable_component (W4, seed-organs-cache).

Covers:
- test_find_credentials_list_returns_resource_manager: semantic query for
  "credentials list with multi-account" should match ResourceManager in top-3
  (the canonical page-scoped CRUD organ).
- test_filter_validated_excludes_shelfware: filtering by validated status
  must exclude shelfware organs.
- test_fallback_to_graph_keyword_when_embed_unreachable: when the embed
  provider raises, keyword fallback activates and returns non-empty results.
- test_find_auth_form_returns_login_form: query for "user authentication form"
  should return LoginForm in top-3.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Insert mcp/ package root so tool modules resolve.
_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))

from tools.noctus.dev.find_reusable_component import (
    CANONICAL_ORGANS,
    ORGAN_CHUNK_KIND,
    SHELFWARE_ORGANS,
    ReusableComponentMatch,
    _connect,
    _ensure_schema,
    _keyword_fallback,
    find_reusable_component,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_temp_cache(tmp_path: Path, organ_rows: list[dict]) -> Path:
    """Create a minimal code-embeddings.sqlite with organ rows for testing."""
    cache_path = tmp_path / "code-embeddings.sqlite"
    conn = sqlite3.connect(str(cache_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cache_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS code_chunks (
          rowid_alias   INTEGER PRIMARY KEY AUTOINCREMENT,
          path          TEXT NOT NULL,
          chunk_idx     INTEGER NOT NULL,
          symbol_name   TEXT NOT NULL,
          kind          TEXT NOT NULL,
          chunk_text    TEXT NOT NULL,
          source_sha    TEXT NOT NULL,
          cached_at     TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_code_chunks_path ON code_chunks(path);
        CREATE INDEX IF NOT EXISTS idx_code_chunks_kind ON code_chunks(kind);
        CREATE TABLE IF NOT EXISTS code_embeddings_json (
          chunk_rowid  INTEGER PRIMARY KEY,
          embedding    TEXT NOT NULL
        );
    """)
    import json
    for row in organ_rows:
        cur = conn.execute(
            "INSERT INTO code_chunks(path,chunk_idx,symbol_name,kind,chunk_text,source_sha,cached_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (row["path"], 0, row["name"], ORGAN_CHUNK_KIND, row["chunk_text"], row["sha"], "2026-05-29T00:00:00+00:00"),
        )
        row_id = cur.lastrowid
        # Store embedding as JSON (pure-python path — no sqlite-vec needed in tests)
        conn.execute(
            "INSERT INTO code_embeddings_json(chunk_rowid, embedding) VALUES (?, ?)",
            (row_id, json.dumps(row["vec"])),
        )
    conn.commit()
    conn.close()
    return cache_path


def _unit_vec(n: int, dim: int = 8) -> list[float]:
    """Create a unit-vector with dimension `dim` where index `n % dim` = 1.0."""
    v = [0.0] * dim
    v[n % dim] = 1.0
    return v


# ── Test fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def organ_cache(tmp_path: Path):
    """Minimal organ cache with 3 organs: ResourceManager, LoginForm, FakeModeBadge."""
    rows = [
        {
            "name": "ResourceManager",
            "path": "seed/lib/frontend/src/components/ResourceManager.tsx",
            "chunk_text": "Component: ResourceManager\ncredentials list multi-account CRUD resource management page-scoped",
            "sha": "sha_rm",
            "vec": _unit_vec(0),
        },
        {
            "name": "LoginForm",
            "path": "seed/lib/frontend/src/design-system/components/LoginForm.tsx",
            "chunk_text": "Component: LoginForm\nuser authentication form login supabase session auth",
            "sha": "sha_lf",
            "vec": _unit_vec(1),
        },
        {
            "name": "FakeModeBadge",
            "path": "seed/lib/frontend/src/components/FakeModeBadge.tsx",
            "chunk_text": "Component: FakeModeBadge\nfake mode badge indicator shelfware zero consumers",
            "sha": "sha_fmb",
            "vec": _unit_vec(2),
        },
    ]
    return _make_temp_cache(tmp_path, rows)


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestFindCredentialsListReturnsResourceManager:
    """Semantic query for 'credentials list' should return ResourceManager in top-3."""

    def test_keyword_fallback_finds_resource_manager(self, organ_cache, tmp_path):
        """Keyword fallback path: 'credentials list multi-account' → ResourceManager.

        _keyword_fallback calls _enrich_matches which calls list_components and
        bundle_component. We stub _enrich_matches to return raw rows directly.
        """
        import tools.noctus.dev.find_reusable_component as _frc_mod
        original = _frc_mod.CACHE_PATH
        original_enrich = _frc_mod._enrich_matches

        def _stub_enrich(rows, *, filter_status, top_k, root):
            return [
                ReusableComponentMatch(
                    name=r["name"], path=r.get("path"),
                    score=float(r["score"]), validation_status="validated",
                    consumers_count=3, snippet=f"<{r['name']} />",
                )
                for r in rows[:top_k]
            ]

        try:
            _frc_mod.CACHE_PATH = organ_cache
            _frc_mod._enrich_matches = _stub_enrich
            results = _keyword_fallback(
                "credentials list multi-account",
                top_k=3,
                filter_status=None,
                root=tmp_path,
            )
        finally:
            _frc_mod.CACHE_PATH = original
            _frc_mod._enrich_matches = original_enrich

        names = [r.name for r in results]
        assert "ResourceManager" in names, f"Expected ResourceManager in {names}"


class TestFindAuthFormReturnsLoginForm:
    """Query 'user authentication form login' should return LoginForm."""

    def test_keyword_fallback_finds_login_form(self, organ_cache, tmp_path):
        import tools.noctus.dev.find_reusable_component as _frc_mod
        original = _frc_mod.CACHE_PATH
        original_enrich = _frc_mod._enrich_matches

        def _stub_enrich(rows, *, filter_status, top_k, root):
            return [
                ReusableComponentMatch(
                    name=r["name"], path=r.get("path"),
                    score=float(r["score"]), validation_status="validated",
                    consumers_count=3, snippet=f"<{r['name']} />",
                )
                for r in rows[:top_k]
            ]

        try:
            _frc_mod.CACHE_PATH = organ_cache
            _frc_mod._enrich_matches = _stub_enrich
            results = _keyword_fallback(
                "user authentication form login",
                top_k=3,
                filter_status=None,
                root=tmp_path,
            )
        finally:
            _frc_mod.CACHE_PATH = original
            _frc_mod._enrich_matches = original_enrich

        names = [r.name for r in results]
        assert "LoginForm" in names, f"Expected LoginForm in {names}"


class TestFilterValidatedExcludesShelfware:
    """filter_status=['validated'] must exclude organs tagged shelfware."""

    def test_filter_excludes_shelfware(self, organ_cache, tmp_path):
        """When list_components returns mixed statuses, filter_status removes shelfware."""
        import tools.noctus.dev.find_reusable_component as _frc_mod

        # Build raw rows that would come from DB search (before enrichment filtering)
        rows = [
            {"name": "ResourceManager", "path": "seed/.../ResourceManager.tsx",
             "score": 0.9, "chunk_text": ""},
            {"name": "FakeModeBadge", "path": "seed/.../FakeModeBadge.tsx",
             "score": 0.7, "chunk_text": ""},
        ]

        # Mock list_components to return status map
        mock_entry_rm = MagicMock()
        mock_entry_rm.name = "ResourceManager"
        mock_entry_rm.validation_status = "validated"
        mock_entry_rm.consumers_count = 3

        mock_entry_fmb = MagicMock()
        mock_entry_fmb.name = "FakeModeBadge"
        mock_entry_fmb.validation_status = "shelfware"
        mock_entry_fmb.consumers_count = 0

        # list_components + bundle_component are imported inside _enrich_matches;
        # patch at the source modules they're imported from.
        import tools.noctus.dev.component_list as _cl_mod
        import tools.noctus.dev.component_bundle as _cb_mod
        original_lc = _cl_mod.list_components
        original_bc = _cb_mod.bundle_component
        try:
            _cl_mod.list_components = lambda **kw: [mock_entry_rm, mock_entry_fmb]
            _cb_mod.bundle_component = lambda *a, **kw: None
            results = _frc_mod._enrich_matches(
                rows,
                filter_status=["validated"],
                top_k=5,
                root=tmp_path,
            )
        finally:
            _cl_mod.list_components = original_lc
            _cb_mod.bundle_component = original_bc

        names = [r.name for r in results]
        assert "FakeModeBadge" not in names, "Shelfware should be excluded by filter_status=['validated']"
        assert "ResourceManager" in names, "Validated organ should be included"


class TestFallbackToKeywordWhenEmbedUnreachable:
    """When embed_sync raises (provider unreachable), keyword fallback activates."""

    def test_embed_failure_triggers_fallback(self, organ_cache, tmp_path):
        import tools.noctus.dev.find_reusable_component as _frc_mod
        original = _frc_mod.CACHE_PATH
        try:
            _frc_mod.CACHE_PATH = organ_cache

            # Patch _enrich_matches to avoid list_components/bundle_component calls
            # (they need the noc-graph which is not set up in tests).
            # We verify the keyword fallback path by checking _embedding_search raises
            # and that find_reusable_component still returns results via keyword path.
            original_enrich = _frc_mod._enrich_matches

            def _stub_enrich(rows, *, filter_status, top_k, root):
                # Return one match per row (raw, no enrichment needed for this test)
                return [
                    ReusableComponentMatch(
                        name=r["name"],
                        path=r.get("path"),
                        score=float(r["score"]),
                        validation_status="validated",
                        consumers_count=3,
                        snippet=f"<{r['name']} />",
                    )
                    for r in rows[:top_k]
                ]

            _frc_mod._enrich_matches = _stub_enrich
            try:
                with patch("tools.noctus.dev.find_reusable_component._ec.embed_sync",
                           side_effect=RuntimeError("provider unreachable")):
                    results = find_reusable_component(
                        "credentials list",
                        top_k=3,
                        repo_root=tmp_path,
                    )
            finally:
                _frc_mod._enrich_matches = original_enrich
        finally:
            _frc_mod.CACHE_PATH = original

        # Keyword fallback should have returned something (ResourceManager chunk has
        # "credentials list" in its text)
        assert isinstance(results, list), "Should return a list even on embed failure"
        names = [r.name for r in results]
        assert "ResourceManager" in names, f"Keyword fallback should find ResourceManager, got: {names}"


class TestCanonicalOrgansAndShelfware:
    """The CANONICAL_ORGANS and SHELFWARE_ORGANS constants are complete and disjoint."""

    def test_canonical_organs_count(self):
        assert len(CANONICAL_ORGANS) == 5
        assert "LoginForm" in CANONICAL_ORGANS
        assert "ForgotPasswordPage" in CANONICAL_ORGANS
        assert "AcceptInvitePage" in CANONICAL_ORGANS
        assert "ResourceManager" in CANONICAL_ORGANS
        assert "DigestCard" in CANONICAL_ORGANS

    def test_shelfware_organs_count(self):
        assert len(SHELFWARE_ORGANS) == 4
        assert "PageSkeleton" in SHELFWARE_ORGANS
        assert "LLMSpendBadge" in SHELFWARE_ORGANS
        assert "FakeModeBadge" in SHELFWARE_ORGANS
        assert "ErrorBoundary" in SHELFWARE_ORGANS

    def test_canonical_and_shelfware_disjoint(self):
        overlap = set(CANONICAL_ORGANS) & set(SHELFWARE_ORGANS)
        assert not overlap, f"Canonical and shelfware sets overlap: {overlap}"

    def test_organ_chunk_kind(self):
        assert ORGAN_CHUNK_KIND == "organ"
