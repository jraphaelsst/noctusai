"""Orçamentos — the proposal lifecycle (roadmap R4–R7, wave-2 slice A).

    compute  `normalizar_itens` + `calcular_totais` — recurrence math and every
             total are SERVER-computed; the client never tells the server what
             a proposal costs
    write    `criar` / `atualizar` / `nova_versao` / `recusar`
    accept   `aceitar` — runs EXACTLY the funnel's fechado transition
             (`comercial_funil.mover_negocio` into the `fechado`-role stage:
             orçamento aceito, siblings substituido, negócio ganho, Cliente
             created) and then generates the calendar pautas
    read     `listar` / `obter` — past `validade` flips rascunho|enviado to
             `expirado` on read

Reads/writes go through the PostgREST client (same seam as the funnel,
`app/pipelines.py` decision D-A1) so the aceite can call the funnel service on
the very same client. Every query filters `org_id` explicitly.

Rule refusals raise :class:`RegraViolada` (`{"detail", "code"}` on the wire):

  409 `orcamento_bloqueado`  edit/new-version of an aceito/recusado/substituido/expirado one
  409 `orcamento_expirado`   accept past validade
  409 `negocio_encerrado`    new orçamento on a perdido/ganho negócio
  409 `negocio_ganho`        accept when the negócio closed with ANOTHER orçamento
  422 `recorrencia_invalida` recorrente item without weekday/qty
  422 `desconto_invalido`    discount above the subtotal
  422 `produto_invalido`     item names an unknown catalogue product
  422 `motivo_obrigatorio`   recusar without a reason
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from noctusai_lib.integrations.persistence.table_reads import in_batched_rows, paged_rows

from app.pipelines import PAPEL_FECHADO, PIPELINE_COMERCIAL, etapas
from app.services import comercial_funil
from app.services import quadro_comum as qc
from app.services.regras import RegraViolada

logger = logging.getLogger(__name__)

__all__ = [
    "SECOES",
    "DIAS_SEMANA",
    "STATUS_ABERTOS",
    "ABAS",
    "quantidade_mensal",
    "frequencia_texto",
    "normalizar_itens",
    "calcular_totais",
    "carregar",
    "montar_dtos",
    "listar",
    "obter",
    "criar",
    "atualizar",
    "nova_versao",
    "recusar",
    "aceitar",
    "gerar_pautas",
    "itens_de",
    "hoje_local",
    "produtos_dos_itens",
    "horas_por_produto",
]

SECOES = ("criacao_conteudo", "gestao_conta")
#: Weekday bitmask, Monday first — `date.weekday()` indexes it directly.
DIAS_SEMANA: tuple[tuple[int, str], ...] = (
    (1, "Seg"), (2, "Ter"), (4, "Qua"), (8, "Qui"), (16, "Sex"), (32, "Sáb"), (64, "Dom"),
)
#: A month is priced as 4 weeks (contract § Shapes: popcount × qtd × 4).
SEMANAS_POR_MES = 4
#: How far ahead an accepted orçamento fills the calendar (roadmap R9).
DIAS_DE_PAUTA = 30
#: Local publishing hour of a generated pauta — a placeholder slot the
#: operator reschedules; midnight UTC would land on the previous day in Brazil.
HORA_PAUTA = time(10, 0)
FUSO = ZoneInfo("America/Sao_Paulo")

STATUS_ABERTOS = ("rascunho", "enviado")
ABAS: dict[str, tuple[str, ...]] = {
    "ativos": STATUS_ABERTOS,
    "aceitos": ("aceito",),
    "recusados": ("recusado", "expirado", "substituido"),
}
LIMITES_PADRAO = {"revisoes_incluidas": 2, "valor_excedente": 0.0}

_ORCAMENTO_SELECT = "*"
_ITEM_SELECT = (
    "id, orcamento_id, produto_servico_id, secao, descricao, preco_unitario, recorrente, "
    "dias_semana, qtd_por_dia, quantidade_mensal, subtotal, ordem"
)
_NUMERICOS = (
    "subtotal_criacao", "subtotal_gestao", "desconto", "total_mensal", "custo_estimado",
    "horas_estimadas",
)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def hoje_local() -> date:
    return datetime.now(FUSO).date()


def _num(valor: Any, padrao: float = 0.0) -> float:
    if valor is None or valor == "":
        return padrao
    return float(valor)


# ── Pure computation ─────────────────────────────────────────────────
def quantidade_mensal(*, recorrente: bool, dias_semana: int, qtd_por_dia: int, quantidade: int) -> int:
    """`popcount(dias_semana) × qtd_por_dia × 4` when recorrente, else `quantidade`."""
    if recorrente:
        return bin(int(dias_semana) & 127).count("1") * int(qtd_por_dia) * SEMANAS_POR_MES
    return int(quantidade)


def frequencia_texto(item: dict) -> str:
    """Human frequency — "Seg, Qua, Sex × 1" for recurring, "Mensal" otherwise."""
    if not item.get("recorrente"):
        return "Mensal"
    mascara = int(item.get("dias_semana") or 0)
    dias = [rotulo for bit, rotulo in DIAS_SEMANA if mascara & bit]
    return f"{', '.join(dias)} × {int(item.get('qtd_por_dia') or 0)}"


def normalizar_itens(itens: Iterable[dict]) -> list[dict]:
    """Validate recurrence and compute `quantidade_mensal` + `subtotal` per item.

    Input dicts carry the inbound fields (`quantidade` only matters when not
    recorrente). Output dicts are the `orcamento_item` columns, in order.
    """
    saida: list[dict] = []
    for indice, item in enumerate(itens):
        recorrente = bool(item.get("recorrente"))
        dias = int(item.get("dias_semana") or 0)
        qtd_dia = int(item.get("qtd_por_dia") or 0)
        if recorrente and (dias <= 0 or qtd_dia <= 0):
            raise RegraViolada(
                422, "recorrencia_invalida",
                f"O item \"{item.get('descricao')}\" é recorrente: escolha ao menos um dia "
                "da semana e a quantidade por dia.",
            )
        qm = quantidade_mensal(
            recorrente=recorrente, dias_semana=dias, qtd_por_dia=qtd_dia,
            quantidade=int(item.get("quantidade") if item.get("quantidade") is not None else 1),
        )
        preco = round(_num(item.get("preco_unitario")), 2)
        ordem = item.get("ordem")
        saida.append({
            "produto_servico_id": item.get("produto_servico_id") or None,
            "secao": item["secao"],
            "descricao": str(item["descricao"]).strip(),
            "preco_unitario": preco,
            "recorrente": recorrente,
            "dias_semana": dias if recorrente else 0,
            "qtd_por_dia": qtd_dia if recorrente else 0,
            "quantidade_mensal": qm,
            "subtotal": round(preco * qm, 2),
            "ordem": int(ordem) if ordem is not None else indice,
        })
    return saida


def calcular_totais(
    itens: list[dict],
    *,
    desconto: float,
    horas_por_produto: dict[str, float],
    custo_hora: float,
) -> dict:
    """Totais from normalized items.

    `custo_estimado` = Σ (produto.horas_estimadas × quantidade_mensal) × the
    team's average custo/hora; `margem_estimada` = (total − custo) / total as
    a % — NEGATIVE when the proposal is below cost (shown, never clamped: a
    clamped 0 would hide the one number the owner most needs to see), `None`
    when the total is zero.
    """
    sub_criacao = round(sum(i["subtotal"] for i in itens if i["secao"] == "criacao_conteudo"), 2)
    sub_gestao = round(sum(i["subtotal"] for i in itens if i["secao"] == "gestao_conta"), 2)
    bruto = round(sub_criacao + sub_gestao, 2)
    desconto = round(_num(desconto), 2)
    if desconto > bruto:
        raise RegraViolada(
            422, "desconto_invalido", "O desconto não pode ser maior que o subtotal do orçamento."
        )
    total = round(bruto - desconto, 2)
    horas = round(
        sum(horas_por_produto.get(str(i.get("produto_servico_id")), 0.0) * i["quantidade_mensal"]
            for i in itens),
        2,
    )
    custo = round(horas * custo_hora, 2)
    margem = round((total - custo) / total * 100, 2) if total > 0 else None
    return {
        "subtotal_criacao": sub_criacao,
        "subtotal_gestao": sub_gestao,
        "desconto": desconto,
        "total_mensal": total,
        "custo_estimado": custo,
        "margem_estimada": margem,
        "horas_estimadas": horas,
    }


def produtos_dos_itens(db: Any, org_id: str, itens: list[dict]) -> dict[str, dict]:
    """`id → produto` for every product the items reference; 422 on an unknown one."""
    ids = {str(i["produto_servico_id"]) for i in itens if i.get("produto_servico_id")}
    produtos = qc.por_ids(db, "produto_servico", org_id, ids,
                          select="id, horas_estimadas, formato, nome")
    faltando = ids - set(produtos)
    if faltando:
        raise RegraViolada(
            422, "produto_invalido",
            "Um dos itens referencia um produto/serviço que não existe neste catálogo.",
        )
    return produtos


def horas_por_produto(produtos: dict[str, dict]) -> dict[str, float]:
    return {pid: _num(p.get("horas_estimadas")) for pid, p in produtos.items()}


# ── Reads ────────────────────────────────────────────────────────────
def carregar(db: Any, org_id: str, orcamento_id: str) -> dict:
    return qc.carregar(db, "orcamento", org_id, orcamento_id, select=_ORCAMENTO_SELECT,
                       rotulo="orçamento")


def _vencido(orcamento: dict, hoje: date) -> bool:
    validade = orcamento.get("validade")
    return bool(validade) and str(validade)[:10] < hoje.isoformat()


def _expirar_vencidos(db: Any, org_id: str, linhas: list[dict], hoje: date) -> None:
    """Flip every open, past-validade orçamento in `linhas` to `expirado` — persisted,
    so the tabs, filters and the aceite all see the same status."""
    vencidos = [r for r in linhas if r.get("status") in STATUS_ABERTOS and _vencido(r, hoje)]
    if not vencidos:
        return
    for lote_inicio in range(0, len(vencidos), 200):
        ids = [str(r["id"]) for r in vencidos[lote_inicio:lote_inicio + 200]]
        db.table("orcamento").update({"status": "expirado"}).eq("org_id", org_id).in_(
            "id", ids
        ).in_("status", list(STATUS_ABERTOS)).execute()
    for r in vencidos:
        r["status"] = "expirado"
    logger.info("orcamentos expirados na leitura org=%s n=%d", org_id, len(vencidos))


def itens_de(db: Any, org_id: str, orcamento_ids: list[str]) -> dict[str, list[dict]]:
    por_orcamento: dict[str, list[dict]] = {oid: [] for oid in orcamento_ids}
    if not orcamento_ids:
        return por_orcamento
    for item in in_batched_rows(db, "orcamento_item", org_id, "orcamento_id",
                                sorted(set(orcamento_ids)), select=_ITEM_SELECT):
        por_orcamento.setdefault(str(item["orcamento_id"]), []).append(_item_dto(item))
    for lista in por_orcamento.values():
        lista.sort(key=lambda i: (i["ordem"], i["descricao"]))
    return por_orcamento


def _item_dto(item: dict) -> dict:
    return {
        "id": item.get("id"),
        "produto_servico_id": item.get("produto_servico_id"),
        "secao": item.get("secao"),
        "descricao": item.get("descricao"),
        "preco_unitario": _num(item.get("preco_unitario")),
        "recorrente": bool(item.get("recorrente")),
        "dias_semana": int(item.get("dias_semana") or 0),
        "qtd_por_dia": int(item.get("qtd_por_dia") or 0),
        # Echoed so the FE round-trips a non-recurring item's quantity.
        "quantidade": int(item.get("quantidade_mensal") or 0),
        "quantidade_mensal": int(item.get("quantidade_mensal") or 0),
        "subtotal": _num(item.get("subtotal")),
        "ordem": int(item.get("ordem") or 0),
    }


def montar_dtos(db: Any, org_id: str, linhas: list[dict]) -> list[dict]:
    """Rows → the contract's `Orcamento` (itens + lead + negocio embedded)."""
    ids = [str(r["id"]) for r in linhas]
    itens = itens_de(db, org_id, ids)
    leads = qc.por_ids(db, "lead", org_id, (r.get("lead_id") for r in linhas),
                       select="id, nome, email, empresa")
    negocios = qc.por_ids(db, "negocio", org_id, (r.get("negocio_id") for r in linhas),
                          select="id, titulo, etapa_id, status")
    saida = []
    for r in linhas:
        dto = {
            "id": r["id"],
            "negocio_id": r.get("negocio_id"),
            "lead_id": r.get("lead_id"),
            "cliente_id": r.get("cliente_id"),
            "versao": int(r.get("versao") or 1),
            "titulo": r.get("titulo"),
            "status": r.get("status"),
            "validade": str(r["validade"])[:10] if r.get("validade") else None,
            "itens": itens.get(str(r["id"]), []),
            "limites_escopo": {**LIMITES_PADRAO, **(r.get("limites_escopo") or {})},
            "observacoes": r.get("observacoes"),
            "pdf_key": r.get("pdf_key"),
            "enviado_em": r.get("enviado_em"),
            "respondido_em": r.get("respondido_em"),
            "aceito_em": r.get("aceito_em"),
            "recusado_em": r.get("recusado_em"),
            "motivo_recusa": r.get("motivo_recusa"),
            "created_at": r.get("created_at"),
            "margem_estimada": (
                _num(r["margem_estimada"]) if r.get("margem_estimada") is not None else None
            ),
            "lead": leads.get(str(r.get("lead_id"))),
            "negocio": negocios.get(str(r.get("negocio_id"))),
        }
        for campo in _NUMERICOS:
            dto[campo] = _num(r.get(campo))
        saida.append(dto)
    return saida


