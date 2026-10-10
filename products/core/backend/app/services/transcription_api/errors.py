"""``{codigo, mensagem}`` error envelope for the transcription API (CONTRACT §2)."""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

# codigo -> (HTTP status, pt-BR message). One table: the status is a property
# of the code, never of the call site.
CODIGOS: dict[str, tuple[int, str]] = {
    "escopo_insuficiente": (403, "Credencial sem permissão para esta operação."),
    "nao_encontrada": (404, "Transcrição não encontrada."),
    "em_processamento": (409, "A transcrição está em processamento e não pode ser removida agora."),
    "arquivo_grande": (413, "Arquivo acima do tamanho máximo permitido."),
    "formato_invalido": (415, "Formato de áudio não suportado."),
    "duracao_excedida": (422, "Duração do áudio acima do máximo permitido."),
    "audio_vazio": (422, "O áudio está vazio ou é curto demais."),
    "audio_corrompido": (422, "Não foi possível ler o áudio enviado."),
    "limite_requisicoes": (429, "Muitas requisições. Tente novamente em instantes."),
    "limite_envios_hora": (429, "Limite de envios por hora atingido."),
    "cota_diaria_chamador": (429, "Cota diária de minutos do chamador atingida."),
    "cota_diaria_org": (429, "Cota diária de minutos da organização atingida."),
    "limite_em_andamento": (429, "Há transcrições demais em andamento para este chamador."),
    "fila_cheia": (503, "A fila de transcrição está cheia. Tente novamente em instantes."),
    "capacidade_diaria": (503, "Capacidade diária de transcrição esgotada."),
    "transcricao_indisponivel": (503, "O serviço de transcrição está indisponível no momento."),
    "transcricao_desativada": (503, "O serviço de transcrição está desativado."),
}

#: Codes the quota RPC may answer (``reservar_transcricao_api``) — a code
#: outside this set is a contract break, surfaced as 503 not guessed at.
CODIGOS_RPC = frozenset(
    {
        "limite_envios_hora",
        "cota_diaria_chamador",
        "limite_em_andamento",
        "cota_diaria_org",
        "capacidade_diaria",
        "fila_cheia",
    }
)


class TranscricaoErro(Exception):
    """Raised anywhere in the API; rendered by :func:`transcricao_erro_handler`."""

    def __init__(self, codigo: str, *, retry_after_s: Optional[float] = None):
        if codigo not in CODIGOS:
            raise ValueError(f"unknown transcription error codigo: {codigo!r}")
        super().__init__(codigo)
        self.codigo = codigo
        self.status_code, self.mensagem = CODIGOS[codigo]
        self.retry_after_s = retry_after_s

    def headers(self) -> Optional[dict[str, str]]:
        # Every 429/503 carries Retry-After (CONTRACT §2).
        if self.status_code in (429, 503):
            return {"Retry-After": str(max(1, int(round(self.retry_after_s or 30))))}
        return None


MENSAGENS_FALHA: dict[str, str] = {
    "transcricao_indisponivel": CODIGOS["transcricao_indisponivel"][1],
    "audio_corrompido": CODIGOS["audio_corrompido"][1],
    "audio_vazio": CODIGOS["audio_vazio"][1],
    "duracao_excedida": CODIGOS["duracao_excedida"][1],
    "formato_invalido": CODIGOS["formato_invalido"][1],
    "tempo_excedido": "A transcrição excedeu o tempo máximo de processamento.",
    "armazenamento": "Falha ao armazenar o áudio enviado.",
    "audio_indisponivel": "O áudio não está mais disponível para processamento.",
}


def mensagem_de_falha(codigo: Optional[str]) -> str:
    return MENSAGENS_FALHA.get(codigo or "", "A transcrição falhou.")


async def transcricao_erro_handler(request: Request, exc: TranscricaoErro) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"codigo": exc.codigo, "mensagem": exc.mensagem},
        headers=exc.headers(),
    )
