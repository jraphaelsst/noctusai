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
from urllib.parse import quote, unquote, urlsplit

logger = logging.getLogger(__name__)

SEND_ENABLED = "enabled"
SEND_DISABLED = "disabled"
_SEND_VALUES = (SEND_ENABLED, SEND_DISABLED)
_POLICY_KEYS = ("send", "mark_online", "full_sync", "auto_repair")
_OPTIONAL_KEYS = ("webhook_relay",)
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


class LinePolicyDrift(RuntimeError):
    """The session WAHA actually runs does not match the line policy (e.g. NOWEB's `markOnline` defaults to TRUE).
    Pairing (QR) on a read-only line is refused until the read-back is clean."""

    def __init__(self, *, line: str, mismatches: "tuple[str, ...]"):
        self.line, self.mismatches = line, mismatches
        super().__init__(f"line {line}: session does not match the policy: {'; '.join(mismatches)}")


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
    #: For a `send: disabled` line: the ONLY webhook base `set_webhook` / `remove_webhook` may touch (the edge's relay,
    #: e.g. ``http://waha-<n>:3001``). None = no webhook may be (re)registered on a disabled line.
    webhook_relay: Optional[str] = None

    @property
    def send_enabled(self) -> bool:
        return self.send == SEND_ENABLED

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"send": self.send, "mark_online": self.mark_online, "full_sync": self.full_sync,
                               "auto_repair": self.auto_repair}
        if self.webhook_relay:
            out["webhook_relay"] = self.webhook_relay
        return out

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
    unknown = sorted(set(data) - set(_POLICY_KEYS) - set(_OPTIONAL_KEYS))
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
    relay = data.get("webhook_relay")
    if relay is not None and not (isinstance(relay, str) and re.match(r"^https?://[^/\s]+$", relay)):
        raise LinePolicyError("line policy: webhook_relay must be a bare http(s)://host[:port] base")
    return LinePolicy(data["send"], data["mark_online"], data["full_sync"], data["auto_repair"],
                      webhook_relay=relay)


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
_SEND_CLASS = re.compile(
    r"^/api/(send|reaction|starttyping|stoptyping|forwardmessage|[^/]+/presence)", re.IGNORECASE)
#: Encoded control characters, `?`, `#`, `/`, `%` or a backslash in the RAW spelling: the shape of every smuggling
#: attempt (`logout%3F/start`, `%0D%0A` splitting). A legitimate segment never needs them (`seg()` would have produced
#: them only for a hostile id), so such a request is a write whatever it decodes to. MIRRORED by the edge (400).
_SUSPICIOUS = re.compile(r"%(0[0-9a-f]|1[0-9a-f]|2[0356f]|3f|5c|7f)|\\", re.IGNORECASE)
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
    if _SUSPICIOUS.search(re.sub(r"^https?://[^/]+", "", path).split("?", 1)[0]):
        return True
    return any(_classify(verb, p) for p in _paths(path))


_SESSION_CREATE = re.compile(r"^/api/sessions/?$", re.IGNORECASE)


def is_session_config_put(method: str, path: str) -> bool:
    """The two calls that SET session config on WAHA: `PUT /api/sessions/{n}` and `POST /api/sessions` (create).
    (`POST .../start` takes no body on WAHA: it can never carry config.)"""
    verb = method.upper()
    ps = _paths(path)
    return (verb == "PUT" and all(_SESSION_CONFIG_PUT.match(p) for p in ps)) or (
        verb == "POST" and all(_SESSION_CREATE.match(p) for p in ps))


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


def _host_only(base_url: str) -> str:
    """Lower-cased hostname without IPv6 brackets or a trailing dot (``waha-x.`` is ``waha-x``)."""
    raw = (base_url or "").strip()
    sp = urlsplit(raw if "://" in raw else "http://" + raw)
    return (sp.hostname or "").lower().rstrip(".")


def _host_key(base_url: str) -> str:
    """Normalised HOST:PORT -- never the URL string. Spelling (case, trailing slash/dot, scheme, default port, path,
    IPv6 brackets) cannot make one line look like another."""
    raw = (base_url or "").strip()
    sp = urlsplit(raw if "://" in raw else "http://" + raw)
    port = sp.port or (443 if sp.scheme == "https" else 80)
    return f"{_host_only(raw)}:{port}"


