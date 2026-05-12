"""LGPD redaction unit tests for therapy audit hook.

These tests pin the redactor lambdas in `app.services.audit_hook.REDACTION_BY_FEATURE`
— each MUST scrub raw clinical content (Art. 11 sensitive data) from
`arguments` and `result` before they land in `tool_call_audits`.

Therapy is the highest-LGPD-risk product (patient session transcripts,
audio bytes, images, observations). A regression that drops clinical text
into an audit row is a compliance incident.

Also pins the bijection between `register_feature` calls in
`app.services.ai_consent_features` and entries in `REDACTION_BY_FEATURE` —
adding a feature without a redactor (or vice-versa) MUST fail loudly.
"""
from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------------------
# Per-redactor unit tests
# ---------------------------------------------------------------------------


class TestSessionSummaryRedaction:
    """`therapy.session_summary` — chat with transcript + observations."""

    def _redactors(self):
        from app.services.audit_hook import REDACTION_BY_FEATURE
        return REDACTION_BY_FEATURE["therapy.session_summary"]

    def test_arguments_scrub_message_content(self):
        """Raw `messages[].content` MUST NOT appear in the redacted dict."""
        redact_args, _ = self._redactors()
        raw_transcript = "Paciente apresenta sintomas depressivos. Histórico de tratamento prévio."
        result = redact_args({
            "messages": [
                {"role": "system", "content": "Você é um assistente clínico..."},
                {"role": "user", "content": raw_transcript},
            ],
            "model": "gpt-4o",
            "temperature": 0.4,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"},
            "cache": False,
            "org_id": "clinic-uuid-xyz",
        })
        # Structural metadata preserved
        assert result["model"] == "gpt-4o"
        assert result["temperature"] == 0.4
        assert result["org_id_present"] is True
        assert result["cache"] is False
        # Message ROLES preserved (we want to know shape)
        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "system"
        assert result["messages"][1]["role"] == "user"
        # CONTENT redacted — length only
        assert result["messages"][1]["content"]["redacted_length"] == len(raw_transcript)
        assert result["messages"][1]["content"]["present"] is True
        # Bijection: clinical content NEVER appears anywhere in the output
        serialized = json.dumps(result, default=str)
        assert raw_transcript not in serialized
        assert "depressivos" not in serialized
        assert "tratamento prévio" not in serialized

    def test_arguments_handles_non_mapping(self):
        """Non-Mapping input → fully redacted dict (defensive shape)."""
        redact_args, _ = self._redactors()
        assert redact_args(None) == {"_redacted": True}
        assert redact_args("just a string") == {"_redacted": True}

    def test_result_scrub_summary_body(self):
        """The `summary` field carries clinical text — must be length-only."""
        _, redact_result = self._redactors()
        summary_text = "A sessão focou em sintomas de ansiedade e estratégias de enfrentamento."
        result = redact_result({
            "summary": summary_text,
            "key_points": ["ansiedade", "TCC", "estratégias"],
            "tags": ["clínico", "ansiedade"],
        })
        assert result["present"] is True
        assert result["summary"]["redacted_length"] == len(summary_text)
        assert result["key_points_count"] == 3
        assert result["tags_count"] == 2
        # Clinical content absent
        serialized = json.dumps(result, default=str)
        assert summary_text not in serialized
        assert "enfrentamento" not in serialized

    def test_result_handles_raw_json_string(self):
        """When LLM returns a raw JSON string, redactor records the length only."""
        _, redact_result = self._redactors()
        raw_json = '{"summary": "Paciente discutiu trauma de infância", "key_points": []}'
        result = redact_result(raw_json)
        assert result["present"] is True
        assert result["response_length"] == len(raw_json)
        assert result["kind"] == "raw_json_string"
        # Clinical content absent
        serialized = json.dumps(result, default=str)
        assert "trauma" not in serialized
        assert "infância" not in serialized

    def test_result_handles_none(self):
        _, redact_result = self._redactors()
        assert redact_result(None) == {"present": False}


