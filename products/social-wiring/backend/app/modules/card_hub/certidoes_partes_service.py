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
from datetime import date
from typing import Any, Callable, Optional
from uuid import UUID

from noctusai_lib.integrations.documents.cpf import only_digits
from noctusai_lib.primitives.exceptions import AppException, NotFoundError

from app.modules.card_hub import partes_service
from app.modules.card_hub.certidoes_matriz_service import (
    _linha_customizada,
    _linha_fixa,
    _status_da_celula,
)
from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO
from app.modules.card_hub.empresas_service import listar as listar_empresas
from app.modules.card_hub.services import (
    AmbiguousAtendimento,
    ensure_cliente,
    resolve_atendimento_id_incluindo_partes,
)
from app.modules.certidoes import service as certidoes_svc
from app.modules.certidoes.service import MARCA_SEGUNDA_VIA
from app.modules.certidoes.matriz_custom_rows import (
    linhas_customizadas_ativas,
)
from app.modules.certidoes.registry import (
    CERTIDOES_CONFIG,
    CONFIG_BY_TIPO,
    CUSTOM_ROW_TIPO,
    MANUAL_CONFIG_BY_TIPO,
    MATRIZ_LINHAS,
    TJSP_TIPO,
    aplicavel_a_tipo_documento,
)
from app.services import table_reads

logger = logging.getLogger(__name__)

ATENDIMENTOS = "atendimentos"
PARTES = "atendimento_partes"
CLIENTES = "clientes"
CONSULTAS = certidoes_svc.CONSULTAS
RESULTADOS = certidoes_svc.RESULTADOS

KINDS = ("pessoa", "empresa")
_TOTAL_CHAVES = ("nao_constam", "constam", "pendente")
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


def _empresas_derivadas(
    client: Any, org_id: UUID, cliente_id: UUID, partes: list[dict]
) -> list[dict]:
    """The `EMP n` columns: the empresas the matriz already derives
    (`empresas_service.listar`, `exige_certidoes=True`) that are NOT already a
    PJ party — same filter as `certidoes_matriz_service.resolver_colunas`."""
    ja_parte = {p["empresa_id"] for p in partes if p.get("empresa_id")}
    out: list[dict] = []
    itens = listar_empresas(client, org_id, cliente_id).get("items", [])
    for item in itens:
        if not item.get("exige_certidoes"):
            continue
        emp = item["empresa"]
        if str(emp["id"]) in ja_parte:
            continue
        out.append({
            "parte_id": None, "titular": False, "lado": None, "papel": "",
            "tipo_pessoa": "PJ", "cliente_id": None, "empresa_id": str(emp["id"]),
            "nome": emp.get("razao_social") or emp.get("nome_fantasia") or "",
            "documento": _documento(emp.get("cnpj")),
        })
    for n, item in enumerate(out, start=1):
        item["rotulo"] = f"EMP {n}"
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


def indexar_vencedores(resultados: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    """`(por_tipo, por_linha_customizada)` — the winning resultado of each."""
    por_tipo: dict[str, dict] = {}
    por_linha: dict[str, dict] = {}
    for r in resultados:
        linha_id = r.get("linha_customizada_id")
        alvo, chave = (por_linha, linha_id) if linha_id else (por_tipo, r.get("tipo"))
        if not chave:
            continue
        atual = alvo.get(chave)
        if atual is None or _vencedor_chave(r) > _vencedor_chave(atual):
            alvo[chave] = r
    return por_tipo, por_linha


def _na(tipo: Optional[str]) -> dict:
    return {
        "status": "na", "texto": "N/A", "tipo": tipo,
        "resultado_id": None, "consulta_id": None, "status_processamento": None,
        "resultado": None, "numero": None, "emitida_em": None, "validade_ate": None,
        "idade_dias": None, "stale_para_contrato": False, "arquivo_url": None,
        "tem_arquivo": False, "arquivo_nome": None, "origem": None,
        "confirmado": False, "analise_ia": None, "erro_mensagem": None,
        "segunda_via": False,
    }


def _origem_da_celula(row: dict) -> Optional[str]:
    """`certidao_resultados.resultado_origem`, plus: a still-`pendente`,
    never-touched placeholder of a MANUAL consulta (migration 147 — nothing
    will ever process it) reads `"manual"` so the FE stops polling on it. Once
    an upload flips it to `processando` the origem is the resultado's own
    again (None until the read lands) and the FE polls as normal."""
    origem = row.get("resultado_origem")
    if origem:
        return origem
    if row.get("status") == "pendente" and row.get("consulta_origem") == "manual":
        return "manual"
    return None


def montar_celula(tipo: Optional[str], row: Optional[dict], hoje: date, limite: int) -> dict:
    status, texto = _status_da_celula(row)
    row = row or {}
    emitida = row.get("emitida_em")
    idade: Optional[int] = None
    if emitida:
        idade = (hoje - date.fromisoformat(str(emitida)[:10])).days
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
        "stale_para_contrato": idade is not None and idade >= limite,
        "arquivo_url": row.get("arquivo_url"),
        "tem_arquivo": bool(row.get("arquivo_url")),
        "arquivo_nome": row.get("arquivo_nome"),
        "origem": _origem_da_celula(row),
        "confirmado": row.get("confirmado_em") is not None,
        "analise_ia": row.get("analise_ia"),
        "erro_mensagem": row.get("erro_mensagem"),
        "segunda_via": _e_segunda_via(row),
    }


