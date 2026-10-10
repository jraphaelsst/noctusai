"""Segundo Cérebro (CoreStudio rebuild) — brains core contract tests
(cerebro-contract.md §4 endpoints 1-12 and 16-18, §8).

The LLM is faked through the real DI seam (``get_cerebro_llm`` dependency
override) and storage through ``get_cerebro_storage`` with a
``FakeStorageBackend`` — no patching of our own code.
"""
from __future__ import annotations

import json
import uuid

import pytest

from noctusai_lib.integrations.storage import FakeStorageBackend

from app.modules.media_creation.cerebro_templates import TEMPLATES_BY_SLUG, question_id
from app.modules.media_creation.deps import CEREBRO_BUCKET, get_cerebro_storage
from app.modules.media_creation.services import cerebro_service
from app.modules.media_creation.services.cerebro_ai import get_cerebro_llm

BASE = "/api/media-creation/cerebro"
ORG = "test-org-123"
MARCA = str(uuid.uuid4())
OTHER_MARCA = str(uuid.uuid4())  # belongs to another org
NUCLEO = "nucleo-de-influencia"
Q1, Q2, Q3 = (question_id(NUCLEO, i) for i in (1, 2, 3))
MSG_SYNTH_FAIL = "Ocorreu um erro ao gerar o cérebro. Tente novamente."


class _BrokenStorage(FakeStorageBackend):
    async def delete(self, *, bucket, key):
        raise RuntimeError("storage down")


@pytest.fixture
def cc(client):
    sb = client.mock_supabase
    sb.from_("marcas").insert({"id": MARCA, "org_id": ORG, "name": "Marca A"}).execute()
    sb.from_("marcas").insert({"id": OTHER_MARCA, "org_id": "other-org", "name": "Marca B"}).execute()
    client.llm_reply = "[]"
    client.llm_error = None
    client.llm_calls = []
    client.storage = FakeStorageBackend()

    async def fake_llm(system, user, org_id):
        client.llm_calls.append((system, user, org_id))
        if client.llm_error:
            raise client.llm_error
        return client.llm_reply

    overrides = client._tc.app.dependency_overrides
    overrides[get_cerebro_llm] = lambda: fake_llm
    overrides[get_cerebro_storage] = lambda: client.storage
    return client


def _rows(cc, table):
    return cc.mock_supabase.from_(table).select("*").execute().data


def _brains(cc):
    return cc.get(f"{BASE}/brains", params={"marca_id": MARCA}).json()["data"]


def _sistema(cc, slug=NUCLEO):
    return next(b for b in _brains(cc) if b["template_slug"] == slug)


