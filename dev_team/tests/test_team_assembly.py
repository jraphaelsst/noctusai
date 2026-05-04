"""Engineer-E checkpoint — Team assembly + sub-team rosters + routing.

Covers:
    1. ``build_team("default")`` returns a Team with 11 members
       (Leader + 10 specialists).
    2. Each sub-team has the correct roster.
    3. ``recommend_route`` heuristic — trivial signals → "direct",
       multi-domain / design signals → "team".
    4. Each specialist factory accepts a config dict and returns the
       agno Agent built by ``base.build_agent``.
    5. Smoke: build the full team without raising.

Mocking strategy
----------------
agno isn't required to be installed for the test suite to run (the
production import is local inside :func:`build_agent` /
:func:`build_team` for exactly this reason). We stub the two agno
classes the factories touch (``Agent`` + ``Team``) by injecting
fake modules into ``sys.modules`` BEFORE the local imports fire,
plus a fake ``anthropic.Claude`` model class via the same path.

Per ``CLAUDE.md §1`` *No workarounds — and no monkey-patching, in
production OR tests*: the carve-out for ``unittest.mock`` against
**external integrations** (LLM SDKs, agno) is explicit. agno is a
third-party framework; mocking ``agno.agent.Agent`` /
``agno.team.Team`` / ``agno.models.anthropic.Claude`` falls inside
that carve-out.

Charters are NOT mocked — the test fixture writes minimal real
charter files (a one-line shared.md + one-line per-role .md) into
the actual ``dev_team/src/dev_team/charters/`` directory inside a
``tmp_path`` copy so :func:`load_charter` exercises its real code
path. This avoids monkey-patching our own ``load_charter``, which
would violate the "no self-monkeypatching" rule.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest


# --------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------- #

ROLE_NAMES = (
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


class _FakeAgent:
    """Stand-in for ``agno.agent.Agent``.

    Records the kwargs it was constructed with so tests can assert
    on ``name``, ``model``, ``tools``, ``instructions``.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.name = kwargs.get("name")
        self.model = kwargs.get("model")
        self.instructions = kwargs.get("instructions")
        self.tools = kwargs.get("tools", [])

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return f"_FakeAgent(name={self.name!r})"


