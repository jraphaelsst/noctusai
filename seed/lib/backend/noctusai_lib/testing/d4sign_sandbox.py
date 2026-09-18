"""`D4SignSandbox` — a local, runnable stub speaking D4Sign's wire protocol.

Built for `projects/signature-integration-CONTRACT.md` §1.6 (the
credential-drop-in path). The office has **no D4Sign account yet** — this
gives every session between now and then a real HTTP surface to drive
`D4SignAdapter` against, so the six `NOC-REMEDIATE[d4sign-*]` corners in
`noctusai_lib.integrations.signature.real` can be exercised end-to-end
today, and re-pointed at the live vendor with a one-line configuration
change once credentials exist (`noctusai_lib.testing.d4sign_harness`).

**What this is not.** This sandbox implements ONLY the shapes contract
§1.4 documents as PINNED (the request bodies + the fields the contract
names on each response). Every corner the contract leaves UNPINNED
(`createlist`'s per-signer response id, `consultar`'s per-signer detail,
the webhook `type_post` vocabulary, whether `sendtosigner`'s message is
echoed) is deliberately left at its documented minimum here — inventing a
plausible-looking extra field and then "verifying" `real.py` against our
own invention would be worse than not testing it at all, because a green
suite would look like verification while proving nothing about the real
vendor. `d4sign_harness.py`'s per-marker report never reports a
sandbox-only result as `verified_live` for exactly this reason.

**Wire endpoints** (contract §1.4, all six):

    POST /api/v1/documents/{safe_uuid}/uploadbinary
    POST /api/v1/documents/{uuid}/createlist
    POST /api/v1/documents/{uuid}/sendtosigner
    GET  /api/v1/documents/{uuid}
    GET  /api/v1/documents/{uuid}/download   (+ GET the returned url)
    POST /api/v1/documents/{uuid}/cancel

**Control endpoints** (sandbox-only — `/_control/...`, never a real D4Sign
path, so a request log is never ambiguous about which surface answered):

    POST /_control/documents/{uuid}/advance   — mark a signer signed and/or
                                                 force completion; emits the
                                                 matching webhook
    GET  /_control/webhooks                   — every webhook emitted so far

**Driving it in-process (what the harness + tests do — no socket needed):**

    sandbox = D4SignSandbox(crypt_key="k", safe_uuid="cofre-1")
    adapter = D4SignAdapter(
        api_token="t", crypt_key="k", safe_uuid="cofre-1",
        transport=httpx.ASGITransport(app=sandbox.app()),
    )
    envelope = await adapter.criar_envelope(documento, [signatario])
    await sandbox.advance(envelope.external_id, signer_email="ana@x.com")
    evento = adapter.validar_webhook(*sandbox.emitted_webhooks[-1].as_wire())

**Driving it as a real local server (for a human with curl/Postman):**

    python -m noctusai_lib.testing.d4sign_sandbox --port 8790 \\
        --crypt-key k --safe-uuid cofre-1

Then point a `D4SignAdapter` at `base_url="http://127.0.0.1:8790/api/v1"`.
"""
from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlencode

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from noctusai_lib.security.webhook_signatures import compute_hmac_sha256_hex

#: statusId the sandbox assigns a brand-new document. Mirrors contract
#: §1.4's `1,2 -> pendente` band (D4Sign documents two "pending" values;
#: the sandbox always starts at "1", matching `real.py`'s own mapping).
_STATUS_PENDENTE = "1"
_STATUS_PARCIAL = "3"
_STATUS_CONCLUIDO = "4"
_STATUS_CANCELADO = "5"


@dataclass
class _SandboxSigner:
    email: str
    signed: bool = False


@dataclass
class _SandboxDocument:
    uuid: str
    name: str
    mime_type: str
    content: bytes
    status_id: str = _STATUS_PENDENTE
    signers: list[_SandboxSigner] = field(default_factory=list)
    cancel_comment: Optional[str] = None


@dataclass(frozen=True)
class EmittedWebhook:
    """One webhook the sandbox fired — the exact bytes+headers a real
    `D4SignAdapter.validar_webhook` call would receive over the wire."""

    body: bytes
    headers: dict[str, str]

    def as_wire(self) -> tuple[bytes, dict[str, str]]:
        """`(body, headers)` — the two positional args `validar_webhook`
        takes. Convenience so a caller doesn't destructure a dataclass."""
        return self.body, self.headers


class UnknownDocumentError(KeyError):
    """Raised by `D4SignSandbox.advance` for an `external_id` the sandbox
    never created via `uploadbinary` — a test/harness authoring mistake,
    never a runtime condition a real D4Sign caller could hit."""


class D4SignSandbox:
    """Stateful double of D4Sign's documented v1 API (contract §1.4) plus a
    `_control/*` surface to drive envelopes through their lifecycle and
    inspect emitted webhooks. One instance = one in-memory "account"; the
    `crypt_key` it is constructed with is the shared secret every emitted
    webhook's `Content-HMAC` is computed against — the SAME value a
    `D4SignAdapter` must be constructed with for `validar_webhook` to
    accept what this sandbox emits.
    """

    def __init__(
        self,
        *,
        crypt_key: str,
        safe_uuid: str,
        api_token: str = "sandbox-token",
        download_host: str = "http://d4sign-sandbox.local",
        webhook_callback_url: Optional[str] = None,
    ) -> None:
        self.crypt_key = crypt_key
        self.safe_uuid = safe_uuid
        self.api_token = api_token
        self.webhook_callback_url = webhook_callback_url
        self._download_host = download_host.rstrip("/")
        self._documents: dict[str, _SandboxDocument] = {}
        self._download_tokens: dict[str, str] = {}
        self.emitted_webhooks: list[EmittedWebhook] = []

    # -- wire endpoints, one per contract §1.4 row ---------------------------

    async def _uploadbinary(self, request: Request) -> Response:
        safe_uuid = request.path_params["safe_uuid"]
        if safe_uuid != self.safe_uuid:
            return JSONResponse({"message": "cofre desconhecido"}, status_code=404)
        corpo = await request.json()
        b64 = corpo.get("base64_binary_file")
        if not b64:
            return JSONResponse(
                {"message": "base64_binary_file ausente"}, status_code=400
            )
        doc_uuid = f"sbx-{secrets.token_hex(8)}"
        self._documents[doc_uuid] = _SandboxDocument(
            uuid=doc_uuid,
            name=corpo.get("name", ""),
            mime_type=corpo.get("mime_type", "application/pdf"),
            content=base64.b64decode(b64),
        )
        # §1.4 pins ONLY `{"uuid": ...}` on this response — no portal-link
        # or any other field is invented here on purpose. See marker
        # `d4sign-portal-link` in `real.py`.
        return JSONResponse({"uuid": doc_uuid})

    async def _createlist(self, request: Request) -> Response:
        doc = self._get_document(request)
        if doc is None:
            return self._not_found()
        corpo = await request.json()
        doc.signers = [
            _SandboxSigner(email=s["email"]) for s in corpo.get("signers") or []
        ]
        # §1.4 pins the REQUEST body only. The contract does not pin a
        # response shape, so the sandbox intentionally returns the
        # plainest legal JSON rather than guessing a per-signer id field
        # — that is exactly marker `d4sign-signer-external-id`'s open
        # question, and it must stay open here too.
        return JSONResponse({"message": "ok"})

    async def _sendtosigner(self, request: Request) -> Response:
        doc = self._get_document(request)
        if doc is None:
            return self._not_found()
        corpo = await request.json()
        # Marker `d4sign-sendtosigner-message`: §1.4 does not pin a
        # response shape, and this sandbox cannot say whether the LIVE
        # vendor echoes/validates the message it received. `echo_message`
        # below is a SANDBOX-ONLY convenience (not a claimed D4Sign wire
        # shape) so `d4sign_harness.py` can confirm our own adapter code
        # sent the exact operator-supplied text on the wire.
        return JSONResponse({"message": "ok", "echo_message": corpo.get("message")})

    async def _status(self, request: Request) -> Response:
        doc = self._get_document(request)
        if doc is None:
            return self._not_found()
        # Marker `d4sign-status-per-signer`: §1.4 pins only `statusId`; no
        # per-signer field is invented here.
        return JSONResponse({"statusId": doc.status_id})

    async def _download(self, request: Request) -> Response:
        doc = self._get_document(request)
        if doc is None:
            return self._not_found()
        if doc.status_id != _STATUS_CONCLUIDO:
            return JSONResponse(
                {"message": "documento ainda nao concluido"}, status_code=400
            )
        token = secrets.token_hex(8)
        self._download_tokens[token] = doc.uuid
        return JSONResponse({"url": f"{self._download_host}/files/{token}"})

    async def _fetch_file(self, request: Request) -> Response:
        token = request.path_params["token"]
        doc_uuid = self._download_tokens.get(token)
        if doc_uuid is None:
            return Response(status_code=404)
        doc = self._documents[doc_uuid]
        return Response(doc.content, media_type=doc.mime_type)

    async def _cancel(self, request: Request) -> Response:
        doc = self._get_document(request)
        if doc is None:
            return self._not_found()
        corpo = await request.json()
        doc.cancel_comment = corpo.get("comment")
        doc.status_id = _STATUS_CANCELADO
        return JSONResponse({"message": "ok"})

    # -- control-only surface (never a real D4Sign path) ---------------------

    async def _control_advance(self, request: Request) -> Response:
        doc = self._get_document(request)
        if doc is None:
            return self._not_found()
        corpo = await request.json()
        signer_email = corpo.get("signer_email")
        force_completed = corpo.get("to") == "completed"
        event = await self.advance(
            doc.uuid, signer_email=signer_email, force_completed=force_completed
        )
        return JSONResponse(
            {
                "status_id": doc.status_id,
                "webhook": {
                    "body": event.body.decode("utf-8"),
                    "headers": event.headers,
                },
            }
        )

    async def _control_webhooks(self, request: Request) -> Response:
        return JSONResponse(
            [
                {"body": e.body.decode("utf-8"), "headers": e.headers}
                for e in self.emitted_webhooks
            ]
        )

    # -- the driveable API (used directly by tests/harness, no HTTP hop) -----

    async def advance(
        self,
        external_id: str,
        *,
        signer_email: Optional[str] = None,
        force_completed: bool = False,
    ) -> EmittedWebhook:
        """Mark `signer_email` as signed (a no-op if already signed, or if
        `signer_email` is `None`), recompute the envelope's `statusId`, and
        emit + record the matching webhook (real `Content-HMAC`, computed
        with `self.crypt_key`). Raises `UnknownDocumentError` for an
        `external_id` never created via `uploadbinary`/`criar_envelope`.
        """
        doc = self._documents.get(external_id)
        if doc is None:
            raise UnknownDocumentError(external_id)
        if signer_email is not None:
            for signer in doc.signers:
                if signer.email == signer_email:
                    signer.signed = True
        all_signed = bool(doc.signers) and all(s.signed for s in doc.signers)
        any_signed = any(s.signed for s in doc.signers)
        if force_completed or all_signed:
            doc.status_id = _STATUS_CONCLUIDO
        elif any_signed:
            doc.status_id = _STATUS_PARCIAL
        return await self._emit_webhook(doc)

    async def _emit_webhook(self, doc: _SandboxDocument) -> EmittedWebhook:
        mensagem = (
            "documento concluido"
            if doc.status_id == _STATUS_CONCLUIDO
            else "atualizacao de status"
        )
        corpo = urlencode(
            {"uuid": doc.uuid, "type_post": doc.status_id, "message": mensagem}
        ).encode("utf-8")
        assinatura = compute_hmac_sha256_hex(corpo, self.crypt_key)
        cabecalhos = {
            "Content-HMAC": assinatura,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        evento = EmittedWebhook(body=corpo, headers=cabecalhos)
        self.emitted_webhooks.append(evento)
        if self.webhook_callback_url:
            async with httpx.AsyncClient() as client:
                await client.post(
                    self.webhook_callback_url, content=corpo, headers=cabecalhos
                )
        return evento

    # -- internals ------------------------------------------------------------

    def _get_document(self, request: Request) -> Optional[_SandboxDocument]:
        return self._documents.get(request.path_params["uuid"])

    @staticmethod
    def _not_found() -> JSONResponse:
        return JSONResponse({"message": "documento nao encontrado"}, status_code=404)

    def app(self) -> Starlette:
        """A fresh Starlette app bound to this sandbox's state. Feed it to
        `httpx.ASGITransport(app=...)` for an in-process double (tests,
        the harness), or serve it with uvicorn for a real local server —
        see `noctusai_lib.testing.d4sign_sandbox.serve`."""
        return Starlette(
            routes=[
                Route(
                    "/api/v1/documents/{safe_uuid}/uploadbinary",
                    self._uploadbinary,
                    methods=["POST"],
                ),
                Route(
                    "/api/v1/documents/{uuid}/createlist",
                    self._createlist,
                    methods=["POST"],
                ),
                Route(
                    "/api/v1/documents/{uuid}/sendtosigner",
                    self._sendtosigner,
                    methods=["POST"],
                ),
                Route(
                    "/api/v1/documents/{uuid}", self._status, methods=["GET"]
                ),
                Route(
                    "/api/v1/documents/{uuid}/download",
                    self._download,
                    methods=["GET"],
                ),
                Route(
                    "/api/v1/documents/{uuid}/cancel",
                    self._cancel,
                    methods=["POST"],
                ),
                Route("/files/{token}", self._fetch_file, methods=["GET"]),
                Route(
                    "/_control/documents/{uuid}/advance",
                    self._control_advance,
                    methods=["POST"],
                ),
                Route(
                    "/_control/webhooks", self._control_webhooks, methods=["GET"]
                ),
            ]
        )


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8790,
    crypt_key: str = "sandbox-crypt-key",
    safe_uuid: str = "sandbox-safe-uuid",
    webhook_callback_url: Optional[str] = None,
) -> None:
    """Run the sandbox as a real local HTTP server (blocking). For a human
    driving it manually with curl/Postman while integrating — automated
    tests/the harness use `D4SignSandbox.app()` + `httpx.ASGITransport`
    instead and never need a real socket. Requires the `testing` extra
    (`pip install noctusai-lib[testing]`) for `uvicorn` — a hard runtime
    dependency here would ship a server runtime to every product image for
    a surface only a human manually running this file ever needs.
    """
    try:
        import uvicorn
    except ImportError as exc:
        raise ImportError(
            "noctusai_lib.testing.d4sign_sandbox.serve() needs uvicorn — "
            "install the 'testing' extra: pip install 'noctusai-lib[testing]'"
        ) from exc

    sandbox = D4SignSandbox(
        crypt_key=crypt_key,
        safe_uuid=safe_uuid,
        webhook_callback_url=webhook_callback_url,
    )
    print(  # noqa: T201 - deliberate operator-facing CLI output
        f"D4Sign sandbox listening on http://{host}:{port}/api/v1 "
        f"(safe_uuid={safe_uuid!r}, crypt_key={crypt_key!r}). "
        f"Control surface: http://{host}:{port}/_control/..."
    )
    uvicorn.run(sandbox.app(), host=host, port=port)


def _main(argv: Optional[list[str]] = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--crypt-key", default="sandbox-crypt-key")
    parser.add_argument("--safe-uuid", default="sandbox-safe-uuid")
    parser.add_argument(
        "--webhook-url",
        default=None,
        help="If set, every advance() also POSTs the webhook here.",
    )
    args = parser.parse_args(argv)
    serve(
        host=args.host,
        port=args.port,
        crypt_key=args.crypt_key,
        safe_uuid=args.safe_uuid,
        webhook_callback_url=args.webhook_url,
    )


if __name__ == "__main__":  # pragma: no cover - manual/local-only entry point
    _main()


__all__ = [
    "D4SignSandbox",
    "EmittedWebhook",
    "UnknownDocumentError",
    "serve",
]
