"""
Embedding vs Rule-based matching comparison — BILATERAL (profile↔interest).
Calls OpenAI API to generate real embeddings, then compares both approaches.

Embedding matching logic:
  B→A: imovel PROFILE emb ↔ permuta INTEREST emb (does permuta want this imovel?)
  A→B: permuta PROFILE emb ↔ imovel INTEREST emb (does imovel owner want this permuta?)
  similarity = avg(sim_ba, sim_ab)

Usage: python -m tests.test_embedding_vs_rules
"""
import sys, os, asyncio, math, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Load .env — take first non-empty value for each key (handles duplicate empty entries)
with open("/Users/rapha/Documents/repository/NoctusAI/noctusai/.env") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if v and k not in os.environ:
            os.environ[k] = v

import httpx
from app.services.embedding_service import (
    build_ativo_text,
    build_interesses_text,
    OPENAI_EMBEDDINGS_URL,
    EMBEDDING_MODEL,
)
from app.services.matching import (
    gerar_matches_para_imovel,
    calcular_compatibilidade_regiao,
    calcular_compatibilidade_preco,
    calcular_compatibilidade_specs,
    calcular_alinhamento_interesses,
    _passa_filtros_minimos,
    _SIM_THRESHOLD,
)

# ── Dataset selection: use large (400+80) or small (100+30) ──
USE_LARGE = "--large" in sys.argv or "-l" in sys.argv

if USE_LARGE:
    from tests.test_mock_matching_large import I, ALL, P, PA
else:
    from tests.test_mock_matching_local import I, ALL, P, PA

SCORE_MINIMO = 45.0


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def generate_embeddings_batch(texts, api_key, batch_size=50):
    all_embeddings = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            response = await client.post(
                OPENAI_EMBEDDINGS_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": EMBEDDING_MODEL, "input": batch},
            )
            if response.status_code != 200:
                raise ValueError(f"OpenAI API error: {response.status_code} — {response.text}")
            data = response.json()
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            all_embeddings.extend([d["embedding"] for d in sorted_data])
            if i + batch_size < len(texts):
                print(f"    Embedded {i + batch_size}/{len(texts)}...")
    return all_embeddings


