"""Lais wave 12 -- Disparos (mass sends, contract 14 / A6).

A disparo = one approved modelo + one segment, fanned out to targets (`lais_disparo_alvos`, status flow
`pendente -> enviado -> respondido -> enviado_sw | erro`). Types: `remarketing` (leads 3-15 / 7-30 days
without reply) and `atualizacao_anuncios` (owners, wave "Atualizacao de imoveis").

THE RULE (A6): everything can be created / edited / scheduled / cancelled on any transport; DISPATCH goes out
only as a Cloud-API template. `disparar` gates on `lais_transporte.cloud_configurada` FIRST and answers 409
`transporte_indisponivel` otherwise -- WAHA free text is never a mass send, and `WahaTransporte` itself
refuses a template, so there is no fallback to degrade into.

Guards (application-level, on top of the migration 275 CHECKs):
  * cap per send = 15 % of the org's month volume (contatos with an inbound in the last 30 days, min 1)
    -> 409 `limite_de_disparo`;
  * per-chat template cap: one phone receives at most `MAX_TEMPLATES_POR_CONTATO` templates per 30 days
    (the target is dropped as `limite_por_contato`);
  * an owner who opted out ("parar") is never contacted (`opt_out`).
A reply re-enters Julia's normal lead path untouched; `registrar_resposta` only flips the target.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_modelos_service, lais_transporte
from app.services.lais_transporte import Transporte

logger = logging.getLogger(__name__)

T_DISPAROS = "lais_disparos"
T_ALVOS = "lais_disparo_alvos"
T_CONTATOS = "lais_contatos"
T_PROPRIETARIOS = "lais_proprietarios_contatos"

TIPOS = ("remarketing", "atualizacao_anuncios")
#: segment -> (min days without reply, max days without reply); owners have no day window.
SEGMENTOS: dict[str, Optional[tuple[int, int]]] = {"leads_3_15": (3, 15), "leads_7_30": (7, 30), "proprietarios": None}
TIPO_DO_SEGMENTO = {"leads_3_15": "remarketing", "leads_7_30": "remarketing", "proprietarios": "atualizacao_anuncios"}
STATUS = ("rascunho", "agendado", "enviando", "enviado", "cancelado", "erro")
#: the page's tabs -> the statuses each shows.
ABAS: dict[str, Optional[tuple[str, ...]]] = {
    "todos": None, "rascunhos": ("rascunho",), "agendados": ("agendado",),
    "enviados": ("enviando", "enviado"), "cancelados": ("cancelado",), "erros": ("erro",),
}
MUTAVEIS = ("rascunho", "agendado")
CAP_PERCENTUAL = 0.15
JANELA_VOLUME_DIAS = 30
MAX_TEMPLATES_POR_CONTATO = 3
JANELA_POR_CONTATO_DIAS = 30


def _agora(agora: Optional[datetime] = None) -> datetime:
    return agora or datetime.now(timezone.utc)


def _nao_encontrado() -> AppException:
    return AppException("disparo_nao_encontrado", "Disparo não encontrado.", status_code=404)


SEGMENTOS_ROTULOS: dict[str, str] = {
    "leads_3_15": "Leads sem resposta há 3 a 15 dias",
    "leads_7_30": "Leads sem resposta há 7 a 30 dias",
    "proprietarios": "Proprietários de imóveis",
}


def lista_segmentos() -> list[dict[str, str]]:
    return [{"chave": k, "label": v} for k, v in SEGMENTOS_ROTULOS.items()]


def catalogo() -> dict[str, Any]:
    return {
        "tipos": list(TIPOS),
        "segmentos": [{"slug": s, "tipo": TIPO_DO_SEGMENTO[s], "dias_sem_resposta": list(v) if v else None} for s, v in SEGMENTOS.items()],
        "abas": list(ABAS),
        "cap_percentual": CAP_PERCENTUAL,
        "max_templates_por_contato": MAX_TEMPLATES_POR_CONTATO,
    }


# ── caps ────────────────────────────────────────────────────────────────────
def volume_mensal(db: Any, org_id: UUID | str, agora: Optional[datetime] = None) -> int:
    """The org's month volume: contatos that wrote in the last 30 days."""
    desde = (_agora(agora) - timedelta(days=JANELA_VOLUME_DIAS)).isoformat()
    res = db.table(T_CONTATOS).select("id", count="exact").eq("org_id", str(org_id)).gte("ultimo_inbound_at", desde).limit(1).execute()
    return int(res.count or 0)