# --- address-level aliasing (container IP, container id, env-overridden base URL) -------------------------------------
#: ``host -> set of resolved addresses`` resolver. A SEAM (DI), not a patch point: tests inject a table; production uses
#: getaddrinfo. Raising / returning None means "cannot resolve".
HostResolver = Any
_resolve_host: "Any" = None
_clock: "Any" = None
#: host -> (resolved-at, addresses). SHORT TTL: a container can be recreated with another IP; a forever-cache would keep
#: matching the old one and let the new address fall through to "*".
_ADDR_TTL = 60.0
_addr_cache: "dict[str, tuple[float, frozenset[str] | None]]" = {}


def set_host_resolver(fn: "Any | None", *, _test_clock: "Any | None" = None) -> None:
    """Inject ``fn(host) -> iterable[str] | None``: a product's OWN extra DNS view. It can only ADD matches -- its answer is
    unioned with ``getaddrinfo`` and never replaces it, so an injected resolver cannot make a read-only machine look like
    something else. ``_test_clock`` is a TEST-ONLY monotonic clock (for the TTL); production code never passes it."""
    global _resolve_host, _clock
    with _lock:
        _resolve_host, _clock = fn, _test_clock
        _addr_cache.clear()


def _now() -> float:
    import time

    return (_clock or time.monotonic)()


def _norm_ip(value: str) -> str:
    """Canonical address text; an IPv4-mapped IPv6 (``::ffff:10.0.0.5``) is the IPv4 address."""
    import ipaddress

    try:
        ip = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return value
    mapped = getattr(ip, "ipv4_mapped", None)
    return str(mapped if mapped is not None else ip)


def _default_resolver(host: str) -> "set[str] | None":
    import socket

    try:
        return {ai[4][0] for ai in socket.getaddrinfo(host, None)}
    except OSError:
        return None


def _addrs(host: str) -> "frozenset[str] | None":
    """Resolved addresses of ``host`` (an IP literal is itself), cached for ``_ADDR_TTL`` -- FAILURES too, so a dead name
    costs one lookup per TTL, not one per request; None = unresolvable. getaddrinfo is blocking: callers on an event loop
    go through :func:`aresolve_line_policy`."""
    import ipaddress

    try:
        ipaddress.ip_address(host.split("%", 1)[0])
        return frozenset({_norm_ip(host)})
    except ValueError:
        pass
    hit = _addr_cache.get(host)
    if hit is not None and _now() - hit[0] < _ADDR_TTL:
        return hit[1]
    found: set[str] = set()
    for resolver in (_default_resolver, _resolve_host):   # injected answers are UNIONED, never a replacement
        if resolver is None:
            continue
        try:
            found |= set(resolver(host) or ())
        except Exception:  # noqa: BLE001 - a resolver failure is "unknown", which fails closed below
            pass
    out = frozenset(_norm_ip(str(a)) for a in found) if found else None
    with _lock:
        _addr_cache[host] = (_now(), out)  # type: ignore[assignment]
    return out


def _is_ip_literal(host: str) -> bool:
    import ipaddress

    try:
        ipaddress.ip_address(host.split("%", 1)[0])
        return True
    except ValueError:
        return False


def _key(base_url: str, session: Optional[str]) -> str:
    base = _host_key(base_url)
    return f"{base}#{session}" if session else base


#: host:port -> policy for every line that is read-only, runtime part. STICKY: registering a `send: disabled` line adds
#: it (all its spellings of the same host:port); nothing removes it except `clear_line_policies` (tests).
_runtime_read_only: dict[str, LinePolicy] = {}


_GENERATED_MODULE = "noctusai_lib.integrations.whatsapp.read_only_lines"


#: TEST SEAM (like :func:`set_host_resolver`): a suite that is not about the fleet's declared lines swaps the generated
#: read-only set for its own table (rows, resolvable). Production never calls it; :func:`clear_line_policies` restores
#: the generated module.
_generated_override: "tuple[dict[str, Any], tuple[str, ...] | None] | None" = None


