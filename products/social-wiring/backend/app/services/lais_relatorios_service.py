"""Lais > Relatorios (wave 10, contract section 12): tipo / imovel / bairro demand vs. the shelf.

Pure read-side aggregation over what Julia already stored -- nothing is written here.

  * a LEAD is a contato with at least one interacao STARTED in the month (America/Sao_Paulo
    boundaries, [first day 00:00, next month 00:00)) whose operacao (interacao, else contato) matches;
    a contato counts ONCE per report no matter how many interacoes it had;
  * lead slots = contato.slots overlaid by the slots of its interacoes in the month (catalogue keys
    `bairro_desejado`, `tipo_imovel`, `tipo_imovel_compra`, `tipo_imovel_apartamento_casa`,
    `faixa_preco`, `quartos` -- migration 269; values are free text so they are parsed leniently);
  * a property CODE counts for a lead when Julia booked a visit for it (`lais_visitas.codigo_imovel`)
    or an applied action carried it (`lais_acoes_aplicadas.payload.codigo|codigo_imovel`) in the
    month, or the agent looked it up through a read tool (`buscar_imoveis` / `detalhes_imovel`) during one
    of the lead's turns (`lais_eventos` tipo `imovel_consultado`, written by the ferramentas route with the
    contato resolved from the turn's `interacao_id`; a lookup with no known contato is stored but is not a
    lead, so it is not counted). Counted per DISTINCT (contato, codigo): the same lead asking twice, or
    two code spellings (`ap0123` / `AP0123`), is one lead -- the Lais UI shows duplicate rows, we do not;
  * the shelf = `imoveis` of the org published on the site with the operacao in `finalidades`;
  * visibility (A7): members only aggregate the contatos they own, admins/owners the whole org.
    The shelf is org inventory and carries no contato data, so it is shown to everyone.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from noctusai_lib.integrations.persistence import iter_paged_rows
from noctusai_lib.primitives.accents import fold_accents_ascii
from noctusai_lib.primitives.exceptions import AppException

from app.services import lais_acesso

TZ = ZoneInfo("America/Sao_Paulo")
OPERACOES = ("compra", "aluguel")
ABAS = ("imoveis", "bairros")
TOP = 10
_MES_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_IN_LOTE = 200
_FINALIDADE = {"compra": "venda", "aluguel": "aluguel"}


# -- params -----------------------------------------------------------------------------------------
def mes_atual(agora: Optional[datetime] = None) -> str:
    d = (agora or datetime.now(timezone.utc)).astimezone(TZ)
    return f"{d.year:04d}-{d.month:02d}"


def limites_mes(mes: str) -> tuple[datetime, datetime]:
    """`[start, end)` of the month as UTC instants, the boundaries being midnight in Sao Paulo."""
    m = _MES_RE.match(mes or "")
    if not m:
        raise AppException("mes_invalido", "Use mes=YYYY-MM.", status_code=422)
    ano, mm = int(m.group(1)), int(m.group(2))
    ini = datetime(ano, mm, 1, tzinfo=TZ)
    fim = datetime(ano + (mm == 12), 1 if mm == 12 else mm + 1, 1, tzinfo=TZ)
    return ini.astimezone(timezone.utc), fim.astimezone(timezone.utc)


def _instante(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        d = v
    elif isinstance(v, str) and v:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _no_mes(v: Any, ini: datetime, fim: datetime) -> bool:
    d = _instante(v)
    return d is not None and ini <= d < fim


# -- lenient parsing of free-text slots ---------------------------------------------------------------
def _norm(s: Any) -> str:
    t = fold_accents_ascii(str(s or "")).lower()
    return re.sub(r"\s+", " ", t).strip()


def _singular(s: str) -> str:
    return s[:-1] if len(s) > 4 and s.endswith("s") and not s.endswith("ss") else s


def chave_tipo(s: Any) -> str:
    return _singular(_norm(s))


def parse_preco(s: Any) -> Optional[float]:
    """`500 mil` -> 500000 · `R$ 1,2 milhao` -> 1200000 · `2.500` -> 2500 · `ate 4k` -> 4000 · junk -> None."""
    t = _norm(s)
    m = re.search(r"(\d[\d.,]*)\s*(milhoes|milhao|mil|mi|k)?", t)
    if not m:
        return None
    n, suf = m.group(1), m.group(2)
    if "," in n and "." in n:
        n = n.replace(".", "").replace(",", ".")
    elif "," in n:
        n = n.replace(",", ".") if len(n.split(",")[-1]) != 3 else n.replace(",", "")
    elif "." in n:
        n = n.replace(".", "") if len(n.split(".")[-1]) == 3 else n
    try:
        v = float(n)
    except ValueError:
        return None
    if suf in ("milhoes", "milhao", "mi"):
        v *= 1_000_000
    elif suf in ("mil", "k"):
        v *= 1_000
    return v if v > 0 else None


def parse_quartos(s: Any) -> Optional[int]:
    m = re.search(r"\d+", str(s or ""))
    if m:
        n = int(m.group(0))
        return n if 0 <= n <= 20 else None
    return None


def _bairros_do_slot(s: Any) -> list[tuple[str, str]]:
    """`Pinheiros, Vila Madalena e Itaim` -> [(chave, rotulo)...] (deduplicated, order kept)."""
    out: dict[str, str] = {}
    for parte in re.split(r"[,;/]|\s+e\s+", str(s or "")):
        rotulo = parte.strip()
        k = _norm(rotulo)
        if k and k not in out:
            out[k] = rotulo[:120]
    return list(out.items())


def _tipo_do_slot(slots: dict[str, Any], operacao: str) -> Optional[str]:
    ordem = ("tipo_imovel", "tipo_imovel_compra", "tipo_imovel_apartamento_casa") if operacao == "compra" \
        else ("tipo_imovel", "tipo_imovel_apartamento_casa")
    for k in ordem:
        if _norm(slots.get(k)):
            return str(slots[k]).strip()
    return None


# -- data access (paged: PostgREST caps an unbounded select at 1000 rows) ------------------------------
def _todos(client: Any, tabela: str, org_id: UUID, colunas: str, *, id_key: str = "id") -> list[dict[str, Any]]:
    def pagina(a: int, b: int) -> Any:
        return client.table(tabela).select(colunas).eq("org_id", str(org_id)).order(id_key).range(a, b).execute().data
    return list(iter_paged_rows(pagina, id_key=id_key, label=tabela))


def _lotes(valores: Iterable[Any]) -> Iterable[list[str]]:
    v = sorted({str(x) for x in valores if x})
    for i in range(0, len(v), _IN_LOTE):
        yield v[i:i + _IN_LOTE]


def _leads(client: Any, ctx: lais_acesso.AcessoCtx, operacao: str, ini: datetime, fim: datetime) -> dict[str, dict[str, Any]]:
    """`{contato_id: {slots, ...}}` for the visible leads of the month and operacao."""
    inter = [i for i in _todos(client, "lais_interacoes", ctx.org_id, "id, contato_id, iniciada_at, operacao, slots")
             if _no_mes(i.get("iniciada_at"), ini, fim)]
    ids = {str(i["contato_id"]) for i in inter}
    contatos: list[dict[str, Any]] = []
    for lote in _lotes(ids):
        contatos += client.table(lais_acesso.T_CONTATOS).select("*").eq("org_id", str(ctx.org_id)).in_("id", lote).execute().data or []
    visiveis = {str(c["id"]): c for c in lais_acesso.filtrar_contatos(client, ctx, contatos)}
    out: dict[str, dict[str, Any]] = {}
    for i in sorted(inter, key=lambda r: str(r.get("iniciada_at"))):
        c = visiveis.get(str(i["contato_id"]))
        if c is None or (i.get("operacao") or c.get("operacao")) != operacao:
            continue
        lead = out.setdefault(str(c["id"]), {"slots": dict(c.get("slots") or {})})
        lead["slots"].update(i.get("slots") or {})
    return out


def _mencoes(client: Any, org_id: UUID, leads: dict[str, dict[str, Any]], ini: datetime, fim: datetime) -> dict[str, set[str]]:
    """`{codigo_norm: {contato_id}}` -- distinct leads per code (visits + applied actions + tool lookups)."""
    out: dict[str, set[str]] = {}

    def somar(contato_id: Any, codigo: Any) -> None:
        cid, cod = str(contato_id), str(codigo or "").strip().upper()
        if cod and cid in leads:
            out.setdefault(cod[:40], set()).add(cid)

    for v in _todos(client, "lais_visitas", org_id, "id, contato_id, codigo_imovel, created_at"):
        if _no_mes(v.get("created_at"), ini, fim):
            somar(v.get("contato_id"), v.get("codigo_imovel"))
    for a in _todos(client, "lais_acoes_aplicadas", org_id, "id, contato_id, payload, created_at"):
        if _no_mes(a.get("created_at"), ini, fim):
            p = a.get("payload") or {}
            somar(a.get("contato_id"), p.get("codigo") or p.get("codigo_imovel"))
    def pagina(a: int, b: int) -> Any:
        return (client.table("lais_eventos").select("id, contato_id, payload, created_at").eq("org_id", str(org_id))
                .eq("tipo", "imovel_consultado").order("id").range(a, b).execute().data)

    for e in iter_paged_rows(pagina, id_key="id", label="lais_eventos"):
        if _no_mes(e.get("created_at"), ini, fim):
            for cod in (e.get("payload") or {}).get("codigos") or []:
                somar(e.get("contato_id"), cod)
    return out


def _imoveis_por_codigo(client: Any, org_id: UUID, codigos: Iterable[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for lote in _lotes(codigos):
        for r in client.table("imoveis").select("codigo, codigo_norm, categoria, valor_venda, valor_locacao, exibir_no_site") \
                .eq("org_id", str(org_id)).in_("codigo_norm", lote).execute().data or []:
            out[str(r.get("codigo_norm") or r["codigo"]).upper()] = r
    return out


def _prateleira(client: Any, org_id: UUID, operacao: str) -> list[dict[str, Any]]:
    alvo = _FINALIDADE[operacao]
    rows = _todos(client, "imoveis", org_id, "codigo, categoria, finalidades, exibir_no_site", id_key="codigo")
    return [r for r in rows if r.get("exibir_no_site") is not False and alvo in (r.get("finalidades") or [])]


def _pct(n: int, total: int) -> float:
    return round(100.0 * n / total, 1) if total else 0.0


def _top_imoveis(mencoes: dict[str, set[str]], cadastro: dict[str, dict[str, Any]], operacao: str,
                 so_leads: Optional[set[str]] = None) -> list[dict[str, Any]]:
    campo = "valor_venda" if operacao == "compra" else "valor_locacao"
    linhas = []
    for cod, cids in mencoes.items():
        n = len(cids & so_leads) if so_leads is not None else len(cids)
        if n:
            im = cadastro.get(cod) or {}
            preco = im.get(campo)
            linhas.append({"codigo": cod, "tipo": im.get("categoria"), "preco": float(preco) if preco is not None else None, "leads": n})
    linhas.sort(key=lambda r: (-r["leads"], r["codigo"]))
    return linhas[:TOP]


# -- the report ------------------------------------------------------------------------------------------
def relatorio(
    client: Any, ctx: lais_acesso.AcessoCtx, *, operacao: str, mes: str, aba: str, bairro: Optional[str] = None,
) -> dict[str, Any]:
    if operacao not in OPERACOES:
        raise AppException("operacao_invalida", "Use operacao=compra ou operacao=aluguel.", status_code=422)
    if aba not in ABAS:
        raise AppException("aba_invalida", "Use aba=imoveis ou aba=bairros.", status_code=422)
    ini, fim = limites_mes(mes)
    leads = _leads(client, ctx, operacao, ini, fim)
    mencoes = _mencoes(client, ctx.org_id, leads, ini, fim)
    base = {"operacao": operacao, "mes": mes, "aba": aba, "total_leads": len(leads)}
    if aba == "imoveis":
        return {**base, **_aba_imoveis(client, ctx, operacao, leads, mencoes)}
    return {**base, **_aba_bairros(client, ctx, operacao, leads, mencoes, bairro)}


def _aba_imoveis(client: Any, ctx: lais_acesso.AcessoCtx, operacao: str, leads: dict, mencoes: dict) -> dict[str, Any]:
    pedidos = Counter()
    rotulos: dict[str, str] = {}
    for lead in leads.values():
        t = _tipo_do_slot(lead["slots"], operacao)
        if t:
            k = chave_tipo(t)
            pedidos[k] += 1
            rotulos.setdefault(k, t.strip().capitalize())
    estoque = Counter()
    for r in _prateleira(client, ctx.org_id, operacao):
        cat = (r.get("categoria") or "").strip()
        if cat:
            k = chave_tipo(cat)
            estoque[k] += 1
            rotulos[k] = cat  # the shelf spelling wins
    tot_l, tot_p = sum(pedidos.values()), sum(estoque.values())
    tipos = [{"tipo": rotulos[k], "pct_leads": _pct(pedidos[k], tot_l), "pct_prateleira": _pct(estoque[k], tot_p)}
             for k in set(pedidos) | set(estoque)]
    tipos.sort(key=lambda r: (-r["pct_leads"], -r["pct_prateleira"], r["tipo"]))
    cadastro = _imoveis_por_codigo(client, ctx.org_id, mencoes)
    return {"tipos": tipos[:TOP], "top_imoveis": _top_imoveis(mencoes, cadastro, operacao)}


def _aba_bairros(client: Any, ctx: lais_acesso.AcessoCtx, operacao: str, leads: dict, mencoes: dict,
                 bairro: Optional[str]) -> dict[str, Any]:
    por_bairro: dict[str, set[str]] = {}
    variantes: dict[str, dict[str, int]] = {}
    for cid, lead in leads.items():
        for k, rot in _bairros_do_slot(lead["slots"].get("bairro_desejado")):
            por_bairro.setdefault(k, set()).add(cid)
            variantes.setdefault(k, {}).setdefault(rot, 0)
            variantes[k][rot] += 1
    # the display label is the most-typed spelling (tie -> alphabetical): the leads arrive in id order, so
    # "first seen" would make the label depend on a random uuid
    rotulos = {k: min(v, key=lambda r: (-v[r], r)) for k, v in variantes.items()}
    ranking = sorted(por_bairro, key=lambda k: (-len(por_bairro[k]), k))
    top = [{"bairro": rotulos[k], "leads": len(por_bairro[k])} for k in ranking[:TOP]]
    disponiveis = sorted((rotulos[k] for k in ranking), key=_norm)
    escolhido = _norm(bairro) if bairro else (ranking[0] if ranking else "")
    desempenho = None
    if escolhido in por_bairro:
        cids = por_bairro[escolhido]
        precos = [p for c in cids if (p := parse_preco(leads[c]["slots"].get("faixa_preco"))) is not None]
        tipos = Counter(chave_tipo(t) for c in cids if (t := _tipo_do_slot(leads[c]["slots"], operacao)))
        nomes = {chave_tipo(t): t.strip().capitalize() for c in cids if (t := _tipo_do_slot(leads[c]["slots"], operacao))}
        qts = Counter(q for c in cids if (q := parse_quartos(leads[c]["slots"].get("quartos"))) is not None)
        cadastro = _imoveis_por_codigo(client, ctx.org_id, mencoes)
        desempenho = {
            "bairro": rotulos[escolhido],
            "mediana_preco": round(statistics.median(precos), 2) if precos else None,
            "pct_por_tipo": sorted(({"tipo": nomes[k], "pct": _pct(n, sum(tipos.values()))} for k, n in tipos.items()),
                                   key=lambda r: (-r["pct"], r["tipo"])),
            "melhor_quartos": sorted(qts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if qts else None,
            "mais_buscados": _top_imoveis(mencoes, cadastro, operacao, so_leads=cids),
        }
    return {"top_bairros": top, "bairros_disponiveis": disponiveis, "desempenho": desempenho}
