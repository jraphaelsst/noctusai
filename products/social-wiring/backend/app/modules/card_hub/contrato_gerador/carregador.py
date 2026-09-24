"""Read `DadosContrato` through the EXISTING services — no duplicated queries.

| Data                          | Service                                              |
|-------------------------------|------------------------------------------------------|
| contract row (404 contract)   | `contratos_service.exigir_contrato`                  |
| titular + partes by lado      | `services.ensure_cliente`, `compradores_service.listar` |
| qualificação gate per person  | `documento_checklist_service.completude_contratual`  |
| certidões per parte           | `certidoes.service.certidoes_por_parte`              |
| certidões do titular (116)    | `certidoes.service.certidoes_por_cliente`            |
| negociação / parcelas / termos| `negociacao_service.obter`, `negociacao_estruturada_service.obter_estruturada` |
| financiamento                 | `financiamento_service.obter`                        |
| imóvel address                | `imovel_hub.busca_service.enriquecer`                |
| imóvel matrícula/ônus/título  | `imovel_hub.dados_service.obter`                     |
| imóvel certidões (118)        | `imovel_hub.documentos_service.certidoes`            |
| última transferência (115/152)| `matriculas.titulo_service.antigos_proprietarios`    |
| matrícula literal text        | `matriculas.estrutura_service.obter_selecao` (logs the text read) |
| ônus source acts (kind/nº)    | `matriculas.estrutura_service.listar_atos` (logs the text read)   |
| permuta ativos (114)          | `permuta_ativos` rows via `table_reads.in_batched_rows` |
| org cadastral + testemunhas   | `settings_router.get_dados_imobiliaria` / `list_testemunhas`      |

Services are called DIRECTLY (Python), never over HTTP — one request, one
transaction-shaped read, and no self-call that would need a token.

🔴 LGPD: the matrícula reads append a `text_view` access row, and the
última-compra-e-venda read a `detalhes_view` row, for the requesting user —
the generator reads the CPF-bearing transcription and its typed details on
their behalf, exactly as the selection panel does.

🔴 THIS MODULE NEVER FORMATS AND NEVER INVENTS. It carries values across
(coercing only types: ISO string -> `date`, numeric string -> `Decimal`).
Wording belongs to `frases`/`contexto`; a value nobody entered stays None so
`derivacao` can NAME it. That is why there is no `or ""` anywhere below.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Optional
from uuid import UUID

from noctusai_lib.integrations.documents.formatting import ranges_from_json

from app.modules.card_hub import compradores_service as compradores_svc
from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub import documento_checklist_service as checklist_svc
from app.modules.card_hub import financiamento_service
from app.modules.card_hub import negociacao_estruturada_service as estruturada_svc
from app.modules.card_hub import negociacao_service
from app.modules.card_hub import services as svc
from app.modules.card_hub.contrato_gerador import derivacao
from app.modules.card_hub.contrato_gerador.dados import (
    AtoCitado,
    Certidao,
    CertidaoImovel,
    DadosContrato,
    Empresa,
    Endereco,
    Favorecido,
    Financiamento,
    Imobiliaria,
    Imovel,
    Intermediario,
    Matricula,
    Parcela,
    PermutaImovel,
    Pessoa,
    Termos,
    Testemunha,
    signatarios,
)
from app.modules.certidoes import service as certidoes_svc
from app.modules.imovel_hub import busca_service, dados_service
from app.modules.imovel_hub import documentos_service as imovel_docs_svc
from app.modules.matriculas import estrutura_service, titulo_service
from app.services import table_reads

#: `permuta_ativos`' own address snapshot (migration 101) — bare column names,
#: same spelling the `imoveis` mirror uses, so ONE `_endereco` call reads either.
_CAMPOS_ENDERECO = ("logradouro", "numero", "complemento", "bairro", "cidade", "uf", "cep")


def _data(valor: Any) -> Optional[date]:
    if not valor:
        return None
    return date.fromisoformat(str(valor)[:10])


def _dec(valor: Any) -> Optional[Decimal]:
    if valor is None or valor == "":
        return None
    return Decimal(str(valor))


def _int(valor: Any) -> Optional[int]:
    if valor is None or valor == "":
        return None
    return int(valor)


def _id(valor: Any) -> Optional[str]:
    return str(valor) if valor else None


def _endereco(fonte: dict, prefixo: str = "endereco_") -> Endereco:
    return Endereco(
        logradouro=fonte.get(f"{prefixo}logradouro"),
        numero=fonte.get(f"{prefixo}numero"),
        complemento=fonte.get(f"{prefixo}complemento"),
        bairro=fonte.get(f"{prefixo}bairro"),
        cidade=fonte.get(f"{prefixo}cidade"),
        uf=fonte.get(f"{prefixo}uf"),
        cep=fonte.get(f"{prefixo}cep"),
    )


def _certidao(r: dict) -> Certidao:
    return Certidao(
        tipo=r["tipo"],
        resultado=r.get("resultado"),
        numero=r.get("numero"),
        emitida_em=_data(r.get("emitida_em")),
        validade_ate=_data(r.get("validade_ate")),
        consulta_tipo_documento=r.get("consulta_tipo_documento") or "cpf",
        consulta_nome=r.get("consulta_nome"),
        consulta_documento=r.get("consulta_documento"),
        # Migration 116 — the CNPJ/CPF's registration state, denormalised onto
        # each resultado by `_resultados_das_consultas`.
        consulta_situacao_cadastral=r.get("consulta_situacao_cadastral"),
        consulta_data_situacao=_data(r.get("consulta_data_situacao")),
    )


def _certidoes_da_empresa(client: Any, org_id: UUID, empresa_id: str) -> list[dict]:
    """Isolates the call into S2a's `certidoes.service.certidoes_por_empresa`
    (contract §E, migration 167) — mirrors `certidoes_por_cliente`'s per-
    entity shape (`app/modules/certidoes/service.py:2651-2676`). 🔴 S2b
    does NOT own `certidoes/service.py`: this ONE wrapper is the seam S2a
    integration wires — when `certidoes_por_empresa` is not yet defined
    there (a worktree that has not merged S2a), calling it raises
    `AttributeError`, which only happens when a deal actually HAS
    `cliente_empresa_participacoes` rows (never on the sparse/synthetic
    fixtures this suite exercises today)."""
    return certidoes_svc.certidoes_por_empresa(client, org_id, empresa_id)


def _empresas(
    client: Any, org_id: UUID, certificando_ids: Iterable[str], pessoas_por_id: dict[str, Pessoa]
) -> list[Empresa]:
    """[E1/E3/E4/E6] The DISTINCT companies (migration 167) a certificando
    holds a Crednet participação in — `cliente_empresa_participacoes` ->
    `empresas`, read directly off the tables (contract §A) rather than
    through S2a's `empresas_service` (not this loader's to own, and not
    guaranteed to exist yet), so this keeps working before that slice
    integrates. `pessoas_por_id` resolves each participação's owner to the
    already-loaded vendedor/comprador `Pessoa` — a cônjuge holding a
    participação who is not otherwise a card party has no `Pessoa` here and
    is excluded from `owners`, but NEVER silently: `derivacao._conjuges_
    sem_pessoa`/`conferir_conjuges_ausentes` (E3) name it as a `faltando`
    off `d.vendedores`/`d.compradores` alone, independent of whether this
    loader ever reaches their empresa at all (S2a's `/empresas` endpoint,
    which loads every parte including bare cônjuges, is the fuller
    picture)."""
    ids = sorted({str(i) for i in certificando_ids if i})
    if not ids:
        return []
    participacoes = table_reads.in_batched_rows(
        client, "cliente_empresa_participacoes", org_id, "cliente_id", ids
    )
    if not participacoes:
        return []
    por_empresa: dict[str, list[dict]] = {}
    for row in participacoes:
        por_empresa.setdefault(str(row["empresa_id"]), []).append(row)
    linhas_empresa = _rows_por_id_generico(client, org_id, "empresas", list(por_empresa))
    saida: list[Empresa] = []
    for empresa_id, participantes in por_empresa.items():
        row = linhas_empresa.get(empresa_id)
        if row is None:
            continue
        donos = [
            pessoas_por_id[str(r["cliente_id"])]
            for r in participantes
            if str(r["cliente_id"]) in pessoas_por_id
        ]
        if not donos:
            continue
        saida.append(
            Empresa(
                id=empresa_id,
                cnpj=row.get("cnpj") or "",
                razao_social=row.get("razao_social"),
                situacao_cadastral=row.get("situacao_cadastral"),
                data_situacao_cadastral=_data(row.get("data_situacao_cadastral")),
                dados_origem=row.get("dados_origem"),
                dados_confirmado_em=_data(row.get("dados_confirmado_em")),
                owners=donos,
                certidoes=[_certidao(r) for r in _certidoes_da_empresa(client, org_id, empresa_id)],
            )
        )
    return saida


def _rows_por_id_generico(client: Any, org_id: UUID, tabela: str, ids: list[str]) -> dict[str, dict]:
    return {
        str(r["id"]): r
        for r in table_reads.in_batched_rows(client, tabela, org_id, "id", ids)
    }


def _pessoa(
    client: Any, org_id: UUID, cliente_id: str, lado: str, papel: str, parte_id: Optional[str]
) -> Pessoa:
    row = svc.ensure_cliente(client, org_id, UUID(cliente_id))
    completude = checklist_svc.completude_contratual(client, org_id, UUID(cliente_id))
    # Migration 116 closed spec §6.1 #18. A parte's certidões stay DEAL-scoped
    # (`atendimento_parte_id`); the TITULAR has no parte row at all, and
    # `certidoes_por_cliente` is what 116 added to reach them.
    brutas = (
        certidoes_svc.certidoes_por_parte(client, org_id, parte_id)
        if parte_id
        else certidoes_svc.certidoes_por_cliente(client, org_id, cliente_id)
    )
    # Migration 117 — the document's OWN emission date, not its upload date.
    certidao_ec = completude.get("certidao_estado_civil") or {}
    return Pessoa(
        cliente_id=cliente_id,
        lado=lado,
        papel=papel,
        parte_id=parte_id,
        nome=row.get("nome_oficial"),
        nome_cadastro=row.get("nome"),
        nacionalidade=row.get("nacionalidade"),
        genero=row.get("genero"),
        # The canonical token (legacy "Casado(a)" mapped) — completude's reading.
        estado_civil=completude.get("estado_civil"),
        regime_bens=row.get("regime_bens"),
        profissao=row.get("profissao"),
        cpf=row.get("cpf"),
        rg=row.get("rg"),
        rg_orgao=row.get("rg_orgao_expedidor"),
        email=row.get("email"),
        endereco=_endereco(row),
        conjuge_cliente_id=_id(row.get("conjuge_cliente_id")),
        data_casamento=_data(row.get("data_casamento")),
        certidao_estado_civil_emitida_em=_data(certidao_ec.get("emitida_em")),
        faltando_qualificacao=list(completude.get("faltando") or []),
        certidoes=[_certidao(r) for r in brutas],
    )


def _endereco_manual(catalogo: dict, dados: dict) -> Endereco:
    """The imóvel's address for the contract — THE property table (owner
    rule, 2026-09-23): a manual override (migration 149, widened by 159)
    wins PER-FIELD over the CRM/Vista mirror for all 7 `Endereco` fields.
    149 shipped only the 4 `derivacao._imovel` gates the contract on
    (logradouro/número/cidade/UF); 159 extends the same per-field-override
    shape to complemento/bairro/CEP, so a condo UNIT's own address (e.g.
    "Alameda Alemanha, 535") can win over the mirror's GATE address (e.g.
    "Itália, 343, compl. 535") when Vista mirrors only the building's
    entrance. This product has no write-back to Vista (see `dados_service.
    CAMPOS_ENDERECO_MANUAL`'s docstring), so the override is the only
    correction path."""
    base = _endereco(catalogo, prefixo="")
    return Endereco(
        logradouro=dados.get("endereco_manual_logradouro") or base.logradouro,
        numero=dados.get("endereco_manual_numero") or base.numero,
        complemento=dados.get("endereco_manual_complemento") or base.complemento,
        bairro=dados.get("endereco_manual_bairro") or base.bairro,
        cidade=dados.get("endereco_manual_cidade") or base.cidade,
        uf=dados.get("endereco_manual_uf") or base.uf,
        cep=dados.get("endereco_manual_cep") or base.cep,
    )


def _empreendimento(catalogo: dict, dados: dict) -> Optional[str]:
    """The development/condomínio name `titulo_curto` prefixes onto the
    address (migration 158): the operator-authored override
    (`imovel_dados.empreendimento_manual`) wins when set, falling back to
    the CRM/Vista mirror's own `empreendimento` otherwise. A manually
    registered imóvel (migration 149) has NO mirror row at all, so without
    the override `catalogo` is `{}` and this is unconditionally `None` —
    exactly the gap this migration closes. `titulo_curto` itself
    (`contexto.py`) is unchanged: it already prints `empreendimento` when
    present and falls through to the address alone when it is not."""
    return dados.get("empreendimento_manual") or catalogo.get("empreendimento")


def _imovel(client: Any, org_id: UUID, codigo: str, usuario_id: Optional[Any]) -> Imovel:
    canonico = busca_service.canonical(codigo)
    catalogo = busca_service.enriquecer(client, org_id, [codigo]).get(canonico) or {}
    dados = dados_service.obter(client, org_id, codigo)

    atos: list[AtoCitado] = []
    fonte_onus = dados.get("onus_fonte")
    if fonte_onus and fonte_onus.get("atos"):
        extracao = estrutura_service.listar_atos(
            client, org_id, UUID(str(fonte_onus["extracao_id"])), usuario_id=usuario_id
        )
        por_id = {str(a["id"]): a for a in extracao["atos"]}
        for citado in fonte_onus["atos"]:
            ato = por_id.get(str(citado.get("ato_id")))
            if ato is not None:
                atos.append(AtoCitado(kind=ato["kind"], numero=ato.get("numero")))

    # Migration 115/152. Only `data_registro` + `transmitentes` + `sem_
    # registro` are read: the service's own `exige_certidoes` is computed
    # against TODAY, while the contract's [Q9] rule runs against the
    # ASSINATURA date — `derivacao` recomputes it there rather than
    # inheriting a differently-dated answer.
    antigos = titulo_service.antigos_proprietarios(client, org_id, codigo, usuario_id=usuario_id)
    ultima = antigos.get("ultima_transferencia") or {}

    fonte_titulo = dados.get("titulo_aquisitivo_fonte") or {}
    return Imovel(
        codigo=codigo,
        titulo=catalogo.get("titulo"),
        # Migration 158 — the authored override wins over the mirror; see
        # `_empreendimento`'s docstring for why a manually registered imóvel
        # needs this at all.
        empreendimento=_empreendimento(catalogo, dados),
        endereco=_endereco_manual(catalogo, dados),
        # Migration 093 — the CRM/Vista mirror's own m², used only by the
        # `derivacao` coherence check (never printed) — see `dados.Imovel
        # .area_total`'s docstring.
        area_total=_dec(catalogo.get("area_total")),
        numero_matricula=dados.get("numero_matricula"),
        numero_registro_imoveis=dados.get("numero_registro_imoveis"),
        inscricao_municipal=dados.get("prefeitura_cadastro_imobiliario"),
        situacao_onus=dados.get("situacao_onus"),
        onus_certidao_em=_data(dados.get("onus_certidao_em")),
        onus_fonte_atos=atos,
        titulo_aquisitivo_confirmado=bool(fonte_titulo.get("confirmado_em")),
        # Migration 115 — the operator's CONFIRMED wording, never the suggestion.
        titulo_aquisitivo_texto=dados.get("titulo_aquisitivo_texto"),
        onus_credor=dados.get("onus_credor"),
        # Migration 139 — the operator-confirmed OVERRIDE for the posse
        # clause's address (an escape hatch; `derivacao.resolver_endereco_
        # posse` derives from the matrícula when this is unset).
        endereco_registro_texto=dados.get("endereco_registro_texto"),
        ultima_transferencia_em=_data(ultima.get("data_registro")),
        ultima_transferencia_transmitentes=tuple(
            t["nome"] for t in antigos.get("transmitentes") or [] if t.get("nome")
        ),
        ultima_transferencia_sem_registro_confirmado=bool(antigos.get("sem_registro")),
        # Migration 118 — the imóvel's own CND / matrícula certidões.
        certidoes=tuple(
            CertidaoImovel(
                tipo=i["tipo"],
                numero=i.get("numero"),
                emitida_em=_data(i.get("emitida_em")),
                validade_ate=_data(i.get("validade_ate")),
                resultado=i.get("resultado"),
                inscricao_imobiliaria=i.get("inscricao_imobiliaria"),
                confirmado=bool(i.get("confirmado")),
            )
            for i in imovel_docs_svc.certidoes(client, org_id, codigo)["items"]
        ),
    )


def _permuta_imoveis(
    client: Any,
    org_id: UUID,
    ativo_ids: Iterable[str],
    selecao: dict,
) -> list[PermutaImovel]:
    """One `PermutaImovel` per ativo the permuta parcela is paid with, in link
    order (migration 114), each carrying ITS OWN matrícula quote —
    `obter_selecao()['permutas']`, keyed by `permuta_ativo_id` (migration 115's
    `papel='permuta'`). That keying IS the per-imóvel act role: a contract
    swapping two matrículas quotes each under its own ativo."""
    ids = [str(a) for a in ativo_ids]
    if not ids:
        return []
    citacoes = {str(p["permuta_ativo_id"]): p for p in selecao.get("permutas") or []}
    ativos = {
        str(r["id"]): r
        for r in table_reads.in_batched_rows(client, "permuta_ativos", org_id, "id", ids)
    }

    saida: list[PermutaImovel] = []
    for ativo_id in ids:
        ativo = ativos.get(ativo_id) or {}
        citacao = citacoes.get(ativo_id) or {}
        codigo = ativo.get("imovel_codigo")
        imovel_dados: dict = {}
        catalogo: dict = {}
        if codigo:
            imovel_dados = dados_service.obter(client, org_id, codigo)
            catalogo = (
                busca_service.enriquecer(client, org_id, [codigo]).get(
                    busca_service.canonical(codigo)
                )
                or {}
            )
        # The catalog imóvel answers when it holds the field; otherwise the
        # ativo's own snapshot does. A permuta ativo is often NOT a catalog
        # listing (migration 101 carries its profile for exactly that case),
        # and a registered-but-empty mirror row must not blank the address.
        fonte_endereco = {
            **{campo: ativo.get(campo) for campo in _CAMPOS_ENDERECO},
            **{campo: catalogo[campo] for campo in _CAMPOS_ENDERECO if catalogo.get(campo)},
        }
        texto = (citacao.get("texto") or "").strip()
        # Migration 136 — the SAME narrowing the OBJETO clause gets
        # (`selecao["descricao_imovel"]`, computed by `_citacao` for every
        # group including permutas). `contexto.py` is where the "prefer
        # this, else fall back to `texto` above and log it" decision lives
        # — this module only carries the value across, never decides.
        descricao_imovel_texto = ((citacao.get("descricao_imovel") or {}).get("texto") or "").strip()
        saida.append(
            PermutaImovel(
                permuta_ativo_id=ativo_id,
                descricao_matricula=texto or None,
                descricao_imovel_texto=descricao_imovel_texto or None,
                endereco=_endereco(fonte_endereco, prefixo=""),
                inscricao_municipal=imovel_dados.get("prefeitura_cadastro_imobiliario"),
                matricula_numero=imovel_dados.get("numero_matricula"),
                cartorio=imovel_dados.get("numero_registro_imoveis"),
                num_atos=len(citacao.get("atos") or []),
                # Migration 139 — same operator-confirmed OVERRIDE as
                # `Imovel.endereco_registro_texto`. Only reachable when this
                # ativo IS a catalog imóvel (`codigo` set, same guard the
                # rest of this row's `imovel_dados` reads already use); an
                # ativo with no catalog code has no `imovel_dados` row to
                # confirm an override in, so it always derives.
                endereco_registro_texto=imovel_dados.get("endereco_registro_texto"),
            )
        )
    return saida


def _termos(bruto: dict) -> Termos:
    """`atendimento_negociacao_termos` (114) as read. `ad_corpus` stays
    TRI-STATE: None = never answered (an aviso), False = answered "not ad
    corpus" (the expression is omitted) — collapsing them would silently turn
    an unanswered question into an answer."""
    return Termos(
        posse_prazo_dias=_int(bruto.get("posse_prazo_dias")),
        posse_marco=bruto.get("posse_marco"),
        posse_marco_parcela_id=_id(bruto.get("posse_marco_parcela_id")),
        permuta_posse_prazo_dias=_int(bruto.get("permuta_posse_prazo_dias")),
        permuta_posse_marco=bruto.get("permuta_posse_marco"),
        permuta_posse_marco_parcela_id=_id(bruto.get("permuta_posse_marco_parcela_id")),
        permuta_obrigacoes_entrega=bruto.get("permuta_obrigacoes_entrega"),
        itens_integrantes=bruto.get("itens_integrantes"),
        itens_integrantes_ausente_confirmado=bool(bruto.get("itens_integrantes_ausente_confirmado")),
        ad_corpus=bruto.get("ad_corpus"),
        obrigacoes_vendedor=bruto.get("obrigacoes_vendedor"),
        onus_quitacao=bruto.get("onus_quitacao"),
        onus_prazo_dias=_int(bruto.get("onus_prazo_dias")),
        confissao_juros_am=_dec(bruto.get("confissao_juros_am")),
        confissao_garantia=bruto.get("confissao_garantia"),
        corretagem_contratantes=bruto.get("corretagem_contratantes"),
        corretagem_num_parcelas=_int(bruto.get("corretagem_num_parcelas")),
    )


def _imobiliaria(client: Any, org_id: UUID) -> tuple[Imobiliaria, list[Testemunha]]:
    # Imported here, not at module top: `settings_router` pulls in the whole
    # settings surface and card_hub must not import it at app assembly time.
    from app.routers import settings_router

    auth = (None, None, str(org_id))
    org = settings_router.get_dados_imobiliaria(auth, client)
    testemunhas = settings_router.list_testemunhas(auth, client)["items"]
    return (
        Imobiliaria(
            razao_social=org.get("razao_social"),
            nome_fantasia=org.get("nome_fantasia"),
            cnpj=org.get("cnpj"),
            creci_pj=org.get("creci_pj"),
            responsavel_nome=org.get("responsavel_nome"),
            responsavel_creci=org.get("responsavel_creci"),
            email=org.get("email"),
            endereco=_endereco(org),
            # Migration 117 — the office's own operational answers.
            posse_multa_diaria=_dec(org.get("posse_multa_diaria")),
            plataforma_assinatura_nome=org.get("plataforma_assinatura_nome"),
            plataforma_assinatura_url=org.get("plataforma_assinatura_url"),
            prazo_pendencias_padrao_dias=_int(org.get("prazo_pendencias_padrao_dias")),
        ),
        [
            Testemunha(nome=t.get("nome"), rg=t.get("rg"), cpf=t.get("cpf"), email=t.get("email"))
            for t in testemunhas
        ],
    )


def carregar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    *,
    usuario_id: Optional[Any],
) -> tuple[DadosContrato, UUID]:
    """Returns (dados, atendimento_id). 404 (NotFoundError) for a deleted or
    foreign contract, before anything else is read."""
    atendimento_id = UUID(str(svc.resolve_atendimento_id(client, org_id, cliente_id)))
    contrato = contratos_svc.exigir_contrato(client, org_id, atendimento_id, contrato_id)

    # The titular IS a comprador (compradores_service's module docstring) and
    # has no atendimento_partes row, hence no parte_id.
    compradores = [_pessoa(client, org_id, str(cliente_id), "comprador", "comprador", None)]
    vendedores: list[Pessoa] = []
    for lado, destino in (("comprador", compradores), ("vendedor", vendedores)):
        partes = compradores_svc.listar(
            client, org_id, cliente_id, atendimento_id=atendimento_id, lado=lado
        )["items"]
        for parte in partes:
            destino.append(
                _pessoa(client, org_id, str(parte["cliente_id"]), lado, parte["papel"], str(parte["id"]))
            )

    negociacao = negociacao_service.obter(client, org_id, cliente_id)
    estruturada = estruturada_svc.obter_estruturada(client, org_id, cliente_id)
    financiamento = financiamento_service.obter(client, org_id, cliente_id)
    codigo = negociacao.get("imovel_codigo")
    imovel = _imovel(client, org_id, codigo, usuario_id) if codigo else None
    selecao = estrutura_service.obter_selecao(client, org_id, contrato_id, usuario_id=usuario_id)
    # [Owner directive, 2026-09-23] The DA ELEIÇÃO DO FORO comarca, read off
    # THIS matrícula's own FULL transcription — independent of which acts
    # the operator selected to quote (`selecao["extracao_id"]` alone is
    # enough; `selecao["texto"]` can legitimately still be empty).
    comarca = (
        derivacao.comarca_de_texto(
            estrutura_service.texto_da_extracao(client, org_id, selecao["extracao_id"])
        )
        if selecao.get("extracao_id")
        else None
    )
    imobiliaria, testemunhas = _imobiliaria(client, org_id)

    parcelas = [
        Parcela(
            id=str(p["id"]),
            tipo=p["tipo"],
            valor=_dec(p.get("valor")),
            vencimento=_data(p.get("vencimento")),
            evento=p.get("evento"),
            forma_pagamento=p.get("forma_pagamento"),
            favorecido_id=_id(p.get("favorecido_id")),
            confissao_divida=bool(p.get("confissao_divida")),
            ordem=int(p.get("ordem") or 0),
            # Migration 114.
            dispara_corretagem=bool(p.get("dispara_corretagem")),
            permuta_ativo_ids=tuple(str(a) for a in p.get("permuta_ativo_ids") or ()),
        )
        for p in estruturada.get("parcelas") or []
    ]
    # 🔴 Permuta is the `tipo='permuta'` PARCELA (114) — not the legacy
    # `atendimento_negociacao.permuta_ativo_id`, which held ONE asset and
    # which `negociacao_estruturada_service` marks superseded.
    permutas = [p for p in parcelas if p.tipo == "permuta"]
    ativos_permuta = [a for p in permutas for a in p.permuta_ativo_ids]

    # [E1/E3/E6] Certificandos: signing vendedores + their cônjuges, plus
    # signing compradores + cônjuges only in a permuta (a comprador giving
    # an imóvel gets exactly the vendedor treatment).
    certificandos = signatarios(vendedores)
    certificando_ids = {p.cliente_id for p in certificandos}
    certificando_ids |= {p.conjuge_cliente_id for p in certificandos if p.conjuge_cliente_id}
    if permutas:
        comp_certificandos = signatarios(compradores)
        certificando_ids |= {p.cliente_id for p in comp_certificandos}
        certificando_ids |= {p.conjuge_cliente_id for p in comp_certificandos if p.conjuge_cliente_id}
    pessoas_por_id = {p.cliente_id: p for p in vendedores + compradores}
    empresas = _empresas(client, org_id, certificando_ids, pessoas_por_id)

    dados = DadosContrato(
        contrato_id=str(contrato_id),
        cliente_id=str(cliente_id),
        modelo=contrato["modelo"],
        vendedores=vendedores,
        compradores=compradores,
        imovel=imovel,
        matricula=Matricula(
            codigo=selecao.get("codigo"),
            texto=selecao.get("texto") or "",
            num_atos=len(selecao.get("atos") or []),
            formatacao=ranges_from_json(selecao.get("formatacao")),
            # Migration 136 — `None` (no `descricao_imovel` block for this
            # extraction) reads as `None` through both fields; `contexto.py`
            # is the one place that decides the fallback.
            descricao_imovel_texto=(selecao.get("descricao_imovel") or {}).get("texto"),
            descricao_imovel_formatacao=ranges_from_json(
                (selecao.get("descricao_imovel") or {}).get("formatacao")
            ),
            comarca=comarca,
        ),
        valor_negociado=_dec(estruturada.get("valor_negociado")),
        pct_comissao=_dec(negociacao.get("pct_comissao")),
        parcelas=parcelas,
        favorecidos=[
            Favorecido(
                id=str(f["id"]), nome=f["nome"], cpf_cnpj=f.get("cpf_cnpj"), banco=f.get("banco"),
                agencia=f.get("agencia"), conta=f.get("conta"), pix=f.get("pix"),
            )
            for f in estruturada.get("favorecidos") or []
        ],
        intermediarios=[
            Intermediario(
                id=str(i["id"]), corretor_id=i.get("corretor_id"), nome=i["nome"], creci=i.get("creci"),
                tipo=i.get("tipo") or "percentual", valor=_dec(i.get("valor")),
                # Migration 114 — the favorecido link + PF/PJ qualification.
                favorecido_id=_id(i.get("favorecido_id")),
                pessoa_tipo=i.get("pessoa_tipo"),
                documento=i.get("documento"),
                email=i.get("email"),
                endereco=_endereco(i),
                representante_nome=i.get("representante_nome"),
                representante_cpf=i.get("representante_cpf"),
                # Migration 162 — old rows read as the table's original,
                # only-ever meaning: a qualified, CRECI-required party.
                natureza=i.get("natureza") or "intermediario",
                papel=i.get("papel"),
            )
            for i in estruturada.get("intermediarios") or []
        ],
        financiamento=Financiamento(
            existe=bool(financiamento.get("existe")),
            situacao=financiamento.get("situacao") or "pendente",
            fgts=bool(financiamento.get("fgts")),
        ),
        imobiliaria=imobiliaria,
        testemunhas=testemunhas,
        termos=_termos(estruturada.get("termos") or {}),
        permuta_imoveis=_permuta_imoveis(client, org_id, ativos_permuta, selecao),
        empresas=empresas,
        # Migration 114.
        prazo_pendencias_dias=_int(contrato.get("prazo_pendencias_dias")),
        assinatura_data=_data(contrato.get("assinatura_data")),
        origem=contrato.get("origem") or "upload",
        # Migration 151.
        processo_legado=bool(contrato.get("processo_legado")),
        # Migration 157.
        modalidade_assinatura=contrato.get("modalidade_assinatura") or "digital",
    )
    return dados, atendimento_id


__all__ = ["carregar"]
