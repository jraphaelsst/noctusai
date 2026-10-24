"""The per-PARTY Certidões tab — `GET/POST /api/clientes/{id}/certidoes/partes…`.
Contract: `projects/atendimento-partes-imoveis-CONTRACT.md` §1.1-§1.4.

Replaces the person-scoped, vendedor-only `certidoes_matriz_service.montar_matriz`
(which stays served, untouched — D6) with a matrix whose COLUMNS are every
party of the atendimento — titular as `COMP 1`, the other compradores, the
vendedores, PF and PJ alike — plus the derived `EMP n` empresa columns the
matriz already computed.

Three rules that differ from the old matriz, all pinned by the contract:

1. **A certidão follows the person.** Cells read through the party's own
   `cliente_id` / `empresa_id` (`certidoes_svc.certidoes_por_alvos`), never
   through `atendimento_parte_id`, so a certidão emitted on another deal
   still answers here. `atendimento_parte_id` stays as write-time provenance.
2. **Newest EMISSION wins**, not newest `created_at`: a dated cell beats an
   undated one, so a re-emission that is still pending or that FAILED never
   shadows the valid certidão already on file.
3. **Staleness is the contract gate's own predicate**
   (`idade_dias >= politica.certidao_max_dias`, `derivacao.py:1452`) with the
   default `Politica`, imported — never a literal 30.

WRITES never mutate an existing resultado: an emission is a NEW consulta (a
billed InfoSimples request per tipo, linked to the party), a re-emission is
a NEW consulta for one tipo, "ensure cell" is a manual placeholder. History
stays; selection by `emitida_em` is what makes the new one win when it lands.

The party list is `partes_service.listar_partes` — the ONE party reader
(CONTRACT §2.1); this module only adds the derived `EMP n` columns on top.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.card_hub import certidoes_exigencias_service as exig_svc
from app.modules.card_hub import compradores_service as comp_svc
from app.modules.card_hub import partes_service
from app.modules.card_hub.certidoes_matriz_service import (
    _linha_customizada,
    _linha_fixa,
    _status_da_celula,
    _status_do_resultado,
)
from app.modules.card_hub.contrato_gerador import certidao_pcen
from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO
from app.modules.card_hub.empresas_service import listar as listar_empresas
from app.modules.card_hub.services import (
    AmbiguousAtendimento,
    ensure_cliente,
    resolve_atendimento_id_incluindo_partes,
)
from app.modules.certidoes import service as certidoes_svc
from app.modules.certidoes.matriz_custom_rows import (
    linhas_customizadas_ativas,
)
from app.modules.certidoes.registry import (
    CERTIDOES_CONFIG,
    CONFIG_BY_TIPO,
    CUSTOM_ROW_TIPO,
    MANUAL_CONFIG_BY_TIPO,
    MATRIZ_LINHAS,
    PENDENCIA_CREDENCIAL_GOVBR,
    TJSP_TIPO,
    aplicavel_a_tipo_documento,
    e_pendencia_de_credencial,
)
from app.services import table_reads

logger = logging.getLogger(__name__)

ATENDIMENTOS = "atendimentos"
PARTES = "atendimento_partes"
CLIENTES = "clientes"
CONSULTAS = certidoes_svc.CONSULTAS
RESULTADOS = certidoes_svc.RESULTADOS

KINDS = ("pessoa", "empresa")
_TOTAL_CHAVES = ("nao_constam", "constam", "pendente", "processando", "relendo", "erros")
#: `status` values of a resultado whose read is running right now.
_LENDO = ("processando", "na_fila")
#: Checklist-order base for a custom row's resultado `ordem` — mirrors
#: `matriz_custom_rows._RESULTADO_ORDEM_BASE`.
_ORDEM_CUSTOM_BASE = 100
_EM_ANDAMENTO = ("pendente", "processando", "na_fila")


def _t(client: Any, table: str):
    return table_reads.table(client, table)


def _nao_encontrada() -> AppException:
    return AppException(
        code="NOT_FOUND", message="Parte não encontrada neste atendimento.", status_code=404
    )


def max_dias() -> int:
    """`politica.certidao_max_dias` — the contract gate's own window."""
    return POLITICA_PADRAO.certidao_max_dias


# ─── Atendimento resolution ───────────────────────────────────────────────


def _resolver_atendimento(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    explicit: Optional[UUID],
    *,
    estrito: bool,
) -> Optional[str]:
    """The atendimento the call is about. `explicit` is validated: it must be
    one this cliente is the titular of or a parte on (accepting an
    unvalidated id would read/write another deal's parties). Without it, the
    single open atendimento; ambiguous ⇒ `None` for a READ (`estrito=False`,
    the contract's "reads never 409"), `AmbiguousAtendimento` (409) for a
    WRITE."""
    if explicit is not None:
        rows = (
            _t(client, ATENDIMENTOS)
            .select("id, cliente_id")
            .eq("org_id", str(org_id))
            .eq("id", str(explicit))
            .limit(1)
            .execute()
        ).data or []
        if not rows:
            raise NotFoundError("atendimentos", str(explicit))
        if str(rows[0]["cliente_id"]) != str(cliente_id):
            e_parte = (
                _t(client, PARTES)
                .select("id")
                .eq("org_id", str(org_id))
                .eq("atendimento_id", str(explicit))
                .eq("cliente_id", str(cliente_id))
                .limit(1)
                .execute()
            ).data or []
            if not e_parte:
                raise NotFoundError("atendimentos", str(explicit))
        return str(explicit)
    try:
        return resolve_atendimento_id_incluindo_partes(client, org_id, cliente_id)
    except AmbiguousAtendimento:
        if estrito:
            raise
        return None


# ─── Parties ──────────────────────────────────────────────────────────────


def _documento(value: Optional[str]) -> Optional[str]:
    digits = only_digits(value or "")
    return digits or None


GRUPO_COMPRADOR = "comprador"
GRUPO_VENDEDOR = "vendedor"
GRUPO_ANTIGO = "antigo_proprietario"
PAPEL_ANTIGO_PROPRIETARIO = comp_svc.PAPEL_ANTIGO_PROPRIETARIO


def _empresas_derivadas(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    partes: list[dict],
    atendimento_id: Optional[str] = None,
) -> list[dict]:
    """The `EMP n` columns: the empresas the matriz already derives
    (`empresas_service.listar`, `exige_certidoes=True`) that are NOT already a
    PJ party — same filter as `certidoes_matriz_service.resolver_colunas`."""
    ja_parte = {p["empresa_id"] for p in partes if p.get("empresa_id")}
    out: list[dict] = []
    itens = listar_empresas(
        client, org_id, cliente_id,
        atendimento_id=UUID(str(atendimento_id)) if atendimento_id else None,
    ).get("items", [])
    for item in itens:
        if not item.get("exige_certidoes"):
            continue
        emp = item["empresa"]
        if str(emp["id"]) in ja_parte:
            continue
        # A company reached ONLY through previous owners belongs to the
        # antigos group (owner 2026-10-05); any other derived company is a
        # seller's.
        certificandos = [o for o in item.get("owners") or [] if o.get("certificando")]
        so_antigos = bool(certificandos) and all(
            o.get("papel") == PAPEL_ANTIGO_PROPRIETARIO for o in certificandos
        )
        out.append({
            "parte_id": None, "titular": False, "lado": None, "papel": "",
            "tipo_pessoa": "PJ", "cliente_id": None, "empresa_id": str(emp["id"]),
            "nome": emp.get("razao_social") or emp.get("nome_fantasia") or "",
            "documento": _documento(emp.get("cnpj")),
            "grupo": GRUPO_ANTIGO if so_antigos else GRUPO_VENDEDOR,
        })
    contadores = {GRUPO_VENDEDOR: 0, GRUPO_ANTIGO: 0}
    for item in out:
        contadores[item["grupo"]] += 1
        prefixo = "EMP" if item["grupo"] == GRUPO_VENDEDOR else "ANT EMP"
        item["rotulo"] = f"{prefixo} {contadores[item['grupo']]}"
    return out


