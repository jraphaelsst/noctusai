"""THE sanctioned way to make an AI call the platform owns: prompt + model + vendor come from the database registry
(``public.plataforma_agentes``), never from code.

* :func:`prompt_e_modelo` -- ``(prompt, modelo, vendor)`` of an active row (cached ~30 s per process).
* :func:`chamar_ia` -- chat. The row's prompt is the ``system`` message, routed to the row's vendor+model.
* :func:`chamar_ia_visao` -- vision. The row's prompt is the instruction sent with the image(s).
* :func:`transcrever_ia` -- transcription. The row's prompt (optional) is passed as the vendor's transcription prompt.

Every call goes through the seed LLM seam (``noctusai_lib.integrations.llm``; Anthropic and OpenAI Real adapters are
registered there), is attributed in the central ``ai_usage`` ledger as feature ``plataforma.<chave>`` and is measured
into ``public.plataforma_agente_chamadas`` (tokens, USD cost, latency, ok/error class; never text). A failed provider
call is measured ``ok=false`` and re-raised; failing to WRITE the measurement is logged at ERROR and never replaces
the call's result.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Awaitable, Callable, Optional, Sequence, Union

from .factory import get_prompt_registry
from .protocol import PromptRegistry
from .types import KIND_POR_CAPACIDADE, chave_valida, ChamadaMedida, ChaveNaoEncontrada, PromptEntry, RegistroIAIndisponivel

__all__ = [
    "ChamadaIA", "TTL_S", "chamar_ia", "chamar_ia_visao", "invalidar_cache", "modelos_permitidos",
    "prompt_e_modelo", "transcrever_ia",
]

logger = logging.getLogger(__name__)

TTL_S = 30.0
VENDORS = ("anthropic", "openai")

_cache: dict[str, tuple[float, PromptEntry]] = {}
_lock = Lock()


def invalidar_cache(chave: Optional[str] = None) -> None:
    with _lock:
        if chave is None:
            _cache.clear()
        else:
            _cache.pop(chave, None)


def _entry(chave: str, registry: Optional[PromptRegistry], agora: Callable[[], float]) -> PromptEntry:
    if not chave_valida(chave):
        raise RegistroIAIndisponivel(f"platform AI call id {chave!r} is not a dotted lowercase logical id")
    cacheavel = registry is None  # an injected registry (tests) bypasses the process cache
    if cacheavel:
        with _lock:
            hit = _cache.get(chave)
        if hit and agora() - hit[0] < TTL_S:
            return hit[1]
        registry = get_prompt_registry()
    try:
        row = registry.obter(chave)
    except ChaveNaoEncontrada as exc:
        raise RegistroIAIndisponivel(f"platform AI call {chave!r} is not registered") from exc
    except RegistroIAIndisponivel:
        raise
    except Exception as exc:
        raise RegistroIAIndisponivel(f"platform AI call {chave!r} could not be read: {exc}") from exc
    if not row.ativo:
        raise RegistroIAIndisponivel(f"platform AI call {chave!r} is inactive")
    if cacheavel:
        with _lock:
            _cache[chave] = (agora(), row)
    return row


def prompt_e_modelo(
    chave: str, *, registry: Optional[PromptRegistry] = None, agora: Callable[[], float] = time.monotonic,
) -> tuple[str, str, str]:
    """``(prompt, modelo, vendor)`` of the active registry row ``chave``. Raises :class:`RegistroIAIndisponivel`."""
    row = _entry(chave, registry, agora)
    return row.prompt, row.modelo, row.vendor


def modelos_permitidos(vendor: str, capacidade: str = "chat") -> list[dict[str, Any]]:
    """The models of the ``capacidade`` (chat|vision|transcription) the seed catalog lists for ``vendor`` (effective catalog: operator overlay applied, stubs
    and duplicate ids dropped). The single list the registry validates ``modelo`` against."""
    from noctusai_lib.integrations.llm.models import models_for

    vistos: dict[str, dict[str, Any]] = {}
    for m in models_for(vendor, KIND_POR_CAPACIDADE[capacidade]):
        if m.stub or m.id in vistos:
            continue
        vistos[m.id] = {
            "id": m.id, "label": m.label, "vendor": m.provider, "descricao": m.description,
            "custo_input_1m": m.cost_per_1m_input_tokens, "custo_output_1m": m.cost_per_1m_output_tokens,
        }
    return list(vistos.values())


@dataclass(frozen=True)
class ChamadaIA:
    texto: str
    chave: str
    vendor: str
    modelo: str
    latencia_ms: int
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None
    custo_usd: Optional[float] = None


async def _executar(
    chave: str, capacidade: str, registry: Optional[PromptRegistry],
    chamar: Callable[[PromptEntry], Awaitable[Any]],
) -> ChamadaIA:
    import anyio.to_thread

    from noctusai_lib.integrations.llm import attribution

    reg = registry if registry is not None else get_prompt_registry()
    row = await anyio.to_thread.run_sync(lambda: _entry(chave, registry, time.monotonic))
    inicio = time.perf_counter()
    try:
        with attribution.llm_usage_context(feature=f"plataforma.{chave}", agent_key=chave):
            res = await chamar(row)
    except Exception as exc:
        await _medir(reg, ChamadaMedida(
            chave, row.vendor, row.modelo, round((time.perf_counter() - inicio) * 1000), False,
            erro=type(exc).__name__, capacidade=capacidade))
        raise
    ms = round((time.perf_counter() - inicio) * 1000)
    texto, u = (res if isinstance(res, tuple) else (res, None))
    await _medir(reg, ChamadaMedida(
        chave, row.vendor, row.modelo, ms, True, capacidade=capacidade,
        tokens_entrada=u.prompt_tokens if u else None, tokens_saida=u.completion_tokens if u else None,
        custo_usd=u.cost_usd if u else None))
    return ChamadaIA(
        texto=texto, chave=chave, vendor=row.vendor, modelo=row.modelo, latencia_ms=ms,
        tokens_entrada=u.prompt_tokens if u else None, tokens_saida=u.completion_tokens if u else None,
        custo_usd=u.cost_usd if u else None)


async def _medir(registry: PromptRegistry, chamada: ChamadaMedida) -> None:
    import anyio.to_thread

    try:
        await anyio.to_thread.run_sync(registry.registrar_chamada, chamada)
    except Exception:
        logger.exception("could not record the measurement of platform AI call %s", chamada.chave)


async def chamar_ia(
    chave: str, messages: list[dict], *, org_id: Optional[str] = None, registry: Optional[PromptRegistry] = None,
    chat: Optional[Callable[..., Awaitable[Any]]] = None, **kwargs: Any,
) -> ChamadaIA:
    """Chat call: ``[{"role": "system", "content": <row prompt>}, *messages]`` to the row's vendor and model.
    ``chat`` is a test seam (default: ``llm.chat_usage.chat_completion_with_usage``)."""
    if chat is None:
        from noctusai_lib.integrations.llm.chat_usage import chat_completion_with_usage as chat

    async def chamar(row: PromptEntry):
        r = await chat(
            [{"role": "system", "content": row.prompt}, *messages],
            model=row.modelo, provider=row.vendor, org_id=org_id, **kwargs)
        return r.text, r.usage

    return await _executar(chave, "chat", registry, chamar)


async def chamar_ia_visao(
    chave: str, image: Union[bytes, str, Sequence[Union[bytes, str]]], *, org_id: Optional[str] = None,
    registry: Optional[PromptRegistry] = None, analisar: Optional[Callable[..., Awaitable[Any]]] = None,
    **kwargs: Any,
) -> ChamadaIA:
    """Vision call: the row's prompt is the instruction sent with ``image`` to the row's vendor and model.
    NOTE: ``llm.vision.analyze_image`` exposes no per-call usage, so tokens/cost are ``None`` (unmeasured, not zero) --
    latency and ok/error are measured; the central ``ai_usage`` ledger still prices the call."""
    if analisar is None:
        from noctusai_lib.integrations.llm.vision import analyze_image as analisar

    async def chamar(row: PromptEntry):
        return await analisar(image, row.prompt, model=row.modelo, provider=row.vendor, org_id=org_id, **kwargs), None

    return await _executar(chave, "vision", registry, chamar)


async def transcrever_ia(
    chave: str, audio: bytes, *, org_id: Optional[str] = None, registry: Optional[PromptRegistry] = None,
    transcrever: Optional[Callable[..., Awaitable[Any]]] = None, **kwargs: Any,
) -> ChamadaIA:
    """Transcription call to the row's vendor and audio model; the row's prompt is forwarded as ``prompt`` (the
    vendor's vocabulary hint) when non-empty. Tokens/cost are ``None`` (``transcribe_audio`` exposes no usage); the
    central ledger still records the call."""
    if transcrever is None:
        from noctusai_lib.integrations.llm.audio import transcribe_audio as transcrever

    async def chamar(row: PromptEntry):
        extra = {"prompt": row.prompt} if row.prompt.strip() else {}
        return await transcrever(audio, model=row.modelo, provider=row.vendor, org_id=org_id, **extra, **kwargs), None

    return await _executar(chave, "transcription", registry, chamar)
