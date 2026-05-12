"""Mailing AI consent features — registered at app boot.

Per `consent-guard-rollout` Phase 2 (2026-04-27). This module is imported
once by `app.main` so its `register_feature(...)` calls populate the
platform-wide consent catalog at boot.

All 7 mailing features default to `default_granted=True` per the §7.2
rubric (low/medium-risk org-internal AI). Users still see them in
`/api/me/consents` for transparency (LGPD + billing) and can toggle off.

**LGPD redaction (llm-tool-audit-rollout Phase 3, 2026-05-11).** Each
feature declares `redact_arguments` + `redact_result` callables that
scrub PII before AuditRecord values land in `mailing.tool_call_audits`.
The general policy:

  - Email + phone literals are masked (`a***@***.com`, `+55***`) so
    audit readers can still see "an email was here" without leaking it.
  - Long text bodies (template HTML, briefings) are truncated to
    `_MAX_TEXT` chars + length suffix — keeps the audit row small and
    pre-emptively avoids inadvertent leakage of mail-merge placeholders
    that may have been pre-substituted.
  - Contact-level data (M3 segmentation) is fully aggregated to counts —
    individual emails / names never enter the audit table.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from noctusai_lib.domain.ai import register_feature

# ---------------------------------------------------------------------------
# Redactor helpers (module-private, pure functions; covered by
# tests/services/test_ai_consent_redaction.py).
# ---------------------------------------------------------------------------

_MAX_TEXT = 200  # Characters preserved before truncation marker.

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Brazilian phone-like sequences (8-13 digits with optional +/(/)/-/. separators).
# Conservative: only triggers on 9+ digits to avoid masking dates / amounts.
_PHONE_RE = re.compile(r"\+?\d[\d\s().\-]{8,}\d")


def _mask_email(match: "re.Match[str]") -> str:
    local = match.group(0).split("@", 1)[0]
    first = local[0] if local else "*"
    return f"{first}***@***"


def _scrub_text(value: Any) -> Any:
    """Mask emails + phones in a string; truncate to `_MAX_TEXT` chars."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    cleaned = _EMAIL_RE.sub(_mask_email, value)
    cleaned = _PHONE_RE.sub("[phone]", cleaned)
    if len(cleaned) > _MAX_TEXT:
        return f"{cleaned[:_MAX_TEXT]}…[+{len(cleaned) - _MAX_TEXT} chars]"
    return cleaned


def _drop_body(_: Any) -> Any:
    """LLM result for body-generating features: dropped entirely. The audit
    row records WHICH feature ran for WHICH user — the body itself is
    reproducible from the prompt + seed and not worth audit storage."""
    return {"_redacted": "body"}


def _summarize_contacts_arg(value: Any) -> Any:
    """M3 segmentation: aggregate contact list to counts only.

    The raw arguments would include a list of `{id, email, nome, empresa, ...}`
    dicts — none of that can land in the audit table. We persist only
    structural counts so audit readers can confirm a segmentation request
    fired, with what shape, without seeing the contacts themselves.
    """
    if not isinstance(value, dict):
        return {"_redacted": "non-dict"}
    contacts = value.get("contacts") or []
    if not isinstance(contacts, list):
        contacts = []
    out: dict[str, Any] = {
        "contact_count": len(contacts),
    }
    for key in ("threshold", "max_segments"):
        if key in value:
            out[key] = value[key]
    if value.get("org_id"):
        # org_id is opaque to PII; hash for join-without-PII semantics.
        digest = hashlib.sha256(str(value["org_id"]).encode("utf-8")).hexdigest()[:12]
        out["org_id_hash"] = digest
    return out


def _summarize_segmentation_result(value: Any) -> Any:
    """M3 segmentation result: AIOutput rows are per-contact and include
    label/chip text that may echo company names. Aggregate to counts +
    distinct labels for audit observability."""
    if not isinstance(value, list):
        return {"_redacted": "non-list"}
    labels = sorted({str(item.get("label", "")) for item in value if isinstance(item, dict)})
    return {
        "row_count": len(value),
        "distinct_labels": labels[:20],  # bounded — clusters cap at 8 anyway.
    }


def _scrub_review_args(value: Any) -> Any:
    """M6 deliverability: keep subject + html-shape stats; strip the body
    so leaked merged-PII can't land in audit. Subject is scrubbed for
    email/phone patterns."""
    if not isinstance(value, dict):
        return _scrub_text(value)
    out: dict[str, Any] = {}
    if "subject" in value:
        out["subject"] = _scrub_text(value.get("subject"))
    if "html" in value and isinstance(value["html"], str):
        out["html_length"] = len(value["html"])
    return out


