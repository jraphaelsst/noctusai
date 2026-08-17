"""Unit tests for `noctusai_lib.security.webhook_signatures`.

Covers all four signature shapes the platform speaks:
  - HMAC-SHA256 with `sha256=…` prefix (Meta, GitHub)
  - Bare HMAC-SHA256 hex (WAHA, internal)
  - Svix protocol (Resend)
  - HTTP Basic shared secret (Grupo OLX leads)

The helpers MUST be constant-time (use `hmac.compare_digest`); these
tests exercise the success paths plus several tampering / wrong-secret
paths that should reject.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from noctusai_lib.security.webhook_signatures import (
    GRUPO_OLX_BASIC_USERNAME,
    compute_hmac_sha256_hex,
    verify_basic_shared_secret,
    verify_hmac_sha256,
    verify_hmac_sha256_hex,
    verify_svix_signature,
)


# -- Pattern 1: sha256=<hex> -----------------------------------------------


def test_verify_hmac_sha256_accepts_correctly_signed_body():
    secret = "shared-secret"
    body = b'{"event":"lead.created"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_hmac_sha256(body, sig, secret) is True


def test_verify_hmac_sha256_rejects_tampered_body():
    secret = "shared-secret"
    body = b'{"event":"lead.created"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_hmac_sha256(b'{"event":"lead.deleted"}', sig, secret) is False


def test_verify_hmac_sha256_rejects_wrong_secret():
    body = b"x"
    sig = "sha256=" + hmac.new(b"right-secret", body, hashlib.sha256).hexdigest()

    assert verify_hmac_sha256(body, sig, "wrong-secret") is False


def test_verify_hmac_sha256_rejects_missing_signature_or_secret():
    assert verify_hmac_sha256(b"x", "", "secret") is False
    assert verify_hmac_sha256(b"x", "sha256=abc", "") is False


# -- Pattern 2: bare hex ---------------------------------------------------


def test_compute_hmac_sha256_hex_matches_stdlib():
    secret = "k"
    body = b"payload"
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert compute_hmac_sha256_hex(body, secret) == expected


def test_verify_hmac_sha256_hex_accepts_correctly_signed_body():
    secret = "k"
    body = b"payload"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_hmac_sha256_hex(body, sig, secret) is True


def test_verify_hmac_sha256_hex_rejects_tampered_body():
    secret = "k"
    body = b"payload"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_hmac_sha256_hex(b"different", sig, secret) is False


def test_verify_hmac_sha256_hex_rejects_missing_inputs():
    assert verify_hmac_sha256_hex(b"x", "", "secret") is False
    assert verify_hmac_sha256_hex(b"x", "abc", "") is False


# -- Replay-window guard ---------------------------------------------------


def _fresh_sig(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_hmac_sha256_accepts_when_timestamp_is_fresh():
    import time

    secret = "k"
    body = b"x"
    sig = _fresh_sig(body, secret)

    assert verify_hmac_sha256(
        body, sig, secret,
        timestamp_value=int(time.time()),
    ) is True


def test_verify_hmac_sha256_rejects_expired_timestamp():
    import time

    secret = "k"
    body = b"x"
    sig = _fresh_sig(body, secret)
    # 1 hour ago, default 300s window
    assert verify_hmac_sha256(
        body, sig, secret,
        timestamp_value=int(time.time()) - 3600,
    ) is False


def test_verify_hmac_sha256_rejects_future_timestamp_outside_window():
    import time

    secret = "k"
    body = b"x"
    sig = _fresh_sig(body, secret)
    # 1 hour in the future — clock-skew abuse
    assert verify_hmac_sha256(
        body, sig, secret,
        timestamp_value=int(time.time()) + 3600,
    ) is False


def test_verify_hmac_sha256_no_timestamp_means_no_replay_check():
    """Default behavior — `timestamp_value=None` opts out cleanly."""
    secret = "k"
    body = b"x"
    sig = _fresh_sig(body, secret)
    assert verify_hmac_sha256(body, sig, secret) is True


def test_verify_hmac_sha256_hex_replay_window_applies():
    import time

    secret = "k"
    body = b"x"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    assert verify_hmac_sha256_hex(
        body, sig, secret, timestamp_value=int(time.time()) - 3600,
    ) is False
    assert verify_hmac_sha256_hex(
        body, sig, secret, timestamp_value=int(time.time()),
    ) is True


# -- Pattern 3: Svix -------------------------------------------------------


def _svix_secret_and_signature(body: bytes, svix_id: str, svix_timestamp: str) -> tuple[str, str]:
    """Generate a valid (secret, signature_header) pair for the given message."""
    secret_bytes = b"the-actual-key-bytes"
    secret_b64 = base64.b64encode(secret_bytes).decode("ascii")
    payload = f"{svix_id}.{svix_timestamp}.{body.decode()}".encode("utf-8")
    sig = base64.b64encode(hmac.new(secret_bytes, payload, hashlib.sha256).digest()).decode("ascii")
    return secret_b64, f"v1,{sig}"


def test_verify_svix_signature_accepts_valid_payload():
    body = b'{"type":"email.delivered"}'
    secret_b64, sig_header = _svix_secret_and_signature(body, "msg_1", "1700000000")

    assert verify_svix_signature(
        svix_id="msg_1",
        svix_timestamp="1700000000",
        body=body,
        signature_header=sig_header,
        secret=secret_b64,
    ) is True


def test_verify_svix_signature_accepts_whsec_prefixed_secret():
    body = b'{"x":1}'
    secret_b64, sig_header = _svix_secret_and_signature(body, "m", "1")

    assert verify_svix_signature(
        svix_id="m",
        svix_timestamp="1",
        body=body,
        signature_header=sig_header,
        secret=f"whsec_{secret_b64}",
    ) is True


def test_verify_svix_signature_handles_multiple_versions_in_header():
    body = b"hi"
    secret_b64, real_sig = _svix_secret_and_signature(body, "m", "1")
    # Real header from Svix often carries a stale + current key for rotation:
    multi = f"v1,old-stale-base64-junk {real_sig}"

    assert verify_svix_signature(
        svix_id="m",
        svix_timestamp="1",
        body=body,
        signature_header=multi,
        secret=secret_b64,
    ) is True


def test_verify_svix_signature_rejects_tamper():
    body = b'{"amount":10}'
    secret_b64, sig_header = _svix_secret_and_signature(body, "m", "1")

    # Same signature, different body → reject
    assert verify_svix_signature(
        svix_id="m",
        svix_timestamp="1",
        body=b'{"amount":10000}',
        signature_header=sig_header,
        secret=secret_b64,
    ) is False


def test_verify_svix_signature_rejects_missing_inputs():
    assert verify_svix_signature(
        svix_id="", svix_timestamp="1", body=b"x", signature_header="v1,abc", secret="k"
    ) is False
    assert verify_svix_signature(
        svix_id="m", svix_timestamp="", body=b"x", signature_header="v1,abc", secret="k"
    ) is False
    assert verify_svix_signature(
        svix_id="m", svix_timestamp="1", body=b"x", signature_header="", secret="k"
    ) is False
    assert verify_svix_signature(
        svix_id="m", svix_timestamp="1", body=b"x", signature_header="v1,abc", secret=""
    ) is False


def test_verify_svix_signature_rejects_non_v1_versions():
    body = b"hi"
    secret_b64, real_sig = _svix_secret_and_signature(body, "m", "1")
    # Provider claims v9 — we don't trust unknown version tags.
    spoofed = real_sig.replace("v1,", "v9,")

    assert verify_svix_signature(
        svix_id="m",
        svix_timestamp="1",
        body=body,
        signature_header=spoofed,
        secret=secret_b64,
    ) is False


def test_verify_svix_signature_rejects_garbage_secret():
    """Non-base64 secret can't possibly verify; must return False, not raise."""
    body = b"x"
    assert verify_svix_signature(
        svix_id="m",
        svix_timestamp="1",
        body=body,
        signature_header="v1,abc",
        secret="not!base64@@@",
    ) is False