def set_generated_read_only(rows: "Mapping[str, Any] | None", resolvable: "tuple[str, ...] | None" = None) -> None:
    """Replace (``rows`` = {host:port: policy-spec}) or, with ``None``, restore the generated read-only set."""
    global _generated_override
    with _lock:
        _generated_override = None if rows is None else (dict(rows), resolvable)
        _addr_cache.clear()


def _generated_read_only(module: str = _GENERATED_MODULE) -> dict[str, LinePolicy]:
    import importlib

    if _generated_override is not None and module == _GENERATED_MODULE:
        return {h: parse_line_policy(spec) for h, spec in _generated_override[0].items()}
    try:
        rows = importlib.import_module(module).READ_ONLY_LINES
    except (ImportError, AttributeError) as exc:  # absent ceiling = we cannot know which lines are read-only: refuse
        raise LinePolicyError(
            "read_only_lines.py (generated from deploy/fleet/waha-instances.yml by noctus.dev.waha_instance render) "
            "is missing or malformed: the read-only host set is unknown"
        ) from exc
    return {h: parse_line_policy(spec) for h, spec in rows.items()}


def _all_read_only() -> dict[str, LinePolicy]:
    out = dict(_generated_read_only())
    for h, p in _runtime_read_only.items():
        out[h] = strictest(out[h], p) if h in out else p
    return out


def _resolvable_hosts(module: str = _GENERATED_MODULE) -> "frozenset[str] | None":
    """Hosts of the GENERATED read-only set that resolve from the product network (noctus-net): the edge aliases. The
    `-core` names live on a private network and never resolve from a product, so they are matched BY NAME only -- counting
    them as "unresolvable aliases" would fail every unrelated host closed. None = the module does not say (all count)."""
    import importlib

    if _generated_override is not None and module == _GENERATED_MODULE:
        res = _generated_override[1]
        return frozenset(res) if res is not None else None
    try:
        rows = getattr(importlib.import_module(module), "RESOLVABLE_FROM_PRODUCT_NETWORK", None)
    except ImportError:
        return None
    return frozenset(rows) if rows is not None else None


def address_alias_candidates(
    all_ro: "dict[str, LinePolicy]", generated: "dict[str, LinePolicy]", resolvable: "frozenset[str] | None"
) -> "dict[str, LinePolicy]":
    """The read-only aliases whose ADDRESS is compared with a request host: every runtime-registered one, plus the
    generated ones that are resolvable from the product network."""
    if resolvable is None:
        return dict(all_ro)
    return {a: p for a, p in all_ro.items()
            if a not in generated or a.rsplit(":", 1)[0] in resolvable}


def _read_only_for(host_key: str) -> Optional[LinePolicy]:
    gen = _generated_read_only().get(host_key)
    rt = _runtime_read_only.get(host_key)
    if gen and rt:
        return strictest(gen, rt)
    return gen or rt


def strictest(a: LinePolicy, b: LinePolicy) -> LinePolicy:
    """The tighter of two policies: `disabled` wins, every flag is the AND, the webhook relay of the disabled one."""
    disabled_one = a if not a.send_enabled else b
    return LinePolicy(
        SEND_ENABLED if (a.send_enabled and b.send_enabled) else SEND_DISABLED,
        a.mark_online and b.mark_online, a.full_sync and b.full_sync, a.auto_repair and b.auto_repair,
        declared=a.declared or b.declared, config_authority=a.config_authority or b.config_authority,
        # two different relays: neither wins -- no relay at all (no webhook may be registered) is the strict answer
        webhook_relay=(a.webhook_relay if a.webhook_relay == b.webhook_relay
                       else (disabled_one.webhook_relay if (a.send_enabled != b.send_enabled) else None)),
    )