class TestLongitudinalRedaction:
    """`therapy.longitudinal_narrative` — aggregates N sessions of clinical text."""

    def _redactors(self):
        from app.services.audit_hook import REDACTION_BY_FEATURE
        return REDACTION_BY_FEATURE["therapy.longitudinal_narrative"]

    def test_arguments_scrub_multi_session_aggregation(self):
        redact_args, _ = self._redactors()
        # Aggregation of 6 sessions of clinical content — highest sensitivity.
        sessions_aggregate = "\n\n".join(
            f"--- Sessão {i} ---\nResumo: paciente relatou sintoma X{i}"
            for i in range(6)
        )
        result = redact_args({
            "messages": [
                {"role": "system", "content": "Análise longitudinal..."},
                {"role": "user", "content": sessions_aggregate},
            ],
            "model": "gpt-4o",
        })
        serialized = json.dumps(result, default=str)
        assert sessions_aggregate not in serialized
        assert "sintoma X3" not in serialized
        # But length is preserved
        assert result["messages"][1]["content"]["redacted_length"] == len(sessions_aggregate)

    def test_result_scrub_narrative_fields(self):
        _, redact_result = self._redactors()
        narrative_text = (
            "Ao longo das sessões, o paciente demonstrou progresso significativo "
            "no manejo de sintomas ansiosos. Padrões recorrentes incluem ruminação noturna."
        )
        result = redact_result({
            "narrative_summary": narrative_text,
            "recurring_themes": ["ansiedade", "ruminação", "trabalho"],
            "progress_timeline": [{"session": 1, "milestone": "início"}, {"session": 4, "milestone": "estabilidade"}],
            "unresolved_topics": ["medo de avaliação"],
            "observation_insights": ["evita olhar contato"],
        })
        assert result["present"] is True
        assert result["narrative_summary"]["redacted_length"] == len(narrative_text)
        assert result["recurring_themes_count"] == 3
        assert result["progress_timeline_count"] == 2
        assert result["unresolved_topics_count"] == 1
        assert result["observation_insights_count"] == 1
        # Clinical content absent
        serialized = json.dumps(result, default=str)
        assert narrative_text not in serialized
        assert "ruminação noturna" not in serialized
        assert "medo de avaliação" not in serialized
        assert "evita olhar contato" not in serialized


class TestImageAttachmentRedaction:
    """`therapy.attachment_analyze_image` — patient-uploaded images via Vision."""

    def _redactors(self):
        from app.services.audit_hook import REDACTION_BY_FEATURE
        return REDACTION_BY_FEATURE["therapy.attachment_analyze_image"]

    def test_arguments_drop_image_bytes(self):
        """Raw bytes MUST be replaced with byte_length only — never stored."""
        redact_args, _ = self._redactors()
        # 8KB of image bytes (simulating a small clinical document scan)
        image_bytes = b"\x89PNG\r\n\x1a\n" + b"X" * 8192
        result = redact_args({
            "image": image_bytes,
            "prompt": "Descreva esta imagem.",
            "model": "gpt-4o",
            "max_tokens": 500,
            "org_id": "clinic-xyz",
        })
        assert result["image_bytes"]["present"] is True
        assert result["image_bytes"]["byte_length"] == len(image_bytes)
        assert result["model"] == "gpt-4o"
        # Bytes never present in serialized form
        serialized = json.dumps(result, default=str)
        assert "PNG" not in serialized  # crude check; bytes wouldn't serialize anyway

    def test_result_drop_vision_response(self):
        _, redact_result = self._redactors()
        vision_response = (
            "A imagem mostra um relatório médico com diagnóstico de transtorno de ansiedade generalizada."
        )
        result = redact_result(vision_response)
        assert result["present"] is True
        assert result["response_length"] == len(vision_response)
        serialized = json.dumps(result, default=str)
        assert vision_response not in serialized
        assert "ansiedade generalizada" not in serialized