def listar(
    db: Any,
    org_id: str,
    *,
    aba: str | None = None,
    status: str | None = None,
    negocio_id: str | None = None,
    lead_id: str | None = None,
    cliente_id: str | None = None,
    q: str | None = None,
    hoje: date | None = None,
) -> list[dict]:
    """The Orçamentos page list, newest first. `aba` groups statuses
    (ativos / aceitos / recusados); `q` searches título, lead and empresa."""
    hoje = hoje or hoje_local()
    filtros = {
        k: v for k, v in
        {"negocio_id": negocio_id, "lead_id": lead_id, "cliente_id": cliente_id}.items() if v
    }
    linhas = paged_rows(db, "orcamento", org_id, eq_filters=filtros or None,
                        select=_ORCAMENTO_SELECT)
    _expirar_vencidos(db, org_id, linhas, hoje)
    if aba:
        linhas = [r for r in linhas if r.get("status") in ABAS[aba]]
    if status:
        linhas = [r for r in linhas if r.get("status") == status]
    dtos = montar_dtos(db, org_id, linhas)
    if q and q.strip():
        termo = q.strip().casefold()

        def _casa(d: dict) -> bool:
            lead = d.get("lead") or {}
            campos = (d.get("titulo"), lead.get("nome"), lead.get("empresa"), lead.get("email"))
            return any(termo in str(c).casefold() for c in campos if c)

        dtos = [d for d in dtos if _casa(d)]
    dtos.sort(key=lambda d: (str(d.get("created_at") or ""), d["versao"]), reverse=True)
    return dtos


