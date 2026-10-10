"""Segundo Cérebro voice answers: endpoint 13, the `cerebro_resposta` completion hook and
`Answer.transcricao` (cerebro-contract.md §3, §4 #13, §10.1)."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import anyio
import pytest
from noctusai_lib.integrations.transcription import FakeTranscriber, TranscriberBusy, TranscriptionRejected

from app.modules.media_creation.cerebro_templates import question_id
from app.modules.media_creation.schemas.cerebro import MAX_ANSWER_CHARS
from app.modules.transcricoes.worker import build_worker
from tests.modules.transcricoes.conftest import AUDIO, ORG, probe

BASE = "/api/media-creation/cerebro"
NUCLEO = "nucleo-de-influencia"
Q1, Q2 = question_id(NUCLEO, 1), question_id(NUCLEO, 2)
MARCA = str(uuid.uuid4())
CFG = SimpleNamespace(transcricao_gate_ttl_seconds=0.0, transcricao_poll_seconds=0.01, transcricao_lease_seconds=60.0)


@pytest.fixture
def cc(client):
    client.mock_supabase.from_("marcas").insert({"id": MARCA, "org_id": ORG, "name": "M"}).execute()
    client.mock_supabase.from_("marcas").insert({"id": str(uuid.uuid4()), "org_id": "other", "name": "X"}).execute()
    return client


def brains(c):
    return c.get(f"{BASE}/brains", params={"marca_id": MARCA}).json()["data"]


def sistema(c):
    return next(b for b in brains(c) if b["template_slug"] == NUCLEO)


def audio(c, brain_id, qid, data=AUDIO):
    return c.post(
        f"{BASE}/brains/{brain_id}/answers/{qid}/audio", files={"arquivo": ("v.webm", data, "audio/webm")}
    )


def detail_answer(c, brain_id, qid):
    d = c.get(f"{BASE}/brains/{brain_id}").json()["data"]
    return next(a for a in d["answers"] if a["question_id"] == qid)


def answer_row(c, brain_id, qid):
    rs = c.mock_supabase.from_("cs_brain_answers").select("*").execute().data
    return next((r for r in rs if r["brain_id"] == brain_id and r["question_id"] == qid), None)


def run_worker(c):
    w = build_worker(c.jobs, c.mock_supabase, c.storage, CFG, lambda: c.transcriber, lambda: True)
    return anyio.run(w.run_once)


def make_due(c):
    for job in list(c.jobs._jobs.values()):
        c.jobs._jobs[job.id] = type(job)(**{**job.__dict__, "scheduled_for": None})


class TestEndpoint13:
    def test_202_answer_with_its_queued_transcricao(self, cc):
        b = sistema(cc)
        r = audio(cc, b["id"], Q1)
        assert r.status_code == 202, r.text
        a = r.json()["data"]
        assert a["question_id"] == Q1 and a["text"] == ""
        t = a["transcricao"]
        assert t["status"] == "na_fila" and t["posicao"] == 1 and t["texto"] is None and t["erro"] is None
        [row] = cc.mock_supabase.from_("transcricoes").select("*").execute().data
        assert row["contexto_tipo"] == "cerebro_resposta" and row["contexto_ref"] == f"{b['id']}:{Q1}"
        assert t["id"] == row["id"]

    def test_delegates_to_the_shared_caps_and_codes(self, cc):
        b = sistema(cc)
        assert audio(cc, b["id"], Q1, data=b"MZ\x90\x00" + b"\x00" * 64).json()["codigo"] == "formato_invalido"
        cc.transcriber = FakeTranscriber(default_probe=probe(601.0))
        r = audio(cc, b["id"], Q1)
        assert r.status_code == 422 and r.json()["codigo"] == "duracao_excedida"
        cc.habilitada = False
        r = audio(cc, b["id"], Q1)
        assert r.status_code == 503 and r.json()["codigo"] == "transcricao_desativada"

    def test_shares_the_per_user_quota_with_the_generic_endpoint(self, cc):
        b = sistema(cc)
        assert audio(cc, b["id"], Q1).status_code == 202
        assert audio(cc, b["id"], Q2).status_code == 202
        r = audio(cc, b["id"], question_id(NUCLEO, 3))
        assert r.status_code == 429 and r.json()["codigo"] == "limite_usuario"

    def test_foreign_unknown_and_custom_brains_are_404(self, cc):
        b = sistema(cc)
        assert audio(cc, uuid.uuid4(), Q1).status_code == 404
        assert audio(cc, b["id"], "nucleo-de-influencia.99").status_code == 404
        custom = cc.post(f"{BASE}/brains", json={"marca_id": MARCA, "name": "Livre"}).json()["data"]
        assert audio(cc, custom["id"], Q1).status_code == 404  # no questionnaire
        assert cc.mock_supabase.from_("transcricoes").select("*").execute().data == []

    def test_another_orgs_brain_is_404(self, cc):
        sb = cc.mock_supabase
        other = str(uuid.uuid4())
        sb.from_("cs_brains").insert({
            "id": other, "org_id": "other", "marca_id": str(uuid.uuid4()), "kind": "sistema",
            "template_slug": NUCLEO, "name": "n", "content": "", "content_version": 0,
        }).execute()
        assert audio(cc, other, Q1).status_code == 404

    def test_unauthenticated_is_401(self, cc):
        b = sistema(cc)
        r = cc.raw().post(
            f"{BASE}/brains/{b['id']}/answers/{Q1}/audio", files={"arquivo": ("v.webm", AUDIO, "audio/webm")}
        )
        assert r.status_code == 401


class TestCompletionHook:
    def test_blank_answer_gets_the_transcript_and_links_the_job(self, cc):
        b = sistema(cc)
        cc.transcriber = FakeTranscriber(script=["Eu ajudo famílias."])
        audio(cc, b["id"], Q1)
        assert run_worker(cc) is True
        a = detail_answer(cc, b["id"], Q1)
        assert a["text"] == "Eu ajudo famílias."
        t = a["transcricao"]
        assert t["status"] == "concluida" and t["texto"] == "Eu ajudo famílias." and t["erro"] is None
        assert answer_row(cc, b["id"], Q1)["transcricao_id"] == t["id"]

    def test_existing_text_is_appended_after_a_blank_line_and_review_resets(self, cc):
        b = sistema(cc)
        cc.put(f"{BASE}/brains/{b['id']}/answers/{Q1}", json={"text": "Já escrevi isto."})
        cc.mock_supabase.from_("cs_brain_answers").update(
            {"review_status": "done", "review_verdict": "approved", "reviewed_text_sha": "x"}
        ).eq("brain_id", b["id"]).execute()
        cc.transcriber = FakeTranscriber(script=["E falei isto."])
        audio(cc, b["id"], Q1)
        run_worker(cc)
        a = detail_answer(cc, b["id"], Q1)
        assert a["text"] == "Já escrevi isto.\n\nE falei isto."
        assert a["review"]["status"] == "none" and a["review"]["verdict"] is None

    def test_applied_exactly_once_even_if_the_job_is_delivered_twice(self, cc):
        b = sistema(cc)
        cc.transcriber = FakeTranscriber(script=["uma vez"])
        audio(cc, b["id"], Q1)
        w = build_worker(cc.jobs, cc.mock_supabase, cc.storage, CFG, lambda: cc.transcriber, lambda: True)
        anyio.run(w.run_once)
        job = next(iter(cc.jobs._jobs.values()))
        anyio.run(lambda: w._handlers["transcricao"](job))  # redelivery
        assert detail_answer(cc, b["id"], Q1)["text"] == "uma vez"

    def test_two_recordings_for_two_questions_land_in_their_own_answers(self, cc):
        b = sistema(cc)
        cc.transcriber = FakeTranscriber(script=["primeira", "segunda"])
        audio(cc, b["id"], Q1)
        audio(cc, b["id"], Q2)
        run_worker(cc)
        run_worker(cc)
        assert detail_answer(cc, b["id"], Q1)["text"] == "primeira"
        assert detail_answer(cc, b["id"], Q2)["text"] == "segunda"

    def test_a_transcript_over_the_answer_cap_is_clipped_and_kept_whole_on_the_job(self, cc):
        b = sistema(cc)
        long = ("palavra " * 1600).strip()  # 12 799 chars > 10 000
        cc.transcriber = FakeTranscriber(script=[long])
        audio(cc, b["id"], Q1)
        run_worker(cc)
        a = detail_answer(cc, b["id"], Q1)
        assert 0 < len(a["text"]) <= MAX_ANSWER_CHARS
        assert a["transcricao"]["texto"] == long

    def test_a_deleted_brain_does_not_break_the_job(self, cc):
        b = sistema(cc)
        cc.transcriber = FakeTranscriber(script=["órfã"])
        audio(cc, b["id"], Q1)
        cc.mock_supabase.from_("cs_brains").delete().eq("id", b["id"]).execute()
        assert run_worker(cc) is True
        [row] = cc.mock_supabase.from_("transcricoes").select("*").execute().data
        assert row["status"] == "concluida"


class TestAnswerTranscricaoStates:
    def test_failed_job_exposes_codigo_and_pt_br_message(self, cc):
        b = sistema(cc)
        cc.transcriber = FakeTranscriber(script=[TranscriptionRejected("audio_corrompido")])
        audio(cc, b["id"], Q1)
        run_worker(cc)
        t = detail_answer(cc, b["id"], Q1)["transcricao"]
        assert t["status"] == "falhou" and t["erro"]["codigo"] == "audio_corrompido" and t["erro"]["mensagem"]
        assert t["texto"] is None

    def test_busy_keeps_it_queued_with_a_position_in_the_brain_detail(self, cc):
        b = sistema(cc)
        cc.transcriber = FakeTranscriber(script=[TranscriberBusy(5.0)])
        audio(cc, b["id"], Q1)
        run_worker(cc)
        t = detail_answer(cc, b["id"], Q1)["transcricao"]
        assert t["status"] == "na_fila" and t["posicao"] == 1 and t["texto"] is None

    def test_reload_during_processing_still_shows_the_job(self, cc):
        b = sistema(cc)
        audio(cc, b["id"], Q1)
        cc.mock_supabase.from_("transcricoes").update({"status": "processando"}).eq("contexto_ref", f"{b['id']}:{Q1}").execute()
        t = detail_answer(cc, b["id"], Q1)["transcricao"]
        assert t["status"] == "processando" and t["posicao"] is None

    def test_recording_before_typing_creates_a_blank_answer_linked_to_the_job(self, cc):
        b = sistema(cc)
        r = audio(cc, b["id"], Q1)
        row = answer_row(cc, b["id"], Q1)
        assert row["text"] == "" and row["transcricao_id"] == r.json()["data"]["transcricao"]["id"]
        assert sistema(cc)["answered"] == 0  # a blank answer is not "answered"

    def test_answers_without_voice_have_no_transcricao(self, cc):
        b = sistema(cc)
        d = cc.get(f"{BASE}/brains/{b['id']}").json()["data"]
        assert all(a["transcricao"] is None for a in d["answers"])
