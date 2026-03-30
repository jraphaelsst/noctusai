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

Hard filters (applied BEFORE scoring):
  - permuta_imovel: must share at least same state (região ≥ 5)
  - permuta_automovel: imovel must have an explicit automovel interest
  - All: must score meaningfully in at least 2 of 3 core categories
    (região, preço, specs) — prevents noise from partial-credit accumulation

Composite score (when embeddings available):
  - Embedding similarity:     40%
  - Price compatibility:      25%
  - Specs compatibility:      20%
  - Interest alignment:       15%
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Minimum thresholds for each category to count as "meaningful"
_MIN_REGIAO = 5       # at least same state
_MIN_PRECO = 8        # at least close to price range or decent ratio
_MIN_SPECS = 5        # at least type match or quartos match


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


def _permuta_atende_interesse(permuta: dict, interesse: dict) -> bool:
    """
    Check if a permuta's actual profile (what they're offering) satisfies
    one of the imóvel owner's interesse criteria.

    For imovel interests: check cidade, tipo_imovel, valor range.
    For automovel interests: check marca, modelo, valor range.

    Lenient: only checks fields the owner actually specified.
    Returns True if all specified criteria match.
    """
    tipo = interesse.get("tipo", "")
    natureza = permuta.get("natureza", "")

    # Type must align
    if tipo == "imovel" and natureza != "permuta_imovel":
        return False
    if tipo == "automovel" and natureza != "permuta_automovel":
        return False

    if tipo == "imovel":
        # City check
        cidade_int = (interesse.get("cidade") or "").strip().lower()
        cidade_perm = (permuta.get("cidade") or "").strip().lower()
        if cidade_int and cidade_perm and cidade_int != cidade_perm:
            return False

        # Property type check
        tipo_im_int = (interesse.get("tipo_imovel") or "").strip().lower()
        tipo_im_perm = (permuta.get("tipo_imovel") or "").strip().lower()
        if tipo_im_int and tipo_im_perm and tipo_im_int != tipo_im_perm:
            return False

        # Value range check
        valor_perm = float(permuta.get("valor", 0) or 0)
        valor_min = float(interesse.get("valor_min", 0) or 0)
        valor_max = float(interesse.get("valor_max", 0) or 0)
        if valor_perm > 0 and valor_min > 0 and valor_max > 0:
            # Allow 20% tolerance beyond the range
            if valor_perm < valor_min * 0.8 or valor_perm > valor_max * 1.2:
                return False

    elif tipo == "automovel":
        marca_int = (interesse.get("marca") or "").strip().lower()
        marca_perm = (permuta.get("marca") or "").strip().lower()
        if marca_int and marca_perm and marca_int != marca_perm:
            return False

        modelo_int = (interesse.get("modelo") or "").strip().lower()
        modelo_perm = (permuta.get("modelo") or "").strip().lower()
        if modelo_int and modelo_perm and modelo_int != modelo_perm:
            return False

        valor_perm = float(permuta.get("valor", 0) or 0)
        valor_min = float(interesse.get("valor_min", 0) or 0)
        valor_max = float(interesse.get("valor_max", 0) or 0)
        if valor_perm > 0 and valor_min > 0 and valor_max > 0:
            if valor_perm < valor_min * 0.8 or valor_perm > valor_max * 1.2:
                return False

    return True


