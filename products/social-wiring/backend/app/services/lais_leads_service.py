"""Lais > Leads (wave 3, contract 5): the table of `lais_contatos` with the live "Filtro de leads" filters
(page-map-v2 59.0 a8), the per-contato resumo and the admin CSV export.

For an owner/admin the filters are pushed to the DB (one `count="exact"` + one `.range()` page) except `imovel`
(its code lives inside the `slots` jsonb). A member's visibility (A7: responsavel, else the connection owner) is
a rule over two tables, so a member's list walks the filtered matches with `iter_paged_rows`, keeps what
`lais_acesso.filtrar_contatos` allows and paginates in memory -- the SAME shared rule every Lais route uses.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterator, Optional
from uuid import UUID

from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_acesso, lais_slots_sensiveis as sensiveis
from app.services import lais_contatos_service as contatos
from app.services.lais_envio_service import FUSO, GATILHO_LABEL, STATUS_ENVIADOS, T_ENTREGAS

PAGE_SIZE_MAX = 100
OPERACOES_FILTRO = ("compra", "aluguel", "administracao")
ATENDIMENTOS = ("sem_atendimento", "atendido_pela_julia")
STATUS_FILTRO = ("nao_pronto", "enviado", "erro")
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_FORMULA = ("=", "+", "-", "@", "\t", "\r")

#: The channel origins the Lais "Filtro de leads" knows (page-map 59.0 a8 + mechanisms.md: 33 portal origin codes plus
#: ads / direct / AI-assistant origins). The filter itself is open -- the stored `canal` is matched as typed -- and
#: `GET /api/lais/leads/canais` returns this catalogue UNION the channels actually present in the org.
CANAIS_CONHECIDOS: tuple[str, ...] = (
    "GrupoZapLais", "SiteProprioLais", "NetImoveisLais", "FacebookAdsLais", "ChavesNaMaoLais", "ImovelWebLais",
    "RemarketingLais", "CasaMineiraLais", "WhatsAppLais", "RocketImobLais", "KenloLais", "PlacaLais", "DFImoveisLais",
    "SUB100Lais", "InstagramAdsLais", "GoogleAdsLais", "WImoveisLais", "ImoblistLais", "CliqueiMudeiLais",
    "Lead4SalesLais", "123iLais", "MappoLais", "GuiaDeImoveisLais", "HubWLais", "CasaJauLais", "RedeInovaLais",
    "SPImovelLais", "ZNImovelLais", "ZLImovelLais", "ZSImovelLais", "ZOImovelLais", "ABCImovelLais",
    "LitoralSPImovelLais", "RDStationLais", "ConversasLais", "ChatGPTLais", "ClaudeLais", "MCPLais", "whatsapp",
)


def _label_canal(slug: str) -> str:
    base = slug[:-4] if slug.endswith("Lais") and len(slug) > 4 else slug
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", base).replace("_", " ").strip() or slug


def canais(client: Any, org_id: UUID | str) -> list[dict[str, str]]:
    """`[{slug, label}]`: the org's SW lead sources, the Lais origin catalogue and every `canal` already stored on a contato."""
    org = str(org_id)
    out: dict[str, str] = {s: _label_canal(s) for s in CANAIS_CONHECIDOS}
    for r in iter_paged_rows(
        lambda a, b: client.table("lead_sources").select("id,slug,label").eq("org_id", org).order("id").range(a, b).execute().data,
        label="lais canais lead_sources",
    ):
        if r.get("slug"):
            out[r["slug"]] = r.get("label") or out.get(r["slug"]) or r["slug"]
    for r in iter_paged_rows(
        lambda a, b: client.table(contatos.T_CONTATOS).select("id,canal").eq("org_id", org).order("id").range(a, b).execute().data,
        label="lais canais",
    ):
        if r.get("canal") and r["canal"] not in out:
            out[r["canal"]] = _label_canal(r["canal"])
    return [{"slug": k, "label": v} for k, v in sorted(out.items(), key=lambda kv: kv[1].lower())]


def _like(texto: str) -> str:
    return f"%{texto.replace('%', '').strip()}%"


def _dia_ini(d: date) -> str:
    return datetime.combine(d, time.min, tzinfo=FUSO).astimezone(timezone.utc).isoformat()


def _dia_fim(d: date) -> str:
    return (datetime.combine(d + timedelta(days=1), time.min, tzinfo=FUSO)).astimezone(timezone.utc).isoformat()


def validar_filtros(f: dict[str, Any]) -> dict[str, Any]:
    """Drop blanks; typed 422 on an out-of-vocabulary value (`filtro_invalido`)."""
    out = {k: v for k, v in f.items() if v not in (None, "")}
    for chave, validos in (("operacao", OPERACOES_FILTRO), ("atendimento", ATENDIMENTOS), ("status", STATUS_FILTRO)):
        if chave in out:
            out[chave] = [out[chave]] if isinstance(out[chave], str) else list(out[chave])
            if any(v not in validos for v in out[chave]):
                raise AppException("filtro_invalido", f"Valor inválido para {chave}.", status_code=422,
                                   details={"filtro": chave, "opcoes": list(validos)})
    if "canal" in out:
        out["canal"] = [out["canal"]] if isinstance(out["canal"], str) else list(out["canal"])
    de, ate = out.get("de"), out.get("ate")
    if de and ate and de > ate:
        raise AppException("filtro_invalido", "O período está invertido.", status_code=422, details={"filtro": "primeiro_contato"})
    return out