def _custom(cc, name="Reels Instagram"):
    r = cc.post(f"{BASE}/brains", json={"marca_id": MARCA, "name": name})
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _answer(cc, brain_id, qid, text):
    r = cc.put(f"{BASE}/brains/{brain_id}/answers/{qid}", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _detail(cc, brain_id):
    return cc.get(f"{BASE}/brains/{brain_id}").json()["data"]


def _row(cc, brain_id):
    return next(r for r in _rows(cc, "cs_brains") if r["id"] == brain_id)


def _foreign_brain(cc):
    bid = str(uuid.uuid4())
    cc.mock_supabase.from_("cs_brains").insert({
        "id": bid, "org_id": "other-org", "marca_id": OTHER_MARCA, "kind": "custom",
        "template_slug": None, "name": "Alheio", "content": "segredo", "content_version": 0,
        "synthesis_status": "idle",
    }).execute()
    return bid


class TestTemplatesAndBrains:
    def test_templates_endpoint_returns_the_four_with_questions(self, cc):
        data = cc.get(f"{BASE}/templates").json()["data"]
        assert [t["slug"] for t in data] == [
            "historia-de-criacao", "historias-de-vida", "metodo-do-especialista", NUCLEO,
        ]
        nucleo = data[-1]
        assert len(nucleo["questions"]) == 15
        assert nucleo["questions"][0]["id"] == Q1 and nucleo["questions"][0]["hint"]
        assert nucleo["questions"][3]["group"] == 1

    def test_list_creates_sistema_brains_once_in_template_order_then_custom(self, cc):
        first = _brains(cc)
        _custom(cc)
        second = _brains(cc)
        assert len([r for r in _rows(cc, "cs_brains") if r["kind"] == "sistema"]) == 4
        assert [b["template_slug"] for b in first] == [
            "historia-de-criacao", "historias-de-vida", "metodo-do-especialista", NUCLEO,
        ]
        assert [b["kind"] for b in second] == ["sistema"] * 4 + ["custom"]
        s = second[0]
        assert s["status"] == "vazio" and s["answered"] == 0 and s["total_questions"] == 9
        assert second[-1]["answered"] is None and second[-1]["total_questions"] is None

    def test_custom_crud_and_duplicate_409(self, cc):
        b = _custom(cc, "Reels Instagram")
        assert b["kind"] == "custom" and b["status"] == "vazio" and b["content_chars"] == 0
        dup = cc.post(f"{BASE}/brains", json={"marca_id": MARCA, "name": "reels instagram"})
        assert dup.status_code == 409 and dup.json()["error"]["message"] == "Já existe um cérebro com esse nome"
        # a custom brain cannot take a Sistema brain's name either
        assert cc.post(f"{BASE}/brains", json={"marca_id": MARCA, "name": "Núcleo de Influência"}).status_code == 409
        r = cc.patch(f"{BASE}/brains/{b['id']}", json={"name": "  Reels  "})
        assert r.status_code == 200 and r.json()["data"]["name"] == "Reels"
        other = _custom(cc, "Outro")
        assert cc.patch(f"{BASE}/brains/{other['id']}", json={"name": "REELS"}).status_code == 409
        assert cc.delete(f"{BASE}/brains/{b['id']}").status_code == 204
        assert cc.get(f"{BASE}/brains/{b['id']}").status_code == 404

    @pytest.mark.parametrize("name", ["", "   ", "x" * 81])
    def test_bad_names_are_422(self, cc, name):
        assert cc.post(f"{BASE}/brains", json={"marca_id": MARCA, "name": name}).status_code == 422

    def test_unknown_body_fields_are_422(self, cc):
        assert cc.post(f"{BASE}/brains", json={"marca_id": MARCA, "name": "x", "kind": "sistema"}).status_code == 422

    def test_sistema_cannot_be_renamed_or_deleted(self, cc):
        s = _sistema(cc)
        r = cc.patch(f"{BASE}/brains/{s['id']}", json={"name": "Outro nome"})
        assert r.status_code == 409 and r.json()["error"]["message"] == "Cérebros do sistema não podem ser renomeados"
        r = cc.delete(f"{BASE}/brains/{s['id']}")
        assert r.status_code == 409 and r.json()["error"]["message"] == "Cérebros do sistema não podem ser excluídos"

    def test_detail_has_one_answer_per_question_and_the_template(self, cc):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "Gilson")
        d = _detail(cc, s["id"])
        assert d["template"]["slug"] == NUCLEO and len(d["answers"]) == 15
        assert d["answers"][0]["text"] == "Gilson" and d["answers"][1]["text"] == ""
        assert d["answers"][1]["review"]["status"] == "none" and d["answers"][0]["transcricao"] is None
        assert d["content"] == "" and d["content_version"] == 0 and d["imports"] == []
        assert _detail(cc, _custom(cc)["id"])["template"] is None

    def test_delete_removes_storage_objects_then_the_row(self, cc):
        b = _custom(cc)
        key = f"{ORG}/{MARCA}/{b['id']}/files/{uuid.uuid4()}-a.txt"
        import anyio
        anyio.run(lambda: cc.storage.put(bucket=CEREBRO_BUCKET, key=key, data=b"x"))
        cc.mock_supabase.from_("cs_brain_imports").insert({
            "id": str(uuid.uuid4()), "org_id": ORG, "brain_id": b["id"], "kind": "file",
            "filename": "a.txt", "storage_path": key, "status": "appended",
            "created_at": "2026-10-09T10:00:00+00:00",
        }).execute()
        assert cc.delete(f"{BASE}/brains/{b['id']}").status_code == 204
        assert not anyio.run(lambda: cc.storage.exists(bucket=CEREBRO_BUCKET, key=key))
        assert not [r for r in _rows(cc, "cs_brains") if r["id"] == b["id"]]

    def test_delete_with_failing_storage_is_surfaced_and_keeps_the_row(self, cc):
        b = _custom(cc)
        cc.mock_supabase.from_("cs_brain_imports").insert({
            "id": str(uuid.uuid4()), "org_id": ORG, "brain_id": b["id"], "kind": "file",
            "filename": "a.txt", "storage_path": "k", "status": "appended",
            "created_at": "2026-10-09T10:00:00+00:00",
        }).execute()
        cc._tc.app.dependency_overrides[get_cerebro_storage] = lambda: _BrokenStorage()
        r = cc.delete(f"{BASE}/brains/{b['id']}")
        assert r.status_code == 502
        assert [x for x in _rows(cc, "cs_brains") if x["id"] == b["id"]]