def limite_por_disparo(db: Any, org_id: UUID | str, agora: Optional[datetime] = None) -> int:
    return max(1, math.floor(volume_mensal(db, org_id, agora) * CAP_PERCENTUAL))


def _enviados_na_janela(db: Any, org_id: UUID | str, telefone: str, agora: datetime) -> int:
    desde = (agora - timedelta(days=JANELA_POR_CONTATO_DIAS)).isoformat()
    res = db.table(T_ALVOS).select("id", count="exact").eq("org_id", str(org_id)).eq("telefone", telefone).in_(
        "status", ["enviado", "respondido", "enviado_sw"]).gte("enviado_at", desde).limit(1).execute()
    return int(res.count or 0)


# ── targets ─────────────────────────────────────────────────────────────────
def _telefone_do_contato(c: dict[str, Any]) -> Optional[str]:
    tel = "".join(ch for ch in str(c.get("telefone_e164") or "") if ch.isdigit())
    if not tel and str(c.get("chat_id") or "").endswith("@c.us"):
        tel = "".join(ch for ch in str(c["chat_id"]).split("@")[0] if ch.isdigit())
    return tel if 10 <= len(tel) <= 15 else None


def calcular_alvos(db: Any, org_id: UUID | str, segmento: str, agora: Optional[datetime] = None) -> list[dict[str, Any]]:
    """The people a segment selects right now: `[{contato_id | proprietario_id, telefone, nome, ...}]`, one per phone."""
    agora = _agora(agora)
    janela = SEGMENTOS.get(segmento)
    vistos: set[str] = set()
    alvos: list[dict[str, Any]] = []
    if segmento == "proprietarios":
        def page_p(start: int, end: int) -> Any:
            return db.table(T_PROPRIETARIOS).select("*").eq("org_id", str(org_id)).eq("opt_out", False).order("id").range(start, end).execute().data

        for p in iter_paged_rows(page_p, id_key="id", label="lais proprietarios alvos"):
            if p["telefone"] in vistos:
                continue
            vistos.add(p["telefone"])
            alvos.append({"proprietario_id": p["id"], "contato_id": None, "telefone": p["telefone"],
                          "nome": p.get("nome"), "imovel_codigo": p.get("imovel_codigo")})
        return alvos
    if janela is None:
        raise AppException("segmento_invalido", "Segmento desconhecido.", status_code=422, details={"validos": list(SEGMENTOS)})
    recente = (agora - timedelta(days=janela[0])).isoformat()  # silent for AT LEAST min days
    antigo = (agora - timedelta(days=janela[1])).isoformat()  # ... and at most max days

    def page_c(start: int, end: int) -> Any:
        return (
            db.table(T_CONTATOS).select("*").eq("org_id", str(org_id)).is_("encerrado_at", "null")
            .gte("ultimo_inbound_at", antigo).lte("ultimo_inbound_at", recente).order("id").range(start, end).execute().data
        )

    for c in iter_paged_rows(page_c, id_key="id", label="lais disparo alvos"):
        tel = _telefone_do_contato(c)
        if not tel or tel in vistos:
            continue
        vistos.add(tel)
        alvos.append({"contato_id": c["id"], "proprietario_id": None, "telefone": tel, "nome": c.get("nome"), "imovel_codigo": None})
    return alvos


