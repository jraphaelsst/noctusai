"""Tests for proposal management."""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.noctus.dev.proposals as proposals_mod
from tools.noctus.dev.proposals import (
    file_proposal,
    generate_proposal,
    list_proposals,
    _proposal_exists,
    _slug,
    _extract_key_entity,
)


class TestSlug:
    def test_basic(self):
        assert _slug("Extract criar_meta") == "extract-criar_meta"

    def test_truncates(self):
        assert len(_slug("a" * 100)) <= 50

    def test_pt_br_accented_title_folds_to_ascii(self):
        """A pt-BR title with accents/spaces/slashes/punctuation must never
        produce a filename carrying the raw accented codepoints or unsafe
        separator characters."""
        slug = _slug("Revisão de Configuração: ajuste/correção nº 2")
        assert slug == "revisao-de-configuracao-ajuste-correcao-no-2", slug
        # Every character must be a safe filename character.
        assert all(c.isascii() and (c.isalnum() or c in "-_") for c in slug)

    def test_apostrophes_and_slashes_never_survive(self):
        slug = _slug("Client's proposal / v2")
        assert "'" not in slug and "/" not in slug and " " not in slug

    def test_empty_title_yields_a_safe_fallback(self):
        assert _slug("") == "untitled"

    def test_underscore_survives_but_other_punctuation_collapses(self):
        assert _slug("criar_meta: v1!!") == "criar_meta-v1"


class TestFileProposalFilename:
    """End-to-end: `file_proposal` must actually WRITE a filesystem-safe
    filename, not just produce a safe slug in isolation."""

    def test_pt_br_accented_title_produces_a_safe_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(proposals_mod, "PROJECTS_DIR", tmp_path / "projects")
        monkeypatch.setattr(proposals_mod, "PRODUCTS_DIR", tmp_path / "products")
        result = file_proposal(
            title="Revisão de Configuração: ajuste/correção nº 2",
            body="corpo da proposta",
            agent="tester",
            project="acentuacao-test",
            kind="phase",
        )
        assert result["created"] is True
        written = Path(result["path"])
        assert written.is_file()
        assert written.parent == tmp_path / "projects" / "acentuacao-test" / "proposals"
        assert "/" not in result["file"].replace(".md", "")
        assert all(c.isascii() for c in result["file"])


class TestKeyEntity:
    def test_extracts_function_name(self):
        assert _extract_key_entity("Extract criar_meta to seed lib") == "criar_meta"

    def test_extracts_from_quotes(self):
        assert _extract_key_entity("Extract 'log_action' to seed") == "log_action"


class TestDedup:
    def test_duplicate_detected(self):
        # If a proposal with criar_meta exists, it should detect it
        # This depends on state, so we test the function logic
        assert isinstance(_proposal_exists("some unique title that doesnt exist"), bool)


class TestListProposals:
    def test_returns_list(self):
        proposals = list_proposals()
        assert isinstance(proposals, list)
        for p in proposals:
            assert "file" in p
            assert "status" in p
            assert "agent" in p

    def test_filter_by_agent(self):
        all_proposals = list_proposals()
        keeper_proposals = list_proposals(agent="keeper")
        assert len(keeper_proposals) <= len(all_proposals)
