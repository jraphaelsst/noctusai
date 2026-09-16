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

**Contract §E.11 (per-conversation isolation, supersedes §E.5's ``user``/
``env``/``resume``/``system_prompt``, per the contract's 2026-09-15 note).**
Every real turn now runs under a leased :class:`~app.runtime.slots.TurnSlot`
(``try_reserve()`` delegates to the injected
:class:`~app.runtime.slots.SlotPool`); :func:`build_launch_options` pins
``user``/``env`` to that slot, moves the persona text off argv into a
slot-owned ``append.md`` handoff file (:func:`_write_turn_handoff`), and
wires an injected :class:`~app.runtime.transcript_mirror.ConversationTranscriptMirror`
as ``session_store``. ``ClaudeAgentSdkRuntime._resolve_resume`` is the one
place that decides whether ``ctx.sdk_session_id`` is a USABLE resume
target — never a bare passthrough — reading the injected
:class:`~app.stores.transcripts.TranscriptStore`.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any
from uuid import UUID

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    MirrorErrorMessage,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultError,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from app.runtime import gate
from app.runtime.academia_api import AcademiaApi, AcademiaNotFoundError
from app.runtime.slots import SlotPool, TurnSlot
from app.runtime.tools import build_academia_tools
from app.runtime.transcript_mirror import ConversationTranscriptMirror
from app.runtime.types import (
    AgentEvent,
    AgentSpec,
    ApprovalBroker,
    TurnContext,
    approval_event_payload,
)
from app.stores.approvals import ApprovalStore
from app.stores.transcripts import TranscriptStore

logger = logging.getLogger(__name__)

__all__ = ["build_launch_options", "ClaudeAgentSdkRuntime"]

#: Contract §E.11 "Launch options" — the persona/JULIA.md text goes in a
#: group-only file inside the slot's handoff dir, never on argv.
_HANDOFF_APPEND_FILENAME = "append.md"

#: Contract §E.11 "Inbound": "uvicorn writes ... mode 0640, group
#: julia-cli-K" (handoff files); the dir itself is 0750 (the slot script
#: and the CLI, running as K, need to read/exec into it; nothing else can).
_HANDOFF_DIR_MODE = 0o750
_HANDOFF_FILE_MODE = 0o640
_HANDOFF_OPEN_FLAGS = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW

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
    approvals: ApprovalStore,
    slot: TurnSlot,
    mirror: ConversationTranscriptMirror,
    resume: str | None,
    cli_path: str = DEFAULT_CLI_PATH,
    plugin_path: str,
    approval_use_window_seconds: int = 120,
) -> ClaudeAgentOptions:
    """Build the exact ``ClaudeAgentOptions`` for one turn — pure,
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

    **Contract §E.11 "Launch options" (supersedes §E.5's ``user``/``env``/
    ``resume``/``system_prompt``).** ``user``/``env`` pin the leased
    ``slot``; the persona (``spec.prompt_append``) never appears here —
    it is written to the slot's own ``append.md`` handoff file by
    :func:`_write_turn_handoff` and referenced only via
    ``extra_args["append-system-prompt-file"]``, because
    ``/proc/<pid>/cmdline`` is readable by every uid. ``resume`` is the
    caller's OWN transcript-usability decision
    (``ClaudeAgentSdkRuntime._resolve_resume``) — never a bare
    ``ctx.sdk_session_id`` passthrough, since an unusable transcript must
    never reach the CLI as a resume attempt.
    """
    allowed_tools = list(BASE_TOOLS) + [
        f"mcp__academia__{n}" for n in _leitura_short_names()
    ]

    return ClaudeAgentOptions(
        cli_path=cli_path,
        tools=list(BASE_TOOLS),
        setting_sources=[],
        system_prompt={"type": "preset", "preset": "claude_code"},
        extra_args={
            "append-system-prompt-file": os.path.join(
                slot.handoff_dir, _HANDOFF_APPEND_FILENAME
            )
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
                approvals=approvals,
                use_window_seconds=approval_use_window_seconds,
            )
        },
        strict_mcp_config=True,
        allowed_tools=allowed_tools,
        disallowed_tools=list(DISALLOWED_TOOLS),
        can_use_tool=can_use_tool,
        env={"CLAUDE_CONFIG_DIR": slot.config_dir},
        user=slot.user_name,
        include_partial_messages=True,
        max_turns=spec.max_turns,
        resume=resume,
        model=spec.model,
        session_store=mirror,
        session_store_flush="batched",
    )