def _aplicar(q: Any, f: dict[str, Any], org_id: UUID | str) -> Any:
    q = q.eq("org_id", str(org_id))
    if f.get("nome"):
        q = q.ilike("nome", _like(f["nome"]))
    if f.get("email"):
        q = q.ilike("email", _like(f["email"]))
    if f.get("telefone"):
        digitos = re.sub(r"\D", "", f["telefone"])
        if digitos:
            q = q.ilike("telefone_e164", f"%{digitos}%")
    if f.get("link"):
        token = f["link"].strip().rstrip("/").rsplit("/", 1)[-1].split("?")[0]
        achado = _UUID_RE.search(f["link"])
        q = q.eq("id", achado.group(0).lower()) if achado else q.ilike("chat_id", _like(token))
    if f.get("operacao"):
        q = q.in_("operacao", f["operacao"])
    if len(set(f.get("atendimento") or [])) == 1:  # both options = no filter
        if f["atendimento"][0] == "atendido_pela_julia":
            q = q.not_.is_("ultimo_outbound_at", "null")
        else:
            q = q.is_("ultimo_outbound_at", "null")
    if f.get("status"):
        db = [e for st in f["status"] for e in (STATUS_ENVIADOS if st == "enviado" else (st,))]
        q = q.in_("status_envio", db)
    if f.get("canal"):
        q = q.in_("canal", f["canal"])
    if f.get("campanha"):
        q = q.ilike("campanha_origem", _like(f["campanha"]))
    if f.get("anuncio"):
        q = q.ilike("anuncio_origem", _like(f["anuncio"]))
    if f.get("de"):
        q = q.gte("created_at", _dia_ini(f["de"]))
    if f.get("ate"):
        q = q.lt("created_at", _dia_fim(f["ate"]))
    if f.get("ids"):
        q = q.in_("id", [str(i) for i in f["ids"]])
    return q


def _por_imovel(rows: list[dict[str, Any]], imovel: str) -> list[dict[str, Any]]:
    alvo = imovel.strip().lower()
    return [r for r in rows if alvo in str((r.get("slots") or {}).get("codigo_imovel") or "").lower()]


def _varrer(client: Any, org_id: UUID | str, f: dict[str, Any]) -> Iterator[dict[str, Any]]:
    def pagina(a: int, b: int) -> Any:
        q = _aplicar(client.table(contatos.T_CONTATOS).select("*"), f, org_id)
        return q.order("created_at", desc=True).order("id").range(a, b).execute().data

    return iter_paged_rows(pagina, label="lais leads")


