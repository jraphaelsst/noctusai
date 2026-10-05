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
    data_por_extenso,
    dias_por_extenso,
    formatar_data_br,
    formatar_inteiro_br,
    numero_com_extenso,
    percentual_por_extenso,
)
from noctusai_lib.integrations.documents.cpf import format_cpf
from noctusai_lib.integrations.documents.nacionalidade import (
    canonico as _nacionalidade_canonica,
    feminino as _nacionalidade_feminina,
)

from app.modules.card_hub.contrato_gerador.extenso import brl_por_extenso
from app.modules.card_hub.contrato_gerador.concordancia import (
    Concordancia,
    genero_exigido,
    lado as concordancia_lado,
)
from app.modules.card_hub.contrato_gerador.dados import (
    AtoCitado,
    Certidao,
    CertidaoImovel,
    Endereco,
    Favorecido,
    Imobiliaria,
    Intermediario,
    PactoAntenupcial,
    Parcela,
    ParteJuridica,
    Pessoa,
)
from app.modules.card_hub.contrato_gerador.estilo import negrito, nome_parte
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
    # A missing bairro is an aviso upstream (`ENDERECO_SEM_BAIRRO`), never a
    # dangling " -  - ": the segment is simply omitted.
    if (e.bairro or "").strip():
        texto += f" - {e.bairro.strip()}"
    return f"{texto} - {e.cidade}/{(e.uf or '').upper()} – CEP: {cep(e.cep)}"


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


def em_uniao_estavel(p: Pessoa) -> bool:
    """[Migration 198] Lives in união estável: the estado civil says so, OR
    the flag beside a legal status that does not (deal 867's divorciado)."""
    return p.estado_civil == "uniao_estavel" or bool(p.convive_uniao_estavel)


def forma_nucleo(p: Pessoa) -> bool:
    """Pairs with a linked partner in ONE qualificação núcleo — married, or
    in união estável (either way of saying it)."""
    return p.estado_civil == "casado" or em_uniao_estavel(p)


def _uniao_com_estado_proprio(a: Pessoa, b: Optional[Pessoa]) -> bool:
    """[Migration 198] A união estável carried by the FLAG (not by the estado
    civil): each partner is then qualified with their OWN legal status —
    "divorciado, …, que convive em união estável com …, solteira, …"."""
    return any(x is not None and x.convive_uniao_estavel and x.estado_civil != "casado" for x in (a, b))

#: Every estado civil the qualificação has wording for — `derivacao._partes`
#: refuses any other (it would silently drop out of `texto_pessoa`).
ESTADOS_COM_REDACAO: tuple[str, ...] = tuple(_ESTADO_CIVIL_FLEX) + ESTADOS_EM_NUCLEO


def _g(p: Pessoa, m: str, f: str) -> str:
    # Never a default gender — `genero_exigido` refuses (the gate requires it).
    return f if genero_exigido(p.genero, p.nome or p.nome_cadastro or "") == "f" else m


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


def e_brasileiro(p: Pessoa) -> bool:
    """True when the party's nationality reads Brazilian (the legacy typed
    spellings or the seed's canonical gentílico) — the RNE/RNM gate's test."""
    bruto = (p.nacionalidade or "").strip()
    if bruto.lower() in _NACIONALIDADE_BR:
        return True
    return _nacionalidade_canonica(bruto) == "brasileiro"


def rg_texto(p: Pessoa) -> str:
    """"<número>-<ÓRGÃO>" — or the number alone when no órgão is on file
    (an aviso, `RG_SEM_ORGAO_EXPEDIDOR`; never a dangling "-")."""
    orgao = re.sub(r"[\s/]+", "-", (p.rg_orgao or "").strip().upper())
    numero = (p.rg or "").strip()
    return f"{numero}-{orgao}" if orgao else numero


#: [Migration 193] `clientes.identidade_tipo` — the identity documents a
#: foreign party is qualified by instead of the RG (corpus: 3 deals, "RNE").
#: `None`/'rg' is the cédula de identidade (RG). RNM (Registro Nacional
#: Migratório, the RNE's 2018 successor) is the same document class under
#: its current name, printed in the SAME shape.
IDENTIDADES_ESTRANGEIRO: dict[str, str] = {"rne": "RNE", "rnm": "RNM"}
IDENTIDADES_VALIDAS: tuple[str, ...] = ("rg", *IDENTIDADES_ESTRANGEIRO)


def identidade_texto(p: Pessoa) -> str:
    """"portador(a) da cédula de identidade RG <n>-<órgão>" — or, for a
    foreign party (corpus deals 141/866/876), "portador(a) da cédula de
    identidade RNE <n> <órgão>" (the corpus's own spacing: no hyphen)."""
    portador = _g(p, "portador", "portadora")
    sigla = IDENTIDADES_ESTRANGEIRO.get((p.identidade_tipo or "").strip().lower())
    if sigla is None:
        return f"{portador} da cédula de identidade RG {rg_texto(p)}"
    orgao = re.sub(r"\s+", " ", (p.rg_orgao or "").strip().upper())
    return f"{portador} da cédula de identidade {sigla} {(p.rg or '').strip()} {orgao}".rstrip()


#: [Migration 193] A person qualified ALONE whose estado civil is one the
#: núcleo normally says for them (a PJ's representante): the plain word.
_ESTADO_CIVIL_AVULSO = {
    "casado": ("casado", "casada"),
    "uniao_estavel": ("convivente em união estável", "convivente em união estável"),
}


