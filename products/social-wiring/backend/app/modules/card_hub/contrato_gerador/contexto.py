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
    brl_por_extenso,
    data_por_extenso,
    numero_com_extenso,
    dias_por_extenso,
    percentual_por_extenso,
)
from noctusai_lib.integrations.documents.abnt import clip_ranges, runs_from_ranges
from noctusai_lib.integrations.docx_render import DocxRenderAdapter

from app.modules.card_hub.contrato_gerador import frases
from app.modules.card_hub.contrato_gerador.concordancia import lado, normalizar_genero
from app.modules.card_hub.contrato_gerador.dados import (
    DadosContrato,
    Pessoa,
    PermutaImovel,
    signatarios,
)
from app.modules.card_hub.contrato_gerador.derivacao import (
    _hoje_padrao,
    antigos_proprietarios,
    certidoes_imovel,
    corretagem_marcos,
    empresas_exigidas,
    exige_antigo_proprietario,
    indice_certidoes,
    numero_da_parcela,
    parcelas_antes_de,
    parcelas_ordenadas,
    pessoas_certificadas,
    prazo_pendencias,
    resolver_endereco_posse,
    tipos_exigidos,
)
from app.modules.card_hub.contrato_gerador.numeracao import (
    ContadorParagrafos,
    juntar,
    letra,
    num2,
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
    return [normalizar_genero(p.genero) or "m" for p in pessoas]


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
    — logged at WARNING so the fallback is visible, never silent.
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
    return i.descricao_matricula or ""


def _texto_parcela_permuta(valor: Decimal, d: DadosContrato, C) -> str:
    """The permuta parcela (spec §2.3 `p.tipo == 'permuta'`) — its value is the
    parcela's own, and each imóvel is one `permuta_ativos` link (114) carrying
    its own matrícula quote (115)."""
    imoveis = d.permuta_imoveis
    nomes = juntar([(p.nome or "").upper() for p in signatarios(d.compradores)])
    descricoes = " E ".join(
        f"{_descricao_matricula_permuta(i, d)} Imóvel devidamente cadastrado pela Prefeitura Municipal de "
        f"{i.endereco.cidade} sob nº {i.inscricao_municipal} e caracterizado na Matrícula Nº "
        f"{frases.matricula_numero(i.matricula_numero)} do {i.cartorio}."
        for i in imoveis
    )
    plural = len(imoveis) > 1
    return (
        f" {brl_por_extenso(valor)}, por permuta {'dos imóveis' if plural else 'do imóvel'} de "
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
    logged at WARNING so the fallback is visible, never silent.

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
    V, C = lado(_generos(vend), "vendedor"), lado(_generos(comp_pessoas), "comprador")
    termos = d.termos
    im = d.imovel
    assert im is not None and d.valor_negociado is not None  # gated

    # ── parcelas + references ──
    parcelas = parcelas_ordenadas(d)
    nums = {p.id: num2(i) for i, p in enumerate(parcelas, start=1)}

    def refs(tipo: str) -> str:
        return juntar([nums[p.id] for p in parcelas if p.tipo == tipo])

    p_ref = {
        "sinal": refs("sinal"),
        "financiamento": refs("financiamento"),
        "saldo": refs("saldo"),
        # The permuta parcela is one of `parcelas` now (114), so it has its own
        # computed number instead of one appended past the end of the schedule.
        "permuta": refs("permuta"),
    }
    favorecidos = {f.id: f for f in d.favorecidos}
    cpf_vendedor = {frases.so_digitos(p.cpf): p for p in vend if p.cpf}
    ja_usados: set[str] = set()
    linhas_parcelas = []
    for p in parcelas:
        if p.tipo == "permuta":
            linhas_parcelas.append(
                {"num": nums[p.id], "texto": _texto_parcela_permuta(p.valor, d, C)}  # type: ignore[arg-type] — gated
            )
            continue
        fav = favorecidos.get(p.favorecido_id or "") if p.tipo in {"sinal", "intermediaria", "direta", "saldo"} else None
        linhas_parcelas.append(
            {
                "num": nums[p.id],
                "texto": frases.texto_parcela(
                    p,
                    V=V,
                    C=C,
                    tem_financiamento=sw["tem_financiamento"],
                    fgts=d.financiamento.fgts,
                    ref_financiamento=p_ref["financiamento"],
                    favorecido=fav,
                    favorecido_repetido=bool(fav and fav.id in ja_usados),
                    vendedor_favorecido=cpf_vendedor.get(frases.so_digitos(fav.cpf_cnpj)) if fav else None,
                    juros_am=termos.confissao_juros_am if p.confissao_divida else None,
                ),
            }
        )
        if fav is not None:
            ja_usados.add(fav.id)

    sinal = next(p for p in parcelas if p.tipo == "sinal")
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
    em_condominio = EM_CONDOMINIO_QUANDO_HA_EMPREENDIMENTO and bool(im.empreendimento)
    imovel = {
        "titulo_curto": titulo_curto,
        "cidade": e.cidade,
        "uf": (e.uf or "").upper(),
        "descricao_matricula": _descricao_matricula_rica(d, adapter),
        "inscricao_municipal": im.inscricao_municipal,
        "matricula_numero": frases.matricula_numero(im.numero_matricula),
        "cartorio": im.numero_registro_imoveis,
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
            frases.pendencia_certidao(t, p.nome or "")
            for t in tipos_exigidos("cpf")
            if t in idx and idx[t].resultado == "nao_emitida"
        ]
    # [E1/E4] PJ groups: DISTINCT required empresas of the certificandos
    # (never per-person — a company both spouses hold is printed ONCE).
    for eex in empresas_exigidas(d, sw, hoje, politica):
        e = eex.empresa
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
    if em_condominio and "cnd_condominio" not in apresentadas:
        pendencias.append(frases.PENDENCIA_CONDOMINIO_PERMUTA if sw["tem_permuta"] else frases.PENDENCIA_CONDOMINIO)
    pendencias.append(frases.pendencia_estado_civil(politica.certidao_estado_civil_max_dias))
    pendencias.append(frases.PENDENCIA_DOCUMENTOS)
    if "matricula" not in apresentadas:
        pendencias.append(frases.PENDENCIA_MATRICULA)
    pendencias.append(frases.PENDENCIA_CONTAS_CONSUMO)
    if "cnd_iptu" not in apresentadas:
        pendencias.append(frases.PENDENCIA_IPTU)
    if sw["tem_saldo_devedor"]:
        pendencias.append(frases.pendencia_baixa_onus(im.situacao_onus or ""))
    pendencias += pendentes_cert

    if sw["tem_permuta"]:
        apresentantes_lista, plural_apres = [f"{V.ART} {V.NOME}", f"{C.art} {C.NOME}"], True
    else:
        apresentantes_lista, plural_apres = [f"{V.ART} {V.NOME}"], V.plural
    antigos = antigos_proprietarios(d)
    if antigos and exige_antigo_proprietario(d, assinatura, politica):
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
        # declared `pronto`. Gate and template must agree on who exists.
        apresentantes_lista.append(frases.antigos_proprietarios_texto(antigos))
        plural_apres = True
    apresentantes = juntar(apresentantes_lista)
    certidoes = {
        "apresentantes_texto": apresentantes,
        "apresenta": "apresentam" if plural_apres else "apresenta",
        "seus_nomes": "seus nomes" if plural_apres else "seu nome",
        "grupos": grupos,
        "grupos_imovel": grupos_imovel,
        "pendencias": [{"letra": letra(i), "texto": t} for i, t in enumerate(pendencias)],
    }

    # ── ônus / posse / permuta ──
    onus: dict[str, Any] = {"quitacao": None}
    if sw["tem_saldo_devedor"]:
        onus = {
            "credor": im.onus_credor,
            "fonte_texto": frases.onus_fonte_texto(im.onus_fonte_atos),
            "quitacao": termos.onus_quitacao,
            "quitacao_texto": frases.onus_quitacao_texto(
                termos.onus_quitacao or "",
                C=C,
                ref_saldo=p_ref["saldo"],
                ref_clausula_preco=cl["preco"].ref if termos.onus_quitacao == "parcela" else "",
            ),
            "prazo_dias": termos.onus_prazo_dias,
        }

    # [§6.1 #12] The marco names its parcela (114); the clause prints THAT
    # parcela's computed number, and the condition covers what precedes it.
    marco = termos.posse_marco or ""
    ref_marco = numero_da_parcela(d, termos.posse_marco_parcela_id) or ""
    if marco == "parcela":
        condicao = frases.condicao_posse_frase(
            parcelas_antes_de(d, termos.posse_marco_parcela_id), todas=False
        )
    elif marco != "assinatura" and sw["a_vista"]:
        condicao = frases.condicao_posse_frase([], todas=True)
    else:
        condicao = ""
    posse = {
        "prazo": termos.posse_prazo_dias,
        "marco_texto": frases.posse_marco_texto(marco, ref_parcela=ref_marco),
        "condicao_frase": condicao,
        # [Q12] the office's value — same daily fine for each party in a permuta.
        "multa_diaria": d.imobiliaria.posse_multa_diaria,
    }
    permuta: dict[str, Any] = {}
    if sw["tem_permuta"]:
        # Same rule as `imovel["endereco_curto"]` above — NEVER
        # `d.permuta_imoveis[0].endereco` (the CRM's público endereço).
        # Gated `faltando` by `derivacao._permuta`, so never `None` here.
        permuta_imovel = d.permuta_imoveis[0]
        endereco_curto_permuta = resolver_endereco_posse(
            permuta_imovel.endereco_registro_texto,
            permuta_imovel.descricao_imovel_texto or permuta_imovel.descricao_matricula or "",
            permuta_imovel.descricao_matricula or "",
        )
        assert endereco_curto_permuta is not None  # gated
        permuta = {
            "endereco_curto": endereco_curto_permuta,
            "posse_prazo": termos.permuta_posse_prazo_dias,
            "posse_marco_texto": frases.posse_marco_texto(
                termos.permuta_posse_marco or "",
                ref_parcela=numero_da_parcela(d, termos.permuta_posse_marco_parcela_id) or "",
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

    return {
        **sw,
        "cl": cl,
        "par": par,
        "brl": brl_por_extenso,
        "dias": dias_por_extenso,
        "pct_extenso": percentual_por_extenso,
        "V": V,
        "C": C,
        "V_qualificacao": frases.qualificacao(vend, lei_6515_desde=politica.lei_6515_vigencia_desde),
        "C_qualificacao": frases.qualificacao(comp_pessoas, lei_6515_desde=politica.lei_6515_vigencia_desde),
        "V_signatarios": [frases.signatario_linha(p) for p in vend],
        "C_signatarios": [frases.signatario_linha(p) for p in comp_pessoas],
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
        # [Q3] multa rescisória = the sinal's valor.
        "multa_rescisoria": sinal.valor,
        "resolutiva_notificacao_email": politica.resolutiva_notificacao_email,
        "corretagem": corretagem,
        # [Owner directive, 2026-09-23] The matrícula-derived comarca
        # (`carregador.carregar` -> `derivacao.comarca_de_texto`) — never
        # the imóvel address; gated `faltando` by `derivacao._contrato`,
        # so this is never blank.
        "foro": {"comarca": d.matricula.comarca},
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
            max(2, len(vend) + len(comp_pessoas)), feminino=True, largura=2
        ),
        "linha_assinatura": frases.LINHA_ASSINATURA,
        "V_assinantes_fisicos": [frases.assinante_fisico(p) for p in vend],
        "C_assinantes_fisicos": [frases.assinante_fisico(p) for p in comp_pessoas],
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
