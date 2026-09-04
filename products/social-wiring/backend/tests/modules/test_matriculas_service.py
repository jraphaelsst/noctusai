"""Tests for the Matrícula extractor service — the PRODUCT's half.

Ported from `erp-imobiliario`'s `tests/services/test_matricula_service.py`
as ERP is retired, plus the two things this port added that ERP never had:
the org predicate on every service-role write, and the recovery sweep.

The transcription ladder lives in the seed
(`noctusai_lib.integrations.documents.transcription`) and its tests go with
it — page routing, the scan-stamp defect and the vision cap are covered in
`seed/lib/backend/tests/integrations/documents/test_transcription.py`.

What is left here is what would silently rot if nobody asserted it: the
`matricula_extracoes` status lifecycle, the mapping from a seed error CODE
to a sentence this product's users can act on, and the fact that a
service-role write cannot escape its org.
"""
import pytest
from unittest.mock import patch

from noctusai_lib.integrations.documents import TextSource
from noctusai_lib.integrations.documents.transcription import (
    TranscribedPage,
    Transcription,
)

from app.modules.matriculas import service as matricula_service
from app.modules.matriculas.service import (
    MENSAGEM_ORFA,
    check_required_credentials,
    processar_extracao,
    varrer_pendentes,
)

_ORG = "11111111-1111-4111-8111-111111111111"


class _RecordingDB:
    """Records what the service wrote, which MockSupabaseClient swallows.

    These tests are about the OUTCOME written to the row — and about the
    predicates the write carried, which is the org-scoping contract — so the
    double has to keep both.
    """

    def __init__(self):
        self.updates: list[dict] = []
        self.predicates: list[list[tuple]] = []
        self._current: list[tuple] = []

    def table(self, _name):
        self._current = []
        return self

    def update(self, payload):
        self.updates.append(payload)
        self.predicates.append(self._current)
        return self

    def eq(self, col, val):
        self._current.append((col, val))
        return self

    def execute(self):
        return type("_R", (), {"data": []})()

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
            "e1", b"%PDF", _ORG, db, transcriber=_StubTranscriber(_ok("P1", "P2"))
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
        await processar_extracao("e2", b"%PDF", _ORG, db, transcriber=stub)

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
        await processar_extracao("e3", b"%PDF", _ORG, db, transcriber=_Explodes())

        assert db.last["status"] == "erro"
        assert "boom" in db.last["erro_mensagem"]

    @pytest.mark.asyncio
    async def test_no_transcriber_and_no_factory_is_recorded_not_raised(self):
        """The service must never build its own transcriber, and must never
        raise out of the background task when neither seam is supplied."""
        db = _RecordingDB()
        await processar_extracao("e3b", b"%PDF", _ORG, db)

        assert db.last["status"] == "erro"
        assert "transcriber" in db.last["erro_mensagem"]

    @pytest.mark.asyncio
    async def test_the_factory_seam_is_called_with_the_org(self):
        chamadas: list = []

        def _factory(org_id):
            chamadas.append(org_id)
            return _StubTranscriber(_ok("P1"))

        db = _RecordingDB()
        await processar_extracao(
            "e3c", b"%PDF", _ORG, db, transcriber_factory=_factory
        )

        assert chamadas == [_ORG]
        assert db.last["status"] == "concluida"


class TestEveryServiceRoleWriteIsOrgScoped:
    """🔴 The background task writes SERVICE-ROLE, which bypasses RLS.

    Whatever scoping RLS would have done has to be done by hand, on every
    single write — an UPDATE that reached only `id` would still be correct
    for a UUID primary key, but it would be correct by accident, and the
    sweep's bulk path is one `.eq` away from being wrong for everyone.
    """

    @pytest.mark.asyncio
    async def test_both_lifecycle_writes_carry_the_org_predicate(self):
        db = _RecordingDB()
        await processar_extracao(
            "e6", b"%PDF", _ORG, db, transcriber=_StubTranscriber(_ok("P1"))
        )

        assert len(db.predicates) == 2
        for preds in db.predicates:
            assert ("id", "e6") in preds
            assert ("org_id", _ORG) in preds

    @pytest.mark.asyncio
    async def test_a_missing_org_is_refused_not_widened(self):
        """An empty org must never produce an unscoped UPDATE. The refusal
        lands as an `erro` row rather than as an exception, because this
        still runs detached."""
        db = _RecordingDB()
        await processar_extracao(
            "e7", b"%PDF", "", db, transcriber=_StubTranscriber(_ok("P1"))
        )

        assert db.updates == [], "an org-less write must not reach the DB at all"


