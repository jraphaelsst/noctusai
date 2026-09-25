"""Data-dependent wording — the phrases `modelo_texto.TEMPLATE` inserts whole.

Plain pt-BR text plus the rule that picks between variants, kept together so
a reviewer reads each alternative next to its condition. Every function here
is pure; none reads a database, none invents a value (callers only reach them
after the gate passed, so every field they print is present).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Optional, Sequence

from noctusai_lib.domain.texto_ptbr import (
    brl_por_extenso,
    dias_por_extenso,
    formatar_data_br,
    formatar_inteiro_br,
    numero_com_extenso,
)
from noctusai_lib.integrations.documents.cpf import format_cpf
from noctusai_lib.integrations.documents.nacionalidade import (
    canonico as _nacionalidade_canonica,
    feminino as _nacionalidade_feminina,
)

from app.modules.card_hub.contrato_gerador.concordancia import (
    Concordancia,
    lado as concordancia_lado,
    normalizar_genero,
)
from app.modules.card_hub.contrato_gerador.dados import (
    AtoCitado,
    Certidao,
    CertidaoImovel,
    Endereco,
    Favorecido,
    Imobiliaria,
    Intermediario,
    Parcela,
    Pessoa,
)
from app.modules.card_hub.contrato_gerador.numeracao import juntar

# ─── documentos / endereços ────────────────────────────────────────────────


def so_digitos(valor: Optional[str]) -> str:
    return re.sub(r"\D", "", valor or "")


def documento(valor: Optional[str]) -> tuple[str, str]:
    """(rótulo, número formatado): CPF by 11 digits, CNPJ by 14."""
    d = so_digitos(valor)
    if len(d) == 11:
        return "CPF", format_cpf(d) or d
    if len(d) == 14:
        return "CNPJ", f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"
    return "CPF/CNPJ", (valor or "").strip()


def cep(valor: Optional[str]) -> str:
    d = so_digitos(valor)
    return f"{d[:5]}-{d[5:]}" if len(d) == 8 else (valor or "").strip()


def endereco_texto(e: Endereco) -> str:
    """"Rua X, nº 10 - Apto 1 - Bairro - Cidade/UF – CEP: 00000-000"."""
    texto = f"{e.logradouro}, nº {e.numero}"
    if e.complemento:
        texto += f" - {e.complemento}"
    return f"{texto} - {e.bairro} - {e.cidade}/{(e.uf or '').upper()} – CEP: {cep(e.cep)}"


def matricula_numero(valor: Optional[str]) -> str:
    """"12345" -> "12.345"; anything not purely digits prints as stored."""
    bruto = (valor or "").strip()
    return formatar_inteiro_br(int(bruto)) if bruto.isdigit() else bruto


def pct_simples(valor: Decimal) -> str:
    """Decimal("6.00") -> "6%"; Decimal("1.5") -> "1,5%"."""
    texto = format(valor.normalize(), "f")
    return texto.replace(".", ",") + "%"


# ─── qualificação das partes (spec §2.1) ──────────────────────────────────

#: Legacy free-text spellings a human typed BEFORE the extractor could read
#: `nacionalidade` (migration 146) — "brasileiro(a)"/"brasil" have no
#: grammatical-gender pair the seed's closed vocabulary recognises
#: (`nacionalidade.canonico` intentionally does not match parenthesised or
#: bare-demonym forms; see that function's own test). Checked FIRST, ahead
#: of the general vocabulary below, so an existing typed value keeps
#: rendering exactly as it always did.
_NACIONALIDADE_BR = {"brasileiro", "brasileira", "brasileiro(a)", "brasileira(o)", "brasil"}

_ESTADO_CIVIL_FLEX = {
    "solteiro": ("solteiro", "solteira"),
    "divorciado": ("divorciado", "divorciada"),
    "separado_judicialmente": ("separado judicialmente", "separada judicialmente"),
    "viuvo": ("viúvo", "viúva"),
}

REGIME_EXTENSO = {
    "comunhao_parcial": "comunhão parcial de bens",
    "comunhao_universal": "comunhão universal de bens",
    "separacao_total": "separação total de bens",
    "separacao_obrigatoria": "separação obrigatória de bens",
    "participacao_final_aquestos": "participação final nos aquestos",
}

ESTADOS_EM_NUCLEO = ("casado", "uniao_estavel")


def _g(p: Pessoa, m: str, f: str) -> str:
    return f if normalizar_genero(p.genero) == "f" else m


def nacionalidade_flex(p: Pessoa) -> str:
    """The party's nationality, gendered to agree with them (spec §2.0).

    Migration 146 made `nacionalidade` extractable — a new-model CNH prints
    "BRASILEIRO" for a woman, and a certidão prints each spouse's own
    grammatical gender. Neither is safe to print verbatim: contract 08 (a
    human-typed reference) renders "brasileira" for a woman and
    "brasileiro" for a man regardless of which form the SOURCE document
    happened to spell, because agreement here is a fact about the PARTY,
    not about the document.

    So a value is re-genderED, not passed through, once it is recognised —
    either the legacy `_NACIONALIDADE_BR` set (kept for backward
    compatibility with a value a human typed before 145 existed) or the
    seed's closed gentílico vocabulary (`nacionalidade.canonico` /
    `.feminino` — the same table `find_nacionalidade` uses to extract, so
    the generator's agreement and the extractor's canonicalisation can
    never drift apart). A value that matches neither is free text with no
    known agreement rule — printed exactly as stored, lower-cased, the same
    fallback this function always had.
    """
    bruto = (p.nacionalidade or "").strip()
    if bruto.lower() in _NACIONALIDADE_BR:
        return _g(p, "brasileiro", "brasileira")
    canonica = _nacionalidade_canonica(bruto)
    if canonica is None:
        return bruto.lower()
    return _g(p, canonica, _nacionalidade_feminina(canonica) or canonica)


def rg_texto(p: Pessoa) -> str:
    orgao = re.sub(r"[\s/]+", "-", (p.rg_orgao or "").strip().upper())
    return f"{(p.rg or '').strip()}-{orgao}"


def texto_pessoa(p: Pessoa, *, em_nucleo: bool) -> str:
    partes = [(p.nome or "").upper(), nacionalidade_flex(p)]
    if not em_nucleo:
        par_ec = _ESTADO_CIVIL_FLEX.get(p.estado_civil or "")
        if par_ec:
            partes.append(_g(p, *par_ec))
    # [2026-09-22] Omitted cleanly when absent — the office accepts a
    # qualification with no profissão (contract 08's REGINA MARIA PELOSI has
    # none), and an empty entry here used to join as a dangling ", ," before
    # "portador(a) da cédula...".
    profissao = (p.profissao or "").strip().lower()
    if profissao:
        partes.append(profissao)
    texto = ", ".join(partes)
    texto += (
        f", {_g(p, 'portador', 'portadora')} da cédula de identidade RG {rg_texto(p)}"
        f" e {_g(p, 'inscrito', 'inscrita')} no CPF/MF {documento(p.cpf)[1]}"
    )
    if p.email:
        texto += f", com endereço eletrônico: {p.email.strip().lower()}"
    return texto


def _residente(p: Pessoa) -> str:
    return _g(p, "residente e domiciliado", "residente e domiciliada")


def nucleos(pessoas: Sequence[Pessoa]) -> list[tuple[Pessoa, Optional[Pessoa]]]:
    """Pair spouses/companions who are BOTH on this side, in display order."""
    por_id = {p.cliente_id: p for p in pessoas}
    usados: set[str] = set()
    saida: list[tuple[Pessoa, Optional[Pessoa]]] = []
    for p in pessoas:
        if p.cliente_id in usados:
            continue
        usados.add(p.cliente_id)
        par = por_id.get(p.conjuge_cliente_id or "")
        if p.estado_civil in ESTADOS_EM_NUCLEO and par is not None and par.cliente_id not in usados:
            usados.add(par.cliente_id)
            saida.append((p, par))
        else:
            saida.append((p, None))
    return saida


def lei_6515_frase(data_casamento: date, vigencia_desde: date) -> str:
    """[Q2] Every casamento cites the Lei 6.515/77 by its date."""
    if data_casamento >= vigencia_desde:
        return ", na vigência da Lei 6.515/77"
    return ", anterior à vigência da Lei 6.515/77"


def qualificacao(pessoas: Sequence[Pessoa], *, lei_6515_desde: date) -> str:
    textos: list[str] = []
    for a, b in nucleos(pessoas):
        if b is None:
            textos.append(
                f"{texto_pessoa(a, em_nucleo=False)}, {_residente(a)} na {endereco_texto(a.endereco)}"
            )
            continue
        mesmo_endereco = endereco_texto(a.endereco) == endereco_texto(b.endereco)
        if mesmo_endereco:
            ta, tb = texto_pessoa(a, em_nucleo=True), texto_pessoa(b, em_nucleo=True)
            sufixo = f", residentes e domiciliados na {endereco_texto(a.endereco)}"
        else:
            ta = f"{texto_pessoa(a, em_nucleo=True)}, {_residente(a)} na {endereco_texto(a.endereco)}"
            tb = f"{texto_pessoa(b, em_nucleo=True)}, {_residente(b)} na {endereco_texto(b.endereco)}"
            sufixo = ""
        if a.estado_civil == "uniao_estavel":
            textos.append(f"{ta}, que convive em união estável com {tb}{sufixo}")
        else:
            lei = lei_6515_frase(a.data_casamento, lei_6515_desde)  # type: ignore[arg-type] — gated
            regime = REGIME_EXTENSO.get(a.regime_bens or "", a.regime_bens or "")
            textos.append(f"{ta}, e {tb}, casados no regime da {regime}{lei}{sufixo}")
    return ", e ".join(textos)


def nome_email_linha(nome: Optional[str], email: Optional[str]) -> str:
    """[Q14] NOME (upper) + the e-mail spaced beside it when present — the
    shape both the signing platform and Contract 08's own witness block need
    (`PRISCILA ANTONIA HIJAZI              priscilahijazi@hotmail.com`).
    Falls back to the bare name when there is no e-mail to show — never a
    blank/placeholder value in a legal instrument."""
    n = (nome or "").upper()
    if email:
        return f"{n}    {email.strip().lower()}"
    return n


def signatario_linha(p: Pessoa) -> str:
    """[Q14] The e-mail stays beside the name (the signing platform needs it)."""
    return nome_email_linha(p.nome, p.email)


# ─── assinatura física (migration 157) ────────────────────────────────────

#: The line a party signs on, printed ABOVE each signer's and each
#: witness's name in a FÍSICA contract.
LINHA_ASSINATURA = "______________________________"


def documento_linha(cpf: Optional[str]) -> str:
    """"CPF 000.000.000-00" (or CNPJ) under a física signer's name; "" when
    there is no document to print — never a dangling label."""
    if not so_digitos(cpf):
        return ""
    rotulo, numero = documento(cpf)
    return f"{rotulo} {numero}"


def testemunha_documento_linha(cpf: Optional[str]) -> str:
    """A física witness's document line: "CPF 000.000.000-00".

    [Migration 168, owner decision] The contract now prints CPF instead of
    RG for every witness — RG left the form and the readiness gate alike, so
    there is no second document to fall back to. Kept as its own function
    (rather than callers using `documento_linha` directly) so a future
    witness-specific document rule has one place to land, same reasoning
    `assinante_fisico` keeps its own wrapper over `documento_linha`."""
    return documento_linha(cpf)


def assinante_fisico(p: Pessoa) -> dict[str, str]:
    """A física signer's block: name (upper) + CPF — no e-mail (nothing is
    e-mailed for a física contract)."""
    return {"nome": (p.nome or "").upper(), "documento": documento_linha(p.cpf)}


# ─── preço / parcelas (spec §2.3) ─────────────────────────────────────────


def _forma(forma: Optional[str]) -> str:
    f = (forma or "").strip()
    return f if f.isupper() else f.lower()


def banco_texto(fav: Favorecido) -> str:
    texto = ""
    if fav.conta:
        banco = (fav.banco or "").strip()
        # "Banco Exemplo" is stored with its own prefix; "Itaú" is not.
        banco = banco if banco.lower().startswith("banco") else f"Banco {banco}"
        texto += f", {banco}, Agência {fav.agencia}, Conta {fav.conta}"
    if fav.pix:
        texto += f" ou Chave PIX: {fav.pix}" if fav.conta else f", Chave PIX: {fav.pix}"
    return texto


def texto_parcela(
    p: Parcela,
    *,
    V: Concordancia,
    C: Concordancia,
    tem_financiamento: bool,
    fgts: bool,
    ref_financiamento: str,
    favorecido: Optional[Favorecido],
    favorecido_repetido: bool,
    vendedor_favorecido: Optional[Pessoa],
    juros_am: Optional[Decimal],
) -> str:
    """Everything after "Parcela NN:" for one parcela."""
    valor = brl_por_extenso(p.valor)  # type: ignore[arg-type] — gate guarantees it
    if p.tipo == "financiamento":
        # [Q6] FGTS + financiamento are ONE parcela (contract 03's wording).
        if fgts:
            valor += ", através do uso de FGTS e financiamento imobiliário"
        else:
            valor += ", por meio de recursos de financiamento imobiliário e/ou moeda corrente nacional"
    elif p.tipo == "saldo":
        # [Q7] saldo = payoff of the seller's existing financing.
        valor += ", destinada à quitação do saldo devedor do financiamento que onera o imóvel"
    frases = [valor]

    if p.vencimento:
        frases.append(f"com vencimento em {formatar_data_br(p.vencimento)}")
    elif p.tipo == "intermediaria" and tem_financiamento:
        frases.append(
            "por ocasião da assinatura do Contrato de Financiamento Imobiliário, "
            f"previsto para quitação da Parcela {ref_financiamento}"
        )
    else:
        frases.append((p.evento or "").strip())

    if favorecido is not None:
        if favorecido_repetido:
            frases.append(
                f"por meio de {_forma(p.forma_pagamento)} na mesma conta corrente anteriormente informada"
            )
        else:
            if vendedor_favorecido is not None:
                gv = concordancia_lado([normalizar_genero(vendedor_favorecido.genero) or "m"], "vendedor")
                em_favor = f"em favor {gv.dos} {gv.NOME}: "
            else:
                em_favor = "em favor de "
            rotulo, numero = documento(favorecido.cpf_cnpj)
            frases.append(
                f"por meio de {_forma(p.forma_pagamento)} a ser realizada {em_favor}"
                f"{favorecido.nome}, {rotulo}: {numero}{banco_texto(favorecido)}"
            )
    if juros_am is not None:
        frases.append(f"acrescidos de {pct_simples(juros_am)} de juros a.m., calculados pro rata die")
    if p.tipo == "sinal":
        frases.append(
            f"operando-se automaticamente a quitação em favor {C.dos} {C.NOME.title()} com o "
            f"efetivo crédito na conta corrente ora indicada {V.pelos} {V.NOME.title()}"
        )
    cabeca = " Sinal e princípio de pagamento:" if p.tipo == "sinal" else ""
    return f"{cabeca} " + ", ".join(frases) + "."


# ─── certidões (spec §2.5 label table) ────────────────────────────────────

#: (tipo, rótulo with {R}, número label, PF, PJ, sistema) — office order.
CERTIDOES: tuple[tuple[str, str, str, bool, bool, Optional[str]], ...] = (
    ("cnd_federal", "Certidão {R} de Débitos Relativos aos Tributos Federais e Dívida Ativa União", "nº", True, True, None),
    ("trf3_sp", "Certidão {R} da Justiça Federal – Ações e Execuções Cíveis - 1ª Instância", "nº", True, True, None),
    ("trf3", "Certidão {R} da Justiça Federal – Ações e Execuções Cíveis – 2ª Instância", "nº", True, True, None),
    ("trt2_digital", "Certidão {R} de Ação Trabalhista em Tramitação Processos Digitais", "nº", True, True, None),
    ("trt2_fisico", "Certidão {R} de Ação Trabalhista em Tramitação Processos Físicos", "nº", True, True, None),
    ("cnd_trabalhista_tst", "Certidão {R} de Débitos Trabalhistas", "nº", True, True, None),
    ("tjsp_esaj", "Certidão {R} Estadual do Distribuidor Cível do Tribunal de Justiça do Estado de São Paulo", "nº", True, True, "E-SAJ"),
    ("tjsp_eproc", "Certidão {R} Estadual do Distribuidor Cível do Tribunal de Justiça do Estado de São Paulo", "nº", True, True, "E-PROC"),
    ("serasa", "Pesquisa {R} junto ao Serasa, relativa a restrições financeiras e protestos com abrangência ao Estado de São Paulo", "protocolo nº", True, False, None),
    ("cenprot", "Pesquisa {R} junto ao Cenprot, relativa a protestos com abrangência ao Estado de São Paulo", "protocolo nº", True, True, None),
    ("cnd_fazenda_sp", "Certidão {R} de Débitos Tributários Não Inscritos na Dívida Ativa do Estado de São Paulo", "nº", True, True, None),
    ("divida_ativa_sp", "Certidão {R} de Débitos Tributários da Dívida Ativa do Estado de São Paulo", "nº", True, True, None),
)

RESULTADO_ROTULO = {
    "negativa": "Negativa",
    "positiva": "Positiva",
    "positiva_com_efeito_de_negativa": "Positiva com Efeito de Negativa",
    # [§6.1 #15] Migration 116's fifth value, and the wording contracts 03/08
    # already use: nada consta for THIS identity, but records under a
    # same-name/CPF third party could not be ruled out. Deliberately NOT
    # collapsed into "Negativa" — it is different due-diligence information.
    "negativa_com_homonimos": "Negativa com apontamentos de Homônimos",
}

#: Results the esclarecimentos paragraph is about — a genuine positiva. THE
#: gerador's ONE classifier for "does this resultado count as an
#: apontamento": both `_certidoes_do_imovel` and `_certidoes` (`derivacao.py`)
#: read `c.resultado in RESULTADOS_COM_APONTAMENTO` and nowhere else in this
#: module re-derives the split — fix membership here, never at a call site.
#:
#: 🔴 [Owner directive, 2026-09-25] `negativa_com_homonimos` COUNTS AS
#: NEGATIVA — no esclarecimentos paragraph, no `CERTIDOES_POSITIVAS`/
#: `CERTIDAO_IMOVEL_COM_APONTAMENTO` aviso. It used to sit alongside
#: `"positiva"` here (migration 116's own §6.1 #15 read: "a negativa whose
#: homônimo apontamentos are precisely what has to be explained away") —
#: reversed by this directive. The certidões matriz's own classifier
#: (`certidoes_matriz_service._NAO_CONSTAM`) already read it as a clean
#: "Não constam" and needed no change; the contract's own listing keeps the
#: document's wording verbatim (`RESULTADO_ROTULO["negativa_com_homonimos"]`
#: above, untouched by this directive — the caveat is due-diligence
#: information, not an unresolved apontamento).
RESULTADOS_COM_APONTAMENTO: tuple[str, ...] = ("positiva",)


def rotulo_certidao(tipo: str, resultado: Optional[str]) -> str:
    modelo = next(c[1] for c in CERTIDOES if c[0] == tipo)
    palavra = RESULTADO_ROTULO.get(resultado or "", "")
    return re.sub(r"\s{2,}", " ", modelo.replace("{R}", palavra))


def item_certidao(tipo: str, c: Certidao) -> str:
    """A presented certidão, or — when `nao_emitida` — a PENDENTE line (its
    number and date do not exist, so none is printed; it also becomes a
    pendência letter)."""
    linha = next(x for x in CERTIDOES if x[0] == tipo)
    if c.resultado == "nao_emitida":
        return f"{rotulo_certidao(tipo, None)} – PENDENTE"
    texto = (
        f"{rotulo_certidao(tipo, c.resultado)} – {linha[2]} {c.numero} - emitida em "
        f"{formatar_data_br(c.emitida_em)}"  # type: ignore[arg-type]
    )
    if linha[5]:
        texto += f"; SISTEMA {linha[5]}"
    return texto


def item_matricula_imovel(numero: str, emitida_em) -> str:
    return (
        f"Visualização da Certidão da Matrícula do imóvel nº {matricula_numero(numero)}, "
        f"emitida em {formatar_data_br(emitida_em)}"
    )


#: [§6.1 #14] The imóvel certidão group's label per tipo (migration 118). The
#: `matricula` tipo is absent on purpose — it names the MATRÍCULA's number
#: rather than the document's, so it keeps `item_matricula_imovel`'s wording.
CERTIDOES_IMOVEL_ROTULO: dict[str, str] = {
    "cnd_iptu": "Certidão Negativa de Débitos Municipais (IPTU)",
    "cnd_condominio": "Certidão Negativa de Débitos Condominiais",
}


def item_certidao_imovel(c: CertidaoImovel, *, numero_matricula: Optional[str]) -> str:
    """One line of the imóvel's own certidão group (migration 118)."""
    if c.tipo == "matricula":
        return item_matricula_imovel(numero_matricula or "", c.emitida_em)
    texto = CERTIDOES_IMOVEL_ROTULO[c.tipo]
    if c.numero:
        texto += f" nº {c.numero}"
    return f"{texto} - emitida em {formatar_data_br(c.emitida_em)}"  # type: ignore[arg-type] — gated


