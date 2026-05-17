"""Tool-call audit-writer factory + LGPD redaction for therapy-platform.

Per `KB § PATTERNS/llm-tool-audit.md`: each LLM dispatch site builds an
`AuditRecord` after the call returns and hands it to `audit_writer(record)`,
which persists one row to `therapy.tool_call_audits` via SQLAlchemy.

**LGPD HIGH-risk product.** Therapy holds Art. 11 sensitive data (patient
session transcripts, audio bytes, images, observations). Per `projects/
llm-tool-audit-rollout/PROJECT.md` §11 finding 2 and the brief, every
dispatch site MUST scrub `arguments` + `result` BEFORE constructing the
`AuditRecord`. This module ships the per-feature redaction lambdas and
the helper `redact_for_feature(...)` consumers call before audit.

**Best-effort.** The seed `make_audit_writer` rolls back + logs on DB
error; tool dispatch is never broken by an audit-side failure. See
`noctusai_lib.domain.ai.tool_audit.make_audit_writer` for the guarantee.

**Lazy SQLAlchemy session.** Therapy's primary data path is the Supabase
admin client. SQLAlchemy is only needed for the `make_audit_writer`
typed-table-class shape. The engine is constructed lazily — first call
to `get_audit_writer()` — so:

  - App boot doesn't require a Postgres connection string.
  - Settings without `postgres_url` get a noop writer (debug log + skip).
  - Tests can override `postgres_url` to point at a fixture DB.

Mirrors the original canonical reference adopter's shape (retired
`media-scheduling`, consolidated into `social-wiring` 2026-05-16;
llm-tool-audit-rollout Phase 1).

**Q2 seed deferred — redaction lambdas live in this module, not in
`register_feature`.** PROJECT.md §7 Q2 (require explicit `redact_*` args
in seed `register_feature`) is a Phase 1 seed-side lift owned by the
architect — modifying it from a per-product rollout brief would collide
with the parallel ERP/mailing engineers. Per-product wiring instead.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Mapping, Optional

from app.config import settings
from app.models.tool_call_audit import ToolCallAudit
from noctusai_lib.domain.ai.tool_audit import (
    AuditRecord,
    AuditWriter,
    make_audit_writer,
    now_utc,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LGPD redaction — per-feature scrubbers
# ---------------------------------------------------------------------------
#
# Therapy holds Art. 11 sensitive data. The seed `_safe_jsonable` fallback
# is defensive coercion, NOT a redaction strategy. Each dispatch site MUST
# scrub `arguments` + `result` BEFORE constructing `AuditRecord`.
#
# Two registered features (per `app/services/ai_consent_features.py`):
#   - therapy.longitudinal_narrative — clinical+patient longitudinal analyses
#   - therapy.session_summary         — per-session base+clinical summaries
#
# Two additional dispatch types not gated by `register_feature` (no UI
# consent surface yet) but still inside the audit's LGPD posture:
#   - therapy.attachment_analyze_image — vision over patient-uploaded images
#   - therapy.attachment_transcribe_audio — Whisper over patient-uploaded audio
#   - therapy.session_transcribe_audio — Whisper over recorded session audio
#
# Redaction strategy: NEVER store raw clinical text / audio bytes / image
# bytes / observation content / session transcripts. Audit rows record
# only fixed structural metadata (sizes, presence flags, model names,
# token counts, clinic_id). Patient-identifying free text is dropped.

_REDACTED = "[REDACTED]"
_REDACTED_LEN_KEY = "redacted_length"
_REDACTED_PREFIX_LEN = 0  # 0 = no prefix retained; can flip to 8 for debug forensics


def _scrub_string(value: Any) -> dict[str, Any]:
    """Replace a string with a length-only summary. Returns a dict the
    audit row can store; never the original characters."""
    if value is None:
        return {"present": False, _REDACTED_LEN_KEY: 0}
    if not isinstance(value, str):
        # Defensive — caller hit the wrong key. Don't leak the value.
        return {"present": True, _REDACTED_LEN_KEY: -1, "kind": type(value).__name__}
    return {"present": True, _REDACTED_LEN_KEY: len(value)}


def _scrub_bytes(value: Any) -> dict[str, Any]:
    """Replace raw bytes with a length-only summary."""
    if value is None:
        return {"present": False, "byte_length": 0}
    try:
        return {"present": True, "byte_length": len(value)}
    except TypeError:
        return {"present": True, "byte_length": -1, "kind": type(value).__name__}


def _scrub_messages(messages: Any) -> list[dict[str, Any]]:
    """Replace a list of `{role, content}` chat messages with role-only
    summaries. The `content` (which holds patient clinical text — transcripts,
    observations, longitudinal aggregations) is replaced with a length flag."""
    if not isinstance(messages, list):
        return [{"_redacted": True, "kind": type(messages).__name__}]
    out: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            out.append({"_redacted": True, "kind": type(msg).__name__})
            continue
        out.append({
            "role": msg.get("role"),
            "content": _scrub_string(msg.get("content")),
        })
    return out


def _redact_session_summary_arguments(args: Mapping[str, Any] | None) -> dict[str, Any]:
    """Scrub args for `therapy.session_summary` dispatches.

    Expected shape (built by `summary_service._call_llm`):
        {"messages": [...], "model": "gpt-4o", "temperature": ..., ...}

    `messages[].content` carries the session transcript (Art. 11) + therapist
    observations. Drop the body, keep structural metadata.
    """
    if not isinstance(args, Mapping):
        return {"_redacted": True}
    return {
        "messages": _scrub_messages(args.get("messages")),
        "model": args.get("model"),
        "temperature": args.get("temperature"),
        "max_tokens": args.get("max_tokens"),
        "response_format": args.get("response_format"),
        "cache": args.get("cache"),
        "org_id_present": args.get("org_id") is not None,
    }


def _redact_session_summary_result(result: Any) -> dict[str, Any]:
    """Scrub the LLM response for `therapy.session_summary`.

    Response shape: a JSON string holding `{summary, key_points, tags}`.
    The `summary` field is patient/therapist clinical text — drop it. Keep
    only structural metadata.
    """
    if result is None:
        return {"present": False}
    if isinstance(result, str):
        return {"present": True, "response_length": len(result), "kind": "raw_json_string"}
    if isinstance(result, Mapping):
        return {
            "present": True,
            "summary": _scrub_string(result.get("summary")),
            "key_points_count": len(result.get("key_points") or []),
            "tags_count": len(result.get("tags") or []),
        }
    return {"present": True, "kind": type(result).__name__}


def _redact_longitudinal_arguments(args: Mapping[str, Any] | None) -> dict[str, Any]:
    """Scrub args for `therapy.longitudinal_narrative`.

    Aggregates multiple session summaries + observations — even more
    sensitive than session_summary. Same structural shape, same scrubbing.
    """
    return _redact_session_summary_arguments(args)


def _redact_longitudinal_result(result: Any) -> dict[str, Any]:
    """Scrub the LLM response for `therapy.longitudinal_narrative`.

    Response shape: `{narrative_summary, recurring_themes, progress_*,
    unresolved_topics, observation_insights}` — every field is clinical
    free text. Drop bodies, keep counts.
    """
    if result is None:
        return {"present": False}
    if isinstance(result, str):
        return {"present": True, "response_length": len(result), "kind": "raw_json_string"}
    if isinstance(result, Mapping):
        return {
            "present": True,
            "narrative_summary": _scrub_string(result.get("narrative_summary")),
            "recurring_themes_count": len(result.get("recurring_themes") or []),
            "progress_timeline_count": len(result.get("progress_timeline") or []),
            "unresolved_topics_count": len(result.get("unresolved_topics") or []),
            "observation_insights_count": len(result.get("observation_insights") or []),
            "ongoing_topics_count": len(result.get("ongoing_topics") or []),
        }
    return {"present": True, "kind": type(result).__name__}


def _redact_image_arguments(args: Mapping[str, Any] | None) -> dict[str, Any]:
    """Scrub args for `therapy.attachment_analyze_image`.

    Patient-uploaded images may show clinical documents, scars, medication
    labels, etc. — Art. 11 by content. Drop the bytes + prompt body.
    """
    if not isinstance(args, Mapping):
        return {"_redacted": True}
    return {
        "image_bytes": _scrub_bytes(args.get("image")),
        "prompt": _scrub_string(args.get("prompt")),
        "model": args.get("model"),
        "max_tokens": args.get("max_tokens"),
        "org_id_present": args.get("org_id") is not None,
    }


def _redact_image_result(result: Any) -> dict[str, Any]:
    """The vision response describes the image — clinical content. Drop body."""
    if result is None:
        return {"present": False}
    if isinstance(result, str):
        return {"present": True, "response_length": len(result)}
    return {"present": True, "kind": type(result).__name__}


def _redact_audio_arguments(args: Mapping[str, Any] | None) -> dict[str, Any]:
    """Scrub args for any Whisper transcription dispatch.

    Raw audio is the highest-sensitivity Art. 11 surface in therapy. Drop
    the bytes; keep only structural metadata.
    """
    if not isinstance(args, Mapping):
        return {"_redacted": True}
    return {
        "audio_bytes": _scrub_bytes(args.get("audio") or args.get("audio_bytes")),
        "model": args.get("model"),
        "filename": args.get("filename"),
        "language": args.get("language"),
        "response_format": args.get("response_format"),
        "org_id_present": args.get("org_id") is not None,
    }


def _redact_audio_result(result: Any) -> dict[str, Any]:
    """The transcript is the most sensitive field in therapy. Length only."""
    if result is None:
        return {"present": False}
    if isinstance(result, str):
        return {"present": True, "transcript_length": len(result)}
    return {"present": True, "kind": type(result).__name__}


# Public registry — dispatch sites look up redactors by feature_key.
RedactArguments = Callable[[Mapping[str, Any] | None], dict[str, Any]]
RedactResult = Callable[[Any], dict[str, Any]]

# Per-feature redactors. Two `register_feature` calls today
# (therapy.longitudinal_narrative + therapy.session_summary) — explicit
# entries below — plus three operational dispatch keys for the
# vision/audio attachment + transcription sites not gated by a consent
# feature (no UI consent surface; they're operational-tier).
REDACTION_BY_FEATURE: dict[str, tuple[RedactArguments, RedactResult]] = {
    "therapy.session_summary": (
        _redact_session_summary_arguments,
        _redact_session_summary_result,
    ),
    "therapy.longitudinal_narrative": (
        _redact_longitudinal_arguments,
        _redact_longitudinal_result,
    ),
    "therapy.attachment_analyze_image": (
        _redact_image_arguments,
        _redact_image_result,
    ),
    "therapy.attachment_transcribe_audio": (
        _redact_audio_arguments,
        _redact_audio_result,
    ),
    "therapy.session_transcribe_audio": (
        _redact_audio_arguments,
        _redact_audio_result,
    ),
}


def redact_for_feature(
    feature_key: str,
    arguments: Mapping[str, Any] | None,
    result: Any,
) -> tuple[dict[str, Any], Any]:
    """Apply per-feature redaction. Unknown feature_key → fail-closed redaction
    (drop both arguments + result entirely). Never leak raw payloads."""
    pair = REDACTION_BY_FEATURE.get(feature_key)
    if pair is None:
        logger.warning(
            "audit_hook: no redactor registered for feature_key=%s; "
            "fail-closed scrubbing applied (arguments + result dropped)",
            feature_key,
        )
        return ({"_redacted": True, "feature_key_unknown": feature_key}, {"_redacted": True})
    redact_args, redact_result = pair
    return (redact_args(arguments), redact_result(result))


# ---------------------------------------------------------------------------
# Writer wiring — lazy SQLAlchemy session + best-effort guarantee
# ---------------------------------------------------------------------------

_engine: Optional["Engine"] = None
_session_factory = None


def _get_engine_and_factory():
    """Lazily construct the SQLAlchemy engine + sessionmaker.

    Returns (engine, session_factory) on success; (None, None) when
    `settings.postgres_url` is empty or the engine cannot be created.
    """
    global _engine, _session_factory
    if _engine is not None and _session_factory is not None:
        return _engine, _session_factory
    if not getattr(settings, "postgres_url", ""):
        return None, None
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        _engine = create_engine(
            settings.postgres_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=2,
        )
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
        return _engine, _session_factory
    except Exception:
        logger.exception(
            "audit_hook: failed to construct SQLAlchemy engine; "
            "tool-call audit will skip writes"
        )
        return None, None


def _noop_writer(record: AuditRecord) -> None:
    """Used when no Postgres connection is configured. Best-effort means
    audit gaps are visible — log at debug so dev runs don't spam."""
    logger.debug(
        "audit_hook: postgres_url unset; skipping tool_call_audit write for tool=%s",
        record.tool_name,
    )