def print_stats(label, matches, all_permutas, possible):
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    print(f"  Total matches: {len(matches)}")
    print(f"  Possible pairs: {possible} | Match rate: {len(matches)/possible*100:.1f}%")
    if not matches:
        print("  NO MATCHES")
        return

    scores = [m["score"] for m in matches]
    print(f"  Score range: {min(scores):.1f}–{max(scores):.1f} | Avg: {sum(scores)/len(scores):.1f}")

    bk = {"90+": 0, "80-89": 0, "70-79": 0, "60-69": 0, "50-59": 0, "45-49": 0, "<45": 0}
    for s in scores:
        if s >= 90: bk["90+"] += 1
        elif s >= 80: bk["80-89"] += 1
        elif s >= 70: bk["70-79"] += 1
        elif s >= 60: bk["60-69"] += 1
        elif s >= 50: bk["50-59"] += 1
        elif s >= 45: bk["45-49"] += 1
        else: bk["<45"] += 1
    print("\n  Score Distribution:")
    for b, c in bk.items():
        bar = "█" * max(1, c // 2) if c > 0 else ""
        print(f"    {b:6s}: {c:4d}  {bar}")

    gr = {"HIGH": [], "MED": [], "LOW": [], "AUTO": []}
    for m in matches:
        ob = next((p["observacoes"] for p in all_permutas if p["id"] == m["ativo_destino_id"]), "")
        if "HIGH" in ob: gr["HIGH"].append(m)
        elif "MED" in ob: gr["MED"].append(m)
        elif "LOW" in ob: gr["LOW"].append(m)
        elif "AUTO" in ob: gr["AUTO"].append(m)
    print("\n  Matches by Group:")
    for g, ms in gr.items():
        if ms:
            gs = [m["score"] for m in ms]
            print(f"    {g:5s}: {len(ms):4d} matches | avg {sum(gs)/len(gs):5.1f} | range {min(gs):.0f}-{max(gs):.0f}")
        else:
            print(f"    {g:5s}:    0 matches")

    mp = {m["ativo_destino_id"] for m in matches}
    um = [x for x in all_permutas if x["id"] not in mp]
    print(f"\n  Unmatched Permutas: {len(um)} / {len(all_permutas)}")
    for x in um:
        print(f"    {x['observacoes']:20s}  {x['cidade']}, {x.get('bairro','—')} – R${x['valor']:,.0f}")

    matches_sorted = sorted(matches, key=lambda m: m["score"], reverse=True)
    print(f"\n  Top 10:")
    for m in matches_sorted[:10]:
        io = next((x["observacoes"] for x in I if x["id"] == m["ativo_origem_id"]), "")[:16]
        po = next((x["observacoes"] for x in all_permutas if x["id"] == m["ativo_destino_id"]), "")[:16]
        j = m.get("justificativa", "")[:40]
        sim_ba = m.get("detalhes", {}).get("embedding_sim_ba", "")
        sim_ab = m.get("detalhes", {}).get("embedding_sim_ab", "")
        extra = f"  B→A={sim_ba:.3f} A→B={sim_ab:.3f}" if sim_ba else ""
        print(f"    {m['score']:5.1f}  {io:16s}  {po:16s}  {j}{extra}")


def run_bilateral_embedding_matching(imoveis, permutas, threshold=_SIM_THRESHOLD):
    """
    Local bilateral embedding matching: profile↔interest (NOT profile↔profile).

    For each imovel-permuta pair:
      B→A: cosine(imovel.profile_emb, permuta.interest_emb) — does permuta want this imovel?
      A→B: cosine(permuta.profile_emb, imovel.interest_emb) — does imovel owner want this permuta?
      similarity = avg(sim_ba, sim_ab)
    """
    matches = []

    for imovel in imoveis:
        imovel_profile = imovel.get("embedding")
        imovel_interest = imovel.get("embedding_interesses")
        if not imovel_profile:
            continue

        for permuta in permutas:
            permuta_profile = permuta.get("embedding")
            permuta_interest = permuta.get("embedding_interesses")

            if permuta.get("owner_id") == imovel.get("owner_id"):
                continue
            if permuta.get("status", "ativo") != "ativo":
                continue

            # B→A: does this permuta WANT this imovel?
            # Compare imovel profile against permuta's interest embedding
            if not permuta_interest:
                continue
            sim_ba = cosine_similarity(imovel_profile, permuta_interest)

            # A→B: does this imovel owner WANT what the permuta offers?
            # Compare permuta profile against imovel's interest embedding
            if not imovel_interest or not permuta_profile:
                continue
            sim_ab = cosine_similarity(permuta_profile, imovel_interest)

            # Both directions must clear the threshold
            if sim_ba < threshold or sim_ab < threshold:
                continue

            similarity = (sim_ba + sim_ab) / 2.0

            # Structured sub-scores
            regiao = calcular_compatibilidade_regiao(imovel, permuta)
            preco = calcular_compatibilidade_preco(imovel, permuta)
            specs = calcular_compatibilidade_specs(imovel, permuta)

            if not _passa_filtros_minimos(imovel, permuta, regiao, preco, specs):
                continue

            interesses = calcular_alinhamento_interesses(imovel, permuta)
            # Composite: 40% semantic + 25% price + 20% specs + 15% interests
            score = round(min(
                0.40 * (similarity * 100)
                + 0.25 * (preco / 25) * 100
                + 0.20 * (specs / 20) * 100
                + 0.15 * (interesses / 15) * 100,
                100.0,
            ), 1)

            if score < SCORE_MINIMO:
                continue

            justificativa_parts = []
            if similarity >= 0.7:
                justificativa_parts.append("Alta compatibilidade bilateral")
            elif similarity >= 0.5:
                justificativa_parts.append("Boa compatibilidade bilateral")
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
                    "compatibilidade_regiao": regiao,
                    "compatibilidade_preco": preco,
                    "compatibilidade_specs": specs,
                    "alinhamento_interesses": interesses,
                    "embedding_similarity": round(similarity, 4),
                    "embedding_sim_ba": round(sim_ba, 4),
                    "embedding_sim_ab": round(sim_ab, 4),
                },
                "score_breakdown": {
                    "embedding_similarity": round(similarity * 100, 1),
                    "compatibilidade_regiao": round((regiao / 30) * 100, 1),
                    "compatibilidade_preco": round((preco / 25) * 100, 1),
                    "compatibilidade_specs": round((specs / 20) * 100, 1),
                    "qualidade_anuncio": 0,
                    "interesses": round((interesses / 15) * 100, 1),
                },
            })

    matches.sort(key=lambda m: m["score"], reverse=True)
    return matches