def _ensure_handoff_dir(handoff_dir: str, gid: int) -> None:
    """Contract §E.11 "Launch options" / "Inbound": the per-slot handoff
    dir under ``/run/julia-handoff`` is uvicorn-owned (mode 0711) but its
    per-slot subdirectory does not exist until uvicorn creates it here —
    mode 0750, group ``gid`` (the slot's own gid, contract: "uid and gid
    2000+K"). Idempotent: the dir survives across turns (only its
    ENTRIES are unlinked by :meth:`~app.runtime.slots.TurnSlot.release`),
    so a later turn on the same slot just re-asserts mode/group."""
    os.makedirs(handoff_dir, exist_ok=True)
    os.chmod(handoff_dir, _HANDOFF_DIR_MODE)
    os.chown(handoff_dir, -1, gid)


def _write_handoff_file(path: str, data: bytes, *, gid: int) -> None:
    """Creates exactly ONE handoff file with the §E.11 flags/mode/group:
    ``O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW``, mode 0640, group ``gid``.

    ``O_EXCL`` makes an already-existing path a hard, loud failure — the
    slot was swept clean before this turn (contract invariant I2), so a
    survivor here is a real invariant breach, never a race to paper over
    by reusing or overwriting it."""
    try:
        fd = os.open(path, _HANDOFF_OPEN_FLAGS, _HANDOFF_FILE_MODE)
    except FileExistsError as exc:
        raise RuntimeError(
            f"handoff file already exists at {path!r} — the slot was not "
            "swept clean before this turn (contract §E.11 invariant I2); "
            "refusing to reuse or overwrite it"
        ) from exc
    try:
        os.fchmod(fd, _HANDOFF_FILE_MODE)
        os.fchown(fd, -1, gid)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except Exception:
        with suppress(FileNotFoundError):
            os.unlink(path)
        raise


