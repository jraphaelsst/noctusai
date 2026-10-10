"""Platform async transcription API — ``/api/transcriptions`` (CONTRACT §2).

Submit audio -> 202 + id -> poll. Auth: seed session dependency (``pk_*``
product token with ``transcription:write|read``, or a platform session).
Errors are the ``{codigo, mensagem}`` envelope; every 429/503 carries
``Retry-After``; another caller's job is a 404, never a 403.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Depends, File, Form, Header, Request, Response, UploadFile

from app.services.transcription_api import limits as L
from app.services.transcription_api.errors import TranscricaoErro
from app.services.transcription_api.service import Caller, caller_from_context
from app.services.transcription_api.wiring import TranscricaoRuntime, get_runtime

router = APIRouter(prefix="/api/transcriptions", tags=["Transcriptions"])

#: Value for ``max_body_path_overrides["/api/transcriptions"]`` in ``main.py``
#: (the keeper needs the key literal there) — file cap + multipart framing, so
#: the handler (not the body middleware) answers an over-cap file with the
#: error envelope.
BODY_LIMIT_BYTES = L.MAX_UPLOAD_BYTES + L.MULTIPART_SLACK_BYTES

_CHUNK = 1024 * 1024


def _guard(kind: str, method: str):
    """Dependency: authenticate + scope-guard + burst-limit by caller identity."""

    async def dependency(
        request: Request,
        response: Response,
        authorization: Optional[str] = Header(None),
        session_cookie: Optional[str] = Cookie(None, alias="nai_session"),
        rt: TranscricaoRuntime = Depends(get_runtime),
    ) -> Caller:
        ctx = await rt.auth.authenticate(kind, request, response, authorization, session_cookie)
        caller = caller_from_context(ctx)
        wait = rt.burst.retry_after_if_limited(method, caller.identity)
        if wait is not None:
            raise TranscricaoErro("limite_requisicoes", retry_after_s=wait)
        return caller

    return dependency


_submit_caller = _guard("write", "POST")
_read_caller = _guard("read", "GET")
_delete_caller = _guard("write", "DELETE")
_admin_caller = _guard("admin", "GET")


async def _read_capped(arquivo: UploadFile, max_bytes: int) -> bytes:
    """Read the upload, cutting the stream at the cap (413 ``arquivo_grande``)."""
    buf = bytearray()
    while chunk := await arquivo.read(_CHUNK):
        buf += chunk
        if len(buf) > max_bytes:
            raise TranscricaoErro("arquivo_grande")
    return bytes(buf)


@router.post("", status_code=202)
async def enviar_transcricao(
    request: Request,
    arquivo: UploadFile = File(...),
    idioma: str = Form("pt"),
    rotulo: Optional[str] = Form(None),
    segmentos: bool = Form(False),
    caller: Caller = Depends(_submit_caller),
    rt: TranscricaoRuntime = Depends(get_runtime),
):
    max_bytes = rt.service.limits.max_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes + L.MULTIPART_SLACK_BYTES:
        raise TranscricaoErro("arquivo_grande")
    audio = await _read_capped(arquivo, max_bytes)
    result = await rt.service.submit(
        caller, audio, idioma=idioma, rotulo=rotulo or None, segmentos=segmentos
    )
    return result


# NOTE: `_stats` MUST be declared before `/{transcricao_id}` or it is shadowed.
@router.get("/_stats")
async def estatisticas(
    _caller: Caller = Depends(_admin_caller),
    rt: TranscricaoRuntime = Depends(get_runtime),
):
    return rt.service.stats(worker_saudavel=rt.worker_saudavel())


@router.get("")
async def listar_transcricoes(
    status: Optional[str] = None,
    limit: int = 20,
    cursor: Optional[str] = None,
    caller: Caller = Depends(_read_caller),
    rt: TranscricaoRuntime = Depends(get_runtime),
):
    return rt.service.listar(caller, status=status, limit=limit, cursor=cursor)


@router.get("/{transcricao_id}")
async def obter_transcricao(
    transcricao_id: str,
    caller: Caller = Depends(_read_caller),
    rt: TranscricaoRuntime = Depends(get_runtime),
):
    return rt.service.obter(caller, transcricao_id)


@router.delete("/{transcricao_id}", status_code=204)
async def remover_transcricao(
    transcricao_id: str,
    caller: Caller = Depends(_delete_caller),
    rt: TranscricaoRuntime = Depends(get_runtime),
):
    await rt.service.remover(caller, transcricao_id)
    return Response(status_code=204)