class TestContent:
    def test_put_bumps_version_and_a_stale_version_is_409(self, cc):
        b = _custom(cc)
        r = cc.put(f"{BASE}/brains/{b['id']}/content", json={"content": "# oi", "expected_version": 0})
        assert r.status_code == 200
        s = r.json()["data"]
        assert s["content_chars"] == 4 and s["status"] == "pronto"
        assert _row(cc, b["id"])["content_version"] == 1
        stale = cc.put(f"{BASE}/brains/{b['id']}/content", json={"content": "x", "expected_version": 0})
        assert stale.status_code == 409
        assert stale.json()["error"]["message"] == "O conteúdo do cérebro mudou enquanto você editava."
        assert _row(cc, b["id"])["content"] == "# oi"

    def test_over_limit_is_422(self, cc):
        b = _custom(cc)
        r = cc.put(f"{BASE}/brains/{b['id']}/content", json={"content": "x" * 200_001, "expected_version": 0})
        assert r.status_code == 422

    def test_blocked_while_synthesis_runs(self, cc):
        b = _custom(cc)
        cc.mock_supabase.from_("cs_brains").update({"synthesis_status": "processing"}).eq("id", b["id"]).execute()
        r = cc.put(f"{BASE}/brains/{b['id']}/content", json={"content": "x", "expected_version": 0})
        assert r.status_code == 409 and r.json()["error"]["message"] == "Aguarde a geração do cérebro terminar."
        assert _detail(cc, b["id"])["status"] == "processando"

    def test_append_rpc_bumps_version_separates_with_a_rule_and_refuses_over_limit(self, cc):
        b = _custom(cc)
        svc = cerebro_service.CerebroService(cc.mock_supabase, ORG)
        assert svc.append_block(b["id"], "primeiro") == 1
        assert svc.append_block(b["id"], "segundo") == 2
        assert _row(cc, b["id"])["content"] == "primeiro\n\n---\n\nsegundo"
        with pytest.raises(cerebro_service.CerebroError) as exc:
            svc.append_block(b["id"], "x" * 200_000)
        assert exc.value.status == 422 and "200.000" in exc.value.detail
        assert _row(cc, b["id"])["content"] == "primeiro\n\n---\n\nsegundo"


class TestAnswers:
    def test_autosave_creates_then_updates_one_row(self, cc):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "um")
        _answer(cc, s["id"], Q1, "dois")
        rows = _rows(cc, "cs_brain_answers")
        assert len(rows) == 1 and rows[0]["text"] == "dois"
        assert _brains(cc)[-1]["answered"] == 1

    def test_blank_answer_does_not_count_as_answered(self, cc):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "   ")
        assert _sistema(cc)["answered"] == 0

    def test_question_of_another_template_or_a_custom_brain_is_404(self, cc):
        s = _sistema(cc)
        other_q = question_id("historia-de-criacao", 1)
        assert cc.put(f"{BASE}/brains/{s['id']}/answers/{other_q}", json={"text": "x"}).status_code == 404
        assert cc.put(f"{BASE}/brains/{s['id']}/answers/nope.99", json={"text": "x"}).status_code == 404
        assert cc.put(f"{BASE}/brains/{_custom(cc)['id']}/answers/{Q1}", json={"text": "x"}).status_code == 404

    def test_too_long_answer_is_422(self, cc):
        s = _sistema(cc)
        assert cc.put(f"{BASE}/brains/{s['id']}/answers/{Q1}", json={"text": "x" * 10_001}).status_code == 422

    def test_reset_deletes_answers_and_leaves_content(self, cc):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "a")
        _answer(cc, s["id"], Q2, "b")
        cc.put(f"{BASE}/brains/{s['id']}/content", json={"content": "keep", "expected_version": 0})
        assert cc.post(f"{BASE}/brains/{s['id']}/answers/reset", json={}).status_code == 422
        r = cc.post(f"{BASE}/brains/{s['id']}/answers/reset", json={"confirm": True})
        assert r.status_code == 200 and r.json()["data"] == {"deleted": 2}
        assert _rows(cc, "cs_brain_answers") == [] and _row(cc, s["id"])["content"] == "keep"