# ─── pendências (spec §2.5) ───────────────────────────────────────────────

PENDENCIA_CONDOMINIO = "Certidão negativa de débitos condominiais"
PENDENCIA_CONDOMINIO_PERMUTA = "Certidão negativa de débitos condominiais, cada qual responsável por seu imóvel"
PENDENCIA_DOCUMENTOS = "Cópia de RG, CPF e comprovante de residência atual"
PENDENCIA_MATRICULA = "Certidão de matrícula atualizada do imóvel"
PENDENCIA_CONTAS_CONSUMO = "Comprovantes de quitação e nada consta das contas de consumo (água, luz e gás)"
PENDENCIA_IPTU = "Certidão Negativa de Débitos Municipais (IPTU)"


def pendencia_estado_civil(max_dias: int) -> str:
    return f"Comprovante de estado civil atualizado, emitido há no máximo {max_dias} dias"


def pendencia_baixa_onus(situacao_onus: str) -> str:
    gravame = "alienação fiduciária" if situacao_onus == "alienacao_fiduciaria" else "hipoteca"
    return f"Termo de quitação do financiamento e matrícula com o registro da baixa da {gravame}"


def antigos_proprietarios_texto(pessoas: Sequence[Pessoa]) -> str:
    """[Q9] "o antigo proprietário" / "a antiga proprietária" / "os antigos
    proprietários" / "as antigas proprietárias" (a mixed group is masculine)."""
    generos = [normalizar_genero(p.genero) or "m" for p in pessoas]
    if not generos:
        # Refuse rather than invent a gender for nobody: an empty group means
        # the CALLER decided wrongly that previous owners take part. Silently
        # returning "o antigo proprietário" would put a party in the contract
        # that does not exist in the deal.
        raise ValueError(
            "antigos_proprietarios_texto: nenhum antigo proprietário — "
            "o chamador não deve pedir a frase quando a lista está vazia."
        )
    if len(generos) > 1:
        return "as antigas proprietárias" if all(g == "f" for g in generos) else "os antigos proprietários"
    return "a antiga proprietária" if generos[0] == "f" else "o antigo proprietário"


