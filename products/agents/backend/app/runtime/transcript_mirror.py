"""``ConversationTranscriptMirror`` — the SDK ``SessionStore`` adapter that
gives Julia durable, per-conversation transcripts (contract §E.11 "Durable
transcripts").

Implements ``claude_agent_sdk.types.SessionStore`` (verified against the
installed 0.2.152 wheel, ``types.py:1587-1704``) by DUCK TYPING — the SDK
never ``isinstance``-checks a session store (``SessionStore`` docstring:
"a duck-typed adapter need not subclass ``SessionStore``"), and probes for
optional methods at call time. Only ``append`` and ``load`` are required;
this adapter implements exactly those two plus the product-specific
``on_mirror_error`` / ``finalize`` / ``load_for_handoff`` hooks the SDK does
NOT define (§E.9 amendment: "transcripts go through an injected
TranscriptStore seam, like the approval broker" — the store is
``app.stores.transcripts.TranscriptStore``, injected here).

**Trusted binding (security).** SEC-C's threat model (§E.10) assumes the
CLI subprocess may be compromised. ``append``'s ``key`` argument is derived
by the SDK from the mirrored file's ON-DISK PATH
(``_internal/session_store.py:file_path_to_session_key`` —
``<project_key>/<session_id>.jsonl`` under ``CLAUDE_CONFIG_DIR/projects``),
which a compromised CLI fully controls (it can create arbitrary session
ids and, in principle, any file under its own tmpfs). This mirror therefore
NEVER derives ``org_id``/``conversation_id`` from ``key`` — those are fixed
at construction time from the trusted ``TurnContext`` the route already
resolved (contract §E.9), and every write lands under that fixed
conversation regardless of what the frame's own path claims.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from claude_agent_sdk.types import SessionKey, SessionStoreEntry

from app.stores.transcripts import TranscriptStore

__all__ = ["ConversationTranscriptMirror"]

#: The slot script (contract §E.11 "Slot script") always creates
#: ``home/.claude/projects/-app`` — HOME is pinned to ``/run/julia-K/home``
#: and the CLI's cwd inside the container is ``/app``, so
#: ``project_key_for_directory("/app")`` sanitizes to this literal. A frame
#: whose ``project_key`` is anything else did not originate from Julia's own
#: cwd and is dropped.
_EXPECTED_PROJECT_KEY = "-app"


class ConversationTranscriptMirror:
    """One instance per turn (or per resumed session), bound to exactly one
    conversation.

    Args:
        store: the injected :class:`~app.stores.transcripts.TranscriptStore`.
        org_id: the trusted org, from ``TurnContext``.
        conversation_id: the trusted conversation, from ``TurnContext`` —
            EVERY write this instance ever makes lands under this id, never
            one derived from a mirror frame.
        expected_session_id: ``conversations.sdk_session_id`` when resuming
            an existing, ``ok`` transcript; ``None`` for a fresh session,
            in which case the FIRST accepted frame's session id is pinned
            and used for every subsequent frame and for :meth:`finalize`.
        cap_bytes: contract §E.11 "Transcript cap of 24 MiB per session".
    """

    def __init__(
        self,
        store: TranscriptStore,
        org_id: UUID,
        conversation_id: UUID,
        expected_session_id: str | None,
        cap_bytes: int = 24 * 1024 * 1024,
    ) -> None:
        self._store = store
        self._org_id = org_id
        self._conversation_id = conversation_id
        # None means "pin on the first accepted frame" (fresh session);
        # a value means "this is a resume — every frame must match it".
        self._pinned_session_id = expected_session_id
        self._cap_bytes = cap_bytes
        self._truncated = False
        self._frames_dropped = 0
        # A resumed, not-yet-capped session may already carry bytes from
        # earlier turns; a fresh session starts at 0 (there is nothing to
        # read yet — total_bytes(..., None) would not even be a valid
        # call). Read once so every `append` only pays for its own delta.
        self._bytes_so_far = (
            store.total_bytes(org_id, conversation_id, expected_session_id)
            if expected_session_id is not None
            else 0
        )

    @property
    def pinned_session_id(self) -> str | None:
        """The session id this mirror writes under — ``None`` until the
        first accepted frame pins it (fresh-session case only)."""
        return self._pinned_session_id

    @property
    def frames_dropped(self) -> int:
        """Count of mirror frames dropped by the filters in :meth:`append`
        (subpath, wrong project key, or session-id mismatch)."""
        return self._frames_dropped

    # ------------------------------------------------------------------
    # claude_agent_sdk.types.SessionStore protocol — required methods.
    # ------------------------------------------------------------------

    async def append(
        self, key: SessionKey, entries: list[SessionStoreEntry]
    ) -> None:
        """Mirror a batch of transcript entries (contract §E.11
        "Outbound").

        Filtering, in order — a dropped frame is counted (see
        :attr:`frames_dropped`) and never reaches the store:

        1. **Subpath frames** (subagent transcripts,
           ``<session>/subagents/agent-<id>.jsonl``) are dropped. Julia has
           no subagents in this slice's scope, and even if she did, only
           the MAIN transcript is durable here.
        2. **Wrong project key.** ``key["project_key"]`` must be
           :data:`_EXPECTED_PROJECT_KEY` — anything else means the frame's
           path did not come from Julia's own pinned cwd (see the module
           docstring's trusted-binding note).
        3. **Session-id mismatch.** A fresh session (``expected_session_id``
           was ``None`` at construction) pins the FIRST accepted frame's
           session id; every later frame — from this or a different SDK
           subprocess writing to the same ``CLAUDE_CONFIG_DIR`` — must match
           it exactly, or it is dropped.

        Once :attr:`_truncated` (the 24 MiB cap has already been crossed by
        a prior call), every further call is a no-op — "no further writes"
        (contract §E.11 SEC-C bullet 6 equivalent for the cap, "Durable
        transcripts" bullet).
        """
        if key.get("subpath"):
            self._frames_dropped += 1
            return
        if key["project_key"] != _EXPECTED_PROJECT_KEY:
            self._frames_dropped += 1
            return
        if self._pinned_session_id is None:
            self._pinned_session_id = key["session_id"]
        elif key["session_id"] != self._pinned_session_id:
            self._frames_dropped += 1
            return

        if self._truncated:
            return

        added = self._store.append_entries(
            self._org_id,
            self._conversation_id,
            self._pinned_session_id,
            list(entries),
        )
        self._bytes_so_far += added
        if self._bytes_so_far > self._cap_bytes:
            self._truncated = True
            self._store.set_estado(self._org_id, self._conversation_id, "truncado")

    async def load(self, key: SessionKey) -> list[SessionStoreEntry] | None:
        """Returns ``None`` ON PURPOSE — this is NOT "no transcript
        exists".

        When ``options.session_store`` AND ``options.resume`` are both set,
        the SDK parent calls this ONCE, before spawning the subprocess
        (``_internal/client.py``: ``materialize_resume_session``), to
        write the loaded entries into a temporary ``CLAUDE_CONFIG_DIR``
        (``_internal/session_resume.py``) the subprocess then resumes
        from. That temp directory is created by (and owned by) the
        control-plane process — uvicorn's own uid, not the leased slot
        uid — so the slot's ``setpriv --reuid=K`` subprocess could never
        read the credentials the SDK would otherwise stage there
        (contract §E.11 "Durable transcripts" / "Outbound": "The SDK's
        own resume copies uvicorn credentials into uvicorn's /tmp, which
        a slot uid cannot read").

        Returning ``None`` here makes ``materialize_resume_session`` treat
        this as "nothing to materialize" and leave ``--resume=<sid>`` on
        argv untouched (``subprocess_cli.py``); the slot script's own
        handoff-file copy (§E.11 "Slot script" step 3) is what actually
        makes that resume succeed, entirely inside the slot's own tmpfs.
        Use :meth:`load_for_handoff` for the real read path.
        """
        return None

    # ------------------------------------------------------------------
    # Product-specific hooks — not part of the SDK's SessionStore
    # protocol. Called by B3 (the runtime), never by the SDK itself.
    # ------------------------------------------------------------------

    def on_mirror_error(self) -> None:
        """Call this when the runtime observes a ``MirrorErrorMessage`` in
        the SDK's event stream (contract §E.11: "A MirrorErrorMessage
        marks it incompleto"). The SDK never calls this itself —
        ``MirrorErrorMessage`` is a regular message the CLIENT reads from
        the stream, not a ``SessionStore`` protocol callback."""
        self._store.set_estado(self._org_id, self._conversation_id, "incompleto")

    def finalize(self, result_session_id: str) -> None:
        """Call this once, at turn end, with ``ResultMessage.session_id``
        (contract §E.11: "At turn end the pinned id must equal
        ResultMessage.session_id; otherwise the transcript is marked
        invalido").

        A match leaves the stored ``transcript_estado`` exactly as it is
        (``ok``, or ``truncado``/``incompleto`` if either fired earlier
        this turn) — this method only ever adds the ``invalido`` finding,
        never removes one."""
        if self._pinned_session_id != result_session_id:
            self._store.set_estado(self._org_id, self._conversation_id, "invalido")

    def load_for_handoff(self) -> list[dict[str, Any]] | None:
        """The REAL read path (contract §E.11 "Inbound"): B3 calls this,
        on a mirror constructed with ``expected_session_id`` set to the
        conversation's stored ``sdk_session_id``, BEFORE spawning the next
        turn's CLI — to get the entries it writes to
        ``/run/julia-handoff/K/<sid>.jsonl`` for the slot script to pick
        up. Returns ``None`` unless the transcript's stored estado is
        exactly ``"ok"`` (a ``truncado``/``incompleto``/``invalido``
        transcript is never handed off — the caller starts a fresh
        session instead), and also ``None`` if this mirror was
        constructed for a fresh session and no frame has pinned a session
        id yet (nothing to hand off)."""
        if self._pinned_session_id is None:
            return None
        estado = self._store.get_estado(self._org_id, self._conversation_id)
        if estado != "ok":
            return None
        return self._store.load(
            self._org_id, self._conversation_id, self._pinned_session_id
        )