def texto_pessoa(p: Pessoa, *, em_nucleo: bool, avulso: bool = False) -> str:
    # The name is the one bold, upper-case stretch of a qualification — the
    # CPF/RG/address after it stay plain (`estilo.py`: names 68% bold+upper,
    # CPF 0%, the rest of a qualification 3%).
    partes = [nome_parte(p.nome or ""), nacionalidade_flex(p)]
    if not em_nucleo:
        par_ec = _ESTADO_CIVIL_FLEX.get(p.estado_civil or "") or (
            _ESTADO_CIVIL_AVULSO.get(p.estado_civil or "") if avulso else None
        )
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
        f", {identidade_texto(p)}"
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
        if forma_nucleo(p) and par is not None and par.cliente_id not in usados:
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


def pacto_frase(pacto: Optional[PactoAntenupcial]) -> str:
    """[Migration 193] Corpus deal 858, verbatim shape: ", conforme escritura
    de pacto antenupcial, lavrada aos <data>, pelo <tabelionato>, no Livro nº
    <livro>, Página nº <folha>". "" when no pacto was entered — the gate
    (`derivacao._pacto_do_casal`) warns `PACTO_ANTENUPCIAL_NAO_CITADO` when
    the regime needs one (most signed contracts omit the citation) and names
    each missing piece of a half-entered one."""
    if pacto is None or pacto.vazio():
        return ""
    tabelionato = re.sub(r"^(?:o|pelo)\s+", "", (pacto.tabelionato or "").strip(), flags=re.IGNORECASE)
    return (
        f", conforme escritura de pacto antenupcial, lavrada aos {data_por_extenso(pacto.data)}, "  # type: ignore[arg-type] — gated
        f"pelo {tabelionato}, no Livro nº {(pacto.livro or '').strip()}, "
        f"Página nº {(pacto.folha or '').strip()}"
    )


def pacto_do_casal(a: Pessoa, b: Optional[Pessoa]) -> Optional[PactoAntenupcial]:
    """The couple's pacto — either spouse's row carries it (gated equal when
    both do: `PACTO_ANTENUPCIAL_DIVERGENTE`)."""
    for p in (a, b):
        if p is not None and p.pacto is not None and not p.pacto.vazio():
            return p.pacto
    return None


#: [Migration 193] Regimes whose adoption REQUIRES an escritura de pacto
#: antenupcial (CC arts. 1.640 p.ú. / 1.653): separação convencional
#: (`separacao_total` — `separacao_obrigatoria` is the legal one, no pacto),
#: participação final nos aquestos, and comunhão universal on/after the Lei
#: 6.515/77 (before it, comunhão universal WAS the legal regime).
_REGIMES_COM_PACTO = ("separacao_total", "participacao_final_aquestos")


def regime_exige_pacto(
    regime: Optional[str], data_casamento: Optional[date], vigencia_desde: date
) -> Optional[bool]:
    """True / False, or `None` when it depends on a marriage date nobody
    entered (that date is its own `faltando`)."""
    if regime in _REGIMES_COM_PACTO:
        return True
    if regime == "comunhao_universal":
        if data_casamento is None:
            return None
        return data_casamento >= vigencia_desde
    return False


def qualificacao(pessoas: Sequence[Pessoa], *, lei_6515_desde: date) -> str:
    textos: list[str] = []
    for a, b in nucleos(pessoas):
        if b is None:
            textos.append(
                f"{texto_pessoa(a, em_nucleo=False)}, {_residente(a)} na {endereco_texto(a.endereco)}"
            )
            continue
        mesmo_endereco = endereco_texto(a.endereco) == endereco_texto(b.endereco)
        # [198] A flag-carried união estável prints each one's legal status.
        nucleo = not _uniao_com_estado_proprio(a, b)
        if mesmo_endereco:
            ta, tb = texto_pessoa(a, em_nucleo=nucleo), texto_pessoa(b, em_nucleo=nucleo)
            sufixo = f", residentes e domiciliados na {endereco_texto(a.endereco)}"
        else:
            ta = f"{texto_pessoa(a, em_nucleo=nucleo)}, {_residente(a)} na {endereco_texto(a.endereco)}"
            tb = f"{texto_pessoa(b, em_nucleo=nucleo)}, {_residente(b)} na {endereco_texto(b.endereco)}"
            sufixo = ""
        if a.estado_civil != "casado" and (em_uniao_estavel(a) or em_uniao_estavel(b)):
            textos.append(f"{ta}, que convive em união estável com {tb}{sufixo}")
        else:
            lei = lei_6515_frase(a.data_casamento, lei_6515_desde)  # type: ignore[arg-type] — gated
            # Gated (`derivacao._partes` — REGIME_BENS_SEM_REDACAO): an
            # unknown regime is refused, never printed as its raw enum.
            regime = REGIME_EXTENSO[a.regime_bens or ""]
            pacto = pacto_frase(pacto_do_casal(a, b))
            textos.append(f"{ta}, e {tb}, casados no regime da {regime}{lei}{pacto}{sufixo}")
    return ", e ".join(textos)


# ─── anuente / parte PJ (migration 193) ───────────────────────────────────


def qualificacao_anuente(a: Pessoa, conjuge: Pessoa, *, lei_6515_desde: date) -> str:
    """[Migration 193] A seller's spouse/companion who signs without owning
    (corpus: 7 deals). Shape of deals 799/839, verbatim: "<qualificação>,
    casada no regime da <regime>, na vigência da Lei 6.515/77 com <NOME DO
    VENDEDOR>, já qualificado anteriormente"; a companion takes deal 867's
    "que convive em união estável com". The address is printed only when it
    differs from the seller's (the corpus states it once, on the seller)."""
    texto = texto_pessoa(a, em_nucleo=not _uniao_com_estado_proprio(a, conjuge))
    nome_conjuge = nome_parte(conjuge.nome or "")
    ja = _g(conjuge, "já qualificado", "já qualificada")
    if a.estado_civil != "casado" and (em_uniao_estavel(a) or em_uniao_estavel(conjuge)):
        texto += f", que convive em união estável com {nome_conjuge}, {ja} anteriormente"
    else:
        lei = lei_6515_frase(a.data_casamento, lei_6515_desde)  # type: ignore[arg-type] — gated
        regime = REGIME_EXTENSO[a.regime_bens or ""]
        pacto = pacto_frase(pacto_do_casal(a, conjuge))
        texto += (
            f", {_g(a, 'casado', 'casada')} no regime da {regime}{lei}{pacto} com "
            f"{nome_conjuge}, {ja} anteriormente"
        )
    if endereco_texto(a.endereco) != endereco_texto(conjuge.endereco):
        texto += f", {_residente(a)} na {endereco_texto(a.endereco)}"
    return texto