def pendencia_certidao(tipo: str, nome: str) -> str:
    return f"{rotulo_certidao(tipo, None)} em nome de {nome.upper()}"


# ─── ônus / posse / rescisão / tributos (spec §2.6–2.9) ───────────────────

QUITACOES_ONUS: tuple[str, ...] = ("compradores_prazo", "interveniente_quitante", "parcela")

#: Stored by migration 114, but NO sample contract carries a clause for it
#: (spec §6.1 #11's "already paid, has termo" state). The gate refuses it by
#: name rather than inventing wording — see `derivacao._imovel`.
QUITACAO_ONUS_SEM_REDACAO = "ja_quitado"

#: 🔴 THE STORAGE VOCABULARY, VERBATIM (`atendimento_negociacao_termos.
#: posse_marco`, migration 114). The generator used to say
#: `parcela_financiamento`, which ASSUMED the marco parcela was the
#: financiamento one — true of one sample contract, false in general. Storage
#: generalised it correctly: a marco of `parcela` NAMES its parcela
#: (`posse_marco_parcela_id`), and `posse_marco_texto` prints THAT parcela's
#: computed number. Mapping the other way would have silently printed the
#: wrong parcela whenever the marco was not the financiamento.
MARCOS_POSSE: tuple[str, ...] = ("assinatura", "parcela", "protocolo_registro")