def obter(db: Any, org_id: str, orcamento_id: str, *, hoje: date | None = None) -> dict:
    linha = carregar(db, org_id, orcamento_id)
    _expirar_vencidos(db, org_id, [linha], hoje or hoje_local())
    return montar_dtos(db, org_id, [linha])[0]


# ── Writes ───────────────────────────────────────────────────────────
def _proxima_versao(db: Any, org_id: str, negocio_id: str) -> int:
    linhas = paged_rows(db, "orcamento", org_id, eq_filters={"negocio_id": negocio_id},
                        select="id, versao")
    return max((int(r.get("versao") or 0) for r in linhas), default=0) + 1


def _gravar_itens(db: Any, org_id: str, orcamento_id: str, itens: list[dict]) -> None:
    """Replace the orçamento's items (delete + insert — items have no identity
    the client edits independently; the proposal is edited as a whole)."""
    db.table("orcamento_item").delete().eq("org_id", org_id).eq(
        "orcamento_id", orcamento_id
    ).execute()
    if itens:
        db.table("orcamento_item").insert(
            [{**i, "org_id": org_id, "orcamento_id": orcamento_id} for i in itens]
        ).execute()


def _totais_para(db: Any, org_id: str, itens: list[dict], desconto: float, custo_hora: float) -> dict:
    produtos = produtos_dos_itens(db, org_id, itens)
    return calcular_totais(itens, desconto=desconto, horas_por_produto=horas_por_produto(produtos),
                           custo_hora=custo_hora)


