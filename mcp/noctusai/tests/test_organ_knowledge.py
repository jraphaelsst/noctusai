"""Tests for organ_knowledge (W5, seed-organs-cache).

Covers the build-learn-cache loop applied to organs:
- query returns the 8 knowledge fields + metadata (read against real LoginForm sidecar)
- query of an unknown organ returns ok=False / organ-not-found
- append to a LIST field grows the list and persists
- append to the SCALAR field sets the value
- append to the OBJECT field (e2e_test) merges the dict
- unknown field / wrong-shape entry are rejected (no silent error)
- re_embed=True calls register_organ(force=True) inline; re_embed=False skips it
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# Insert mcp/ package root so tool modules resolve.
_MCP_ROOT = Path(__file__).resolve().parents[1]
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))

from tools.noctus.dev.organ_knowledge import (
    KNOWLEDGE_FIELDS,
    LIST_FIELDS,
    SCALAR_FIELDS,
    OBJECT_FIELDS,
    organ_knowledge_append,
    organ_knowledge_query,
)

try:
    import settings as _settings
    _REPO_ROOT: Path = _settings.REPO_ROOT
except Exception:
    _REPO_ROOT = Path(__file__).resolve().parents[3]


# ── Temp-repo fixture: a writable organ sidecar under the expected path ────────


@pytest.fixture()
def temp_repo() -> Path:
    """A throwaway repo root holding one writable TestOrgan.organ.yaml.

    Placed under the design-system/components dir that _find_organ_yaml scans.
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        sidecar_dir = root / "seed" / "lib" / "frontend" / "src" / "design-system" / "components"
        sidecar_dir.mkdir(parents=True)
        sidecar = sidecar_dir / "TestOrgan.organ.yaml"
        sidecar.write_text(
            yaml.safe_dump(
                {
                    "name": "TestOrgan",
                    "path": "seed/lib/frontend/src/design-system/components/TestOrgan.tsx",
                    "phase": "test",
                    "registered_at": "2026-05-29",
                    "validation_status": "emerging",
                    "known_facts": ["fact one"],
                    "errors_encountered": [],
                    "drifts_surfaced": [],
                    "alternatives_considered": [],
                    "manual_validation_log": [],
                    "integration_test_status": "unknown",
                    "e2e_test": {"path": None, "status": "pending", "last_run": None, "runs_in_ci": False},
                    "bugs_fixed_during_dev": [],
                },
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        yield root


def _reload(root: Path) -> dict:
    p = root / "seed" / "lib" / "frontend" / "src" / "design-system" / "components" / "TestOrgan.organ.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))


# ── Taxonomy invariants ────────────────────────────────────────────────────────


def test_eight_knowledge_fields():
    assert len(KNOWLEDGE_FIELDS) == 8
    assert KNOWLEDGE_FIELDS == LIST_FIELDS | SCALAR_FIELDS | OBJECT_FIELDS


# ── Query (read-only against the real LoginForm sidecar) ───────────────────────


def test_query_returns_all_eight_fields():
    result = organ_knowledge_query("LoginForm", repo_root=_REPO_ROOT)
    assert result["ok"] is True
    assert result["name"] == "LoginForm"
    for field in KNOWLEDGE_FIELDS:
        assert field in result, f"query missing knowledge field {field!r}"
    # LoginForm carries known_facts in its sidecar.
    assert isinstance(result["known_facts"], list)
    assert len(result["known_facts"]) >= 1


def test_query_unknown_organ():
    result = organ_knowledge_query("NoSuchOrgan", repo_root=_REPO_ROOT)
    assert result["ok"] is False
    assert result["status"] == "organ-not-found"


# ── Append: list field ─────────────────────────────────────────────────────────


def test_append_list_field_grows_and_persists(temp_repo):
    result = organ_knowledge_append(
        "TestOrgan", "known_facts", "fact two", re_embed=False, repo_root=temp_repo
    )
    assert result["ok"] is True
    assert result["action"] == "appended"
    assert result["re_embedded"] is False
    data = _reload(temp_repo)
    assert data["known_facts"] == ["fact one", "fact two"]


def test_append_manual_validation_log_dict(temp_repo):
    entry = {"date": "2026-05-29", "validator": "rapha", "finding": "works", "status": "pass"}
    result = organ_knowledge_append(
        "TestOrgan", "manual_validation_log", entry, re_embed=False, repo_root=temp_repo
    )
    assert result["ok"] is True
    data = _reload(temp_repo)
    assert data["manual_validation_log"] == [entry]


# ── Append: scalar field ────────────────────────────────────────────────────────


def test_append_scalar_field_sets(temp_repo):
    result = organ_knowledge_append(
        "TestOrgan", "integration_test_status", "passing (12/12)", re_embed=False, repo_root=temp_repo
    )
    assert result["ok"] is True
    assert result["action"] == "set"
    data = _reload(temp_repo)
    assert data["integration_test_status"] == "passing (12/12)"


# ── Append: object field ─────────────────────────────────────────────────────────


def test_append_object_field_merges(temp_repo):
    result = organ_knowledge_append(
        "TestOrgan",
        "e2e_test",
        {"path": "src/x.test.tsx", "status": "passing", "runs_in_ci": True},
        re_embed=False,
        repo_root=temp_repo,
    )
    assert result["ok"] is True
    assert result["action"] == "merged"
    data = _reload(temp_repo)
    # Merge preserves the untouched key (last_run) while updating the rest.
    assert data["e2e_test"]["path"] == "src/x.test.tsx"
    assert data["e2e_test"]["status"] == "passing"
    assert data["e2e_test"]["runs_in_ci"] is True
    assert data["e2e_test"]["last_run"] is None


def test_append_object_field_needs_dict(temp_repo):
    result = organ_knowledge_append(
        "TestOrgan", "e2e_test", "not-a-dict", re_embed=False, repo_root=temp_repo
    )
    assert result["ok"] is False
    assert "object-field-needs-dict" in result["status"]


# ── Guards: no silent errors ─────────────────────────────────────────────────────


def test_append_unknown_field_rejected(temp_repo):
    result = organ_knowledge_append(
        "TestOrgan", "made_up_field", "x", re_embed=False, repo_root=temp_repo
    )
    assert result["ok"] is False
    assert "unknown-field" in result["status"]


def test_append_unknown_organ_rejected(temp_repo):
    result = organ_knowledge_append(
        "NoSuchOrgan", "known_facts", "x", re_embed=False, repo_root=temp_repo
    )
    assert result["ok"] is False
    assert result["status"] == "organ-not-found"


# ── Re-embed contract (§3b W5) ───────────────────────────────────────────────────


def test_re_embed_calls_register_organ_force(temp_repo):
    with patch("tools.noctus.dev.organ_knowledge.register_organ") as mock_ro:
        mock_ro.return_value = {"ok": True, "status": "registered", "source_sha": "abc123", "rows_written": 1}
        result = organ_knowledge_append(
            "TestOrgan", "known_facts", "fact three", re_embed=True, repo_root=temp_repo
        )
    assert result["ok"] is True
    assert result["re_embedded"] is True
    assert result["source_sha"] == "abc123"
    mock_ro.assert_called_once()
    _, kwargs = mock_ro.call_args
    assert kwargs.get("force") is True


def test_no_re_embed_skips_register_organ(temp_repo):
    with patch("tools.noctus.dev.organ_knowledge.register_organ") as mock_ro:
        result = organ_knowledge_append(
            "TestOrgan", "known_facts", "fact four", re_embed=False, repo_root=temp_repo
        )
    assert result["ok"] is True
    assert result["re_embedded"] is False
    mock_ro.assert_not_called()