def _write_turn_handoff(
    slot: TurnSlot,
    *,
    persona_text: str,
    handoff_entries: list[dict[str, Any]] | None,
    resume_session_id: str | None,
) -> None:
    """Writes the §E.11 handoff files for this turn's leased slot, BEFORE
    any CLI is spawned. Never writes anything else into the handoff dir.

    ``handoff_entries``/``resume_session_id`` are either both ``None`` (a
    fresh session — only ``append.md`` is written) or both set (a usable
    resume — ``append.md`` plus ``<resume_session_id>.jsonl``, one JSON
    entry per line in ``seq`` order, exactly what
    :meth:`~app.runtime.transcript_mirror.ConversationTranscriptMirror.load_for_handoff`
    returned).
    """
    _ensure_handoff_dir(slot.handoff_dir, slot.uid)
    append_path = os.path.join(slot.handoff_dir, _HANDOFF_APPEND_FILENAME)
    _write_handoff_file(append_path, persona_text.encode("utf-8"), gid=slot.uid)

    if handoff_entries is not None:
        transcript_path = os.path.join(slot.handoff_dir, f"{resume_session_id}.jsonl")
        body = "".join(json.dumps(entry) + "\n" for entry in handoff_entries)
        _write_handoff_file(transcript_path, body.encode("utf-8"), gid=slot.uid)


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

        # Contract §E.9 revision 2026-09-14: `approval.requested` is
        # emitted from INSIDE `on_created` — the broker has already
        # persisted the pendente row and registered the wake-up future by
        # the time it calls this, so the event carries the row's REAL id
        # (the earlier behaviour queued this event before the row existed,
        # so it never carried one at all).
        async def on_created(record: Any) -> None:
            await self.queue.put(
                {"event": "approval.requested", "payload": approval_event_payload(record)}
            )

        decision = await self._broker.request(
            self._ctx,
            tool_name=tool_name,
            tool_input=tool_input,
            resumo=resumo_text,
            diff=diff,
            on_created=on_created,
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

        # Contract §E.9 revision 2026-09-14 / §E.10: only the id is
        # injected. `approved_by` is no longer forwarded — the escrita
        # handler (tools.py) reads it from the STORED, decided row instead
        # of trusting whatever the CLI subprocess echoes back, closing the
        # forged-approver hole the security review flagged.
        updated_input = {
            **tool_input,
            "_approval": {"approval_id": str(decision.approval_id)},
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


#: contract §E.9/§E.11 "Durable transcripts" — exact PT-BR text the route
#: persists as a `system` message when a resume attempt fails (or the
#: stored transcript is unusable) and the runtime falls back to a fresh
#: session.
RESUME_LOST_CONTEXT_TEXT = (
    "O contexto anterior desta conversa não está mais disponível; "
    "Julia começou uma nova sessão."
)

#: contract §E.11 "Durable transcripts" — "'Too long' (`truncado`) has its
#: own text." Distinct from :data:`RESUME_LOST_CONTEXT_TEXT` so the user
#: knows THIS session grew past the 24 MiB cap, rather than context being
#: lost to an infrastructure event.
RESUME_TRUNCATED_TEXT = (
    "O histórico desta conversa ficou muito longo; Julia começou uma "
    "nova sessão e não tem mais acesso ao contexto anterior."
)

#: contract §E.11 / ``LGPD-WARNINGS.md`` (2026-09-15 retention mitigation):
#: an abandoned session (nothing will ever resume from it again) — as
#: opposed to a merely MISSING transcript, which was never stored at all
#: and has nothing to delete.
_ABANDONED_ESTADOS = ("truncado", "incompleto", "invalido")


class ClaudeAgentSdkRuntime:
    """Real :class:`~app.runtime.types.AgentRuntime`."""

    def __init__(
        self,
        *,
        academia_api: AcademiaApi,
        agent_id: UUID,
        approval_secret: str,
        plugin_path: str,
        approvals: ApprovalStore,
        slot_pool: SlotPool,
        transcripts: TranscriptStore,
        cli_path: str = DEFAULT_CLI_PATH,
        approval_use_window_seconds: int = 120,
        transport_factory: Any = None,
    ) -> None:
        self._academia_api = academia_api
        self._agent_id = agent_id
        self._approval_secret = approval_secret
        self._plugin_path = plugin_path
        self._approvals = approvals
        self._slot_pool = slot_pool
        self._transcripts = transcripts
        self._cli_path = cli_path
        self._approval_use_window_seconds = approval_use_window_seconds
        # Test-only seam (contract §E.9 "Resume after a restart" — pinning
        # the SDK's unknown-resume-id signal needs a stubbed `Transport`,
        # never a monkeypatch of this module). ``None`` in production: the
        # SDK builds its own `SubprocessCLITransport`.
        self._transport_factory = transport_factory

    def try_reserve(self) -> TurnSlot | None:
        """Contract §E.11 "Slot pool": delegates to this runtime's own
        injected :class:`~app.runtime.slots.SlotPool` — the SAME pool
        instance across every turn this process serves (constructor
        injection, never a fresh pool per call)."""
        return self._slot_pool.try_reserve()

    def _make_client(self, options: ClaudeAgentOptions) -> ClaudeSDKClient:
        transport = self._transport_factory() if self._transport_factory else None
        return ClaudeSDKClient(options, transport=transport)

    def _resolve_resume(
        self, ctx: TurnContext
    ) -> tuple[ConversationTranscriptMirror, list[dict[str, Any]] | None, str | None]:
        """Contract §E.11 "Durable transcripts" / "Inbound": decides, BEFORE
        any CLI is spawned, whether ``ctx.sdk_session_id``'s stored
        transcript is a usable resume target.

        Returns ``(mirror, handoff_entries, fallback_text)``:

        - a genuinely fresh conversation (``ctx.sdk_session_id is None``)
          → a fresh mirror, ``None`` entries, ``None`` fallback text (no
          fallback message — there was never anything to resume; nothing
          is deleted — there is no old session to abandon).
        - a usable transcript (``estado == "ok"`` and it has stored
          entries) → a mirror already pinned to ``ctx.sdk_session_id``,
          its entries, ``None`` fallback text. Never mutates the store.
        - missing (no stored entries despite ``estado == "ok"``) → a
          fresh mirror, ``None`` entries, the generic fallback text.
          Nothing is deleted — there is nothing TO delete.
        - ``truncado``, ``incompleto`` or ``invalido`` (an ABANDONED
          session, contract §E.11 / ``LGPD-WARNINGS.md`` 2026-09-15:
          retention is bounded by the conversation, so an abandoned
          session's entries have no purpose and no way to be reached
          once a fresh session starts) → :meth:`_abandon_old_session`
          deletes ``ctx.sdk_session_id``'s rows and resets
          ``transcript_estado`` back to ``"ok"`` for the NEW session,
          then this returns a fresh mirror, ``None`` entries, and the
          PT-BR fallback text (`truncado` gets its own; the other two
          get the generic one).
        """
        if ctx.sdk_session_id is None:
            fresh = ConversationTranscriptMirror(
                self._transcripts, ctx.org_id, ctx.conversation_id, None
            )
            return fresh, None, None

        probe = ConversationTranscriptMirror(
            self._transcripts, ctx.org_id, ctx.conversation_id, ctx.sdk_session_id
        )
        entries = probe.load_for_handoff()
        if entries is not None:
            return probe, entries, None

        estado = self._transcripts.get_estado(ctx.org_id, ctx.conversation_id)
        fallback_text = (
            RESUME_TRUNCATED_TEXT if estado == "truncado" else RESUME_LOST_CONTEXT_TEXT
        )
        if estado in _ABANDONED_ESTADOS:
            self._abandon_old_session(ctx, old_sdk_session_id=ctx.sdk_session_id, estado=estado)
        fresh = ConversationTranscriptMirror(
            self._transcripts, ctx.org_id, ctx.conversation_id, None
        )
        return fresh, None, fallback_text

    def _abandon_old_session(
        self, ctx: TurnContext, *, old_sdk_session_id: str, estado: str
    ) -> None:
        """Deletes an abandoned (``truncado``/``incompleto``/``invalido``)
        session's rows and resets ``transcript_estado`` back to ``"ok"``,
        so the fresh session about to start is never judged by the
        abandoned one's state (contract §E.11; ``LGPD-WARNINGS.md``
        2026-09-15 retention mitigation — an abandoned session's entries
        must not linger once a fresh session starts).

        Neither call is allowed to kill the turn — a store failure is
        logged loudly (no silent pass) and the fresh session proceeds
        regardless; a delete failure leaves the orphaned rows to be
        retried the next time THIS conversation abandons a session, and
        an estado-reset failure is surfaced so the next turn's resume
        decision reading a stale estado is a known, logged condition,
        never a silent one.
        """
        try:
            self._transcripts.delete_session(
                ctx.org_id, ctx.conversation_id, old_sdk_session_id
            )
        except Exception:
            logger.error(
                "run_turn: delete_session failed for the abandoned "
                "sdk_session_id=%s (estado=%s, conversation=%s, org=%s); "
                "continuing with a fresh session regardless — the "
                "orphaned rows will be retried on a future abandonment",
                old_sdk_session_id,
                estado,
                ctx.conversation_id,
                ctx.org_id,
                exc_info=True,
            )

        try:
            self._transcripts.set_estado(ctx.org_id, ctx.conversation_id, "ok")
        except Exception:
            logger.error(
                "run_turn: failed to reset transcript_estado to 'ok' "
                "after abandoning sdk_session_id=%s (conversation=%s, "
                "org=%s); the next turn's resume decision may still see "
                "estado=%s",
                old_sdk_session_id,
                ctx.conversation_id,
                ctx.org_id,
                estado,
                exc_info=True,
            )

    async def _connect_or_fresh(
        self,
        options: ClaudeAgentOptions,
        prompt: str,
        ctx: TurnContext,
        mirror: ConversationTranscriptMirror,
    ) -> tuple[ClaudeSDKClient, bool, ConversationTranscriptMirror]:
        """Contract §E.9/§E.11 "Resume after a restart": ``options.resume``
        may point at a session the CLI subprocess's tmpfs transcript store
        no longer has (e.g. a container restart mid-turn). Verified live
        against the installed SDK (0.2.152) — an unknown ``resume`` id
        surfaces as a terminal `result` frame with ``is_error: true`` that
        the CLI then exits non-zero over; the SDK's background reader
        (``claude_agent_sdk/_internal/query.py::Query._read_messages``)
        replaces the resulting ``ProcessError`` with the richer
        ``ResultError`` subclass when it saw that frame first, and
        delivers it to the still-in-flight ``initialize`` control request
        — so it is ``client.connect()`` itself (which awaits
        ``Query.initialize()``) that raises, before any turn message is
        ever seen. This is exactly the case ``query.py``'s own comment
        names: "an `initialize` still in flight when the CLI reports an
        error result during startup (e.g. a refused resume)".

        Narrowed to ``ResultError`` (never the broader ``ProcessError`` —
        e.g. a wrapper refusal, exit 126, is a real failure and must
        propagate, never be mistaken for lost context). Keyed off
        ``options.resume is None`` (never ``ctx.sdk_session_id`` — since
        §E.11, a stored session id can be present while ``options.resume``
        is still ``None``, when ``_resolve_resume`` already decided the
        transcript is unusable; in that case NO resume was attempted, so a
        genuine connect failure here must propagate too).

        Returns ``(client, used_fresh_session, active_mirror)`` — a fresh
        fallback swaps in a NEW, unpinned mirror (the CLI will mint a new
        session id the old, still-pinned ``mirror`` would only drop
        frames for), so the caller must use ``active_mirror`` for the
        rest of the turn, never the ``mirror`` argument itself.
        """
        client = self._make_client(options)
        try:
            await client.connect(prompt)
            return client, False, mirror
        except ResultError:
            if options.resume is None:
                raise
            logger.warning(
                "run_turn: resume of sdk_session_id=%s failed; starting a "
                "fresh session (conversation=%s, org=%s)",
                ctx.sdk_session_id,
                ctx.conversation_id,
                ctx.org_id,
            )
            with suppress(Exception):
                await client.disconnect()
            fresh_mirror = ConversationTranscriptMirror(
                self._transcripts, ctx.org_id, ctx.conversation_id, None
            )
            fresh_options = dataclasses.replace(
                options, resume=None, session_store=fresh_mirror
            )
            fresh_client = self._make_client(fresh_options)
            await fresh_client.connect(prompt)
            return fresh_client, True, fresh_mirror

    async def run_turn(
        self,
        spec: AgentSpec,
        ctx: TurnContext,
        prompt: str,
        broker: ApprovalBroker,
        slot: TurnSlot | None = None,
    ) -> AsyncIterator[AgentEvent]:
        if slot is None:
            raise RuntimeError(
                "ClaudeAgentSdkRuntime.run_turn requires a reserved "
                "TurnSlot (contract §E.11) — the caller must reserve one "
                "via try_reserve() and pass it through; running the real "
                "runtime without one would launch the CLI under a shared "
                "uid, defeating the per-conversation isolation this slot "
                "pool exists to guarantee."
            )

        mirror, handoff_entries, fallback_text = self._resolve_resume(ctx)
        resume_session_id = ctx.sdk_session_id if handoff_entries is not None else None

        _write_turn_handoff(
            slot,
            persona_text=spec.prompt_append,
            handoff_entries=handoff_entries,
            resume_session_id=resume_session_id,
        )

        driver = _TurnDriver(ctx=ctx, broker=broker, academia_api=self._academia_api)
        options = build_launch_options(
            spec=spec,
            ctx=ctx,
            academia_api=self._academia_api,
            agent_id=self._agent_id,
            approval_secret=self._approval_secret,
            can_use_tool=driver.can_use_tool,
            approvals=self._approvals,
            slot=slot,
            mirror=mirror,
            resume=resume_session_id,
            cli_path=self._cli_path,
            plugin_path=self._plugin_path,
            approval_use_window_seconds=self._approval_use_window_seconds,
        )

        client, resumed_fresh, active_mirror = await self._connect_or_fresh(
            options, prompt, ctx, mirror
        )
        result_holder: dict[str, str | None] = {
            "sdk_session_id": None if resumed_fresh else resume_session_id
        }
        if fallback_text is not None:
            yield {
                "event": "session.resume_fallback",
                "payload": {"texto": fallback_text},
            }
        elif resumed_fresh:
            yield {
                "event": "session.resume_fallback",
                "payload": {"texto": RESUME_LOST_CONTEXT_TEXT},
            }

        async def pump() -> None:
            try:
                async for message in client.receive_response():
                    if isinstance(message, MirrorErrorMessage):
                        # Contract §E.11: "A MirrorErrorMessage marks it
                        # incompleto." Non-fatal — the CLI's own local
                        # transcript write already succeeded; only the
                        # durable mirror copy missed this batch.
                        active_mirror.on_mirror_error()
                        continue
                    for event in driver.translate(message):
                        await driver.queue.put(event)
                    if isinstance(message, ResultMessage):
                        result_holder["sdk_session_id"] = (
                            message.session_id or result_holder["sdk_session_id"]
                        )
            finally:
                await driver.queue.put(_PUMP_DONE)  # type: ignore[arg-type]

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

        # Contract §E.11 "Durable transcripts": "At turn end the pinned id
        # must equal ResultMessage.session_id; otherwise the transcript is
        # marked invalido." A missing result session id (no ResultMessage
        # ever observed) has nothing to finalize against — logged, never
        # silently ignored, but not a crash on the success path either.
        final_session_id = result_holder["sdk_session_id"]
        if final_session_id is not None:
            active_mirror.finalize(final_session_id)
        else:
            logger.warning(
                "run_turn: no ResultMessage.session_id observed; skipping "
                "mirror.finalize (conversation=%s, org=%s)",
                ctx.conversation_id,
                ctx.org_id,
            )

        # Guarantee (contract §E.9): the last event is always session.status
        # on the success path — the SAME guarantee on the FAILURE path is
        # fulfilled by the caller (contract §E.9 "What the routes must do"
        # item 6: catches the raise above and publishes session.status
        # itself), not by this generator yielding after an exception.
        yield {
            "event": "session.status",
            "payload": {"status": "ociosa", "sdk_session_id": final_session_id},
        }
