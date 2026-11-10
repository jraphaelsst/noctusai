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
import re
import threading
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Protocol

logger = logging.getLogger(__name__)

SEND_ENABLED = "enabled"
SEND_DISABLED = "disabled"
_SEND_VALUES = (SEND_ENABLED, SEND_DISABLED)
_POLICY_KEYS = ("send", "mark_online", "full_sync", "auto_repair")
#: Env var carrying a JSON map ``{"<base_url>" | "<base_url>#<session>" | "*": <policy>}`` for processes whose
#: lines are DB-sourced (a connection row holds the URL) and so cannot be named by one ``<PRODUCT>_WAHA_LINE_POLICY``.
LINE_POLICIES_ENV = "WAHA_LINE_POLICIES"

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
#: Case-insensitive on purpose: WAHA's router is. Order matters, first match wins:
#:   1. the session lifecycle / config / QR (`/api/sessions...`) is NOT a WhatsApp write, any verb;
#:   2. a read verb on a send-class path IS (WAHA still serves some sends on GET);
#:   3. any other read verb is a read;
#:   4. everything else -- every non-read verb on any other path, unknown endpoints included -- is a write.
_SESSION_LIFECYCLE = re.compile(r"^/api/sessions(/|$)", re.IGNORECASE)
_SEND_CLASS = re.compile(r"^/api/(send|reaction|starttyping|stoptyping|forwardmessage)", re.IGNORECASE)
_READ_VERBS = ("GET", "HEAD", "OPTIONS")


def is_whatsapp_write(method: str, path: str) -> bool:
    """True when ``method path`` writes to WhatsApp (or might: the allow-list is the session lifecycle + plain reads,
    never the other way round). ``path`` is the WAHA path or a full URL."""
    verb = method.upper()
    p = re.sub(r"^https?://[^/]+", "", path).split("?", 1)[0]
    if _SESSION_LIFECYCLE.match(p):
        return False
    if verb in _READ_VERBS:
        return bool(_SEND_CLASS.match(p))
    return True


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


def register_line_policy(base_url: str, policy: LinePolicy, *, session: Optional[str] = None) -> None:
    """Declare a line's policy at product boot. ``base_url="*"`` is the process-wide default (legacy products whose
    lines are DB-sourced); a product that should be strict never registers it."""
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


def load_line_policies_from_env(environ: Optional[Mapping[str, str]] = None) -> int:
    """Register every entry of ``WAHA_LINE_POLICIES`` (JSON map). Raises :class:`LinePolicyError` on a bad value."""
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
    for url, spec in mapping.items():
        base, _, session = str(url).partition("#")
        register_line_policy(base if base != "*" else "*", parse_line_policy(spec), session=session or None)
    return len(mapping)


def resolve_line_policy(base_url: str, session: Optional[str] = None) -> LinePolicy:
    """(url, session) -> (url) -> ``"*"`` -> :data:`UNDECLARED` (fail-closed)."""
    global _env_loaded
    if not _env_loaded:
        with _lock:
            already = _env_loaded
            _env_loaded = True
        if not already:
            load_line_policies_from_env()
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

    def _guard_write(self, method: str, path: str) -> None:
        if self.line_policy.send_enabled or not is_whatsapp_write(method, path):
            return
        reason = self._refusal_reason()
        endpoint = redact_path(path)
        self.line_event_sink.record(LineEvent(
            EVENT_WRITE_REFUSED, self._line_label, f"{method.upper()} {endpoint}", reason, self.line_policy.as_dict()))
        raise LineWriteRefused(line=self._line_label, method=method.upper(), path=endpoint, reason=reason)

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
