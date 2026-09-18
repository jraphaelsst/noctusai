"""D4Sign contract-verification harness — contract §1.6.

Three things this file proves:

1. `mode="sandbox"` runs clean today (no D4Sign account exists yet) and
   every one of the 6 markers reports a status that is NEVER mistakable
   for a live-vendor confirmation (`sandbox_coherent` only, or
   `unverified_needs_live` for the one marker no API call can answer).
2. `mode="real"` with no credentials configured is HONEST —
   `not_configured` on all 6 markers, never a silent downgrade to the
   sandbox and never a crash.
3. The per-marker CLASSIFICATION LOGIC that decides `verified_live` vs.
   `contradicted_live` once real evidence exists is itself correct —
   rehearsed directly against the private `_check_*` functions with
   hand-built evidence, since no live D4Sign account exists to exercise
   the real HTTP path in CI. This is the harness testing ITSELF, not a
   live D4Sign call — see the module docstring's honesty vocabulary.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from noctusai_lib.integrations.signature.real import D4SignAdapter
from noctusai_lib.integrations.signature.types import DocumentoParaAssinar, Signatario
from noctusai_lib.security.webhook_signatures import compute_hmac_sha256_hex
from noctusai_lib.testing.d4sign_harness import (
    HarnessReport,
    MarkerResult,
    _check_error_body_shape,
    _check_portal_link,
    _check_sendtosigner_message,
    _check_signer_external_id,
    _check_status_per_signer,
    _check_webhook_type_post,
    _Session,
    run_contract_harness,
)

_ALL_MARKERS = (
    "d4sign-portal-link",
    "d4sign-signer-external-id",
    "d4sign-webhook-type-post",
    "d4sign-status-per-signer",
    "d4sign-sendtosigner-message",
    "d4sign-error-body-shape",
)


def _no_credentials(key: str, org_id=None) -> None:
    return None


def _all_credentials(key: str, org_id=None) -> str:
    return {
        "d4sign_api_token": "tok",
        "d4sign_crypt_key": "crypt",
        "d4sign_safe_uuid": "safe",
    }[key]


# ---------------------------------------------------------------------------
# 1. mode="sandbox" — the mode this session can actually run
# ---------------------------------------------------------------------------


def test_sandbox_mode_answers_all_six_markers() -> None:
    report = asyncio.run(run_contract_harness(mode="sandbox"))

    assert report.mode == "sandbox"
    assert {m.marker for m in report.markers} == set(_ALL_MARKERS)
    for marker in report.markers:
        assert marker.status in ("sandbox_coherent", "unverified_needs_live")
        # Never claim vendor truth from a sandbox run.
        assert marker.status not in ("verified_live", "contradicted_live")


def test_sandbox_mode_is_never_reported_as_verified_end_to_end() -> None:
    report = asyncio.run(run_contract_harness(mode="sandbox"))
    assert report.all_verified_live is False


def test_sandbox_mode_webhook_marker_actually_exercises_the_real_hmac_parse() -> None:
    report = asyncio.run(run_contract_harness(mode="sandbox"))
    webhook_marker = next(
        m for m in report.markers if m.marker == "d4sign-webhook-type-post"
    )
    assert webhook_marker.status == "sandbox_coherent"
    assert webhook_marker.evidence["parsed_status"] == "concluido"


def test_sandbox_mode_sendtosigner_marker_confirms_the_message_was_sent() -> None:
    report = asyncio.run(run_contract_harness(mode="sandbox"))
    marker = next(
        m for m in report.markers if m.marker == "d4sign-sendtosigner-message"
    )
    assert marker.status == "sandbox_coherent"
    assert marker.evidence["sandbox_echo"] == marker.evidence["mensagem_enviada"]


def test_report_serializes_to_a_plain_dict() -> None:
    report = asyncio.run(run_contract_harness(mode="sandbox"))
    as_dict = report.to_dict()
    assert as_dict["mode"] == "sandbox"
    assert len(as_dict["markers"]) == 6
    json.dumps(as_dict)  # must be JSON-serializable end to end


# ---------------------------------------------------------------------------
# 2. mode="real" with no credentials — honest, never a faked pass
# ---------------------------------------------------------------------------


def test_real_mode_without_credentials_is_not_configured_on_every_marker() -> None:
    report = asyncio.run(run_contract_harness(mode="real", resolver=_no_credentials))

    assert report.mode == "real"
    assert {m.marker for m in report.markers} == set(_ALL_MARKERS)
    for marker in report.markers:
        assert marker.status == "not_configured"
        assert marker.evidence["faltando"] == [
            "d4sign_api_token",
            "d4sign_crypt_key",
            "d4sign_safe_uuid",
        ]
    assert report.all_verified_live is False


def test_real_mode_names_only_the_missing_credentials() -> None:
    def partial(key: str, org_id=None):
        return "present" if key == "d4sign_api_token" else None

    report = asyncio.run(run_contract_harness(mode="real", resolver=partial))
    marker = report.markers[0]
    assert marker.status == "not_configured"
    assert marker.evidence["faltando"] == ["d4sign_crypt_key", "d4sign_safe_uuid"]


# ---------------------------------------------------------------------------
# 3. Per-marker classification logic — rehearsed with hand-built evidence
#    (no live D4Sign account exists to generate this evidence for real; see
#    module docstring). Constructs `_Session` objects directly rather than
#    driving a real network call.
# ---------------------------------------------------------------------------


def _real_session_with_raw(step: str, body: dict) -> _Session:
    session = _Session(mode="real")
    session.raw[step] = [body]
    return session


class _FakeEnvelope:
    def __init__(self, link: str, signatarios=()):
        self.link_assinatura = link
        self.signatarios = signatarios


def test_real_mode_portal_link_verified_when_response_is_uuid_only() -> None:
    session = _real_session_with_raw("uploadbinary", {"uuid": "doc-1"})
    envelope = _FakeEnvelope("https://secure.d4sign.com.br/documents/doc-1")

    result = _check_portal_link(session, envelope)
    assert result.status == "verified_live"


def test_real_mode_portal_link_contradicted_when_vendor_sends_extra_fields() -> None:
    session = _real_session_with_raw(
        "uploadbinary", {"uuid": "doc-1", "url": "https://d4sign/real-link"}
    )
    envelope = _FakeEnvelope("https://secure.d4sign.com.br/documents/doc-1")

    result = _check_portal_link(session, envelope)
    assert result.status == "contradicted_live"
    assert "url" in result.detail


def test_real_mode_signer_external_id_contradicted_on_extra_field() -> None:
    session = _real_session_with_raw(
        "createlist", {"message": "ok", "key_signer": "abc123"}
    )
    envelope = _FakeEnvelope("irrelevant", signatarios=[])

    result = _check_signer_external_id(session, envelope)
    assert result.status == "contradicted_live"
    assert "key_signer" in result.detail


def test_real_mode_signer_external_id_verified_when_message_only() -> None:
    session = _real_session_with_raw("createlist", {"message": "ok"})
    envelope = _FakeEnvelope("irrelevant", signatarios=[])

    result = _check_signer_external_id(session, envelope)
    assert result.status == "verified_live"


def test_real_mode_status_per_signer_contradicted_on_extra_field() -> None:
    session = _Session(mode="real")
    result = _check_status_per_signer(
        session, {"statusId": "4", "signers": [{"email": "a@x.com"}]}
    )
    assert result.status == "contradicted_live"


def test_real_mode_status_per_signer_verified_when_statusid_only() -> None:
    session = _Session(mode="real")
    result = _check_status_per_signer(session, {"statusId": "4"})
    assert result.status == "verified_live"


def test_real_mode_sendtosigner_message_is_always_unverified_needs_live() -> None:
    """No D4Sign API confirms a signer actually SAW the message — this
    marker can never auto-resolve to verified/contradicted, live or not."""
    session = _Session(mode="real")
    result = _check_sendtosigner_message(session, "alguma mensagem")
    assert result.status == "unverified_needs_live"


def test_real_mode_webhook_without_capture_path_is_unverified_needs_live() -> None:
    session = _Session(mode="real")
    session.adapter = D4SignAdapter(api_token="t", crypt_key="k", safe_uuid="s")

    result = _check_webhook_type_post(session, None, None)
    assert result.status == "unverified_needs_live"


def test_real_mode_webhook_with_captured_file_verifies(tmp_path) -> None:
    crypt_key = "real-crypt-key"
    body = "uuid=live-doc-1&type_post=4&message=ok"
    assinatura = compute_hmac_sha256_hex(body.encode("utf-8"), crypt_key)
    capture_path = tmp_path / "captured_webhook.json"
    capture_path.write_text(
        json.dumps({"body": body, "headers": {"Content-HMAC": assinatura}})
    )

    session = _Session(mode="real")
    session.adapter = D4SignAdapter(api_token="t", crypt_key=crypt_key, safe_uuid="s")

    result = _check_webhook_type_post(session, None, str(capture_path))
    assert result.status == "verified_live"
    assert result.evidence["parsed_status"] == "concluido"


def test_real_mode_webhook_with_captured_file_contradicted_on_bad_signature(
    tmp_path,
) -> None:
    body = "uuid=live-doc-1&type_post=4&message=ok"
    capture_path = tmp_path / "captured_webhook.json"
    capture_path.write_text(
        json.dumps({"body": body, "headers": {"Content-HMAC": "not-a-real-signature"}})
    )

    session = _Session(mode="real")
    session.adapter = D4SignAdapter(api_token="t", crypt_key="real-crypt-key", safe_uuid="s")

    result = _check_webhook_type_post(session, None, str(capture_path))
    assert result.status == "contradicted_live"


def test_real_mode_error_body_shape_reports_verified_live_with_evidence() -> None:
    session = _Session(mode="real")
    result = _check_error_body_shape(session)
    assert result.status == "verified_live"