def denominacao_anuentes(anuentes: Sequence[Pessoa]) -> str:
    """"denominado/denominada/denominados/denominadas neste ato simplesmente
    "ANUENTE(S)"" — corpus 799/839 write "denominadas" for two women."""
    generos = [genero_exigido(p.genero, p.nome or p.nome_cadastro or "") for p in anuentes]
    if len(generos) == 1:
        palavra, rotulo = ("denominada" if generos[0] == "f" else "denominado"), "ANUENTE"
    else:
        palavra = "denominadas" if all(g == "f" for g in generos) else "denominados"
        rotulo = "ANUENTES"
    return f'{palavra} neste ato simplesmente {negrito(chr(34) + rotulo + chr(34))}'


def linhas_anuentes(textos: Sequence[str], anuentes: Sequence[Pessoa]) -> list[str]:
    """One paragraph for one anuente; a numbered list ("1-) …;") for several,
    the denomination closing the last item — corpus 799/839."""
    if not textos:
        return []
    fecho = denominacao_anuentes(anuentes)
    if len(textos) == 1:
        return [f"{textos[0]}, {fecho};"]
    linhas = [f"{i}-) {t};" for i, t in enumerate(textos[:-1], start=1)]
    linhas.append(f"{len(textos)}-) {textos[-1]}, {fecho};")
    return linhas


def _cargo_representante(r: Pessoa) -> tuple[str, str]:
    """(qualifying phrase, signature label) — corpus deal 866: "representada
    neste ato por sua sócia e administradora …" / "Sócia-Administradora"."""
    if genero_exigido(r.genero, r.nome or r.nome_cadastro or "") == "f":
        return "sua sócia e administradora", "Sócia-Administradora"
    return "seu sócio e administrador", "Sócio-Administrador"


def qualificacao_pj(pj: ParteJuridica, representante: Pessoa) -> str:
    """[Migration 193] A company party — corpus deal 866, verbatim shape:
    "<RAZÃO SOCIAL>, pessoa jurídica de direito privado, devidamente inscrita
    sob CNPJ nº <cnpj> e NIRE <nire>, com sede na <endereço>, representada
    neste ato por sua sócia e administradora <qualificação PF>, residente e
    domiciliada na <endereço>". Derived from ONE signed contract — the gate
    always raises `PJ_REDACAO_A_CONFIRMAR` and a legal-review item."""
    cargo, _rotulo = _cargo_representante(representante)
    return (
        f"{nome_parte(pj.razao_social or '')}, pessoa jurídica de direito privado, devidamente "
        f"inscrita sob CNPJ nº {documento(pj.cnpj)[1]} e NIRE {(pj.nire or '').strip()}, com sede na "
        f"{endereco_texto(pj.sede)}, representada neste ato por {cargo} "
        f"{texto_pessoa(representante, em_nucleo=False, avulso=True)}, "
        f"{_residente(representante)} na {endereco_texto(representante.endereco)}"
    )


def signatario_pj_linhas(pj: ParteJuridica, representante: Pessoa) -> list[str]:
    """Digital signature block of a PJ — corpus 866: "<RAZÃO SOCIAL> / Por:
    <REPRESENTANTE> / Sócia-Administradora" (e-mail beside the signer, [Q14])."""
    _cargo, rotulo = _cargo_representante(representante)
    return [
        nome_parte(pj.razao_social or ""),
        f"Por: {signatario_linha(representante)}",
        rotulo,
    ]


def assinante_fisico_pj(pj: ParteJuridica, representante: Pessoa) -> dict[str, str]:
    """Física signature block of a PJ: the company, then who signs for it,
    their cargo and CPF (corpus 866: "Por: … / Sócia-Administradora / CPF")."""
    _cargo, rotulo = _cargo_representante(representante)
    return {
        "nome": (pj.razao_social or "").upper(),
        "documento": " – ".join(
            x for x in (
                f"Por: {(representante.nome or '').upper()}", rotulo, documento_linha(representante.cpf),
            ) if x
        ),
    }


def nome_email_linha(nome: Optional[str], email: Optional[str]) -> str:
    """[Q14] NOME (upper) + the e-mail spaced beside it when present — the
    shape both the signing platform and Contract 08's own witness block need
    (`PRISCILA ANTONIA HIJAZI              priscilahijazi@hotmail.com`).
    Falls back to the bare name when there is no e-mail to show — never a
    blank/placeholder value in a legal instrument."""
    n = nome_parte(nome or "")
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


#: Lower-case connectives a Title-Cased vocabulary label may carry ("Cartão de
#: Crédito") without stopping being a label.
_FORMA_CONECTIVOS = frozenset(
    {"a", "o", "e", "de", "da", "do", "das", "dos", "em", "no", "na", "com", "por", "via", "para"}
)


def _sigla(palavra: str) -> bool:
    return len(palavra) > 1 and palavra.isupper()


