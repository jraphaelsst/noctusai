"""
Matching Algorithm — Unified Ativos Table

Scores compatibility between an imovel (ativo natureza='imovel') and a
permuta (ativo natureza='permuta_imovel' or 'permuta_automovel').

Score breakdown (100 pts max):
  - Region compatibility:     30 pts
  - Price compatibility:      25 pts
  - Specs compatibility:      20 pts
  - Interest alignment:       15 pts
  - Listing quality:          10 pts
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def calcular_compatibilidade_regiao(imovel: dict, permuta: dict) -> int:
    """
    Compare location fields: cidade, estado, bairro, zona, regiao_preferida.
    Max 30 pts.
    """
    score = 0
    # Same state
    if imovel.get('estado') and permuta.get('estado'):
        if imovel['estado'].lower() == permuta['estado'].lower():
            score += 5

    # Same city
    if imovel.get('cidade') and permuta.get('cidade'):
        if imovel['cidade'].lower() == permuta['cidade'].lower():
            score += 10

    # Same bairro
    if imovel.get('bairro') and permuta.get('bairro'):
        if imovel['bairro'].lower() == permuta['bairro'].lower():
            score += 10

    # Region preference match
    regioes = permuta.get('regiao_preferida') or []
    if regioes:
        imovel_location = ' '.join(filter(None, [
            imovel.get('cidade', ''),
            imovel.get('estado', ''),
            imovel.get('bairro', ''),
        ])).lower()
        for regiao in regioes:
            if regiao.lower() in imovel_location:
                score += 5
                break

    # Same zona
    if imovel.get('zona') and permuta.get('zona'):
        if imovel['zona'].lower() == permuta['zona'].lower():
            score += 5

    return min(score, 30)


def calcular_compatibilidade_preco(imovel: dict, permuta: dict) -> int:
    """
    Compare valor of imovel vs permuta's price range.
    Max 25 pts.
    """
    valor_imovel = float(imovel.get('valor', 0) or 0)
    valor_permuta = float(permuta.get('valor', 0) or 0)
    faixa_min = float(permuta.get('faixa_preco_min', 0) or 0)
    faixa_max = float(permuta.get('faixa_preco_max', 0) or 0)

    if valor_imovel <= 0:
        return 0

    score = 0

    # Check if imovel valor is within permuta's price range
    if faixa_min > 0 and faixa_max > 0:
        if faixa_min <= valor_imovel <= faixa_max:
            score += 15
        elif valor_imovel < faixa_min:
            diff_pct = (faixa_min - valor_imovel) / faixa_min
            if diff_pct < 0.2:
                score += 8
        elif valor_imovel > faixa_max:
            diff_pct = (valor_imovel - faixa_max) / faixa_max
            if diff_pct < 0.2:
                score += 8

    # Direct value comparison
    if valor_permuta > 0:
        ratio = min(valor_imovel, valor_permuta) / max(valor_imovel, valor_permuta)
        score += int(ratio * 10)

    # Accepts completing the difference
    if permuta.get('aceita_completar_diferenca'):
        score += 3

    return min(score, 25)


def calcular_compatibilidade_specs(imovel: dict, permuta: dict) -> int:
    """
    Compare property specs (quartos, vagas, area) or vehicle specs (marca, modelo).
    Max 20 pts.
    """
    score = 0
    natureza_permuta = permuta.get('natureza', '')

    if natureza_permuta == 'permuta_imovel':
        # Property type match
        if (imovel.get('tipo_imovel') and permuta.get('tipo_imovel')
                and imovel['tipo_imovel'] == permuta['tipo_imovel']):
            score += 5

        # Quartos
        quartos_imovel = imovel.get('quartos', 0) or 0
        quartos_min = permuta.get('quartos_min', 0) or permuta.get('quartos', 0) or 0
        if quartos_min > 0 and quartos_imovel >= quartos_min:
            score += 5

        # Vagas
        vagas_imovel = imovel.get('vagas', 0) or 0
        vagas_min = permuta.get('vagas_min', 0) or permuta.get('vagas', 0) or 0
        if vagas_min > 0 and vagas_imovel >= vagas_min:
            score += 3

        # Area
        area_imovel = float(imovel.get('area_total', 0) or imovel.get('area_privativa', 0) or 0)
        metragem_min = float(permuta.get('metragem_min', 0) or 0)
        metragem_max = float(permuta.get('metragem_max', 0) or 0)
        if metragem_min > 0 and area_imovel >= metragem_min:
            score += 4
        if metragem_max > 0 and area_imovel <= metragem_max:
            score += 3

    elif natureza_permuta == 'permuta_automovel':
        # For auto matching — check interests on the imovel side
        interesses = imovel.get('interesses') or []
        for interesse in interesses:
            if interesse.get('tipo') == 'automovel':
                if (interesse.get('marca') and permuta.get('marca')
                        and interesse['marca'].lower() == permuta['marca'].lower()):
                    score += 10
                if (interesse.get('modelo') and permuta.get('modelo')
                        and interesse['modelo'].lower() == permuta['modelo'].lower()):
                    score += 5
                valor_min = float(interesse.get('valor_min', 0) or 0)
                valor_max = float(interesse.get('valor_max', 0) or 0)
                valor_auto = float(permuta.get('valor', 0) or 0)
                if valor_min <= valor_auto <= valor_max:
                    score += 5
                break

    return min(score, 20)


def calcular_alinhamento_interesses(imovel: dict, permuta: dict) -> int:
    """
    Check if the imovel's interesses JSON matches the permuta's natureza and attributes.
    Max 15 pts.
    """
    interesses = imovel.get('interesses') or []
    if not interesses:
        return 0

    score = 0
    natureza_permuta = permuta.get('natureza', '')

    for interesse in interesses:
        tipo_interesse = interesse.get('tipo', '')

        # Match natureza type
        if ((tipo_interesse == 'imovel' and natureza_permuta == 'permuta_imovel') or
                (tipo_interesse == 'automovel' and natureza_permuta == 'permuta_automovel')):
            score += 8

            # Check sub-criteria
            if tipo_interesse == 'imovel':
                if (interesse.get('tipo_imovel') and permuta.get('tipo_imovel')
                        and interesse['tipo_imovel'] == permuta['tipo_imovel']):
                    score += 4
                if interesse.get('cidade') and permuta.get('cidade'):
                    if interesse['cidade'].lower() == permuta['cidade'].lower():
                        score += 3

            break

    return min(score, 15)


def calcular_qualidade_anuncio(imovel: dict) -> int:
    """
    Score listing quality based on completeness of the imovel record.
    Max 10 pts.
    """
    score = 0
    if imovel.get('titulo_anuncio'):
        score += 2
    if imovel.get('descricao_seo'):
        score += 2
    fotos = imovel.get('fotos') or []
    if len(fotos) >= 3:
        score += 3
    elif len(fotos) >= 1:
        score += 1
    if imovel.get('tour_virtual_url'):
        score += 1
    if imovel.get('pontos_de_interesse'):
        score += 1
    if imovel.get('condominio_nome') or imovel.get('condominio_id'):
        score += 1
    return min(score, 10)


def calcular_score_total(imovel: dict, permuta: dict) -> dict:
    """
    Calculate total match score between an imovel and a permuta.
    Returns dict with score, sub-scores, justificativa.
    """
    regiao = calcular_compatibilidade_regiao(imovel, permuta)
    preco = calcular_compatibilidade_preco(imovel, permuta)
    specs = calcular_compatibilidade_specs(imovel, permuta)
    interesses = calcular_alinhamento_interesses(imovel, permuta)
    qualidade = calcular_qualidade_anuncio(imovel)

    total = regiao + preco + specs + interesses + qualidade

    # Build justificativa
    justificativa_parts = []
    if regiao >= 15:
        justificativa_parts.append("Boa compatibilidade de região")
    if preco >= 15:
        justificativa_parts.append("Preço alinhado")
    if specs >= 10:
        justificativa_parts.append("Características compatíveis")
    if interesses >= 8:
        justificativa_parts.append("Alinhado com interesses")

    valor_imovel = float(imovel.get('valor', 0) or 0)
    valor_permuta = float(permuta.get('valor', 0) or 0)

    return {
        'score': total,
        'justificativa': '. '.join(justificativa_parts) if justificativa_parts else 'Match parcial',
        'detalhes': {
            'compatibilidade_regiao': regiao,
            'compatibilidade_preco': preco,
            'compatibilidade_specs': specs,
            'alinhamento_interesses': interesses,
            'qualidade_anuncio': qualidade,
            'gap_valor': abs(valor_imovel - valor_permuta),
        },
    }


def gerar_matches_para_imovel(imovel: dict, permutas: list[dict], score_minimo: int = 20) -> list[dict]:
    """
    Generate matches for a single imovel against all permutas.
    """
    matches = []
    for permuta in permutas:
        if permuta.get('owner_id') == imovel.get('owner_id'):
            continue
        if permuta.get('status', 'ativo') != 'ativo':
            continue

        resultado = calcular_score_total(imovel, permuta)
        if resultado['score'] >= score_minimo:
            matches.append({
                'ativo_origem_id': imovel['id'],
                'ativo_destino_id': permuta['id'],
                **resultado,
            })

    matches.sort(key=lambda m: m['score'], reverse=True)
    return matches


def gerar_matches_para_permuta(permuta: dict, imoveis: list[dict], score_minimo: int = 20) -> list[dict]:
    """
    Generate matches for a single permuta against all imoveis (that accept permutas).
    """
    matches = []
    for imovel in imoveis:
        if imovel.get('owner_id') == permuta.get('owner_id'):
            continue
        if not imovel.get('aceita_permutas'):
            continue
        if imovel.get('status', 'ativo') != 'ativo':
            continue

        resultado = calcular_score_total(imovel, permuta)
        if resultado['score'] >= score_minimo:
            matches.append({
                'ativo_origem_id': imovel['id'],
                'ativo_destino_id': permuta['id'],
                **resultado,
            })

    matches.sort(key=lambda m: m['score'], reverse=True)
    return matches