def _materializar(db: Any, org_id: UUID | str, disparo: dict[str, Any], agora: datetime) -> list[dict[str, Any]]:
    """Snapshot the segment into `lais_disparo_alvos` (once: an existing snapshot is kept)."""
    existentes = db.table(T_ALVOS).select("*").eq("org_id", str(org_id)).eq("disparo_id", disparo["id"]).limit(1000).execute().data or []
    if existentes:
        return existentes
    novos = calcular_alvos(db, org_id, disparo["segmento"], agora)
    _checar_limite(db, org_id, len(novos), agora)
    rows = [{
        "id": str(uuid4()), "org_id": str(org_id), "disparo_id": disparo["id"], "contato_id": a["contato_id"],
        "proprietario_id": a["proprietario_id"], "telefone": a["telefone"], "status": "pendente",
    } for a in novos]
    for i in range(0, len(rows), 200):
        db.table(T_ALVOS).insert(rows[i:i + 200]).execute()
    db.table(T_DISPAROS).update({"total_alvos": len(rows), "updated_at": agora.isoformat()}).eq("org_id", str(org_id)).eq(
        "id", disparo["id"]).execute()
    return rows


def _checar_limite(db: Any, org_id: UUID | str, total: int, agora: datetime) -> None:
    cap = limite_por_disparo(db, org_id, agora)
    if total > cap:
        raise AppException(
            "limite_de_disparo",
            f"Um disparo pode atingir no máximo {int(CAP_PERCENTUAL * 100)}% do volume mensal ({cap} contatos); o segmento tem {total}.",
            status_code=409, details={"limite": cap, "alvos": total},
        )


def previa(db: Any, org_id: UUID | str, disparo_id: UUID | str, agora: Optional[datetime] = None) -> dict[str, Any]:
    d = obter(db, org_id, disparo_id)
    agora = _agora(agora)
    total = len(db.table(T_ALVOS).select("id").eq("org_id", str(org_id)).eq("disparo_id", d["id"]).limit(1000).execute().data or []) \
        or len(calcular_alvos(db, org_id, d["segmento"], agora))
    cap = limite_por_disparo(db, org_id, agora)
    return {"alvos": total, "limite": cap, "volume_mensal": volume_mensal(db, org_id, agora), "dentro_do_limite": total <= cap}


# ── CRUD ────────────────────────────────────────────────────────────────────
def obter(db: Any, org_id: UUID | str, disparo_id: UUID | str) -> dict[str, Any]:
    rows = db.table(T_DISPAROS).select("*").eq("org_id", str(org_id)).eq("id", str(disparo_id)).limit(1).execute().data or []
    if not rows:
        raise _nao_encontrado()
    return rows[0]


def detalhe(db: Any, org_id: UUID | str, disparo_id: UUID | str) -> dict[str, Any]:
    d = obter(db, org_id, disparo_id)
    alvos_completos = db.table(T_ALVOS).select("*").eq("org_id", str(org_id)).eq("disparo_id", d["id"]).limit(1000).execute().data or []
    alvos = alvos_completos
    contagem: dict[str, int] = {}
    for a in alvos:
        contagem[a["status"]] = contagem.get(a["status"], 0) + 1
    return {**d, "template_id": d["modelo_id"], "alvos_por_status": contagem, "alvos": alvos_completos}


def listar(db: Any, org_id: UUID | str, *, aba: str = "todos") -> list[dict[str, Any]]:
    if aba not in ABAS:
        raise AppException("aba_invalida", "Aba desconhecida.", status_code=422, details={"validas": list(ABAS)})
    q = db.table(T_DISPAROS).select("*").eq("org_id", str(org_id))
    if ABAS[aba]:
        q = q.in_("status", list(ABAS[aba]))
    return sorted(q.limit(500).execute().data or [], key=lambda r: str(r.get("created_at") or ""), reverse=True)


def _validar_segmento(tipo: str, segmento: str) -> None:
    if tipo not in TIPOS:
        raise AppException("tipo_invalido", "Tipo de disparo desconhecido.", status_code=422, details={"validos": list(TIPOS)})
    if segmento not in SEGMENTOS:
        raise AppException("segmento_invalido", "Segmento desconhecido.", status_code=422, details={"validos": list(SEGMENTOS)})
    if TIPO_DO_SEGMENTO[segmento] != tipo:
        raise AppException("segmento_incompativel", "O segmento não combina com o tipo do disparo.", status_code=422)