def _looser(new: LinePolicy, prior: LinePolicy) -> bool:
    """`new` allows something `prior` forbids. A DIFFERENT webhook relay on a read-only line is a loosening too: the
    relay is where the core is allowed to send, and the declared one is the only one."""
    return (
        (not prior.send_enabled and bool(prior.webhook_relay) and new.webhook_relay != prior.webhook_relay)
        or
        (new.send_enabled and not prior.send_enabled)
        or (new.mark_online and not prior.mark_online)
        or (new.full_sync and not prior.full_sync)
        or (new.auto_repair and not prior.auto_repair)
    )


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
    lines are DB-sourced); it cannot carry a session. A strict line is never given a ``"*"``.

    `send: disabled` is STICKY: a host:port that is (or becomes) read-only can never be re-registered with a looser
    policy (:class:`LinePolicyError`), and ``"*"`` never resolves for it."""
    if base_url == "*" and session:
        raise LinePolicyError('"*" is the process-wide default and cannot be scoped to a session')
    _check_registrable(base_url, policy, allow_memory_sink)
    with _lock:
        if base_url == "*":
            prior = _registry.get("*")
            if prior is not None and _looser(policy, prior):
                raise LinePolicyError('"*" is already registered with a stricter policy; it cannot be loosened')
            _registry["*"] = replace(policy, config_authority=False)
            return
        hk, key = _host_key(base_url), _key(base_url, session)
        for prior in (_registry.get(key), _registry.get(hk), _read_only_for(hk)):
            if prior is not None and _looser(policy, prior):
                raise LinePolicyError(
                    f"line {base_url!r}: refusing to loosen an already declared policy ({prior.as_json()}); "
                    "a read-only line is sticky for the life of the process"
                )
        _registry[key] = policy
        if not policy.send_enabled:
            _runtime_read_only[hk] = strictest(_runtime_read_only[hk], policy) if hk in _runtime_read_only else policy


def clear_line_policies() -> None:
    global _env_loaded, _generated_override
    with _lock:
        _generated_override = None
        _registry.clear()
        _runtime_read_only.clear()
        _addr_cache.clear()
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


def resolve_line_policy(
    base_url: str, session: Optional[str] = None, *, explicit: Optional[LinePolicy] = None
) -> LinePolicy:
    """The STRICTEST of: the explicit policy, the registry entry ((host,session) -> host -> ``"*"``), and the seed's
    read-only host set (generated from waha-instances.yml + every disabled line registered at runtime). ``"*"`` is never
    consulted for a read-only host. Nothing found -> :data:`UNDECLARED` (fail-closed). A policy can only ever get
    stricter on the way in, so no code path can loosen a declared read-only line."""
    global _env_loaded
    if not _env_loaded:
        load_line_policies_from_env()  # raises on a bad value: loud on EVERY call, never a silent UNDECLARED
        _env_loaded = True
    hk = _host_key(base_url)
    with _lock:
        ro = _read_only_for(hk)
        # BOTH the session entry and the host entry, never "session else host": a stricter host-level policy must not
        # be shadowed by a looser session entry (security re-check, 2026-11-10).
        _sess_reg, _host_reg = _registry.get(_key(base_url, session)), _registry.get(hk)
        explicit_reg = (strictest(_sess_reg, _host_reg) if _sess_reg is not None and _host_reg is not None
                        else _sess_reg or _host_reg)
        reg = explicit_reg
        all_ro = _all_read_only()
    if ro is None and all_ro and not base_url.startswith("fake://"):
        # not a known alias BY NAME: it may still be the same machine (container IP, container id, an env-overridden
        # base URL). Compare resolved addresses; if the host cannot be resolved, fail CLOSED unless it is positively
        # known to be a send-enabled line (an explicit, non-"*" registry entry).
        host = _host_only(base_url)
        mine = _addrs(host)
        positively_enabled = explicit_reg is not None and explicit_reg.send_enabled
        if mine is None:
            if not positively_enabled:
                return UNDECLARED
        else:
            unresolved_alias = False
            gen_rows = _generated_read_only()
            for alias, pol in address_alias_candidates(all_ro, gen_rows, _resolvable_hosts()).items():
                theirs = _addrs(alias.rsplit(":", 1)[0])
                if theirs is None:
                    unresolved_alias = True
                elif theirs & mine:
                    ro = pol
                    break
            # an IP literal could be the address of a read-only alias we cannot resolve right now: fail CLOSED. A NAME that
            # resolves cannot be a down alias of the same machine (an up container answers to every one of its names on the
            # network; a down one answers to none), so a down read-only edge must not refuse every other sender
            # (2026-11-10: waha-assistant down == a fleet-wide WhatsApp outage). The edge's own nginx deny + the private
            # core network stay as the second layer.
            if ro is None and unresolved_alias and not positively_enabled and _is_ip_literal(host):
                return UNDECLARED
    if reg is None and ro is None:
        with _lock:
            reg = _registry.get("*")
    found = [p for p in (explicit, reg, ro) if p is not None]
    if not found:
        return UNDECLARED
    out = found[0]
    for p in found[1:]:
        out = strictest(out, p)
    gen = _generated_read_only().get(hk)
    if gen is not None and gen.webhook_relay:
        out = replace(out, webhook_relay=gen.webhook_relay)  # the generated ceiling's relay is authoritative
    return out


async def aresolve_line_policy(
    base_url: str, session: Optional[str] = None, *, explicit: Optional[LinePolicy] = None
) -> LinePolicy:
    """:func:`resolve_line_policy` for a running event loop: the blocking getaddrinfo runs in a worker thread, and only when
    this process has a read-only line at all (otherwise there is no DNS to do and no thread hop)."""
    import asyncio

    if not _all_read_only_nonempty():
        return resolve_line_policy(base_url, session, explicit=explicit)
    return await asyncio.to_thread(resolve_line_policy, base_url, session, explicit=explicit)


def _all_read_only_nonempty() -> bool:
    with _lock:
        return bool(_all_read_only())


# --- the guard both WahaClient and FakeWahaClient share --------------------------------------------------------------


class LinePolicyGuard:
    """Mixin: ``self.line_policy``, ``self.line_event_sink``, ``self._line_label``. One implementation of "refuse,
    record, raise" so the Real and the Fake cannot drift."""

    line_policy: LinePolicy
    line_event_sink: LineEventSink
    _line_label: str

    def _init_line_policy(
        self, *, label: str, policy: LinePolicy, sink: Optional[LineEventSink],
        resolve_args: "Optional[tuple[str, Optional[str], Optional[LinePolicy]]]" = None,
    ) -> None:
        self._line_label = label
        self._policy_resolve_args = resolve_args
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

    async def _arefresh_policy(self) -> None:
        args = getattr(self, "_policy_resolve_args", None)
        if args:
            self.line_policy = strictest(self.line_policy, await aresolve_line_policy(args[0], args[1], explicit=args[2]))

    def _refresh_policy(self) -> None:
        """Re-resolve right before a request leaves (DNS can move: a container recreated with a new IP). The policy can
        only get STRICTER: the fresh answer is merged with the current one, never replaces it with a looser one."""
        args = getattr(self, "_policy_resolve_args", None)
        if not args:
            return
        fresh = resolve_line_policy(args[0], args[1], explicit=args[2])
        self.line_policy = strictest(self.line_policy, fresh)

    def _final_url_hook(self, policy_config: bool = False):
        """httpx request event hook (sync + async twins): re-judges the FINAL request URL after httpx has built and
        normalised it, so no spelling of the path can slip past the pre-check."""
        def check(request) -> None:
            self._refresh_policy()
            self._guard_write(request.method, request.url.raw_path.decode('ascii', 'replace'), policy_config=policy_config)

        async def acheck(request) -> None:
            await self._arefresh_policy()   # DNS off the event loop
            self._guard_write(request.method, request.url.raw_path.decode('ascii', 'replace'), policy_config=policy_config)

        return check, acheck

    def _guard_webhook(self, url: str) -> None:
        """On a disabled line a webhook may only be (re)registered under the declared relay base (the edge's 3001)."""
        if self.line_policy.send_enabled:
            return
        relay = (self.line_policy.webhook_relay or "").rstrip("/")
        if relay and (url == relay or url.startswith(relay + "/")):
            return
        reason = "webhook_url_not_relay" if self.line_policy.declared else "no_line_policy"
        self.line_event_sink.record(LineEvent(
            EVENT_WRITE_REFUSED, self._line_label, "PUT /api/sessions/*/webhooks", reason, self.line_policy.as_dict()))
        raise LineWriteRefused(line=self._line_label, method="PUT", path="/api/sessions/*/webhooks", reason=reason)

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
