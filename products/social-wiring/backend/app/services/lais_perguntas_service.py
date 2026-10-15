"""Lais "Perguntas essenciais" (lais-build-contract section 4, wave 2).

The org picks the questions Julia asks from a global catalogue (`lais_perguntas_catalogo`):
<= 8 active, <= 5 qualifying, `objetivo` always on. The API validates first (typed 422/409), the
trigger on `lais_perguntas_org` (migration 269) is the DB backstop.

Wiring (at import, by registry -- nobody edits the foundation builders):
  * contexto provider `perguntas`  -> the org's active questions (filtered by the contato's operacao)
  * action handler  `salvar_slots` -> the foundation handler, with CPF/renda protected first
    (contract 17). Key validation stays the foundation's: a key must be in `contexto.perguntas`.

An org with no stored rows still has `objetivo` active (and qualifying): a virtual default, so a fresh
org is never asked nothing and never asked 63 things.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_acoes_service, lais_contexto_service
from app.services import lais_slots_sensiveis as sensiveis

logger = logging.getLogger(__name__)

T_CATALOGO = "lais_perguntas_catalogo"
T_ORG = "lais_perguntas_org"
OBJETIVO = "objetivo"
MAX_ATIVAS = 8
MAX_QUALIFICATORIAS = 5


# ── reads ───────────────────────────────────────────────────────────────────
def listar_catalogo(client: Any) -> list[dict[str, Any]]:
    rows = client.table(T_CATALOGO).select("*").execute().data or []
    return sorted(rows, key=lambda r: (r.get("ordem") is None, r.get("ordem")))


def _linhas(client: Any, org_id: UUID | str) -> dict[str, bool]:
    """`{chave: qualificatoria}` of the ACTIVE stored rows (no virtual default)."""
    rows = client.table(T_ORG).select("*").eq("org_id", str(org_id)).execute().data or []
    return {r["chave"]: bool(r.get("qualificatoria")) for r in rows if r.get("ativa", True)}


def selecao_org(client: Any, org_id: UUID | str) -> dict[str, dict[str, bool]]:
    """`{chave: {ativa, qualificatoria}}` of the org's ACTIVE questions, `objetivo` always present."""
    out = {c: {"ativa": True, "qualificatoria": q} for c, q in _linhas(client, org_id).items()}
    out.setdefault(OBJETIVO, {"ativa": True, "qualificatoria": True})
    return out


def _sem_criterios(_client: Any, _org_id: UUID | str) -> dict[str, list[str]]:
    return {}


#: Wave 3 (`lais_envio_criterios`) binds its reader here with `registrar_criterios`; until that table
#: exists no question is referenced by a send criterion.
_criterios_fn: Callable[[Any, UUID | str], dict[str, list[str]]] = _sem_criterios


def registrar_criterios(fn: Callable[[Any, UUID | str], dict[str, list[str]]]) -> None:
    global _criterios_fn
    _criterios_fn = fn


def criterios_que_usam(client: Any, org_id: UUID | str) -> dict[str, list[str]]:
    """`{chave: [criterion names]}` of the wave-3 send criteria that reference a question."""
    return _criterios_fn(client, org_id)


def montar_saida(client: Any, org_id: UUID | str) -> dict[str, Any]:
    sel = selecao_org(client, org_id)
    usadas = criterios_que_usam(client, org_id)
    catalogo = []
    for q in listar_catalogo(client):
        s = sel.get(q["chave"])
        catalogo.append({
            "chave": q["chave"], "label": q["label"], "dica": q.get("dica"), "categoria": q["categoria"],
            "operacao": q.get("operacao"), "ativa": s is not None,
            "qualificatoria": bool(s and s["qualificatoria"]),
            "bloqueada": q["chave"] == OBJETIVO, "usada_em_criterio": bool(usadas.get(q["chave"])),
        })
    return {"catalogo": catalogo, "limites": {"max_ativas": MAX_ATIVAS, "max_qualificatorias": MAX_QUALIFICATORIAS}}