def _forma(forma: Optional[str]) -> str:
    """`forma_pagamento` as it reads after "por meio de …".

    Two shapes reach here. A vocabulary LABEL (`FORMAS_PAGAMENTO_SUGERIDAS`,
    Title Case: "Transferência", "Cartão de Crédito") reads in lower case,
    acronyms kept ("PIX"). Free PROSE (the field is unbounded since
    2026-10-03: "Transferência bancária com recursos liberados pela Caixa
    Econômica Federal") keeps what the person typed — only its sentence-initial
    capital drops — because lower-casing it whole would print "caixa econômica
    federal". Whitespace runs collapse (a pasted double space would trip the
    lint's spacing rule)."""
    f = " ".join((forma or "").split())
    if not f or f.isupper():
        return f
    palavras = f.split(" ")
    rotulo = all(
        not p[:1].isalpha() or p[:1].isupper() or p.lower() in _FORMA_CONECTIVOS
        for p in palavras
    )
    if rotulo:
        return " ".join(p if _sigla(p) else p.lower() for p in palavras)
    if not _sigla(palavras[0]):
        palavras[0] = palavras[0][:1].lower() + palavras[0][1:]
    return " ".join(palavras)


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


def _momento_parcela(p: Parcela, *, tem_financiamento: bool, ref_financiamento: str) -> str:
    """WHEN a parcela is paid — its date, the financing contract (an
    intermediária in a financed deal), or the agreed evento."""
    if p.vencimento:
        return f"com vencimento em {formatar_data_br(p.vencimento)}"
    if p.tipo == "intermediaria" and tem_financiamento:
        return (
            "por ocasião da assinatura do Contrato de Financiamento Imobiliário, "
            f"previsto para quitação da Parcela {ref_financiamento}"
        )
    return (p.evento or "").strip()


def _em_favor_de(favorecido: Favorecido, vendedor_favorecido: Optional[Pessoa]) -> str:
    """"em favor do VENDEDOR: NOME, CPF: …, Banco …" — the payee and the
    account it is paid into (spec §5.1)."""
    if vendedor_favorecido is not None:
        gv = concordancia_lado(
            [genero_exigido(vendedor_favorecido.genero, vendedor_favorecido.nome or "")],
            "vendedor",
        )
        em_favor = f"em favor {gv.dos} {negrito(gv.NOME)}: "
    else:
        em_favor = "em favor de "
    rotulo, numero = documento(favorecido.cpf_cnpj)
    return f"{em_favor}{nome_parte(favorecido.nome)}, {rotulo}: {numero}{banco_texto(favorecido)}"


def _frase_favorecido(
    forma_pagamento: Optional[str],
    favorecido: Favorecido,
    *,
    repetido: bool,
    vendedor_favorecido: Optional[Pessoa],
) -> str:
    if repetido:
        return f"por meio de {_forma(forma_pagamento)} na mesma conta corrente anteriormente informada"
    return (
        f"por meio de {_forma(forma_pagamento)} a ser realizada "
        f"{_em_favor_de(favorecido, vendedor_favorecido)}"
    )


def _quitacao_sinal(V: Concordancia, C: Concordancia, *, varias_contas: bool) -> str:
    conta = "nas contas correntes ora indicadas" if varias_contas else "na conta corrente ora indicada"
    return (
        f"operando-se automaticamente a quitação em favor {C.dos} {C.NOME.title()} com o "
        f"efetivo crédito {conta} {V.pelos} {V.NOME.title()}"
    )


_CABECA_SINAL = "Sinal e princípio de pagamento:"


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
    fgts_valores: Optional[tuple[Decimal, Decimal]] = None,
    dividida: bool = False,
    divisao_ref: Optional[str] = None,
) -> str:
    """Everything after "Parcela NN:" for one parcela.

    - `fgts_valores` = (FGTS, financiado) when the financing parcela's split
      is known (migration 192's `valor_fgts`, or a folded `fgts` parcela).
      The printed value is their sum.
    - `dividida` — the parcela is split among several favorecidos (192): the
      line ends "… a ser realizada da seguinte forma:" and the shares follow
      as sub-items (`subitem_divisao`).
    - `divisao_ref` — the parcela repeats an earlier split's accounts AND
      proportions: the office writes "nas mesmas contas correntes e
      proporções informadas na Parcela NN".
    """
    valor = negrito(brl_por_extenso(p.valor))  # type: ignore[arg-type] — gate guarantees it
    if p.tipo == "financiamento":
        # [Q6, revised 2026-10-03] FGTS + financiamento are ONE parcela, in
        # the wording of the office's SIGNED contracts (catalog §2): the split
        # form (5 deals) when the amounts are known, else the combined form
        # (871, 888). The old "através do uso de FGTS e financiamento
        # imobiliário" appears in none of the 34.
        if fgts_valores is not None:
            valor_fgts, valor_fin = fgts_valores
            valor = (
                f"{negrito(brl_por_extenso(valor_fgts + valor_fin))}, onde será utilizado "
                f"{negrito(brl_por_extenso(valor_fgts))}, por meio do uso das contas vinculadas ao FGTS e "
                f"{negrito(brl_por_extenso(valor_fin))} por meio de recursos de financiamento imobiliário "
                "e/ou moeda corrente nacional"
            )
        elif fgts:
            valor += (
                ", por meio do uso das contas vinculadas ao FGTS e de recursos de financiamento "
                "imobiliário e/ou moeda corrente nacional"
            )
        else:
            valor += ", por meio de recursos de financiamento imobiliário e/ou moeda corrente nacional"
    elif p.tipo == "saldo":
        # [Q7] saldo = payoff of the seller's existing financing.
        valor += ", destinada à quitação do saldo devedor do financiamento que onera o imóvel"
    frases = [valor, _momento_parcela(p, tem_financiamento=tem_financiamento, ref_financiamento=ref_financiamento)]

    if divisao_ref is not None:
        frases.append(
            f"por meio de {_forma(p.forma_pagamento)} nas mesmas contas correntes e proporções "
            f"informadas na Parcela {divisao_ref}"
        )
    elif favorecido is not None and not dividida:
        frases.append(
            _frase_favorecido(
                p.forma_pagamento, favorecido,
                repetido=favorecido_repetido, vendedor_favorecido=vendedor_favorecido,
            )
        )
    elif not dividida and p.tipo in ("intermediaria", "direta", "saldo") and (p.forma_pagamento or "").strip():
        # [P5 F8] A parcela with no favorecido (aviso `PARCELA_SEM_FAVORECIDO`):
        # the forma alone, no account — corpus 783 "por meio de recursos de
        # consórcio imobiliário".
        frases.append(f"por meio de {_forma(p.forma_pagamento)}")
    if juros_am is not None:
        frases.append(f"acrescidos de {pct_simples(juros_am)} de juros a.m., calculados pro rata die")
    if p.tipo == "sinal":
        frases.append(_quitacao_sinal(V, C, varias_contas=dividida or divisao_ref is not None))
    cabeca = " " + negrito(_CABECA_SINAL) if p.tipo == "sinal" else ""
    if dividida:
        frases.append(f"por meio de {_forma(p.forma_pagamento)} a ser realizada da seguinte forma")
        return f"{cabeca} " + ", ".join(frases) + ":"
    return f"{cabeca} " + ", ".join(frases) + "."