def _imovel_atende_permuta(imovel: dict, permuta: dict) -> bool:
    """
    Reverse bilateral: does the imóvel's profile satisfy what the permuta wants?

    If the permuta has `interesses`, check those (symmetric with _permuta_atende_interesse).
    Otherwise, fall back to the permuta's search criteria fields:
      - faixa_preco_min/max → imóvel valor must be in range (20% tolerance)
      - regiao_preferida → imóvel location must match at least one
    """
    # ── Path 1: permuta has explicit interesses ──
    interesses_list = permuta.get("interesses") or []
    if interesses_list:
        for interesse in interesses_list:
            tipo = interesse.get("tipo", "")
            if tipo != "imovel":
                continue

            # City check
            cidade_int = (interesse.get("cidade") or "").strip().lower()
            cidade_im = (imovel.get("cidade") or "").strip().lower()
            if cidade_int and cidade_im and cidade_int != cidade_im:
                continue

            # Property type check
            tipo_int = (interesse.get("tipo_imovel") or "").strip().lower()
            tipo_im = (imovel.get("tipo_imovel") or "").strip().lower()
            if tipo_int and tipo_im and tipo_int != tipo_im:
                continue

            # Value range check
            valor_im = float(imovel.get("valor", 0) or 0)
            valor_min = float(interesse.get("valor_min", 0) or 0)
            valor_max = float(interesse.get("valor_max", 0) or 0)
            if valor_im > 0 and valor_min > 0 and valor_max > 0:
                if valor_im < valor_min * 0.8 or valor_im > valor_max * 1.2:
                    continue

            return True  # at least one interesse matched

        return False  # none of the interesses matched

    # ── Path 2: use permuta's search criteria fields ──
    valor_im = float(imovel.get("valor", 0) or 0)
    faixa_min = float(permuta.get("faixa_preco_min", 0) or 0)
    faixa_max = float(permuta.get("faixa_preco_max", 0) or 0)
    if valor_im > 0 and faixa_min > 0 and faixa_max > 0:
        if valor_im < faixa_min * 0.8 or valor_im > faixa_max * 1.2:
            return False

    regioes = permuta.get("regiao_preferida") or []
    if regioes:
        imovel_location = " ".join(filter(None, [
            imovel.get("cidade", ""),
            imovel.get("bairro", ""),
            imovel.get("zona", ""),
        ])).lower()
        if not any(r.lower() in imovel_location for r in regioes):
            return False

    return True


def _passa_filtros_minimos(imovel: dict, permuta: dict, regiao: int, preco: int, specs: int) -> bool:
    """
    Hard gate: discard pairs that don't meet minimum relevance criteria.
    Returns True if the pair should proceed to scoring, False to skip.

    Rules:
      1. Bilateral A→B: the permuta's profile (what they offer) must satisfy
         at least one of the imóvel owner's interesses.
      2. Bilateral B→A: the imóvel's profile must satisfy what the permuta wants
         (via permuta's interesses or search criteria like faixa_preco, regiao_preferida).
      3. permuta_imovel: must share at least same state (regiao >= 5)
      4. permuta_automovel: imovel must have an explicit automovel interest
      5. All: must score meaningfully in at least 2 of 3 core categories
    """
    natureza = permuta.get("natureza", "")
    interesses_list = imovel.get("interesses") or []

    # ── Bilateral A→B: does the permuta's profile match what the imovel owner wants? ──
    if interesses_list:
        if not any(_permuta_atende_interesse(permuta, i) for i in interesses_list):
            return False

    # ── Bilateral B→A: does the imóvel match what the permuta wants? ──
    if not _imovel_atende_permuta(imovel, permuta):
        return False

    # ── Type-specific gates ──
    if natureza == "permuta_imovel":
        # Hard region gate: no match across completely unrelated locations
        if regiao < _MIN_REGIAO:
            return False

    elif natureza == "permuta_automovel":
        # Automovel permutas only make sense if the imovel owner explicitly
        # listed interest in automobiles
        has_auto_interest = any(
            i.get("tipo") == "automovel" for i in interesses_list
        )
        if not has_auto_interest:
            return False

    # ── Require meaningful scores in at least 2 of 3 core categories ──
    meaningful = 0
    if regiao >= _MIN_REGIAO:
        meaningful += 1
    if preco >= _MIN_PRECO:
        meaningful += 1
    if specs >= _MIN_SPECS:
        meaningful += 1

    return meaningful >= 2


_SIM_THRESHOLD = 0.60


def _calcular_bilateral_similarity(imovel: dict, permuta: dict) -> float:
    """
    Compute bilateral embedding similarity (profile↔interest).

    B→A: cosine(imovel.embedding, permuta.embedding_interesses)
         → does the permuta WANT this imovel?
    A→B: cosine(permuta.embedding, imovel.embedding_interesses)
         → does the imovel owner WANT what the permuta offers?

    Returns avg similarity, or 0.0 if embeddings are missing or below threshold.
    """
    imovel_profile = imovel.get("embedding")
    permuta_interest = permuta.get("embedding_interesses")
    permuta_profile = permuta.get("embedding")
    imovel_interest = imovel.get("embedding_interesses")

    if not (imovel_profile and permuta_interest and permuta_profile and imovel_interest):
        return 0.0

    # Cosine similarity
    def _cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    sim_ba = _cosine(imovel_profile, permuta_interest)
    sim_ab = _cosine(permuta_profile, imovel_interest)

    # Both directions must clear the threshold
    if sim_ba < _SIM_THRESHOLD or sim_ab < _SIM_THRESHOLD:
        return 0.0

    return (sim_ba + sim_ab) / 2.0