def criar(db: Any, org_id: str, dados: dict, *, custo_hora: float) -> dict:
    """New orçamento for a negócio — `versao` = max + 1 for that negócio."""
    negocio = qc.carregar(db, "negocio", org_id, dados["negocio_id"],
                          select="id, lead_id, cliente_id, titulo, status", rotulo="negócio")
    if negocio.get("status") != "aberto":
        raise RegraViolada(
            409, "negocio_encerrado",
            f"Este negócio está {negocio.get('status')} — não aceita novos orçamentos.",
        )
    itens = normalizar_itens(dados.get("itens") or [])
    totais = _totais_para(db, org_id, itens, dados.get("desconto") or 0, custo_hora)
    versao = _proxima_versao(db, org_id, str(negocio["id"]))
    titulo = (dados.get("titulo") or "").strip() or f"Proposta — {negocio.get('titulo')}"
    validade = dados.get("validade")
    linha = {
        "org_id": org_id,
        "negocio_id": negocio["id"],
        "lead_id": negocio.get("lead_id"),
        "cliente_id": negocio.get("cliente_id"),
        "versao": versao,
        "titulo": titulo,
        "status": "rascunho",
        "validade": validade.isoformat() if isinstance(validade, date) else validade,
        "limites_escopo": dados.get("limites_escopo") or dict(LIMITES_PADRAO),
        "observacoes": dados.get("observacoes"),
        **totais,
    }
    criado = db.table("orcamento").insert(linha).execute().data or []
    if not criado:
        raise RuntimeError("insert de orcamento não retornou a linha criada")
    orcamento = criado[0]
    _gravar_itens(db, org_id, str(orcamento["id"]), itens)
    logger.info("orcamento criado org=%s orcamento=%s negocio=%s v%d",
                org_id, orcamento["id"], negocio["id"], versao)
    return montar_dtos(db, org_id, [orcamento])[0]


