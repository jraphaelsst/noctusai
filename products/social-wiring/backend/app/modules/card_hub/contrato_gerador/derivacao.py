"""Switches, derived modelo, completeness gate and consistency checks (spec §1, §5).

Pure over `DadosContrato`. Three outputs, never mixed:

- `faltando`  — a value the contract needs and nobody has entered (or the
                system cannot hold yet, spec §6.1). Named field + pt-BR label
                + where in the card it is fixed.
- `bloqueios` — the data is there but contradicts itself or the law of the
                instrument (Σ parcelas ≠ preço, RG = CPF, expired certidão…).
- `avisos`    — generation proceeds, but a human should know (an office
                default was applied, an optional clause was omitted…).

`pronto` is `not faltando and not bloqueios`. A switch that needs a MISSING
field adds a `faltando`; optional wording whose switch is off is omitted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from noctusai_lib.domain.texto_ptbr import formatar_brl
from noctusai_lib.integrations.documents import is_same_as_cpf
from noctusai_lib.integrations.documents.cpf import is_valid as cpf_valido

from app.modules.card_hub.contrato_gerador import frases
from app.modules.card_hub.contrato_gerador.concordancia import normalizar_genero
from app.modules.card_hub.contrato_gerador.dados import (
    PAPEIS_SEM_REDACAO,
    Certidao,
    DadosContrato,
    Parcela,
    Pessoa,
    signatarios,
)
from app.modules.card_hub.contrato_gerador.numeracao import num2
from app.modules.card_hub.contrato_gerador.politica import (
    DESPESAS_PERMUTA,
    ENCARGOS_RESCISAO,
    ONUS_COM_SALDO,
    ONUS_SUPORTADOS,
    Politica,
)

MODELO_COMPRA_VENDA = "compra_venda"
MODELO_A_VISTA = "compra_venda_a_vista"
MODELO_PERMUTA = "compra_venda_permuta"

#: Parcelas paid into an account the contract must print (spec §5.1).
TIPOS_PAGOS_A_FAVORECIDO = frozenset({"sinal", "intermediaria", "direta", "saldo"})

ROTULO_QUALIFICACAO = {
    "nome_oficial": "Nome oficial",
    "nacionalidade": "Nacionalidade",
    "profissao": "Profissão",
    "estado_civil": "Estado civil",
    "rg": "RG",
    "rg_orgao_expedidor": "Órgão expedidor do RG",
    "cpf": "CPF",
    "endereco": "Endereço completo",
    "regime_bens": "Regime de bens",
    "conjuge": "Cônjuge vinculado",
    "conjuge_qualificacao": "Qualificação do cônjuge",
    "genero": "Gênero",
}

SUFIXO_SEM_CAMPO = " — campo ainda não existe no sistema"


@dataclass
class Avaliacao:
    faltando: list[dict] = field(default_factory=list)
    bloqueios: list[dict] = field(default_factory=list)
    avisos: list[dict] = field(default_factory=list)

    @property
    def pronto(self) -> bool:
        return not self.faltando and not self.bloqueios

    def falta(self, campo: str, rotulo: str, onde: str, parte_id: Optional[str] = None) -> None:
        chave = (campo, parte_id)
        if any((f["campo"], f["parte_id"]) == chave for f in self.faltando):
            return
        self.faltando.append({"campo": campo, "rotulo": rotulo, "onde": onde, "parte_id": parte_id})

    def bloqueia(self, codigo: str, mensagem: str) -> None:
        if not any(b["codigo"] == codigo and b["mensagem"] == mensagem for b in self.bloqueios):
            self.bloqueios.append({"codigo": codigo, "mensagem": mensagem})

    def avisa(self, codigo: str, mensagem: str) -> None:
        if not any(a["codigo"] == codigo and a["mensagem"] == mensagem for a in self.avisos):
            self.avisos.append({"codigo": codigo, "mensagem": mensagem})


# ─── switches ─────────────────────────────────────────────────────────────


def parcelas_ordenadas(d: DadosContrato) -> list[Parcela]:
    return sorted(d.parcelas, key=lambda p: p.ordem)


def todas_certidoes(pessoas: list[Pessoa]) -> list[Certidao]:
    return [c for p in pessoas for c in (p.certidoes or [])]


def derivar_switches(d: DadosContrato, politica: Politica) -> dict[str, bool]:
    """Spec §1.1 — computed, never typed."""
    tipos = {p.tipo for p in d.parcelas}
    tem_financiamento = "financiamento" in tipos
    tem_fgts = "fgts" in tipos
    tem_parcelas_diretas = "direta" in tipos
    tem_permuta = d.permuta_ativo_id is not None
    comp = d.complementos
    partes = signatarios(d.vendedores) + signatarios(d.compradores)
    return {
        "tem_financiamento": tem_financiamento,
        "tem_fgts": tem_fgts,
        "tem_intermediaria": "intermediaria" in tipos,
        "tem_permuta": tem_permuta,
        "tem_parcelas_diretas": tem_parcelas_diretas,
        "tem_confissao": any(p.tipo == "direta" and p.confissao_divida for p in d.parcelas),
        "a_vista": not (tem_financiamento or tem_fgts or tem_parcelas_diretas),
        "tem_saldo_devedor": bool(d.imovel and d.imovel.situacao_onus in ONUS_COM_SALDO),
        "tem_intermediacao": bool(d.intermediarios),
        "tem_itens_integrantes": bool((comp.itens_integrantes or "").strip()),
        "ad_corpus": bool(comp.ad_corpus),
        "tem_pj_certidoes": any(
            c.consulta_tipo_documento == "cnpj" for c in todas_certidoes(partes)
        ),
        "tem_declaracao_partes": politica.tem_declaracao_partes,
        "tem_multa_diaria_posse": (not tem_permuta) and politica.posse_multa_diaria is not None,
    }


def modelo_derivado(switches: dict[str, bool]) -> str:
    """The `modelo` label the switches imply — a check, never a selector."""
    if switches["tem_permuta"]:
        return MODELO_PERMUTA
    if switches["a_vista"]:
        return MODELO_A_VISTA
    return MODELO_COMPRA_VENDA


# ─── certidões index ──────────────────────────────────────────────────────


def tipos_exigidos(tipo_documento: str) -> list[str]:
    coluna = 3 if tipo_documento == "cpf" else 4
    return [c[0] for c in frases.CERTIDOES if c[coluna]]


def indice_certidoes(
    certidoes: list[Certidao], tipo_documento: str, politica: Politica
) -> tuple[dict[str, Certidao], bool]:
    """tipo -> the result to print for ONE consulta kind. Returns whether the
    API `tjsp` result stood in for `tjsp_esaj` [Q8]."""
    idx: dict[str, Certidao] = {}
    for c in certidoes:
        if c.consulta_tipo_documento != tipo_documento:
            continue
        atual = idx.get(c.tipo)
        # Most recently emitted wins when a type was issued more than once.
        if atual is None or (c.emitida_em or date.min) > (atual.emitida_em or date.min):
            idx[c.tipo] = c
    usou_api = False
    if "tjsp_esaj" not in idx and "tjsp" in idx and politica.tjsp_api_equivale_esaj:
        idx["tjsp_esaj"] = idx["tjsp"]
        usou_api = True
    return idx, usou_api


def grupos_pj(pessoa: Pessoa) -> dict[str, list[Certidao]]:
    """documento -> results of each CNPJ consulta linked to this person."""
    grupos: dict[str, list[Certidao]] = {}
    for c in pessoa.certidoes or []:
        if c.consulta_tipo_documento == "cnpj":
            grupos.setdefault(c.consulta_documento or "", []).append(c)
    return grupos


# ─── the gate ─────────────────────────────────────────────────────────────


def _nome(p: Pessoa) -> str:
    return p.nome or "(sem nome oficial)"


def _doc_norm(valor: Optional[str]) -> str:
    return re.sub(r"\W", "", (valor or "").upper())


def _partes(av: Avaliacao, d: DadosContrato, politica: Politica) -> None:
    vend, comp = signatarios(d.vendedores), signatarios(d.compradores)
    if not vend:
        av.falta("partes.vendedores", "Ao menos um vendedor (proprietário) no card", "partes")
    if not comp:
        av.falta("partes.compradores", "Ao menos um comprador no card", "partes")
    for p in d.vendedores + d.compradores:
        if p not in vend and p not in comp:
            av.avisa(
                "PARTE_NAO_SIGNATARIA",
                f"{_nome(p)} ({p.papel}) não entra na qualificação nem assina o contrato.",
            )

    documentos: dict[str, str] = {}
    for lado_pessoas in (vend, comp):
        ids_lado = {p.cliente_id: p for p in lado_pessoas}
        for p in lado_pessoas:
            for chave in p.faltando_qualificacao:
                conjuge = ids_lado.get(p.conjuge_cliente_id or "")
                if chave == "conjuge_qualificacao" and conjuge is not None:
                    continue  # the spouse is a signatory and is gated on their own
                av.falta(
                    f"qualificacao.{chave}",
                    f"{ROTULO_QUALIFICACAO.get(chave, chave)} — {_nome(p)}",
                    "partes",
                    p.parte_id,
                )
            if normalizar_genero(p.genero) is None:
                av.falta("qualificacao.genero", f"Gênero — {_nome(p)}", "partes", p.parte_id)
            if p.papel in PAPEIS_SEM_REDACAO:
                av.falta(
                    f"qualificacao.{p.papel}",
                    f"Dados e redação de {p.papel} (procuração/inventário) — {_nome(p)}{SUFIXO_SEM_CAMPO}",
                    "partes",
                    p.parte_id,
                )
            if politica.email_no_bloco_assinatura and not p.email:
                av.avisa("PARTE_SEM_EMAIL", f"{_nome(p)} não tem e-mail; o bloco de assinatura sai sem ele.")
            if p.cpf and not cpf_valido(p.cpf):
                av.bloqueia("CPF_INVALIDO", f"O CPF de {_nome(p)} não confere (dígitos verificadores).")
            if is_same_as_cpf(p.rg, p.cpf):
                av.bloqueia("RG_IGUAL_CPF", f"O RG de {_nome(p)} é igual ao CPF — corrija o RG.")
            for valor in (p.cpf, p.rg):
                norm = _doc_norm(valor)
                if not norm:
                    continue
                dono = documentos.setdefault(norm, p.cliente_id)
                if dono != p.cliente_id:
                    av.bloqueia(
                        "DOCUMENTO_DUPLICADO",
                        f"{_nome(p)} tem RG/CPF igual ao de outra parte do contrato.",
                    )

            if p.estado_civil in frases.ESTADOS_EM_NUCLEO and p.conjuge_cliente_id:
                conjuge = ids_lado.get(p.conjuge_cliente_id)
                if conjuge is None:
                    av.bloqueia(
                        "CONJUGE_FORA_DO_LADO",
                        f"O cônjuge/companheiro(a) de {_nome(p)} precisa estar no mesmo lado do contrato.",
                    )
                    continue
                if conjuge.conjuge_cliente_id != p.cliente_id:
                    av.bloqueia("CONJUGE_NAO_RECIPROCO", f"O vínculo de cônjuge de {_nome(p)} não é recíproco.")
                if p.estado_civil == "casado":
                    if (p.regime_bens or "") != (conjuge.regime_bens or ""):
                        av.bloqueia("REGIME_DIVERGENTE", f"{_nome(p)} e o cônjuge têm regimes de bens diferentes.")
                    if p.regime_bens == "separacao_total":
                        av.avisa(
                            "CONJUGE_SEPARACAO_TOTAL",
                            f"{_nome(p)} é casado(a) em separação total; o cônjuge ainda assina.",
                        )
                    if politica.citar_lei_6515:
                        av.falta(
                            "qualificacao.data_casamento",
                            f"Data do casamento (Lei 6.515/77) — {_nome(p)}{SUFIXO_SEM_CAMPO}",
                            "partes",
                            p.parte_id,
                        )
                    else:
                        av.avisa(
                            "LEI_6515_NAO_CITADA",
                            "A menção à Lei 6.515/77 não é feita: a data do casamento não é registrada [Q2].",
                        )


def _imovel(av: Avaliacao, d: DadosContrato, sw: dict[str, bool]) -> None:
    im = d.imovel
    if im is None:
        av.falta("negociacao.imovel", "Imóvel negociado no card", "negociacao")
        return
    for campo, rotulo in (
        ("logradouro", "Logradouro do imóvel"),
        ("numero", "Número do imóvel"),
        ("cidade", "Cidade do imóvel"),
        ("uf", "UF do imóvel"),
    ):
        if not getattr(im.endereco, campo):
            av.falta(f"imovel.{campo}", rotulo, "imovel")
    for campo, rotulo in (
        ("numero_matricula", "Número da matrícula"),
        ("numero_registro_imoveis", "Cartório de registro de imóveis"),
        ("inscricao_municipal", "Inscrição municipal (cadastro na prefeitura)"),
    ):
        if not getattr(im, campo):
            av.falta(f"imovel.{campo}", rotulo, "imovel")

    if d.matricula.num_atos == 0 or not d.matricula.texto.strip():
        av.falta("matricula.atos", "Atos da matrícula selecionados para o contrato", "matricula")
    elif d.matricula.codigo != im.codigo:
        av.bloqueia(
            "MATRICULA_DE_OUTRO_IMOVEL",
            "Os atos selecionados são de uma matrícula de outro imóvel.",
        )
    if not im.titulo_aquisitivo_confirmado:
        av.falta("matricula.titulo_aquisitivo", "Título aquisitivo confirmado na matrícula", "matricula")
    if not (d.complementos.titulo_aquisitivo_texto or "").strip():
        av.falta(
            "contrato.titulo_aquisitivo_texto",
            "Redação do título aquisitivo (instrumento, data, livro/folhas, tabelionato)" + SUFIXO_SEM_CAMPO,
            "matricula",
        )

    if not im.situacao_onus:
        av.falta("imovel.situacao_onus", "Situação de ônus do imóvel", "imovel")
    elif im.situacao_onus not in ONUS_SUPORTADOS:
        av.bloqueia(
            "ONUS_NAO_SUPORTADO",
            f"O gerador não tem redação para ônus do tipo '{im.situacao_onus}'.",
        )

    if sw["tem_saldo_devedor"]:
        comp = d.complementos
        if not im.onus_fonte_atos:
            av.falta("matricula.onus_fonte", "Atos da matrícula que registram o ônus", "matricula")
        elif any(a.kind not in ("R", "AV") or a.numero is None for a in im.onus_fonte_atos):
            av.bloqueia("ONUS_FONTE_INVALIDA", "O ônus aponta para um ato sem número (abertura).")
        if not comp.onus_credor:
            av.falta("contrato.onus_credor", "Credor do financiamento que onera o imóvel" + SUFIXO_SEM_CAMPO, "imovel")
        if not comp.onus_quitacao:
            av.falta("contrato.onus_quitacao", "Forma de quitação do saldo devedor" + SUFIXO_SEM_CAMPO, "imovel")
        elif comp.onus_quitacao not in frases.QUITACOES_ONUS:
            av.bloqueia("ONUS_QUITACAO_INVALIDA", f"Forma de quitação desconhecida: {comp.onus_quitacao}.")
        elif comp.onus_quitacao == "compradores_prazo" and not comp.onus_prazo_dias:
            av.falta("contrato.onus_prazo_dias", "Prazo (dias) para os compradores quitarem o saldo" + SUFIXO_SEM_CAMPO, "imovel")
        elif comp.onus_quitacao == "parcela" and not any(p.tipo == "saldo" for p in d.parcelas):
            av.bloqueia("ONUS_QUITACAO_SEM_PARCELA_SALDO", "A quitação do ônus é por parcela, mas não há parcela de saldo.")


def _negociacao(
    av: Avaliacao, d: DadosContrato, sw: dict[str, bool], politica: Politica, assinatura: date
) -> None:
    if d.valor_negociado is None:
        av.falta("negociacao.valor_negociado", "Valor negociado", "negociacao")
    parcelas = parcelas_ordenadas(d)
    if not parcelas:
        av.falta("negociacao.parcelas", "Parcelas do preço", "negociacao")
    else:
        sinais = [p for p in parcelas if p.tipo == "sinal"]
        if not sinais:
            av.falta("negociacao.parcela_sinal", "Parcela de sinal", "negociacao")
        elif len(sinais) > 1:
            av.bloqueia("MAIS_DE_UM_SINAL", "O contrato admite exatamente uma parcela de sinal.")

    favorecidos = {f.id: f for f in d.favorecidos}
    cpfs_vendedores = {frases.so_digitos(p.cpf) for p in signatarios(d.vendedores) if p.cpf}
    ultimo_venc: Optional[date] = None
    for i, p in enumerate(parcelas, start=1):
        rot = f"Parcela {num2(i)}"
        if p.valor is None or p.valor <= 0:
            av.falta(f"negociacao.parcela.{p.id}.valor", f"Valor da {rot}", "negociacao")
        if not p.vencimento and not (p.evento or "").strip():
            av.falta(f"negociacao.parcela.{p.id}.momento", f"Vencimento ou evento da {rot}", "negociacao")
        if p.tipo in TIPOS_PAGOS_A_FAVORECIDO:
            if not p.favorecido_id:
                av.falta(f"negociacao.parcela.{p.id}.favorecido", f"Favorecido da {rot}", "negociacao")
            else:
                fav = favorecidos.get(p.favorecido_id)
                if fav is None:
                    av.bloqueia("FAVORECIDO_INEXISTENTE", f"O favorecido da {rot} não existe mais.")
                else:
                    if not fav.conta and not fav.pix:
                        av.falta(f"negociacao.favorecido.{fav.id}.conta", f"Conta ou chave PIX de {fav.nome}", "negociacao")
                    if fav.conta and not (fav.banco and fav.agencia):
                        av.falta(f"negociacao.favorecido.{fav.id}.banco", f"Banco e agência de {fav.nome}", "negociacao")
                    if frases.so_digitos(fav.cpf_cnpj) not in cpfs_vendedores:
                        av.avisa("FAVORECIDO_TERCEIRO", f"{fav.nome} ({rot}) não é um dos vendedores.")
            if not (p.forma_pagamento or "").strip():
                av.falta(f"negociacao.parcela.{p.id}.forma_pagamento", f"Forma de pagamento da {rot}", "negociacao")
        if "financiamento" in (p.evento or "").lower() and not sw["tem_financiamento"]:
            av.bloqueia("EVENTO_CITA_FINANCIAMENTO", f"A {rot} cita financiamento, mas não há parcela de financiamento.")
        if p.tipo == "saldo" and politica.saldo_quita_financiamento_vendedor and not sw["tem_saldo_devedor"]:
            av.bloqueia("SALDO_SEM_ONUS", f"A {rot} é de saldo (quitação do financiamento do vendedor), mas o imóvel não tem ônus [Q7].")
        if p.confissao_divida and p.tipo != "direta":
            av.bloqueia("CONFISSAO_EM_PARCELA_NAO_DIRETA", f"Só parcelas diretas entram na confissão de dívida ({rot}).")
        if p.vencimento:
            if ultimo_venc is not None and p.vencimento <= ultimo_venc:
                av.bloqueia("VENCIMENTOS_FORA_DE_ORDEM", f"O vencimento da {rot} não é posterior ao da parcela anterior.")
            ultimo_venc = p.vencimento

    if d.valor_negociado is not None and parcelas and all(p.valor is not None for p in parcelas):
        soma = sum((p.valor for p in parcelas), Decimal("0"))  # type: ignore[misc]
        permuta = d.complementos.permuta_parcela_valor
        if not sw["tem_permuta"] or permuta is not None:
            soma += permuta or Decimal("0")
            if soma != d.valor_negociado:
                av.bloqueia(
                    "SOMA_PARCELAS_DIFERENTE_DO_PRECO",
                    f"As parcelas somam {formatar_brl(soma)}, mas o preço é {formatar_brl(d.valor_negociado)}.",
                )

    comp = d.complementos
    if not comp.posse_prazo_dias:
        av.falta("contrato.posse_prazo_dias", "Prazo de entrega da posse (dias)" + SUFIXO_SEM_CAMPO, "negociacao")
    if not comp.posse_marco:
        av.falta("contrato.posse_marco", "Marco inicial do prazo da posse" + SUFIXO_SEM_CAMPO, "negociacao")
    elif comp.posse_marco not in frases.MARCOS_POSSE:
        av.bloqueia("POSSE_MARCO_INVALIDO", f"Marco da posse desconhecido: {comp.posse_marco}.")
    elif comp.posse_marco == "parcela_financiamento" and not sw["tem_financiamento"]:
        av.bloqueia("POSSE_MARCO_SEM_FINANCIAMENTO", "A posse conta do financiamento, mas não há parcela de financiamento.")
    if not sw["tem_permuta"] and politica.posse_multa_diaria is None:
        av.avisa("MULTA_DIARIA_POSSE_OMITIDA", "O parágrafo de multa diária pela posse foi omitido: valor não definido [Q12].")

    if sw["tem_confissao"]:
        if comp.juros_am_confissao is None:
            av.falta("contrato.juros_am_confissao", "Juros remuneratórios ao mês da confissão de dívida" + SUFIXO_SEM_CAMPO, "negociacao")
        for i, p in enumerate(parcelas, start=1):
            if not p.confissao_divida:
                continue
            if not p.vencimento:
                av.falta(f"negociacao.parcela.{p.id}.vencimento", f"Vencimento da Parcela {num2(i)} (confissão de dívida)", "negociacao")
            elif p.vencimento <= assinatura:
                av.bloqueia("CONFISSAO_VENCIMENTO_PASSADO", f"A Parcela {num2(i)} da confissão vence antes da assinatura.")


def _financiamento(av: Avaliacao, d: DadosContrato, sw: dict[str, bool]) -> None:
    if sw["tem_financiamento"]:
        if not d.financiamento.existe:
            av.falta("financiamento", "Registro do financiamento do atendimento", "financiamento")
        elif d.financiamento.situacao == "recusado":
            av.bloqueia("FINANCIAMENTO_RECUSADO", "O financiamento deste atendimento está recusado.")
    if sw["tem_fgts"] and not d.financiamento.fgts:
        av.bloqueia("FGTS_NAO_MARCADO", "Há parcela de FGTS, mas o financiamento não marca uso de FGTS.")
    if d.financiamento.fgts and not sw["tem_fgts"]:
        av.avisa("FGTS_SEM_PARCELA", "O financiamento marca FGTS, mas nenhuma parcela é de FGTS [Q6].")


def _permuta(av: Avaliacao, d: DadosContrato, sw: dict[str, bool], politica: Politica) -> None:
    if not sw["tem_permuta"]:
        return
    comp = d.complementos
    if comp.permuta_parcela_valor is None:
        av.falta("contrato.permuta_parcela", "Parcela de permuta (valor do imóvel dado em permuta)" + SUFIXO_SEM_CAMPO, "negociacao")
    if not comp.permuta_imoveis:
        av.falta("contrato.permuta_imoveis", "Descrição e matrícula do imóvel dado em permuta" + SUFIXO_SEM_CAMPO, "matricula")
    if not comp.permuta_posse_prazo_dias:
        av.falta("contrato.permuta_posse_prazo_dias", "Prazo de entrega da posse do imóvel da permuta" + SUFIXO_SEM_CAMPO, "negociacao")
    if not comp.permuta_posse_marco:
        av.falta("contrato.permuta_posse_marco", "Marco da posse do imóvel da permuta" + SUFIXO_SEM_CAMPO, "negociacao")
    elif comp.permuta_posse_marco not in frases.MARCOS_POSSE:
        av.bloqueia("POSSE_MARCO_INVALIDO", f"Marco da posse da permuta desconhecido: {comp.permuta_posse_marco}.")
    if politica.permuta_despesas is None:
        av.falta("contrato.permuta_despesas", "Quem paga escritura/ITBI de cada imóvel da permuta [Q13]", "contrato")
    elif politica.permuta_despesas not in DESPESAS_PERMUTA:
        av.bloqueia("PERMUTA_DESPESAS_INVALIDA", f"Política de despesas desconhecida: {politica.permuta_despesas}.")


def _certidoes(
    av: Avaliacao, d: DadosContrato, sw: dict[str, bool], politica: Politica, assinatura: date
) -> None:
    exigidas = signatarios(d.vendedores) + (signatarios(d.compradores) if sw["tem_permuta"] else [])
    sem_validade: list[str] = []
    positivas: list[str] = []

    def conferir(p: Pessoa, certs: list[Certidao], tipo_documento: str, nome_grupo: str) -> None:
        idx, usou_api = indice_certidoes(certs, tipo_documento, politica)
        if usou_api:
            av.avisa("TJSP_API_COMO_ESAJ", f"A certidão TJSP da API foi usada como E-SAJ para {nome_grupo} [Q8].")
        for tipo in tipos_exigidos(tipo_documento):
            rotulo = frases.rotulo_certidao(tipo, None)
            c = idx.get(tipo)
            if c is None or not c.resultado:
                av.falta(f"certidao.{tipo}", f"{rotulo} — {nome_grupo}", "certidoes", p.parte_id)
                continue
            if c.resultado == "nao_emitida":
                continue
            if not c.numero:
                av.falta(f"certidao.{tipo}.numero", f"Número da {rotulo} — {nome_grupo}", "certidoes", p.parte_id)
            if not c.emitida_em:
                av.falta(f"certidao.{tipo}.emitida_em", f"Data de emissão da {rotulo} — {nome_grupo}", "certidoes", p.parte_id)
                continue
            if c.emitida_em > assinatura:
                av.bloqueia("CERTIDAO_EMITIDA_APOS_ASSINATURA", f"{rotulo} de {nome_grupo} tem emissão posterior à assinatura.")
            validade = c.validade_ate
            if validade is None and tipo in politica.validade_padrao_dias:
                validade = c.emitida_em + timedelta(days=politica.validade_padrao_dias[tipo])
            if validade is None:
                sem_validade.append(f"{rotulo} ({nome_grupo})")
            elif validade < assinatura:
                av.bloqueia("CERTIDAO_VENCIDA", f"{rotulo} de {nome_grupo} está vencida na data da assinatura.")
            if c.resultado == "positiva":
                positivas.append(f"{rotulo} ({nome_grupo})")

    for p in exigidas:
        if p.certidoes is None:
            av.falta(
                f"certidoes.titular.{p.cliente_id}",
                f"Certidões de {_nome(p)} (titular do card) — não vinculáveis ao titular hoje",
                "certidoes",
                None,
            )
            continue
        conferir(p, p.certidoes, "cpf", _nome(p))
        for documento, certs in grupos_pj(p).items():
            conferir(p, certs, "cnpj", certs[0].consulta_nome or documento)

    if sem_validade:
        av.avisa(
            "CERTIDOES_SEM_VALIDADE",
            f"{len(sem_validade)} certidão(ões) sem data de validade não tiveram a validade conferida [Q10].",
        )
    if positivas:
        av.avisa("CERTIDOES_POSITIVAS", "Certidões positivas exigem esclarecimentos: " + "; ".join(positivas) + ".")


def _imobiliaria(av: Avaliacao, d: DadosContrato, politica: Politica) -> None:
    org = d.imobiliaria
    for valor, campo, rotulo in (
        (org.razao_social, "razao_social", "Razão social da imobiliária"),
        (org.cnpj, "cnpj", "CNPJ da imobiliária"),
        (org.responsavel_nome, "responsavel_nome", "Responsável legal da imobiliária"),
        (org.responsavel_creci, "responsavel_creci", "CRECI do responsável"),
        (org.endereco.cidade, "endereco_cidade", "Cidade da imobiliária (local de assinatura)"),
    ):
        if not valor:
            av.falta(f"imobiliaria.{campo}", rotulo, "imobiliaria")
    if len(d.testemunhas) != 2:
        av.falta("imobiliaria.testemunhas", "Duas testemunhas cadastradas", "imobiliaria")
    for i, t in enumerate(d.testemunhas, start=1):
        if not t.nome:
            av.falta(f"imobiliaria.testemunha.{i}.nome", f"Nome da testemunha {i}", "imobiliaria")
        if not t.rg:
            av.falta(f"imobiliaria.testemunha.{i}.rg", f"RG da testemunha {i}", "imobiliaria")
        if politica.testemunha_exige_cpf and not t.cpf:
            av.falta(f"imobiliaria.testemunha.{i}.cpf", f"CPF da testemunha {i}", "imobiliaria")
    comp = d.complementos
    if not comp.plataforma_assinatura_nome or not comp.plataforma_assinatura_url:
        av.falta(
            "imobiliaria.plataforma_assinatura",
            "Plataforma de assinatura digital (nome e endereço)" + SUFIXO_SEM_CAMPO,
            "imobiliaria",
        )


def _intermediacao(av: Avaliacao, d: DadosContrato, sw: dict[str, bool], politica: Politica) -> None:
    if not sw["tem_intermediacao"]:
        return
    comp = d.complementos
    favorecidos = {f.id: f for f in d.favorecidos}
    for it in d.intermediarios:
        if not it.creci:
            av.falta(f"negociacao.intermediario.{it.id}.creci", f"CRECI de {it.nome}", "negociacao")
        if it.valor is None:
            av.falta(f"negociacao.intermediario.{it.id}.valor", f"Valor da corretagem de {it.nome}", "negociacao")
        if not it.corretor_id and it.id not in comp.intermediarios_qualificacao:
            av.falta(
                f"contrato.intermediario.{it.id}.qualificacao",
                f"Qualificação (PF/PJ, documento, endereço) do intermediário externo {it.nome}" + SUFIXO_SEM_CAMPO,
                "negociacao",
            )
        fav_id = comp.corretagem_favorecidos.get(it.id)
        if not fav_id:
            av.falta(
                f"contrato.intermediario.{it.id}.favorecido",
                f"Favorecido que recebe a corretagem de {it.nome}" + SUFIXO_SEM_CAMPO,
                "negociacao",
            )
        elif fav_id not in favorecidos:
            av.bloqueia("FAVORECIDO_INEXISTENTE", f"O favorecido da corretagem de {it.nome} não existe.")
        elif not favorecidos[fav_id].conta and not favorecidos[fav_id].pix:
            fav = favorecidos[fav_id]
            av.falta(f"negociacao.favorecido.{fav.id}.conta", f"Conta ou chave PIX de {fav.nome}", "negociacao")
    if not comp.corretagem_contratantes:
        av.falta("contrato.corretagem_contratantes", "Quem paga a corretagem (vendedores ou partes)" + SUFIXO_SEM_CAMPO, "negociacao")
    elif comp.corretagem_contratantes not in ("vendedores", "partes"):
        av.bloqueia("CORRETAGEM_CONTRATANTES_INVALIDO", f"Pagador de corretagem desconhecido: {comp.corretagem_contratantes}.")
    if not comp.corretagem_parcelas_marco:
        av.falta(
            "contrato.corretagem_parcelas_marco",
            "Parcelas cujo recebimento dispara o pagamento da corretagem" + SUFIXO_SEM_CAMPO,
            "negociacao",
        )
    elif any(not 1 <= n <= len(d.parcelas) for n in comp.corretagem_parcelas_marco):
        av.bloqueia("CORRETAGEM_MARCO_INEXISTENTE", "A corretagem cita uma parcela que não existe.")
    if d.pct_comissao is None:
        av.falta("negociacao.pct_comissao", "Percentual de comissão", "negociacao")
    elif politica.corretagem_rescisao_igual_comissao:
        av.avisa(
            "CORRETAGEM_RESCISAO_PELA_COMISSAO",
            "O percentual de corretagem devido na rescisão é o da comissão do negócio [Q5].",
        )
        pct_total = sum((i.valor for i in d.intermediarios if i.tipo == "percentual" and i.valor is not None), Decimal("0"))
        if pct_total and pct_total != d.pct_comissao:
            av.avisa("CORRETAGEM_PERCENTUAL_DIVERGE", "Os percentuais dos intermediários não somam o percentual de comissão.")


def _contrato(av: Avaliacao, d: DadosContrato, sw: dict[str, bool], politica: Politica) -> None:
    derivado = modelo_derivado(sw)
    if d.modelo != derivado:
        av.avisa("MODELO_DIVERGENTE", f"O modelo do contrato é '{d.modelo}', mas os dados indicam '{derivado}'.")
    if politica.rescisao_encargo is None:
        av.avisa("ENCARGO_RESCISAO_NAO_DEFINIDO", "O encargo adicional na rescisão foi omitido: política não definida [Q4].")
    elif politica.rescisao_encargo not in ENCARGOS_RESCISAO:
        av.bloqueia("ENCARGO_RESCISAO_INVALIDO", f"Encargo de rescisão desconhecido: {politica.rescisao_encargo}.")
    if d.complementos.itens_integrantes is None:
        av.avisa("ITENS_INTEGRANTES_NAO_INFORMADOS", "Itens integrantes não informados; o parágrafo foi omitido.")
    if d.complementos.ad_corpus is None:
        av.avisa("AD_CORPUS_NAO_INFORMADO", "Venda ad corpus não informada; a expressão foi omitida.")
    if d.imovel is not None:
        av.avisa("FORO_PELA_CIDADE", "O foro usa a cidade do imóvel como comarca.")


def avaliar(
    d: DadosContrato, switches: dict[str, bool], politica: Politica, assinatura: date
) -> Avaliacao:
    av = Avaliacao()
    _partes(av, d, politica)
    _imovel(av, d, switches)
    _negociacao(av, d, switches, politica, assinatura)
    _financiamento(av, d, switches)
    _permuta(av, d, switches, politica)
    _certidoes(av, d, switches, politica, assinatura)
    _imobiliaria(av, d, politica)
    _intermediacao(av, d, switches, politica)
    _contrato(av, d, switches, politica)
    return av


__all__ = [
    "Avaliacao",
    "MODELO_A_VISTA",
    "MODELO_COMPRA_VENDA",
    "MODELO_PERMUTA",
    "avaliar",
    "derivar_switches",
    "grupos_pj",
    "indice_certidoes",
    "modelo_derivado",
    "parcelas_ordenadas",
    "tipos_exigidos",
]
