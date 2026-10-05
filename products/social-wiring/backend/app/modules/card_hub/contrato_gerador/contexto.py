"""`DadosContrato` -> the template context (spec §3 placeholder dictionary).

Only reached after `derivacao.avaliar` returned `pronto` — every value used
here has been gated present. Money stays `Decimal` until `brl()` prints it.

The placeholder KEYS are unchanged by the F6 wiring: what moved is where each
value is read FROM (`termos` / `permuta_imoveis` / the imóvel's own certidões
instead of a side-car), which is why `modelo_texto` needed no edit at all.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from noctusai_lib.domain.texto_ptbr import (
    CENTAVO,
    data_por_extenso,
    numero_com_extenso,
    dias_por_extenso,
    percentual_por_extenso,
)
from noctusai_lib.integrations.documents.abnt import clip_ranges, runs_from_ranges
from noctusai_lib.integrations.docx_render import DocxRenderAdapter

from app.modules.card_hub.contrato_gerador.extenso import brl_por_extenso
from app.modules.card_hub.contrato_gerador import frases
from app.modules.card_hub.contrato_gerador.concordancia import genero_exigido, lado
from app.modules.card_hub.contrato_gerador.dados import (
    DadosContrato,
    ParteJuridica,
    Pessoa,
    PermutaImovel,
    anuentes,
    representantes,
    signatarios,
)
from app.modules.card_hub.contrato_gerador.derivacao import (
    _hoje_padrao,
    antigos_no_contrato,
    antigos_proprietarios,
    antigos_proprietarios_pj,
    empresas_impressas_como_parte,
    partes_pj_contratantes,
    anuentes_certificandos,
    conjuge_do_anuente,
    pj_certificandas,
    certidoes_imovel,
    corretagem_marcos,
    empresas_exigidas,
    foro_comarca,
    indice_certidoes,
    grupos_de_parcelas,
    numero_da_parcela,
    numeros_impressos,
    parcelas_antes_de,
    parcelas_ordenadas,
    pessoas_certificadas,
    prazo_pendencias,
    resolver_endereco_posse,
    tipos_exigidos,
    valores_da_divisao,
)
from app.modules.card_hub.contrato_gerador.estilo import negrito, nome_parte
from app.modules.card_hub.contrato_gerador.numeracao import (
    ContadorParagrafos,
    juntar,
    letra,
    numerar_clausulas,
)
from app.modules.card_hub.contrato_gerador.politica import (
    EM_CONDOMINIO_QUANDO_HA_EMPREENDIMENTO,
    Politica,
)

logger = logging.getLogger(__name__)

#: [titulo-aquisitivo-adquirido-quebra-frase] `frase_titulo_aquisitivo`
#: (noctusai_lib) no longer generates a leading "adquirido"/"adquirida" —
#: but the OPERATOR'S CONFIRMED wording (`titulo_aquisitivo_texto`) is
#: free text an operator can still edit or type from scratch, and an
#: existing DB row confirmed BEFORE this fix keeps the old broken shape
#: (migration data is never rewritten). The template frame already supplies
#: the verb ("tornou-se … proprietária"), so a leading "adquirido(a) " here
#: would repeat the same grammar break this fix closes — stripped
#: defensively rather than trusted to have been re-confirmed.
_ADQUIRIDO_INICIAL_RE = re.compile(r"^adquirid[oa]\s+", re.IGNORECASE)


def _sem_adquirido_inicial(texto: str) -> str:
    return _ADQUIRIDO_INICIAL_RE.sub("", texto)


def _generos(pessoas: list[Pessoa]) -> list[str]:
    # Never a default — every signatário's gender is gated (`qualificacao.genero`).
    return [genero_exigido(p.genero, p.nome or p.nome_cadastro or "") for p in pessoas]


def _pj_com_representante(d: DadosContrato, lado_nome: str) -> list[tuple[ParteJuridica, Pessoa]]:
    """[Migration 193] The side's PJ parties, each with the ONE representante
    the gate required (`derivacao._parte_juridica`)."""
    return [
        (pj, representantes(d.vendedores + d.compradores, pj.parte_id)[0])
        for pj in partes_pj_contratantes(d)
        if pj.lado == lado_nome
    ]


def _qualificacao_lado(pessoas: list[Pessoa], pjs: list[tuple[ParteJuridica, Pessoa]], politica: Politica) -> str:
    """The side's persons (núcleos) then its companies — corpus 866's PJ
    wording joined like any other party (", e ")."""
    textos = [frases.qualificacao(pessoas, lei_6515_desde=politica.lei_6515_vigencia_desde)] if pessoas else []
    textos += [frases.qualificacao_pj(pj, rep) for pj, rep in pjs]
    return ", e ".join(textos)


def _descricao_matricula_permuta(i: PermutaImovel, d: DadosContrato) -> str:
    """Migration 136: the SAME narrowing `_descricao_matricula_rica` applies
    to the OBJETO clause, for the SAME reason — a de-furnitured abertura
    still ends in `PROPRIETÁRIOS: …`, which on a resold property names the
    PREVIOUS owners, and this text is quoted into the same deed. Unlike the
    OBJETO clause this is plain text (`{{ p.texto }}` is not a `{{r }}`
    rich-text slot — the permuta parcela line has no formatting story), so
    there is no `formatacao` to carry alongside it.

    Falls back to `i.descricao_matricula` (the whole selection, the pre-136
    behaviour) ONLY when the extraction carries no `descricao_imovel` block
    — surfaced to the operator as the `MATRICULA_PERMUTA_SEM_DESCRICAO_IMOVEL`
    aviso (`derivacao._permuta`) and logged at WARNING, never silent.
    """
    if i.descricao_imovel_texto is not None:
        return i.descricao_imovel_texto
    logger.warning(
        "contrato %s: permuta ativo %s sem bloco 'descricao_imovel' — a "
        "parcela de permuta usa a seleção inteira (comportamento anterior "
        "à migração 136)",
        d.contrato_id,
        i.permuta_ativo_id,
    )
    return i.descricao_matricula or ""  # gated: derivacao._permuta `matricula.permuta.<id>.atos`


def _brl_negrito(valor: Decimal) -> str:
    """"R$ x,xx (por extenso)" in bold — the template's `brl()` and the
    permuta parcela alike (`estilo.py`: money+extenso 81% bold, 20/20 docs)."""
    return negrito(brl_por_extenso(valor))


def _texto_parcela_permuta(valor: Decimal, d: DadosContrato, C, imoveis: list[PermutaImovel]) -> str:  # noqa: N803
    """A permuta parcela (spec §2.3 `p.tipo == 'permuta'`) — its value is the
    parcela's own, and each imóvel is one `permuta_ativos` link (114) carrying
    its own matrícula quote (115). `imoveis` are THIS parcela's (a deal may
    carry several permuta parcelas, each with its own imóveis — signed
    contract 873 is one parcela with two)."""
    # gated: derivacao._partes `qualificacao.nome_oficial` (every signatário)
    nomes = juntar(
        [nome_parte(p.nome or "") for p in signatarios(d.compradores)]
        + [nome_parte(pj.razao_social or "") for pj in d.partes_pj if pj.lado == "comprador"]
    )
    # inscricao_municipal / cidade / matrícula / cartório: gated by derivacao._permuta.
    descricoes = " E ".join(
        f"{_descricao_matricula_permuta(i, d)} Imóvel devidamente cadastrado pela Prefeitura Municipal de "
        f"{i.endereco.cidade} sob nº {negrito(i.inscricao_municipal or '')} e caracterizado na Matrícula Nº "
        f"{negrito(frases.matricula_numero(i.matricula_numero))} do {frases.cartorio_texto(i.cartorio)}."
        for i in imoveis
    )
    plural = len(imoveis) > 1
    return (
        f" {_brl_negrito(valor)}, por permuta {'dos imóveis' if plural else 'do imóvel'} de "
        f"propriedade {C.dos} {C.NOME.title()}, {nomes}, já {C.g('qualificado', 'qualificada', 'qualificados')} "
        f"anteriormente, {'caracterizados' if plural else 'caracterizado'} como: {descricoes}"
    )


def _descricao_matricula_rica(d: DadosContrato, adapter: DocxRenderAdapter) -> Any:
    """The matrícula quote as a docxtpl `{{r ... }}` context value (contract
    §5): bold/underline PER RUN — `[]` renders the quote plain, exactly as
    before this feature existed.

    🔴 Migration 136: the IMÓVEL: clause quotes the `descricao_imovel`
    typed block SPECIFICALLY (`d.matricula.descricao_imovel_texto` /
    `_formatacao`), never the whole abertura/selection — a de-furnitured
    abertura still ends in `PROPRIETÁRIOS: …`, which on a resold property
    names the PREVIOUS owners and would put the wrong parties in a deed.
    Falls back to the whole selection (`d.matricula.texto` / `formatacao`,
    the pre-136 behaviour) ONLY when the extraction carries no such block —
    surfaced to the operator as the `MATRICULA_SEM_DESCRICAO_IMOVEL` aviso
    (`derivacao._imovel`) and logged at WARNING, never silent.

    `.rstrip()` matches the plain-string behaviour it replaces; ranges are
    re-clipped to the (possibly shortened) stripped length so a range
    touching only the stripped trailing whitespace never overflows it.
    """
    if d.matricula.descricao_imovel_texto is not None:
        texto = d.matricula.descricao_imovel_texto.rstrip()
        ranges = clip_ranges(d.matricula.descricao_imovel_formatacao, 0, len(texto))
    else:
        logger.warning(
            "contrato %s: matrícula %s sem bloco 'descricao_imovel' — a "
            "cláusula IMÓVEL: usa a seleção inteira (comportamento anterior "
            "à migração 136)",
            d.contrato_id,
            d.matricula.codigo,
        )
        texto = d.matricula.texto.rstrip()
        ranges = clip_ranges(d.matricula.formatacao, 0, len(texto))
    return adapter.rich_text(runs_from_ranges(texto, ranges))


def montar_contexto(
    d: DadosContrato,
    sw: dict[str, bool],
    politica: Politica,
    assinatura: date,
    par: ContadorParagrafos,
    adapter: DocxRenderAdapter,
    hoje: Optional[date] = None,
) -> dict[str, Any]:
    """`hoje` (default TODAY — `_hoje_padrao`) is the E1 empresa-
    classification reference `empresas_exigidas` needs below; it is NEVER
    `assinatura` (E2/H2)."""
    hoje = hoje or _hoje_padrao()
    cl = numerar_clausulas(sw)
    vend, comp_pessoas = signatarios(d.vendedores), signatarios(d.compradores)
    pj_vend, pj_comp = _pj_com_representante(d, "vendedor"), _pj_com_representante(d, "comprador")
    # [Migration 193] A company party agrees in the feminine ("a VENDEDORA" —
    # corpus deal 866: "a pessoa jurídica").
    V = lado(_generos(vend) + ["f"] * len(pj_vend), "vendedor")
    C = lado(_generos(comp_pessoas) + ["f"] * len(pj_comp), "comprador")
    anu = anuentes(d.vendedores)
    termos = d.termos
    im = d.imovel
    assert im is not None and d.valor_negociado is not None  # gated

    # ── parcelas + references ──
    parcelas = parcelas_ordenadas(d)
    grupos = grupos_de_parcelas(d)
    nums = numeros_impressos(d)

    def refs(tipo: str) -> str:
        return juntar(list(dict.fromkeys(nums[p.id] for p in parcelas if p.tipo == tipo)))

    p_ref = {
        # A sinal paid in tranches is ONE printed parcela
        # (`derivacao.grupos_de_parcelas`), so this is still one number.
        "sinal": refs("sinal"),
        "financiamento": refs("financiamento"),
        "saldo": refs("saldo"),
        # The permuta parcela is one of `parcelas` now (114), so it has its own
        # computed number instead of one appended past the end of the schedule.
        "permuta": refs("permuta"),
    }
    favorecidos = {f.id: f for f in d.favorecidos}
    cpf_vendedor = {frases.so_digitos(p.cpf): p for p in vend if p.cpf}
    imoveis_permuta = {i.permuta_ativo_id: i for i in d.permuta_imoveis}

    def vendedor_de(fav):
        return cpf_vendedor.get(frases.so_digitos(fav.cpf_cnpj)) if fav else None

    ja_usados: set[str] = set()
    #: [192] Each printed split: (number, {favorecido_id: share/parcela}) —
    #: a later parcela with the SAME accounts and proportions cites it.
    divisoes_impressas: list[tuple[str, dict[str, Decimal]]] = []
    linhas_parcelas = []
    for grupo in grupos:
        p = grupo[0]
        num = nums[p.id]
        if p.tipo == "permuta":
            # gated: derivacao._permuta — every linked ativo is loaded.
            imoveis = [imoveis_permuta[a] for a in p.permuta_ativo_ids]
            linhas_parcelas.append(
                {"num": num, "texto": _texto_parcela_permuta(p.valor, d, C, imoveis), "subitens": []}  # type: ignore[arg-type] — gated
            )
            continue
        if p.tipo == "sinal" and len(grupo) > 1:
            # gated: derivacao._sinal_em_parcelas (consecutive, no split) +
            # `_negociacao` (each tranche's valor/momento/favorecido/forma).
            partes = []
            for t in grupo:
                fav = favorecidos[t.favorecido_id or ""]
                partes.append((t, fav, fav.id in ja_usados, vendedor_de(fav)))
                ja_usados.add(fav.id)
            linhas_parcelas.append(
                {
                    "num": num,
                    "texto": frases.texto_sinal_em_partes(
                        partes, V=V, C=C, tem_financiamento=sw["tem_financiamento"],
                        ref_financiamento=p_ref["financiamento"],
                    ),
                    "subitens": [],
                }
            )
            continue
        fgts_valores = None
        if p.tipo == "financiamento":
            # gated: derivacao._financiamento — at most one FGTS source, a
            # strict part of the parcela, FGTS marked on the financing.
            dobrada = next((q for q in grupo[1:] if q.tipo == "fgts"), None)
            if dobrada is not None:
                fgts_valores = (dobrada.valor, p.valor)
            elif p.valor_fgts is not None:
                fgts_valores = (p.valor_fgts, p.valor - p.valor_fgts)  # type: ignore[operator]
        fav = (
            favorecidos.get(p.favorecido_id or "")
            if p.tipo in {"sinal", "intermediaria", "direta", "saldo"} and not p.divisao
            else None
        )
        subitens: list[str] = []
        divisao_ref = None
        if p.divisao:
            # gated: derivacao._divisao — every share names a loaded
            # favorecido and the shares add up to the parcela exactly.
            valores = valores_da_divisao(p)
            proporcoes = {q.favorecido_id: v / p.valor for q, v in zip(p.divisao, valores)}  # type: ignore[operator]
            divisao_ref = next((n for n, prop in divisoes_impressas if prop == proporcoes), None)
            if divisao_ref is None:
                for i, (q, v) in enumerate(zip(p.divisao, valores), start=1):
                    fq = favorecidos[q.favorecido_id or ""]
                    subitens.append(
                        frases.subitem_divisao(
                            num, i, v, q.percentual, fq,  # type: ignore[arg-type] — gated
                            repetido=fq.id in ja_usados, vendedor_favorecido=vendedor_de(fq),
                        )
                    )
                    ja_usados.add(fq.id)
                divisoes_impressas.append((num, proporcoes))
        linhas_parcelas.append(
            {
                "num": num,
                "texto": frases.texto_parcela(
                    p,
                    V=V,
                    C=C,
                    tem_financiamento=sw["tem_financiamento"],
                    fgts=d.financiamento.fgts,
                    ref_financiamento=p_ref["financiamento"],
                    favorecido=fav,
                    favorecido_repetido=bool(fav and fav.id in ja_usados),
                    vendedor_favorecido=vendedor_de(fav),
                    juros_am=termos.confissao_juros_am if p.confissao_divida else None,
                    fgts_valores=fgts_valores,
                    dividida=bool(subitens),
                    divisao_ref=divisao_ref,
                ),
                "subitens": subitens,
            }
        )
        if fav is not None:
            ja_usados.add(fav.id)

    sinais = [p for p in parcelas if p.tipo == "sinal"]
    confissao_parcelas = [p for p in parcelas if p.confissao_divida]

    # ── imóvel ──
    e = im.endereco
    # The posse clauses' AND (below) the title's address — NEVER `e` (the
    # CRM's público endereço, a deliberate portaria/gatehouse decoy at at
    # least one tenant). Gated `faltando` by `derivacao._imovel`, so this is
    # never `None` here.
    endereco_curto = resolver_endereco_posse(
        im.endereco_registro_texto,
        d.matricula.descricao_imovel_texto or d.matricula.texto,
        d.matricula.texto,
    )
    assert endereco_curto is not None  # gated
    # 🔴 [endereco-portaria-vs-imovel] `titulo_curto` is the INSTRUMENT'S OWN
    # TITLE (`modelo_texto.TEMPLATE`'s opening line) — used to fall back to
    # `e.logradouro`/`e.numero` (the SAME CRM decoy) whenever there is no
    # `empreendimento`; ONE7515 only escaped this because it happens to
    # carry one ("Euroville - Km 23"). Reuses the SAME resolved,
    # registry-derived `endereco_curto` the posse clauses print, rather than
    # a separate loteamento-name extraction: a street+número reads correctly
    # for any property (a loteamento's own "situado na Alameda X" IS its
    # street), the mechanism is already built and tested for the posse
    # clauses, and reusing it means one value to keep correct instead of two.
    #
    # 🔴 [titulo-empreendimento-omitido] The title MUST carry BOTH pieces when
    # `empreendimento` is present, never one OR the other — reference contract
    # 08 (RESIDENCIAL EUROVILLE / RODRIGO MORASCHI ENRIQUEZ, 2026-09-22) reads
    # "… – RESIDENCIAL EUROVILLE – ALAMEDA ALEMANHA, Nº 535 – …", and a
    # `titulo_curto` that dropped to `empreendimento` alone silently omitted
    # the very street the instrument is about. `e.complemento` (the CRM's
    # own apto/unit number, e.g. "Apto 11") stays folded into the
    # `empreendimento` segment when present — it names a unit WITHIN the
    # building, not a street, so it carries none of the CRM-público-endereço
    # decoy risk `e.logradouro`/`e.numero` do.
    if im.empreendimento:
        nome_empreendimento = (
            f"{im.empreendimento} – {e.complemento}" if e.complemento else im.empreendimento
        )
        titulo_curto = f"{nome_empreendimento} – {endereco_curto}"
    else:
        titulo_curto = endereco_curto
    # Two different questions, two answers:
    #  - `tem_empreendimento_condominio` (pendência da CND de condomínio) still
    #    needs a named empreendimento to ask for a document about, unless the
    #    card explicitly says the imóvel is NOT in a condomínio;
    #  - `em_condominio` (the vistoria clause's wording) is the condomínio
    #    wording by default — 91/93 signed contracts, owner decision
    #    2026-10-05 — and only an EXPLICIT `False` on the card switches it off.
    nao_e_condominio = im.em_condominio is False
    tem_empreendimento_condominio = (
        EM_CONDOMINIO_QUANDO_HA_EMPREENDIMENTO and bool(im.empreendimento) and not nao_e_condominio
    )
    em_condominio = not nao_e_condominio
    imovel = {
        "titulo_curto": titulo_curto,
        "cidade": e.cidade,
        "uf": (e.uf or "").upper(),
        "descricao_matricula": _descricao_matricula_rica(d, adapter),
        "inscricao_municipal": im.inscricao_municipal,
        "matricula_numero": frases.matricula_numero(im.numero_matricula),
        # [Corpus catalog §6, 34/34] "Cartório de Registro de Imóveis de
        # <cidade>" — never the transcribed heading ("SERVENTIA DO REGISTRO
        # DE IMÓVEIS de Cotia"). Gated: `derivacao._imovel`.
        "cartorio": frases.cartorio_texto(im.numero_registro_imoveis),
        "endereco_curto": endereco_curto,
        "em_condominio": em_condominio,
    }

    # ── certidões ──
    # Whose certidões are presented and which companies — [Q9] — come from
    # the same derivacao rules the gate checked.
    pessoas_cert = pessoas_certificadas(d, sw, assinatura, politica)
    grupos, pendentes_cert = [], []
    n = 0
    for p in pessoas_cert:
        idx = indice_certidoes(p.certidoes, "cpf")
        # [R1, reverses df54184ab] EVERY certificando's certidões are
        # `faltando`-gated again (`derivacao.conferir`), so a required
        # `tipo` is always present in `idx` by the time this runs (`avaliar`
        # already returned `pronto`) — the `if t in idx` guard stays only
        # as a defensive no-op against a future relaxation, never load-
        # bearing for a live card.
        itens = [frases.item_certidao(t, idx[t]) for t in tipos_exigidos("cpf") if t in idx]
        if not itens:
            continue
        n += 1
        grupos.append({"num": n, "em_nome_de": p.nome, "sufixo": None, "itens": itens})
        pendentes_cert += [
            # gated: signatários by `_partes`, antigos by `_certidoes` (`nome_oficial`)
            frases.pendencia_certidao(t, p.nome or "")
            for t in tipos_exigidos("cpf")
            if t in idx and idx[t].resultado == "nao_emitida"
        ]
    # [Migration 193] A PJ PARTY's own group — its 11 CNPJ certidões.
    for pj in pj_certificandas(d, sw):
        idx = indice_certidoes(pj.certidoes, "cnpj")
        nome_pj = pj.razao_social or pj.cnpj or ""
        tipos = tipos_exigidos("cnpj")
        itens = [frases.item_certidao(t, idx[t]) for t in tipos if t in idx]
        if not itens:
            continue
        n += 1
        grupos.append({"num": n, "em_nome_de": nome_pj, "sufixo": None, "itens": itens})
        pendentes_cert += [
            frases.pendencia_certidao(t, nome_pj) for t in tipos if t in idx and idx[t].resultado == "nao_emitida"
        ]
    # [P5] A COMPANY antigo proprietário's own group — its CNPJ certidões,
    # only when the antigos enter the contract (same predicate as a person).
    antigos_pj = antigos_proprietarios_pj(d) if antigos_no_contrato(d, assinatura, politica) else []
    for pj in antigos_pj:
        idx = indice_certidoes(pj.certidoes, "cnpj")
        nome_pj = pj.razao_social or pj.cnpj or ""
        tipos = tipos_exigidos("cnpj")
        itens = [frases.item_certidao(t, idx[t]) for t in tipos if t in idx]
        if not itens:
            continue
        n += 1
        grupos.append({"num": n, "em_nome_de": nome_pj, "sufixo": None, "itens": itens})
        pendentes_cert += [
            frases.pendencia_certidao(t, nome_pj) for t in tipos if t in idx and idx[t].resultado == "nao_emitida"
        ]
    # [E1/E4] PJ groups: DISTINCT required empresas of the certificandos
    # (never per-person — a company both spouses hold is printed ONCE).
    empresas_partes = empresas_impressas_como_parte(d, assinatura, politica)
    for eex in empresas_exigidas(d, sw, hoje, politica):
        e = eex.empresa
        if e.id in empresas_partes:
            continue  # already printed as the party's own group above
        idx = indice_certidoes(e.certidoes, "cnpj")
        nome_pj = e.razao_social or e.cnpj
        tipos = tipos_exigidos("cnpj")
        itens = [frases.item_certidao(t, idx[t]) for t in tipos if t in idx]
        if not itens:
            continue
        n += 1
        grupos.append({"num": n, "em_nome_de": nome_pj, "sufixo": eex.sufixo, "itens": itens})
        pendentes_cert += [
            frases.pendencia_certidao(t, nome_pj) for t in tipos if t in idx and idx[t].resultado == "nao_emitida"
        ]

    # [§6.1 #14] The imóvel's own group (migration 118): matrícula + IPTU CND +
    # condominial CND, whichever are on file.
    cert_imovel = certidoes_imovel(d)
    apresentadas = {c.tipo for c in cert_imovel}
    grupos_imovel = []
    if cert_imovel:
        n += 1
        grupos_imovel.append(
            {
                "num": n,
                "titulo": imovel["endereco_curto"],
                "itens": [
                    frases.item_certidao_imovel(c, numero_matricula=im.numero_matricula)
                    for c in cert_imovel
                ],
            }
        )

    # A document already PRESENTED above is not also requested below (spec
    # §2.5: the IPTU CND is a pendência "only when not already listed").
    pendencias: list[str] = []
    if tem_empreendimento_condominio and "cnd_condominio" not in apresentadas:
        pendencias.append(frases.PENDENCIA_CONDOMINIO_PERMUTA if sw["tem_permuta"] else frases.PENDENCIA_CONDOMINIO)
    pendencias.append(frases.pendencia_estado_civil(politica.certidao_estado_civil_max_dias))
    pendencias.append(frases.PENDENCIA_DOCUMENTOS)
    if sw["tem_onus_ja_quitado"]:
        # [Migration 193] Corpus deal 867: the matrícula requested WITH the
        # baixa — even when a matrícula certidão was presented (it predates
        # the baixa).
        pendencias.append(frases.pendencia_matricula_baixa(im.situacao_onus or ""))
    elif "matricula" not in apresentadas:
        pendencias.append(frases.PENDENCIA_MATRICULA)
    pendencias.extend(frases.PENDENCIAS_CONTAS_CONSUMO)
    if "cnd_iptu" not in apresentadas:
        pendencias.append(frases.PENDENCIA_IPTU)
    if sw["tem_saldo_devedor"]:
        # gated: `imovel.situacao_onus` (tem_saldo_devedor ⇒ an ONUS_COM_SALDO value)
        pendencias.append(frases.pendencia_baixa_onus(im.situacao_onus or ""))
    pendencias += pendentes_cert

    if sw["tem_permuta"]:
        apresentantes_lista, plural_apres = [f"{V.ART} {negrito(V.NOME)}", f"{C.art} {negrito(C.NOME)}"], True
    else:
        apresentantes_lista, plural_apres = [f"{V.ART} {negrito(V.NOME)}"], V.plural
    antigos = antigos_proprietarios(d)
    if (antigos or antigos_pj) and antigos_no_contrato(d, assinatura, politica):
        # [Q9] the previous owner(s) present certidões too.
        #
        # 🔴 `antigos` MUST be checked here, not only the window predicate.
        # The two disagree by design since migration 151: a contract flagged
        # `processo_legado` skips the antigo-proprietário GATE entirely (the
        # deal predates the platform, so nobody ever recorded those parties),
        # while `exige_antigo_proprietario` still answers True because the
        # registered transfer really is recent. Rendering then asked for a
        # phrase naming an EMPTY list and died with `IndexError: list index
        # out of range` inside `frases.antigos_proprietarios_texto` — a 500
        # on POST .../gerar, live 2026-09-22, on a contract the gate had just
        # declared `pronto`. Gate and template must agree on who exists —
        # `antigos_no_contrato` (2026-10-03) also keeps a legacy deal that
        # DOES record antigos from printing parties the gate never checked.
        apresentantes_lista.append(frases.antigos_proprietarios_texto(antigos, empresas=antigos_pj))
        plural_apres = True
    apresentantes = juntar(apresentantes_lista)
    seus_nomes = "seus nomes" if plural_apres else "seu nome"
    anu_cert = anuentes_certificandos(d, politica)
    if anu_cert:
        # [Migration 193] Corpus deal 141: "apresenta neste momento as
        # certidões em seu nome, em nome da Anuente …".
        ga = _generos(anu_cert)
        if len(ga) == 1:
            quem = "da Anuente" if ga[0] == "f" else "do Anuente"
        else:
            quem = "das Anuentes" if all(g == "f" for g in ga) else "dos Anuentes"
        seus_nomes += f", em nome {quem}"
    certidoes = {
        "apresentantes_texto": apresentantes,
        "apresenta": "apresentam" if plural_apres else "apresenta",
        "seus_nomes": seus_nomes,
        "grupos": grupos,
        "grupos_imovel": grupos_imovel,
        "pendencias": [{"letra": letra(i), "texto": t} for i, t in enumerate(pendencias)],
    }

    # ── ônus / posse / permuta ──
    onus: dict[str, Any] = {"quitacao": None}
    if sw["tem_onus_ja_quitado"]:
        # gated: derivacao._imovel — protocolo date, exactly one R/AV ato, a
        # cartório with a readable city.
        partes_cartorio = frases.cartorio_partes(im.numero_registro_imoveis)
        assert partes_cartorio is not None  # gated
        onus = {
            "quitacao": termos.onus_quitacao,
            "ja_quitado_texto": frases.onus_ja_quitado_frase(
                im.situacao_onus or "", im.onus_fonte_atos[0], termos.onus_baixa_protocolo_em,  # type: ignore[arg-type]
                partes_cartorio[1], V=V, C=C,
            ),
        }
    if sw["tem_usufruto"]:
        onus["usufruto_texto"] = frases.usufruto_frase(V=V, C=C)
    if sw["tem_saldo_devedor"]:
        onus = {
            "credor": im.onus_credor,
            "fonte_texto": frases.onus_fonte_texto(im.onus_fonte_atos),
            "quitacao": termos.onus_quitacao,
            # gated: derivacao._imovel `negociacao.onus_quitacao` (+ known value)
            "quitacao_texto": frases.onus_quitacao_texto(
                termos.onus_quitacao or "",
                C=C,
                ref_saldo=p_ref["saldo"],
                ref_clausula_preco=cl["preco"].ref if termos.onus_quitacao == "parcela" else "",
                # [192] read only by the 'vendedores_boleto' wording.
                V=V,
                prazo_dias=termos.onus_prazo_dias,
            ),
            "prazo_dias": termos.onus_prazo_dias,
        }

    # [§6.1 #12] The marco names its parcela (114); the clause prints THAT
    # parcela's computed number, and the condition covers what precedes it.
    # gated: derivacao._posse — marco present + known; a 'parcela' marco's
    # parcela must be in the schedule (POSSE_MARCO_PARCELA_DESCONHECIDA). The
    # ref is read only by the 'parcela' wording, so "" never prints.
    marco = termos.posse_marco or ""
    ref_marco = numero_da_parcela(d, termos.posse_marco_parcela_id) or ""
    if marco == "parcela":
        condicao = frases.condicao_posse_frase(
            parcelas_antes_de(d, termos.posse_marco_parcela_id), todas=False
        )
    elif marco == "data_fixa":
        # Corpus 859: the fixed date is conditioned on the price being paid in
        # full ("todas as parcelas do preço ... integralmente quitadas").
        condicao = frases.condicao_posse_frase([], todas=True)
    elif marco != "assinatura" and sw["a_vista"]:
        condicao = frases.condicao_posse_frase([], todas=True)
    else:
        condicao = ""
    posse = {
        "prazo": termos.posse_prazo_dias,
        "marco_texto": frases.posse_marco_texto(marco, ref_parcela=ref_marco),
        # The whole timing phrase (prazo N / concomitante / data fixa) — the
        # template prints it, never `dias(prazo)` raw (0 → "0 dias" was wrong).
        # gated: derivacao._posse.
        "prazo_frase": frases.posse_prazo_texto(
            termos.posse_prazo_dias, marco, ref_parcela=ref_marco, data=termos.posse_data,
        ),
        "prazo_frase_maximo": frases.posse_prazo_texto(
            termos.posse_prazo_dias, marco, ref_parcela=ref_marco, data=termos.posse_data,
            intro=frases.POSSE_INTRO_PRAZO_MAXIMO_VIRGULA,
        ),
        "condicao_frase": condicao,
        # [Q12] the office's value — same daily fine for each party in a permuta.
        "multa_diaria": d.imobiliaria.posse_multa_diaria,
    }
    permuta: dict[str, Any] = {}
    if sw["tem_permuta"]:
        # Same rule as `imovel["endereco_curto"]` above — NEVER
        # `d.permuta_imoveis[0].endereco` (the CRM's público endereço).
        # Gated `faltando` by `derivacao._permuta`, so never `None` here.
        # EVERY permuta imóvel (several parcelas / several imóveis per
        # parcela): one posse clause names them all, distinct addresses
        # joined; "imóveis" whenever there is more than one imóvel.
        enderecos: list[str] = []
        for permuta_imovel in d.permuta_imoveis:
            # gated: derivacao._permuta (atos selected + registry address resolved)
            endereco = resolver_endereco_posse(
                permuta_imovel.endereco_registro_texto,
                permuta_imovel.descricao_imovel_texto or permuta_imovel.descricao_matricula or "",
                permuta_imovel.descricao_matricula or "",
            )
            assert endereco is not None  # gated
            if endereco not in enderecos:
                enderecos.append(endereco)
        plural_permuta = len(d.permuta_imoveis) > 1
        permutas_nums = juntar(
            list(dict.fromkeys(nums[p.id] for p in parcelas if p.tipo == "permuta"))
        )
        varias_parcelas_permuta = len([p for p in parcelas if p.tipo == "permuta"]) > 1
        permuta = {
            "endereco_curto": " e à ".join(enderecos),
            "plural": plural_permuta,
            # The preço ¶ citing where the permuta imóvel(is) are described.
            "escritura_ref": (
                f"{'dos imóveis melhor descritos' if plural_permuta else 'do imóvel melhor descrito'} "
                f"{'nas Parcelas' if varias_parcelas_permuta else 'na Parcela'} {permutas_nums}"
            ),
            "posse_prazo": termos.permuta_posse_prazo_dias,
            "posse_marco_texto": frases.posse_marco_texto(
                termos.permuta_posse_marco or "",
                ref_parcela=numero_da_parcela(d, termos.permuta_posse_marco_parcela_id) or "",
            ),
            # gated: derivacao._posse(escopo="permuta_posse") — prazo present.
            "posse_prazo_frase": frases.posse_prazo_texto(
                termos.permuta_posse_prazo_dias,
                termos.permuta_posse_marco or "",
                ref_parcela=numero_da_parcela(d, termos.permuta_posse_marco_parcela_id) or "",
                intro=frases.POSSE_INTRO_PRAZO_MAXIMO,
            ),
        }

    # ── intermediação ──
    corretagem: dict[str, Any] = {}
    if sw["tem_intermediacao"]:
        qualificados = []
        if any(i.corretor_id for i in d.intermediarios):
            qualificados.append(frases.qualificacao_imobiliaria(d.imobiliaria))
        # [§6.1 #21] Each external intermediário is qualified from its OWN
        # row. Migration 162 — a 'parceiro_split' row (a commission-split
        # beneficiary, never a contracted party) is NEVER added here, same
        # as reference contract 08's own commission clause: its 3rd
        # beneficiary appears only in the split-payment paragraph below
        # (`valores`/`splits`), never in "as empresas a seguir qualificadas".
        qualificados += [
            frases.qualificacao_intermediario(i)
            for i in d.intermediarios
            if not i.corretor_id and i.natureza == "intermediario"
        ]
        # gated: derivacao._intermediacao `negociacao.corretagem_contratantes` (+ known value)
        texto, texto_cap, contrata = frases.corretagem_contratantes(
            termos.corretagem_contratantes or "", V=V, C=C
        )
        valores = []
        for it in d.intermediarios:
            if it.tipo == "percentual":
                valor = (d.valor_negociado * it.valor / Decimal(100)).quantize(CENTAVO, rounding=ROUND_HALF_UP)  # type: ignore[operator]
            else:
                valor = it.valor  # type: ignore[assignment]
            valores.append((valor, favorecidos[it.favorecido_id]))  # type: ignore[index] — gated
        plural_emp = len(qualificados) > 1
        corretagem = {
            "qualificados": qualificados,
            "contratantes_texto": texto,
            "contratantes_texto_cap": texto_cap,
            "contrata": contrata,
            "empresas_texto": "as empresas a seguir qualificadas" if plural_emp else "a empresa a seguir qualificada",
            "contratadas_texto": "as empresas contratadas" if plural_emp else "a empresa contratada",
            "total": sum((v for v, _ in valores), Decimal("0")),
            "parcelamento_texto": frases.parcelamento_texto(termos.corretagem_num_parcelas),
            # [§6.1 #23] The marco parcelas are the ones flagged on the schedule.
            "marcos_texto": frases.marcos_texto(corretagem_marcos(d)),
            "splits": [frases.split_corretagem(v, fav) for v, fav in valores],
            "pct_rescisao": frases.pct_simples(d.pct_comissao),  # type: ignore[arg-type] — [Q5]
        }

    # ── anuentes (migration 193) ──
    # gated: derivacao._partes — every anuente is a signing seller's
    # reciprocal spouse/companion (ANUENTE_SEM_REDACAO otherwise).
    anuentes_textos = [
        frases.qualificacao_anuente(
            a, conjuge_do_anuente(d, a), lei_6515_desde=politica.lei_6515_vigencia_desde  # type: ignore[arg-type]
        )
        for a in anu
    ]
    A_NOME = "ANUENTES" if len(anu) > 1 else "ANUENTE"  # noqa: N806 — template token

    return {
        **sw,
        "cl": cl,
        "par": par,
        "brl": _brl_negrito,
        "dias": dias_por_extenso,
        "dias_simples": frases.dias_simples,
        "pct_extenso": percentual_por_extenso,
        "V": V,
        "C": C,
        "V_qualificacao": _qualificacao_lado(vend, pj_vend, politica),
        "C_qualificacao": _qualificacao_lado(comp_pessoas, pj_comp, politica),
        "V_signatarios": [frases.signatario_linha(p) for p in vend]
        + [linha for pj, rep in pj_vend for linha in frases.signatario_pj_linhas(pj, rep)],
        "C_signatarios": [frases.signatario_linha(p) for p in comp_pessoas]
        + [linha for pj, rep in pj_comp for linha in frases.signatario_pj_linhas(pj, rep)],
        # [Migration 193] The seller's spouse/companion signing as ANUENTE.
        "anuentes_linhas": frases.linhas_anuentes(anuentes_textos, anu),
        "A_NOME": A_NOME,
        "A_signatarios": [frases.signatario_linha(p) for p in anu],
        "A_assinantes_fisicos": [frases.assinante_fisico(p) for p in anu],
        # [Migration 193] Operator-typed obligations, VERBATIM.
        "obrigacoes_vendedor": frases.paragrafos_livres(termos.obrigacoes_vendedor),
        "permuta_obrigacoes": (
            frases.paragrafos_livres(termos.permuta_obrigacoes_entrega) if sw["tem_permuta"] else []
        ),
        "imovel": imovel,
        "titulo_aquisitivo": _sem_adquirido_inicial((im.titulo_aquisitivo_texto or "").strip()),
        "itens_integrantes": (termos.itens_integrantes or "").strip(),
        "preco": d.valor_negociado,
        "parcelas": linhas_parcelas,
        "p_ref": p_ref,
        "confissao": {
            "parcelas_nums": juntar([nums[p.id] for p in confissao_parcelas]),
            "total": sum((p.valor for p in confissao_parcelas), Decimal("0")),  # type: ignore[misc]
            "juros_am": termos.confissao_juros_am,
            "garantia_texto": (termos.confissao_garantia or "").strip(),
        },
        "certidoes": certidoes,
        "prazo_pendencias": prazo_pendencias(d, politica),
        "prazo_esclarecimentos": politica.prazo_esclarecimentos_dias,
        "onus": onus,
        "posse": posse,
        "permuta": permuta,
        # [Q4] ¶2 wording is fixed in the template (multa + proven costs).
        "rescisao": {"cura_frase": frases.cura_rescisao_frase(politica.rescisao_cura_dias)},
        # [Q3] multa rescisória = the sinal's valor — the SUM of its
        # tranches when it is paid in parts (owner, 2026-10-03).
        "multa_rescisoria": sum((p.valor for p in sinais), Decimal("0")),  # type: ignore[misc] — gated
        "resolutiva_notificacao_email": politica.resolutiva_notificacao_email,
        "corretagem": corretagem,
        # [Owner directive, 2026-09-23] The matrícula-derived comarca
        # (`carregador.carregar` -> `derivacao.comarca_de_texto`), else the
        # confirmed cartório's city (`derivacao.foro_comarca`) — never the
        # imóvel address; gated `faltando` by `derivacao._contrato`, so this
        # is never blank.
        "foro": {"comarca": foro_comarca(d)},
        "assinatura": {
            "local": d.imobiliaria.endereco.cidade,
            "data_extenso": data_por_extenso(assinatura),
            "plataforma_nome": d.imobiliaria.plataforma_assinatura_nome,
            "plataforma_url": d.imobiliaria.plataforma_assinatura_url,
        },
        # [Migration 168, owner decision — supersedes Q14] witnesses print
        # NOME + E-MAIL (when present) + CPF, never RG (RG left the form and
        # the print alike). `linha` reuses the same NOME/e-mail shape a
        # comprador/vendedor signatário line already prints.
        "testemunhas": [
            {"linha": frases.nome_email_linha(t.nome, t.email), "cpf": frases.documento_linha(t.cpf)}
            for t in d.testemunhas
        ],
        # Migration 157 — read ONLY by the física branch of the closing /
        # signature block (`tem_assinatura_digital` off). One signature
        # line per signer and per witness; "vias" = one per signer (each
        # party keeps a signed copy), never fewer than two.
        "vias": numero_com_extenso(
            max(2, len(vend) + len(comp_pessoas) + len(anu) + len(pj_vend) + len(pj_comp)),
            feminino=True, largura=2,
        ),
        "linha_assinatura": frases.LINHA_ASSINATURA,
        "V_assinantes_fisicos": [frases.assinante_fisico(p) for p in vend]
        + [frases.assinante_fisico_pj(pj, rep) for pj, rep in pj_vend],
        "C_assinantes_fisicos": [frases.assinante_fisico(p) for p in comp_pessoas]
        + [frases.assinante_fisico_pj(pj, rep) for pj, rep in pj_comp],
        "testemunhas_fisicas": [
            {
                "nome": (t.nome or "").upper(),
                "documento": frases.testemunha_documento_linha(t.cpf),
            }
            for t in d.testemunhas
        ],
    }


def snapshot_sha256(d: DadosContrato, politica: Politica, assinatura: date) -> str:
    """SHA-256 of the canonical JSON of everything the render read (§5.2 #18,
    migration 112). Same card state + policy + date -> same hash."""
    payload = {
        "dados": asdict(d),
        "politica": asdict(politica),
        "assinatura": assinatura.isoformat(),
    }
    canonico = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


__all__ = ["montar_contexto", "snapshot_sha256"]
