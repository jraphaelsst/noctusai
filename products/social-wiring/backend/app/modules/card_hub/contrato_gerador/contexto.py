"""`DadosContrato` -> the template context (spec §3 placeholder dictionary).

Only reached after `derivacao.avaliar` returned `pronto` — every value used
here has been gated present. Money stays `Decimal` until `brl()` prints it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from noctusai_lib.domain.texto_ptbr import (
    CENTAVO,
    brl_por_extenso,
    data_por_extenso,
    dias_por_extenso,
    percentual_por_extenso,
)

from app.modules.card_hub.contrato_gerador import frases
from app.modules.card_hub.contrato_gerador.concordancia import lado, normalizar_genero
from app.modules.card_hub.contrato_gerador.dados import DadosContrato, Pessoa, signatarios
from app.modules.card_hub.contrato_gerador.derivacao import (
    grupos_pj,
    indice_certidoes,
    parcelas_ordenadas,
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


def _generos(pessoas: list[Pessoa]) -> list[str]:
    return [normalizar_genero(p.genero) or "m" for p in pessoas]


def _texto_parcela_permuta(valor: Decimal, d: DadosContrato, C) -> str:
    """The permuta parcela (spec §2.3 `p.tipo == 'permuta'`). Its value and the
    permuta imóvel description are §6.1 Complementos."""
    imoveis = d.complementos.permuta_imoveis
    nomes = juntar([(p.nome or "").upper() for p in signatarios(d.compradores)])
    descricoes = " E ".join(
        f"{i.descricao_matricula} Imóvel devidamente cadastrado pela Prefeitura Municipal de "
        f"{i.cidade} sob nº {i.inscricao_municipal} e caracterizado na Matrícula Nº "
        f"{frases.matricula_numero(i.matricula_numero)} do {i.cartorio}."
        for i in imoveis
    )
    plural = len(imoveis) > 1
    return (
        f" {brl_por_extenso(valor)}, por permuta {'dos imóveis' if plural else 'do imóvel'} de "
        f"propriedade {C.dos} {C.NOME.title()}, {nomes}, já {C.g('qualificado', 'qualificada', 'qualificados')} "
        f"anteriormente, {'caracterizados' if plural else 'caracterizado'} como: {descricoes}"
    )


def montar_contexto(
    d: DadosContrato,
    sw: dict[str, bool],
    politica: Politica,
    assinatura: date,
    par: ContadorParagrafos,
) -> dict[str, Any]:
    cl = numerar_clausulas(sw)
    vend, comp_pessoas = signatarios(d.vendedores), signatarios(d.compradores)
    V, C = lado(_generos(vend), "vendedor"), lado(_generos(comp_pessoas), "comprador")
    comp = d.complementos
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
        "fgts": refs("fgts"),
        "saldo": refs("saldo"),
        "permuta": num2(len(parcelas) + 1) if sw["tem_permuta"] else "",
    }
    favorecidos = {f.id: f for f in d.favorecidos}
    cpf_vendedor = {frases.so_digitos(p.cpf): p for p in vend if p.cpf}
    ja_usados: set[str] = set()
    linhas_parcelas = []
    for p in parcelas:
        fav = favorecidos.get(p.favorecido_id or "") if p.tipo in {"sinal", "intermediaria", "direta", "saldo"} else None
        linhas_parcelas.append(
            {
                "num": nums[p.id],
                "texto": frases.texto_parcela(
                    p,
                    V=V,
                    C=C,
                    tem_financiamento=sw["tem_financiamento"],
                    ref_financiamento=p_ref["financiamento"],
                    favorecido=fav,
                    favorecido_repetido=bool(fav and fav.id in ja_usados),
                    vendedor_favorecido=cpf_vendedor.get(frases.so_digitos(fav.cpf_cnpj)) if fav else None,
                    juros_am=comp.juros_am_confissao if p.confissao_divida else None,
                ),
            }
        )
        if fav is not None:
            ja_usados.add(fav.id)
    if sw["tem_permuta"]:
        linhas_parcelas.append(
            {"num": p_ref["permuta"], "texto": _texto_parcela_permuta(comp.permuta_parcela_valor, d, C)}  # type: ignore[arg-type]
        )

    sinal = next(p for p in parcelas if p.tipo == "sinal")
    confissao_parcelas = [p for p in parcelas if p.confissao_divida]

    # ── imóvel ──
    e = im.endereco
    if im.empreendimento:
        titulo_curto = f"{im.empreendimento} – {e.complemento}" if e.complemento else im.empreendimento
    else:
        titulo_curto = f"{e.logradouro}, nº {e.numero}"
    em_condominio = EM_CONDOMINIO_QUANDO_HA_EMPREENDIMENTO and bool(im.empreendimento)
    imovel = {
        "titulo_curto": titulo_curto,
        "cidade": e.cidade,
        "uf": (e.uf or "").upper(),
        "descricao_matricula": d.matricula.texto.rstrip(),
        "inscricao_municipal": im.inscricao_municipal,
        "matricula_numero": frases.matricula_numero(im.numero_matricula),
        "cartorio": im.numero_registro_imoveis,
        "endereco_curto": frases.endereco_curto(e),
        "em_condominio": em_condominio,
    }

    # ── certidões ──
    pessoas_cert = vend + (comp_pessoas if sw["tem_permuta"] else [])
    grupos, pendentes_cert = [], []
    n = 0
    for p in pessoas_cert:
        idx, _ = indice_certidoes(p.certidoes or [], "cpf", politica)
        n += 1
        grupos.append(
            {"num": n, "em_nome_de": p.nome, "itens": [frases.item_certidao(t, idx[t]) for t in tipos_exigidos("cpf")]}
        )
        pendentes_cert += [frases.pendencia_certidao(t, p.nome or "") for t in tipos_exigidos("cpf") if idx[t].resultado == "nao_emitida"]
    for p in pessoas_cert:
        for documento, certs in grupos_pj(p).items():
            idx, _ = indice_certidoes(certs, "cnpj", politica)
            nome_pj = certs[0].consulta_nome or documento
            n += 1
            tipos = [t for t in tipos_exigidos("cnpj") if t in idx]
            grupos.append({"num": n, "em_nome_de": nome_pj, "itens": [frases.item_certidao(t, idx[t]) for t in tipos]})
            pendentes_cert += [frases.pendencia_certidao(t, nome_pj) for t in tipos if idx[t].resultado == "nao_emitida"]
    grupos_imovel = []
    if im.onus_certidao_em and im.numero_matricula:
        n += 1
        grupos_imovel.append(
            {"num": n, "titulo": imovel["endereco_curto"], "itens": [frases.item_matricula_imovel(im.numero_matricula, im.onus_certidao_em)]}
        )

    pendencias: list[str] = []
    if em_condominio:
        pendencias.append(frases.PENDENCIA_CONDOMINIO_PERMUTA if sw["tem_permuta"] else frases.PENDENCIA_CONDOMINIO)
    pendencias.append(frases.pendencia_estado_civil(politica.comprovante_estado_civil_max_dias))
    pendencias.append(frases.PENDENCIA_DOCUMENTOS)
    if not grupos_imovel:
        pendencias.append(frases.PENDENCIA_MATRICULA)
    pendencias.append(frases.PENDENCIA_CONTAS_CONSUMO)
    pendencias.append(frases.PENDENCIA_IPTU)
    if sw["tem_saldo_devedor"]:
        pendencias.append(frases.pendencia_baixa_onus(im.situacao_onus or ""))
    pendencias += pendentes_cert

    if sw["tem_permuta"]:
        apresentantes, plural_apres = f"{V.ART} {V.NOME} e {C.art} {C.NOME}", True
    else:
        apresentantes, plural_apres = f"{V.ART} {V.NOME}", V.plural
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
            "credor": comp.onus_credor,
            "fonte_texto": frases.onus_fonte_texto(im.onus_fonte_atos),
            "quitacao": comp.onus_quitacao,
            "quitacao_texto": frases.onus_quitacao_texto(
                comp.onus_quitacao or "",
                C=C,
                ref_saldo=p_ref["saldo"],
                ref_clausula_preco=cl["preco"].ref if comp.onus_quitacao == "parcela" else "",
            ),
            "prazo_dias": comp.onus_prazo_dias,
        }

    marco = comp.posse_marco or ""
    if marco == "parcela_financiamento":
        primeira_fin = next(i for i, p in enumerate(parcelas) if p.tipo == "financiamento")
        condicao = frases.condicao_posse_frase([nums[p.id] for p in parcelas[:primeira_fin]], todas=False)
    elif marco != "assinatura" and sw["a_vista"]:
        condicao = frases.condicao_posse_frase([], todas=True)
    else:
        condicao = ""
    posse = {
        "prazo": comp.posse_prazo_dias,
        "marco_texto": frases.posse_marco_texto(marco, ref_financiamento=p_ref["financiamento"]),
        "condicao_frase": condicao,
        "multa_diaria": politica.posse_multa_diaria,
    }
    permuta: dict[str, Any] = {}
    if sw["tem_permuta"]:
        permuta = {
            "endereco_curto": comp.permuta_imoveis[0].endereco_curto,
            "posse_prazo": comp.permuta_posse_prazo_dias,
            "posse_marco_texto": frases.posse_marco_texto(
                comp.permuta_posse_marco or "", ref_financiamento=p_ref["financiamento"]
            ),
            "despesas_texto": frases.despesas_permuta_texto(politica.permuta_despesas or "", C=C),
        }

    # ── intermediação ──
    corretagem: dict[str, Any] = {}
    if sw["tem_intermediacao"]:
        qualificados = []
        if any(i.corretor_id for i in d.intermediarios):
            qualificados.append(frases.qualificacao_imobiliaria(d.imobiliaria))
        qualificados += [comp.intermediarios_qualificacao[i.id] for i in d.intermediarios if not i.corretor_id]
        texto, texto_cap, contrata = frases.corretagem_contratantes(comp.corretagem_contratantes or "", V=V)
        valores = []
        for it in d.intermediarios:
            if it.tipo == "percentual":
                valor = (d.valor_negociado * it.valor / Decimal(100)).quantize(CENTAVO, rounding=ROUND_HALF_UP)  # type: ignore[operator]
            else:
                valor = it.valor  # type: ignore[assignment]
            valores.append((valor, favorecidos[comp.corretagem_favorecidos[it.id]]))
        plural_emp = len(qualificados) > 1
        corretagem = {
            "qualificados": qualificados,
            "contratantes_texto": texto,
            "contratantes_texto_cap": texto_cap,
            "contrata": contrata,
            "empresas_texto": "as empresas a seguir qualificadas" if plural_emp else "a empresa a seguir qualificada",
            "contratadas_texto": "as empresas contratadas" if plural_emp else "a empresa contratada",
            "total": sum((v for v, _ in valores), Decimal("0")),
            "parcelamento_texto": frases.parcelamento_texto(comp.corretagem_num_parcelas),
            "marcos_texto": frases.marcos_texto([num2(x) for x in comp.corretagem_parcelas_marco]),
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
        "V_qualificacao": frases.qualificacao(vend, citar_lei_6515=politica.citar_lei_6515),
        "C_qualificacao": frases.qualificacao(comp_pessoas, citar_lei_6515=politica.citar_lei_6515),
        "V_signatarios": [frases.signatario_linha(p, com_email=politica.email_no_bloco_assinatura) for p in vend],
        "C_signatarios": [frases.signatario_linha(p, com_email=politica.email_no_bloco_assinatura) for p in comp_pessoas],
        "imovel": imovel,
        "titulo_aquisitivo": (comp.titulo_aquisitivo_texto or "").strip(),
        "itens_integrantes": (comp.itens_integrantes or "").strip(),
        "preco": d.valor_negociado,
        "parcelas": linhas_parcelas,
        "p_ref": p_ref,
        "confissao": {
            "parcelas_nums": juntar([nums[p.id] for p in confissao_parcelas]),
            "total": sum((p.valor for p in confissao_parcelas), Decimal("0")),  # type: ignore[misc]
            "juros_am": comp.juros_am_confissao,
            "garantia_texto": (comp.garantia_confissao or "").strip(),
        },
        "certidoes": certidoes,
        "prazo_pendencias": politica.prazo_pendencias_dias,
        "prazo_esclarecimentos": politica.prazo_esclarecimentos_dias,
        "onus": onus,
        "posse": posse,
        "permuta": permuta,
        "rescisao": {
            "cura_frase": frases.cura_rescisao_frase(politica.rescisao_cura_dias),
            "encargo_texto": frases.ENCARGO_RESCISAO_TEXTO.get(politica.rescisao_encargo or "nenhum", ""),
        },
        # [Q3] multa rescisória = the sinal's valor.
        "multa_rescisoria": sinal.valor,
        "resolutiva_notificacao_email": politica.resolutiva_notificacao_email,
        "corretagem": corretagem,
        "foro": {"comarca": f"{e.cidade}/{(e.uf or '').upper()}"},
        "assinatura": {
            "local": d.imobiliaria.endereco.cidade,
            "data_extenso": data_por_extenso(assinatura),
            "plataforma_nome": comp.plataforma_assinatura_nome,
            "plataforma_url": comp.plataforma_assinatura_url,
        },
        "testemunhas": [{"nome": (t.nome or "").upper(), "rg": t.rg} for t in d.testemunhas],
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