def subitem_divisao(
    num: str,
    indice: int,
    valor: Decimal,
    percentual: Optional[Decimal],
    favorecido: Favorecido,
    *,
    repetido: bool,
    vendedor_favorecido: Optional[Pessoa],
) -> str:
    """[Migration 192] One share of a divided parcela, in the office's two
    signed layouts merged (catalog §2): "1.1) {VALOR} em favor de …" and
    "{VALOR}, correspondentes a {PCT}% ({extenso}) da parcela, em favor …".
    The template adds the closing ';' / '.'."""
    texto = f"{num}.{indice}) {negrito(brl_por_extenso(valor))}"
    if percentual is not None:
        texto += f", correspondentes a {percentual_por_extenso(percentual)} da parcela,"
    if repetido:
        return f"{texto} em favor de {nome_parte(favorecido.nome)}, na mesma conta corrente anteriormente informada"
    return f"{texto} {_em_favor_de(favorecido, vendedor_favorecido)}"


def texto_sinal_em_partes(
    partes: Sequence[tuple[Parcela, Favorecido, bool, Optional[Pessoa]]],
    *,
    V: Concordancia,
    C: Concordancia,
    tem_financiamento: bool,
    ref_financiamento: str,
) -> str:
    """More than one sinal parcela, printed as ONE parcela paid in tranches —
    signed contract 783: "Sinal e princípio de pagamento: {TOTAL}, a serem
    pagos da seguinte forma: {A} no ato da assinatura …, e {B} … com
    vencimento …, operando-se automaticamente a quitação …". Each tranche is
    `(parcela, favorecido, favorecido_repetido, vendedor_favorecido)`; every
    field is gated (valor, momento, favorecido, forma)."""
    total = sum((p.valor for p, _f, _r, _v in partes), Decimal("0"))  # type: ignore[misc]
    itens = []
    for p, fav, repetido, vendedor in partes:
        momento = _momento_parcela(p, tem_financiamento=tem_financiamento, ref_financiamento=ref_financiamento)
        itens.append(
            f"{negrito(brl_por_extenso(p.valor))} {momento}, "  # type: ignore[arg-type] — gated
            + _frase_favorecido(p.forma_pagamento, fav, repetido=repetido, vendedor_favorecido=vendedor)
        )
    enumeracao = ", ".join(itens[:-1]) + ", e " + itens[-1]
    varias_contas = len({fav.id for _p, fav, _r, _v in partes}) > 1
    return (
        f" {negrito(_CABECA_SINAL)} {negrito(brl_por_extenso(total))}, a serem pagos da seguinte forma: "
        f"{enumeracao}, {_quitacao_sinal(V, C, varias_contas=varias_contas)}."
    )


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
    """`resultado=None` is the deliberate un-qualified label (a PENDENTE line,
    a readiness message). Any OTHER value must be a known one — the gate
    refuses an unknown resultado (`CERTIDAO_RESULTADO_DESCONHECIDO`), so one
    reaching here is a gate/template disagreement: refuse, never print an
    empty slot ("Certidão  de Débitos...")."""
    modelo = next(c[1] for c in CERTIDOES if c[0] == tipo)
    palavra = "" if resultado is None else RESULTADO_ROTULO[resultado]
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
#: The un-qualified label (readiness messages); the PRINTED line carries the
#: certidão's own resultado (`CERTIDOES_IMOVEL_MODELO`).
CERTIDOES_IMOVEL_ROTULO: dict[str, str] = {
    "cnd_iptu": "Certidão Negativa de Débitos Municipais (IPTU)",
    "cnd_condominio": "Certidão Negativa de Débitos Condominiais",
}

#: [2026-10-03 bug fix] The printed label WITH the resultado — a positive
#: IPTU certidão used to print "Certidão Negativa de …" (only an aviso said
#: otherwise). Same `{R}` model + `RESULTADO_ROTULO` as a party's certidão.
CERTIDOES_IMOVEL_MODELO: dict[str, str] = {
    "cnd_iptu": "Certidão {R} de Débitos Municipais (IPTU)",
    "cnd_condominio": "Certidão {R} de Débitos Condominiais",
}