def ato_rotulo(a: AtoCitado) -> str:
    return f"R-{a.numero:02d}" if a.kind == "R" else f"Av.{a.numero:02d}"


def onus_fonte_texto(atos: Sequence[AtoCitado]) -> str:
    if len(atos) == 1:
        return ("no " if atos[0].kind == "R" else "na ") + ato_rotulo(atos[0])
    return "nos atos " + juntar([ato_rotulo(a) for a in atos])


def onus_quitacao_texto(quitacao: str, *, C: Concordancia, ref_saldo: str, ref_clausula_preco: str) -> str:
    if quitacao == "compradores_prazo":
        return f"que deverá ser quitado {C.pelos} {C.NOME}"
    if quitacao == "interveniente_quitante":
        return "que deverá ser quitado pelo sistema interveniente quitante"
    return f"o qual deverá ser quitado conforme determinado na Parcela {ref_saldo} da {ref_clausula_preco}"


def posse_marco_texto(marco: str, *, ref_parcela: str) -> str:
    """`ref_parcela` is the NAMED marco parcela's computed number (migration
    114's `*_marco_parcela_id`), never an assumption about which parcela it is."""
    if marco == "assinatura":
        return "da assinatura do presente contrato"
    if marco == "parcela":
        return f"do recebimento da parcela {ref_parcela}"
    return "da apresentação do protocolo de entrada do registro de imóveis e pagamento da guia de ITBI"