def _review_reply(*entries):
    return json.dumps([
        {"question_id": q, "verdict": v, "reason": r, "improved": i} for q, v, r, i in entries
    ])


class TestReview:
    def test_review_marks_done_with_verdict_reason_and_improved(self, cc):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "Gilson, corretor")
        _answer(cc, s["id"], Q2, "ainda não")
        cc.llm_reply = _review_reply((Q1, "approved", "Boa.", None), (Q2, "rejected", "Muito curta.", "Ainda não tenho um termo."))
        r = cc.post(f"{BASE}/brains/{s['id']}/review", json={})
        assert r.status_code == 202 and r.json()["data"] == {"queued": 2}
        d = _detail(cc, s["id"])
        a1, a2 = d["answers"][0]["review"], d["answers"][1]["review"]
        assert (a1["status"], a1["verdict"], a1["reason"]) == ("done", "approved", "Boa.")
        assert (a2["status"], a2["verdict"], a2["improved"]) == ("done", "rejected", "Ainda não tenho um termo.")
        system, user, org = cc.llm_calls[0]
        assert "Gilson, corretor" in user and "Qual é o seu nome" in user and org == ORG
        assert len(cc.llm_calls) == 1   # one call per request

    def test_question_ids_filter_and_nothing_to_review_is_422(self, cc):
        s = _sistema(cc)
        r = cc.post(f"{BASE}/brains/{s['id']}/review", json={})
        assert r.status_code == 422 and r.json()["error"]["message"] == "Responda ao menos uma pergunta"
        _answer(cc, s["id"], Q1, "a")
        _answer(cc, s["id"], Q2, "b")
        cc.llm_reply = _review_reply((Q2, "approved", "ok", None))
        r = cc.post(f"{BASE}/brains/{s['id']}/review", json={"question_ids": [Q2, "nope.1"]})
        assert r.json()["data"] == {"queued": 1}
        assert _detail(cc, s["id"])["answers"][0]["review"]["status"] == "none"
        assert cc.post(f"{BASE}/brains/{s['id']}/review", json={"question_ids": ["nope.1"]}).status_code == 422

    def test_missing_id_errors_only_that_answer_unknown_ids_ignored(self, cc):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "a")
        _answer(cc, s["id"], Q2, "b")
        cc.llm_reply = _review_reply((Q1, "approved", "ok", None), ("zzz.01", "approved", "x", None))
        cc.post(f"{BASE}/brains/{s['id']}/review", json={})
        reviews = [a["review"] for a in _detail(cc, s["id"])["answers"][:2]]
        assert reviews[0]["status"] == "done"
        assert reviews[1]["status"] == "error" and reviews[1]["error"] == "A IA não avaliou esta resposta."

    @pytest.mark.parametrize("reply", ["isto não é json", "{}"])
    def test_non_json_reply_errors_every_pending_answer(self, cc, reply):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "a")
        _answer(cc, s["id"], Q2, "b")
        cc.llm_reply = reply
        cc.post(f"{BASE}/brains/{s['id']}/review", json={})
        reviews = [a["review"] for a in _detail(cc, s["id"])["answers"][:2]]
        assert [r["status"] for r in reviews] == ["error", "error"]
        assert reviews[0]["error"] == "Falha ao revisar com IA"

    def test_llm_exception_errors_every_pending_answer(self, cc):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "a")
        cc.llm_error = RuntimeError("boom")
        assert cc.post(f"{BASE}/brains/{s['id']}/review", json={}).status_code == 202
        r = _detail(cc, s["id"])["answers"][0]["review"]
        assert r["status"] == "error" and r["error"] == "Falha ao revisar com IA"

    def test_editing_the_answer_resets_the_review_but_resaving_the_same_text_does_not(self, cc):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "a")
        cc.llm_reply = _review_reply((Q1, "rejected", "vago", "melhor"))
        cc.post(f"{BASE}/brains/{s['id']}/review", json={})
        _answer(cc, s["id"], Q1, "a")
        assert _detail(cc, s["id"])["answers"][0]["review"]["status"] == "done"
        _answer(cc, s["id"], Q1, "a, editada")
        r = _detail(cc, s["id"])["answers"][0]["review"]
        assert r["status"] == "none" and r["verdict"] is None and r["improved"] is None

    def test_late_result_after_an_edit_is_dropped(self, cc):
        """The review in flight must not overwrite a reset caused by a newer edit."""
        import anyio
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "a")
        svc = cerebro_service.CerebroService(cc.mock_supabase, ORG)
        targets = svc.request_review(s["id"], None)
        _answer(cc, s["id"], Q1, "a2")          # user edits while the review is "running"

        async def llm(system, user, org):
            return _review_reply((Q1, "approved", "ok", None))

        anyio.run(svc.run_review, s["id"], targets, llm)
        assert _detail(cc, s["id"])["answers"][0]["review"]["status"] == "none"

    def test_accept_replaces_text_with_improved_dismiss_keeps_it(self, cc):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "a")
        _answer(cc, s["id"], Q2, "b")
        cc.llm_reply = _review_reply((Q1, "rejected", "vago", "A melhorada"), (Q2, "rejected", "vago", "B melhorada"))
        cc.post(f"{BASE}/brains/{s['id']}/review", json={})
        r = cc.post(f"{BASE}/brains/{s['id']}/answers/{Q1}/suggestion", json={"action": "accept"})
        assert r.status_code == 200
        a = r.json()["data"]
        assert a["text"] == "A melhorada" and a["review"]["decision"] == "accepted" and a["review"]["status"] == "done"
        r = cc.post(f"{BASE}/brains/{s['id']}/answers/{Q2}/suggestion", json={"action": "dismiss"})
        a = r.json()["data"]
        assert a["text"] == "b" and a["review"]["decision"] == "dismissed"
        # the accepted answer keeps its review (sha moved with the accepted text)
        _answer(cc, s["id"], Q1, "A melhorada")
        assert _detail(cc, s["id"])["answers"][0]["review"]["decision"] == "accepted"

    def test_suggestion_without_a_finished_review_is_409(self, cc):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "a")
        r = cc.post(f"{BASE}/brains/{s['id']}/answers/{Q1}/suggestion", json={"action": "accept"})
        assert r.status_code == 409
        assert cc.post(f"{BASE}/brains/{s['id']}/answers/{Q3}/suggestion", json={"action": "accept"}).status_code == 404
        assert cc.post(f"{BASE}/brains/{s['id']}/answers/{Q1}/suggestion", json={"action": "boh"}).status_code == 422