def item_certidao_imovel(c: CertidaoImovel, *, numero_matricula: Optional[str]) -> str:
    """One line of the imóvel's own certidão group (migration 118). The gate
    (`derivacao._certidoes_do_imovel`) refuses a missing or unknown resultado,
    so `RESULTADO_ROTULO[c.resultado]` never misses here."""
    if c.tipo == "matricula":
        return item_matricula_imovel(numero_matricula or "", c.emitida_em)
    texto = CERTIDOES_IMOVEL_MODELO[c.tipo].replace("{R}", RESULTADO_ROTULO[c.resultado or ""])
    if c.numero:
        texto += f" nº {c.numero}"
    return f"{texto} - emitida em {formatar_data_br(c.emitida_em)}"  # type: ignore[arg-type] — gated


# ─── pendências (spec §2.5) ───────────────────────────────────────────────

PENDENCIA_CONDOMINIO = "Certidão negativa de despesas condominiais relativas ao imóvel"
PENDENCIA_CONDOMINIO_PERMUTA = "Certidão negativa de despesas condominiais, cada qual responsável por seu imóvel"
PENDENCIA_DOCUMENTOS = "Cópia de RG, CPF e comprovante de residência atual"
PENDENCIA_MATRICULA = "Matrícula Atualizada do Imóvel"
#: Signed corpus (2026-10-05): two items, in this order — the copy of the last
#: bills (65 contracts) and the nada-consta extract (47) — each closing with the
#: condomínio carve-out.
_SEM_CONDOMINIO = "As que estiverem incluídas no condomínio, não são necessárias a apresentação"
PENDENCIAS_CONTAS_CONSUMO: tuple[str, ...] = (
    f"Cópia das últimas contas de consumo do imóvel - água, luz, gás. {_SEM_CONDOMINIO}",
    f"Extrato de nada consta das contas de consumo. {_SEM_CONDOMINIO}",
)
PENDENCIA_IPTU = "Certidão Negativa de Débitos Municipais (IPTU)"


def pendencia_estado_civil(max_dias: int) -> str:
    # 78 signed contracts: "Comprovante de estado civil, com data de emissão
    # inferior a N dias" (N is the office policy, `certidao_estado_civil_max_dias`).
    return f"Comprovante de estado civil, com data de emissão inferior a {max_dias} dias"


def dias_simples(n: int) -> str:
    """`10` -> "10 dias corridos" — the pendências deadline as the office writes
    it (74 signed contracts; 8 add the extenso)."""
    return f"{n} dia corrido" if n == 1 else f"{n} dias corridos"


def pendencia_baixa_onus(situacao_onus: str) -> str:
    gravame = "alienação fiduciária" if situacao_onus == "alienacao_fiduciaria" else "hipoteca"
    return f"Termo de quitação do financiamento e matrícula com o registro da baixa da {gravame}"


def pendencia_matricula_baixa(situacao_onus: str) -> str:
    """[Migration 193] `ja_quitado` — corpus deal 867's pendência, verbatim:
    "Matrícula Atualizada do Imóvel com a baixa da alienação fiduciária"."""
    gravame = "alienação fiduciária" if situacao_onus == "alienacao_fiduciaria" else "hipoteca"
    return f"Matrícula Atualizada do Imóvel com a baixa da {gravame}"


def antigos_proprietarios_texto(pessoas: Sequence[Pessoa], *, empresas: Sequence[object] = ()) -> str:
    """[Q9] "o antigo proprietário" / "a antiga proprietária" / "os antigos
    proprietários" / "as antigas proprietárias" (a mixed group is masculine).
    A company antigo (`empresas`, P5) agrees as "a empresa": feminine."""
    generos = [genero_exigido(p.genero, p.nome or p.nome_cadastro or "") for p in pessoas]
    generos += ["f"] * len(empresas)
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

#: [Migration 192] The seller pays the lien off by bank slip within
#: `Termos.onus_prazo_dias` — 2 signed contracts (catalog §4).
QUITACAO_ONUS_VENDEDORES_BOLETO = "vendedores_boleto"

QUITACOES_ONUS: tuple[str, ...] = (
    "compradores_prazo", "interveniente_quitante", "parcela", QUITACAO_ONUS_VENDEDORES_BOLETO,
)

#: [Migration 193] The "already paid, baixa requested" state (spec §6.1 #11).
#: Worded since the corpus catalog found it in signed deal 867 — it is NOT a
#: saldo-devedor quitação (nothing is left to pay), so it is not in
#: `QUITACOES_ONUS`: `derivacao.derivar_switches` turns `tem_saldo_devedor`
#: off and `tem_onus_ja_quitado` on.
QUITACAO_ONUS_JA_QUITADO = "ja_quitado"


def onus_ja_quitado_frase(
    situacao_onus: str, ato: AtoCitado, protocolo_em: date, cidade_registro: str,
    *, V: Concordancia, C: Concordancia,
) -> str:
    """Corpus deal 867's objeto paragraph, verbatim shape (after the
    "Parágrafo …:" label)."""
    gravame = "Alienação Fiduciária" if situacao_onus == "alienacao_fiduciaria" else "Hipoteca"
    return (
        f"{C.ART} {negrito(C.NOME)} {C.pl('declara', 'declaram')} ter conhecimento de que {V.art} "
        f"{negrito(V.NOME)} {V.pl('protocolou', 'protocolaram')}, em {formatar_data_br(protocolo_em)}, junto ao "
        f"Registro de Imóveis de {cidade_registro}, o requerimento de baixa da {gravame} registrada sob o "
        f"{ato_rotulo(ato)} da matrícula do imóvel, estando {C.g('ciente', 'ciente', 'cientes')} de que a "
        "efetivação da referida baixa depende da conclusão do procedimento registral pelo Oficial competente."
    )