def criar(
    db: Any, org_id: UUID | str, *, nome: str, tipo: str, segmento: str, modelo_id: UUID | str,
    connection_id: Optional[UUID | str] = None, user_id: Any = None,
) -> dict[str, Any]:
    if not (1 <= len(nome.strip()) <= 80):
        raise AppException("nome_invalido", "O nome deve ter de 1 a 80 caracteres.", status_code=422)
    _validar_segmento(tipo, segmento)
    lais_modelos_service.obter(db, org_id, modelo_id)  # 404 for a modelo of another org / unknown
    row = {
        "id": str(uuid4()), "org_id": str(org_id), "nome": nome.strip(), "tipo": tipo, "segmento": segmento,
        "modelo_id": str(modelo_id), "connection_id": str(connection_id) if connection_id else None,
        "status": "rascunho", "created_by": str(user_id) if user_id else None,
    }
    created = db.table(T_DISPAROS).insert(row).execute().data or []
    if not created:
        raise RuntimeError("lais: disparo insert returned no row")
    return created[0]


def atualizar(db: Any, org_id: UUID | str, disparo_id: UUID | str, patch: dict[str, Any]) -> dict[str, Any]:
    d = obter(db, org_id, disparo_id)
    if d["status"] not in MUTAVEIS:
        raise AppException("disparo_nao_editavel", "Só disparos em rascunho ou agendados podem ser editados.", status_code=409)
    campos = {k: v for k, v in patch.items() if k in ("nome", "segmento", "modelo_id", "connection_id") and v is not None}
    if "segmento" in campos:
        _validar_segmento(d["tipo"], campos["segmento"])
    if "modelo_id" in campos:
        lais_modelos_service.obter(db, org_id, campos["modelo_id"])
        campos["modelo_id"] = str(campos["modelo_id"])
    if "connection_id" in campos:
        campos["connection_id"] = str(campos["connection_id"])
    if "nome" in campos:
        campos["nome"] = campos["nome"].strip()
    if campos:
        if "segmento" in campos and campos["segmento"] != d["segmento"]:
            # the target snapshot belonged to the old segment
            db.table(T_ALVOS).delete().eq("org_id", str(org_id)).eq("disparo_id", d["id"]).execute()
            campos.update(total_alvos=0)
        campos["updated_at"] = _agora().isoformat()
        db.table(T_DISPAROS).update(campos).eq("org_id", str(org_id)).eq("id", d["id"]).execute()
    return obter(db, org_id, disparo_id)


def apagar(db: Any, org_id: UUID | str, disparo_id: UUID | str) -> None:
    d = obter(db, org_id, disparo_id)
    if d["status"] not in ("rascunho", "cancelado"):
        raise AppException("disparo_nao_apagavel", "Só rascunhos e disparos cancelados podem ser apagados.", status_code=409)
    db.table(T_ALVOS).delete().eq("org_id", str(org_id)).eq("disparo_id", d["id"]).execute()
    db.table(T_DISPAROS).delete().eq("org_id", str(org_id)).eq("id", d["id"]).execute()


def _modelo_aprovado(db: Any, org_id: UUID | str, d: dict[str, Any]) -> dict[str, Any]:
    modelo = lais_modelos_service.obter(db, org_id, d["modelo_id"])
    if modelo["status"] != "aprovado":
        raise AppException("modelo_nao_aprovado", "O modelo ainda não foi aprovado pela Meta.", status_code=409)
    return modelo


def agendar(db: Any, org_id: UUID | str, disparo_id: UUID | str, quando: datetime, *, agora: Optional[datetime] = None) -> dict[str, Any]:
    """Schedule (allowed on any transport: nothing is sent now). Needs an approved modelo and a future
    instant, and snapshots + cap-checks the targets so a too-big segment is refused up front."""
    agora = _agora(agora)
    d = obter(db, org_id, disparo_id)
    if d["status"] not in MUTAVEIS:
        raise AppException("disparo_nao_agendavel", "Só rascunhos e agendados podem ser (re)agendados.", status_code=409)
    if quando.tzinfo is None:
        raise AppException("data_invalida", "Informe a data com fuso horário.", status_code=422)
    if quando <= agora:
        raise AppException("data_invalida", "O agendamento deve ser no futuro.", status_code=422)
    _modelo_aprovado(db, org_id, d)
    _materializar(db, org_id, d, agora)
    db.table(T_DISPAROS).update({"status": "agendado", "agendado_para": quando.isoformat(), "updated_at": agora.isoformat()}).eq(
        "org_id", str(org_id)).eq("id", d["id"]).execute()
    return obter(db, org_id, disparo_id)