DOC = "### Perfil Profissional\nSou Gilson.\n\n### Elementos para conteúdo\n- Público: \"Corretores\""


class TestSynthesis:
    def _setup(self, cc, rejected=False):
        s = _sistema(cc)
        _answer(cc, s["id"], Q1, "Gilson")
        if rejected:
            cc.llm_reply = _review_reply((Q1, "rejected", "vago", None))
            cc.post(f"{BASE}/brains/{s['id']}/review", json={})
        return s

    def _synth(self, cc, s, mode="replace", version=0):
        return cc.post(f"{BASE}/brains/{s['id']}/synthesize", json={"mode": mode, "expected_version": version})

    def test_replace_writes_the_document_bumps_version_and_includes_rejected_answers(self, cc):
        s = self._setup(cc, rejected=True)
        cc.llm_calls.clear()
        cc.llm_reply = DOC
        r = self._synth(cc, s)
        assert r.status_code == 202 and r.json()["data"]["brain"]["synthesis_status"] == "processing"
        d = _detail(cc, s["id"])
        assert d["content"] == DOC and d["content_version"] == 1
        assert d["synthesis_status"] == "idle" and d["synthesis_error"] is None and d["synthesized_at"]
        assert d["status"] == "pronto"
        system, user, org = cc.llm_calls[0]
        assert "Perfil Profissional" in system and "Gilson" in user

    def test_unreviewed_answers_are_enough(self, cc):
        s = self._setup(cc)
        cc.llm_reply = DOC
        assert self._synth(cc, s).status_code == 202
        assert _row(cc, s["id"])["content"] == DOC

    def test_zero_answers_is_422_and_custom_is_409(self, cc):
        s = _sistema(cc)
        r = self._synth(cc, s)
        assert r.status_code == 422 and r.json()["error"]["message"] == "Responda ao menos uma pergunta"
        assert self._synth(cc, _custom(cc)).status_code == 409
        assert _row(cc, s["id"])["synthesis_status"] == "idle"

    def test_append_mode_goes_through_cs_brain_append(self, cc):
        s = self._setup(cc)
        cc.put(f"{BASE}/brains/{s['id']}/content", json={"content": "antes", "expected_version": 0})
        cc.llm_reply = DOC
        assert self._synth(cc, s, "append", 1).status_code == 202
        # the contract fake of `cs_brain_append` (tests/support/rpc_fakes.py) did the append
        row = _row(cc, s["id"])
        assert row["content"] == "antes\n\n---\n\n" + DOC and row["content_version"] == 2
        assert row["synthesis_status"] == "idle"

    def test_llm_failure_leaves_content_byte_identical_and_sets_error(self, cc):
        s = self._setup(cc)
        cc.put(f"{BASE}/brains/{s['id']}/content", json={"content": "meu texto", "expected_version": 0})
        cc.llm_error = RuntimeError("boom")
        assert self._synth(cc, s, "replace", 1).status_code == 202
        row = _row(cc, s["id"])
        assert row["content"] == "meu texto" and row["content_version"] == 1
        assert row["synthesis_status"] == "error" and row["synthesis_error"] == MSG_SYNTH_FAIL
        # the user can simply try again
        cc.llm_error, cc.llm_reply = None, DOC
        assert self._synth(cc, s, "replace", 1).status_code == 202
        assert _row(cc, s["id"])["content"] == DOC

    def test_empty_llm_reply_never_blanks_the_brain(self, cc):
        s = self._setup(cc)
        cc.put(f"{BASE}/brains/{s['id']}/content", json={"content": "meu texto", "expected_version": 0})
        cc.llm_reply = "   "
        self._synth(cc, s, "replace", 1)
        row = _row(cc, s["id"])
        assert row["content"] == "meu texto" and row["synthesis_status"] == "error"

    def test_version_moved_mid_run_is_an_error_with_content_untouched(self, cc):
        """An import/extraction appended while the LLM ran: replace must not clobber it."""
        import anyio
        s = self._setup(cc)
        svc = cerebro_service.CerebroService(cc.mock_supabase, ORG)
        svc.start_synthesis(s["id"], "replace", 0)

        async def llm(system, user, org):
            svc.append_block(s["id"], "anexo chegou")   # concurrent append bumps the version
            return DOC

        anyio.run(svc.run_synthesis, s["id"], "replace", 0, llm)
        row = _row(cc, s["id"])
        assert row["content"] == "anexo chegou"
        assert row["synthesis_status"] == "error"
        assert row["synthesis_error"] == "O conteúdo mudou durante a geração; gere novamente."

    def test_concurrent_synthesis_is_409(self, cc):
        s = self._setup(cc)
        cc.mock_supabase.from_("cs_brains").update({"synthesis_status": "processing"}).eq("id", s["id"]).execute()
        r = self._synth(cc, s)
        assert r.status_code == 409 and r.json()["error"]["message"] == "Aguarde a geração do cérebro terminar."

    def test_stale_expected_version_is_409(self, cc):
        s = self._setup(cc)
        assert self._synth(cc, s, "replace", 5).status_code == 409
        assert _row(cc, s["id"])["synthesis_status"] == "idle"