def usufruto_frase(*, V: Concordancia, C: Concordancia) -> str:
    """[Migration 193] Corpus deal 839's objeto paragraph, verbatim shape —
    the usufruto's baixa as a precondition of the buyers' financing."""
    return (
        f"{V.ART} {negrito(V.NOME)} {V.pl('declara', 'declaram')} estar {V.g('ciente', 'ciente', 'cientes')} "
        "da necessidade de lavratura de escritura pública de baixa do usufruto, como condição prévia ao "
        f"início do processo junto à instituição financeira a ser escolhida {C.pelos} {negrito(C.NOME)} "
        "para fins de financiamento imobiliário."
    )


# ─── cartório de registro (migration 193) ─────────────────────────────────

#: A `numero_registro_imoveis` reading — the matrícula heading as
#: `find_cartorio` returns it, or as the operator typed it: "1º OFICIAL DE
#: REGISTRO DE IMÓVEIS DE COTIA", "SERVENTIA DO REGISTRO DE IMÓVEIS de Cotia -
#: CNS: 11991-7", "OFICIAL DE REGISTRO DE IMÓVEIS DA COMARCA DE SÃO PAULO/SP",
#: "LIVRO Nº 2 - REGISTRO GERAL | SERVENTIA DO REGISTRO DE IMÓVEIS de Cotia"
#: (a book header riding in front — prod, 2026-10-03), "2º Oficial de Registro
#: de Imóveis, Títulos e Documentos da Comarca de Cotia".
#:
#: The value is split into segments on `|` / line breaks and each segment is
#: SEARCHED (not anchored): a leading header or a CNS tail is not part of
#: the registry's name. The ordinal is only the one written right in front
#: of the office noun with an ordinal mark ("1º", "2.º", "3o") — a book
#: number ("LIVRO Nº 2") is never read as the cartório's ordinal.
_CARTORIO_RE = re.compile(
    r"(?:(?<![\w.])(?P<ord>\d{1,2})\s*\.?\s*[ºo°ª]\.?\s+(?:[A-Za-zÀ-ÿ]+\s+){0,3}?)?"
    r"registro\s+(?:de\s+im[óo]veis|imobili[áa]rio)"
    # "…, Títulos e Documentos e Civil de Pessoa Jurídica" — the office's
    # other attributions, never the city.
    r"(?:[,\s]+(?:t[íi]tulos|documentos|civil|civis|pessoas?|jur[íi]dicas?|naturais|anexos|e)\b"
    r"(?:\s+(?:de|da|do)(?=\s+(?:pessoas?|t[íi]tulos)\b))?)*"
    r"\s*,?\s+(?:(?:da|de)\s+comarca\s+)?(?:de|da|do|dos|das|em)\s+"
    r"(?P<cidade>[A-Za-zÀ-ÿ'][A-Za-zÀ-ÿ' ]*?)"
    r"(?=\s*(?:$|[/\-–—,;:(.|]|\bCNS\b)|(?-i:\s+(?:AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN"
    r"|RS|RO|RR|SC|SP|SE|TO))\s*$)",
    re.IGNORECASE,
)
_CARTORIO_SEPARADORES = re.compile(r"[|\n\r]+")
_CONECTIVOS = {"de", "da", "do", "das", "dos", "e"}


def cidade_titulo(cidade: str) -> str:
    palavras = re.sub(r"\s+", " ", cidade).strip().lower().split(" ")
    return " ".join(
        w if (i > 0 and w in _CONECTIVOS) else w[:1].upper() + w[1:]
        for i, w in enumerate(palavras)
    )


def _cartorio_do_segmento(segmento: str) -> Optional[tuple[Optional[int], str]]:
    m = _CARTORIO_RE.search(segmento)
    if not m:
        return None
    cidade = m.group("cidade").strip()
    # "… DA CAPITAL" names no city by itself (which capital is a UF fact the
    # reading does not carry) — a named gap, never "de Capital".
    if not cidade or cidade.lower() == "capital":
        return None
    ordinal = int(m.group("ord")) if m.group("ord") else None
    return ordinal, cidade_titulo(cidade)


def cartorio_partes(valor: Optional[str]) -> Optional[tuple[Optional[int], str]]:
    """(ordinal, cidade) read off a `numero_registro_imoveis` value, or
    `None` when no city can be read (a bare CNS, "da Capital", free text) or
    when two segments name DIFFERENT registries — the gate names it
    (`imovel.numero_registro_imoveis`), never a guess."""
    lidos = {
        partes
        for segmento in _CARTORIO_SEPARADORES.split(valor or "")
        if (partes := _cartorio_do_segmento(segmento)) is not None
    }
    if len(lidos) != 1:
        return None
    return next(iter(lidos))


def cartorio_texto(valor: Optional[str]) -> Optional[str]:
    """[Corpus catalog §6, 34/34 signed CCVs] "Cartório de Registro de Imóveis
    de <Cidade>" — prefixed "<N>º" when the registry carries an ordinal (the
    corpus's "{N}º Cartório de Registro de Imóveis de {CIDADE}"). The heading
    as transcribed ("SERVENTIA DO REGISTRO DE IMÓVEIS de Cotia") is never
    printed: no signed contract uses it."""
    partes = cartorio_partes(valor)
    if partes is None:
        return None
    ordinal, cidade = partes
    prefixo = f"{ordinal}º " if ordinal else ""
    return f"{prefixo}Cartório de Registro de Imóveis de {cidade}"


# ─── texto livre do operador (migration 193) ──────────────────────────────


def paragrafos_livres(texto: Optional[str]) -> list[str]:
    """Operator-typed obligations, VERBATIM, one paragraph per non-blank line
    (a Word paragraph cannot hold a line break of the template's own)."""
    return [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]