def cancelar(db: Any, org_id: UUID | str, disparo_id: UUID | str) -> dict[str, Any]:
    d = obter(db, org_id, disparo_id)
    if d["status"] not in MUTAVEIS:
        raise AppException("disparo_nao_cancelavel", "Só rascunhos e agendados podem ser cancelados.", status_code=409)
    db.table(T_DISPAROS).update({"status": "cancelado", "updated_at": _agora().isoformat()}).eq("org_id", str(org_id)).eq("id", d["id"]).execute()
    return obter(db, org_id, disparo_id)


def alvos(db: Any, org_id: UUID | str, disparo_id: UUID | str) -> list[dict[str, Any]]:
    obter(db, org_id, disparo_id)
    rows = db.table(T_ALVOS).select("*").eq("org_id", str(org_id)).eq("disparo_id", str(disparo_id)).limit(1000).execute().data or []
    return sorted(rows, key=lambda r: str(r.get("created_at") or ""))


# ── dispatch (Cloud only) ───────────────────────────────────────────────────
def exigir_cloud(connection: Any) -> None:
    """THE gate: 409 `transporte_indisponivel` unless the connection is a configured Cloud one."""
    if not lais_transporte.cloud_configurada(connection):
        raise lais_transporte.transporte_indisponivel()


def valores_do_alvo(alvo: dict[str, Any], nome: Optional[str], contexto: dict[str, str]) -> dict[str, str]:
    return {
        "nome_pessoa": (nome or "").strip() or "tudo bem",
        "nome_lais": contexto.get("nome_lais") or "",
        "nome_imobiliaria": contexto.get("nome_imobiliaria") or "",
        "codigo_imovel": alvo.get("imovel_codigo") or "",
    }


def _id_da_mensagem(resp: Any) -> Optional[str]:
    try:
        return str((resp.get("messages") or [{}])[0].get("id") or "") or None
    except AttributeError:
        return None


async def disparar(
    db: Any, org_id: UUID | str, disparo_id: UUID | str, *, connection: Any, transporte: Transporte,
    contexto: Optional[dict[str, str]] = None, agora: Optional[datetime] = None,
) -> dict[str, Any]:
    """Send every pending target as the modelo's Cloud template. 409 order: transport -> status -> modelo ->
    cap. Returns the refreshed disparo with `alvos_por_status`."""
    exigir_cloud(connection)
    agora = _agora(agora)
    d = obter(db, org_id, disparo_id)
    if d["status"] not in MUTAVEIS:
        raise AppException("disparo_nao_disparavel", "Este disparo já foi enviado ou cancelado.", status_code=409)
    modelo = _modelo_aprovado(db, org_id, d)
    pendentes = [a for a in _materializar(db, org_id, d, agora) if a["status"] == "pendente"]
    _checar_limite(db, org_id, len(pendentes), agora)
    contexto = contexto or {}
    db.table(T_DISPAROS).update({"status": "enviando", "disparado_at": agora.isoformat(), "updated_at": agora.isoformat()}).eq(
        "org_id", str(org_id)).eq("id", d["id"]).execute()
    chaves = lais_modelos_service.corpo_posicional(modelo["corpo"])[1]
    enviados = 0
    for alvo in pendentes:
        patch = await _enviar_um(db, org_id, d, modelo, chaves, alvo, transporte, contexto, agora)
        enviados += 1 if patch["status"] == "enviado" else 0
        db.table(T_ALVOS).update(patch).eq("org_id", str(org_id)).eq("id", alvo["id"]).execute()
    final = "enviado" if enviados or not pendentes else "erro"
    db.table(T_DISPAROS).update({"status": final, "updated_at": _agora().isoformat()}).eq("org_id", str(org_id)).eq("id", d["id"]).execute()
    return detalhe(db, org_id, disparo_id)


