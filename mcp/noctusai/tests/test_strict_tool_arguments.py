"""A tool call carrying an argument the tool does not declare must be REFUSED.

🔴 THE INCIDENT THIS PINS (2026-09-19)
--------------------------------------
An agent called ``noctus.dev.task_branch`` as
``{"payload": {"action": "start", "slug": "one-ops-agents", "confirm": true}}``
— wrongly generalising the ``payload`` shape that the ``noctus.team.*`` tools
genuinely use — and got back::

    {"ok": true, "action": "status", "slug": null, ... 32 active worktrees ...}

Nothing was created. Nothing complained. The call was reported as a defect in
the MCP wrapper and a keeper was nearly written for a bug that did not exist;
the real fault was that **unknown arguments are silently discarded**.

Three facts make this specific failure severe, and all three are pinned below:

1. FastMCP registers its handler with ``validate_input=False``
   (``mcp/server/fastmcp/server.py`` ``_setup_handlers``), so the lowlevel
   server never validates arguments against the advertised ``inputSchema``.
2. Pydantic then drops undeclared fields, so EVERY declared parameter falls
   back to its default.
3. ``noctus.dev.task_branch``'s default ``action`` is ``"status"`` — read-only,
   ``ok: true``, and visually indistinguishable from a real result. The same
   shape applies to any tool whose default action is a benign no-op.

``server.install_strict_tool_arguments`` closes this by refusing the call.
These tests pin the properties that fix depends on — in particular that the
enforcement sits on the LIVE path, since the two obvious places to put it
both silently miss.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import build_server, install_strict_tool_arguments  # noqa: E402

TOOL = "noctus.dev.task_branch"


@pytest.fixture(scope="module")
def server():
    return build_server()


def _call(server, name: str, arguments: dict):
    return asyncio.run(server.call_tool(name, arguments))


class TestUnknownArgumentsAreRefused:
    def test_the_exact_call_from_the_incident_is_refused(self, server):
        """``payload={...}`` must raise, not return a defaulted status result."""
        with pytest.raises(Exception) as exc:
            _call(server, TOOL, {"payload": {"action": "start", "slug": "x", "confirm": True}})
        assert "payload" in str(exc.value)

    def test_refusal_names_the_unknown_arg_and_the_valid_ones(self, server):
        """A refusal the caller cannot act on just moves the confusion."""
        with pytest.raises(Exception) as exc:
            _call(server, TOOL, {"actoin": "start"})
        message = str(exc.value)
        assert "actoin" in message, "must name what was wrong"
        assert "action" in message, "must list what is accepted"

    def test_a_typo_never_degrades_into_a_read_only_success(self, server):
        """The whole point: a bad call must not look like `ok: true`."""
        with pytest.raises(Exception):
            _call(server, TOOL, {"slugg": "one-ops-agents", "action": "start"})


class TestLegitimateCallsStillWork:
    def test_declared_args_are_accepted(self, server):
        result = _call(server, TOOL, {"action": "status"})
        assert '"action": "status"' in str(result)

    def test_omitting_optional_args_still_uses_defaults(self, server):
        """Strictness is about UNKNOWN keys, never about requiring every key."""
        result = _call(server, TOOL, {})
        assert '"ok": true' in str(result)

    def test_a_pydantic_payload_tool_still_accepts_its_payload(self, server):
        """``noctus.team.*`` genuinely declares ``payload`` — it must not break."""
        registry = install_strict_tool_arguments(server)
        team = {n: a for n, a in registry.items() if n.startswith("noctus.team.")}
        assert team, "expected noctus.team.* tools to be registered"
        assert any("payload" in allowed for allowed in team.values()), (
            "team tools declare a pydantic `payload` input; strictness must "
            "accept it rather than reject the shape wholesale"
        )


class TestEnforcementIsOnTheLivePath:
    """Both obvious enforcement points silently miss. These pin the right one."""

    def test_schema_additional_properties_is_not_the_gate(self, server):
        """Measured 2026-09-19: FastMCP does NOT enforce additionalProperties.

        It is set as a hint for clients that validate, so it must be PRESENT —
        but a test asserting only that would be green while the server still
        accepted anything. The refusal tests above are the real proof.
        """
        tool = server._tool_manager.get_tool(TOOL)
        assert tool.parameters.get("additionalProperties") is False

    def test_wrapping_fastmcp_call_tool_would_have_missed(self, server):
        """``_setup_handlers`` binds ``self.call_tool`` at construction.

        So patching ``server.call_tool`` after build leaves the live stdio path
        holding the ORIGINAL bound method. Enforcement therefore lives on
        ``_tool_manager.call_tool``, which ``FastMCP.call_tool`` resolves per
        call. This pins the assumption so an upstream refactor that inlines the
        manager lookup fails here rather than silently disarming the gate.
        """
        import inspect

        source = inspect.getsource(type(server).call_tool)
        assert "_tool_manager.call_tool" in source, (
            "FastMCP.call_tool no longer delegates to the tool manager — the "
            "strict-argument gate is no longer on the live request path"
        )

    def test_every_registered_tool_is_covered(self, server):
        """A tool registered after the installer runs would be unguarded."""
        registry = install_strict_tool_arguments(server)
        registered = {t.name for t in server._tool_manager.list_tools()}
        assert registered, "expected a non-empty tool registry"
        assert registered <= set(registry), (
            f"tools missing from the strict-argument registry: "
            f"{sorted(registered - set(registry))}"
        )


class TestMcpToolsRejectUnknownArgs:
    """Regression test for the `check_mcp_tools_reject_unknown_args` detector.

    Named to match the detector so `check_detector_has_regression_test` finds it
    (it scans `tests/` for `class Test<detector-body>`). That keeper caught this
    file on its first full run — the detector had shipped without a discoverable
    regression test — which is the meta-gate working as designed. Renaming was
    the fix; an entry in `_DETECTOR_TEST_OVERRIDES` would have been suppressing
    a gate rather than satisfying it.

    Pins that the backstop actually bites.

    A keeper that only ever returns `[]` is indistinguishable from one that
    works. Each case below mutates `server.py` in a way that would REALLY
    disarm the gate, and asserts the keeper catches it.
    """

    @staticmethod
    def _run_against(source: str) -> list[dict]:
        import tempfile
        from pathlib import Path as _Path

        sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
        from tools.noctus.dev.compliance import check_mcp_tools_reject_unknown_args

        with tempfile.TemporaryDirectory() as tmp:
            root = _Path(tmp)
            (root / "mcp/noctusai").mkdir(parents=True)
            (root / "mcp/noctusai/server.py").write_text(source, encoding="utf-8")
            return check_mcp_tools_reject_unknown_args(repo_root=root)

    @property
    def _real_source(self) -> str:
        return (Path(__file__).resolve().parent.parent / "server.py").read_text(encoding="utf-8")

    def test_the_real_server_passes(self):
        assert self._run_against(self._real_source) == []

    def test_catches_the_installer_call_being_removed(self):
        mutated = self._real_source.replace("    install_strict_tool_arguments(server)\n", "")
        issues = self._run_against(mutated)
        assert issues, "removing the call must be caught"
        assert "never calls" in issues[0]["issue"]

    def test_catches_the_installer_being_deleted(self):
        mutated = self._real_source.replace(
            "def install_strict_tool_arguments(", "def _disabled_installer("
        )
        issues = self._run_against(mutated)
        assert issues, "deleting the installer must be caught"

    def test_catches_installation_before_register_all(self):
        """Installing first builds an EMPTY registry — wired, but guarding nothing."""
        mutated = self._real_source.replace(
            "    register_all(server)\n    # AFTER register_all",
            "    install_strict_tool_arguments(server)\n    register_all(server)\n    # AFTER register_all",
        ).replace("    install_strict_tool_arguments(server)\n    return server", "    return server")
        issues = self._run_against(mutated)
        assert issues, "ordering must be enforced, not just presence"
        assert "BEFORE" in issues[0]["issue"]