def _entregas_de(client: Any, org_id: UUID | str, ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for i in range(0, len(ids), PAGE_SIZE_MAX):
        lote = ids[i:i + PAGE_SIZE_MAX]
        rows = client.table(T_ENTREGAS).select("*").eq("org_id", str(org_id)).in_("contato_id", lote).order("created_at", desc=True).execute().data or []
        for r in rows:
            out.setdefault(str(r["contato_id"]), []).append(r)
    return out


def status_ui(status_envio: str) -> str:
    return "enviado" if status_envio in STATUS_ENVIADOS else (status_envio if status_envio in ("nao_pronto", "erro") else "nao_pronto")


def enviado_por(entregas: list[dict[str, Any]]) -> Optional[str]:
    ok = next((e for e in entregas if e.get("status") == "ok"), None)
    if ok is None:
        return None
    return {"qualificado": "julia", "manual": "manual"}.get(ok["gatilho"], "automatico")


def _item(c: dict[str, Any], entregas: list[dict[str, Any]]) -> dict[str, Any]:
    slots = c.get("slots") or {}
    ultima = entregas[0] if entregas else None
    return {
        "id": str(c["id"]), "connection_id": str(c["connection_id"]), "chat_id": c["chat_id"],
        "nome": c.get("nome"), "telefone": c.get("telefone_e164"), "email": c.get("email"),
        "operacao": c.get("operacao"), "codigo_imovel": slots.get("codigo_imovel"),
        "canal": c.get("canal"), "campanha_origem": c.get("campanha_origem"), "anuncio_origem": c.get("anuncio_origem"),
        "primeiro_contato_at": c.get("created_at"), "ultimo_inbound_at": c.get("ultimo_inbound_at"),
        "atendido_pela_julia": bool(c.get("ultimo_outbound_at")),
        "status_envio": c.get("status_envio"), "status": status_ui(str(c.get("status_envio"))),
        "enviado_por": enviado_por(entregas),
        "gatilho": next((e["gatilho"] for e in entregas if e.get("status") == "ok"), None),
        "lead_id": str(c["lead_id"]) if c.get("lead_id") else None,
        "erro": (ultima.get("erro") if ultima and c.get("status_envio") == "erro" else None),
        "responsavel_user_id": str(c["responsavel_user_id"]) if c.get("responsavel_user_id") else None,
    }


def listar(client: Any, org_id: UUID | str, filtros: dict[str, Any], *, ctx: lais_acesso.AcessoCtx,
           page: int = 1, page_size: int = 25) -> dict[str, Any]:
    f = validar_filtros(filtros)
    page_size = max(1, min(int(page_size), PAGE_SIZE_MAX))
    page = max(1, int(page))
    ini = (page - 1) * page_size
    if f.get("imovel") or not ctx.admin:
        todos = list(_varrer(client, org_id, f))
        if f.get("imovel"):
            todos = _por_imovel(todos, f["imovel"])
        if not ctx.admin:
            todos = lais_acesso.filtrar_contatos(client, ctx, todos)
        total, linhas = len(todos), todos[ini:ini + page_size]
    else:
        total = _aplicar(client.table(contatos.T_CONTATOS).select("id", count="exact"), f, org_id).execute().count or 0
        linhas = (
            _aplicar(client.table(contatos.T_CONTATOS).select("*"), f, org_id)
            .order("created_at", desc=True).order("id").range(ini, ini + page_size - 1).execute().data or []
        )
    entregas = _entregas_de(client, org_id, [str(r["id"]) for r in linhas])
    return {"items": [_item(r, entregas.get(str(r["id"]), [])) for r in linhas], "total": total}


def obter_contato(client: Any, ctx: lais_acesso.AcessoCtx, contato_id: UUID | str) -> dict[str, Any]:
    """The shared A7 guard: 404 for another org's / a missing contato, 403 `sem_acesso` for a same-org stranger."""
    return lais_acesso.exigir_contato(client, ctx, contato_id)


def resumo(client: Any, org_id: UUID | str, contato: dict[str, Any]) -> dict[str, Any]:
    """`GET /api/lais/leads/{id}/resumo`: who, what was collected, the episodes' summaries and the send history."""
    inter = (
        client.table(contatos.T_INTERACOES).select("*").eq("org_id", str(org_id)).eq("contato_id", str(contato["id"]))
        .order("iniciada_at", desc=True).limit(20).execute().data or []
    )
    entregas = _entregas_de(client, org_id, [str(contato["id"])]).get(str(contato["id"]), [])
    slots = {k: v for k, v in (contato.get("slots") or {}).items() if k not in sensiveis.SENSIVEIS}
    return {
        "contato": _item(contato, entregas),
        "slots": slots,
        "interacoes": [
            {k: i.get(k) for k in ("id", "iniciada_at", "encerrada_at", "operacao", "resumo", "desfecho", "intencoes")}
            for i in inter
        ],
        "entregas": [
            {"id": str(e["id"]), "gatilho": e["gatilho"], "gatilho_label": GATILHO_LABEL.get(e["gatilho"], e["gatilho"]),
             "status": e["status"], "erro": e.get("erro"), "lead_id": str(e["lead_id"]) if e.get("lead_id") else None,
             "created_at": e.get("created_at")}
            for e in entregas
        ],
    }


# ── CSV export (admin only; the router enforces it) ─────────────────────────
CSV_COLUNAS = ("nome", "telefone", "email", "operacao", "imovel", "canal", "campanha", "anuncio",
               "primeiro_contato", "atendido_pela_julia", "status", "enviado_por")


def _celula(v: Any) -> str:
    texto = "" if v is None else str(v)
    return "'" + texto if texto.startswith(_FORMULA) else texto  # spreadsheet formula injection


def exportar_csv(client: Any, org_id: UUID | str, filtros: dict[str, Any]) -> str:
    """Admin only (the router enforces it): every contato of the org matching the filters."""
    f = validar_filtros(filtros)
    linhas = list(_varrer(client, org_id, f))
    if f.get("imovel"):
        linhas = _por_imovel(linhas, f["imovel"])
    entregas = _entregas_de(client, org_id, [str(r["id"]) for r in linhas])
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(CSV_COLUNAS)
    for r in linhas:
        i = _item(r, entregas.get(str(r["id"]), []))
        w.writerow([_celula(v) for v in (
            i["nome"], i["telefone"], i["email"], i["operacao"], i["codigo_imovel"], i["canal"], i["campanha_origem"],
            i["anuncio_origem"], i["primeiro_contato_at"], "sim" if i["atendido_pela_julia"] else "não", i["status"], i["enviado_por"],
        )])
    return buf.getvalue()


__all__ = [
    "ATENDIMENTOS", "CANAIS_CONHECIDOS", "CSV_COLUNAS", "OPERACOES_FILTRO", "PAGE_SIZE_MAX", "STATUS_FILTRO", "canais",
    "enviado_por", "exportar_csv", "listar", "obter_contato", "resumo", "status_ui", "validar_filtros",
]