async def _enviar_um(
    db: Any, org_id: UUID | str, disparo: dict[str, Any], modelo: dict[str, Any], chaves: list[str],
    alvo: dict[str, Any], transporte: Transporte, contexto: dict[str, str], agora: datetime,
) -> dict[str, Any]:
    nome: Optional[str] = None
    if alvo.get("proprietario_id"):
        dono = db.table(T_PROPRIETARIOS).select("*").eq("org_id", str(org_id)).eq("id", str(alvo["proprietario_id"])).limit(1).execute().data or []
        if not dono or dono[0].get("opt_out"):
            return {"status": "erro", "erro": "opt_out"}
        nome, imovel = dono[0].get("nome"), dono[0].get("imovel_codigo")
        alvo = {**alvo, "imovel_codigo": imovel}
    elif alvo.get("contato_id"):
        c = db.table(T_CONTATOS).select("nome").eq("org_id", str(org_id)).eq("id", str(alvo["contato_id"])).limit(1).execute().data or []
        nome = c[0].get("nome") if c else None
    if _enviados_na_janela(db, org_id, alvo["telefone"], agora) >= MAX_TEMPLATES_POR_CONTATO:
        return {"status": "erro", "erro": "limite_por_contato"}
    valores = valores_do_alvo(alvo, nome, contexto)
    try:
        resp = await transporte.enviar_template(
            alvo["telefone"], lais_modelos_service.nome_meta(modelo), [valores.get(c) or "-" for c in chaves],
            modelo.get("idioma") or lais_transporte.IDIOMA_PADRAO,
        )
    except lais_transporte.OperacaoRequerApiOficial as exc:
        raise lais_transporte.transporte_indisponivel() from exc
    except Exception as exc:  # one failing target must not stop the fan-out
        logger.error("lais disparo %s: envio falhou (%s)", disparo["id"], type(exc).__name__)
        return {"status": "erro", "erro": type(exc).__name__}
    return {"status": "enviado", "enviado_at": agora.isoformat(), "message_id": _id_da_mensagem(resp), "erro": None}


async def solicitar_proprietario(
    db: Any, org_id: UUID | str, proprietario: dict[str, Any], *, connection: Any, transporte: Transporte,
    modelo_id: Optional[UUID | str] = None, contexto: Optional[dict[str, str]] = None, agora: Optional[datetime] = None,
) -> dict[str, Any]:
    """Ask ONE owner to confirm status/price now: a single-target `atualizacao_anuncios` disparo (audit trail
    included), sent as an approved Cloud template. Gate order: transport -> opt-out -> modelo."""
    exigir_cloud(connection)
    agora = _agora(agora)
    if proprietario.get("opt_out"):
        raise AppException("proprietario_opt_out", "O proprietário pediu para não ser contatado.", status_code=409)
    if modelo_id is None:
        aprovados = [m for m in db.table("lais_modelos").select("*").eq("org_id", str(org_id)).eq("status", "aprovado").eq(
            "categoria", "administrativo").limit(100).execute().data or []]
        if not aprovados:
            raise AppException("modelo_nao_aprovado", "Nenhum modelo aprovado para solicitar a atualização.", status_code=409)
        modelo_id = max(aprovados, key=lambda m: str(m.get("created_at") or ""))["id"]
    modelo = _modelo_aprovado(db, org_id, {"modelo_id": str(modelo_id)})
    d = criar(db, org_id, nome=f"Solicitação {proprietario['imovel_codigo']}", tipo="atualizacao_anuncios",
              segmento="proprietarios", modelo_id=modelo["id"])
    alvo = {"id": str(uuid4()), "org_id": str(org_id), "disparo_id": d["id"], "contato_id": None,
            "proprietario_id": proprietario["id"], "telefone": proprietario["telefone"], "status": "pendente"}
    db.table(T_ALVOS).insert(alvo).execute()
    chaves = lais_modelos_service.corpo_posicional(modelo["corpo"])[1]
    patch = await _enviar_um(db, org_id, d, modelo, chaves, alvo, transporte, contexto or {}, agora)
    db.table(T_ALVOS).update(patch).eq("org_id", str(org_id)).eq("id", alvo["id"]).execute()
    db.table(T_DISPAROS).update({
        "status": "enviado" if patch["status"] == "enviado" else "erro", "total_alvos": 1, "disparado_at": agora.isoformat(),
        "updated_at": agora.isoformat(),
    }).eq("org_id", str(org_id)).eq("id", d["id"]).execute()
    if patch["status"] != "enviado":
        raise AppException("envio_falhou", "Não foi possível enviar a solicitação.", status_code=409, details={"motivo": patch.get("erro")})
    return {"disparo_id": d["id"], "status": "enviado"}