class TestPerfil:
    def test_empty_then_saved_then_replaced(self, cc):
        r = cc.get(f"{BASE}/perfil", params={"marca_id": MARCA})
        assert r.status_code == 200 and r.json()["data"] == {"marca_id": MARCA, "bio": "", "updated_at": None}
        r = cc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "bio": "Empresário do mercado imobiliário"})
        assert r.status_code == 200 and r.json()["data"]["bio"] == "Empresário do mercado imobiliário"
        cc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "bio": "nova"})
        assert len(_rows(cc, "cs_marca_perfil")) == 1
        assert cc.get(f"{BASE}/perfil", params={"marca_id": MARCA}).json()["data"]["bio"] == "nova"

    def test_bio_over_5000_is_422(self, cc):
        assert cc.put(f"{BASE}/perfil", json={"marca_id": MARCA, "bio": "x" * 5001}).status_code == 422


class TestImportsList:
    def test_newest_first_and_limit(self, cc):
        b = _custom(cc)
        for i in range(3):
            cc.mock_supabase.from_("cs_brain_imports").insert({
                "id": str(uuid.uuid4()), "org_id": ORG, "brain_id": b["id"], "kind": "file",
                "filename": f"f{i}.txt", "status": "appended", "chars_appended": 10,
                "created_at": f"2026-10-09T10:0{i}:00+00:00",
            }).execute()
        data = cc.get(f"{BASE}/brains/{b['id']}/imports").json()["data"]
        assert [i["filename"] for i in data] == ["f2.txt", "f1.txt", "f0.txt"]
        assert len(cc.get(f"{BASE}/brains/{b['id']}/imports", params={"limit": 2}).json()["data"]) == 2
        assert cc.get(f"{BASE}/brains/{b['id']}/imports", params={"limit": 51}).status_code == 422

    def test_processing_import_makes_the_brain_processando(self, cc):
        b = _custom(cc)
        cc.mock_supabase.from_("cs_brain_imports").insert({
            "id": str(uuid.uuid4()), "org_id": ORG, "brain_id": b["id"], "kind": "file",
            "filename": "f.pdf", "status": "processing", "created_at": cerebro_service._iso(),
        }).execute()
        assert _detail(cc, b["id"])["status"] == "processando"


