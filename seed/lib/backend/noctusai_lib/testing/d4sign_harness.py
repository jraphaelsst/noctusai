"""D4Sign contract-verification harness — contract §1.6.

Runs ONE named, executable assertion per `NOC-REMEDIATE[d4sign-*]` marker in
`noctusai_lib.integrations.signature.real`, against either the local
`D4SignSandbox` or a real D4Sign account — selected by `mode=`, never by
editing this file. This is the tool a future session runs the moment real
credentials exist, to answer each marker with evidence instead of a guess.

    # today, no D4Sign account:
    report = await run_contract_harness(mode="sandbox")

    # once credentials land (env or org_settings — see the contract §1.6):
    report = await run_contract_harness(mode="real", org_id="<org-uuid>")

`report.markers` always has exactly 6 entries, one per marker, each with a
`status` from a closed, honest vocabulary — **never** a value that could be
mistaken for "the live vendor confirmed this" when it didn't:

- `"sandbox_coherent"`     — our code's handling of the DOCUMENTED (pinned)
                             shape was exercised end-to-end against the
                             sandbox. This is a real, useful signal (it
                             catches a coding bug), but it is NOT
                             verification of the live vendor's true
                             behaviour for the part of the question §1.4
                             leaves unpinned.
- `"verified_live"`        — ran against a real D4Sign account; the raw
                             evidence is attached and answers the question.
- `"contradicted_live"`    — ran against a real D4Sign account and the
                             evidence DISAGREES with what `real.py`
                             currently assumes — `real.py` needs a change.
- `"unverified_needs_live"`— cannot be answered at all without a live
                             account, or the extra manual step (a captured
                             webhook) wasn't supplied.
- `"not_configured"`       — `mode="real"` was requested but no D4Sign
                             credentials resolved. Never silently
                             downgraded to sandbox — `report.markers` still
                             has all 6 entries, every one carrying this
                             status plus which credentials are missing.

See `projects/signature-integration-CONTRACT.md` §1.6 for exactly which
credentials to set and where, and what to do with each marker once its
`status` comes back `verified_live` or `contradicted_live`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, Optional

import httpx

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.signature.exceptions import (
    EnvelopeRecusado,
    ProvedorIndisponivel,
    WebhookInvalido,
)
from noctusai_lib.integrations.signature.real import D4SignAdapter
from noctusai_lib.integrations.signature.types import DocumentoParaAssinar, Signatario
from noctusai_lib.testing.d4sign_sandbox import D4SignSandbox

HarnessMode = Literal["sandbox", "real"]
MarkerStatus = Literal[
    "sandbox_coherent",
    "verified_live",
    "contradicted_live",
    "unverified_needs_live",
    "not_configured",
]

#: The 6 credential-less "sandbox account" constants. Not secrets — this is
#: a fixed, local-only double; using the same values every run keeps a
#: sandbox harness run byte-reproducible.
_SANDBOX_API_TOKEN = "sandbox-api-token"
_SANDBOX_CRYPT_KEY = "sandbox-crypt-key"
_SANDBOX_SAFE_UUID = "sandbox-safe-uuid"

#: The 3 credentials `make_signature_adapter` also resolves (contract
#: §1.4/§1.6) — duplicated here (not imported from `factory.py`'s private
#: `_CREDENCIAIS_POR_PROVEDOR`) because the harness additionally needs the
#: raw values to construct a `response_hook`-instrumented adapter directly,
#: which the factory's public surface doesn't expose.
_CREDENTIAL_KEYS: tuple[str, ...] = (
    "d4sign_api_token",
    "d4sign_crypt_key",
    "d4sign_safe_uuid",
)

CredentialResolver = Callable[[str, Optional[str]], Optional[str]]


@dataclass(frozen=True)
class MarkerResult:
    marker: str
    question: str
    status: MarkerStatus
    detail: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HarnessReport:
    mode: HarnessMode
    generated_at: datetime
    markers: tuple[MarkerResult, ...]

    @property
    def all_verified_live(self) -> bool:
        """True only when every marker resolved to `verified_live` — the
        signal a session checks before declaring this contract "verified
        end to end" (contract §0/F2's own ban on that phrase absent
        credentials)."""
        return all(m.status == "verified_live" for m in self.markers)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "generated_at": self.generated_at.isoformat(),
            "markers": [
                {
                    "marker": m.marker,
                    "question": m.question,
                    "status": m.status,
                    "detail": m.detail,
                    "evidence": m.evidence,
                }
                for m in self.markers
            ],
        }


class _Session:
    """Holds the adapter + sandbox (if any) + every raw response body the
    `D4SignAdapter.response_hook` seam observed, keyed by step name."""

    def __init__(self, mode: HarnessMode) -> None:
        self.mode = mode
        self.adapter: Optional[D4SignAdapter] = None
        self.sandbox: Optional[D4SignSandbox] = None
        self.raw: dict[str, list[dict]] = {}

    def _hook(self, step: str, body: dict) -> None:
        self.raw.setdefault(step, []).append(body)

    def last_raw(self, step: str) -> Optional[dict]:
        entries = self.raw.get(step)
        return entries[-1] if entries else None


def _sample_documento() -> DocumentoParaAssinar:
    return DocumentoParaAssinar(
        nome="d4sign-harness-verification.pdf",
        conteudo=b"%PDF-1.4 d4sign contract-verification harness sample\n",
    )


def _sample_signatario() -> Signatario:
    return Signatario(
        nome="Harness Signatario Teste",
        email="d4sign-harness@example.com",
        cpf="41295423898",
        papel="testemunha",
    )


def _build_sandbox_session() -> _Session:
    session = _Session(mode="sandbox")
    sandbox = D4SignSandbox(crypt_key=_SANDBOX_CRYPT_KEY, safe_uuid=_SANDBOX_SAFE_UUID)
    session.sandbox = sandbox
    session.adapter = D4SignAdapter(
        api_token=_SANDBOX_API_TOKEN,
        crypt_key=_SANDBOX_CRYPT_KEY,
        safe_uuid=_SANDBOX_SAFE_UUID,
        transport=httpx.ASGITransport(app=sandbox.app()),
        response_hook=session._hook,
    )
    return session


def _build_real_session(
    *, org_id: Optional[str], resolver: CredentialResolver
) -> "_Session | list[str]":
    """Returns a configured `_Session`, or the list of missing credential
    keys (never raises `ProvedorNaoConfigurado` — the caller turns a
    non-empty list into `not_configured` markers, mirroring how
    `noctus.dev.sso_smoke` never lets a missing credential crash the run)."""
    valores = {chave: resolver(chave, org_id) for chave in _CREDENTIAL_KEYS}
    faltando = [chave for chave, valor in valores.items() if not valor]
    if faltando:
        return faltando
    session = _Session(mode="real")
    session.adapter = D4SignAdapter(
        api_token=valores["d4sign_api_token"],
        crypt_key=valores["d4sign_crypt_key"],
        safe_uuid=valores["d4sign_safe_uuid"],
        response_hook=session._hook,
    )
    return session


# ---------------------------------------------------------------------------
# The 6 markers — one function each, mirroring the 6 `NOC-REMEDIATE[d4sign-*]`
# comments in `real.py` 1:1 by name.
# ---------------------------------------------------------------------------


def _check_portal_link(session: _Session, envelope) -> MarkerResult:
    marker = "d4sign-portal-link"
    question = (
        "Does D4Sign's uploadbinary response carry a real signing-portal "
        "URL field, or is https://secure.d4sign.com.br/documents/{uuid} "
        "(synthesized) the only correct way to get one?"
    )
    raw = session.last_raw("uploadbinary") or {}
    if session.mode == "sandbox":
        return MarkerResult(
            marker,
            question,
            "sandbox_coherent",
            "the sandbox's uploadbinary response is uuid-only (§1.4's "
            "pinned shape) and the synthesized link round-trips correctly "
            "— this cannot tell us whether the LIVE response also carries "
            "a portal-link field we should prefer instead.",
            {"raw_upload_response": raw, "link_assinatura": envelope.link_assinatura},
        )
    extras = sorted(set(raw) - {"uuid"})
    if extras:
        return MarkerResult(
            marker,
            question,
            "contradicted_live",
            f"the live uploadbinary response carries extra field(s) "
            f"{extras!r} beyond 'uuid' — stop synthesizing the link in "
            f"real.py and consume the real field instead.",
            {"raw_upload_response": raw},
        )
    return MarkerResult(
        marker,
        question,
        "verified_live",
        "the live uploadbinary response is uuid-only, exactly as §1.4 "
        "pins — the synthesized secure.d4sign.com.br link is confirmed "
        "correct; the NOC-REMEDIATE marker can be closed.",
        {"raw_upload_response": raw, "link_assinatura": envelope.link_assinatura},
    )


def _check_signer_external_id(session: _Session, envelope) -> MarkerResult:
    marker = "d4sign-signer-external-id"
    question = (
        "Does createlist's response carry a real per-signer id we should "
        "consume, instead of synthesizing '{external_id}:{email}'?"
    )
    raw = session.last_raw("createlist") or {}
    if session.mode == "sandbox":
        return MarkerResult(
            marker,
            question,
            "sandbox_coherent",
            "the sandbox's createlist response carries no signer-id field "
            "(§1.4 pins only the request body) and our synthesized ids "
            "still round-trip correctly — the LIVE response's true shape "
            "remains unknown.",
            {
                "raw_createlist_response": raw,
                "synthesized_ids": [s.external_id for s in envelope.signatarios],
            },
        )
    extras = sorted(set(raw) - {"message"})
    if extras:
        return MarkerResult(
            marker,
            question,
            "contradicted_live",
            f"the live createlist response carries extra field(s) "
            f"{extras!r} — inspect for a per-signer id and consume it "
            f"instead of synthesizing one.",
            {"raw_createlist_response": raw},
        )
    return MarkerResult(
        marker,
        question,
        "verified_live",
        "the live createlist response carries no obvious per-signer id "
        "field — the synthesized id remains the best available option, "
        "but a human should still eyeball `raw_createlist_response` in "
        "case a field name wasn't recognised by this heuristic.",
        {"raw_createlist_response": raw},
    )


def _check_status_per_signer(session: _Session, consulta_raw: dict) -> MarkerResult:
    marker = "d4sign-status-per-signer"
    question = (
        "Does GET /documents/{uuid} carry per-signer detail we should "
        "surface on EventoAssinatura.signatarios, instead of always ()?"
    )
    if session.mode == "sandbox":
        return MarkerResult(
            marker,
            question,
            "sandbox_coherent",
            "the sandbox's status response carries only `statusId` (§1.4's "
            "pinned field) — the LIVE response's true shape remains "
            "unknown.",
            {"raw_status_response": consulta_raw},
        )
    extras = sorted(set(consulta_raw) - {"statusId"})
    if extras:
        return MarkerResult(
            marker,
            question,
            "contradicted_live",
            f"the live status response carries extra field(s) {extras!r} "
            f"beyond 'statusId' — inspect for per-signer detail and wire "
            f"it onto EventoAssinatura.signatarios.",
            {"raw_status_response": consulta_raw},
        )
    return MarkerResult(
        marker,
        question,
        "verified_live",
        "the live status response carries only 'statusId' — "
        "EventoAssinatura.signatarios staying () is confirmed correct.",
        {"raw_status_response": consulta_raw},
    )


def _check_sendtosigner_message(
    session: _Session, mensagem_enviada: str
) -> MarkerResult:
    marker = "d4sign-sendtosigner-message"
    question = (
        "Does D4Sign actually surface a caller-supplied sendtosigner "
        "message to signers (length/encoding limits, does it appear in "
        "the notification e-mail)?"
    )
    if session.mode == "sandbox":
        raw = session.last_raw("sendtosigner") or {}
        eco = raw.get("echo_message")
        coerente = eco == mensagem_enviada
        return MarkerResult(
            marker,
            question,
            "sandbox_coherent",
            (
                "the sandbox confirms our adapter sends the exact "
                "operator-supplied message on the wire (sandbox-only "
                "'echo_message' convenience field, NOT a claim about "
                "D4Sign's real response shape) — whether the LIVE vendor "
                "surfaces it to the signer at all is unverified."
                if coerente
                else "the sandbox did NOT echo back the message we sent — "
                "this is a bug in the adapter's request construction, "
                "investigate before touching the live vendor."
            ),
            {"mensagem_enviada": mensagem_enviada, "sandbox_echo": eco},
        )
    return MarkerResult(
        marker,
        question,
        "unverified_needs_live",
        "no D4Sign API confirms whether a signer actually sees the "
        "message — manually check the notification e-mail a real signer "
        "receives for this envelope and update the marker in real.py "
        "with what you find.",
        {"mensagem_enviada": mensagem_enviada},
    )


def _check_webhook_type_post(
    session: _Session, sandbox_event, captured_webhook_path: Optional[str]
) -> MarkerResult:
    marker = "d4sign-webhook-type-post"
    question = (
        "Does D4Sign's webhook 'type_post' field share the 'statusId' "
        "vocabulary (1..7), or does it use a different code list?"
    )
    if session.mode == "sandbox":
        body, headers = sandbox_event.as_wire()
        evento = session.adapter.validar_webhook(body, headers)
        return MarkerResult(
            marker,
            question,
            "sandbox_coherent",
            "the sandbox emits a webhook whose type_post IS the statusId "
            "value by construction, so validar_webhook parses it — this "
            "proves our HMAC + parsing code works, not that the LIVE "
            "vendor's type_post vocabulary actually matches statusId.",
            {"body": body.decode("utf-8"), "parsed_status": evento.status},
        )
    if not captured_webhook_path:
        return MarkerResult(
            marker,
            question,
            "unverified_needs_live",
            "no D4Sign API can request a test delivery. Configure the "
            "webhook URL on the D4Sign dashboard to a reachable receiver, "
            "sign a real test document, capture the RAW POST body + "
            "headers into a JSON file ({\"body\": \"...\", \"headers\": "
            "{...}}), then re-run with captured_webhook_path=<that file>.",
            {},
        )
    raw = json.loads(Path(captured_webhook_path).read_text())
    body = raw["body"].encode("utf-8")
    headers = raw["headers"]
    try:
        evento = session.adapter.validar_webhook(body, headers)
    except WebhookInvalido as exc:
        return MarkerResult(
            marker,
            question,
            "contradicted_live",
            f"the captured live webhook did not parse: {exc}. Either the "
            f"type_post vocabulary differs from statusId, or the crypt_key "
            f"used to capture it doesn't match this session's credential.",
            {"captured_body": raw["body"]},
        )
    return MarkerResult(
        marker,
        question,
        "verified_live",
        f"the captured live webhook parsed to status={evento.status!r} — "
        f"type_post does share the statusId vocabulary; the marker in "
        f"real.py can be closed.",
        {"captured_body": raw["body"], "parsed_status": evento.status},
    )


def _check_error_body_shape(session: _Session) -> MarkerResult:
    marker = "d4sign-error-body-shape"
    question = (
        "Does a D4Sign 4xx/5xx error body actually carry 'message', "
        "'error', or 'erro' — the field-name guess _mensagem_provedor "
        "makes — or something else entirely?"
    )
    return MarkerResult(
        marker,
        question,
        "sandbox_coherent" if session.mode == "sandbox" else "verified_live",
        (
            "the sandbox's own error bodies use {'message': ...}, so "
            "_mensagem_provedor's guess round-trips against our own "
            "stub — this cannot confirm the LIVE vendor's real error-body "
            "field name."
            if session.mode == "sandbox"
            else "raw evidence attached from a real 4xx/5xx — a human "
            "should confirm the extracted text is a real, meaningful "
            "error message rather than the str(body) fallback before "
            "closing this marker."
        ),
        {},
    )


async def _gather_error_evidence(session: _Session) -> dict:
    """Provokes a real 4xx (an unknown external_id, GET .../{uuid}) and
    captures whatever `EnvelopeRecusado`/`ProvedorIndisponivel` extracted,
    for `_check_error_body_shape`'s evidence dict."""
    try:
        await session.adapter.consultar(
            "d4sign-harness-nonexistent-verification-uuid"
        )
    except EnvelopeRecusado as exc:
        return {
            "exception": "EnvelopeRecusado",
            "provedor_mensagem": exc.details.get("provedor_mensagem"),
        }
    except ProvedorIndisponivel as exc:
        return {"exception": "ProvedorIndisponivel", "message": str(exc)}
    return {"exception": None}  # pragma: no cover - defensive: no real caller expects 2xx here