class TestSeedErrorCodesReachUsersAsPortuguese:
    """🔴 The seam the seed lift created.

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
            # Provider-agnostic since the manual OpenAI ↔ Anthropic switch
            # (2026-09-04): which key is missing depends on the org's
            # selection, so the sentence points at the screen that shows
            # BOTH the keys and the switch instead of naming one vendor.
            ("missing_credentials", "Chaves de API"),
            ("too_many_vision_pages", "muito longo"),
            ("rasterize_failed", "todas as páginas"),
        ],
    )
    @pytest.mark.asyncio
    async def test_every_actionable_code_has_portuguese(self, codigo, trecho):
        db = _RecordingDB()
        await processar_extracao(
            "e4", b"%PDF", _ORG, db,
            transcriber=_StubTranscriber(
                Transcription(error=codigo, error_message="dev-facing detail")
            ),
        )

        assert db.last["status"] == "erro"
        assert trecho in db.last["erro_mensagem"]
        assert "dev-facing detail" not in db.last["erro_mensagem"], (
            "a mapped code must not leak the developer message to the user"
        )

    @pytest.mark.asyncio
    async def test_the_credentials_message_names_the_page_to_go_to(self):
        """"OpenAI API Key não configurada" tells the user WHAT is wrong and
        nothing about what to do. The destination is the actionable half, and
        it names THIS product's page (the `Chaves de API` section of
        `frontend/src/pages/Settings.tsx`), not ERP's."""
        db = _RecordingDB()
        await processar_extracao(
            "e8", b"%PDF", _ORG, db,
            transcriber=_StubTranscriber(
                Transcription(error="missing_credentials")
            ),
        )
        assert "Configurações → Chaves de API" in db.last["erro_mensagem"]

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
            "e5", b"%PDF", _ORG, db,
            transcriber=_StubTranscriber(
                Transcription(
                    error="transcription_failed", error_message="mupdf exploded"
                )
            ),
        )
        assert "mupdf exploded" in db.last["erro_mensagem"]


class _SweepDB:
    """A double that answers the sweep's SELECT and records its UPDATEs."""

    def __init__(self, rows):
        self._rows = rows
        self.updates: list[tuple[dict, list]] = []
        self._preds: list = []
        self._mode = None

    # ── chain ────────────────────────────────────────────────────────────
    def table(self, _name):
        self._preds = []
        self._mode = None
        return self

    def select(self, _cols, **_k):
        self._mode = "select"
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def in_(self, col, val):
        self._preds.append((col, val))
        return self

    def lt(self, col, val):
        self._preds.append((col, val))
        return self

    def eq(self, col, val):
        self._preds.append((col, val))
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        if self._mode == "update":
            self.updates.append((self._payload, list(self._preds)))
            return type("_R", (), {"data": []})()
        return type("_R", (), {"data": list(self._rows)})()


