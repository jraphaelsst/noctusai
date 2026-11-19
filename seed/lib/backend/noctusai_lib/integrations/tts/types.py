"""TTS seam value objects, ports and coded errors.

`synthesize` returns word timings as seed-domain words (`texto/inicio_s/fim_s`);
vendor JSON (ElevenLabs character alignment) stops at the mapper
(`alignment.py`). Errors carry a stable `codigo` + the HTTP-ish `status` the
callers already branch on; none of them ever carries the API key or the text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured


class TtsError(Exception):
    """Base. `codigo` is stable/machine-readable; `status` mirrors the HTTP class."""

    codigo = "tts_erro"

    def __init__(self, message: str, *, status: Optional[int] = None, codigo: Optional[str] = None):
        super().__init__(message)
        self.status = status
        if codigo:
            self.codigo = codigo


class TtsRefused(TtsError):
    """Refused by one of OUR guards (cap, balance, consent). No vendor call was made."""

    def __init__(self, message: str, *, codigo: str = "recusado"):
        super().__init__(message, status=422, codigo=codigo)


class ConsentimentoAusente(TtsRefused):
    """The voice's holder has no valid consent on file for this org."""

    def __init__(self, message: str = "consentimento da voz ausente ou revogado; nenhuma chamada foi feita"):
        super().__init__(message, codigo="consentimento_ausente")


class TtsUpstreamError(TtsError):
    """The vendor (or the network) failed. `status` is the upstream status, 502 when unreachable."""

    codigo = "upstream"


class TtsNotConfigured(TtsError, IntegrationNotConfigured):
    """No API key resolved. Never degrades to the Fake unless the caller opts in."""

    codigo = "nao_configurado"

    def __init__(self, message: str = "elevenlabs_api_key nao configurada"):
        super().__init__(message, status=424)


@runtime_checkable
class ConsentChecker(Protocol):
    """Implemented by the product (its consent ledger). `voice_id` is the voice being used or,
    for `clone_instant` (the voice does not exist yet), the consent reference being exercised."""

    def vigente(self, org: Optional[str], voice_id: str) -> bool: ...


@dataclass(frozen=True)
class PalavraTiming:
    texto: str
    inicio_s: float
    fim_s: float


@dataclass(frozen=True)
class TtsResult:
    audio_path: str
    timings: list[PalavraTiming]
    caracteres: int
    creditos_cobrados: Optional[int]
    request_id: Optional[str]
    audio_s: Optional[float]
    creditos_fonte: str = "indisponivel"  # response_header | estimado_multiplicador | indisponivel
    audio_s_fonte: Optional[str] = None  # alinhamento | estimado_bitrate
    timings_path: Optional[str] = None


@dataclass(frozen=True)
class Preflight:
    """What a synthesize would cost, with zero spend."""

    caracteres: int
    model: str
    creditos_max: Optional[float]
    max_texto_por_chamada: Optional[int]
    saldo: Optional[int]
    tier: Optional[str] = None
    limite: Optional[int] = None
    basis: str = ""


@dataclass(frozen=True)
class CloneResult:
    voice_id: Optional[str]
    requires_verification: Optional[bool] = None
    library_voice_match: Optional[dict] = None
    extra: dict = field(default_factory=dict)


@runtime_checkable
class TtsClient(Protocol):
    def estimate(self, text: str, model: str) -> Optional[float]: ...

    def synthesize(self, text: str, voice_id: str, model: str, *, consent_ref: str, **opts) -> TtsResult: ...