# ── write (full replace) ────────────────────────────────────────────────────
def validar_selecao(selecao: list[dict[str, Any]], chaves_catalogo: set[str]) -> dict[str, bool]:
    """-> `{chave: qualificatoria}`; raises the contract's typed 422s."""
    vistas: dict[str, bool] = {}
    for item in selecao:
        chave = item["chave"]
        if chave not in chaves_catalogo:
            raise AppException("chave_desconhecida", f"Pergunta desconhecida: {chave}.", status_code=422,
                               details={"chave": chave})
        if chave in vistas:
            raise AppException("selecao_invalida", f"Pergunta repetida: {chave}.", status_code=422,
                               details={"chave": chave})
        vistas[chave] = bool(item.get("qualificatoria"))
    if OBJETIVO not in vistas:
        raise AppException("objetivo_obrigatorio",
                           "Esta pergunta é essencial para a identificação da operação correta.", status_code=422)
    if len(vistas) > MAX_ATIVAS:
        raise AppException("limite_ativas", "Você atingiu o limite de perguntas adicionadas.", status_code=422,
                           details={"max": MAX_ATIVAS})
    if sum(vistas.values()) > MAX_QUALIFICATORIAS:
        raise AppException("limite_qualificatorias", "Você atingiu o limite de perguntas qualificatórias.",
                           status_code=422, details={"max": MAX_QUALIFICATORIAS})
    return vistas


def substituir_selecao(client: Any, org_id: UUID | str, selecao: list[dict[str, Any]]) -> dict[str, Any]:
    chaves = {q["chave"] for q in listar_catalogo(client)}
    nova = validar_selecao(selecao, chaves)
    atual = _linhas(client, org_id)

    removidas = [c for c in atual if c not in nova]
    usadas = criterios_que_usam(client, org_id)
    bloqueadas = {c: usadas[c] for c in removidas if usadas.get(c)}
    if bloqueadas:
        criterios = sorted({n for nomes in bloqueadas.values() for n in nomes})
        raise AppException("usada_em_criterio", "Primeiro desative os critérios de envio que usam esta pergunta.",
                           status_code=409, details={"criterios": criterios, "chaves": sorted(bloqueadas)})

    org = str(org_id)
    tabela = client.table  # one attribute read, used per call below
    # Order keeps every intermediate state inside the limits (the DB trigger checks each write):
    # deletions, then qualifying -> plain, then everything else.
    for chave in removidas:
        tabela(T_ORG).delete().eq("org_id", org).eq("chave", chave).execute()
    for chave, qual in nova.items():
        if not qual and atual.get(chave):
            tabela(T_ORG).upsert({"org_id": org, "chave": chave, "ativa": True, "qualificatoria": False},
                                 on_conflict="org_id,chave").execute()
    for chave, qual in nova.items():
        if qual or chave not in atual:
            tabela(T_ORG).upsert({"org_id": org, "chave": chave, "ativa": True, "qualificatoria": qual},
                                 on_conflict="org_id,chave").execute()
    return montar_saida(client, org_id)


# ── contexto provider ───────────────────────────────────────────────────────
def contexto_provider(ctx: lais_contexto_service.ContextoCtx) -> dict[str, Any]:
    sel = selecao_org(ctx.client, ctx.org_id)
    op = ctx.contato.get("operacao")
    perguntas: list[dict[str, Any]] = []
    for q in listar_catalogo(ctx.client):
        s = sel.get(q["chave"])
        if s is None:
            continue
        if q.get("operacao") and op in ("compra", "aluguel") and q["operacao"] != op:
            continue
        perguntas.append({
            "chave": q["chave"], "label": q["label"], "dica": q.get("dica"), "categoria": q["categoria"],
            "qualificatoria": s["qualificatoria"], "operacao": q.get("operacao"),
        })
    return {"perguntas": perguntas}


# ── salvar_slots handler: protect CPF / renda, then the foundation handler ──
def _h_salvar_slots(ctx: lais_acoes_service.AcaoCtx, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    slots = payload.get("slots")
    if not isinstance(slots, dict):
        return lais_acoes_service._h_salvar_slots(ctx, payload)  # noqa: SLF001 - same-package base handler
    protegidos: dict[str, Any] = {}
    descartados: list[str] = []
    for chave, valor in slots.items():
        if str(chave) in sensiveis.SENSIVEIS:
            if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
                protegidos[chave] = valor  # base handler ignores it
                continue
            prot = sensiveis.proteger(str(chave), valor, str(ctx.org_id))
            if prot is None:
                descartados.append(str(chave))
                continue
            protegidos[chave] = prot
        else:
            protegidos[chave] = valor
    res = lais_acoes_service._h_salvar_slots(ctx, {**payload, "slots": protegidos}) or {}  # noqa: SLF001
    if descartados:
        res = {**res, "ignorados": [*res.get("ignorados", []), *descartados]}
    return res


def registrar() -> None:
    lais_contexto_service.registrar_provider("perguntas", contexto_provider)
    lais_acoes_service.registrar_handler("salvar_slots", _h_salvar_slots)


registrar()