def test_verify_svix_signature_replay_window_accepts_fresh():
    import time

    body = b"x"
    ts = str(int(time.time()))
    secret_b64, sig_header = _svix_secret_and_signature(body, "m", ts)

    assert verify_svix_signature(
        svix_id="m",
        svix_timestamp=ts,
        body=body,
        signature_header=sig_header,
        secret=secret_b64,
        enforce_replay_window=True,
    ) is True


def test_verify_svix_signature_replay_window_rejects_stale():
    import time

    body = b"x"
    stale = str(int(time.time()) - 3600)
    secret_b64, sig_header = _svix_secret_and_signature(body, "m", stale)

    assert verify_svix_signature(
        svix_id="m",
        svix_timestamp=stale,
        body=body,
        signature_header=sig_header,
        secret=secret_b64,
        enforce_replay_window=True,
    ) is False


def test_verify_svix_signature_replay_window_rejects_non_numeric_timestamp():
    body = b"x"
    secret_b64, sig_header = _svix_secret_and_signature(body, "m", "not-a-number")

    assert verify_svix_signature(
        svix_id="m",
        svix_timestamp="not-a-number",
        body=body,
        signature_header=sig_header,
        secret=secret_b64,
        enforce_replay_window=True,
    ) is False


def test_verify_svix_signature_default_no_replay_check():
    """Default `enforce_replay_window=False` keeps existing callers working."""
    body = b"x"
    secret_b64, sig_header = _svix_secret_and_signature(body, "m", "1")

    assert verify_svix_signature(
        svix_id="m",
        svix_timestamp="1",
        body=body,
        signature_header=sig_header,
        secret=secret_b64,
    ) is True


