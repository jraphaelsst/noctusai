"""
Matching algorithm — server-side scoring.

This module contains the core business logic for matching
imóveis with perfis de permuta. It calculates a compatibility
score from 0-100 based on 4 criteria:

  - Região (0-30 pts): location compatibility
  - Preço (0-25 pts): price range alignment
  - Especificações (0-20 pts): property specs match
  - Qualidade do anúncio (0-10 pts): listing completeness

Ported from the frontend useMatching.ts to run server-side.
"""
from typing import Any

from app.schemas.matching import MatchResult, MatchDetails


def calcular_score_regiao(imovel: dict[str, Any], perfil: dict[str, Any]) -> int:
    """
    Score based on region compatibility.
    Returns 0-30 points.
    """
    regiao_preferida = perfil.get("regiao_preferida") or []

    if not regiao_preferida:
        return 20  # No preference = neutral score

    for regiao in regiao_preferida:
        reg_lower = regiao.lower()
        cidade = (imovel.get("cidade") or "").lower()
        estado = (imovel.get("estado") or "").lower()
        bairro = (imovel.get("bairro") or "").lower()

        if reg_lower in cidade or reg_lower in estado or reg_lower in bairro:
            return 30  # Region match

    return 10  # Region mismatch


def calcular_score_preco(imovel: dict[str, Any], perfil: dict[str, Any]) -> int:
    """
    Score based on price range alignment.
    Returns 0-25 points.
    """
    faixa_min = perfil.get("faixa_preco_min")
    faixa_max = perfil.get("faixa_preco_max")

    if not faixa_min and not faixa_max:
        return 20  # No price preference

    preco = imovel.get("preco_pedido", 0)
    min_val = faixa_min or 0
    max_val = faixa_max or float("inf")

    if min_val <= preco <= max_val:
        # Score weighted by proximity to center
        effective_max = max_val if max_val != float("inf") else min_val * 2
        centro = (min_val + effective_max) / 2
        amplitude = (effective_max - min_val) / 2

        if amplitude == 0:
            return 25

        distancia_centro = abs(preco - centro)
        score_normalizado = 1 - (distancia_centro / amplitude)
        return round(25 * score_normalizado)

    # Outside range with 10% tolerance
    tolerancia = 0.1
    if preco < min_val and preco >= min_val * (1 - tolerancia):
        return 15
    if max_val != float("inf") and preco > max_val and preco <= max_val * (1 + tolerancia):
        return 15

    return 0


def calcular_score_especificacoes(imovel: dict[str, Any], perfil: dict[str, Any]) -> int:
    """
    Score based on property specification matching.
    Returns 0-20 points (5 pts each criterion).
    """
    score = 0

    # Property type
    if perfil.get("tipo_imovel") and perfil["tipo_imovel"] == imovel.get("tipo"):
        score += 5

    # Area
    metragem_min = perfil.get("metragem_min")
    metragem_max = perfil.get("metragem_max")
    if metragem_min or metragem_max:
        area = imovel.get("area_total") or imovel.get("area_privativa") or 0
        min_m = metragem_min or 0
        max_m = metragem_max or float("inf")
        if min_m <= area <= max_m:
            score += 5

    # Bedrooms
    quartos_min = perfil.get("quartos_min")
    quartos_imovel = imovel.get("quartos")
    if quartos_min and quartos_imovel and quartos_imovel >= quartos_min:
        score += 5

    # Parking
    vagas_min = perfil.get("vagas_min")
    vagas_imovel = imovel.get("vagas")
    if vagas_min and vagas_imovel and vagas_imovel >= vagas_min:
        score += 5

    return score


def calcular_qualidade_anuncio(imovel: dict[str, Any]) -> int:
    """
    Score based on listing completeness/quality.
    Returns 0-10 points.
    """
    score = 0

    # Photos
    fotos = imovel.get("fotos") or []
    if len(fotos) >= 8:
        score += 3
    elif len(fotos) >= 4:
        score += 2
    elif len(fotos) > 0:
        score += 1

    # Title and description
    titulo = imovel.get("titulo_anuncio") or ""
    descricao = imovel.get("descricao_seo") or ""
    if len(titulo) > 20:
        score += 2
    if len(descricao) > 50:
        score += 2

    # Keywords
    palavras = imovel.get("palavras_chave") or []
    if len(palavras) >= 3:
        score += 1

    # Points of interest
    pontos = imovel.get("pontos_de_interesse") or []
    if len(pontos) > 0:
        score += 1

    # Virtual tour
    if imovel.get("tour_virtual_url"):
        score += 1

    return score


def calcular_match(imovel: dict[str, Any], perfil: dict[str, Any]) -> MatchResult:
    """
    Calculate the compatibility match between an imóvel and a perfil de permuta.

    Returns a MatchResult with score 0-100, justification, and sub-score details.
    """
    # Only match imóvel permutas for now
    if perfil.get("categoria") != "imovel":
        return MatchResult(
            imovel_id=imovel["id"],
            perfil_permuta_id=perfil["id"],
            score=0,
            justificativa="Matching de móveis ainda não implementado",
            detalhes=MatchDetails(),
        )

    score_regiao = calcular_score_regiao(imovel, perfil)
    score_preco = calcular_score_preco(imovel, perfil)
    score_specs = calcular_score_especificacoes(imovel, perfil)
    score_qualidade = calcular_qualidade_anuncio(imovel)

    score_total = score_regiao + score_preco + score_specs + score_qualidade

    # Gap calculation
    gap_valor = imovel.get("preco_pedido", 0) - (perfil.get("valor_estimado") or 0)
    pode_complementar = (
        perfil.get("aceita_completar_diferenca")
        and gap_valor <= (perfil.get("limite_complemento") or 0)
    )

    # Build justification
    justificativa = ""
    if score_total >= 80:
        justificativa = "Compatibilidade alta. "
    elif score_total >= 60:
        justificativa = "Compatibilidade boa. "
    elif score_total >= 40:
        justificativa = "Compatibilidade média. "
    else:
        justificativa = "Compatibilidade baixa. "

    if score_regiao >= 25:
        justificativa += "Região compatível. "
    if score_preco >= 20:
        justificativa += "Preço dentro do esperado. "
    if gap_valor > 0 and pode_complementar:
        justificativa += f"Diferença de R$ {gap_valor:.2f} coberta pelo complemento."

    return MatchResult(
        imovel_id=imovel["id"],
        perfil_permuta_id=perfil["id"],
        score=min(score_total, 100),
        justificativa=justificativa.strip(),
        detalhes=MatchDetails(
            compatibilidade_regiao=score_regiao,
            compatibilidade_preco=score_preco,
            compatibilidade_specs=score_specs,
            qualidade_anuncio=score_qualidade,
            gap_valor=gap_valor,
        ),
    )


def gerar_matches_para_imovel(
    imovel: dict[str, Any],
    perfis: list[dict[str, Any]],
) -> list[MatchResult]:
    """Generate matches for one imóvel against all perfis."""
    matches = [calcular_match(imovel, perfil) for perfil in perfis]
    return sorted(
        [m for m in matches if m.score > 0],
        key=lambda m: m.score,
        reverse=True,
    )


def gerar_matches_para_perfil(
    perfil: dict[str, Any],
    imoveis: list[dict[str, Any]],
) -> list[MatchResult]:
    """Generate matches for one perfil against all imóveis."""
    matches = [calcular_match(imovel, perfil) for imovel in imoveis]
    return sorted(
        [m for m in matches if m.score > 0],
        key=lambda m: m.score,
        reverse=True,
    )
