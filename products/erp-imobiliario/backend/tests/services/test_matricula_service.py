"""Tests for the Matrícula extractor service — the PRODUCT's half.

The transcription ladder moved to the seed on 2026-08-25
(`noctusai_lib.integrations.documents.transcription`), and its tests went
with it — page routing, the scan-stamp defect and the vision cap are
covered in `seed/lib/backend/tests/integrations/documents/test_transcription.py`.

What is left here is what did NOT move, and what would silently rot if
nobody asserted it: the `matricula_extracoes` status lifecycle, and the
mapping from a seed error CODE to a sentence this product's users can act
on. That mapping is the reason the seed returns codes rather than prose,
so a gap in it is a real defect — an unmapped code reaches the user as a
developer string.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.services import matricula_service
from app.services.matricula_service import (
    check_required_credentials,
    processar_extracao,
)
from noctusai_lib.integrations.documents import TextSource
from noctusai_lib.integrations.documents.transcription import (
    TranscribedPage,
    Transcription,
)


class _RecordingDB:
    """Records what the service wrote, which MockSupabaseClient swallows.

    These tests are about the OUTCOME written to the row, so the double has
    to keep it.
    """

    def __init__(self):
        self.updates: list[dict] = []

    def table(self, _name):
        return self

    def update(self, payload):
        self.updates.append(payload)
        return self

    def eq(self, _col, _val):
        return self

    def execute(self):
        return MagicMock(data=[])

    @property
    def last(self) -> dict:
        return self.updates[-1]


class _StubTranscriber:
    """Stands in for the seed transcriber."""

    def __init__(self, resultado):
        self._resultado = resultado
        self.calls = 0

    async def transcribe(self, content, *, mimetype=None, filename=None):
        self.calls += 1
        return self._resultado


def _ok(*textos: str) -> Transcription:
    return Transcription(
        pages=tuple(
            TranscribedPage(number=i, text=t, source=TextSource.OCR)
            for i, t in enumerate(textos, 1)
        ),
        num_paginas=len(textos),
    )


class TestTheStatusLifecycle:
    @pytest.mark.asyncio
    async def test_a_successful_extraction_goes_processando_then_concluida(self):
        db = _RecordingDB()
        await processar_extracao(
            "e1", b"%PDF", "org-1", db, transcriber=_StubTranscriber(_ok("P1", "P2"))
        )

        assert [u.get("status") for u in db.updates] == ["processando", "concluida"]
        assert db.last["texto_extraido"] == "P1\n\nP2"
        assert db.last["num_paginas"] == 2

    @pytest.mark.asyncio
    async def test_the_row_is_marked_processando_before_any_work(self):
        """A row stuck at 'pendente' is indistinguishable from one nobody
        picked up, so the transition has to happen first."""
        db = _RecordingDB()
        stub = _StubTranscriber(_ok("P1"))
        await processar_extracao("e2", b"%PDF", None, db, transcriber=stub)

        assert db.updates[0] == {"status": "processando"}
        assert stub.calls == 1

    @pytest.mark.asyncio
    async def test_an_unexpected_exception_still_lands_as_erro(self):
        """This runs as a background task — an escaping exception would
        strand the row at 'processando' forever."""
        class _Explodes:
            async def transcribe(self, content, **kw):
                raise RuntimeError("boom")

        db = _RecordingDB()
        await processar_extracao("e3", b"%PDF", None, db, transcriber=_Explodes())

        assert db.last["status"] == "erro"
        assert "boom" in db.last["erro_mensagem"]


class TestSeedErrorCodesReachUsersAsPortuguese:
    """🔴 The seam the lift created.

    The seed reports machine codes because a chatbot and a settings screen
    need different words for the same failure. That only holds if this
    product actually maps them — an unmapped code reaches the user as a
    developer string.
    """

    @pytest.mark.parametrize(
        "codigo,trecho",
        [
            ("no_pages", "sem páginas"),
            ("empty_document", "vazio"),
            ("missing_credentials", "OpenAI API Key"),
            ("too_many_vision_pages", "muito longo"),
            ("rasterize_failed", "todas as páginas"),
        ],
    )
    @pytest.mark.asyncio
    async def test_every_actionable_code_has_portuguese(self, codigo, trecho):
        db = _RecordingDB()
        await processar_extracao(
            "e4", b"%PDF", None, db,
            transcriber=_StubTranscriber(
                Transcription(error=codigo, error_message="dev-facing detail")
            ),
        )

        assert db.last["status"] == "erro"
        assert trecho in db.last["erro_mensagem"]
        assert "dev-facing detail" not in db.last["erro_mensagem"], (
            "a mapped code must not leak the developer message to the user"
        )

    def test_the_map_covers_every_code_the_seed_can_return(self):
        """Guards against the seed growing a code this product silently
        renders as 'Erro inesperado'."""
        import inspect

        from noctusai_lib.integrations.documents import transcription

        fonte = inspect.getsource(transcription)
        codigos = {
            linha.split('error="')[1].split('"')[0]
            for linha in fonte.split("\n")
            if 'error="' in linha
        }
        # `transcription_failed` is deliberately unmapped: it means a bug,
        # not a condition the user can act on, so it falls through WITH the
        # developer detail attached rather than behind a generic apology.
        naomapeados = codigos - set(matricula_service._MENSAGENS) - {
            "transcription_failed", "vision_disabled",
        }
        assert not naomapeados, f"seed codes with no Portuguese: {naomapeados}"

    @pytest.mark.asyncio
    async def test_an_unmapped_code_still_says_what_happened(self):
        db = _RecordingDB()
        await processar_extracao(
            "e5", b"%PDF", None, db,
            transcriber=_StubTranscriber(
                Transcription(
                    error="transcription_failed", error_message="mupdf exploded"
                )
            ),
        )
        assert "mupdf exploded" in db.last["erro_mensagem"]


class TestCheckRequiredCredentials:
    def test_sem_openai_retorna_mensagem(self):
        with patch(
            "app.services.matricula_service.resolve_credential", return_value=None
        ):
            missing = check_required_credentials("org-001")
        assert len(missing) == 1
        assert "OpenAI" in missing[0]

    def test_com_openai_retorna_vazio(self):
        with patch(
            "app.services.matricula_service.resolve_credential", return_value="sk-test"
        ):
            missing = check_required_credentials("org-001")
        assert missing == []
