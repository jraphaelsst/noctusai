"""Read `DadosContrato` through the EXISTING services — no duplicated queries.

| Data                          | Service                                              |
|-------------------------------|------------------------------------------------------|
| contract row (404 contract)   | `contratos_service.exigir_contrato`                  |
| titular + partes by lado      | `services.ensure_cliente`, `compradores_service.listar` |
| qualificação gate per person  | `documento_checklist_service.completude_contratual`  |
| certidões per parte           | `certidoes.service.certidoes_por_parte`              |
| negociação / parcelas / …     | `negociacao_service.obter`, `negociacao_estruturada_service.obter_estruturada` |
| financiamento                 | `financiamento_service.obter`                        |
| imóvel address                | `imovel_hub.busca_service.enriquecer`                |
| imóvel matrícula/ônus/título  | `imovel_hub.dados_service.obter`                     |
| matrícula literal text        | `matriculas.estrutura_service.obter_selecao` (logs the text read) |
| ônus source acts (kind/nº)    | `matriculas.estrutura_service.listar_atos` (logs the text read)   |
| org cadastral + testemunhas   | `settings_router.get_dados_imobiliaria` / `list_testemunhas`      |

🔴 LGPD: both matrícula reads append a `text_view` access row for the
requesting user — the generator reads the CPF-bearing transcription on their
behalf, exactly as the selection panel does.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from app.modules.card_hub import compradores_service as compradores_svc
from app.modules.card_hub import contratos_service as contratos_svc
from app.modules.card_hub import documento_checklist_service as checklist_svc
from app.modules.card_hub import financiamento_service
from app.modules.card_hub import negociacao_estruturada_service as estruturada_svc
from app.modules.card_hub import negociacao_service
from app.modules.card_hub import services as svc
from app.modules.card_hub.contrato_gerador.dados import (
    AtoCitado,
    Certidao,
    Complementos,
    DadosContrato,
    Endereco,
    Favorecido,
    Financiamento,
    Imobiliaria,
    Imovel,
    Intermediario,
    Matricula,
    Parcela,
    Pessoa,
    Testemunha,
)
from app.modules.certidoes import service as certidoes_svc
from app.modules.imovel_hub import busca_service, dados_service
from app.modules.matriculas import estrutura_service


def _data(valor: Any) -> Optional[date]:
    if not valor:
        return None
    return date.fromisoformat(str(valor)[:10])


def _dec(valor: Any) -> Optional[Decimal]:
    if valor is None or valor == "":
        return None
    return Decimal(str(valor))


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


def _pessoa(
    client: Any, org_id: UUID, cliente_id: str, lado: str, papel: str, parte_id: Optional[str]
) -> Pessoa:
    row = svc.ensure_cliente(client, org_id, UUID(cliente_id))
    completude = checklist_svc.completude_contratual(client, org_id, UUID(cliente_id))
    certidoes: Optional[list[Certidao]] = None
    if parte_id:
        certidoes = [
            Certidao(
                tipo=r["tipo"],
                resultado=r.get("resultado"),
                numero=r.get("numero"),
                emitida_em=_data(r.get("emitida_em")),
                validade_ate=_data(r.get("validade_ate")),
                consulta_tipo_documento=r.get("consulta_tipo_documento") or "cpf",
                consulta_nome=r.get("consulta_nome"),
                consulta_documento=r.get("consulta_documento"),
            )
            for r in certidoes_svc.certidoes_por_parte(client, org_id, parte_id)
        ]
    return Pessoa(
        cliente_id=cliente_id,
        lado=lado,
        papel=papel,
        parte_id=parte_id,
        nome=row.get("nome_oficial"),
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
        conjuge_cliente_id=(str(row["conjuge_cliente_id"]) if row.get("conjuge_cliente_id") else None),
        faltando_qualificacao=list(completude.get("faltando") or []),
        certidoes=certidoes,
    )


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

    fonte_titulo = dados.get("titulo_aquisitivo_fonte") or {}
    return Imovel(
        codigo=codigo,
        titulo=catalogo.get("titulo"),
        empreendimento=catalogo.get("empreendimento"),
        endereco=_endereco(catalogo, prefixo=""),
        numero_matricula=dados.get("numero_matricula"),
        numero_registro_imoveis=dados.get("numero_registro_imoveis"),
        inscricao_municipal=dados.get("prefeitura_cadastro_imobiliario"),
        situacao_onus=dados.get("situacao_onus"),
        onus_certidao_em=_data(dados.get("onus_certidao_em")),
        onus_fonte_atos=atos,
        titulo_aquisitivo_confirmado=bool(fonte_titulo.get("confirmado_em")),
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
        ),
        [Testemunha(nome=t.get("nome"), rg=t.get("rg"), cpf=t.get("cpf")) for t in testemunhas],
    )


def carregar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    contrato_id: UUID,
    *,
    usuario_id: Optional[Any],
    complementos: Complementos,
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
    imobiliaria, testemunhas = _imobiliaria(client, org_id)

    dados = DadosContrato(
        contrato_id=str(contrato_id),
        modelo=contrato["modelo"],
        vendedores=vendedores,
        compradores=compradores,
        imovel=imovel,
        matricula=Matricula(
            codigo=selecao.get("codigo"), texto=selecao.get("texto") or "", num_atos=len(selecao.get("atos") or [])
        ),
        valor_negociado=_dec(estruturada.get("valor_negociado")),
        pct_comissao=_dec(negociacao.get("pct_comissao")),
        parcelas=[
            Parcela(
                id=str(p["id"]),
                tipo=p["tipo"],
                valor=_dec(p.get("valor")),
                vencimento=_data(p.get("vencimento")),
                evento=p.get("evento"),
                forma_pagamento=p.get("forma_pagamento"),
                favorecido_id=(str(p["favorecido_id"]) if p.get("favorecido_id") else None),
                confissao_divida=bool(p.get("confissao_divida")),
                ordem=int(p.get("ordem") or 0),
            )
            for p in estruturada.get("parcelas") or []
        ],
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
            )
            for i in estruturada.get("intermediarios") or []
        ],
        permuta_ativo_id=(str(negociacao["permuta_ativo_id"]) if negociacao.get("permuta_ativo_id") else None),
        financiamento=Financiamento(
            existe=bool(financiamento.get("existe")),
            situacao=financiamento.get("situacao") or "pendente",
            fgts=bool(financiamento.get("fgts")),
        ),
        imobiliaria=imobiliaria,
        testemunhas=testemunhas,
        complementos=complementos,
    )
    return dados, atendimento_id


__all__ = ["carregar"]