def _exigir_editavel(orcamento: dict, acao: str) -> None:
    if orcamento.get("status") not in STATUS_ABERTOS:
        raise RegraViolada(
            409, "orcamento_bloqueado",
            f"Não é possível {acao}: este orçamento está {orcamento.get('status')}.",
        )


def atualizar(db: Any, org_id: str, orcamento_id: str, dados: dict, *, custo_hora: float,
              hoje: date | None = None) -> dict:
    """Edit a rascunho/enviado orçamento. Any content change voids the PDF —
    a PDF must never show numbers the proposal no longer has."""
    atual = carregar(db, org_id, orcamento_id)
    _expirar_vencidos(db, org_id, [atual], hoje or hoje_local())
    _exigir_editavel(atual, "editar")

    updates: dict[str, Any] = {}
    for campo in ("titulo", "observacoes", "limites_escopo"):
        if campo in dados:
            updates[campo] = dados[campo]
    if "validade" in dados:
        v = dados["validade"]
        updates["validade"] = v.isoformat() if isinstance(v, date) else v
    if "itens" in dados or "desconto" in dados:
        if "itens" in dados:
            itens = normalizar_itens(dados["itens"] or [])
        else:
            itens = [
                {**i, "produto_servico_id": i.get("produto_servico_id")}
                for i in itens_de(db, org_id, [orcamento_id])[orcamento_id]
            ]
        desconto = dados["desconto"] if dados.get("desconto") is not None else _num(atual.get("desconto"))
        updates.update(_totais_para(db, org_id, itens, desconto, custo_hora))
        if "itens" in dados:
            _gravar_itens(db, org_id, orcamento_id, itens)
    if updates:
        updates["pdf_key"] = None
        linhas = db.table("orcamento").update(updates).eq("id", orcamento_id).eq(
            "org_id", org_id
        ).execute().data or []
        if not linhas:
            raise RuntimeError("update de orcamento não retornou a linha")
    return obter(db, org_id, orcamento_id, hoje=hoje)