class TestIsolation:
    def test_cross_org_marca_is_404_everywhere(self, cc):
        m = OTHER_MARCA
        assert cc.get(f"{BASE}/brains", params={"marca_id": m}).status_code == 404
        assert cc.post(f"{BASE}/brains", json={"marca_id": m, "name": "x"}).status_code == 404
        assert cc.get(f"{BASE}/perfil", params={"marca_id": m}).status_code == 404
        assert cc.put(f"{BASE}/perfil", json={"marca_id": m, "bio": "x"}).status_code == 404
        assert _rows(cc, "cs_brains") == []          # nothing was created for the foreign marca

    def test_other_orgs_brain_is_404_everywhere(self, cc):
        b = _foreign_brain(cc)
        p = f"{BASE}/brains/{b}"
        assert cc.get(p).status_code == 404
        assert cc.patch(p, json={"name": "x"}).status_code == 404
        assert cc.delete(p).status_code == 404
        assert cc.put(f"{p}/content", json={"content": "x", "expected_version": 0}).status_code == 404
        assert cc.put(f"{p}/answers/{Q1}", json={"text": "x"}).status_code == 404
        assert cc.post(f"{p}/answers/reset", json={"confirm": True}).status_code == 404
        assert cc.post(f"{p}/review", json={}).status_code == 404
        assert cc.post(f"{p}/answers/{Q1}/suggestion", json={"action": "accept"}).status_code == 404
        assert cc.post(f"{p}/synthesize", json={"mode": "replace", "expected_version": 0}).status_code == 404
        assert cc.get(f"{p}/imports").status_code == 404
        assert _row(cc, b)["content"] == "segredo"


class TestAuth:
    @pytest.mark.parametrize("method,path,kw", [
        ("get", "/templates", {}),
        ("get", f"/brains?marca_id={MARCA}", {}),
        ("post", "/brains", {"json": {"marca_id": MARCA, "name": "x"}}),
        ("get", f"/brains/{uuid.uuid4()}", {}),
        ("patch", f"/brains/{uuid.uuid4()}", {"json": {"name": "x"}}),
        ("delete", f"/brains/{uuid.uuid4()}", {}),
        ("put", f"/brains/{uuid.uuid4()}/content", {"json": {"content": "x", "expected_version": 0}}),
        ("put", f"/brains/{uuid.uuid4()}/answers/{Q1}", {"json": {"text": "x"}}),
        ("post", f"/brains/{uuid.uuid4()}/answers/reset", {"json": {"confirm": True}}),
        ("post", f"/brains/{uuid.uuid4()}/review", {"json": {}}),
        ("post", f"/brains/{uuid.uuid4()}/answers/{Q1}/suggestion", {"json": {"action": "accept"}}),
        ("post", f"/brains/{uuid.uuid4()}/synthesize", {"json": {"mode": "replace", "expected_version": 0}}),
        ("get", f"/brains/{uuid.uuid4()}/imports", {}),
        ("get", f"/perfil?marca_id={MARCA}", {}),
        ("put", "/perfil", {"json": {"marca_id": MARCA, "bio": "x"}}),
    ])
    def test_unauthenticated_is_401(self, client, method, path, kw):
        r = getattr(client._tc, method)(BASE + path, **kw)
        assert r.status_code == 401, (path, r.status_code, r.text)