def _chave(parte: dict) -> str:
    return f"c:{parte['cliente_id']}" if parte.get("cliente_id") else f"e:{parte['empresa_id']}"


def _kind(parte: dict) -> str:
    return "pessoa" if parte.get("cliente_id") else "empresa"


# ─── Lines + cells ────────────────────────────────────────────────────────


def _linha(linha: dict) -> dict:
    """A fixed matriz line + `automatico` (CONTRACT amendment): true exactly
    when the tipo is emitted through InfoSimples — derived from the registry,
    never a second hand-kept list."""
    return {**_linha_fixa(linha), "automatico": linha["tipo"] in CONFIG_BY_TIPO}


def _linha_custom(row: dict) -> dict:
    return {**_linha_customizada(row), "automatico": False}


def montar_linhas(client: Any, org_id: UUID, titular_id: str) -> list[dict]:
    custom = linhas_customizadas_ativas(client, org_id, titular_id)
    return [_linha(l) for l in MATRIZ_LINHAS] + [_linha_custom(r) for r in custom]


def _vencedor_chave(resultado: dict) -> tuple:
    """Newest EMISSION wins; a dated cell always beats an undated one;
    ties/nulls fall back to `created_at`."""
    emitida = resultado.get("emitida_em")
    return (emitida is not None, str(emitida or ""), str(resultado.get("created_at") or ""))


def _cancelado_vazio(resultado: dict) -> bool:
    """An empty manual placeholder an operator cancelled (`erro` /
    "Cancelado manualmente"). It carries no evidence, so it must read like no
    row at all — never win the cell and paint it red."""
    return resultado.get("status") == "erro" and certidoes_svc.e_placeholder_vazio(
        resultado, resultado.get("consulta_origem")
    )