class TestTheRecoverySweep:
    """🔴 A deploy mid-extraction strands a row in `processando` forever.

    Nothing else moves it: the request is long gone, the background task
    died with the process, and no error was ever raised to anyone. The row
    just sits there with an empty text field. That is a silent error with a
    schedule attached, and this is the only thing that closes it.
    """

    @pytest.mark.asyncio
    async def test_a_stranded_row_is_closed_out_with_a_usable_message(self):
        db = _SweepDB([
            {"id": "s1", "org_id": _ORG, "nome_arquivo": "m.pdf",
             "status": "processando"},
        ])

        resultado = await varrer_pendentes(db, None)

        assert resultado == {"encontrados": 1, "marcados": 1}
        payload, preds = db.updates[0]
        assert payload["status"] == "erro"
        assert payload["erro_mensagem"] == MENSAGEM_ORFA
        assert ("id", "s1") in preds and ("org_id", _ORG) in preds

    @pytest.mark.asyncio
    async def test_the_message_asks_for_a_re_upload_because_retry_is_impossible(self):
        """This workflow keeps no copy of the PDF — the bytes live only in
        the background task's closure. A message implying a retry would be a
        promise nothing can keep."""
        assert "novamente" in MENSAGEM_ORFA.lower()

    @pytest.mark.asyncio
    async def test_nothing_stranded_means_nothing_written(self):
        db = _SweepDB([])
        assert await varrer_pendentes(db, None) == {"encontrados": 0, "marcados": 0}
        assert db.updates == []

    @pytest.mark.asyncio
    async def test_an_org_less_row_is_skipped_never_swept_unscoped(self):
        """`org_id` is NOT NULL with a DB default, so a row without one means
        the schema drifted. Sweeping it would need an UPDATE with no org
        predicate — reaching every tenant. It is reported and left alone."""
        db = _SweepDB([
            {"id": "s2", "org_id": None, "status": "processando"},
            {"id": "s3", "org_id": _ORG, "status": "pendente"},
        ])

        resultado = await varrer_pendentes(db, None)

        assert resultado == {"encontrados": 2, "marcados": 1}
        assert [preds for _p, preds in db.updates] == [
            [("id", "s3"), ("org_id", _ORG)]
        ]

    @pytest.mark.asyncio
    async def test_only_non_terminal_states_are_looked_at(self):
        db = _SweepDB([])
        await varrer_pendentes(db, None)
        assert ("status", ["pendente", "processando"]) in db._preds


class TestCheckRequiredCredentials:
    """🔴 Checks the SELECTED provider's key, not OpenAI's unconditionally.

    Since the manual switch landed (2026-09-04) an org can run on Anthropic.
    Warning it forever about an OpenAI key it deliberately does not use is
    how a settings panel trains its operators to ignore it — and it hides
    the warning that matters when the key that IS used goes missing.
    """

    #: The org's stored choice. Patched rather than reached for: resolving
    #: it for real builds the encrypted store, which needs a Supabase client
    #: these unit tests deliberately do not have.
    _NO_PROVEDOR = "app.services.api_keys_store.resolve_vision_provider"

    def test_sem_a_chave_do_provedor_selecionado_retorna_mensagem(self):
        with patch(
            "app.modules.matriculas.service.resolve_credential", return_value=None
        ), patch(self._NO_PROVEDOR, return_value="openai"):
            missing = check_required_credentials(_ORG)
        assert len(missing) == 1
        assert "OpenAI" in missing[0]

    def test_com_a_chave_retorna_vazio(self):
        with patch(
            "app.modules.matriculas.service.resolve_credential", return_value="sk-test"
        ), patch(self._NO_PROVEDOR, return_value="openai"):
            missing = check_required_credentials(_ORG)
        assert missing == []

    def test_um_org_no_anthropic_e_avisado_sobre_a_chave_anthropic(self):
        """The whole point of the switch: the warning follows the choice."""
        with patch(
            "app.modules.matriculas.service.resolve_credential", return_value=None
        ), patch(self._NO_PROVEDOR, return_value="anthropic"):
            missing = check_required_credentials(_ORG)
        assert len(missing) == 1
        assert "Anthropic" in missing[0]
        assert "OpenAI" not in missing[0]


class TestTheSweepIsActuallyScheduled:
    """A safety net that is never registered is not a safety net.

    `configure()` must run at IMPORT time, before `start_scheduler()` fires
    in `app/lifespan.py`, and it must not land on a minute one of the two
    existing sweeps already occupies.
    """

    def test_configure_registers_the_job(self):
        from noctusai_lib.api import scheduler as seed_scheduler

        from app.modules.matriculas import extracao_scheduler

        extracao_scheduler.configure()
        assert seed_scheduler.scheduler.get_job(extracao_scheduler.JOB_ID) is not None

    def test_the_cron_minute_does_not_collide_with_the_sibling_sweeps(self):
        from app.modules.card_hub import extracao_scheduler as card
        from app.modules.imovel_hub import extracao_scheduler as imovel
        from app.modules.matriculas import extracao_scheduler as matriculas

        minutos = {
            c.CRON.split()[0] for c in (card, imovel, matriculas)
        }
        assert len(minutos) == 3, f"two sweeps share a minute: {minutos}"
