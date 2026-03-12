"""
Matching Algorithm — Unified Ativos Table

Scores compatibility between an imovel (ativo natureza='imovel') and a
permuta (ativo natureza='permuta_imovel' or 'permuta_automovel').

Rule-based score breakdown (100 pts max):
  - Region compatibility:     30 pts
  - Price compatibility:      25 pts
  - Specs compatibility:      20 pts
  - Interest alignment:       15 pts
  - Listing quality:          10 pts

Composite score (when embeddings available):
  - Embedding similarity:     40%
  - Price compatibility:      25%
  - Specs compatibility:      20%
  - Interest alignment:       15%
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


def calcular_score_composto(similarity: float, preco: int, specs: int, interesses: int) -> float:
    """
    Calculate composite score using weighted formula:
      40% embedding similarity + 25% price + 20% specs + 15% interests.

    Each sub-score is normalized to 0-100 before weighting.
    Returns a float score capped at 100.0.
    """
    score = (
        0.40 * (similarity * 100)
        + 0.25 * (preco / 25) * 100
        + 0.20 * (specs / 20) * 100
        + 0.15 * (interesses / 15) * 100
    )
    return round(min(score, 100.0), 1)


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
        'score': float(total),
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


def gerar_matches_para_imovel(imovel: dict, permutas: list[dict], score_minimo: float = 20) -> list[dict]:
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


def gerar_matches_para_permuta(permuta: dict, imoveis: list[dict], score_minimo: float = 20) -> list[dict]:
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


def upsert_matches(matches: list[dict], db) -> None:
    """
    Persist matches to the database in a single bulk upsert.

    Args:
        matches: List of match dicts from gerar_matches_* functions.
        db: Supabase client.
    """
    if not matches:
        return

    all_upsert_data = []
    for match in matches:
        upsert_data = {
            "ativo_origem_id": match["ativo_origem_id"],
            "ativo_destino_id": match["ativo_destino_id"],
            "score": match["score"],
            "justificativa": match["justificativa"],
            "detalhes": match["detalhes"],
            "status": "pendente",
        }
        if "score_breakdown" in match:
            upsert_data["score_breakdown"] = match["score_breakdown"]
        all_upsert_data.append(upsert_data)

    db.table("matches").upsert(
        all_upsert_data,
        on_conflict="ativo_origem_id,ativo_destino_id",
    ).execute()

    logger.info(f"Bulk upserted {len(all_upsert_data)} matches")


async def gerar_matches_com_embeddings(
    source_ativo: dict,
    db,
    score_minimo: float = 20.0,
    match_count: int = 50,
) -> list[dict]:
    """
    Generate matches using embedding similarity + structured sub-scores.
    Composite: 40% semantic + 25% price + 20% specs + 15% interests.

    Requires the source ativo to have an embedding. Returns empty list if not.
    """
    embedding = source_ativo.get("embedding")
    if not embedding:
        logger.info(f"Ativo {source_ativo.get('id')} has no embedding, skipping AI matching")
        return []

    # Call Supabase RPC for semantic similarity search
    rpc_result = db.rpc(
        "match_ativos",
        {
            "query_embedding": embedding,
            "match_count": match_count,
            "similarity_threshold": 0.3,
            "exclude_id": source_ativo["id"],
        },
    ).execute()

    candidates = rpc_result.data or []
    if not candidates:
        return []

    matches = []
    is_imovel = source_ativo.get("natureza") == "imovel"

    for candidate in candidates:
        candidate_id = candidate["id"]
        similarity = float(candidate["similarity"])

        # Fetch full ativo data
        ativo_res = db.table("ativos").select("*").eq("id", candidate_id).single().execute()
        if not ativo_res.data:
            continue

        candidate_ativo = ativo_res.data

        # Skip same owner
        if candidate_ativo.get("owner_id") == source_ativo.get("owner_id"):
            continue
        # Skip inactive
        if candidate_ativo.get("status", "ativo") != "ativo":
            continue

        # Determine imovel/permuta roles for structured scoring
        if is_imovel:
            imovel = source_ativo
            permuta = candidate_ativo
            # Skip if candidate is also an imovel (we need a permuta)
            if candidate_ativo.get("natureza") == "imovel":
                continue
        else:
            permuta = source_ativo
            imovel = candidate_ativo
            # Skip if candidate is also a permuta
            if candidate_ativo.get("natureza") != "imovel":
                continue
            # Skip if imovel doesn't accept permutas
            if not imovel.get("aceita_permutas"):
                continue

        # Compute structured sub-scores
        preco = calcular_compatibilidade_preco(imovel, permuta)
        specs = calcular_compatibilidade_specs(imovel, permuta)
        interesses = calcular_alinhamento_interesses(imovel, permuta)

        # Composite score
        score = calcular_score_composto(similarity, preco, specs, interesses)

        if score < score_minimo:
            continue

        # Build justificativa
        justificativa_parts = []
        if similarity >= 0.7:
            justificativa_parts.append("Alta similaridade semântica")
        elif similarity >= 0.5:
            justificativa_parts.append("Boa similaridade semântica")
        if preco >= 15:
            justificativa_parts.append("Preço alinhado")
        if specs >= 10:
            justificativa_parts.append("Características compatíveis")
        if interesses >= 8:
            justificativa_parts.append("Alinhado com interesses")

        matches.append({
            "ativo_origem_id": imovel["id"],
            "ativo_destino_id": permuta["id"],
            "score": score,
            "justificativa": ". ".join(justificativa_parts) if justificativa_parts else "Match parcial",
            "detalhes": {
                "compatibilidade_preco": preco,
                "compatibilidade_specs": specs,
                "alinhamento_interesses": interesses,
                "embedding_similarity": round(similarity, 4),
            },
            "score_breakdown": {
                "embedding": round(similarity * 100, 1),
                "preco": round((preco / 25) * 100, 1),
                "specs": round((specs / 20) * 100, 1),
                "interesses": round((interesses / 15) * 100, 1),
                "weights": {
                    "embedding": 0.40,
                    "preco": 0.25,
                    "specs": 0.20,
                    "interesses": 0.15,
                },
            },
        })

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches
