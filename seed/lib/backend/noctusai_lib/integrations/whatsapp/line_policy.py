"""WhatsApp LINE POLICY v1 -- what a WAHA line is allowed to do, declared per line and enforced in the seed.

A *line* is one WAHA instance + session (one WhatsApp number). Its policy is DATA, declared per instance in
``deploy/fleet/waha-instances.yml`` (the platform ceiling) and handed to the product as ``<PRODUCT>_WAHA_LINE_POLICY``
(a JSON object, see :func:`parse_line_policy`)::

    {"send": "disabled", "mark_online": false, "full_sync": false, "auto_repair": false}

* ``send``        -- ``enabled`` | ``disabled``. ``disabled`` refuses EVERY write to WhatsApp (sends, read receipts,
                     typing/presence, reactions, group admin, message delete...). Session lifecycle / QR / config calls
                     are NOT WhatsApp writes and stay allowed.
* ``mark_online`` -- WAHA NOWEB ``markOnline`` (presence broadcast on connect). ``false`` keeps the linked phone's
                     "last seen" untouched.
* ``full_sync``   -- WAHA NOWEB ``store.fullSync`` (history backfill at pairing).
* ``auto_repair`` -- may the seed run the re-pair ladder (``restart_session`` / ``recover_session``: restart, logout,
                     fresh QR) on its own. ``false`` = a human drives any re-pair.

FAIL-CLOSED: a line with no declared policy resolves to :data:`UNDECLARED` (``send: disabled``) and its writes are
REFUSED. A refusal is loud and typed (:class:`LineWriteRefused`) and is recorded as an immutable event
(``whatsapp.line.write_refused``) through the :class:`LineEventSink` seam -- never a silent no-op.

Layer 3 of the zero-write defence (edge deny proxy -> product mounts no send routes -> THIS). KB § CONTEXT/INTEGRATIONS/
whatsapp.md § 6a.
"""
from __future__ import annotations

import json
import logging
import os
import posixpath
import re
import threading
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Protocol
from urllib.parse import quote, unquote

logger = logging.getLogger(__name__)

SEND_ENABLED = "enabled"
SEND_DISABLED = "disabled"
_SEND_VALUES = (SEND_ENABLED, SEND_DISABLED)
_POLICY_KEYS = ("send", "mark_online", "full_sync", "auto_repair")
#: Env var carrying a JSON map ``{"<base_url>" | "<base_url>#<session>" | "*": <policy>}`` for processes whose
#: lines are DB-sourced (a connection row holds the URL) and so cannot be named by one ``<PRODUCT>_WAHA_LINE_POLICY``.
LINE_POLICIES_ENV = "WAHA_LINE_POLICIES"

#: registry key under which a FakeWahaClient resolves its policy (no real URL exists for a fake)
FAKE_LINE_URL = "fake://waha"
EVENT_WRITE_REFUSED = "whatsapp.line.write_refused"
EVENT_REPAIR_REFUSED = "whatsapp.line.repair_refused"


class LinePolicyError(ValueError):
    """A line policy that cannot be parsed faithfully (unknown key, bad type, missing ``send``)."""


class LineWriteRefused(RuntimeError):
    """The line's policy forbids this write to WhatsApp (``send: disabled`` or no policy declared)."""

    def __init__(self, *, line: str, method: str, path: str, reason: str):
        self.line, self.method, self.path, self.reason = line, method, path, reason
        super().__init__(f"line {line}: write {method} {path} refused ({reason})")


class LineRepairRefused(RuntimeError):
    """The line's policy has ``auto_repair: false``: the seed will not re-pair (restart/logout/QR) on its own."""

    def __init__(self, *, line: str, op: str, reason: str):
        self.line, self.op, self.reason = line, op, reason
        super().__init__(f"line {line}: {op} refused ({reason})")


@dataclass(frozen=True)
class LinePolicy:
    send: str
    mark_online: bool
    full_sync: bool
    auto_repair: bool
    declared: bool = True
    #: ``False`` for the process-wide ``"*"`` default (legacy, possibly SHARED sessions): the policy still gates writes,
    #: but session-config writes leave ``markOnline`` / ``fullSync`` as their owner set them (the 2026-10-15 shared-
    #: session hazard). A line named by URL is its own config authority.
    config_authority: bool = True

    @property
    def send_enabled(self) -> bool:
        return self.send == SEND_ENABLED

    def as_dict(self) -> dict[str, Any]:
        return {"send": self.send, "mark_online": self.mark_online, "full_sync": self.full_sync,
                "auto_repair": self.auto_repair}

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), separators=(",", ":"), sort_keys=False)


#: A line nobody declared. Fail-closed: no writes, no presence, no history sync, no self-repair.
UNDECLARED = LinePolicy(SEND_DISABLED, False, False, False, declared=False)


def parse_line_policy(raw: "str | Mapping[str, Any]") -> LinePolicy:
    """Strict parse of the env / yaml form. Every key is required; unknown keys and wrong types raise
    :class:`LinePolicyError` (a typo must not become a silently-permissive line)."""
    data: Any = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise LinePolicyError(f"line policy is not valid JSON: {exc}") from exc
    if not isinstance(data, Mapping):
        raise LinePolicyError("line policy must be a JSON object")
    unknown = sorted(set(data) - set(_POLICY_KEYS))
    if unknown:
        raise LinePolicyError(f"line policy: unknown key(s) {unknown}")
    missing = [k for k in _POLICY_KEYS if k not in data]
    if missing:
        raise LinePolicyError(f"line policy: missing key(s) {missing}")
    if data["send"] not in _SEND_VALUES:
        raise LinePolicyError(f"line policy: send must be one of {_SEND_VALUES}, got {data['send']!r}")
    for key in ("mark_online", "full_sync", "auto_repair"):
        if not isinstance(data[key], bool):
            raise LinePolicyError(f"line policy: {key} must be a boolean, got {data[key]!r}")
    return LinePolicy(data["send"], data["mark_online"], data["full_sync"], data["auto_repair"])


# --- what is a write to WhatsApp ---------------------------------------------------------------------------------------

#: The decision table, ONE place. It is MIRRORED by the edge deny proxy's nginx `map` (rendered by
#: `noctus.dev.waha_instance`; a test evaluates the rendered map against `is_whatsapp_write` over a path matrix).
#: Case-insensitive on purpose: WAHA's router is. Order matters, first match wins. On a `send: disabled` line:
#:   1. `POST /api/sessions/{name}/start` passes (the pairing entry point; its config is written FROM the policy);
#:   2. a read verb on a send-class path IS a write (WAHA still serves some sends on GET);
#:   3. any other read verb passes (this includes `GET /api/sessions...` and the QR);
#:   4. everything else is a write: logout, stop, restart, DELETE, a session-config PUT (it could set markOnline or move
#:      webhooks -- the client's own policy-derived config PUT is the only exception, see `policy_config`), every
#:      non-read verb on any other path, unknown endpoints included.
_SESSION_START = re.compile(r"^/api/sessions/[^/]+/start$", re.IGNORECASE)
_SESSION_CONFIG_PUT = re.compile(r"^/api/sessions/[^/]+$", re.IGNORECASE)
_SEND_CLASS = re.compile(r"^/api/(send|reaction|starttyping|stoptyping|forwardmessage)", re.IGNORECASE)
_READ_VERBS = ("GET", "HEAD", "OPTIONS")


def seg(value: str) -> str:
    """Percent-encode ONE path segment: ``/`` and ``?`` can never leave the segment and ``.`` / ``..`` can never be a
    dot-segment (httpx would normalise them away and reroute the request: ``/api/sessions/../sendText``)."""
    out = quote(str(value), safe="@")
    return out.replace(".", "%2E") if ".." in out or out == "." else out


def _paths(path: str) -> list[str]:
    raw = re.sub(r"^https?://[^/]+", "", path).split("?", 1)[0]
    norm = posixpath.normpath(unquote(raw)) if raw else raw
    if raw.startswith("/") and not norm.startswith("/"):
        norm = "/" + norm
    return [raw, norm] if norm != raw else [raw]


def _classify(verb: str, p: str) -> bool:
    if verb == "POST" and _SESSION_START.match(p):
        return False
    if verb in _READ_VERBS:
        return bool(_SEND_CLASS.match(p))
    return True


def is_whatsapp_write(method: str, path: str) -> bool:
    """True when ``method path`` writes to WhatsApp (or might: the allow-list is session start + plain reads, never the
    other way round). Judged on BOTH the raw and the dot-normalised path: either one being a write makes it one."""
    verb = method.upper()
    return any(_classify(verb, p) for p in _paths(path))


def is_session_config_put(method: str, path: str) -> bool:
    return method.upper() == "PUT" and all(_SESSION_CONFIG_PUT.match(p) for p in _paths(path))


def redact_path(path: str) -> str:
    """Event-safe endpoint: digits runs (phones / ids) never reach the ledger."""
    return re.sub(r"\d{6,}", "*", re.sub(r"^https?://[^/]+", "", path).split("?", 1)[0])


# --- events (EOA) --------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LineEvent:
    """Immutable, intent-named fact: a line's policy refused something. No message content, no phone numbers."""

    event: str
    line: str
    op: str
    reason: str
    policy: dict[str, Any]
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class LineEventSink(Protocol):
    def record(self, event: LineEvent) -> None: ...


class InMemoryLineEventSink:
    """Bounded in-process sink (default + tests). Products wire a persistent sink via ``set_default_line_event_sink``
    (S2: the assistant's append-only events table)."""

    def __init__(self, maxlen: int = 1000):
        self.events: "deque[LineEvent]" = deque(maxlen=maxlen)

    def record(self, event: LineEvent) -> None:
        self.events.append(event)
        logger.error("%s line=%s op=%s reason=%s", event.event, event.line, event.op, event.reason)


_default_sink: LineEventSink = InMemoryLineEventSink()


def set_default_line_event_sink(sink: LineEventSink) -> None:
    global _default_sink
    _default_sink = sink


def get_default_line_event_sink() -> LineEventSink:
    return _default_sink


# --- registry ----------------------------------------------------------------------------------------------------------

_lock = threading.Lock()
_registry: dict[str, LinePolicy] = {}
_env_loaded = False


def _key(base_url: str, session: Optional[str]) -> str:
    base = (base_url or "").rstrip("/").lower()
    return f"{base}#{session}" if session else base


def _check_registrable(base_url: str, policy: LinePolicy, allow_memory_sink: bool) -> None:
    # NOC-REMEDIATE[line-event-persistence]: refusal events reach only the in-memory sink until S2 (products/assistant)
    # ships its append-only events table and calls set_default_line_event_sink(...). Until then a send:disabled line
    # cannot be registered without an explicit allow_memory_sink=True (tests only) -- a refusal nobody can audit later
    # must not be what protects a personal number. — 2026-11-10
    if not policy.send_enabled and isinstance(_default_sink, InMemoryLineEventSink) and not allow_memory_sink:
        raise LinePolicyError(
            f"line {base_url!r}: refusing to register `send: disabled` while the event sink is in-memory "
            "(refusals would not be persisted); call set_default_line_event_sink(<persistent sink>) first"
        )


def register_line_policy(
    base_url: str, policy: LinePolicy, *, session: Optional[str] = None, allow_memory_sink: bool = False
) -> None:
    """Declare a line's policy at product boot. ``base_url="*"`` is the process-wide default (legacy products whose
    lines are DB-sourced); it cannot carry a session. A strict line is never given a ``"*"``."""
    if base_url == "*" and session:
        raise LinePolicyError('"*" is the process-wide default and cannot be scoped to a session')
    _check_registrable(base_url, policy, allow_memory_sink)
    with _lock:
        if base_url == "*":
            _registry["*"] = replace(policy, config_authority=False)
        else:
            _registry[_key(base_url, session)] = policy


def clear_line_policies() -> None:
    global _env_loaded
    with _lock:
        _registry.clear()
        _env_loaded = False


def load_line_policies_from_env(
    environ: Optional[Mapping[str, str]] = None, *, allow_memory_sink: bool = False
) -> int:
    """Register every entry of ``WAHA_LINE_POLICIES`` (JSON map) ATOMICALLY: everything is parsed and validated first,
    so a bad entry registers nothing. Raises :class:`LinePolicyError`."""
    env = os.environ if environ is None else environ
    raw = env.get(LINE_POLICIES_ENV, "").strip()
    if not raw:
        return 0
    try:
        mapping = json.loads(raw)
    except ValueError as exc:
        raise LinePolicyError(f"{LINE_POLICIES_ENV} is not valid JSON: {exc}") from exc
    if not isinstance(mapping, dict):
        raise LinePolicyError(f"{LINE_POLICIES_ENV} must be a JSON object")
    parsed: list[tuple[str, Optional[str], LinePolicy]] = []
    for url, spec in mapping.items():
        base, _, session = str(url).partition("#")
        if base == "*" and session:
            raise LinePolicyError(f'{LINE_POLICIES_ENV}: "{url}" -- "*" cannot be scoped to a session')
        policy = parse_line_policy(spec)
        _check_registrable(base, policy, allow_memory_sink)
        parsed.append((base, session or None, policy))
    for base, session, policy in parsed:
        register_line_policy(base, policy, session=session, allow_memory_sink=allow_memory_sink)
    return len(parsed)


def resolve_line_policy(base_url: str, session: Optional[str] = None) -> LinePolicy:
    """(url, session) -> (url) -> ``"*"`` -> :data:`UNDECLARED` (fail-closed)."""
    global _env_loaded
    if not _env_loaded:
        load_line_policies_from_env()  # raises on a bad value: loud on EVERY call, never a silent UNDECLARED
        _env_loaded = True
    with _lock:
        for key in (_key(base_url, session), _key(base_url, None), "*"):
            if key in _registry:
                return _registry[key]
    return UNDECLARED


# --- the guard both WahaClient and FakeWahaClient share --------------------------------------------------------------


class LinePolicyGuard:
    """Mixin: ``self.line_policy``, ``self.line_event_sink``, ``self._line_label``. One implementation of "refuse,
    record, raise" so the Real and the Fake cannot drift."""

    line_policy: LinePolicy
    line_event_sink: LineEventSink
    _line_label: str

    def _init_line_policy(
        self, *, label: str, policy: LinePolicy, sink: Optional[LineEventSink]
    ) -> None:
        self._line_label = label
        self.line_policy = policy
        self.line_event_sink = sink or get_default_line_event_sink()

    def _refusal_reason(self) -> str:
        return "send_disabled" if self.line_policy.declared else "no_line_policy"

    def _config_policy(self) -> "LinePolicy | None":
        """The policy that drives session-config writes. Declared + config-authoritative: the line's own policy. The
        legacy ``"*"`` default: None (existing keys preserved). UNDECLARED: its (all-off) flags -- never WAHA's defaults."""
        p = self.line_policy
        if not p.declared:
            return UNDECLARED
        return p if p.config_authority else None

    def _guard_write(self, method: str, path: str, *, policy_config: bool = False) -> None:
        if self.line_policy.send_enabled:
            return
        if policy_config and is_session_config_put(method, path):
            return  # the client's own policy-derived config PUT (markOnline/fullSync come FROM the policy)
        if not is_whatsapp_write(method, path):
            return
        reason = self._refusal_reason()
        endpoint = redact_path(path)
        self.line_event_sink.record(LineEvent(
            EVENT_WRITE_REFUSED, self._line_label, f"{method.upper()} {endpoint}", reason, self.line_policy.as_dict()))
        raise LineWriteRefused(line=self._line_label, method=method.upper(), path=endpoint, reason=reason)

    def _final_url_hook(self, policy_config: bool = False):
        """httpx request event hook (sync + async twins): re-judges the FINAL request URL after httpx has built and
        normalised it, so no spelling of the path can slip past the pre-check."""
        def check(request) -> None:
            self._guard_write(request.method, request.url.path, policy_config=policy_config)

        async def acheck(request) -> None:
            check(request)

        return check, acheck

    def _guard_repair(self, op: str) -> None:
        if self.line_policy.auto_repair:
            return
        reason = "auto_repair_disabled" if self.line_policy.declared else "no_line_policy"
        self.line_event_sink.record(LineEvent(
            EVENT_REPAIR_REFUSED, self._line_label, op, reason, self.line_policy.as_dict()))
        raise LineRepairRefused(line=self._line_label, op=op, reason=reason)


# --- read-back -------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyReadback:
    ok: bool
    mismatches: tuple[str, ...]
    status: Optional[str]


def check_session_against_policy(session: Mapping[str, Any], policy: LinePolicy) -> PolicyReadback:
    """Compare what WAHA reports for the session (``GET /api/sessions/{name}``) with the policy. A config you PUT and
    never read back is unverified -- run this BEFORE the QR scan. A key WAHA does not echo is a mismatch, never a pass."""
    config = session.get("config") if isinstance(session.get("config"), Mapping) else {}
    noweb = config.get("noweb") if isinstance(config.get("noweb"), Mapping) else {}
    store = noweb.get("store") if isinstance(noweb.get("store"), Mapping) else {}
    problems: list[str] = []
    for label, got, want in (
        ("noweb.markOnline", noweb.get("markOnline"), policy.mark_online),
        ("noweb.store.fullSync", store.get("fullSync"), policy.full_sync),
    ):
        if got is None:
            problems.append(f"{label}: not reported by WAHA (expected {want})")
        elif got is not want:
            problems.append(f"{label}: WAHA has {got!r}, policy says {want}")
    if store.get("enabled") is not True:
        problems.append(f"noweb.store.enabled: WAHA has {store.get('enabled')!r}, expected True")
    status = session.get("status")
    return PolicyReadback(not problems, tuple(problems), str(status) if status is not None else None)
