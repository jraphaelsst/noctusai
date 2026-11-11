"""The scheduling classifier: ONE inbound message text in, a strict `{is_scheduling, confidence, reason_code}` out.

* The prompt, the model and the vendor come from the platform prompt registry (`public.plataforma_agentes`, key
  :data:`CHAVE`) through `chamar_ia` -- never from code (KB § PATTERNS/ai/prompts-from-registry.md). The call goes
  through the seed LLM seam, so the org's budget, the spend guard, the ai_usage ledger and the registry's own
  measurement table all apply.
* TEXT ONLY reaches the provider: the user turn is the message body and nothing else -- no phone, no chat_ref, no
  name, no intake id (plan item 4). `cache=False`: third-party message text never lands in the response cache.
* Model output is data; the server decides (canon §5): exactly one JSON object with exactly the three keys, a known
  reason code consistent with the boolean, confidence in [0, 1]. Anything else is :class:`SaidaInvalida` -- never a
  best-effort guess.
* `prompt_version` = ``<chave>@<sha256(prompt)[:12]>`` of the row actually sent: any edit in the registry UI moves it,
  which is what makes the (message, prompt_version, model) idempotency key and the replay meaningful.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from noctusai_lib.integrations.llm.exceptions import (
    LLMBudgetExceeded,
    LLMBudgetNotConfigured,
    LLMBudgetUnverifiable,
    LLMCreditsExhausted,
    LLMCreditsUnverifiable,
    SpendCeilingExceeded,
    SpendCeilingUnverifiable,
)
from noctusai_lib.integrations.prompt_registry import PromptRegistry, chamar_ia, prompt_e_modelo

CHAVE = "assistant.classificador_agendamento"

#: Upper bound of message text sent to the model (cost cap per call; the rest is cut and the cut is recorded).
MAX_CHARS_PADRAO = 4000
#: The classifier answers three short keys; anything longer is not a valid answer.
MAX_TOKENS = 80

MOTIVOS_SIM = ("pede_horario", "propoe_horario", "confirma_horario", "remarca", "cancela")
MOTIVOS_NAO = ("sem_agendamento", "insuficiente")
ReasonCode = Literal["pede_horario", "propoe_horario", "confirma_horario", "remarca", "cancela",
                     "sem_agendamento", "insuficiente"]

#: Every exception that means "the money gate refused or could not verify" -> outcome `skipped_budget` (fail-closed).
ERROS_ORCAMENTO: tuple[type[BaseException], ...] = (
    LLMBudgetExceeded, LLMBudgetUnverifiable, LLMBudgetNotConfigured,
    SpendCeilingExceeded, SpendCeilingUnverifiable,
    LLMCreditsExhausted, LLMCreditsUnverifiable,
)

_CERCA = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", re.DOTALL)


class SaidaInvalida(ValueError):
    """The model's answer is not the strict contract. Carries a reason CODE only, never the model's text."""

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo


class RegistroMudou(RuntimeError):
    """The registry row moved between the version read and the call: the job retries (nothing is written)."""


class Classificacao(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    is_scheduling: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason_code: ReasonCode


@dataclass(frozen=True)
class Resultado:
    classificacao: Classificacao
    modelo: str
    vendor: str
    prompt_version: str
    latencia_ms: int
    tokens_entrada: Optional[int]
    tokens_saida: Optional[int]
    custo_usd: Optional[float]
    truncado: bool

    def metadata(self, origem: str) -> dict[str, Any]:
        """Measurements only (latency, tokens, cost, vendor) -- never message or model text."""
        return {
            "origem": origem, "vendor": self.vendor, "latencia_ms": self.latencia_ms,
            "tokens_entrada": self.tokens_entrada, "tokens_saida": self.tokens_saida, "custo_usd": self.custo_usd,
            "truncado": self.truncado,
        }


def versao_do_prompt(prompt: str) -> str:
    return f"{CHAVE}@{hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:12]}"


def versao_atual(*, registry: Optional[PromptRegistry] = None) -> tuple[str, str]:
    """``(prompt_version, modelo)`` of the registry row as it stands now. Raises `RegistroIAIndisponivel`."""
    prompt, modelo, _vendor = prompt_e_modelo(CHAVE, registry=registry)
    return versao_do_prompt(prompt), modelo


def interpretar(texto: str) -> Classificacao:
    """Strict parse of the model's answer. A ```json fence around the object is the only tolerance."""
    bruto = (texto or "").strip()
    cerca = _CERCA.match(bruto)
    if cerca:
        bruto = cerca.group(1).strip()
    if not (bruto.startswith("{") and bruto.endswith("}")):
        raise SaidaInvalida("nao_e_objeto_json")
    try:
        dados = json.loads(bruto)
    except ValueError:
        raise SaidaInvalida("json_invalido") from None
    if not isinstance(dados, dict):
        raise SaidaInvalida("nao_e_objeto_json")
    if isinstance(dados.get("confidence"), int) and not isinstance(dados.get("confidence"), bool):
        dados["confidence"] = float(dados["confidence"])  # `1` / `0` are valid confidences in JSON
    try:
        c = Classificacao.model_validate(dados)
    except ValidationError:
        raise SaidaInvalida("fora_do_contrato") from None
    if c.is_scheduling != (c.reason_code in MOTIVOS_SIM):
        raise SaidaInvalida("motivo_incoerente")
    return c


async def classificar(
    texto: str,
    *,
    org_id: str,
    max_chars: int = MAX_CHARS_PADRAO,
    registry: Optional[PromptRegistry] = None,
    chat: Optional[Callable[..., Awaitable[Any]]] = None,
) -> Resultado:
    """Classify one message text. Raises: an :data:`ERROS_ORCAMENTO` member (budget refused / unverifiable),
    :class:`SaidaInvalida`, `RegistroIAIndisponivel`, or the seam's provider errors (`LLMAPIError`, ...).

    ``registry`` / ``chat`` are the seed's own test seams of `chamar_ia` (a Fake registry, a recording chat)."""
    corpo = texto or ""
    truncado = len(corpo) > max_chars
    if truncado:
        corpo = corpo[:max_chars]
    prompt, modelo, _vendor = prompt_e_modelo(CHAVE, registry=registry)
    versao = versao_do_prompt(prompt)
    extra: dict[str, Any] = {"chat": chat} if chat is not None else {}
    r = await chamar_ia(
        CHAVE, [{"role": "user", "content": corpo}], org_id=str(org_id), registry=registry,
        temperature=0, max_tokens=MAX_TOKENS, cache=False, purpose="classify", **extra,
    )
    # The row is read twice (here for the version, inside chamar_ia for the call), both through the same ~30 s process
    # cache; an edit landing between the two reads would label the output with the wrong version -> refuse, retry.
    if r.modelo != modelo or versao_atual(registry=registry)[0] != versao:
        raise RegistroMudou("the registry row changed during the call")
    return Resultado(
        classificacao=interpretar(r.texto), modelo=r.modelo, vendor=r.vendor, prompt_version=versao,
        latencia_ms=r.latencia_ms, tokens_entrada=r.tokens_entrada, tokens_saida=r.tokens_saida,
        custo_usd=r.custo_usd, truncado=truncado,
    )
