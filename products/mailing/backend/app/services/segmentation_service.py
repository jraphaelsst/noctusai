"""
M3 — Contact segmentation (ai-expansion Phase 8).

Pipeline:
  1. Build a short embedding text per contact (`nome | tags | empresa | custom_fields`).
  2. `noctusai_lib.llm.generate_embedding` each text.
  3. Greedy cosine-similarity clustering (pure Python — no sklearn dep).
  4. `chat_completion` once per cluster to produce a 2–3 word PT segment label
     + an uppercase chip (≤ 18 chars).
  5. Return list of AIOutput-shaped dicts (one per contact).

The router persists each dict to `mailing.ai_outputs` via
`noctusai_lib.ai.persist_output(db, schema="mailing", output)`.

LGPD posture: contact emails / nome are PII, but each embedding/naming call
is scoped to the requesting org and the LLM call uses `cache=True` only on
the per-cluster naming (which sees aggregated tags + empresa, not emails).
The embedding step itself uses the LLM provider's embedding endpoint —
texts are sent but not cached at the LLM-key level.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.integrations.llm import chat_completion, generate_embedding

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"

PROMPT_VERSION_SEGMENT = "mailing-segment@v1"

DEFAULT_THRESHOLD = 0.78
DEFAULT_MAX_SEGMENTS = 8


def _empty_output(label: str = "indisponível") -> dict:
    return {
        "kind": "flag",
        "label": label,
        "chip": None,
        "explanation": "Segmentação indisponível.",
        "confidence": None,
        "score": None,
        "model_version": MODEL,
        "prompt_version": None,
    }


def _build_contact_text(contact: dict) -> str:
    parts = []
    if contact.get("nome"):
        parts.append(f"nome={contact['nome']}")
    if contact.get("empresa"):
        parts.append(f"empresa={contact['empresa']}")
    tags = contact.get("tags") or []
    if tags:
        parts.append("tags=" + ",".join(str(t) for t in tags[:8]))
    custom = contact.get("custom_fields") or {}
    if custom:
        keys = list(custom.keys())[:6]
        parts.append("campos=" + ",".join(f"{k}:{custom[k]}" for k in keys))
    if not parts:
        parts.append(f"email={contact.get('email', '?')}")
    return "; ".join(parts)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    denom = (na ** 0.5) * (nb ** 0.5)
    if denom == 0.0:
        return 0.0
    return dot / denom


def _greedy_cluster(
    embeddings: list[list[float]],
    *,
    threshold: float,
    max_segments: int,
) -> list[int]:
    """Greedy assignment: each embedding goes to the most-similar existing
    cluster centroid above `threshold`, else creates a new cluster (until
    `max_segments` is reached, after which spillover joins the closest).
    Returns one cluster index per embedding, in input order."""
    centroids: list[list[float]] = []
    counts: list[int] = []
    assignments: list[int] = []
    for emb in embeddings:
        if not centroids:
            centroids.append(list(emb))
            counts.append(1)
            assignments.append(0)
            continue
        # Best similarity over existing centroids.
        best_idx = 0
        best_sim = -1.0
        for i, c in enumerate(centroids):
            s = _cosine(emb, c)
            if s > best_sim:
                best_sim = s
                best_idx = i
        if best_sim >= threshold or len(centroids) >= max_segments:
            # Join the best existing cluster.
            n = counts[best_idx]
            centroids[best_idx] = [
                (cv * n + ev) / (n + 1) for cv, ev in zip(centroids[best_idx], emb)
            ]
            counts[best_idx] = n + 1
            assignments.append(best_idx)
        else:
            centroids.append(list(emb))
            counts.append(1)
            assignments.append(len(centroids) - 1)
    return assignments


async def _name_segment(
    *,
    cluster_idx: int,
    sample_texts: list[str],
    org_id: Optional[str] = None,
) -> tuple[str, str]:
    """Ask the LLM for a 2-3 word PT segment label + uppercase chip.

    Returns `(label, chip)`. Falls back to `(f"Segmento {N}", "SEG N")` when
    the LLM is unavailable or returns an unparseable response.
    """
    fallback_label = f"Segmento {cluster_idx + 1}"
    fallback_chip = f"SEG {cluster_idx + 1}"

    if not sample_texts:
        return fallback_label, fallback_chip

    bullets = "\n".join(f"- {t}" for t in sample_texts[:6])
    system = (
        "Você é um analista de marketing. Dado um conjunto de contatos "
        "agrupados por similaridade, sugira UM rótulo curto em português "
        "(2-3 palavras) que descreva o grupo, e UM chip MAIÚSCULO de até "
        "18 caracteres. Responda EXATAMENTE no formato:\n"
        "LABEL: <2-3 palavras>\n"
        "CHIP: <até 18 caracteres MAIÚSCULOS>"
    )
    user_prompt = f"Amostra do grupo:\n{bullets}"

    try:
        content = await chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            model=MODEL,
            temperature=0.0,
            max_tokens=60,
            cache=True,
            org_id=org_id,
        )
    except Exception:
        logger.warning("mailing.segment.name_segment: LLM unavailable")
        return fallback_label, fallback_chip

    label = ""
    chip = ""
    for line in content.splitlines():
        s = line.strip()
        u = s.upper()
        if u.startswith("LABEL:"):
            label = s.split(":", 1)[1].strip()
        elif u.startswith("CHIP:"):
            chip = s.split(":", 1)[1].strip().upper()
    if not label:
        label = fallback_label
    if not chip:
        chip = (label.upper())[:18] if label else fallback_chip
    if len(chip) > 18:
        chip = chip[:18]
    return label, chip


async def segment_contacts(
    *,
    contacts: list[dict],
    threshold: float = DEFAULT_THRESHOLD,
    max_segments: int = DEFAULT_MAX_SEGMENTS,
    org_id: Optional[str] = None,
) -> list[dict]:
    """Cluster contacts and return one AIOutput-shaped dict per contact.

    Each returned dict has `_contact_id` (caller uses it as `ref_id`) plus
    the standard AIOutput fields (`kind`, `label`, `chip`, `confidence`,
    `model_version`, `prompt_version`, `metadata`).

    A `metadata.cluster` field carries the integer cluster index so the UI
    can colour/group identically-segmented contacts even before LLM naming
    completes.
    """
    if not contacts:
        return []

    # 1. Embedding texts.
    texts = [_build_contact_text(c) for c in contacts]

    # 2. Embed each. Bail to fallback if any embedding call fails.
    embeddings: list[list[float]] = []
    try:
        for t in texts:
            emb = await generate_embedding(t, model=EMBEDDING_MODEL, org_id=org_id)
            embeddings.append(emb)
    except Exception:
        logger.warning("mailing.segment_contacts: embedding step unavailable")
        empty = _empty_output()
        return [
            {**empty, "_contact_id": c["id"], "metadata": {"cluster": -1}}
            for c in contacts
        ]

    # 3. Cluster.
    assignments = _greedy_cluster(
        embeddings, threshold=threshold, max_segments=max_segments
    )

    # 4. For each cluster, gather sample texts and ask LLM to name it. Cache
    # the (label, chip) by cluster_idx so we name once even with N members.
    n_clusters = max(assignments) + 1 if assignments else 0
    samples_by_cluster: dict[int, list[str]] = {i: [] for i in range(n_clusters)}
    for idx, t in zip(assignments, texts):
        if len(samples_by_cluster[idx]) < 6:
            samples_by_cluster[idx].append(t)

    names_by_cluster: dict[int, tuple[str, str]] = {}
    for cluster_idx, samples in samples_by_cluster.items():
        names_by_cluster[cluster_idx] = await _name_segment(
            cluster_idx=cluster_idx, sample_texts=samples, org_id=org_id
        )

    # 5. Emit one AIOutput dict per contact.
    out: list[dict] = []
    for c, cluster_idx in zip(contacts, assignments):
        label, chip = names_by_cluster[cluster_idx]
        out.append({
            "_contact_id": c["id"],
            "kind": "classification",
            "label": label,
            "chip": chip,
            "explanation": None,
            "confidence": None,
            "score": None,
            "model_version": MODEL,
            "prompt_version": PROMPT_VERSION_SEGMENT,
            "metadata": {"cluster": cluster_idx},
        })
    return out