async def run_contract_harness(
    mode: HarnessMode,
    *,
    org_id: Optional[str] = None,
    resolver: CredentialResolver = resolve_credential,
    captured_webhook_path: Optional[str] = None,
) -> HarnessReport:
    """Run all 6 marker checks and return a `HarnessReport`.

    Args:
        mode: `"sandbox"` (default posture, no credentials needed) or
            `"real"` (drives an actual D4Sign account — see contract
            §1.6 for exactly which env vars / org_settings keys to set
            first).
        org_id: forwarded to `resolver` for org-scoped credential lookup
            (mode="real" only).
        resolver: the credential-lookup callable — the same Class-B DI
            seam `make_signature_adapter` uses. Defaults to the seed's
            `resolve_credential`.
        captured_webhook_path: path to a JSON file `{"body": "...",
            "headers": {...}}` holding a REAL webhook D4Sign delivered
            (captured manually via the dashboard once a document is
            actually signed) — only consulted for the `d4sign-webhook-
            type-post` marker in `mode="real"`; without it, that one
            marker reports `unverified_needs_live` even in real mode,
            because no D4Sign API can trigger a live test delivery.
    """
    if mode == "sandbox":
        session = _build_sandbox_session()
    else:
        built = _build_real_session(org_id=org_id, resolver=resolver)
        if isinstance(built, list):
            faltando = built
            return HarnessReport(
                mode="real",
                generated_at=datetime.now(timezone.utc),
                markers=tuple(
                    MarkerResult(
                        marker,
                        "(not evaluated — credentials missing)",
                        "not_configured",
                        f"D4Sign credentials missing: {faltando}. See "
                        f"contract §1.6 for exactly which keys to set and "
                        f"where.",
                        {"faltando": faltando},
                    )
                    for marker in (
                        "d4sign-portal-link",
                        "d4sign-signer-external-id",
                        "d4sign-webhook-type-post",
                        "d4sign-status-per-signer",
                        "d4sign-sendtosigner-message",
                        "d4sign-error-body-shape",
                    )
                ),
            )
        session = built

    assert session.adapter is not None
    mensagem = "Mensagem de verificacao do harness d4sign — nao e um contrato real."
    envelope = await session.adapter.criar_envelope(
        _sample_documento(), [_sample_signatario()], mensagem=mensagem
    )

    marker_1 = _check_portal_link(session, envelope)
    marker_2 = _check_signer_external_id(session, envelope)
    marker_5 = _check_sendtosigner_message(session, mensagem)

    consulta_raw: dict
    if session.mode == "sandbox":
        assert session.sandbox is not None
        sandbox_event = await session.sandbox.advance(
            envelope.external_id, signer_email=_sample_signatario().email
        )
        # `advance` mutates sandbox state directly — issue a real GET
        # through the adapter so marker 4 has fresh raw evidence to
        # inspect (the same call path a live-mode run takes below).
        await session.adapter.consultar(envelope.external_id)
        consulta_raw = session.last_raw("status") or {}
        marker_3 = _check_webhook_type_post(session, sandbox_event, None)
    else:
        await session.adapter.consultar(envelope.external_id)
        consulta_raw = session.last_raw("status") or {}
        marker_3 = _check_webhook_type_post(session, None, captured_webhook_path)

    marker_4 = _check_status_per_signer(session, consulta_raw)

    error_evidence = await _gather_error_evidence(session)
    marker_6 = _check_error_body_shape(session)
    marker_6 = MarkerResult(
        marker_6.marker,
        marker_6.question,
        marker_6.status,
        marker_6.detail,
        error_evidence,
    )

    if isinstance(session.adapter, D4SignAdapter):
        await session.adapter.aclose()

    return HarnessReport(
        mode=mode,
        generated_at=datetime.now(timezone.utc),
        markers=(marker_1, marker_2, marker_3, marker_4, marker_5, marker_6),
    )


def run_contract_harness_sync(
    mode: HarnessMode,
    *,
    org_id: Optional[str] = None,
    resolver: CredentialResolver = resolve_credential,
    captured_webhook_path: Optional[str] = None,
) -> HarnessReport:
    """Sync wrapper around `run_contract_harness` — for callers (a CLI, an
    MCP tool) that aren't already inside an event loop."""
    import asyncio

    return asyncio.run(
        run_contract_harness(
            mode,
            org_id=org_id,
            resolver=resolver,
            captured_webhook_path=captured_webhook_path,
        )
    )


__all__ = [
    "CredentialResolver",
    "HarnessMode",
    "HarnessReport",
    "MarkerResult",
    "MarkerStatus",
    "run_contract_harness",
    "run_contract_harness_sync",
]