def get_audit_writer() -> AuditWriter:
    """Return an `AuditWriter` bound to a fresh SQLAlchemy session.

    Wraps `noctusai_lib.domain.ai.tool_audit.make_audit_writer(db, ToolCallAudit)`
    — seed pattern, no hand-rolled SQL. Each call opens a short-lived
    session, writes the row, commits, closes.

    When `postgres_url` is unset, returns a noop writer that debug-logs
    each call so audit-trail gaps remain observable.
    """
    _engine_, session_factory = _get_engine_and_factory()
    if session_factory is None:
        return _noop_writer

    def write(record: AuditRecord) -> None:
        # Per-call session: seed `make_audit_writer` does the
        # try/commit/rollback/log dance internally; we just ensure the
        # session is closed.
        session = session_factory()
        try:
            inner = make_audit_writer(session, ToolCallAudit)
            inner(record)
        finally:
            session.close()

    return write


def audit_dispatch(
    *,
    feature_key: str,
    tool_name: str,
    status: str,
    duration_ms: int,
    arguments: Mapping[str, Any] | None,
    result: Any,
    error: str | None = None,
    user_id: int | None = None,
    correlation_id: str | None = None,
    conversation_id: str | None = None,
) -> None:
    """One-shot dispatch-site helper: redact via the feature's lambdas, then
    write a `tool_call_audits` row. Best-effort — never raises.

    Call this from any LLM dispatch site after the upstream call returns
    (or in the exception handler). Example:

        from app.services.audit_hook import audit_dispatch
        # ... after chat_completion / analyze_image / transcribe_audio
        audit_dispatch(
            feature_key="therapy.session_summary",
            tool_name="chat_completion",
            status="success",
            duration_ms=elapsed_ms,
            arguments={"messages": messages, "model": "gpt-4o", ...},
            result=content,
            user_id=therapist_id_int,
        )
    """
    try:
        redacted_args, redacted_result = redact_for_feature(
            feature_key, arguments, result
        )
        record = AuditRecord(
            tool_name=tool_name,
            status=status,  # type: ignore[arg-type]
            duration_ms=duration_ms,
            started_at=now_utc(),
            arguments=redacted_args,
            result=redacted_result,
            error=error,
            user_id=user_id,
            correlation_id=correlation_id,
            conversation_id=conversation_id,
        )
        writer = get_audit_writer()
        writer(record)
    except Exception:
        # Best-effort guarantee: an audit-side failure NEVER reaches the
        # caller. The seed make_audit_writer already swallows DB errors;
        # this catch covers the redactor / record-construction path.
        logger.exception(
            "audit_hook.audit_dispatch failed for feature=%s tool=%s — "
            "audit row not written, user-facing dispatch unaffected",
            feature_key,
            tool_name,
        )


__all__ = [
    "REDACTION_BY_FEATURE",
    "audit_dispatch",
    "get_audit_writer",
    "redact_for_feature",
]
