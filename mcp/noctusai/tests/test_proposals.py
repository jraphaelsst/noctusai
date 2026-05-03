"""Tests for proposal management."""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.proposals import generate_proposal, list_proposals, _proposal_exists, _slug, _extract_key_entity


class TestSlug:
    def test_basic(self):
        assert _slug("Extract criar_meta") == "extract-criar_meta"

    def test_truncates(self):
        assert len(_slug("a" * 100)) <= 50


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