# ---------------------------------------------------------------------------
# Feature registrations
# ---------------------------------------------------------------------------

# M1 — Subject-line generation (low-risk: org-internal copy)
register_feature(
    "mailing.subject_gen",
    title="Geração de linha de assunto por IA",
    rationale=(
        "A IA lê o resumo da campanha e sugere variantes de assunto "
        "(3-5 opções com tons diferentes). Conteúdo do resumo transita "
        "pelo provedor LLM para gerar as sugestões."
    ),
    product="mailing",
    default_granted=True,
    redact_arguments=lambda v: {"campaign_summary": _scrub_text((v or {}).get("campaign_summary"))}
        if isinstance(v, dict) else _scrub_text(v),
    redact_result=lambda v: {"variant_count": len(v) if isinstance(v, list) else 0},
)

# M2 — Template draft from prompt (low-risk: org-internal copy)
register_feature(
    "mailing.template_draft",
    title="Rascunho de template de e-mail por IA",
    rationale=(
        "A IA gera um rascunho HTML responsivo a partir do briefing "
        "fornecido. O briefing transita pelo provedor LLM."
    ),
    product="mailing",
    default_granted=True,
    redact_arguments=lambda v: {"prompt": _scrub_text((v or {}).get("prompt"))}
        if isinstance(v, dict) else _scrub_text(v),
    redact_result=_drop_body,
)

# M5 — Re-engagement variants (low-risk: org-internal copy)
register_feature(
    "mailing.reengagement_variants",
    title="Variantes de re-engajamento",
    rationale=(
        "A IA gera 3 variantes de e-mail de re-engajamento (leve, direto, "
        "valor) a partir do contexto. O contexto transita pelo provedor LLM."
    ),
    product="mailing",
    default_granted=True,
    redact_arguments=lambda v: {"context": _scrub_text((v or {}).get("context"))}
        if isinstance(v, dict) else _scrub_text(v),
    redact_result=lambda v: {"variant_count": len(v) if isinstance(v, list) else 0},
)

# M6 — Deliverability review (low-risk: org-internal copy)
register_feature(
    "mailing.deliverability_review",
    title="Revisão de entregabilidade",
    rationale=(
        "A IA analisa o HTML e o assunto para sinalizar palavras de "
        "spam, problemas de formatação, ou outros riscos de entrega. "
        "Apenas o conteúdo da campanha (sem dados de contatos) entra "
        "no prompt."
    ),
    product="mailing",
    default_granted=True,
    redact_arguments=_scrub_review_args,
    redact_result=lambda v: {
        "finding_count": len((v or {}).get("findings", [])) if isinstance(v, dict) else 0,
    },
)

# M7 — Translation (low-risk: org-internal copy)
register_feature(
    "mailing.translate",
    title="Tradução de templates",
    rationale=(
        "A IA traduz o HTML do template (PT → EN/ES/FR) preservando a "
        "estrutura. O conteúdo do template transita pelo provedor LLM."
    ),
    product="mailing",
    default_granted=True,
    redact_arguments=lambda v: (
        {
            "target_lang": (v or {}).get("target_lang"),
            "html_length": len((v or {}).get("html") or ""),
        } if isinstance(v, dict) else {"_redacted": "non-dict"}
    ),
    redact_result=_drop_body,
)

# M3 — Contact segmentation (medium-risk: contact PII in embeddings)
register_feature(
    "mailing.segment_contacts",
    title="Segmentação automática de contatos",
    rationale=(
        "A IA gera embeddings e agrupa seus contatos em segmentos por "
        "similaridade (nome, empresa, tags, campos customizados). Os "
        "dados de contato entram no provedor LLM apenas para gerar "
        "embeddings — não são armazenados externamente."
    ),
    product="mailing",
    default_granted=True,
    redact_arguments=_summarize_contacts_arg,
    redact_result=_summarize_segmentation_result,
)

# M4 — Campaign debrief (low-risk: anonymous aggregates)
register_feature(
    "mailing.campaign_debrief",
    title="Resumo automático de campanha (debrief)",
    rationale=(
        "Após cada envio, a IA gera um relatório de 3 parágrafos com "
        "métricas agregadas (entregues / abertos / cliques) + comentário "
        "narrativo. Apenas estatísticas anônimas entram no prompt — "
        "nenhum e-mail individual ou conteúdo de contato."
    ),
    product="mailing",
    default_granted=True,
    redact_arguments=lambda v: {
        "campaign_id": (v or {}).get("campaign_id") if isinstance(v, dict) else None,
    },
    redact_result=_drop_body,
)