def nova_versao(db: Any, org_id: str, orcamento_id: str, *, hoje: date | None = None) -> dict:
    """Clone as a new `rascunho` (versao = max + 1); the source → `substituido`.

    An aceito proposal cannot be superseded (it is the deal), nor can one that
    is already substituido (clone the newest instead). A validade already past
    is not carried over — the new version would be born expired.
    """
    hoje = hoje or hoje_local()
    origem = carregar(db, org_id, orcamento_id)
    _expirar_vencidos(db, org_id, [origem], hoje)
    if origem.get("status") in ("aceito", "substituido"):
        raise RegraViolada(
            409, "orcamento_bloqueado",
            f"Não é possível criar nova versão: este orçamento está {origem.get('status')}.",
        )
    negocio_id = str(origem["negocio_id"])
    versao = _proxima_versao(db, org_id, negocio_id)
    copiar = (
        "negocio_id", "lead_id", "cliente_id", "titulo", "limites_escopo", "observacoes",
        *_NUMERICOS, "margem_estimada",
    )
    linha = {k: origem.get(k) for k in copiar}
    linha.update({
        "org_id": org_id,
        "versao": versao,
        "status": "rascunho",
        "validade": None if _vencido(origem, hoje) else origem.get("validade"),
    })
    db.table("orcamento").update({"status": "substituido"}).eq("id", orcamento_id).eq(
        "org_id", org_id
    ).execute()
    criado = db.table("orcamento").insert(linha).execute().data or []
    if not criado:
        raise RuntimeError("insert de orcamento não retornou a linha criada")
    novo = criado[0]
    itens = [
        {k: v for k, v in i.items() if k not in ("id", "quantidade")}
        for i in itens_de(db, org_id, [orcamento_id])[orcamento_id]
    ]
    _gravar_itens(db, org_id, str(novo["id"]), itens)
    logger.info("orcamento nova versao org=%s de=%s para=%s v%d",
                org_id, orcamento_id, novo["id"], versao)
    return montar_dtos(db, org_id, [novo])[0]


def recusar(db: Any, org_id: str, orcamento_id: str, motivo: str, *,
            hoje: date | None = None) -> dict:
    """The lead declined. Kept (with the reason) for the loss statistics."""
    if not (motivo or "").strip():
        raise RegraViolada(422, "motivo_obrigatorio", "Informe o motivo da recusa.")
    atual = carregar(db, org_id, orcamento_id)
    _expirar_vencidos(db, org_id, [atual], hoje or hoje_local())
    if atual.get("status") not in (*STATUS_ABERTOS, "expirado"):
        raise RegraViolada(
            409, "orcamento_bloqueado",
            f"Não é possível recusar: este orçamento está {atual.get('status')}.",
        )
    db.table("orcamento").update({
        "status": "recusado", "recusado_em": _agora(), "motivo_recusa": motivo.strip(),
    }).eq("id", orcamento_id).eq("org_id", org_id).execute()
    return obter(db, org_id, orcamento_id, hoje=hoje)


# ── Aceite ───────────────────────────────────────────────────────────
def _etapa_fechado(db: Any, org_id: str) -> dict:
    for etapa in etapas(db, PIPELINE_COMERCIAL, org_id):
        if etapa.get("papel") == PAPEL_FECHADO:
            return etapa
    raise RegraViolada(
        409, "funil_sem_fechamento",
        "O funil comercial não tem etapa de fechamento ativa. Configure as etapas primeiro.",
    )