def condicao_posse_frase(anteriores: Sequence[str], *, todas: bool) -> str:
    if todas:
        return ", com a condição que todas as parcelas do preço tenham sido anteriormente e integralmente quitadas"
    if not anteriores:
        return ""
    if len(anteriores) == 1:
        return f", com a condição que a parcela {anteriores[0]} do preço tenha sido anteriormente e integralmente quitada"
    return f", com a condição que as parcelas {juntar(list(anteriores))} do preço tenham sido anteriormente e integralmente quitadas"


def cura_rescisao_frase(dias: Optional[int]) -> str:
    if not dias:
        return ""
    return (
        ", desde que a infração contratual seja apontada em notificação extrajudicial enviada à "
        f"Parte considerada como infratora e não seja sanada no prazo de até {dias_por_extenso(dias, uteis=True)}"
    )


# ─── intermediação (spec §2.16) ───────────────────────────────────────────


def qualificacao_imobiliaria(org: Imobiliaria) -> str:
    texto = org.razao_social or ""
    if org.nome_fantasia:
        texto += f", com nome fantasia de {org.nome_fantasia}"
    texto += f", pessoa jurídica inscrita no CNPJ sob o nº {documento(org.cnpj)[1]}"
    if org.creci_pj:
        texto += f", com inscrição no CRECI sob o nº {org.creci_pj}"
    texto += (
        f", neste ato representada por seu sócio {org.responsavel_nome}, corretor de imóveis "
        f"CRECI {org.responsavel_creci}"
    )
    if org.email:
        texto += f", endereço eletrônico: {org.email.strip().lower()}"
    if org.endereco.logradouro:
        texto += f", com sede na {endereco_texto(org.endereco)}"
    return texto + "."


