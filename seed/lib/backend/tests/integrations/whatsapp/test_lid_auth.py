"""@lid 3-tier authorization + canonical-session resolution.

Validates the reconcile to workspace commit ``598f8f7`` (LID-aware
auth, SESSION-NOTES §4.2). lid_auth.py shipped without colocated
tests — this closes that gap as part of the Wave 1.E2 reconcile.
"""

from noctusai_lib.integrations.whatsapp import (
    InMemoryLidPhoneCache,
    LidPhoneCache,
    RedisLidPhoneCache,
    extract_resolved_remote,
    get_lid_phone_cache,
    is_authorized,
    is_lid,
    is_phone_jid,
    normalize_phone,
    remember_lid_phone,
    resolve_canonical_session,
)
from noctusai_lib.integrations.redis import make_fake_redis_client

_LID = "33613018058989@lid"
_PHONE_JID = "5511974693365@c.us"


def test_normalize_phone_strips_plus_and_suffix() -> None:
    assert normalize_phone("+5511974693365") == "5511974693365"
    assert normalize_phone(_PHONE_JID) == "5511974693365"


def test_jid_classification() -> None:
    assert is_lid(_LID) and not is_phone_jid(_LID)
    assert is_phone_jid(_PHONE_JID) and not is_lid(_PHONE_JID)


def test_empty_whitelist_is_open() -> None:
    assert is_authorized(_LID, phone_whitelist=[]) is True


def test_tier1_raw_lid_whitelist_verbatim() -> None:
    assert is_authorized(
        _LID, phone_whitelist=["999"], raw_lid_whitelist=[_LID]
    ) is True


def test_tier2_phone_form() -> None:
    assert is_authorized(
        _PHONE_JID, phone_whitelist=["+5511974693365"]
    ) is True
    assert is_authorized(
        "5599999999999@c.us", phone_whitelist=["+5511974693365"]
    ) is False


def test_tier3_lid_via_cache_binding() -> None:
    cache = InMemoryLidPhoneCache()
    # No binding yet → unauthorized.
    assert is_authorized(
        _LID, phone_whitelist=["5511974693365"], cache=cache
    ) is False
    cache.bind(_LID, _PHONE_JID)
    assert is_authorized(
        _LID, phone_whitelist=["5511974693365"], cache=cache
    ) is True


def test_extract_resolved_remote_from_send_response() -> None:
    assert extract_resolved_remote(
        {"_data": {"id": {"remote": _PHONE_JID}}}
    ) == _PHONE_JID
    assert extract_resolved_remote({"id": {"remote": _PHONE_JID}}) == _PHONE_JID
    assert extract_resolved_remote({}) is None


def test_remember_lid_phone_binds_only_for_lid_and_phone_jid() -> None:
    cache = InMemoryLidPhoneCache()
    remember_lid_phone(cache, lid_chat_id=_LID, resolved_remote=_PHONE_JID)
    assert cache.get_phone_for_lid(_LID) == "5511974693365"

    cache2 = InMemoryLidPhoneCache()
    remember_lid_phone(cache2, lid_chat_id=_PHONE_JID, resolved_remote=_PHONE_JID)
    assert cache2.get_phone_for_lid(_PHONE_JID) is None


def test_canonical_session_collapses_lid_and_phone_to_one_key() -> None:
    cache = InMemoryLidPhoneCache()
    assert resolve_canonical_session(_PHONE_JID, cache) == "wa:5511974693365"
    # Unbound LID → isolated stable key.
    assert resolve_canonical_session(_LID, cache) == "wa:lid:33613018058989"
    # Bound LID → same key as the phone JID.
    cache.bind(_LID, _PHONE_JID)
    assert resolve_canonical_session(_LID, cache) == "wa:5511974693365"


def test_factory_and_protocol() -> None:
    assert isinstance(get_lid_phone_cache(), InMemoryLidPhoneCache)
    real = get_lid_phone_cache(redis_client=make_fake_redis_client())
    assert isinstance(real, RedisLidPhoneCache)
    assert isinstance(InMemoryLidPhoneCache(), LidPhoneCache)
    assert isinstance(real, LidPhoneCache)