def indexar_vencedores(resultados: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    """`(por_tipo, por_linha_customizada)` — the winning resultado of each.

    A cancelled EMPTY manual placeholder never wins (see `_cancelado_vazio`);
    `garantir_celula` revives it when the operator opens the cell again.
    """
    por_tipo: dict[str, dict] = {}
    por_linha: dict[str, dict] = {}
    for r in resultados:
        if _cancelado_vazio(r):
            continue
        if certidoes_svc.e_cancelado_manual_com_evidencia(r, r.get("consulta_origem")):
            # Pre-cancel state: the human's cell was never in progress.
            r = {**r, "status": "pendente", "erro_mensagem": None}
        linha_id = r.get("linha_customizada_id")
        alvo, chave = (por_linha, linha_id) if linha_id else (por_tipo, r.get("tipo"))
        if not chave:
            continue
        atual = alvo.get(chave)
        if atual is None or _vencedor_chave(r) > _vencedor_chave(atual):
            alvo[chave] = r
    return por_tipo, por_linha


_TENTATIVA_STATUS = ("erro", "pendente", *_LENDO)


def ultimas_tentativas(
    resultados: list[dict], vencedores: dict[str, dict]
) -> dict[str, dict]:
    """`tipo -> ultima_tentativa` — the newest AUTOMATIC attempt that is NOT the
    cell's winning evidence and was created AFTER it (F100).

    `indexar_vencedores` lets a dated certidão beat an undated failed/in-flight
    re-emission (so a re-emission can never destroy valid evidence), which also
    made the failure INVISIBLE: the operator clicked "Re-emitir", it errored,
    and the cell kept showing the old PDF with no hint. This is that hint:
    `{status, erro, em, resultado_id}`. Never replaces the winner. Manual
    consultas, custom rows, empty cancelled placeholders and credential
    pendências (their own `pendencia` channel) are not attempts.
    """
    out: dict[str, dict] = {}
    for r in resultados:
        tipo = r.get("tipo")
        if (
            r.get("linha_customizada_id") or not _emissao_automatica(tipo, r)
            or r.get("status") not in _TENTATIVA_STATUS
            or _cancelado_vazio(r) or e_pendencia_de_credencial(r)
        ):
            continue
        ganhador = vencedores.get(tipo)
        if ganhador is None or ganhador.get("id") == r.get("id"):
            continue
        if str(r.get("created_at") or "") <= str(ganhador.get("created_at") or ""):
            continue
        atual = out.get(tipo)
        if atual is None or str(r.get("created_at") or "") > str(atual["_criada"]):
            out[tipo] = {
                "status": r["status"],
                "erro": r.get("erro_mensagem") if r["status"] == "erro" else None,
                "em": r.get("updated_at") or r.get("created_at"),
                "resultado_id": r.get("id"),
                "_criada": r.get("created_at") or "",
            }
    for t in out.values():
        t.pop("_criada")
    return out


def _na(tipo: Optional[str]) -> dict:
    return {
        "status": "na", "texto": "N/A", "tipo": tipo,
        "resultado_id": None, "consulta_id": None, "status_processamento": None,
        "resultado": None, "numero": None, "emitida_em": None, "validade_ate": None,
        "idade_dias": None, "stale_para_contrato": False, "arquivo_url": None,
        "tem_arquivo": False, "arquivo_manual": False, "pode_reler": False, "releitura": None,
        "arquivo_nome": None, "origem": None, "emitida_em_origem": None,
        "confirmado": False, "analise_ia": None, "erro_mensagem": None,
        "segunda_via": False, "pcen": None, "pendencia": None,
        "aguarda_humano": False, "emissao_automatica": False, "ultima_tentativa": None,
    }


def _origem_da_celula(row: dict) -> Optional[str]:
    """`certidao_resultados.resultado_origem` — who produced the cell's values,
    nothing else. (It used to ALSO read `"manual"` for an untouched manual
    placeholder so the FE would stop polling; that made a cell with nothing on
    it look hand-filled and offered "Voltar à leitura automática" on it — the
    polling signal is `_aguarda_humano` now.)"""
    return row.get("resultado_origem") or None


def _aguarda_humano(row: dict) -> bool:
    """A still-`pendente`, never-touched placeholder of a MANUAL consulta
    (migration 147): nothing will ever process it, only a person can fill it —
    the FE must not keep polling on it. Once an upload flips it to
    `processando` it is the pipeline's again."""
    return row.get("status") == "pendente" and row.get("consulta_origem") == "manual"


def _emissao_automatica(tipo: Optional[str], row: dict) -> bool:
    """The cell's row belongs to a live InfoSimples emission — a consulta that
    is not manual and a tipo the registry emits. Cancel / retry / discard act
    on these only; a manual cell is the operator's, never the pipeline's."""
    return bool(row.get("id")) and tipo in CONFIG_BY_TIPO and row.get("consulta_origem") != "manual"


def montar_celula(
    tipo: Optional[str], row: Optional[dict], hoje: date, limite: int,
    tentativa: Optional[dict] = None,
) -> dict:
    status, texto = _status_da_celula(row)
    row = row or {}
    if row.get("status") in _LENDO and row.get("resultado"):
        # A RE-read keeps the previous values until the new read lands
        # (`preparar_releitura` clears nothing): classify by them rather than
        # showing a cell that holds a result as "pendente".
        status, texto = _status_do_resultado(row.get("resultado"))
    emitida = row.get("emitida_em")
    idade: Optional[int] = None
    if emitida:
        idade = (hoje - date.fromisoformat(str(emitida)[:10])).days
    validade = _iso_para_data(row.get("validade_ate"))
    excecao = certidao_pcen.excecao_aplica(
        resultado=row.get("resultado"),
        segunda_via=certidao_pcen.e_segunda_via(row.get("api_response")),
        validade_ate=validade,
    )
    # ONE rule with the contract gate (`derivacao._certidoes`): the Receita
    # PCEN 2ª via is judged by its printed validity, everything else by age.
    vencida = certidao_pcen.esta_vencida(
        emitida_em=_iso_para_data(emitida), validade_ate=validade,
        referencia=hoje, max_dias=limite, excecao=excecao,
    )
    return {
        "status": status,
        "texto": texto,
        "tipo": tipo,
        "resultado_id": row.get("id"),
        "consulta_id": row.get("consulta_id"),
        "status_processamento": row.get("status"),
        "resultado": row.get("resultado"),
        "numero": row.get("numero"),
        "emitida_em": emitida,
        "validade_ate": row.get("validade_ate"),
        "idade_dias": idade,
        "stale_para_contrato": vencida,
        "arquivo_url": row.get("arquivo_url"),
        "tem_arquivo": bool(row.get("arquivo_url")),
        # A human's upload sits in our bucket — the "Ler o documento
        # novamente" action re-reads it (`certidoes.service.tem_arquivo_manual`).
        "arquivo_manual": certidoes_svc.tem_arquivo_manual(row),
        # Any PDF in our bucket — upload OR live receipt — can be re-read
        # ("Reler", `certidoes.service.pode_reler`); `releitura` is the last
        # re-read's state + divergences (migration 196).
        "pode_reler": certidoes_svc.pode_reler(row),
        "releitura": _releitura_publica(row),
        "arquivo_nome": row.get("arquivo_nome"),
        "origem": _origem_da_celula(row),
        "aguarda_humano": _aguarda_humano(row),
        "emissao_automatica": _emissao_automatica(tipo, row),
        # A newer automatic attempt that did not win the cell (failed / in
        # flight) — see `ultimas_tentativas`. None when the winner IS the latest.
        "ultima_tentativa": tentativa,
        # `metadados_pdf` = the date was INFERRED from the PDF CreationDate
        # (the consulta printed no date); None = printed / registry / typed.
        "emitida_em_origem": row.get("emitida_em_origem"),
        "confirmado": row.get("confirmado_em") is not None,
        "analise_ia": row.get("analise_ia"),
        "erro_mensagem": row.get("erro_mensagem"),
        "segunda_via": certidao_pcen.e_segunda_via(row.get("api_response")),
        "pcen": _bloco_pcen(row, validade, hoje) if excecao else None,
        # PENDING for a reason a human can fix (not an error): the org has no
        # GOV.BR login for this tipo, `erro_mensagem` carries the pt-BR text.
        "pendencia": PENDENCIA_CREDENCIAL_GOVBR if e_pendencia_de_credencial(row) else None,
    }


def _releitura_publica(row: dict) -> Optional[dict]:
    """The cell's view of `certidao_resultados.releitura`: `em_andamento`
    only while it is genuinely in flight (`certidoes.service.
    releitura_em_andamento` — an interrupted one stops reading as running),
    plus the divergences a human must decide."""
    estado = row.get("releitura")
    if not isinstance(estado, dict):
        return None
    return {
        "em_andamento": certidoes_svc.releitura_em_andamento({"releitura": estado}),
        "concluida_em": estado.get("concluida_em"),
        "divergencias": list(estado.get("divergencias") or []),
    }


def _iso_para_data(valor: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


def _bloco_pcen(row: dict, validade: date, hoje: date) -> dict:
    """The educational block of the Receita PCEN 2ª via (shared copy with the
    contract readiness `confirmacao`) + its acknowledgment state."""
    emitida = _iso_para_data(row.get("emitida_em"))
    ciente = certidao_pcen.ciente_vale(
        ciente_em=row.get("pcen_ciente_em"),
        ciente_validade=_iso_para_data(row.get("pcen_ciente_validade")),
        validade_ate=validade,
    )
    return {
        "titulo": certidao_pcen.TITULO,
        "mensagem": certidao_pcen.aviso(emitida, validade),
        "explicacao": certidao_pcen.explicacao(emitida, validade),
        "validade_ate": validade.isoformat(),
        "vencida": validade < hoje,
        "ciente": ciente,
        "ciente_em": row.get("pcen_ciente_em") if ciente else None,
        "duvida_em": row.get("pcen_duvida_em"),
        "acoes": {"entendi": certidao_pcen.ACAO_ENTENDI, "duvida": certidao_pcen.ACAO_DUVIDA},
    }


def _aplicavel(linha: dict, parte: dict) -> bool:
    """Owner rules unchanged from the matriz: FGTS is N/A on a PF, SERASA on a
    PJ, custom rows never N/A."""
    tipo = linha.get("tipo")
    if not tipo or tipo not in MANUAL_CONFIG_BY_TIPO:
        return True
    return aplicavel_a_tipo_documento(tipo, "cpf" if parte["tipo_pessoa"] == "PF" else "cnpj")


#: Owner decision 2026-10-21 (migration 295): the matriz row whose certidão is
#: optional unless the deal opts in (`exigir_crf_fgts`).
TIPO_CRF_FGTS = "fgts_regularidade"


def _opcional(
    parte: dict, tipo: Optional[str], status: str, exigencias: dict
) -> bool:
    """Is this EMPTY cell optional for the deal? Only a cell with nothing on
    file can be "Opcional" — a certidão that exists is data, never hidden."""
    if status != "pendente":
        return False
    if parte.get("grupo") == GRUPO_ANTIGO and not exigencias.get("exigir_certidoes_antigos"):
        return True
    return tipo == TIPO_CRF_FGTS and not exigencias.get("exigir_crf_fgts")


def montar_parte(
    parte: dict, linhas: list[dict], resultados: list[dict], hoje: date, limite: int,
    exigencias: Optional[dict] = None,
) -> dict:
    exigencias = exigencias or {}
    por_tipo, por_linha = indexar_vencedores(resultados)
    tentativas = ultimas_tentativas(resultados, por_tipo)
    celulas: dict[str, dict] = {}
    totais = {**{k: 0 for k in _TOTAL_CHAVES}, "vencidas": 0, "opcionais": 0}
    for linha in linhas:
        chave = linha["chave"]
        if not _aplicavel(linha, parte):
            celulas[chave] = {**_na(linha.get("tipo")), "opcional": False}
            continue
        row = por_linha.get(chave) if linha["custom"] else por_tipo.get(chave)
        celula = montar_celula(
            linha.get("tipo"), row, hoje, limite,
            None if linha["custom"] else tentativas.get(linha.get("tipo")),
        )
        celula["opcional"] = _opcional(parte, linha.get("tipo"), celula["status"], exigencias)
        celulas[chave] = celula
        lendo = celula["status_processamento"] in _LENDO
        if celula["status_processamento"] == "erro" or (
            celula["ultima_tentativa"] and celula["ultima_tentativa"]["status"] == "erro"
        ):
            # An overlay (the cell stays counted in its color bucket): how many
            # of the party's cells FAILED, for the summary line.
            totais["erros"] += 1
        # A cell being read is counted APART from the pendentes (it is not a
        # pendência, it is in flight): `processando` when it holds no value
        # yet, `relendo` when it keeps its previous value (counted in its
        # color bucket too — `relendo` is an overlay, not a partition).
        if lendo and celula["status"] == "pendente":
            totais["processando"] += 1
        else:
            totais["opcionais" if celula["opcional"] else celula["status"]] += 1
            if lendo or celula["releitura"] and celula["releitura"].get("em_andamento"):
                totais["relendo"] += 1
        if celula["stale_para_contrato"]:
            totais["vencidas"] += 1
    return {
        "chave": _chave(parte),
        "kind": _kind(parte),
        "tipo_pessoa": parte["tipo_pessoa"],
        "rotulo": parte["rotulo"],
        "lado": parte["lado"],
        # `comprador` | `vendedor` | `antigo_proprietario` — the UI splits its
        # subtabs on this, never on a papel string.
        "grupo": parte["grupo"],
        "papel": parte["papel"],
        "titular": parte["titular"],
        "nome": parte["nome"],
        "documento": parte["documento"],
        "cliente_id": parte["cliente_id"],
        "empresa_id": parte["empresa_id"],
        "parte_id": parte["parte_id"],
        "totais": totais,
        "celulas": celulas,
    }


def _vazio(hoje: date) -> dict:
    return {
        "atendimento_id": None,
        "data_referencia": hoje.isoformat(),
        "max_dias": max_dias(),
        "linhas": [_linha(l) for l in MATRIZ_LINHAS],
        "partes": [],
        "exigencias": exig_svc.da_linha({}),
    }


def _todas_as_partes(
    client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: str
) -> list[dict]:
    _alvo, partes = partes_service.listar_partes(
        client, org_id, cliente_id, atendimento_id=UUID(str(atendimento_id))
    )
    antigos = partes_service.listar_antigos(
        client, org_id, cliente_id, atendimento_id=UUID(str(atendimento_id))
    )
    for p in partes:
        p["grupo"] = p["lado"]
    for p in antigos:
        p["grupo"] = GRUPO_ANTIGO
    derivadas = _empresas_derivadas(
        client, org_id, cliente_id, partes + antigos, atendimento_id=atendimento_id
    )
    # Buyers, sellers, the sellers' companies; THEN the previous owners and
    # their companies — each group its own subtab in the UI.
    return (
        partes
        + [e for e in derivadas if e["grupo"] == GRUPO_VENDEDOR]
        + antigos
        + [e for e in derivadas if e["grupo"] == GRUPO_ANTIGO]
    )


def _titular_do(partes: list[dict]) -> str:
    return next(p["cliente_id"] for p in partes if p["titular"])


def data_assinatura_do_atendimento(client: Any, org_id: UUID, atendimento_id: str) -> Optional[date]:
    """The signing date stored on the deal's contract(s)
    (`atendimento_contratos.assinatura_data`, migration 114) — the latest set
    one. The contract gate (`contrato_gerador.service.data_assinatura`) ages
    every certidão against it; the grid must use the same reference."""
    rows = (
        _t(client, "atendimento_contratos")
        .select("assinatura_data")
        .eq("org_id", str(org_id))
        .eq("atendimento_id", str(atendimento_id))
        .execute()
    ).data or []
    datas = [d for d in (_iso_para_data(r.get("assinatura_data")) for r in rows) if d]
    return max(datas) if datas else None


def montar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    atendimento_id: Optional[UUID] = None,
    hoje: Optional[date] = None,
) -> dict:
    """`GET …/certidoes/partes` — the whole response (CONTRACT §1.1)."""
    hoje = hoje or date.today()
    ensure_cliente(client, org_id, cliente_id)
    alvo = _resolver_atendimento(client, org_id, cliente_id, atendimento_id, estrito=False)
    if alvo is None:
        return _vazio(hoje)
    partes = _todas_as_partes(client, org_id, cliente_id, alvo)
    if not partes:
        return {**_vazio(hoje), "atendimento_id": alvo}
    linhas = montar_linhas(client, org_id, _titular_do(partes))
    resultados = certidoes_svc.certidoes_por_alvos(
        client, org_id,
        cliente_ids=[p["cliente_id"] for p in partes if p["cliente_id"]],
        empresa_ids=[p["empresa_id"] for p in partes if p["empresa_id"]],
    )
    limite = max_dias()
    exigencias = exig_svc.ler(client, org_id, alvo)
    # Age against the contract's signing date when set (same reference as the
    # gate's "na data da assinatura"); today only when absent.
    hoje = data_assinatura_do_atendimento(client, org_id, alvo) or hoje
    return {
        "atendimento_id": alvo,
        "exigencias": exigencias,
        "data_referencia": hoje.isoformat(),
        "max_dias": limite,
        "linhas": linhas,
        "partes": [
            montar_parte(p, linhas, resultados.get(_chave(p), []), hoje, limite, exigencias)
            for p in partes
        ],
    }


# ─── Writes ───────────────────────────────────────────────────────────────


def _achar_parte(partes: list[dict], kind: str, alvo_id: str) -> dict:
    for p in partes:
        if _kind(p) == kind and str(p["cliente_id"] or p["empresa_id"]) == str(alvo_id):
            return p
    raise _nao_encontrada()


def _exigir_kind(kind: str) -> str:
    if kind not in KINDS:
        raise AppException(code="NOT_FOUND", message="Recurso não encontrado.", status_code=404)
    return kind


def _tipo_automatico(tipo: str) -> dict:
    """The InfoSimples config for `tipo`, or the contract's 422."""
    config = CONFIG_BY_TIPO.get(tipo)
    if config is not None:
        return config
    manual = MANUAL_CONFIG_BY_TIPO.get(tipo)
    if manual is not None or tipo == CUSTOM_ROW_TIPO:
        rotulo = manual["nome"] if manual else "Outras certidões"
        raise AppException(
            code="TIPO_NAO_AUTOMATICO",
            message=f"{rotulo} é registrada manualmente — envie o PDF na célula.",
            status_code=422,
            details={"tipo": tipo},
        )
    raise AppException(
        code="TIPO_INVALIDO", message=f"Tipo de certidão inválido: {tipo}.",
        status_code=422, details={"tipo": tipo},
    )


def _documento_valido(parte: dict) -> Optional[str]:
    """The party's CPF/CNPJ when it has the right length for its kind."""
    documento = parte.get("documento")
    esperado = 11 if parte["tipo_pessoa"] == "PF" else 14
    return documento if documento and len(documento) == esperado else None


def _dados_consulta(
    client: Any, org_id: UUID, parte: dict, *, exigir_documento: bool = True
) -> dict:
    """The party-identifying columns of a new consulta. `data_nascimento` /
    `genero` / `rg` / `nome_mae` are copied off the cliente when present — the
    same fields `ConsultaCreate` takes (CND Federal needs the birthdate).

    `exigir_documento=False` is the MANUAL cell holder only (`garantir_celula`,
    F86): its consulta is never dispatched to InfoSimples, so the CPF/CNPJ —
    an API parameter — is not needed, and a party known only by name (an
    antigo proprietário whose identity comes from his certidões) must still
    receive its PDFs. `documento` is then NULL (migration 307 allows it for
    `origem='manual'` only); `feed_parte.alimentar_documento_impresso` offers
    the CPF the uploaded certidão prints back to the party."""
    documento = _documento_valido(parte)
    if documento is None and exigir_documento:
        raise AppException(
            code="DOCUMENTO_AUSENTE",
            message="Informe o CPF/CNPJ da parte antes de solicitar certidões.",
            status_code=422,
        )
    nome = parte["nome"] or documento
    if not nome:
        raise AppException(
            code="PARTE_SEM_IDENTIFICACAO",
            message="Informe o nome ou o CPF/CNPJ da parte antes de enviar certidões.",
            status_code=422,
        )
    dados: dict[str, Any] = {
        "tipo_documento": "cpf" if parte["tipo_pessoa"] == "PF" else "cnpj",
        "documento": documento,
        "nome": nome,
    }
    if parte["tipo_pessoa"] == "PF":
        row = (
            _t(client, CLIENTES)
            .select("id, data_nascimento, genero, rg, nome_mae")
            .eq("org_id", str(org_id))
            .eq("id", parte["cliente_id"])
            .limit(1)
            .execute()
        ).data or []
        if row:
            for campo in ("data_nascimento", "rg", "nome_mae"):
                if row[0].get(campo):
                    dados[campo] = str(row[0][campo])
            if row[0].get("genero") in ("M", "F"):
                dados["genero"] = row[0]["genero"]
    return dados


def _vinculo(parte: dict) -> dict:
    out: dict[str, Any] = {}
    if parte.get("cliente_id"):
        out["cliente_id"] = parte["cliente_id"]
    if parte.get("empresa_id"):
        out["empresa_id"] = parte["empresa_id"]
    if parte.get("parte_id"):
        out["atendimento_parte_id"] = parte["parte_id"]
    return out


def _criar_consulta_automatica(
    client: Any, org_id: UUID, user_id: Any, parte: dict, configs: list[dict]
) -> dict:
    consulta = client.table(CONSULTAS).insert({
        **_dados_consulta(client, org_id, parte),
        **_vinculo(parte),
        "org_id": str(org_id),
        "created_by": str(user_id),
        "status": "pendente",
        "total_certidoes": len(configs),
        "concluidas": 0,
    }).execute().data
    if not consulta:
        raise AppException(code="INTERNAL_ERROR", message="Erro ao criar consulta", status_code=500)
    consulta = consulta[0]
    resultados = client.table(RESULTADOS).insert([
        {
            "consulta_id": consulta["id"], "org_id": str(org_id), "tipo": c["tipo"],
            "nome_display": c["nome"], "ordem": c["ordem"], "status": "pendente",
        }
        for c in configs
    ]).execute().data or []
    # A Serasa Crednet uploaded BEFORE this consulta existed has nobody to
    # apply it: fill the `serasa` cell now (`aplicar_crednet_pendente` is a
    # no-op for a CNPJ consulta or when no reading is on file).
    certidoes_svc.aplicar_crednet_pendente(client, org_id, consulta)
    return {
        "consulta_id": consulta["id"],
        "resultados": [
            {"resultado_id": r["id"], "tipo": r["tipo"], "status_processamento": "pendente"}
            for r in resultados
        ],
    }


def _preflight_credenciais(check: Callable[[str], list[str]], org_id: UUID) -> None:
    faltando = check(str(org_id))
    if faltando:
        raise AppException(
            code="CREDENCIAIS_AUSENTES",
            message=" ".join(faltando) + " Configure em Configurações → Chaves de API.",
            status_code=422,
        )


def solicitar_emissao(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    kind: str,
    alvo_id: UUID,
    *,
    tipos: Optional[list[str]],
    atendimento_id: Optional[UUID],
    user_id: Any,
    check_credentials: Callable[[str], list[str]],
) -> dict:
    """`POST …/certidoes/partes/{kind}/{alvo_id}/emissao` (CONTRACT §1.2).
    Everything is validated, and credentials pre-flighted, BEFORE the first
    write. The caller schedules `processar_consulta(result["consulta_id"])`."""
    _exigir_kind(kind)
    ensure_cliente(client, org_id, cliente_id)
    alvo = _resolver_atendimento(client, org_id, cliente_id, atendimento_id, estrito=True)
    partes = _todas_as_partes(client, org_id, cliente_id, alvo)
    parte = _achar_parte(partes, kind, str(alvo_id))
    ignoradas: list[str] = []
    if tipos is None:
        # "All" never re-buys what is already good: a paid certidão still in
        # date (or being emitted right now) is skipped, and said so. A tipo
        # picked by name is the operator's explicit choice and goes through.
        celulas = _parte_montada(client, org_id, alvo, partes, parte)["celulas"]
        ignoradas = [
            c["tipo"] for c in CERTIDOES_CONFIG
            if c["tipo"] != TJSP_TIPO and _vigente_ou_em_andamento(celulas.get(c["tipo"]))
        ]
        tipos = [c["tipo"] for c in CERTIDOES_CONFIG if c["tipo"] != TJSP_TIPO and c["tipo"] not in ignoradas]
        if not tipos:
            raise AppException(
                code="NADA_A_EMITIR",
                message="Todas as certidões automáticas desta parte já estão válidas ou sendo emitidas.",
                status_code=409,
                details={"ignoradas": ignoradas},
            )
    out = solicitar_emissao_da_parte(
        client, org_id, parte, tipos=tipos, user_id=user_id, check_credentials=check_credentials,
    )
    return {**out, "ignoradas": ignoradas}


def _vigente_ou_em_andamento(celula: Optional[dict]) -> bool:
    """A cell NOT worth paying for again: a finished read still in date, or one
    that is being produced right now."""
    if not celula:
        return False
    estado = celula["status_processamento"]
    if estado in _LENDO:
        return True
    return estado == "sucesso" and not celula["stale_para_contrato"]


def todas_as_partes(
    client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: str
) -> list[dict]:
    """Public handle on the Certidões tab's party list (buyers, sellers, the
    sellers' derived `EMP n`, then the previous owners) — what `montar` walks."""
    return _todas_as_partes(client, org_id, cliente_id, atendimento_id)


def solicitar_emissao_da_parte(
    client: Any,
    org_id: UUID,
    parte: dict,
    *,
    tipos: Optional[list[str]],
    user_id: Any,
    check_credentials: Callable[[str], list[str]],
) -> dict:
    """The write half of `solicitar_emissao`, for a party ALREADY resolved.

    Exists for callers that certify a person who is not a row of the
    atendimento's party list — the registered cônjuge of a seller who never
    got an `atendimento_partes` row of their own (post-aceite automation,
    CONTRACT sw-lead-to-contract §7.1). Same validation, same pre-flight, same
    consulta; `parte` needs `tipo_pessoa`, `nome`, `documento`, `cliente_id` /
    `empresa_id` and (optionally) `parte_id`."""
    if tipos is None:
        configs = [c for c in CERTIDOES_CONFIG if c["tipo"] != TJSP_TIPO]
    else:
        configs = [_tipo_automatico(t) for t in dict.fromkeys(tipos)]
    if not configs:
        raise AppException(
            code="TIPO_INVALIDO", message="Informe ao menos um tipo de certidão.", status_code=422,
        )
    _dados_consulta(client, org_id, parte)  # DOCUMENTO_AUSENTE before any write
    _preflight_credenciais(check_credentials, org_id)
    return _criar_consulta_automatica(client, org_id, user_id, parte, configs)


def _consulta_do_resultado(client: Any, org_id: UUID, resultado_id: str) -> tuple[dict, dict]:
    """`(resultado, consulta)` for a live resultado, or the contract's 404."""
    rows = (
        _t(client, RESULTADOS)
        .select("id, consulta_id, tipo")
        .eq("org_id", str(org_id))
        .eq("id", resultado_id)
        .is_("excluida_em", "null")
        .limit(1)
        .execute()
    ).data or []
    if not rows:
        raise NotFoundError("Resultado")
    consultas = (
        _t(client, CONSULTAS)
        .select("id, cliente_id, empresa_id")
        .eq("org_id", str(org_id))
        .eq("id", rows[0]["consulta_id"])
        .is_("excluida_em", "null")
        .limit(1)
        .execute()
    ).data or []
    if not consultas:
        raise NotFoundError("Resultado")
    return rows[0], consultas[0]


def _candidatos_do_card(
    client: Any, org_id: UUID, cliente_id: UUID
) -> list[tuple[str, list[dict]]]:
    """`[(atendimento_id, partes)]` of the card's atendimento — or, when it is
    ambiguous, of every candidate (a body-less write has no `atendimento_id` to
    say which)."""
    try:
        candidatos = [resolve_atendimento_id_incluindo_partes(client, org_id, cliente_id)]
    except AmbiguousAtendimento as exc:
        candidatos = list(exc.candidates)
    return [(a, _todas_as_partes(client, org_id, cliente_id, a)) for a in candidatos]


def _partes_do_card(client: Any, org_id: UUID, cliente_id: UUID) -> list[list[dict]]:
    return [partes for _a, partes in _candidatos_do_card(client, org_id, cliente_id)]


def _resultados_da_parte(client: Any, org_id: UUID, parte: dict) -> list[dict]:
    """EVERY live resultado of the party (follows the person across deals)."""
    return certidoes_svc.certidoes_por_alvos(
        client, org_id,
        cliente_ids=[parte["cliente_id"]] if parte["cliente_id"] else [],
        empresa_ids=[parte["empresa_id"]] if parte["empresa_id"] else [],
    ).get(_chave(parte), [])


def _parte_montada(
    client: Any, org_id: UUID, alvo: str, partes: list[dict], parte: dict,
    *, hoje: Optional[date] = None,
) -> dict:
    """The party as `GET …/partes` would serve it right now — the same
    `montar_parte` (reference date = the contract's signing date when set), so a
    write can hand the FE the party's true state instead of a guess."""
    limite = max_dias()
    referencia = data_assinatura_do_atendimento(client, org_id, alvo) or hoje or date.today()
    return montar_parte(
        parte,
        montar_linhas(client, org_id, _titular_do(partes)),
        _resultados_da_parte(client, org_id, parte),
        referencia, limite, exig_svc.ler(client, org_id, alvo),
    )


def _localizar(
    client: Any, org_id: UUID, cliente_id: UUID, resultado_id: str
) -> tuple[str, list[dict], dict, dict]:
    """`(atendimento_id, partes, parte, resultado)` of a live resultado that
    belongs to one of the card's parties — anything else is the contract's 404
    (a resultado of another card / org never answers here)."""
    _consulta_do_resultado(client, org_id, resultado_id)
    for alvo, partes in _candidatos_do_card(client, org_id, cliente_id):
        for parte in partes:
            for r in _resultados_da_parte(client, org_id, parte):
                if r["id"] == resultado_id:
                    return alvo, partes, parte, r
    raise NotFoundError("Resultado")


def reemitir(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    resultado_id: str,
    *,
    user_id: Any,
    check_credentials: Callable[[str], list[str]],
) -> dict:
    """`POST …/certidoes/resultados/{resultado_id}/reemitir` (CONTRACT §1.3):
    a NEW consulta + NEW resultado, same party and tipo; the original is
    untouched."""
    ensure_cliente(client, org_id, cliente_id)
    resultado, consulta = _consulta_do_resultado(client, org_id, resultado_id)
    kind = "pessoa" if consulta.get("cliente_id") else "empresa"
    alvo_id = str(consulta.get("cliente_id") or consulta.get("empresa_id"))
    parte = next(
        (
            p
            for partes in _partes_do_card(client, org_id, cliente_id)
            for p in partes
            if _kind(p) == kind and str(p["cliente_id"] or p["empresa_id"]) == alvo_id
        ),
        None,
    )
    if parte is None:
        raise NotFoundError("Resultado")
    config = _tipo_automatico(resultado["tipo"])
    _dados_consulta(client, org_id, parte)
    _preflight_credenciais(check_credentials, org_id)
    return _criar_consulta_automatica(client, org_id, user_id, parte, [config])


def _suporte_da_org(client: Any, org_id: UUID) -> Optional[dict]:
    """The office's SUPPORT contact — `org_dados_cadastrais.suporte_*`
    (migration 189, set in Configurações → Imobiliária). Deliberately NOT the
    notification recipients (owner decision 2026-10-02: a lead-alert inbox is
    not a help desk), and no fallback to them. `None` = not configured; the UI
    says so instead of showing a dead button."""
    try:
        rows = (
            _t(client, "org_dados_cadastrais")
            .select("suporte_nome, suporte_whatsapp, suporte_email")
            .eq("org_id", str(org_id)).limit(1).execute()
        ).data or []
    except Exception:  # noqa: BLE001 — a lookup failure must not block the acknowledgment
        logger.warning("ciencia-pcen: could not read the support contact", exc_info=True)
        return None
    r = rows[0] if rows else {}
    if not (r.get("suporte_whatsapp") or r.get("suporte_email")):
        return None
    return {
        "nome": r.get("suporte_nome"),
        "email": r.get("suporte_email"),
        "whatsapp": r.get("suporte_whatsapp"),
    }


def registrar_ciencia_pcen(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    resultado_id: str,
    *,
    acao: str,
    user_id: Any,
    hoje: Optional[date] = None,
) -> dict:
    """`POST …/certidoes/resultados/{resultado_id}/ciencia-pcen`: record WHO
    acknowledged (or questioned) a Receita "positiva com efeitos de negativa"
    2ª via, WHEN, and for WHICH printed validity. Only valid while the
    exception actually applies and the certidão is still within validity —
    anything else is a 409, never a silent write."""
    hoje = hoje or date.today()
    ensure_cliente(client, org_id, cliente_id)
    _localizar(client, org_id, cliente_id, resultado_id)
    row = (
        _t(client, RESULTADOS).select("*").eq("org_id", str(org_id)).eq("id", resultado_id)
        .limit(1).execute()
    ).data[0]
    validade = _iso_para_data(row.get("validade_ate"))
    if not certidao_pcen.excecao_aplica(
        resultado=row.get("resultado"),
        segunda_via=certidao_pcen.e_segunda_via(row.get("api_response")),
        validade_ate=validade,
    ) or validade is None or validade < hoje:
        raise AppException(
            code="CIENCIA_PCEN_NAO_APLICAVEL",
            message="Esta certidão não exige ciência (não é uma 2ª via positiva com efeitos de negativa em vigor).",
            status_code=409,
        )
    agora = datetime.now(timezone.utc).isoformat()
    if acao == "entendi":
        patch = {
            "pcen_ciente_por": str(user_id), "pcen_ciente_em": agora,
            "pcen_ciente_validade": validade.isoformat(),
        }
    else:
        patch = {"pcen_duvida_por": str(user_id), "pcen_duvida_em": agora}
    _t(client, RESULTADOS).update(patch).eq("org_id", str(org_id)).eq("id", resultado_id).execute()
    logger.info("ciencia-pcen: resultado %s acao=%s por %s (validade %s)", resultado_id, acao, user_id, validade)
    return {
        "resultado_id": resultado_id,
        "acao": acao,
        "pcen": _bloco_pcen({**row, **patch}, validade, hoje),
        "suporte": _suporte_da_org(client, org_id),
    }


def definir_exigencias(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    exigir_certidoes_antigos: Optional[bool],
    exigir_crf_fgts: Optional[bool],
    atendimento_id: Optional[UUID],
) -> dict:
    """`PUT …/certidoes/exigencias` — owner decision 2026-10-21 (migration 295)."""
    ensure_cliente(client, org_id, cliente_id)
    alvo = _resolver_atendimento(client, org_id, cliente_id, atendimento_id, estrito=True)
    return {
        "atendimento_id": alvo,
        "exigencias": exig_svc.definir(
            client, org_id, alvo,
            exigir_certidoes_antigos=exigir_certidoes_antigos, exigir_crf_fgts=exigir_crf_fgts,
        ),
    }


def garantir_celula(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    kind: str,
    alvo_id: UUID,
    linha_chave: str,
    atendimento_id: Optional[UUID],
    user_id: Any,
) -> tuple[dict, bool]:
    """`POST …/certidoes/celulas` (CONTRACT §1.4) → `(body, criado)`: the
    existing winner's resultado, or a new manual-origin placeholder to upload
    onto through the EXISTING upload route.

    🔴 The placeholder is a CELL HOLDER, not a consulta in progress: a manual
    consulta (`origem='manual'`, `total_certidoes=1`) is never an InfoSimples
    job (`certidoes.service` refuses every API dispatch for it), the
    `/certidoes` list hides it until it carries evidence
    (`certidoes.service.ids_consultas_placeholder_vazio`), cancelling it is a
    no-op, and a legacy cancelled-empty one is revived here, not duplicated.

    No CPF/CNPJ required (F86): a party known only by name still gets its
    cell — the document is an InfoSimples parameter, and this consulta is
    never sent there (`_dados_consulta(exigir_documento=False)`)."""
    ensure_cliente(client, org_id, cliente_id)
    alvo = _resolver_atendimento(client, org_id, cliente_id, atendimento_id, estrito=True)
    partes = _todas_as_partes(client, org_id, cliente_id, alvo)
    parte = _achar_parte(partes, _exigir_kind(kind), str(alvo_id))
    linhas = montar_linhas(client, org_id, _titular_do(partes))
    linha = next((l for l in linhas if l["chave"] == linha_chave), None)
    if linha is None:
        raise AppException(
            code="LINHA_INVALIDA", message="Linha de certidão inválida.", status_code=422,
        )
    if not _aplicavel(linha, parte):
        raise AppException(
            code="CELULA_NAO_APLICAVEL",
            message="Esta certidão não se aplica a este tipo de parte.",
            status_code=422,
        )

    resultados = certidoes_svc.certidoes_por_alvos(
        client, org_id,
        cliente_ids=[parte["cliente_id"]] if parte["cliente_id"] else [],
        empresa_ids=[parte["empresa_id"]] if parte["empresa_id"] else [],
    ).get(_chave(parte), [])
    por_tipo, por_linha = indexar_vencedores(resultados)
    existente = por_linha.get(linha_chave) if linha["custom"] else por_tipo.get(linha_chave)
    if existente is not None:
        return {
            "resultado_id": existente["id"], "consulta_id": existente["consulta_id"],
            "criado": False,
        }, False

    # A cancelled empty placeholder of this very cell is revived rather than
    # duplicated (it lost the cell in `indexar_vencedores`).
    revivivel = next((
        r for r in resultados
        if _cancelado_vazio(r) and (
            r.get("linha_customizada_id") == linha["id"] if linha["custom"]
            else r.get("tipo") == linha_chave and not r.get("linha_customizada_id")
        )
    ), None)
    if revivivel is not None:
        client.table(RESULTADOS).update({"status": "pendente", "erro_mensagem": None}).eq(
            "id", revivivel["id"]
        ).execute()
        return {
            "resultado_id": revivivel["id"], "consulta_id": revivivel["consulta_id"],
            "criado": False,
        }, False

    if linha["custom"]:
        placeholder = {
            "tipo": CUSTOM_ROW_TIPO, "linha_customizada_id": linha["id"],
            "nome_display": linha["rotulo"],
            "ordem": _ORDEM_CUSTOM_BASE + int(linha["linha"].split(".")[1]),
        }
    else:
        config = MANUAL_CONFIG_BY_TIPO.get(linha_chave) or CONFIG_BY_TIPO[linha_chave]
        placeholder = {
            "tipo": config["tipo"], "nome_display": config["nome"], "ordem": config["ordem"],
        }
    consulta = client.table(CONSULTAS).insert({
        **_dados_consulta(client, org_id, parte, exigir_documento=False),
        **_vinculo(parte),
        "org_id": str(org_id),
        "created_by": str(user_id),
        "status": "pendente",
        "origem": "manual",
        "total_certidoes": 1,
        "concluidas": 0,
    }).execute().data
    if not consulta:
        raise AppException(code="INTERNAL_ERROR", message="Erro ao criar consulta", status_code=500)
    resultado = client.table(RESULTADOS).insert({
        **placeholder,
        "consulta_id": consulta[0]["id"], "org_id": str(org_id), "status": "pendente",
    }).execute().data
    if not resultado:
        raise AppException(code="INTERNAL_ERROR", message="Erro ao criar resultado", status_code=500)
    # The Serasa placeholder created here is the cell a Crednet uploaded
    # BEFORE it existed has nobody else to fill (same deferral
    # `_criar_consulta_automatica` closes): apply the reading on file now.
    if placeholder.get("tipo") == "serasa":
        certidoes_svc.aplicar_crednet_pendente(client, org_id, consulta[0])
    return {
        "resultado_id": resultado[0]["id"], "consulta_id": consulta[0]["id"], "criado": True,
    }, True


# ─── Cancel / retry / discard / download (the card is the only emission screen) ──


#: A resultado being produced by the pipeline right now.
_EM_VOO = ("processando", "na_fila")


def _cancelaveis(rows: list[dict]) -> list[dict]:
    """In-flight rows of AUTOMATIC consultas only. A manual consulta's
    `processando` is the read of a human's upload — cancelling it would throw
    the operator's file away; `pendente` rows are not cancellable either (about
    to start, or waiting on a credential a human must give)."""
    return [
        r for r in rows
        if r.get("status") in _EM_VOO and _emissao_automatica(r.get("tipo"), r)
    ]


def _cancelar(client: Any, org_id: UUID, rows: list[dict], cancelar: Callable[..., dict]) -> int:
    """One `cancelar_processamento` per consulta, narrowed to those rows."""
    por_consulta: dict[str, list[str]] = {}
    for r in rows:
        por_consulta.setdefault(r["consulta_id"], []).append(r["id"])
    return sum(
        cancelar(cid, str(org_id), client, resultado_ids=ids, statuses=_EM_VOO)["cancelados"]
        for cid, ids in por_consulta.items()
    )


def cancelar_emissao_da_parte(
    client: Any, org_id: UUID, cliente_id: UUID, kind: str, alvo_id: UUID,
    *, atendimento_id: Optional[UUID], cancelar: Callable[..., dict],
) -> dict:
    """`POST …/certidoes/partes/{kind}/{alvo_id}/cancelar`: stop every
    emission of the party that is running (`processando` / `na_fila`) —
    `certidoes.service.cancelar_processamento`, narrowed to those cells."""
    _exigir_kind(kind)
    ensure_cliente(client, org_id, cliente_id)
    alvo = _resolver_atendimento(client, org_id, cliente_id, atendimento_id, estrito=True)
    partes = _todas_as_partes(client, org_id, cliente_id, alvo)
    parte = _achar_parte(partes, kind, str(alvo_id))
    n = _cancelar(client, org_id, _cancelaveis(_resultados_da_parte(client, org_id, parte)), cancelar)
    return {"cancelados": n, "parte": _parte_montada(client, org_id, alvo, partes, parte)}


def cancelar_emissao_do_resultado(
    client: Any, org_id: UUID, cliente_id: UUID, resultado_id: str,
    *, cancelar: Callable[..., dict],
) -> dict:
    """`POST …/certidoes/resultados/{resultado_id}/cancelar` — one cell. 409
    when it is not an emission in progress (nothing to cancel is not a no-op
    the operator should be left guessing about)."""
    ensure_cliente(client, org_id, cliente_id)
    alvo, partes, parte, row = _localizar(client, org_id, cliente_id, resultado_id)
    if not _cancelaveis([row]):
        raise AppException(
            code="NAO_CANCELAVEL",
            message="Só dá para cancelar uma emissão automática em andamento.",
            status_code=409,
        )
    n = _cancelar(client, org_id, [row], cancelar)
    return {"cancelados": n, "parte": _parte_montada(client, org_id, alvo, partes, parte)}


def reemitir_com_erro(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    kind: str,
    alvo_id: UUID,
    *,
    atendimento_id: Optional[UUID],
    check_credentials: Callable[[str], list[str]],
    reprocessar: Callable[..., list[str]],
) -> dict:
    """`POST …/certidoes/partes/{kind}/{alvo_id}/reemitir-erros`: retry ONLY the
    party's FAILED automatic cells, in place — same consulta, `erro` ->
    `pendente` (TJSP -> `na_fila`), `certidoes.service.reprocessar_resultados`.
    Never a new consulta, never a cell that succeeded (those were paid for).
    A cell waiting on a credential (`pendencia`) is not a failure. The caller
    schedules `processar_consulta` for each id in `consultas`."""
    _exigir_kind(kind)
    ensure_cliente(client, org_id, cliente_id)
    alvo = _resolver_atendimento(client, org_id, cliente_id, atendimento_id, estrito=True)
    partes = _todas_as_partes(client, org_id, cliente_id, alvo)
    parte = _achar_parte(partes, kind, str(alvo_id))
    resultados = _resultados_da_parte(client, org_id, parte)
    por_tipo, _por_linha = indexar_vencedores(resultados)
    falhas = [
        r for r in por_tipo.values()
        if r.get("status") == "erro" and _emissao_automatica(r.get("tipo"), r)
        and not e_pendencia_de_credencial(r)
    ]
    # A failed re-emission hidden behind older valid evidence (F100) is a
    # failure to retry too — in place, on its own row.
    por_id = {r["id"]: r for r in resultados}
    falhas += [
        por_id[t["resultado_id"]]
        for t in ultimas_tentativas(resultados, por_tipo).values()
        if t["status"] == "erro" and t["resultado_id"] in por_id
    ]
    por_consulta: dict[str, list[str]] = {}
    for r in falhas:
        por_consulta.setdefault(r["consulta_id"], []).append(r["id"])
    if por_consulta:
        _preflight_credenciais(check_credentials, org_id)
    movidos: list[str] = []
    for cid, ids in por_consulta.items():
        movidos.extend(reprocessar(client, org_id, cid, ids))
    return {
        "reemitidos": len(movidos),
        "consultas": list(por_consulta),
        "tem_tjsp": any(r.get("tipo") == TJSP_TIPO and r["id"] in movidos for r in falhas),
        "parte": _parte_montada(client, org_id, alvo, partes, parte),
    }


def descartar_emissao(
    client: Any, org_id: UUID, cliente_id: UUID, resultado_id: str,
    *, user_id: Any, descartar: Callable[..., Optional[dict]],
) -> dict:
    """`DELETE …/certidoes/resultados/{resultado_id}`: throw away a wrong
    emission (soft-delete, restorable — `certidoes.service.soft_delete_
    resultado`) so the cell's previous evidence, or an empty cell, wins again.
    409 while it is still running (cancel first). Answers with the party as it
    reads afterwards."""
    ensure_cliente(client, org_id, cliente_id)
    alvo, partes, parte, row = _localizar(client, org_id, cliente_id, resultado_id)
    if row.get("status") in _EM_VOO:
        raise AppException(
            code="EMISSAO_EM_ANDAMENTO",
            message="Cancele a emissão em andamento antes de descartá-la.",
            status_code=409,
        )
    if descartar(client, org_id, resultado_id, user_id) is None:
        raise NotFoundError("Resultado")
    logger.info("certidoes: emissão descartada user_id=%s org_id=%s resultado_id=%s", user_id, org_id, resultado_id)
    return {"resultado_id": resultado_id, "parte": _parte_montada(client, org_id, alvo, partes, parte)}


def arquivos_da_parte(
    client: Any, org_id: UUID, cliente_id: UUID, kind: str, alvo_id: UUID,
    *, atendimento_id: Optional[UUID],
) -> tuple[dict, list[dict]]:
    """`(parte, items)` for `…/partes/{kind}/{alvo_id}/download-zip`: the PDF of
    each cell that currently WINS (what the grid shows), shaped for
    `certidoes.service.montar_zip`."""
    _exigir_kind(kind)
    ensure_cliente(client, org_id, cliente_id)
    alvo = _resolver_atendimento(client, org_id, cliente_id, atendimento_id, estrito=True)
    parte = _achar_parte(_todas_as_partes(client, org_id, cliente_id, alvo), kind, str(alvo_id))
    por_tipo, por_linha = indexar_vencedores(_resultados_da_parte(client, org_id, parte))
    vencedores = sorted(
        [*por_tipo.values(), *por_linha.values()], key=lambda r: (r.get("ordem") or 0, str(r.get("tipo")))
    )
    return parte, [
        {
            "arquivo_url": r["arquivo_url"], "arquivo_nome": r.get("arquivo_nome"),
            "nome_display": r.get("nome_display") or r.get("tipo") or "certidao",
        }
        for r in vencedores if r.get("arquivo_url")
    ]


# ─── Re-read every stored manual upload of the card ───────────────────────


def resultados_do_card(
    client: Any, org_id: UUID, cliente_id: UUID, *, atendimento_id: Optional[UUID]
) -> list[dict]:
    """Every live resultado of every party of the card's atendimento —
    titular, compradores, vendedores and the derived `EMP n` empresas — the
    whole history, not only each cell's winner (an older manual upload was
    read by the same outdated reader). De-duplicated by id."""
    ensure_cliente(client, org_id, cliente_id)
    alvo = _resolver_atendimento(client, org_id, cliente_id, atendimento_id, estrito=True)
    partes = _todas_as_partes(client, org_id, cliente_id, alvo)
    por_alvo = certidoes_svc.certidoes_por_alvos(
        client, org_id,
        cliente_ids=[p["cliente_id"] for p in partes if p["cliente_id"]],
        empresa_ids=[p["empresa_id"] for p in partes if p["empresa_id"]],
    )
    vistos: dict[str, dict] = {}
    for lista in por_alvo.values():
        for row in lista:
            vistos.setdefault(row["id"], row)
    return list(vistos.values())


async def reler_certidoes_do_card(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    atendimento_id: Optional[UUID],
    storage: Any,
    http_client: Any,
    preparar: Callable[..., Any],
    usuario_id: Any = None,
) -> tuple[dict, list[dict]]:
    """`POST …/certidoes/reler` → `(contagem, extracoes)`.

    For each resultado of the card (`resultados_do_card`): one with no stored
    PDF (`certidoes.service.pode_reler` — upload or live receipt) counts
    `sem_arquivo`; one already being read counts
    `em_andamento`; otherwise `preparar` (`certidoes.service.preparar_
    releitura` — validates, fetches the bytes, marks `processando`) and its
    `executar_releitura` kwargs join `extracoes`, which the caller
    schedules — one `BackgroundTasks` job each, run sequentially in order.
    A blob that is gone, or any unexpected failure on one row, counts `erros`
    (logged) and never stops the others.
    """
    contagem = {"relidos": 0, "sem_arquivo": 0, "em_andamento": 0, "erros": 0}
    extracoes: list[dict] = []
    for row in resultados_do_card(client, org_id, cliente_id, atendimento_id=atendimento_id):
        if not certidoes_svc.pode_reler(row):
            contagem["sem_arquivo"] += 1
            continue
        try:
            _marca, pdf_bytes = await preparar(
                row, org_id=str(org_id), db=client, storage=storage, http_client=http_client,
                usuario_id=usuario_id,
            )
        except certidoes_svc.ReleituraRecusada as exc:
            chave = "em_andamento" if exc.motivo == certidoes_svc.RELEITURA_EM_ANDAMENTO else "erros"
            if chave == "erros":
                logger.warning("reler-card: resultado %s recusado (%s)", row["id"], exc.motivo)
            contagem[chave] += 1
            continue
        except Exception:  # noqa: BLE001 — one row's failure must not sink the batch
            logger.error("reler-card: resultado %s falhou ao preparar", row["id"], exc_info=True)
            contagem["erros"] += 1
            continue
        extracoes.append(
            certidoes_svc.kwargs_extracao_releitura(row, pdf_bytes, str(org_id), client)
        )
        contagem["relidos"] += 1
    return contagem, extracoes

__all__ = [
    "arquivos_da_parte",
    "cancelar_emissao_da_parte",
    "cancelar_emissao_do_resultado",
    "descartar_emissao",
    "garantir_celula",
    "indexar_vencedores",
    "ultimas_tentativas",
    "max_dias",
    "montar",
    "montar_celula",
    "montar_linhas",
    "montar_parte",
    "reemitir",
    "reler_certidoes_do_card",
    "resultados_do_card",
    "registrar_ciencia_pcen",
    "reemitir_com_erro",
    "solicitar_emissao",
]