def qualificacao_intermediario(it: Intermediario) -> str:
    """[§6.1 #21] An EXTERNAL intermediário's qualification (migration 114).

    The office's own intermediação (`corretor_id` set) is qualified from
    `Imobiliaria` by `qualificacao_imobiliaria` instead — same clause, but the
    data lives on the org row, not on the intermediário.

    🔴 GENDER-NEUTRAL BY CONSTRUCTION (2026-09-23). `Intermediario` (`dados.py`)
    carries no `genero` column — unlike `Pessoa`, whose qualification agrees
    per `p.genero` via `concordancia.normalizar_genero` — because neither
    `atendimento_intermediarios` nor `lead_corretores` (migrations 108/025)
    stores one. `corretor de imóveis inscrito` hardcoded the masculine form
    regardless, so a female corretora (contract 08's own human-typed
    reference qualifies RENATA DIAS GONÇALVES as "corretora ... inscrita")
    rendered with the wrong gender every time. `"(a)"` is this file's own
    established convention for a term that must stay correct with no gender
    fact to agree from — see `nacionalidade_flex`'s "brasileiro(a)" above.
    """
    rotulo, numero = documento(it.documento)
    if it.pessoa_tipo == "pj":
        texto = f"{it.nome}, pessoa jurídica inscrita no {rotulo} sob o nº {numero}"
    else:
        texto = f"{it.nome}, corretor(a) de imóveis inscrito(a) no {rotulo} sob o nº {numero}"
    if it.creci:
        texto += f", com inscrição no CRECI sob o nº {it.creci}"
    if it.representante_nome:
        texto += f", neste ato representada por {it.representante_nome}"
        if it.representante_cpf:
            texto += f", CPF {documento(it.representante_cpf)[1]}"
    if it.email:
        texto += f", endereço eletrônico: {it.email.strip().lower()}"
    if it.endereco.logradouro:
        texto += f", com sede na {endereco_texto(it.endereco)}"
    return texto + "."