# -- Pattern 4: HTTP Basic shared secret (Grupo OLX) -------------------------


def _basic(username: str, secret: str) -> str:
    return "Basic " + base64.b64encode(f"{username}:{secret}".encode()).decode("ascii")


def test_verify_basic_accepts_documented_grupo_olx_credential():
    secret = "594F803B380A41396ED63DCA39503542"
    header = _basic(GRUPO_OLX_BASIC_USERNAME, secret)

    assert verify_basic_shared_secret(header, secret) is True


def test_verify_basic_rejects_wrong_secret():
    header = _basic(GRUPO_OLX_BASIC_USERNAME, "not-the-key")

    assert verify_basic_shared_secret(header, "the-key") is False


def test_verify_basic_rejects_wrong_username():
    secret = "the-key"
    header = _basic("someone-else", secret)

    assert verify_basic_shared_secret(header, secret) is False


def test_verify_basic_ignores_username_when_expected_is_none():
    """A provider that rebrands the username half must not lock us out —
    `expected_username=None` verifies only the secret."""
    secret = "the-key"
    header = _basic("grupoolx", secret)

    assert verify_basic_shared_secret(header, secret, expected_username=None) is True


def test_verify_basic_rejects_empty_secret():
    """An unset secret must never authenticate. The 'no secret configured'
    case is `webhook_endpoint`'s `bypass_when_unset` decision, taken before
    this function is reached — reaching it with an empty secret is a bug,
    and the safe answer is False."""
    assert verify_basic_shared_secret(_basic(GRUPO_OLX_BASIC_USERNAME, ""), "") is False


def test_verify_basic_rejects_malformed_headers_without_raising():
    secret = "the-key"
    good = base64.b64encode(f"{GRUPO_OLX_BASIC_USERNAME}:{secret}".encode()).decode()
    malformed = [
        "",                                   # absent header
        "Bearer " + good,                     # wrong auth type
        "Basic",                              # no credential
        "Basic ",                             # empty credential
        "Basic !!!not-base64!!!",             # undecodable
        "Basic " + base64.b64encode(b"\xff\xfe").decode(),      # non-UTF-8 bytes
        "Basic " + base64.b64encode(b"no-colon-here").decode(),  # no separator
    ]

    for header in malformed:
        assert verify_basic_shared_secret(header, secret) is False, header


def test_verify_basic_accepts_lowercase_scheme_token():
    """HTTP auth-scheme tokens are case-insensitive (RFC 7235); a provider
    sending `basic` rather than `Basic` is conformant, not an attacker."""
    secret = "the-key"
    header = _basic(GRUPO_OLX_BASIC_USERNAME, secret).replace("Basic ", "basic ", 1)

    assert verify_basic_shared_secret(header, secret) is True


def test_verify_basic_accepts_secret_containing_a_colon():
    """`partition(':')` splits on the FIRST colon, so a secret with colons
    in it survives — the username half is what is delimited, not the secret."""
    secret = "a:b:c"
    header = _basic(GRUPO_OLX_BASIC_USERNAME, secret)

    assert verify_basic_shared_secret(header, secret) is True