#: 🔴 THE STORAGE VOCABULARY, VERBATIM (`atendimento_negociacao_termos.
#: posse_marco`, migration 114). The generator used to say
#: `parcela_financiamento`, which ASSUMED the marco parcela was the
#: financiamento one — true of one sample contract, false in general. Storage
#: generalised it correctly: a marco of `parcela` NAMES its parcela
#: (`posse_marco_parcela_id`), and `posse_marco_texto` prints THAT parcela's
#: computed number. Mapping the other way would have silently printed the
#: wrong parcela whenever the marco was not the financiamento.
MARCOS_POSSE_PERMUTA: tuple[str, ...] = ("assinatura", "parcela", "protocolo_registro")
#: The imóvel's posse may also fall on a fixed calendar date (migration 201) —
#: the permuta imóvel's may not (the DB CHECK on `permuta_posse_marco` keeps 3).
MARCOS_POSSE: tuple[str, ...] = (*MARCOS_POSSE_PERMUTA, "data_fixa")


def ato_rotulo(a: AtoCitado) -> str:
    return f"R-{a.numero:02d}" if a.kind == "R" else f"Av.{a.numero:02d}"


def onus_fonte_texto(atos: Sequence[AtoCitado]) -> str:
    if len(atos) == 1:
        return ("no " if atos[0].kind == "R" else "na ") + ato_rotulo(atos[0])
    return "nos atos " + juntar([ato_rotulo(a) for a in atos])


def onus_quitacao_texto(
    quitacao: str,
    *,
    C: Concordancia,
    ref_saldo: str,
    ref_clausula_preco: str,
    V: Optional[Concordancia] = None,
    prazo_dias: Optional[int] = None,
) -> str:
    if quitacao == QUITACAO_ONUS_VENDEDORES_BOLETO:
        # Signed contract 884, verbatim but for the agreement: "o qual deverá
        # ser quitado através de boleto bancário emitido pela instituição
        # financeira responsável, onde OS VENDEDORES terão o prazo de até N
        # dias corridos para realizar a quitação e apresentar o comprovante
        # de pagamento." Gated: `V` + `negociacao.onus_prazo_dias`.
        if V is None or not prazo_dias:
            raise ValueError("onus_quitacao_texto: boleto exige V e prazo_dias (o gate garante)")
        return (
            "o qual deverá ser quitado através de boleto bancário emitido pela instituição financeira "
            f"responsável, onde {V.ART} {negrito(V.NOME)} {V.pl('terá', 'terão')} o prazo de até "
            f"{dias_por_extenso(prazo_dias)} para realizar a quitação e apresentar o comprovante de pagamento"
        )
    if quitacao == "compradores_prazo":
        return f"que deverá ser quitado {C.pelos} {negrito(C.NOME)}"
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


#: How a posse prazo is introduced — the template's three sites word it
#: differently (the corpus' own wording, kept byte-for-byte).
POSSE_INTRO_EM_ATE = "em até {dias} a contar {marco}"
POSSE_INTRO_PRAZO_MAXIMO = "no prazo máximo de {dias} a contar {marco}"
POSSE_INTRO_PRAZO_MAXIMO_VIRGULA = "no prazo máximo de {dias}, a contar {marco}"


def posse_concomitante_texto(marco: str, *, ref_parcela: str) -> str:
    """`posse_prazo_dias = 0` — the posse is delivered AT the marco, not N
    days after it. Signed corpus wording: "concomitante com o recebimento da
    Parcela 04" (876 and 6 more), "na apresentação do protocolo de entrada do
    Registro de Imóveis e pagamento da guia do ITBI" (863)."""
    if marco == "assinatura":
        return "concomitante com a assinatura do presente contrato"
    if marco == "parcela":
        return f"concomitante com o recebimento da parcela {ref_parcela}"
    return "na apresentação do protocolo de entrada do registro de imóveis e pagamento da guia de ITBI"


def posse_prazo_texto(
    prazo: Optional[int],
    marco: str,
    *,
    ref_parcela: str,
    data: Optional[date] = None,
    intro: str = POSSE_INTRO_EM_ATE,
) -> str:
    """The whole posse timing phrase. `data_fixa` prints the date ("na data de
    30 de novembro de 2026", deal 859); prazo 0 prints the concomitant wording
    — never "0 dias"; a positive prazo prints `intro` (N days from the marco).
    Gated by `derivacao._posse`: the date / prazo this needs is present."""
    if marco == "data_fixa":
        if data is None:
            raise ValueError("posse_prazo_texto: data_fixa exige a data (o gate garante)")
        return f"na data de {data_por_extenso(data)}"
    if prazo is None:
        raise ValueError("posse_prazo_texto: prazo ausente (o gate garante)")
    if prazo == 0:
        return posse_concomitante_texto(marco, ref_parcela=ref_parcela)
    return intro.format(dias=dias_por_extenso(prazo), marco=posse_marco_texto(marco, ref_parcela=ref_parcela))


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
    texto = nome_parte(org.razao_social or "")
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
        texto = f"{nome_parte(it.nome)}, pessoa jurídica inscrita no {rotulo} sob o nº {numero}"
    else:
        texto = f"{nome_parte(it.nome)}, corretor(a) de imóveis inscrito(a) no {rotulo} sob o nº {numero}"
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
        return f"{V.art} {negrito(V.NOME)}", f"{V.ART} {negrito(V.NOME)}", V.pl("contrata", "contratam")
    if quem == "compradores":
        return f"{C.art} {negrito(C.NOME)}", f"{C.ART} {negrito(C.NOME)}", C.pl("contrata", "contratam")
    return f"as {negrito('PARTES')}", f"As {negrito('PARTES')}", "contratam"


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
        f"{negrito(brl_por_extenso(valor))}, por meio de depósito bancário em favor de {nome_parte(fav.nome)}, "
        f"{rotulo} nº {numero}{banco_texto(fav)}"
    )
