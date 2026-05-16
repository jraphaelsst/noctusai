"""WhatsApp @lid identity resolution + whitelist authorization.

Reconciled to the live-validated `noctusai-youtube-crawler` workspace
implementation (workspace commit `598f8f7` — "LID-aware auth"). See
the noc handoff note `SESSION-NOTES_chatbot-multichannel-2026-05-12.md`
§4.2 for the production bug this closes.

The problem
-----------
Modern WhatsApp delivers inbound from a *linked-identity* address
``<random_digits>@lid`` (e.g. ``33613018058989@lid``). The @lid number
is **opaque** — it does NOT contain the phone number, and the same
human can present different LIDs in different chats. A naive
phone-form whitelist (strip ``@c.us`` / ``@s.whatsapp.net`` only)
silently rejects every @lid sender.

The 3-tier resolution (validated in production)
-----------------------------------------------
``is_authorized(chat_id)`` accepts the message when ANY tier matches:

1. **Raw-LID whitelist** — the operator may whitelist a known raw LID
   string verbatim (``33613018058989@lid``). Cheapest, no IO.
2. **Phone form** — strip the JID suffix; if it is a ``@c.us`` /
   ``@s.whatsapp.net`` JID the bare digits ARE the phone, compare to
   the phone whitelist.
3. **Redis lid↔phone cache** — for a ``@lid`` chat_id, look up the
   phone previously bound to that LID. The binding is populated
   *opportunistically* from outbound send responses (WAHA returns the
   resolved ``_data.id.remote`` ``@c.us`` JID), via
   ``remember_lid_phone(...)``. First-contact-from-LID before any
   outbound is correctly unauthorized until the bind exists.

The cache is an injectable seam (Protocol + Fake + Real + factory)
mirroring `KB § PATTERNS/seed-fake-real-adapter.md` so tests exercise
the real resolution logic against an in-memory store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redis import Redis

_LID_SUFFIX = "@lid"
_PHONE_JID_SUFFIXES = ("@c.us", "@s.whatsapp.net")
_DEFAULT_CACHE_PREFIX = "wa:lid_phone:"


def normalize_phone(value: str) -> str:
    """Reduce a phone / JID local-part to bare digits (no ``+``, no suffix).

    ``+5511974693365`` → ``5511974693365``;
    ``5511974693365@c.us`` → ``5511974693365``.
    """
    local = value.split("@", 1)[0]
    return local.lstrip("+").strip()


def is_lid(chat_id: str) -> bool:
    """True when ``chat_id`` is a WhatsApp linked-identity address."""
    return chat_id.endswith(_LID_SUFFIX)


def is_phone_jid(chat_id: str) -> bool:
    """True when ``chat_id`` is a phone-bearing JID (``@c.us`` / ``@s.whatsapp.net``)."""
    return chat_id.endswith(_PHONE_JID_SUFFIXES)


@runtime_checkable
class LidPhoneCache(Protocol):
    """Bidirectional LID↔phone binding store.

    `@runtime_checkable` so consumers can ``isinstance(x, LidPhoneCache)``.
    Both `RedisLidPhoneCache` (real) and `InMemoryLidPhoneCache` (fake)
    satisfy this Protocol naturally — same shape as the buffer's
    `RedisBufferClient`.
    """

    def get_phone_for_lid(self, lid: str) -> str | None: ...

    def bind(self, lid: str, phone: str) -> None: ...


class InMemoryLidPhoneCache:
    """Deterministic in-memory LID↔phone cache (no network).

    The Fake half of the Fake+Real pair. Used in tests and as the
    dev/local fallback when no Redis URL is configured.
    """

    def __init__(self) -> None:
        self._lid_to_phone: dict[str, str] = {}

    def get_phone_for_lid(self, lid: str) -> str | None:
        return self._lid_to_phone.get(lid)

    def bind(self, lid: str, phone: str) -> None:
        self._lid_to_phone[lid] = normalize_phone(phone)

    def clear(self) -> None:
        """Reset between test cases."""
        self._lid_to_phone.clear()


class RedisLidPhoneCache:
    """Redis-backed LID↔phone cache.

    The Real half of the Fake+Real pair. Keys are
    ``<prefix><lid>`` → phone digits. No TTL by default: a LID↔phone
    binding is stable for the life of the linked device, and a stale
    binding fails closed (phone whitelist still applies).
    """

    def __init__(self, redis_client: "Redis", *, key_prefix: str = _DEFAULT_CACHE_PREFIX):
        self._redis = redis_client
        self._prefix = key_prefix

    def _key(self, lid: str) -> str:
        return f"{self._prefix}{lid}"

    def get_phone_for_lid(self, lid: str) -> str | None:
        value = self._redis.get(self._key(lid))
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode()
        return str(value)

    def bind(self, lid: str, phone: str) -> None:
        self._redis.set(self._key(lid), normalize_phone(phone))


def get_lid_phone_cache(
    *,
    redis_client: "Redis | None" = None,
    key_prefix: str = _DEFAULT_CACHE_PREFIX,
) -> LidPhoneCache:
    """Return `RedisLidPhoneCache` when a Redis client is supplied;
    `InMemoryLidPhoneCache` otherwise.

    Mirrors `get_whatsapp_client()` / `get_calendar_adapter()` factory
    shape per `KB § PATTERNS/seed-fake-real-adapter.md`. The presence
    of a Redis client is the configured-vs-not signal.
    """
    if redis_client is None:
        return InMemoryLidPhoneCache()
    return RedisLidPhoneCache(redis_client, key_prefix=key_prefix)


def remember_lid_phone(
    cache: LidPhoneCache,
    *,
    lid_chat_id: str,
    resolved_remote: str | None,
) -> None:
    """Opportunistically bind a LID to its phone from an outbound send response.

    WAHA's ``/api/sendText`` response carries the resolved JID at
    ``_data.id.remote`` (a ``@c.us`` form). When we sent TO a ``@lid``
    chat and WAHA resolved it to a phone JID, persist the binding so
    future inbound from that LID authorizes via tier 3.

    No-ops safely when ``lid_chat_id`` is not a LID or no phone JID
    could be extracted from the response.
    """
    if not is_lid(lid_chat_id):
        return
    if not resolved_remote or not is_phone_jid(resolved_remote):
        return
    cache.bind(lid_chat_id, normalize_phone(resolved_remote))


def extract_resolved_remote(send_response: dict) -> str | None:
    """Pull the resolved remote JID from a WAHA send-text response.

    WAHA shape (validated): ``{"_data": {"id": {"remote": "<jid>@c.us"}}}``.
    Tolerates the flatter ``{"id": {"remote": ...}}`` shape too. Returns
    None when absent — caller treats that as "no binding learned".
    """
    for container_key in ("_data", None):
        node = send_response if container_key is None else send_response.get(container_key)
        if not isinstance(node, dict):
            continue
        id_node = node.get("id")
        if isinstance(id_node, dict):
            remote = id_node.get("remote")
            if isinstance(remote, str) and remote:
                return remote
    return None


def resolve_canonical_session(chat_id: str, cache: LidPhoneCache) -> str:
    """Canonical, surface-agnostic session key for a WhatsApp chat_id.

    A LID and its phone JID for the same human MUST map to ONE session
    so conversation memory stays coherent across the @lid→phone switch
    (SESSION-NOTES §4.2). Resolution:

    - phone JID → ``wa:<phone-digits>``
    - LID with a known phone binding → ``wa:<bound-phone-digits>``
    - LID without a binding yet → ``wa:lid:<raw-lid-digits>`` (stable,
      isolated; migrates to the phone session once the bind lands —
      consumers copy memory on first capture if they need continuity)
    """
    if is_phone_jid(chat_id):
        return f"wa:{normalize_phone(chat_id)}"
    if is_lid(chat_id):
        bound = cache.get_phone_for_lid(chat_id)
        if bound:
            return f"wa:{normalize_phone(bound)}"
        return f"wa:lid:{normalize_phone(chat_id)}"
    return f"wa:{normalize_phone(chat_id)}"


def is_authorized(
    chat_id: str,
    *,
    phone_whitelist: Iterable[str],
    raw_lid_whitelist: Iterable[str] = (),
    cache: LidPhoneCache | None = None,
) -> bool:
    """3-tier whitelist authorization for an inbound WhatsApp chat_id.

    Tier 1 — raw-LID whitelist (verbatim string match, no IO).
    Tier 2 — phone form (works for ``@c.us`` / ``@s.whatsapp.net``).
    Tier 3 — Redis lid↔phone cache (only for ``@lid`` chat_ids; needs
             a prior outbound to have bound the LID).

    An empty ``phone_whitelist`` AND empty ``raw_lid_whitelist`` means
    "no whitelist configured" → open (returns True), matching the
    workspace's posture where an unset whitelist is unrestricted.
    """
    phones = {normalize_phone(p) for p in phone_whitelist if p}
    raw_lids = {r.strip() for r in raw_lid_whitelist if r}

    if not phones and not raw_lids:
        return True

    # Tier 1 — raw-LID verbatim.
    if chat_id.strip() in raw_lids:
        return True

    # Tier 2 — phone form (only meaningful for phone-bearing JIDs).
    if is_phone_jid(chat_id) and normalize_phone(chat_id) in phones:
        return True

    # Tier 3 — LID → phone via cache.
    if is_lid(chat_id) and cache is not None:
        bound = cache.get_phone_for_lid(chat_id)
        if bound and normalize_phone(bound) in phones:
            return True

    return False
