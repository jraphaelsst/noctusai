"""The transcription error envelope (transcription-contract.md section 4).

Platform standard: ``{"codigo": ..., "mensagem": ...}`` with a pt-BR message,
plus ``detail`` (= mensagem) so the generic frontend error handler that reads
``detail`` keeps working. 429/503 carry ``Retry-After``.
"""
from __future__ import annotations

from typing import Optional

from fastapi.responses import JSONResponse

#: codigo -> (HTTP status, pt-BR message). The single source of truth for the
#: synchronous submit codes; ``reservar_transcricao()`` returns the 429/503 ones.
CODIGOS: dict[str, tuple[int, str]] = {
    "arquivo_grande": (413, "O áudio excede o tamanho máximo de 15 MB."),
    "formato_invalido": (415, "Formato de áudio não suportado."),
    "duracao_excedida": (422, "O áudio excede a duração máxima de 10 minutos."),
    "audio_vazio": (422, "O áudio é curto demais ou está vazio."),
    "audio_corrompido": (422, "Não foi possível ler este áudio. Grave novamente."),
    "limite_usuario": (429, "Você já tem gravações demais em processamento ou enviadas na última hora. Aguarde um pouco."),
    "cota_diaria_usuario": (429, "Você atingiu o limite diário de transcrição. Tente novamente mais tarde."),
    "cota_diaria_org": (429, "Sua organização atingiu o limite diário de transcrição. Tente novamente mais tarde."),
    "fila_cheia": (503, "A fila de transcrição está cheia. Tente novamente em alguns minutos."),
    "capacidade_diaria": (503, "A capacidade diária de transcrição foi atingida. Tente novamente mais tarde."),
    "transcricao_indisponivel": (503, "O serviço de transcrição está indisponível no momento. Tente novamente em instantes."),
    "transcricao_desativada": (503, "A transcrição por voz está desativada no momento."),
    "contexto_invalido": (422, "Contexto da transcrição inválido."),
    "nao_encontrada": (404, "Transcrição não encontrada."),
    "em_processamento": (409, "A transcrição já está em processamento e não pode ser cancelada."),
    "nao_cancelavel": (409, "Esta transcrição já foi finalizada."),
    "tempo_esgotado": (422, "A transcrição demorou demais e foi cancelada. Tente novamente."),
    "audio_ausente": (422, "O áudio desta gravação não está mais disponível."),
}

DEFAULT_RETRY_AFTER_S = 60


class TranscricaoErro(Exception):
    """A request-level failure carrying the envelope's ``codigo``."""

    def __init__(
        self,
        codigo: str,
        *,
        status: Optional[int] = None,
        mensagem: Optional[str] = None,
        retry_after_s: Optional[int] = None,
    ) -> None:
        default_status, default_msg = CODIGOS.get(codigo, (500, "Erro na transcrição."))
        self.codigo = codigo
        self.status = status if status is not None else default_status
        self.mensagem = mensagem or default_msg
        if retry_after_s is None and self.status in (429, 503):
            retry_after_s = DEFAULT_RETRY_AFTER_S
        self.retry_after_s = retry_after_s
        super().__init__(f"{codigo}: {self.mensagem}")


def mensagem_de(codigo: Optional[str]) -> str:
    """pt-BR message for a stored ``erro_codigo`` (generic text when unknown)."""
    return CODIGOS.get(codigo or "", (0, "Falha na transcrição."))[1]


def erro_response(exc: TranscricaoErro) -> JSONResponse:
    headers = {"Retry-After": str(int(exc.retry_after_s))} if exc.retry_after_s else None
    return JSONResponse(
        status_code=exc.status,
        content={"codigo": exc.codigo, "mensagem": exc.mensagem, "detail": exc.mensagem},
        headers=headers,
    )