def calcular_score_total(imovel: dict, permuta: dict) -> Any:
    """
    Calculate total match score between an imovel and a permuta.

    Flow: hard filters first (free) → structured scoring → embedding enhancement.
    If both ativos have embeddings, bilateral similarity is blended into the score.
    Returns None if the pair fails hard filters.
    """
    regiao = calcular_compatibilidade_regiao(imovel, permuta)
    preco = calcular_compatibilidade_preco(imovel, permuta)
    specs = calcular_compatibilidade_specs(imovel, permuta)

    # Hard gate: discard pairs that don't meet minimum relevance
    if not _passa_filtros_minimos(imovel, permuta, regiao, preco, specs):
        return None

    interesses = calcular_alinhamento_interesses(imovel, permuta)
    qualidade = calcular_qualidade_anuncio(imovel)

    # Rule-based score (100 pts max)
    rule_score = float(regiao + preco + specs + interesses + qualidade)

    # Embedding enhancement: only computed for pairs that passed hard filters
    similarity = _calcular_bilateral_similarity(imovel, permuta)

    if similarity > 0:
        # Composite: 40% semantic + 25% price + 20% specs + 15% interests
        composite = (
            0.40 * (similarity * 100)
            + 0.25 * (preco / 25) * 100
            + 0.20 * (specs / 20) * 100
            + 0.15 * (interesses / 15) * 100
        )
        total = round(min(composite, 100.0), 1)
    else:
        total = rule_score

    # Build justificativa
    justificativa_parts = []
    if similarity >= 0.7:
        justificativa_parts.append("Alta compatibilidade bilateral")
    elif similarity >= 0.5:
        justificativa_parts.append("Boa compatibilidade bilateral")
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
            'embedding_similarity': round(similarity, 4) if similarity > 0 else 0,
        },
        'score_breakdown': {
            'embedding_similarity': round(similarity * 100, 1) if similarity > 0 else 0,
            'compatibilidade_regiao': round((regiao / 30) * 100, 1),
            'compatibilidade_preco': round((preco / 25) * 100, 1),
            'compatibilidade_specs': round((specs / 20) * 100, 1),
            'qualidade_anuncio': round((qualidade / 10) * 100, 1),
            'interesses': round((interesses / 15) * 100, 1),
        },
    }


def gerar_matches_para_imovel(imovel: dict, permutas: list[dict], score_minimo: float = 45) -> list[dict]:
    """
    Generate matches for a single imovel against all permutas.
    Applies hard filters before scoring to discard irrelevant pairs.
    """
    matches = []
    for permuta in permutas:
        if permuta.get('owner_id') == imovel.get('owner_id'):
            continue
        if permuta.get('status', 'ativo') != 'ativo':
            continue

        resultado = calcular_score_total(imovel, permuta)
        if resultado is None:
            continue
        if resultado['score'] >= score_minimo:
            matches.append({
                'ativo_origem_id': imovel['id'],
                'ativo_destino_id': permuta['id'],
                **resultado,
            })

    matches.sort(key=lambda m: m['score'], reverse=True)
    return matches


def gerar_matches_para_permuta(permuta: dict, imoveis: list[dict], score_minimo: float = 45) -> list[dict]:
    """
    Generate matches for a single permuta against all imoveis (that accept permutas).
    Applies hard filters before scoring to discard irrelevant pairs.
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
        if resultado is None:
            continue
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
    Skips pairs that already have non-pendente status (accepted/rejected).

    Args:
        matches: List of match dicts from gerar_matches_* functions.
        db: Supabase client.
    """
    if not matches:
        return

    # Get pairs that already have non-pendente status (accepted/rejected)
    origin_ids = list({m["ativo_origem_id"] for m in matches})
    existing = db.table("matches").select("ativo_origem_id,ativo_destino_id,status") \
        .in_("ativo_origem_id", origin_ids) \
        .neq("status", "pendente").execute()

    protected = {
        (r["ativo_origem_id"], r["ativo_destino_id"])
        for r in (existing.data or [])
        if "ativo_origem_id" in r and "ativo_destino_id" in r
    }

    all_upsert_data = []
    for match in matches:
        pair = (match["ativo_origem_id"], match["ativo_destino_id"])
        if pair in protected:
            continue

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

    if not all_upsert_data:
        logger.info("No new matches to upsert (all protected)")
        return

    db.table("matches").upsert(
        all_upsert_data,
        on_conflict="ativo_origem_id,ativo_destino_id",
    ).execute()

    logger.info(f"Bulk upserted {len(all_upsert_data)} matches (skipped {len(protected)} protected)")


