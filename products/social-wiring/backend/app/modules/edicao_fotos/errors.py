"""The error envelope and the engine-exception → status map.

Body: `{"detail": "<pt-BR message>", "code": "<machine code>"}` — the seed's
machine-error shape, passed through verbatim by
`noctusai_lib.primitives.exceptions.http_exception_handler` and read by the
seed FE `ApiError.code`. (A nested `{"detail": {"code", "message"}}` would be
stringified by that handler and the code lost — contract §0 was corrected to
this shape on 2026-09-16.)"""
from __future__ import annotations

from fastapi import HTTPException

from noctusai_lib.domain.photo_editing import (
    BatchNotDecidedError,
    CommentRequiredError,
    GuideNotActiveError,
    NotFoundError,
    NothingApprovedError,
    PhotoNotDecidableError,
    PhotoNotRetryableError,
    SubmissionError,
)


def api_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"detail": message, "code": code})


#: SubmissionError.code → HTTP status (anything unlisted is a 422).
_SUBMISSION_STATUS = {
    "lote_ja_submetido": 409,
    "lote_cheio": 409,
    "lote_vazio": 409,
    "arquivo_grande_demais": 413,
    "formato_nao_suportado": 415,
}


def engine_error(exc: Exception) -> HTTPException:
    """Map a domain exception raised by the engine to the envelope.

    Raises the exception back when it is not a known domain error — an
    unexpected failure must surface as a 500, not be relabelled."""
    if isinstance(exc, SubmissionError):
        return api_error(_SUBMISSION_STATUS.get(exc.code, 422), exc.code, str(exc))
    if isinstance(exc, CommentRequiredError):
        return api_error(422, exc.code, str(exc))
    if isinstance(exc, (PhotoNotDecidableError, PhotoNotRetryableError)):
        return api_error(409, exc.code, str(exc))
    if isinstance(exc, (BatchNotDecidedError, NothingApprovedError)):
        return api_error(409, exc.code, str(exc))
    if isinstance(exc, GuideNotActiveError):
        # Submission snapshots the active company guide; none is active yet.
        return api_error(409, exc.code, "Nenhum guia de estilo ativo — a plataforma precisa ativar um.")
    if isinstance(exc, NotFoundError):
        return api_error(404, exc.code, str(exc))
    raise exc


ENGINE_ERRORS = (
    SubmissionError,
    CommentRequiredError,
    GuideNotActiveError,
    PhotoNotDecidableError,
    PhotoNotRetryableError,
    BatchNotDecidedError,
    NothingApprovedError,
    NotFoundError,
)

__all__ = ["ENGINE_ERRORS", "api_error", "engine_error"]