def registrar_resposta(db: Any, org_id: UUID | str, telefone: str) -> bool:
    """An inbound arrived from `telefone`: its most recent `enviado` target becomes `respondido`. The message
    itself keeps flowing through Julia's ordinary lead path (the re-entry is the absence of any special case)."""
    rows = db.table(T_ALVOS).select("*").eq("org_id", str(org_id)).eq("telefone", telefone).eq("status", "enviado").limit(100).execute().data or []
    if not rows:
        return False
    ultimo = max(rows, key=lambda r: str(r.get("enviado_at") or ""))
    db.table(T_ALVOS).update({"status": "respondido", "respondido_at": _agora().isoformat()}).eq("org_id", str(org_id)).eq("id", ultimo["id"]).execute()
    return True


# ── Meta lead-form first contact ────────────────────────────────────────────
ABORDAGENS = {"comercial": "abordagem comercial", "neutra": "abordagem neutra"}


async def primeiro_contato_meta(
    db: Any, org_id: UUID | str, *, connection: Any, transporte: Optional[Transporte], telefone: str,
    nome: Optional[str], abordagem: str, contexto: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Meta lead-form lead -> Julia's first contact as the approved "Abordagem comercial|neutra" template
    (category `primeiro_contato`). Cloud only: without it the hook returns `transporte_indisponivel` and the
    lead keeps flowing through the ordinary (WAHA) path -- it never degrades into a free-text mass send."""
    if abordagem not in ABORDAGENS:
        raise AppException("abordagem_invalida", "abordagem deve ser comercial ou neutra.", status_code=422)
    if not lais_transporte.cloud_configurada(connection) or transporte is None:
        return {"enviado": False, "motivo": "transporte_indisponivel"}
    modelos = db.table("lais_modelos").select("*").eq("org_id", str(org_id)).eq("categoria", "primeiro_contato").eq(
        "status", "aprovado").limit(100).execute().data or []
    modelo = next((m for m in modelos if str(m["nome"]).strip().lower() == ABORDAGENS[abordagem]), None)
    if modelo is None:
        return {"enviado": False, "motivo": "modelo_nao_aprovado"}
    tel = "".join(ch for ch in telefone if ch.isdigit())
    chaves = lais_modelos_service.corpo_posicional(modelo["corpo"])[1]
    valores = valores_do_alvo({"imovel_codigo": None}, nome, contexto or {})
    resp = await transporte.enviar_template(
        tel, lais_modelos_service.nome_meta(modelo), [valores.get(c) or "-" for c in chaves], modelo.get("idioma") or lais_transporte.IDIOMA_PADRAO,
    )
    return {"enviado": True, "modelo_id": modelo["id"], "message_id": _id_da_mensagem(resp)}


__all__ = [
    "ABAS", "CAP_PERCENTUAL", "MAX_TEMPLATES_POR_CONTATO", "SEGMENTOS", "agendar", "alvos", "apagar", "atualizar",
    "calcular_alvos", "cancelar", "catalogo", "criar", "detalhe", "disparar", "exigir_cloud", "limite_por_disparo",
    "listar", "obter", "previa", "primeiro_contato_meta", "registrar_resposta", "volume_mensal",
]