class TestAudioRedaction:
    """Audio dispatch keys: `therapy.attachment_transcribe_audio` +
    `therapy.session_transcribe_audio` — Whisper over raw patient audio."""

    @pytest.mark.parametrize(
        "feature_key",
        ["therapy.attachment_transcribe_audio", "therapy.session_transcribe_audio"],
    )
    def test_arguments_drop_audio_bytes(self, feature_key):
        from app.services.audit_hook import REDACTION_BY_FEATURE
        redact_args, _ = REDACTION_BY_FEATURE[feature_key]
        # 64KB simulated audio
        audio_bytes = b"\x00" * (64 * 1024)
        result = redact_args({
            "audio": audio_bytes,
            "model": "whisper-1",
            "filename": "session.ogg",
            "language": "pt",
            "org_id": "clinic-xyz",
        })
        assert result["audio_bytes"]["byte_length"] == len(audio_bytes)
        assert result["model"] == "whisper-1"
        assert result["language"] == "pt"

    @pytest.mark.parametrize(
        "feature_key",
        ["therapy.attachment_transcribe_audio", "therapy.session_transcribe_audio"],
    )
    def test_result_drop_transcript(self, feature_key):
        from app.services.audit_hook import REDACTION_BY_FEATURE
        _, redact_result = REDACTION_BY_FEATURE[feature_key]
        # Whisper output: the actual session transcript — the MOST sensitive surface.
        transcript = (
            "Paciente: Tenho me sentido muito ansioso ultimamente. Terapeuta: "
            "Pode me contar mais sobre isso? Paciente: Episódios de pânico no trabalho."
        )
        result = redact_result(transcript)
        assert result["present"] is True
        assert result["transcript_length"] == len(transcript)
        serialized = json.dumps(result, default=str)
        assert transcript not in serialized
        assert "ansioso" not in serialized
        assert "pânico no trabalho" not in serialized


# ---------------------------------------------------------------------------
# Bijection / coverage tests
# ---------------------------------------------------------------------------


class TestFeatureRedactorBijection:
    """Pin the contract: every `register_feature` call has a matching
    redactor entry. Adding a feature without wiring its redactor is the
    LGPD slip we're guarding against (Phase 0 finding §11.2)."""

    def test_every_therapy_feature_has_a_redactor(self):
        """The boot-time assert in `ai_consent_features._assert_redactor_coverage`
        runs at import. This pins the bijection explicitly for CI."""
        from app.services import ai_consent_features  # noqa: F401 — runs boot-assert
        from app.services.audit_hook import REDACTION_BY_FEATURE
        from noctusai_lib.domain.ai import get_catalog

        therapy_features = {f.key for f in get_catalog() if f.product == "therapy"}
        for key in therapy_features:
            assert key in REDACTION_BY_FEATURE, (
                f"feature {key!r} has no redactor — LGPD compliance gap. "
                f"Add to app.services.audit_hook.REDACTION_BY_FEATURE."
            )

    def test_redact_for_feature_fail_closed_on_unknown_key(self, caplog):
        """Unknown feature_key MUST fail-closed (drop both args + result),
        never pass through raw content."""
        import logging as _logging

        from app.services.audit_hook import redact_for_feature

        raw_clinical = "Paciente: histórico de trauma"
        with caplog.at_level(_logging.WARNING):
            args, result = redact_for_feature(
                "therapy.unknown_feature_xyz",
                {"messages": [{"role": "user", "content": raw_clinical}]},
                raw_clinical,
            )
        # Fail-closed posture: both fields redacted.
        assert args == {"_redacted": True, "feature_key_unknown": "therapy.unknown_feature_xyz"}
        assert result == {"_redacted": True}
        # Log records the gap so we can spot drift.
        assert any(
            "no redactor registered" in r.getMessage() for r in caplog.records
        )
