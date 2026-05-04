"""B2 Engineer-A test module — verify the 12 charter files + loaders.

Run from repo root:
    PYTHONPATH=dev_team/src venv/bin/python -m pytest dev_team/tests/test_charters.py -v

Covers:
- Existence of all 12 charter files (1 shared + 11 role).
- Minimum length floors (shared >=1000 chars, each role >=800 chars).
- Loader contracts (load_shared_charter / load_charter / compose_instructions).
- Compose joins both layers with the '---' divider.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dev_team.agents.base import (
    CHARTER_DIR,
    SHARED_CHARTER_FILE,
    AgentName,
    compose_instructions,
    load_charter,
    load_shared_charter,
)


# The 11 role names that must each have a charter file.
ROLE_NAMES: tuple[AgentName, ...] = (
    "leader",
    "product_manager",
    "ux_designer",
    "solution_architect",
    "backend_engineer",
    "frontend_engineer",
    "devops_engineer",
    "security_engineer",
    "qa_engineer",
    "code_reviewer",
    "technical_writer",
)


def test_all_12_charter_files_exist():
    """1 shared + 11 role charters = 12 markdown files in charters/."""
    assert SHARED_CHARTER_FILE.exists(), (
        f"missing shared charter at {SHARED_CHARTER_FILE}"
    )
    missing: list[str] = []
    for role in ROLE_NAMES:
        path = CHARTER_DIR / f"{role}.md"
        if not path.exists():
            missing.append(role)
    assert not missing, f"missing role charters: {missing}"


def test_shared_charter_min_length():
    """Shared charter floor — must cover the universal rules in detail."""
    body = load_shared_charter()
    assert isinstance(body, str)
    assert len(body) >= 1000, (
        f"shared charter too short ({len(body)} chars); target ~1500 tokens "
        "covering all CLAUDE.md §1 universal rules."
    )


@pytest.mark.parametrize("role", ROLE_NAMES)
def test_each_role_charter_min_length(role: AgentName):
    """Each role charter floor — must be substantive enough to instruct an agent."""
    body = load_charter(role)
    assert isinstance(body, str)
    assert len(body) >= 800, (
        f"role charter for {role!r} too short ({len(body)} chars); "
        "target ~1000-1500 tokens covering mission/responsibilities/"
        "outputs/inputs/handoffs/sub-team/tools/boundary/behavioral specifics."
    )


def test_load_shared_charter_returns_string():
    body = load_shared_charter()
    assert isinstance(body, str)
    assert body.strip(), "shared charter body is empty/whitespace-only"


@pytest.mark.parametrize("role", ROLE_NAMES)
def test_load_charter_for_each_role(role: AgentName):
    """load_charter returns the role's markdown body (not silently empty)."""
    body = load_charter(role)
    assert isinstance(body, str)
    assert body.strip(), f"role charter for {role!r} is empty/whitespace-only"


@pytest.mark.parametrize("role", ROLE_NAMES)
def test_compose_instructions_includes_both_layers(role: AgentName):
    """Composed instructions = shared + '---' divider + role body."""
    composed = compose_instructions(role)
    assert isinstance(composed, str)
    # The composer joins via '\n\n---\n\n' per agents/base.py::compose_instructions.
    assert "---" in composed, (
        f"compose_instructions for {role!r} missing the '---' divider; "
        "shared and role layers must be joined."
    )
    shared = load_shared_charter()
    role_body = load_charter(role)
    # Both layer bodies appear in the composition.
    assert shared in composed, "shared charter body not found in composition"
    assert role_body in composed, f"role body for {role!r} not found in composition"
    # Sanity: the composition is at least the sum of the two bodies.
    assert len(composed) >= len(shared) + len(role_body)


def test_charters_dir_contains_no_stray_md_files():
    """Only the 12 expected .md files; no orphan drafts in charters/."""
    expected = {"shared.md"} | {f"{role}.md" for role in ROLE_NAMES}
    found = {p.name for p in CHARTER_DIR.glob("*.md")}
    stray = found - expected
    assert not stray, f"unexpected .md files in charters/: {stray}"
    missing = expected - found
    assert not missing, f"expected .md files missing from charters/: {missing}"


def test_shared_charter_mentions_core_rules():
    """Sanity: shared charter substance check — the universal rules are present.

    Looser than a per-rule asserter; just verifies key phrases land so the
    charter doesn't drift into a stub."""
    body = load_shared_charter().lower()
    # Sample of universal rules; not exhaustive (those are the rule bodies).
    must_appear = (
        "seed first",
        "no quick fixes",
        "ast-first",
        "recurrence rule",
        "three-way sync",
        "no silent errors",
        "replication-to-seed",
        "mcp",
    )
    missing = [phrase for phrase in must_appear if phrase not in body]
    assert not missing, (
        f"shared charter missing references to: {missing}; "
        "rephrase from CLAUDE.md §1 — substance verbatim."
    )


def test_role_charter_has_section_headers():
    """Each role charter has the standard 9 sections per the brief.

    Looser than a strict header parse; just verifies the canonical section
    titles appear so engineers down the line have predictable structure."""
    expected_section_keywords = (
        "mission",
        "responsibilities",
        "outputs",
        "inputs",
        "handoffs",
        "tools",
        "boundary",
    )
    failures: dict[str, list[str]] = {}
    for role in ROLE_NAMES:
        body = load_charter(role).lower()
        missing = [k for k in expected_section_keywords if k not in body]
        if missing:
            failures[role] = missing
    assert not failures, f"role charters missing canonical sections: {failures}"