def aceitar(db: Any, org_id: str, orcamento_id: str, *, user_id: Any,
            hoje: date | None = None) -> dict:
    """Accept = the funnel's fechado transition + the calendar.

    The transition is NOT re-implemented: the negócio is moved into the
    `fechado`-role stage by `comercial_funil.mover_negocio`, the one code path
    that accepts the orçamento, supersedes its open siblings, marks the deal
    ganho and creates the Cliente. Re-accepting an already-accepted orçamento
    is a no-op transition (pautas are idempotent per item).
    """
    hoje = hoje or hoje_local()
    orcamento = carregar(db, org_id, orcamento_id)
    negocio = qc.carregar(db, "negocio", org_id, str(orcamento["negocio_id"]),
                          select=comercial_funil.NEGOCIO_SELECT, rotulo="negócio")
    ja_aceito = (
        orcamento.get("status") == "aceito"
        and negocio.get("status") == "ganho"
        and str(negocio.get("orcamento_aceito_id")) == str(orcamento_id)
    )
    if not ja_aceito:
        if negocio.get("status") == "ganho":
            raise RegraViolada(
                409, "negocio_ganho", "Este negócio já foi fechado com outro orçamento.",
            )
        if orcamento.get("status") in STATUS_ABERTOS and _vencido(orcamento, hoje):
            _expirar_vencidos(db, org_id, [orcamento], hoje)
        if orcamento.get("status") == "expirado":
            raise RegraViolada(409, "orcamento_expirado", "A validade deste orçamento já passou.")
        fechado = _etapa_fechado(db, org_id)
        comercial_funil.mover_negocio(
            db, org_id,
            negocio_id=str(negocio["id"]),
            para_etapa_id=str(fechado["id"]),
            user_id=user_id,
            orcamento_id=orcamento_id,
        )
        negocio = qc.carregar(db, "negocio", org_id, str(negocio["id"]),
                              select=comercial_funil.NEGOCIO_SELECT, rotulo="negócio")
        orcamento = carregar(db, org_id, orcamento_id)
        if orcamento.get("status") != "aceito" or negocio.get("status") != "ganho":
            # The funnel refused silently (e.g. the card already sat in the
            # fechado stage while still aberto). Never report an aceite that
            # did not happen.
            raise RegraViolada(
                409, "aceite_nao_aplicado",
                "O negócio não pôde ser fechado com este orçamento — verifique a etapa do card.",
            )
    cliente = qc.carregar(db, "cliente", org_id, str(negocio["cliente_id"]), rotulo="cliente")
    pautas = gerar_pautas(db, org_id, orcamento_id, cliente_id=str(cliente["id"]), inicio=hoje)
    logger.info("orcamento aceito org=%s orcamento=%s negocio=%s pautas=%d",
                org_id, orcamento_id, negocio["id"], len(pautas))
    return {
        "orcamento": montar_dtos(db, org_id, [orcamento])[0],
        "negocio": negocio,
        "cliente": cliente,
        "pautas_criadas": len(pautas),
    }


def gerar_pautas(db: Any, org_id: str, orcamento_id: str, *, cliente_id: str,
                 inicio: date) -> list[dict]:
    """Calendar pautas for every RECURRING criação item, next 30 days.

    Pautas only — esteira tarefas are created on demand (roadmap R9). One pauta
    per matching weekday × `qtd_por_dia`, `gerada_automaticamente=true`, linked
    by `orcamento_item_id`. Idempotent per item: an item that already has
    generated pautas is skipped, so a retried aceite never doubles the calendar.
    """
    itens = [
        i for i in itens_de(db, org_id, [orcamento_id])[orcamento_id]
        if i["recorrente"] and i["secao"] == "criacao_conteudo"
    ]
    if not itens:
        return []
    existentes = {
        str(p.get("orcamento_item_id"))
        for p in in_batched_rows(db, "pauta", org_id, "orcamento_item_id",
                                 [str(i["id"]) for i in itens], select="id, orcamento_item_id")
    }
    produtos = qc.por_ids(db, "produto_servico", org_id,
                          (i.get("produto_servico_id") for i in itens), select="id, formato")
    novas: list[dict] = []
    for item in itens:
        if str(item["id"]) in existentes:
            continue
        formato = (produtos.get(str(item.get("produto_servico_id"))) or {}).get("formato")
        qtd = int(item["qtd_por_dia"])
        for delta in range(DIAS_DE_PAUTA):
            dia = inicio + timedelta(days=delta)
            if not item["dias_semana"] & (1 << dia.weekday()):
                continue
            quando = datetime.combine(dia, HORA_PAUTA, tzinfo=FUSO).isoformat()
            for n in range(qtd):
                novas.append({
                    "org_id": org_id,
                    "cliente_id": cliente_id,
                    "titulo": item["descricao"] if qtd == 1 else f"{item['descricao']} ({n + 1}/{qtd})",
                    "formato": formato,
                    "data_publicacao": quando,
                    "gerada_automaticamente": True,
                    "orcamento_item_id": item["id"],
                })
    criadas: list[dict] = []
    for lote_inicio in range(0, len(novas), 500):
        lote = novas[lote_inicio:lote_inicio + 500]
        criadas.extend(db.table("pauta").insert(lote).execute().data or [])
    if len(criadas) != len(novas):
        raise RuntimeError(
            f"insert de pautas retornou {len(criadas)} de {len(novas)} linhas"
        )
    return criadas
