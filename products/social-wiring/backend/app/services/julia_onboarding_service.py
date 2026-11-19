"""Staff-channel writes of the operational settings an onboarding interview collects (agents -> social-wiring).

The allow-list below is the WHOLE surface: a setting not in :data:`SETTINGS` is refused (422 ``setting_nao_permitida``)
before anything is read or written. Each setting maps onto the SAME service the org-admin route calls (one write path,
one validator); this module only supplies the body shape the interview produces and the merge for sectioned settings.
Every applied write records ONE ``configuracao_alterada`` event (``julia_eventos``) with the acting platform user and
``via=onboarding`` -- ids, setting names and key names only, never a value.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from noctusai_lib.primitives.exceptions import AppException

from app.services import julia_avaliacoes_service as avaliacoes
from app.services import julia_conhecimento_service as conhecimento
from app.services import julia_envio_service as envio
from app.services import julia_eventos_service as eventos
from app.services import julia_reengajamento_service as reengajamento

logger = logging.getLogger(__name__)

VIA = "onboarding"
AREA = "onboarding"


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Reengajamento(_Estrito):
    minutos_ativo: Optional[bool] = None
    minutos_intervalo: Optional[int] = None
    horas_ativo: Optional[bool] = None
    horas_intervalo: Optional[int] = None


class _Frios(_Estrito):
    ativo: Optional[bool] = None
    minutos: Optional[int] = Field(default=None, ge=1, le=1440)


class _FriosInvalido(_Estrito):
    frios: Optional[_Frios] = None
    whatsapp_invalido: Optional[bool] = None


class _Captacoes(_Estrito):
    captacoes: str


class _Pesquisa(_Estrito):
    pesquisa: bool


class _EnderecoCompleto(_Estrito):
    endereco_completo: bool


class _Ativo(_Estrito):
    ativo: bool


class _Recesso(_Estrito):
    inicio: date
    fim: date
    mensagem: str = Field(min_length=1, max_length=500)


class _Url(_Estrito):
    url: str = Field(min_length=1, max_length=500)


def _reengajamento(client: Any, org: UUID, c: _Reengajamento, ator: str) -> list[str]:
    from app.routers.julia_reengajamento_router import ConfigUpdate  # the admin route's own validators

    valores = c.model_dump(exclude_none=True)
    try:
        ConfigUpdate.model_validate(valores)
    except ValidationError as exc:
        raise AppException(
            "config_invalida", "Valores de reengajamento inválidos.", 422,
            {"erros": [".".join(str(p) for p in e["loc"]) for e in exc.errors()]},
        ) from exc
    reengajamento.salvar_config(client, org, valores, registrar_evento=False)  # this service records the one event
    return sorted(valores)


def _politicas(client: Any, org: UUID, patch: dict[str, Any]) -> list[str]:
    envio.salvar_politicas(client, org, patch)
    return sorted(patch)


def _secao(client: Any, org: UUID, secao: str, mudar: dict[str, Any], ator: str) -> list[str]:
    atual = conhecimento.ler_secoes(client, org)[secao]
    dados = {**(atual.get("dados") or {}), **mudar}
    conhecimento.salvar_secao(client, org, secao, dados, int(atual["versao"]), ator)
    return sorted(mudar)


def _avaliacao(client: Any, org: UUID, c: _Url, ator: str) -> list[str]:
    avaliacoes.salvar_config(client, org, {"google_review_url": c.url})
    return ["google_review_url"]


def _aplicadores() -> dict[str, tuple[type[_Estrito], Callable[[Any, UUID, Any, str], list[str]]]]:
    return {
        "reengajamento": (_Reengajamento, _reengajamento),
        "envio_frios_invalido": (_FriosInvalido, lambda cl, o, c, a: _politicas(cl, o, c.model_dump(exclude_none=True))),
        "envio_captacoes": (_Captacoes, lambda cl, o, c, a: _politicas(cl, o, {"captacoes": c.captacoes})),
        "pesquisa": (_Pesquisa, lambda cl, o, c, a: _politicas(cl, o, {"pesquisa": c.pesquisa})),
        "politica_endereco": (_EnderecoCompleto, lambda cl, o, c, a: _secao(cl, o, "endereco_iptu", {"endereco_completo": c.endereco_completo}, a)),
        "politica_iptu": (_Ativo, lambda cl, o, c, a: _secao(cl, o, "endereco_iptu", {"usar_iptu": c.ativo}, a)),
        "mostrar_atendente": (_Ativo, lambda cl, o, c, a: _secao(cl, o, "exibir_atendente", {"ativo": c.ativo}, a)),
        "recesso": (_Recesso, lambda cl, o, c, a: _secao(cl, o, "recesso", {"ativo": True, **c.model_dump(mode="json")}, a)),
        "avaliacao_google": (_Url, _avaliacao),
    }


#: The closed allow-list (setting id = the interview checklist's destination id).
SETTINGS: frozenset[str] = frozenset(_aplicadores())


def org_existe(core_client: Any, org_id: UUID) -> bool:
    """``public.organizations`` row exists. A read failure is NOT 'absent' (it raises: the route answers a typed 503)."""
    rows = core_client.table("organizations").select("id").eq("id", str(org_id)).limit(1).execute().data or []
    return bool(rows)


def aplicar(
    client: Any, org_id: UUID, setting: str, corpo: dict[str, Any], *, ator_id: str, grant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Validate ``corpo`` for ``setting`` (422 ``setting_nao_permitida`` / ``corpo_invalido``), write it through the
    setting's own service, record the event. Returns ``{setting, chaves, evento_registrado}``."""
    entrada = _aplicadores().get(setting)
    if entrada is None:
        raise AppException(
            "setting_nao_permitida", "Esta configuração não é aplicável pelo canal de onboarding.", 422, {"setting": setting},
        )
    modelo, aplicar_fn = entrada
    try:
        c = modelo.model_validate(corpo)
    except ValidationError as exc:
        raise AppException(
            "corpo_invalido", "Corpo inválido para esta configuração.", 422,
            {"setting": setting, "erros": [{"campo": ".".join(str(p) for p in e["loc"]), "motivo": e["msg"]} for e in exc.errors()]},
        ) from exc
    chaves = aplicar_fn(client, org_id, c, ator_id)
    payload: dict[str, Any] = {"area": AREA, "setting": setting, "chaves": chaves, "ator": ator_id, "via": VIA}
    if grant_id:
        payload["grant_id"] = grant_id
    stored = eventos.emitir(client, org_id, "configuracao_alterada", None, payload)
    if stored is None:
        logger.error("julia_onboarding: setting applied but event NOT recorded org=%s setting=%s ator=%s", org_id, setting, ator_id)
    return {"setting": setting, "chaves": chaves, "evento_registrado": stored is not None}


__all__ = ["SETTINGS", "aplicar", "org_existe"]