def corretagem_contratantes(quem: str, *, V: Concordancia, C: Concordancia) -> tuple[str, str, str]:
    """(texto, texto capitalizado, verbo 'contrata').

    `compradores` is migration 114's third payer — the mirror of `vendedores`
    on the other side of the table, so it takes the BUYERS' own agreement
    rather than a second spelling of the sellers'.
    """
    if quem == "vendedores":
        return f"{V.art} {V.NOME}", f"{V.ART} {V.NOME}", V.pl("contrata", "contratam")
    if quem == "compradores":
        return f"{C.art} {C.NOME}", f"{C.ART} {C.NOME}", C.pl("contrata", "contratam")
    return "as PARTES", "As PARTES", "contratam"


def parcelamento_texto(n: Optional[int]) -> str:
    if not n or n == 1:
        return "em uma única parcela"
    return f"em {numero_com_extenso(n, feminino=True, largura=2)} parcelas iguais"


def marcos_texto(nums: Sequence[str]) -> str:
    if len(nums) == 1:
        return f"da Parcela {nums[0]}"
    return f"das Parcelas {juntar(list(nums))}"


def split_corretagem(valor: Decimal, fav: Favorecido) -> str:
    rotulo, numero = documento(fav.cpf_cnpj)
    return (
        f"{brl_por_extenso(valor)}, por meio de depósito bancário em favor de {fav.nome}, "
        f"{rotulo} nº {numero}{banco_texto(fav)}"
    )