async def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found in environment")
        sys.exit(1)

    print("=" * 80)
    print("BILATERAL EMBEDDING (profile↔interest) vs RULE-BASED COMPARISON")
    print(f"Imóveis: {len(I)} | Permutas: {len(ALL)} (imovel: {len(P)}, auto: {len(PA)})")
    print("=" * 80)

    # ── Step 1: Build texts ──
    all_ativos = I + ALL

    print("\n[1/4] Building profile + interest texts...")
    profile_texts = [build_ativo_text(a) for a in all_ativos]
    interest_texts = [build_interesses_text(a) for a in all_ativos]

    has_interest = sum(1 for t in interest_texts if t)
    print(f"  Ativos with profile text: {sum(1 for t in profile_texts if t)}/{len(all_ativos)}")
    print(f"  Ativos with interest text: {has_interest}/{len(all_ativos)}")

    # Show samples
    print(f"\n  Imovel PROFILE: {profile_texts[0][:100]}...")
    print(f"  Imovel INTEREST: {interest_texts[0][:100]}...")
    print(f"  Permuta PROFILE: {profile_texts[len(I)][:100]}...")
    print(f"  Permuta INTEREST: {interest_texts[len(I)][:100]}...")

    # ── Step 2: Generate embeddings ──
    print(f"\n[2/4] Generating embeddings via OpenAI API...")

    # Profile embeddings
    print("  Profile embeddings:")
    t0 = time.time()
    profile_embeddings = await generate_embeddings_batch(profile_texts, api_key)
    t1 = time.time()
    print(f"    {len(profile_embeddings)} embeddings in {t1 - t0:.1f}s")

    # Interest embeddings (only for ativos that have interests)
    print("  Interest embeddings:")
    # Build list of non-empty texts with indices
    interest_pairs = [(i, t) for i, t in enumerate(interest_texts) if t]
    interest_only_texts = [t for _, t in interest_pairs]
    interest_embeddings_raw = await generate_embeddings_batch(interest_only_texts, api_key)
    t2 = time.time()
    print(f"    {len(interest_embeddings_raw)} embeddings in {t2 - t1:.1f}s")

    # Map back to full list
    interest_embeddings = [None] * len(all_ativos)
    for j, (orig_idx, _) in enumerate(interest_pairs):
        interest_embeddings[orig_idx] = interest_embeddings_raw[j]

    # Attach to ativos
    for i, ativo in enumerate(all_ativos):
        ativo["embedding"] = profile_embeddings[i]
        ativo["embedding_interesses"] = interest_embeddings[i]

    print(f"\n  Total API time: {t2 - t0:.1f}s | Dimensions: {len(profile_embeddings[0])}")

    # ── Step 3: Similarity sanity check (profile↔interest) ──
    print("\n[3/4] Bilateral similarity sanity check (profile↔interest)...")

    im0 = I[0]   # SP-ZS-01 Moema apt
    pm0 = P[0]   # PERM-HIGH-01 Moema, wants apt in SP
    pm_low = P[20]  # PERM-LOW-01 Rio
    au0 = PA[0]  # PERM-AUTO-01 BMW

    # B→A: imovel profile vs permuta interest (does permuta want this imovel?)
    sim_ba_good = cosine_similarity(im0["embedding"], pm0["embedding_interesses"])
    sim_ba_bad = cosine_similarity(im0["embedding"], pm_low["embedding_interesses"])
    sim_ba_auto = cosine_similarity(im0["embedding"], au0["embedding_interesses"])

    # A→B: permuta profile vs imovel interest (does imovel owner want this permuta?)
    sim_ab_good = cosine_similarity(pm0["embedding"], im0["embedding_interesses"])
    sim_ab_bad = cosine_similarity(pm_low["embedding"], im0["embedding_interesses"])
    sim_ab_auto = cosine_similarity(au0["embedding"], im0["embedding_interesses"])

    print(f"  SP-ZS-01 (Moema) ↔ PERM-HIGH-01 (Moema, wants SP apt):")
    print(f"    B→A (permuta wants imovel?):    {sim_ba_good:.4f}")
    print(f"    A→B (imovel wants permuta?):    {sim_ab_good:.4f}")
    print(f"    Avg bilateral:                  {(sim_ba_good + sim_ab_good) / 2:.4f}")
    print(f"  SP-ZS-01 (Moema) ↔ PERM-LOW-01 (Rio, wants Rio apt):")
    print(f"    B→A (permuta wants imovel?):    {sim_ba_bad:.4f}")
    print(f"    A→B (imovel wants permuta?):    {sim_ab_bad:.4f}")
    print(f"    Avg bilateral:                  {(sim_ba_bad + sim_ab_bad) / 2:.4f}")
    print(f"  SP-ZS-01 (Moema) ↔ PERM-AUTO-01 (BMW, wants SP apt):")
    print(f"    B→A (permuta wants imovel?):    {sim_ba_auto:.4f}")
    print(f"    A→B (imovel wants permuta?):    {sim_ab_auto:.4f}")
    print(f"    Avg bilateral:                  {(sim_ba_auto + sim_ab_auto) / 2:.4f}")

    # ── Step 4: Run matching with multiple thresholds ──
    thresholds = [0.60, 0.65, 0.75, 0.80, 0.85]
    possible = len(I) * len(ALL)

    # Rule-based (no embeddings — strip them temporarily)
    saved_embeddings = {}
    for a in I + ALL:
        saved_embeddings[a["id"]] = (a.pop("embedding", None), a.pop("embedding_interesses", None))

    rule_matches = []
    for im in I:
        rule_matches.extend(gerar_matches_para_imovel(im, ALL))

    # Restore embeddings
    for a in I + ALL:
        emb, emb_int = saved_embeddings[a["id"]]
        if emb is not None:
            a["embedding"] = emb
        if emb_int is not None:
            a["embedding_interesses"] = emb_int

    print(f"\n[4/4] Running matching across {len(thresholds)} thresholds...")
    print_stats("RULE-BASED (bilateral filters + scoring)", rule_matches, ALL, possible)

    rule_pairs = {(m["ativo_origem_id"], m["ativo_destino_id"]) for m in rule_matches}
    rule_map = {(m["ativo_origem_id"], m["ativo_destino_id"]): m for m in rule_matches}

    # ── Summary table header ──
    print(f"\n{'=' * 80}")
    print("  THRESHOLD COMPARISON SUMMARY")
    print(f"{'=' * 80}")
    print(f"  {'Threshold':>10s}  {'Matches':>8s}  {'Rate':>6s}  {'Avg':>6s}  {'Min':>6s}  {'Max':>6s}  {'HIGH':>5s}  {'MED':>5s}  {'LOW':>5s}  {'AUTO':>5s}  {'Shared':>7s}  {'Emb-only':>8s}")
    print(f"  {'-'*10}  {'-'*8}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*7}  {'-'*8}")

    for threshold in thresholds:
        emb_matches = run_bilateral_embedding_matching(I, ALL, threshold=threshold)

        emb_pairs = {(m["ativo_origem_id"], m["ativo_destino_id"]) for m in emb_matches}
        both = rule_pairs & emb_pairs
        emb_only = emb_pairs - rule_pairs

        scores = [m["score"] for m in emb_matches] if emb_matches else [0]
        avg_s = sum(scores) / len(scores)
        min_s = min(scores)
        max_s = max(scores)

        # Group counts
        gr = {"HIGH": 0, "MED": 0, "LOW": 0, "AUTO": 0}
        for m in emb_matches:
            ob = next((p["observacoes"] for p in ALL if p["id"] == m["ativo_destino_id"]), "")
            if "HIGH" in ob: gr["HIGH"] += 1
            elif "MED" in ob: gr["MED"] += 1
            elif "LOW" in ob: gr["LOW"] += 1
            elif "AUTO" in ob: gr["AUTO"] += 1

        rate = len(emb_matches) / possible * 100 if possible else 0
        print(f"  {threshold:>10.2f}  {len(emb_matches):>8d}  {rate:>5.1f}%  {avg_s:>6.1f}  {min_s:>6.1f}  {max_s:>6.1f}  {gr['HIGH']:>5d}  {gr['MED']:>5d}  {gr['LOW']:>5d}  {gr['AUTO']:>5d}  {len(both):>7d}  {len(emb_only):>8d}")

    # ── Baseline row ──
    r_scores = [m["score"] for m in rule_matches]
    r_gr = {"HIGH": 0, "MED": 0, "LOW": 0, "AUTO": 0}
    for m in rule_matches:
        ob = next((p["observacoes"] for p in ALL if p["id"] == m["ativo_destino_id"]), "")
        if "HIGH" in ob: r_gr["HIGH"] += 1
        elif "MED" in ob: r_gr["MED"] += 1
        elif "LOW" in ob: r_gr["LOW"] += 1
        elif "AUTO" in ob: r_gr["AUTO"] += 1
    r_rate = len(rule_matches) / possible * 100
    print(f"  {'-'*10}  {'-'*8}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*7}  {'-'*8}")
    print(f"  {'RULE-BASED':>10s}  {len(rule_matches):>8d}  {r_rate:>5.1f}%  {sum(r_scores)/len(r_scores):>6.1f}  {min(r_scores):>6.1f}  {max(r_scores):>6.1f}  {r_gr['HIGH']:>5d}  {r_gr['MED']:>5d}  {r_gr['LOW']:>5d}  {r_gr['AUTO']:>5d}  {'—':>7s}  {'—':>8s}")

    # ── Detailed per-threshold stats ──
    for threshold in thresholds:
        emb_matches = run_bilateral_embedding_matching(I, ALL, threshold=threshold)
        if not emb_matches:
            continue
        print(f"\n{'─' * 60}")
        print(f"  THRESHOLD {threshold} — Top 10")
        print(f"{'─' * 60}")
        emb_sorted = sorted(emb_matches, key=lambda m: m["score"], reverse=True)
        for m in emb_sorted[:10]:
            io = next((x["observacoes"] for x in I if x["id"] == m["ativo_origem_id"]), "")[:16]
            po = next((x["observacoes"] for x in ALL if x["id"] == m["ativo_destino_id"]), "")[:16]
            d = m["detalhes"]
            print(f"    {m['score']:5.1f}  {io:16s}  {po:16s}  B→A={d['embedding_sim_ba']:.3f} A→B={d['embedding_sim_ab']:.3f}")

        # Unmatched permutas
        mp = {m["ativo_destino_id"] for m in emb_matches}
        um = [x for x in ALL if x["id"] not in mp]
        print(f"  Unmatched: {len(um)}/{len(ALL)} permutas")

    print(f"\n{'=' * 80}")
    print("DONE")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    asyncio.run(main())