def _e_segunda_via(row: dict) -> bool:
    """The certidão is a 2ª via (the Receita refused a new one): its
    `emitida_em` is the ORIGINAL emission date, which is why it may read as
    stale. Read off the marker `certidoes.service` stamps into `api_response`."""
    resposta = row.get("api_response")
    return isinstance(resposta, dict) and bool(resposta.get(MARCA_SEGUNDA_VIA))


def _aplicavel(linha: dict, parte: dict) -> bool:
    """Owner rules unchanged from the matriz: FGTS is N/A on a PF, SERASA on a
    PJ, custom rows never N/A."""
    tipo = linha.get("tipo")
    if not tipo or tipo not in MANUAL_CONFIG_BY_TIPO:
        return True
    return aplicavel_a_tipo_documento(tipo, "cpf" if parte["tipo_pessoa"] == "PF" else "cnpj")


def montar_parte(
    parte: dict, linhas: list[dict], resultados: list[dict], hoje: date, limite: int
) -> dict:
    por_tipo, por_linha = indexar_vencedores(resultados)
    celulas: dict[str, dict] = {}
    totais = {**{k: 0 for k in _TOTAL_CHAVES}, "vencidas": 0}
    for linha in linhas:
        chave = linha["chave"]
        if not _aplicavel(linha, parte):
            celulas[chave] = _na(linha.get("tipo"))
            continue
        row = por_linha.get(chave) if linha["custom"] else por_tipo.get(chave)
        celula = montar_celula(linha.get("tipo"), row, hoje, limite)
        celulas[chave] = celula
        totais[celula["status"]] += 1
        if celula["stale_para_contrato"]:
            totais["vencidas"] += 1
    return {
        "chave": _chave(parte),
        "kind": _kind(parte),
        "tipo_pessoa": parte["tipo_pessoa"],
        "rotulo": parte["rotulo"],
        "lado": parte["lado"],
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
    }


def _todas_as_partes(
    client: Any, org_id: UUID, cliente_id: UUID, atendimento_id: str
) -> list[dict]:
    _alvo, partes = partes_service.listar_partes(
        client, org_id, cliente_id, atendimento_id=UUID(str(atendimento_id))
    )
    return partes + _empresas_derivadas(client, org_id, cliente_id, partes)


def _titular_do(partes: list[dict]) -> str:
    return next(p["cliente_id"] for p in partes if p["titular"])


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
    return {
        "atendimento_id": alvo,
        "data_referencia": hoje.isoformat(),
        "max_dias": limite,
        "linhas": linhas,
        "partes": [
            montar_parte(p, linhas, resultados.get(_chave(p), []), hoje, limite)
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


def _dados_consulta(client: Any, org_id: UUID, parte: dict) -> dict:
    """The party-identifying columns of a new consulta. `data_nascimento` /
    `genero` / `rg` / `nome_mae` are copied off the cliente when present — the
    same fields `ConsultaCreate` takes (CND Federal needs the birthdate)."""
    documento = parte.get("documento")
    esperado = 11 if parte["tipo_pessoa"] == "PF" else 14
    if not documento or len(documento) != esperado:
        raise AppException(
            code="DOCUMENTO_AUSENTE",
            message="Informe o CPF/CNPJ da parte antes de solicitar certidões.",
            status_code=422,
        )
    dados: dict[str, Any] = {
        "tipo_documento": "cpf" if parte["tipo_pessoa"] == "PF" else "cnpj",
        "documento": documento,
        "nome": parte["nome"] or documento,
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
    parte = _achar_parte(_todas_as_partes(client, org_id, cliente_id, alvo), kind, str(alvo_id))

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


def _partes_do_card(client: Any, org_id: UUID, cliente_id: UUID) -> list[list[dict]]:
    """The party lists of the card's atendimento — or, when it is ambiguous,
    of every candidate (a body-less `reemitir` has no `atendimento_id` to say
    which)."""
    try:
        alvo = resolve_atendimento_id_incluindo_partes(client, org_id, cliente_id)
        candidatos = [alvo]
    except AmbiguousAtendimento as exc:
        candidatos = list(exc.candidates)
    return [_todas_as_partes(client, org_id, cliente_id, a) for a in candidatos]


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
    onto through the EXISTING upload route."""
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
        **_dados_consulta(client, org_id, parte),
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
    return {
        "resultado_id": resultado[0]["id"], "consulta_id": consulta[0]["id"], "criado": True,
    }, True


__all__ = [
    "garantir_celula",
    "indexar_vencedores",
    "max_dias",
    "montar",
    "montar_celula",
    "montar_linhas",
    "montar_parte",
    "reemitir",
    "solicitar_emissao",
]