class _FakeTeam:
    """Stand-in for ``agno.team.Team``.

    Records ``name``, ``members``, ``mode`` so tests can assert on
    composition without depending on real agno installation.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.name = kwargs.get("name")
        self.members = list(kwargs.get("members", []))
        self.mode = kwargs.get("mode")

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return f"_FakeTeam(name={self.name!r}, members={len(self.members)}, mode={self.mode!r})"


class _FakeClaude:
    """Stand-in for ``agno.models.anthropic.Claude``."""

    def __init__(self, id: str | None = None, **kwargs: Any) -> None:
        self.id = id
        self.kwargs = kwargs

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return f"_FakeClaude(id={self.id!r})"


@pytest.fixture
def fake_agno(monkeypatch):
    """Inject fake agno modules into sys.modules so local imports
    inside ``build_agent`` / ``build_team`` resolve to our stand-ins.

    Per CLAUDE.md the carve-out for ``unittest.mock`` against external
    integrations applies — agno is a third-party framework. We use
    monkeypatch to scope the injection to the test (auto-restored at
    teardown).
    """
    agno = types.ModuleType("agno")
    agno_agent = types.ModuleType("agno.agent")
    agno_team = types.ModuleType("agno.team")
    agno_models = types.ModuleType("agno.models")
    agno_models_anthropic = types.ModuleType("agno.models.anthropic")

    agno_agent.Agent = _FakeAgent  # type: ignore[attr-defined]
    agno_team.Team = _FakeTeam  # type: ignore[attr-defined]
    agno_models_anthropic.Claude = _FakeClaude  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "agno", agno)
    monkeypatch.setitem(sys.modules, "agno.agent", agno_agent)
    monkeypatch.setitem(sys.modules, "agno.team", agno_team)
    monkeypatch.setitem(sys.modules, "agno.models", agno_models)
    monkeypatch.setitem(sys.modules, "agno.models.anthropic", agno_models_anthropic)

    yield {"Agent": _FakeAgent, "Team": _FakeTeam, "Claude": _FakeClaude}


@pytest.fixture
def fake_charters(monkeypatch, tmp_path):
    """Write minimal real charter files into a tmp dir and point
    :mod:`dev_team.agents.base` at it via its module-level constants.

    We re-bind ``CHARTER_DIR`` + ``SHARED_CHARTER_FILE`` (data, not
    behaviour). The :func:`load_charter` / :func:`load_shared_charter`
    functions are NOT touched — they exercise their real code path
    against this temp directory.
    """
    from dev_team.agents import base

    charter_dir = tmp_path / "charters"
    charter_dir.mkdir()
    (charter_dir / "shared.md").write_text(
        "# Shared charter (test fixture)\n\nMinimal stub for engineer-E tests.\n",
        encoding="utf-8",
    )
    for role in ROLE_NAMES:
        (charter_dir / f"{role}.md").write_text(
            f"# {role} role charter (test fixture)\n\nMinimal stub.\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(base, "CHARTER_DIR", charter_dir)
    monkeypatch.setattr(base, "SHARED_CHARTER_FILE", charter_dir / "shared.md")
    yield charter_dir


@pytest.fixture
def loaded_config():
    from dev_team.configs import load_config

    return load_config("default")


# --------------------------------------------------------------------- #
# Specialist-factory tests
# --------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "factory_module, factory_name, expected_role",
    [
        ("dev_team.agents.product_manager", "build_product_manager", "product_manager"),
        ("dev_team.agents.ux_designer", "build_ux_designer", "ux_designer"),
        (
            "dev_team.agents.solution_architect",
            "build_solution_architect",
            "solution_architect",
        ),
        (
            "dev_team.agents.backend_engineer",
            "build_backend_engineer",
            "backend_engineer",
        ),
        (
            "dev_team.agents.frontend_engineer",
            "build_frontend_engineer",
            "frontend_engineer",
        ),
        (
            "dev_team.agents.devops_engineer",
            "build_devops_engineer",
            "devops_engineer",
        ),
        (
            "dev_team.agents.security_engineer",
            "build_security_engineer",
            "security_engineer",
        ),
        ("dev_team.agents.qa_engineer", "build_qa_engineer", "qa_engineer"),
        ("dev_team.agents.code_reviewer", "build_code_reviewer", "code_reviewer"),
        (
            "dev_team.agents.technical_writer",
            "build_technical_writer",
            "technical_writer",
        ),
    ],
)
def test_specialist_factories_return_agent(
    fake_agno, fake_charters, loaded_config, factory_module, factory_name, expected_role
):
    """Every specialist factory accepts the config dict and returns
    an Agent named for the role with a Claude model attached."""
    import importlib

    module = importlib.import_module(factory_module)
    factory = getattr(module, factory_name)

    agent = factory(loaded_config)

    assert isinstance(agent, _FakeAgent), (
        f"{factory_name} should return an agno.agent.Agent (mocked as _FakeAgent); "
        f"got {type(agent).__name__}"
    )
    assert agent.name == expected_role, (
        f"{factory_name} should construct Agent(name={expected_role!r}); "
        f"got name={agent.name!r}"
    )
    assert isinstance(agent.model, _FakeClaude), (
        f"{factory_name} should attach a Claude model; got {type(agent.model).__name__}"
    )
    assert agent.instructions, (
        f"{factory_name} should compose layer-1 + layer-2 instructions; got empty"
    )


def test_build_leader_returns_leader_agent(fake_agno, fake_charters, loaded_config):
    """The Leader factory builds an Agent with name='leader'."""
    from dev_team.leader import build_leader

    leader = build_leader(loaded_config)

    assert isinstance(leader, _FakeAgent)
    assert leader.name == "leader"
    assert isinstance(leader.model, _FakeClaude)


# --------------------------------------------------------------------- #
# Top-level team assembly
# --------------------------------------------------------------------- #


def test_build_team_returns_eleven_members(fake_agno, fake_charters):
    """build_team('default') returns a coordinate-mode Team with 11
    members: Leader + 10 specialists."""
    from dev_team.team import build_team

    team = build_team("default")

    assert isinstance(team, _FakeTeam), (
        f"build_team must return an agno.team.Team; got {type(team).__name__}"
    )
    assert team.mode == "coordinate", (
        f"dev_team must be coordinate-mode per design-reference.md §1.2; got {team.mode!r}"
    )
    assert len(team.members) == 11, (
        f"dev_team must have 11 members (Leader + 10 specialists); got {len(team.members)}"
    )

    member_names = [m.name for m in team.members]
    assert member_names[0] == "leader", (
        "Leader must be the first member per design-reference.md §1.2 / §2.1"
    )
    for role in ROLE_NAMES[1:]:
        assert role in member_names, (
            f"Specialist {role!r} missing from dev_team roster; have {member_names}"
        )


def test_build_team_smoke_does_not_raise(fake_agno, fake_charters):
    """Smoke: build the full team end-to-end without raising."""
    from dev_team.team import build_team

    team = build_team("default")
    assert team is not None


# --------------------------------------------------------------------- #
# Sub-team rosters
# --------------------------------------------------------------------- #


def test_design_review_team_roster(fake_agno, fake_charters, loaded_config):
    """design_review_team: Architect (lead) + Backend + Frontend +
    DevOps + Security, mode=collaborate."""
    from dev_team.teams.design_review_team import build_design_review_team

    sub = build_design_review_team(loaded_config)

    assert isinstance(sub, _FakeTeam)
    assert sub.name == "design_review_team"
    assert sub.mode == "collaborate", (
        "Sub-teams must be collaborate-mode per design-reference.md §1.2"
    )

    names = [m.name for m in sub.members]
    assert names[0] == "solution_architect", (
        "Architect must be the lead (first member) per design-reference.md §2.4"
    )
    assert set(names) == {
        "solution_architect",
        "backend_engineer",
        "frontend_engineer",
        "devops_engineer",
        "security_engineer",
    }, f"design_review_team roster mismatch; got {names}"


def test_code_review_team_roster(fake_agno, fake_charters, loaded_config):
    """code_review_team: Code Reviewer (lead) + Security + QA,
    mode=collaborate."""
    from dev_team.teams.code_review_team import build_code_review_team

    sub = build_code_review_team(loaded_config)

    assert isinstance(sub, _FakeTeam)
    assert sub.name == "code_review_team"
    assert sub.mode == "collaborate"

    names = [m.name for m in sub.members]
    assert names[0] == "code_reviewer", (
        "Code Reviewer must lead per design-reference.md §2.10"
    )
    assert set(names) == {
        "code_reviewer",
        "security_engineer",
        "qa_engineer",
    }, f"code_review_team roster mismatch; got {names}"


def test_incident_response_team_roster(fake_agno, fake_charters, loaded_config):
    """incident_response_team: DevOps (lead) + Security + Backend +
    Frontend (situational), mode=collaborate."""
    from dev_team.teams.incident_response_team import build_incident_response_team

    sub = build_incident_response_team(loaded_config)

    assert isinstance(sub, _FakeTeam)
    assert sub.name == "incident_response_team"
    assert sub.mode == "collaborate"

    names = [m.name for m in sub.members]
    assert names[0] == "devops_engineer", (
        "DevOps must lead incident_response_team per design-reference.md §2.7 / §10"
    )
    assert set(names) == {
        "devops_engineer",
        "security_engineer",
        "backend_engineer",
        "frontend_engineer",
    }, f"incident_response_team roster mismatch; got {names}"


# --------------------------------------------------------------------- #
# Routing heuristic
# --------------------------------------------------------------------- #


def test_recommend_route_trivial_returns_direct():
    from dev_team.team import recommend_route

    decision = recommend_route("rename foo to bar")
    assert decision["recommended"] == "direct"
    assert "rename" in decision["matched"]
    assert "rationale" in decision


def test_recommend_route_multidomain_returns_team():
    from dev_team.team import recommend_route

    decision = recommend_route("design and ship a new product")
    assert decision["recommended"] == "team"
    assert decision["matched"], "team route should expose matched signals"
    assert "rationale" in decision


def test_recommend_route_design_mentions_design_review_team():
    """When 'design' / 'architect' signals fire, the rationale should
    name design_review_team so the Leader can route directly there."""
    from dev_team.team import recommend_route

    decision = recommend_route("design review for a new feature")
    assert decision["recommended"] == "team"
    assert "design_review_team" in decision["rationale"]


def test_recommend_route_typo_is_direct():
    from dev_team.team import recommend_route

    decision = recommend_route("fix a typo in the README")
    assert decision["recommended"] == "direct"


def test_recommend_route_one_line_is_direct():
    from dev_team.team import recommend_route

    decision = recommend_route("apply a one-line bug fix to the parser")
    assert decision["recommended"] == "direct"


def test_recommend_route_security_is_team():
    from dev_team.team import recommend_route

    decision = recommend_route("security audit of the auth flow")
    assert decision["recommended"] == "team"


def test_recommend_route_incident_is_team():
    from dev_team.team import recommend_route

    decision = recommend_route("production incident: 500s on /api/orders")
    assert decision["recommended"] == "team"


def test_recommend_route_default_is_direct():
    """Single-domain task with no matched signals defaults to direct."""
    from dev_team.team import recommend_route

    decision = recommend_route("update the banner copy")
    assert decision["recommended"] == "direct"
    assert decision["matched"] == []


def test_recommend_route_rejects_non_string():
    from dev_team.team import recommend_route

    with pytest.raises(TypeError):
        recommend_route(None)  # type: ignore[arg-type]


# --------------------------------------------------------------------- #
# Sub-team factories accept config dict
# --------------------------------------------------------------------- #


def test_subteam_factories_accept_config(fake_agno, fake_charters, loaded_config):
    """All three sub-team factories accept the config dict and return Team."""
    from dev_team.teams.code_review_team import build_code_review_team
    from dev_team.teams.design_review_team import build_design_review_team
    from dev_team.teams.incident_response_team import build_incident_response_team

    for factory in (
        build_design_review_team,
        build_code_review_team,
        build_incident_response_team,
    ):
        team = factory(loaded_config)
        assert isinstance(team, _FakeTeam)
        assert team.mode == "collaborate"
        assert team.members, f"{factory.__name__} produced empty member list"
