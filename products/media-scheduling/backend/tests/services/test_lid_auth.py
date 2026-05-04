"""LID-aware first-inbound capture.

Ported from `whatsapp-google-scheduling/tests/test_lid_aware_auth.py`.

Source-side: SQLAlchemy-backed `AuthorizationService` over `users` +
`pending_chat_identities`.
Product-side: `app.services.lid_auth.LidAuthService` runs against the
Supabase admin client (RLS-bypass; webhook path runs as service_role).

Resolution order (mirror of source):
  1. `@lid_*` chat_id → `authorized_users.linked_identity == chat_id` direct hit.
  2. else / miss → phone fallback against `authorized_users.phone_number`.
  3. phone hit + LID present + LID not yet stored → opportunistic capture.
  4. unknown LID → caller can `capture_pending_lid(...)` for admin review.

Helpers `looks_like_lid` and `normalize_phone_number` are pure functions.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.lid_auth import (
    LidAuthService,
    looks_like_lid,
    normalize_phone_number,
)


# ---------------------------------------------------------------------------
# Minimal Supabase admin-client stub. Tracks state across queries so
# updates flowing from path-3 capture are observable on subsequent reads.
# ---------------------------------------------------------------------------


@dataclass
class _StubResponse:
    data: list[dict]


class _Builder:
    def __init__(self, table_name: str, store: dict[str, list[dict]]):
        self._table = table_name
        self._store = store
        self._filters: list[tuple[str, object]] = []
        self._pending_update: dict | None = None
        self._pending_insert: dict | None = None
        self._mode: str = "select"
        self._limit: int | None = None

    def select(self, *_args, **_kwargs) -> "_Builder":
        self._mode = "select"
        return self

    def update(self, payload: dict) -> "_Builder":
        self._mode = "update"
        self._pending_update = payload
        return self

    def insert(self, payload: dict) -> "_Builder":
        self._mode = "insert"
        self._pending_insert = payload
        return self

    def eq(self, col: str, value: object) -> "_Builder":
        self._filters.append((col, value))
        return self

    def limit(self, n: int) -> "_Builder":
        self._limit = n
        return self

    def execute(self) -> _StubResponse:
        rows = self._store.setdefault(self._table, [])
        if self._mode == "select":
            matched = [
                r for r in rows
                if all(r.get(c) == v for c, v in self._filters)
            ]
            if self._limit is not None:
                matched = matched[: self._limit]
            return _StubResponse(data=matched)

        if self._mode == "update":
            assert self._pending_update is not None
            updated: list[dict] = []
            for r in rows:
                if all(r.get(c) == v for c, v in self._filters):
                    r.update(self._pending_update)
                    updated.append(r)
            return _StubResponse(data=updated)

        if self._mode == "insert":
            assert self._pending_insert is not None
            new = dict(self._pending_insert)
            new.setdefault("id", len(rows) + 1)
            rows.append(new)
            return _StubResponse(data=[new])

        raise AssertionError(f"unexpected mode {self._mode!r}")


class _StubAdminClient:
    """Mimics the Supabase admin client surface `LidAuthService` exercises:
    `.table("authorized_users").select(...).eq(...).execute()` and update/insert.
    Note: the service does NOT call `.schema(...)` on the admin client (per
    Phase 3 design — admin path uses a service-role schema-bound client)."""

    def __init__(self, store: dict[str, list[dict]]):
        self._store = store

    def table(self, name: str) -> _Builder:
        return _Builder(name, self._store)


def _seed_store() -> dict[str, list[dict]]:
    return {
        "authorized_users": [
            {
                "id": 2,
                "name": "Ana Corretora",
                "role": "real_estate_agent",
                "phone_number": "+5511999999999",
                "email": "ana@example.com",
                "linked_identity": None,
                "active": True,
            },
            {
                "id": 5,
                "name": "Corretor Inativo",
                "role": "real_estate_agent",
                "phone_number": "+5511666666666",
                "email": "inactive@example.com",
                "linked_identity": None,
                "active": False,
            },
        ],
        "pending_chat_identities": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_phone_lookup_still_works() -> None:
    store = _seed_store()
    auth = LidAuthService(_StubAdminClient(store))

    user = auth.authorized_user_for_phone("+5511999999999")

    assert user is not None
    assert user["name"] == "Ana Corretora"


def test_chat_id_at_c_us_resolves_via_phone() -> None:
    """Standard `<digits>@c.us` falls through to phone match — no LID capture."""
    store = _seed_store()
    auth = LidAuthService(_StubAdminClient(store))

    user = auth.authorized_user_for_chat_id(
        "5511999999999@c.us",
        from_phone="+5511999999999",
    )

    assert user is not None
    assert user["name"] == "Ana Corretora"
    # No LID to capture — linked_identity stays None.
    assert user.get("linked_identity") is None


def test_first_lid_inbound_captures_lid_on_user_row() -> None:
    """Path 3: LID + matching phone → opportunistically attach the LID."""
    store = _seed_store()
    auth = LidAuthService(_StubAdminClient(store))
    chat_id = "5511999999999@lid_abcdef0123456789"

    user = auth.authorized_user_for_chat_id(
        chat_id,
        from_phone="+5511999999999",
    )

    assert user is not None
    assert user["name"] == "Ana Corretora"
    assert user["linked_identity"] == chat_id

    # Verify it persisted to the store, not just the in-memory dict.
    persisted = next(r for r in store["authorized_users"] if r["id"] == 2)
    assert persisted["linked_identity"] == chat_id


def test_subsequent_lid_inbound_resolves_via_path_1() -> None:
    """After capture, the same LID resolves WITHOUT needing a phone hint."""
    store = _seed_store()
    auth = LidAuthService(_StubAdminClient(store))
    chat_id = "5511999999999@lid_x"

    auth.authorized_user_for_chat_id(chat_id, from_phone="+5511999999999")

    # No phone supplied — must hit via path 1 (LID direct match).
    user = auth.authorized_user_for_chat_id(chat_id, from_phone=None)
    assert user is not None
    assert user["name"] == "Ana Corretora"


def test_unknown_lid_with_unknown_phone_returns_none() -> None:
    """No phone match, no LID match → caller is on its own."""
    store = _seed_store()
    auth = LidAuthService(_StubAdminClient(store))

    user = auth.authorized_user_for_chat_id(
        "5500000000000@lid_zzz",
        from_phone="+5500000000000",
    )

    assert user is None


def test_inactive_user_does_not_match_via_lid() -> None:
    """Even if a LID is on an inactive user row, lookups must skip them."""
    store = _seed_store()
    # Hand-attach a LID to the inactive user.
    inactive = next(r for r in store["authorized_users"] if r["id"] == 5)
    inactive["linked_identity"] = "5511666666666@lid_inactive"

    auth = LidAuthService(_StubAdminClient(store))

    assert (
        auth.authorized_user_for_chat_id(
            "5511666666666@lid_inactive",
            from_phone=None,
        )
        is None
    )


def test_capture_pending_lid_creates_row() -> None:
    store = _seed_store()
    auth = LidAuthService(_StubAdminClient(store))

    pending = auth.capture_pending_lid(
        "5500000000000@lid_unknown",
        push_name="Mystery User",
        phone_hint="+5500000000000",
    )

    assert pending is not None
    assert pending["status"] == "pending"
    assert pending["push_name"] == "Mystery User"
    assert pending["phone_hint"] == "+5500000000000"


def test_capture_pending_lid_is_idempotent_on_chat_id() -> None:
    store = _seed_store()
    auth = LidAuthService(_StubAdminClient(store))

    first = auth.capture_pending_lid(
        "5500000000000@lid_dup",
        push_name="Carlos",
    )
    second = auth.capture_pending_lid(
        "5500000000000@lid_dup",
        push_name="Carlos",
        phone_hint="+5500000000000",
    )

    assert first is not None and second is not None
    assert first["id"] == second["id"]
    # phone_hint backfilled on the second call (first didn't supply it).
    assert second["phone_hint"] == "+5500000000000"

    # Only one row in the store — idempotent on chat_id.
    rows = [
        r for r in store["pending_chat_identities"]
        if r.get("chat_id") == "5500000000000@lid_dup"
    ]
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_looks_like_lid_helper() -> None:
    assert looks_like_lid("5511999999999@lid_abc") is True
    assert looks_like_lid("5511999999999@lid") is True
    assert looks_like_lid("5511999999999@c.us") is False
    assert looks_like_lid(None) is False
    assert looks_like_lid("") is False


def test_normalize_phone_number_strips_to_e164() -> None:
    assert normalize_phone_number("+55 (11) 99999-9999") == "+5511999999999"
    assert normalize_phone_number("5511999999999@c.us") == "+5511999999999"
    assert normalize_phone_number("") == ""
