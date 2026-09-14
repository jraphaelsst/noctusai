"""``ClaudeAgentSdkRuntime`` — the real :class:`~app.runtime.types.AgentRuntime`,
launching Julia via the Claude Agent SDK (contract §E.5, SEC-A/SEC-C).

Two pieces are kept SEPARATELY TESTABLE, per the G2 brief:

- :func:`build_launch_options` — a pure factory asserting every §E.5 field,
  callable WITHOUT spawning the CLI (it returns a
  ``claude_agent_sdk.ClaudeAgentOptions``, nothing more).
- :class:`ClaudeAgentSdkRuntime` — wires that factory to a real
  ``ClaudeSDKClient`` and maps the SDK's message stream to the exact E.3
  events (contract §E.9's guarantees).

**Why a queue, not a plain generator.** ``can_use_tool`` is invoked by the
SDK's OWN internal reader task while ``run_turn``'s consumer loop is
paused awaiting the CLI's next message (which will not arrive until the
permission decision is made — the tool cannot execute until then). If
``approval.requested``/``approval.resolved`` were only derived from SDK
messages, they would not reach subscribers until AFTER the whole tool
call finished — defeating the point of a real-time approval card. So
``can_use_tool`` pushes those two events directly onto a per-turn
``asyncio.Queue`` the moment they happen; a background task pumps the SDK
message stream (translated via :meth:`_TurnDriver.translate`) onto the
SAME queue; ``run_turn`` drains the merged queue and yields in arrival
order — that order is what gives contract §E.9's "escrita tools follow a
fixed sequence" guarantee its actual real-time meaning.

``claude_agent_sdk`` is imported at module scope deliberately (this module
is ONLY imported by :func:`app.runtime.get_agent_runtime` when the real
runtime is selected — see ``app/runtime/__init__.py`` — so tests that only
exercise :class:`~app.runtime.fake_runtime.FakeAgentRuntime` never pay for
it). The launch-options test in ``tests/runtime/`` DOES import this
module directly (it asserts the options shape without spawning a
process), so the package must still be installed wherever tests run.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from app.runtime import gate
from app.runtime.academia_api import AcademiaApi, AcademiaNotFoundError
from app.runtime.tools import build_academia_tools
from app.runtime.types import AgentEvent, AgentSpec, ApprovalBroker, TurnContext

logger = logging.getLogger(__name__)

__all__ = ["build_launch_options", "ClaudeAgentSdkRuntime"]

#: Contract §E.5 — the `env -i` wrapper's location inside the image.
DEFAULT_CLI_PATH = "/app/bin/julia-cli-exec"

#: Contract §E.5 base built-in tool set. MCP academia proxies arrive via
#: `mcp_servers`, not this list.
BASE_TOOLS: tuple[str, ...] = ("WebSearch", "Skill")

#: Contract §E.5 defence-in-depth blocklist — every dangerous built-in.
DISALLOWED_TOOLS: tuple[str, ...] = (
    "Bash",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Read",
    "Grep",
    "Glob",
    "Task",
    "WebFetch",
)

_ACADEMIA_AUD = "academia-de-reciclagem"

# Sentinel telling run_turn's queue-drain loop the message pump is done.
_PUMP_DONE = object()


def _leitura_short_names() -> list[str]:
    """The E.4 leitura academia tool short names (without the
    ``mcp__academia__`` prefix) — derived from :mod:`app.runtime.gate` so
    this factory and the gate table can never drift apart."""
    return [
        name.removeprefix("mcp__academia__")
        for name in gate.LEITURA
        if name.startswith("mcp__academia__")
    ]


def build_launch_options(
    *,
    spec: AgentSpec,
    ctx: TurnContext,
    academia_api: AcademiaApi,
    agent_id: UUID,
    approval_secret: str,
    can_use_tool: Any,
    cli_path: str = DEFAULT_CLI_PATH,
    plugin_path: str,
) -> ClaudeAgentOptions:
    """Build the exact §E.5 ``ClaudeAgentOptions`` for one turn — pure,
    synchronous, no subprocess spawned. ``can_use_tool`` is threaded in
    (rather than built here) so tests can assert this factory's shape
    with a stub callback, independently of the real gate + broker wiring.

    **Contract defect flagged (2026-09-14, reported to the tech-lead):**
    §E.5 literally lists ``allowed_tools=[E.4 leitura + escrita names]``.
    The installed SDK (0.2.152, verified live —
    ``claude_agent_sdk/types.py:_whole_tool_allowed`` /
    ``_get_can_use_tool_shadowed_warning``) treats a bare ``allowed_tools``
    entry as a WHOLE-TOOL grant that auto-approves the call BEFORE
    ``can_use_tool`` is ever invoked. Putting the ESCRITA names there
    would silently bypass the entire approval gate this slice exists to
    build — the opposite of SEC-A/SEC-C's intent. This factory instead
    puts ONLY the LEITURA names (§E.4) plus the two base built-ins into
    ``allowed_tools`` — every ESCRITA call therefore falls through to
    ``can_use_tool`` (gate → broker), which is the one and only place a
    write is allowed to proceed. ``tests/runtime/test_claude_runtime.py``
    asserts no ESCRITA name ever appears in ``allowed_tools``.
    """
    allowed_tools = list(BASE_TOOLS) + [
        f"mcp__academia__{n}" for n in _leitura_short_names()
    ]

    return ClaudeAgentOptions(
        cli_path=cli_path,
        tools=list(BASE_TOOLS),
        setting_sources=[],
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": spec.prompt_append,
        },
        plugins=[{"type": "local", "path": plugin_path}],
        skills=list(spec.skills),
        mcp_servers={
            "academia": build_academia_tools(
                ctx=ctx,
                academia_api=academia_api,
                agent_id=agent_id,
                secret=approval_secret,
                aud=_ACADEMIA_AUD,
            )
        },
        strict_mcp_config=True,
        allowed_tools=allowed_tools,
        disallowed_tools=list(DISALLOWED_TOOLS),
        can_use_tool=can_use_tool,
        env={},
        user="julia-cli",
        include_partial_messages=True,
        max_turns=spec.max_turns,
        resume=ctx.sdk_session_id,
        model=spec.model,
    )


class _TurnDriver:
    """Per-turn state shared between ``can_use_tool`` (the SDK's permission
    callback) and the SDK-message translator — both push onto the same
    ``asyncio.Queue`` so their output interleaves in real arrival order.
    """

    def __init__(
        self, *, ctx: TurnContext, broker: ApprovalBroker, academia_api: AcademiaApi
    ) -> None:
        self._ctx = ctx
        self._broker = broker
        self._academia_api = academia_api
        self.queue: "asyncio.Queue[AgentEvent]" = asyncio.Queue()
        self._tool_names: dict[str, str] = {}
        self._denied_tool_use_ids: set[str] = set()

    async def can_use_tool(
        self, tool_name: str, tool_input: dict[str, Any], context: Any
    ) -> Any:
        tool_use_id = getattr(context, "tool_use_id", None) or ""
        cls = gate.classify(tool_name)

        if cls == "deny":
            self._denied_tool_use_ids.add(tool_use_id)
            return PermissionResultDeny(
                message=f"{tool_name} não é uma ferramenta permitida."
            )

        if cls == "leitura":
            return PermissionResultAllow()

        # escrita — the gate: request approval before this call proceeds.
        diff = await self._build_diff(tool_name, tool_input)
        resumo_text = gate.resumo(tool_name, tool_input)

        await self.queue.put(
            {
                "event": "approval.requested",
                "payload": {
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "resumo": resumo_text,
                    "diff": diff,
                },
            }
        )

        decision = await self._broker.request(
            self._ctx,
            tool_name=tool_name,
            tool_input=tool_input,
            resumo=resumo_text,
            diff=diff,
        )

        await self.queue.put(
            {
                "event": "approval.resolved",
                "payload": {
                    "approval_id": str(decision.approval_id),
                    "decision": "aprovada" if decision.aprovada else "negada",
                    "decided_by": str(decision.approved_by) if decision.approved_by else None,
                },
            }
        )

        if not decision.aprovada:
            self._denied_tool_use_ids.add(tool_use_id)
            return PermissionResultDeny(message="Aprovação negada.")

        updated_input = {
            **tool_input,
            "_approval": {
                "approval_id": str(decision.approval_id),
                "approved_by": str(decision.approved_by),
            },
        }
        return PermissionResultAllow(updated_input=updated_input)

    async def _build_diff(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> dict[str, Any] | None:
        """contract §E.4: for ``kb_escrever`` the control plane first GETs
        the current entry, and the diff compares it with the proposed
        ``corpo_md`` — BEFORE ``broker.request`` (this runs earlier in
        ``can_use_tool``, above)."""
        if tool_name != "mcp__academia__kb_escrever":
            return None
        depois = tool_input.get("corpo_md")
        slug = tool_input.get("slug")
        if not slug:
            return {"antes": None, "depois": depois}
        try:
            current = await self._academia_api.get(f"/api/kb/{slug}")
        except AcademiaNotFoundError:
            return {"antes": None, "depois": depois}
        return {"antes": current.get("corpo_md"), "depois": depois}

    def translate(self, message: Any) -> list[AgentEvent]:
        events: list[AgentEvent] = []

        if isinstance(message, AssistantMessage):
            text = "".join(b.text for b in message.content if isinstance(b, TextBlock))
            if text:
                events.append(
                    {
                        "event": "message.new",
                        "payload": {"role": "assistant", "texto": text, "blocks": []},
                    }
                )
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    self._tool_names[block.id] = block.name
                    events.append(
                        {
                            "event": "tool.started",
                            "payload": {
                                "tool_use_id": block.id,
                                "tool_name": block.name,
                                "classe": (
                                    "escrita"
                                    if gate.classify(block.name) == "escrita"
                                    else "leitura"
                                ),
                                "resumo": gate.resumo(block.name, block.input),
                            },
                        }
                    )
            return events

        if isinstance(message, UserMessage):
            content = message.content
            blocks = content if isinstance(content, list) else []
            for block in blocks:
                if isinstance(block, ToolResultBlock):
                    if block.tool_use_id in self._denied_tool_use_ids:
                        resultado = "negada"
                    elif block.is_error:
                        resultado = "erro"
                    else:
                        resultado = "ok"
                    events.append(
                        {
                            "event": "tool.finished",
                            "payload": {
                                "tool_use_id": block.tool_use_id,
                                "tool_name": self._tool_names.get(block.tool_use_id, ""),
                                "resultado": resultado,
                            },
                        }
                    )
            return events

        if isinstance(message, StreamEvent):
            raw = message.event or {}
            if raw.get("type") == "content_block_delta":
                delta = raw.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    events.append(
                        {
                            "event": "message.delta",
                            "payload": {
                                "message_temp_id": message.uuid,
                                "texto_parcial": delta["text"],
                            },
                        }
                    )
            return events

        return events


class ClaudeAgentSdkRuntime:
    """Real :class:`~app.runtime.types.AgentRuntime`."""

    def __init__(
        self,
        *,
        academia_api: AcademiaApi,
        agent_id: UUID,
        approval_secret: str,
        plugin_path: str,
        cli_path: str = DEFAULT_CLI_PATH,
    ) -> None:
        self._academia_api = academia_api
        self._agent_id = agent_id
        self._approval_secret = approval_secret
        self._plugin_path = plugin_path
        self._cli_path = cli_path

    async def run_turn(
        self,
        spec: AgentSpec,
        ctx: TurnContext,
        prompt: str,
        broker: ApprovalBroker,
    ) -> AsyncIterator[AgentEvent]:
        driver = _TurnDriver(ctx=ctx, broker=broker, academia_api=self._academia_api)
        options = build_launch_options(
            spec=spec,
            ctx=ctx,
            academia_api=self._academia_api,
            agent_id=self._agent_id,
            approval_secret=self._approval_secret,
            can_use_tool=driver.can_use_tool,
            cli_path=self._cli_path,
            plugin_path=self._plugin_path,
        )

        client = ClaudeSDKClient(options)
        result_holder: dict[str, str | None] = {"sdk_session_id": ctx.sdk_session_id}

        async def pump() -> None:
            try:
                async for message in client.receive_response():
                    for event in driver.translate(message):
                        await driver.queue.put(event)
                    if isinstance(message, ResultMessage):
                        result_holder["sdk_session_id"] = (
                            message.session_id or result_holder["sdk_session_id"]
                        )
            finally:
                await driver.queue.put(_PUMP_DONE)  # type: ignore[arg-type]

        await client.connect(prompt)
        pump_task = asyncio.create_task(pump())
        try:
            while True:
                item = await driver.queue.get()
                if item is _PUMP_DONE:
                    break
                yield item
            # The pump already finished (it just enqueued the sentinel) —
            # `await` only to re-raise anything it caught internally.
            await pump_task
        except Exception:
            pump_task.cancel()
            logger.exception(
                "run_turn failed (conversation=%s, org=%s)", ctx.conversation_id, ctx.org_id
            )
            raise
        finally:
            await client.disconnect()

        # Guarantee (contract §E.9): the last event is always session.status
        # on the success path — the SAME guarantee on the FAILURE path is
        # fulfilled by the caller (contract §E.9 "What the routes must do"
        # item 6: catches the raise above and publishes session.status
        # itself), not by this generator yielding after an exception.
        yield {
            "event": "session.status",
            "payload": {"status": "ociosa", "sdk_session_id": result_holder["sdk_session_id"]},
        }
