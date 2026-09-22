"""Wave-1 security review — BE-DEF findings (H1, H2, M1, M3, L1, L2, L7, L8)
plus the atomic ``replace_draft_bundle`` the importer calls.

Router tests ride the shared ``studio`` harness (real FastAPI app, Fake
store/gate/catalog bound through ``dependency_overrides``); store tests hit
``FakeStudioDefinitionStore`` directly and pin the Real store's RPC shapes
with the recording Supabase-client double.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.stores.studio_definitions import (
    FakeStudioDefinitionStore,
    SectionInput,
    StudioConflict,
    SupabaseStudioDefinitionStore,
    VersionImmutable,
)
from app.studio.models import LIMITS, GateRun

BASE = "/api/studio/agents"
ORG = UUID("11111111-1111-1111-1111-111111111111")
USER = UUID("33333333-3333-3333-3333-333333333333")
SECTIONS = {"secoes": [
    {"chave": "identidade", "titulo": "Identidade", "ordem": 10, "conteudo": "Você é estrategista.", "ativo": True},
    {"chave": "regras", "titulo": "Regras", "ordem": 20, "conteudo": "Seja direta.", "ativo": True},
]}
REASON = "Publicação urgente aprovada pela coordenação."


def _publishable(studio, key="isa"):
    assert studio.post(BASE, json={"key": key, "nome": "Isa"}).status_code == 201
    resp = studio.put(f"{BASE}/{key}/draft/sections", json=SECTIONS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _gate(studio, draft, *, score=0.9, completa=True, total=3, register=True):
    run = GateRun(
        id=uuid4(), score=score, limiar=0.8, compiled_hash=draft["compiled_hash"], status="concluida",
        completa=completa, total=total,
    )
    studio.gate.set_run(studio.org_id, UUID(draft["id"]), run)
    if register:
        studio.store.register_eval_run(
            studio.org_id, UUID(draft["id"]), run_id=run.id, score=score,
            compiled_hash=draft["compiled_hash"], completa=completa, total=total,
        )
    return run


def _agent_id(studio, key="isa"):
    return studio.store.get_agent(studio.org_id, key).id


# ── H1 — the gate only accepts a COMPLETE run ───────────────────────────────


class TestGateNeedsCompleteRun:
    def test_subset_run_never_passes(self, studio):
        draft = _publishable(studio)
        _gate(studio, draft, completa=False)
        resp = studio.post(f"{BASE}/isa/draft/publish", json={})
        assert resp.status_code == 409
        body = resp.json()
        assert body["code"] == "eval_required"
        assert body["ultima_execucao"]["completa"] is False

    def test_empty_run_never_passes(self, studio):
        draft = _publishable(studio)
        _gate(studio, draft, total=0)
        assert studio.post(f"{BASE}/isa/draft/publish", json={}).json()["code"] == "eval_required"

    def test_db_recheck_refuses_when_no_active_case_is_left(self, studio):
        """The Python gate passes; the DB function's own re-check (agent
        still has >= 1 active case) refuses."""
        draft = _publishable(studio)
        run = _gate(studio, draft, register=False)
        studio.store.register_eval_run(
            studio.org_id, UUID(draft["id"]), run_id=run.id, score=0.9,
            compiled_hash=draft["compiled_hash"], active_cases=0,
        )
        resp = studio.post(f"{BASE}/isa/draft/publish", json={})
        assert resp.status_code == 409
        assert resp.json()["code"] == "eval_required"

    def test_db_recheck_refuses_a_run_it_cannot_see(self, studio):
        draft = _publishable(studio)
        _gate(studio, draft, register=False)  # Python gate says yes, DB has no such run
        resp = studio.post(f"{BASE}/isa/draft/publish", json={})
        assert resp.status_code == 409
        assert resp.json()["code"] == "eval_required"


# ── H2 — threshold floor, snapshots, audit log ──────────────────────────────


class TestThresholdGames:
    def test_limiar_floor_422(self, studio):
        studio.post(BASE, json={"key": "isa", "nome": "Isa"})
        resp = studio.patch(f"{BASE}/isa", json={"publicacao_limiar": 0.49})
        assert resp.status_code == 422
        assert studio.patch(f"{BASE}/isa", json={"publicacao_limiar": 0.5}).status_code == 200

    def test_store_floor(self):
        store = FakeStudioDefinitionStore()
        store.create_studio_agent(ORG, "isa", "Isa", None)
        with pytest.raises(ValueError):
            store.update_agent(ORG, "isa", {"publicacao_limiar": 0.1})

    def test_publish_snapshots_limiar_and_score(self, studio):
        draft = _publishable(studio)
        _gate(studio, draft, score=0.91)
        body = studio.post(f"{BASE}/isa/draft/publish", json={}).json()
        assert body["limiar_aplicado"] == pytest.approx(0.8)
        assert body["eval_score"] == pytest.approx(0.91)
        # Lowering the threshold later never rewrites what the publish was held to.
        studio.patch(f"{BASE}/isa", json={"publicacao_limiar": 0.6})
        again = studio.get(f"{BASE}/isa/versions/{body['id']}").json()
        assert again["limiar_aplicado"] == pytest.approx(0.8)

    def test_override_publish_has_no_score_snapshot(self, studio):
        _publishable(studio)
        body = studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": REASON}).json()
        assert body["eval_score"] is None
        assert body["limiar_aplicado"] == pytest.approx(0.8)

    def test_threshold_change_is_audited_with_actor(self, studio):
        studio.post(BASE, json={"key": "isa", "nome": "Isa"})
        studio.patch(f"{BASE}/isa", json={"publicacao_limiar": 0.95})
        studio.patch(f"{BASE}/isa", json={"nome": "Isa 2"})  # not a threshold change
        log = studio.store.list_audit_log(studio.org_id, _agent_id(studio))
        assert [a.acao for a in log] == ["limiar_alterado"]
        assert log[0].actor == studio.user_id
        assert log[0].antes == {"publicacao_limiar": 0.8}
        assert log[0].depois == {"publicacao_limiar": 0.95}

    def test_publish_override_and_discard_are_audited(self, studio):
        draft = _publishable(studio)
        _gate(studio, draft)
        studio.post(f"{BASE}/isa/draft/publish", json={})
        studio.post(f"{BASE}/isa/draft", json={})
        studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": REASON})
        studio.post(f"{BASE}/isa/draft", json={})
        assert studio.delete(f"{BASE}/isa/draft").status_code == 204
        log = studio.store.list_audit_log(studio.org_id, _agent_id(studio))
        assert [a.acao for a in log] == ["rascunho_descartado", "publicado_override", "publicado"]
        assert all(a.actor == studio.user_id for a in log)
        assert log[1].depois["override_reason"] == REASON
        assert log[1].antes["versao"] == 1  # the version it superseded
        assert log[2].depois["eval_score"] == pytest.approx(0.9)


# ── M1 — publish race ───────────────────────────────────────────────────────


class TestPublishRace:
    def test_child_write_nulls_the_draft_hash(self):
        store = FakeStudioDefinitionStore()
        agent = store.create_studio_agent(ORG, "isa", "Isa", None)
        d = store.create_draft(ORG, agent.id, None, USER)
        store.set_compiled_hash(ORG, d.id, "sha256:" + "a" * 64)
        store.create_skill(ORG, d.id, nome="s", descricao="d", corpo="c")
        assert store.get_version(ORG, d.id).compiled_hash is None

    def test_setting_change_nulls_the_hash_but_notas_does_not(self):
        store = FakeStudioDefinitionStore()
        agent = store.create_studio_agent(ORG, "isa", "Isa", None)
        d = store.create_draft(ORG, agent.id, None, USER)
        store.set_compiled_hash(ORG, d.id, "sha256:" + "a" * 64)
        store.update_draft(ORG, d.id, {"notas": "n"})
        assert store.get_version(ORG, d.id).compiled_hash is not None
        store.update_draft(ORG, d.id, {"model": "claude-sonnet-5"})
        assert store.get_version(ORG, d.id).compiled_hash is None

    def test_publish_refuses_a_hash_the_row_no_longer_has(self):
        store = FakeStudioDefinitionStore()
        agent = store.create_studio_agent(ORG, "isa", "Isa", None)
        d = store.create_draft(ORG, agent.id, None, USER)
        h = "sha256:" + "a" * 64
        store.set_compiled_hash(ORG, d.id, h)
        # A write lands between the gate check and the publish call.
        store.replace_sections(ORG, d.id, [SectionInput(chave="x", titulo="X", ordem=1, conteudo="x")])
        with pytest.raises(StudioConflict) as exc:
            store.publish_version(ORG, d.id, USER, None, REASON, expected_hash=h, texto="T", manifest=[])
        assert exc.value.code == "draft_changed"
        assert store.get_version(ORG, d.id).status == "rascunho"

    def test_stale_stamp_is_refused_by_compare_and_set(self):
        store = FakeStudioDefinitionStore()
        agent = store.create_studio_agent(ORG, "isa", "Isa", None)
        d = store.create_draft(ORG, agent.id, None, USER)
        read = store.get_version(ORG, d.id)
        store.create_skill(ORG, d.id, nome="s", descricao="d", corpo="c")  # concurrent write
        with pytest.raises(StudioConflict) as exc:
            store.set_compiled_hash(ORG, d.id, "sha256:" + "b" * 64, expected_updated_at=read.updated_at)
        assert exc.value.code == "draft_changed"

    def test_draft_save_path_restamps_after_its_write(self, studio):
        _publishable(studio)
        body = studio.post(f"{BASE}/isa/draft/skills", json={"nome": "s", "descricao": "d", "corpo": "c"})
        assert body.status_code == 201
        draft = studio.store.get_draft(studio.org_id, _agent_id(studio))
        assert draft.compiled_hash is not None and draft.compiled_hash.startswith("sha256:")

    def test_router_passes_the_gate_checked_hash(self, studio):
        """A write that lands between the gate check and the publish RPC →
        409 draft_changed. The race is injected through the DI seam: a Fake
        subclass whose publish first performs the concurrent write."""

        class RacingStore(FakeStudioDefinitionStore):
            def publish_version(self, org_id, version_id, *args, **kwargs):
                self.replace_sections(
                    org_id, version_id, [SectionInput(chave="novo", titulo="Novo", ordem=1, conteudo="injetado")],
                )
                return super().publish_version(org_id, version_id, *args, **kwargs)

        studio.store = RacingStore()  # the harness's store override reads this attribute per request
        draft = _publishable(studio)
        _gate(studio, draft)
        resp = studio.post(f"{BASE}/isa/draft/publish", json={})
        assert resp.status_code == 409
        assert resp.json()["code"] == "draft_changed"
        assert studio.store.get_active_version(studio.org_id, _agent_id(studio)) is None


# ── M3 — size caps ──────────────────────────────────────────────────────────


class TestCaps:
    @pytest.mark.parametrize(
        "method, path, body",
        [
            ("put", "/draft/sections", {"secoes": [{**SECTIONS["secoes"][0], "conteudo": "x" * (LIMITS["section.conteudo"] + 1)}]}),
            ("post", "/draft/skills", {"nome": "s", "descricao": "d", "corpo": "x" * (LIMITS["skill.corpo"] + 1)}),
            ("post", "/clients", {"slug": "c", "nome": "C", "resumo": "x" * (LIMITS["client.resumo"] + 1)}),
        ],
    )
    def test_http_caps_422(self, studio, method, path, body):
        studio.post(BASE, json={"key": "isa", "nome": "Isa"})
        resp = getattr(studio, method)(f"{BASE}/isa{path}", json=body)
        assert resp.status_code == 422

    def test_skill_file_and_entry_caps_422(self, studio):
        studio.post(BASE, json={"key": "isa", "nome": "Isa"})
        skill = studio.post(f"{BASE}/isa/draft/skills", json={"nome": "s", "descricao": "d", "corpo": "c"}).json()
        big = "x" * (LIMITS["skill_file.conteudo"] + 1)
        resp = studio.put(f"{BASE}/isa/draft/skills/{skill['id']}/files", json={"caminho": "a.md", "conteudo": big})
        assert resp.status_code == 422
        client = studio.post(f"{BASE}/isa/clients", json={"slug": "c", "nome": "C"}).json()
        for body in (
            {"tipo": "nota", "titulo": "x" * (LIMITS["entry.titulo"] + 1)},
            {"tipo": "nota", "titulo": "t", "conteudo": "x" * (LIMITS["entry.conteudo"] + 1)},
        ):
            assert studio.post(f"{BASE}/isa/clients/{client['id']}/entries", json=body).status_code == 422

    def test_store_caps_without_the_http_layer(self):
        store = FakeStudioDefinitionStore()
        agent = store.create_studio_agent(ORG, "isa", "Isa", None)
        d = store.create_draft(ORG, agent.id, None, USER)
        with pytest.raises(ValueError):
            store.replace_sections(ORG, d.id, [SectionInput(chave="a", titulo="A", ordem=1, conteudo="x" * 40_001)])
        with pytest.raises(ValueError):
            store.create_client(ORG, agent.id, slug="c", nome="C", resumo="x" * 8_001)

    def test_active_entry_cap_409(self, studio):
        studio.post(BASE, json={"key": "isa", "nome": "Isa"})
        client = studio.post(f"{BASE}/isa/clients", json={"slug": "c", "nome": "C"}).json()
        cid = UUID(client["id"])
        for i in range(LIMITS["client.active_entries"]):
            studio.store.create_client_entry(studio.org_id, cid, tipo="nota", titulo=f"n{i}")
        resp = studio.post(f"{BASE}/isa/clients/{client['id']}/entries", json={"tipo": "nota", "titulo": "201"})
        assert resp.status_code == 409
        assert resp.json()["code"] == "client_entries_cap"
        # archived entries don't count
        arch = studio.post(
            f"{BASE}/isa/clients/{client['id']}/entries", json={"tipo": "nota", "titulo": "a", "status": "arquivado"},
        )
        assert arch.status_code == 201
        reactivate = studio.patch(f"{BASE}/isa/clients/{client['id']}/entries/{arch.json()['id']}", json={"status": "ativo"})
        assert reactivate.status_code == 409


# ── L1 — override reason ────────────────────────────────────────────────────


class TestOverrideReason:
    @pytest.mark.parametrize("reason", ["   " + "x" * 19 + "   ", "a b c d e f g h i j k l m n o p q r s", "\n" * 30])
    def test_whitespace_padding_does_not_count(self, studio, reason):
        _publishable(studio)
        assert studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": reason}).status_code == 422

    def test_reason_is_stored_stripped(self, studio):
        _publishable(studio)
        body = studio.post(f"{BASE}/isa/draft/publish", json={"override_reason": f"  {REASON}  "}).json()
        assert body["publish_override_reason"] == REASON

    def test_store_refuses_a_short_reason(self):
        store = FakeStudioDefinitionStore()
        agent = store.create_studio_agent(ORG, "isa", "Isa", None)
        d = store.create_draft(ORG, agent.id, None, USER)
        h = "sha256:" + "a" * 64
        store.set_compiled_hash(ORG, d.id, h)
        with pytest.raises(StudioConflict) as exc:
            store.publish_version(ORG, d.id, USER, None, " " * 25, expected_hash=h, texto="T", manifest=[])
        assert exc.value.code == "eval_required"


# ── L2 — compiled prompts erasure ───────────────────────────────────────────


class TestCompiledPromptErasure:
    def test_erase_removes_only_that_clients_prompts(self):
        store = FakeStudioDefinitionStore()
        agent = store.create_studio_agent(ORG, "isa", "Isa", None)
        d = store.create_draft(ORG, agent.id, None, USER)
        c1, c2 = uuid4(), uuid4()
        store.save_compiled_prompt(ORG, hash="sha256:" + "1" * 64, version_id=d.id, client_id=c1, texto="a", manifest=[])
        store.save_compiled_prompt(ORG, hash="sha256:" + "2" * 64, version_id=d.id, client_id=c2, texto="b", manifest=[])
        assert store.erase_client_compiled_prompts(ORG, c1) == 1
        assert store.get_compiled_prompt(ORG, "sha256:" + "2" * 64).texto == "b"


# ── L7 — GET compiled never writes ──────────────────────────────────────────


class TestCompiledReadIsPure:
    def test_get_compiled_does_not_touch_the_stored_hash(self, studio):
        from app.studio.models import CollectionSummary

        _publishable(studio)
        agent_id = _agent_id(studio)
        before = studio.store.get_draft(studio.org_id, agent_id)
        studio.catalog.set(studio.org_id, agent_id, [
            CollectionSummary(slug="k", nome="K", tag=None, descricao="", doc_count=1),
        ])
        body = studio.get(f"{BASE}/isa/versions/{before.id}/compiled").json()
        after = studio.store.get_draft(studio.org_id, agent_id)
        assert body["hash"] != before.compiled_hash
        assert (after.compiled_hash, after.updated_at) == (before.compiled_hash, before.updated_at)


# ── L8 — discard after eval runs ────────────────────────────────────────────


class TestDiscardWithRuns:
    def test_draft_with_eval_runs_can_be_discarded(self, studio):
        draft = _publishable(studio)
        _gate(studio, draft)
        assert studio.delete(f"{BASE}/isa/draft").status_code == 204
        assert studio.store._eval_runs == {}


# ── replace_draft_bundle (importer seam) ────────────────────────────────────


class TestReplaceDraftBundle:
    def _draft(self):
        store = FakeStudioDefinitionStore()
        agent = store.create_studio_agent(ORG, "isa", "Isa", None)
        return store, store.create_draft(ORG, agent.id, None, USER)

    def test_replaces_sections_skills_and_files(self):
        store, d = self._draft()
        store.replace_sections(ORG, d.id, [SectionInput(chave="velha", titulo="V", ordem=1, conteudo="v")])
        store.create_skill(ORG, d.id, nome="velha", descricao="d", corpo="c")
        res = store.replace_draft_bundle(ORG, d.id, [
            {"chave": "nova", "titulo": "N", "ordem": 1, "conteudo": "n", "ativo": True},
        ], [
            {"nome": "roteiro", "descricao": "R", "corpo": "passos", "ordem": 0, "ativo": True,
             "arquivos": [{"caminho": "references/a.md", "titulo": "A", "conteudo": "aaa"}]},
        ])
        assert (res.secoes, res.skills, res.arquivos) == (1, 1, 1)
        assert [s.chave for s in store.list_sections(ORG, d.id)] == ["nova"]
        assert [s.nome for s in store.list_skills(ORG, d.id)] == ["roteiro"]
        assert [f.caminho for f in store.list_version_skill_files(ORG, d.id)] == ["references/a.md"]

    @pytest.mark.parametrize(
        "secoes, skills, code",
        [
            ([{"chave": "a", "titulo": "A", "ordem": 1}, {"chave": "a", "titulo": "B", "ordem": 2}], [], "chave_conflict"),
            ([], [{"nome": "s", "descricao": "d"}, {"nome": "s", "descricao": "d"}], "skill_exists"),
            ([], [{"nome": "s", "descricao": "d", "arquivos": [{"caminho": "a.md"}, {"caminho": "a.md"}]}], "caminho_conflict"),
        ],
    )
    def test_a_bad_bundle_changes_nothing(self, secoes, skills, code):
        store, d = self._draft()
        store.replace_sections(ORG, d.id, [SectionInput(chave="keep", titulo="K", ordem=1, conteudo="k")])
        with pytest.raises(StudioConflict) as exc:
            store.replace_draft_bundle(ORG, d.id, secoes, skills)
        assert exc.value.code == code
        assert [s.chave for s in store.list_sections(ORG, d.id)] == ["keep"]

    def test_published_version_is_immutable(self):
        store, d = self._draft()
        h = "sha256:" + "a" * 64
        store.set_compiled_hash(ORG, d.id, h)
        store.publish_version(ORG, d.id, USER, None, REASON, expected_hash=h, texto="T", manifest=[])
        with pytest.raises(VersionImmutable):
            store.replace_draft_bundle(ORG, d.id, [], [])


# ── Real store: RPC shapes + error mapping of the new functions ─────────────


class _APIError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, rec, table, rpc=None):
        self._rec, self._table, self._rpc, self.calls = rec, table, rpc, []

    def __getattr__(self, name):
        def _chain(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self
        return _chain

    def execute(self):
        self._rec.executed.append((self._table, self._rpc, list(self.calls)))
        out = self._rec.outcomes.pop(0) if self._rec.outcomes else []
        if isinstance(out, Exception):
            raise out
        return _Resp(out)


class _Client:
    def __init__(self, outcomes):
        self.outcomes, self.executed = list(outcomes), []

    def schema(self, name):
        return self

    def table(self, name):
        return _Query(self, name)

    def rpc(self, fn, params):
        return _Query(self, None, (fn, params))


def _version_row(vid: UUID, status: str = "rascunho", **extra) -> dict:
    return {
        "id": str(vid), "org_id": str(ORG), "agent_id": str(uuid4()), "versao": 1, "status": status,
        "notas": None, "model": "claude-opus-5", "effort": "high", "max_turns": 40, "idioma": "pt-BR",
        "tool_policy": {}, "based_on_version_id": None, "created_by": str(USER), "published_by": None,
        "published_at": None, "compiled_hash": None, "eval_run_id": None, "publish_override_reason": None,
        "created_at": "2026-09-21T00:00:00+00:00", "updated_at": "2026-09-21T00:00:00.123456+00:00", **extra,
    }


class TestRealStore:
    def test_replace_sections_is_one_rpc(self):
        vid = uuid4()
        client = _Client([None, []])
        SupabaseStudioDefinitionStore(client).replace_sections(ORG, vid, [
            SectionInput(chave="a", titulo="A", ordem=1, conteudo="x"),
        ])
        fn, params = client.executed[0][1]
        assert fn == "replace_draft_sections"
        assert params["p_secoes"] == [{"id": None, "chave": "a", "titulo": "A", "ordem": 1, "conteudo": "x", "ativo": True}]
        # No table-level delete/upsert anymore — the only write is the RPC.
        writes = [c for t, rpc, calls in client.executed for c in calls if c[0] in ("delete", "upsert", "insert")]
        assert writes == []

    def test_replace_draft_bundle_rpc_payload(self):
        vid = uuid4()
        client = _Client([None])
        res = SupabaseStudioDefinitionStore(client).replace_draft_bundle(ORG, vid, [
            {"chave": "a", "titulo": "A", "ordem": 1, "conteudo": "x", "ativo": True},
        ], [
            {"nome": "s", "descricao": "d", "corpo": "c", "ordem": 2, "ativo": False,
             "arquivos": [{"caminho": "f.md", "titulo": None, "conteudo": "z"}]},
        ])
        fn, params = client.executed[0][1]
        assert fn == "replace_draft_bundle"
        assert params["p_skills"] == [{
            "nome": "s", "descricao": "d", "corpo": "c", "ordem": 2, "ativo": False,
            "arquivos": [{"caminho": "f.md", "titulo": None, "conteudo": "z"}],
        }]
        assert (res.secoes, res.skills, res.arquivos) == (1, 1, 1)

    def test_set_compiled_hash_compare_and_set(self):
        vid = uuid4()
        # CAS misses (no row) → re-read shows a draft → draft_changed
        client = _Client([[], [_version_row(vid)]])
        with pytest.raises(StudioConflict) as exc:
            SupabaseStudioDefinitionStore(client).set_compiled_hash(
                ORG, vid, "sha256:" + "a" * 64, expected_updated_at="2026-09-21T00:00:00.123456+00:00",
            )
        assert exc.value.code == "draft_changed"
        calls = client.executed[0][2]
        assert ("eq", ("updated_at", "2026-09-21T00:00:00.123456+00:00"), {}) in calls

    def test_limiar_goes_through_the_audited_function(self):
        agent_row = {
            "id": str(uuid4()), "org_id": str(ORG), "key": "isa", "nome": "Isa", "descricao": None,
            "definition_mode": "studio", "runtime": "claude_sdk", "ativo": False, "publicacao_limiar": 0.8,
            "created_at": "x", "updated_at": "x",
        }
        client = _Client([[agent_row], None, [agent_row]])
        SupabaseStudioDefinitionStore(client).update_agent(ORG, "isa", {"publicacao_limiar": 0.9}, actor=USER)
        fn, params = client.executed[1][1]
        assert fn == "set_agent_publicacao_limiar"
        assert params == {"p_org_id": str(ORG), "p_agent_id": agent_row["id"], "p_limiar": 0.9, "p_actor": str(USER)}

    @pytest.mark.parametrize("code", ["draft_changed", "eval_required", "client_entries_cap", "chave_conflict"])
    def test_new_machine_codes_map_to_409_codes(self, code):
        client = _Client([_APIError("P0001", code)])
        with pytest.raises(StudioConflict) as exc:
            SupabaseStudioDefinitionStore(client).publish_version(
                ORG, uuid4(), USER, None, REASON, expected_hash="sha256:" + "a" * 64, texto="T", manifest=[],
            )
        assert exc.value.code == code

    def test_check_violation_is_a_value_error(self):
        client = _Client([_APIError("23514", 'new row violates check constraint "agent_clients_resumo_check"')])
        with pytest.raises(ValueError):
            SupabaseStudioDefinitionStore(client).create_client(ORG, uuid4(), slug="c", nome="C")

    def test_discard_fk_violation_is_draft_referenced(self):
        client = _Client([_APIError("23503", "violates foreign key constraint")])
        with pytest.raises(StudioConflict) as exc:
            SupabaseStudioDefinitionStore(client).discard_draft(ORG, uuid4(), actor=USER)
        assert exc.value.code == "draft_referenced"

    def test_erase_calls_the_service_role_function(self):
        cid = uuid4()
        client = _Client([3])
        assert SupabaseStudioDefinitionStore(client).erase_client_compiled_prompts(ORG, cid) == 3
        assert client.executed[0][1] == ("erase_compiled_prompts", {"p_org_id": str(ORG), "p_client_id": str(cid)})

    def test_version_snapshots_are_read(self):
        vid = uuid4()
        client = _Client([[_version_row(vid, "ativa", limiar_aplicado="0.800", eval_score="0.910")]])
        v = SupabaseStudioDefinitionStore(client).get_version(ORG, vid)
        assert (v.limiar_aplicado, v.eval_score) == (0.8, 0.91)


# ── compliance #3 — the production binding for the evals' current-hash seam ─


class TestCompiledHashProvider:
    def test_hashes_the_version_as_compiled_now_without_writing(self, studio):
        from app.routers.studio_agents_router import get_compiled_hash_provider
        from app.studio.models import CollectionSummary

        _publishable(studio)
        agent = studio.store.get_agent(studio.org_id, "isa")
        draft = studio.store.get_draft(studio.org_id, agent.id)
        studio.catalog.set(studio.org_id, agent.id, [
            CollectionSummary(slug="k", nome="K", tag=None, descricao="", doc_count=2),
        ])
        provider = get_compiled_hash_provider(store=studio.store, catalog=studio.catalog)
        now_hash = provider(studio.org_id, agent, draft)
        assert now_hash.startswith("sha256:") and now_hash != draft.compiled_hash
        assert studio.store.get_draft(studio.org_id, agent.id).compiled_hash == draft.compiled_hash
