"""Protocol-conformance suite for `KnowledgeStore` — contract §A.11.

Runs EXCLUSIVELY against `FakeKnowledgeStore`. `PgKnowledgeStore` needs a
live Postgres, and this slice is explicitly forbidden from applying
migrations to any database — see `app/knowledge/pg.py`'s module docstring
(`NOC-REMEDIATE[pg-knowledge-store-untested]`).

The signature tests below are the ones engineer A2 depends on staying
green: A2's importer is built against this exact method/parameter shape
in parallel, so a drift here is a silent `TypeError` at their call site,
not a merge conflict.
"""
from __future__ import annotations

import inspect
from datetime import date
from uuid import uuid4

import pytest

from app.knowledge.errors import AssertionUsed, Conflict, Invalid, NotFound
from app.knowledge.fake import FakeKnowledgeStore
from app.knowledge.store import KnowledgeStore, Provenance

_POS = inspect.Parameter.POSITIONAL_OR_KEYWORD
_KW = inspect.Parameter.KEYWORD_ONLY

# name -> ordered [(param_name, kind), ...] EXCLUDING `self`, exactly as
# contract §A.11's fenced code block declares them.
_EXPECTED_SIGNATURES: dict[str, list[tuple[str, inspect._ParameterKind]]] = {
    "search_kb": [
        ("org_id", _POS), ("consulta", _KW), ("categoria", _KW),
        ("subcategoria", _KW), ("tag", _KW), ("limite", _KW), ("offset", _KW),
    ],
    "get_kb": [("org_id", _POS), ("slug", _POS)],
    "create_kb": [("org_id", _POS), ("data", _POS), ("prov", _POS)],
    "update_kb": [("org_id", _POS), ("slug", _POS), ("changes", _POS), ("prov", _POS)],
    "archive_kb": [("org_id", _POS), ("slug", _POS), ("prov", _POS)],
    "list_revisions": [("org_id", _POS), ("entity_type", _POS), ("entity_id", _POS)],
    "list_decisions": [("org_id", _POS), ("estado", _KW)],
    "get_decision": [("org_id", _POS), ("codigo", _POS)],
    "create_decision": [("org_id", _POS), ("data", _POS), ("prov", _POS)],
    "supersede_decision": [("org_id", _POS), ("codigo", _POS), ("data", _POS), ("prov", _POS)],
    "list_questions": [("org_id", _POS), ("estado", _KW)],
    "create_question": [("org_id", _POS), ("data", _POS), ("prov", _POS)],
    "answer_question": [("org_id", _POS), ("codigo", _POS), ("resposta", _POS), ("prov", _POS)],
    "list_phases": [("org_id", _POS)],
    "update_phase": [("org_id", _POS), ("codigo", _POS), ("changes", _POS), ("prov", _POS)],
    "list_tasks": [("org_id", _POS), ("fase", _KW), ("estado", _KW)],
    "create_task": [("org_id", _POS), ("data", _POS), ("prov", _POS)],
    "update_task": [("org_id", _POS), ("codigo", _POS), ("changes", _POS), ("prov", _POS)],
    "session_prep": [("org_id", _POS)],
    "list_content": [("org_id", _POS), ("tipo", _KW)],
    "get_content": [("org_id", _POS), ("codigo", _POS)],
    "create_content": [("org_id", _POS), ("data", _POS), ("prov", _POS)],
    "list_timeline": [("org_id", _POS), ("limite", _KW)],
    "create_timeline_event": [("org_id", _POS), ("data", _POS), ("prov", _POS)],
    "create_source": [("org_id", _POS), ("data", _POS), ("prov", _POS)],
    "import_entity": [
        ("org_id", _POS), ("entity_type", _POS), ("natural_key", _POS),
        ("snapshot", _POS), ("prov", _POS),
    ],
    "seed_counters": [("org_id", _POS), ("counters", _POS)],
}


def test_protocol_method_set_matches_contract():
    """No extra, no missing methods vs. contract §A.11's fenced block."""
    declared = {
        name for name, member in vars(KnowledgeStore).items()
        if not name.startswith("_") and callable(member)
    }
    assert declared == set(_EXPECTED_SIGNATURES)


@pytest.mark.parametrize("method_name", sorted(_EXPECTED_SIGNATURES))
def test_protocol_signature_matches_contract(method_name):
    """Character-for-character parameter names + kinds, per §A.11."""
    func = vars(KnowledgeStore)[method_name]
    params = [(name, p.kind) for name, p in inspect.signature(func).parameters.items() if name != "self"]
    assert params == _EXPECTED_SIGNATURES[method_name], (
        f"{method_name}: signature drifted from contract §A.11 — "
        f"got {params}, expected {_EXPECTED_SIGNATURES[method_name]}"
    )


def test_fake_and_pg_implement_every_protocol_method():
    """Both concrete stores implement every §A.11 method (structural check).

    Only structural — `PgKnowledgeStore`'s behaviour is not exercised here
    (see module docstring).
    """
    from app.knowledge.pg import PgKnowledgeStore

    for cls in (FakeKnowledgeStore, PgKnowledgeStore):
        for name in _EXPECTED_SIGNATURES:
            assert hasattr(cls, name), f"{cls.__name__} is missing {name}"


# ---------------------------------------------------------------------------
# Behavioural conformance — every invariant the A1 brief calls out.
# ---------------------------------------------------------------------------


@pytest.fixture
def store() -> FakeKnowledgeStore:
    return FakeKnowledgeStore()


@pytest.fixture
def org_id():
    return uuid4()


def human_prov(**kwargs) -> Provenance:
    return Provenance(author_kind="human", **kwargs)


async def _seed_phase(store, org_id, *, codigo="P1", estado="em-andamento", ordem=1):
    return await store.import_entity(
        org_id, "roadmap_phase", codigo,
        {"titulo": "Fase 1", "objetivo": "obj", "concluida_quando": "quando", "estado": estado, "ordem": ordem},
        Provenance(author_kind="import", git_sha="seed-phase"),
    )


class TestKbEntries:
    @pytest.mark.asyncio
    async def test_create_get_update_archive_and_revision_count(self, store, org_id):
        created = await store.create_kb(org_id, {
            "slug": "dominio-regulatorio-pnrs", "categoria": "dominio",
            "titulo": "PNRS", "corpo_md": "# PNRS",
        }, human_prov(motivo="seed"))
        assert created["arquivado"] is False
        assert created["current_revision_id"] is not None

        fetched = await store.get_kb(org_id, "dominio-regulatorio-pnrs")
        assert fetched["id"] == created["id"]

        updated = await store.update_kb(org_id, "dominio-regulatorio-pnrs", {"titulo": "PNRS v2"}, human_prov())
        assert updated["titulo"] == "PNRS v2"

        archived = await store.archive_kb(org_id, "dominio-regulatorio-pnrs", human_prov())
        assert archived["arquivado"] is True

        revs = await store.list_revisions(org_id, "kb_entry", created["id"])
        assert [r["op"] for r in revs] == ["archive", "update", "create"]  # newest first
        assert [r["rev_no"] for r in revs] == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_create_kb_slug_conflict(self, store, org_id):
        data = {"slug": "dup", "categoria": "geral", "titulo": "A", "corpo_md": "x"}
        await store.create_kb(org_id, data, human_prov())
        with pytest.raises(Conflict):
            await store.create_kb(org_id, {**data, "titulo": "B"}, human_prov())

    @pytest.mark.asyncio
    async def test_update_kb_novo_slug_conflict(self, store, org_id):
        await store.create_kb(org_id, {"slug": "a", "categoria": "geral", "titulo": "A", "corpo_md": "x"}, human_prov())
        await store.create_kb(org_id, {"slug": "b", "categoria": "geral", "titulo": "B", "corpo_md": "y"}, human_prov())
        with pytest.raises(Conflict):
            await store.update_kb(org_id, "a", {"novo_slug": "b"}, human_prov())

    @pytest.mark.asyncio
    async def test_get_update_archive_unknown_slug_not_found(self, store, org_id):
        with pytest.raises(NotFound):
            await store.get_kb(org_id, "nope")
        with pytest.raises(NotFound):
            await store.update_kb(org_id, "nope", {"titulo": "x"}, human_prov())
        with pytest.raises(NotFound):
            await store.archive_kb(org_id, "nope", human_prov())

    @pytest.mark.asyncio
    async def test_kb_scoped_per_org(self, store, org_id):
        other_org = uuid4()
        await store.create_kb(org_id, {"slug": "s", "categoria": "geral", "titulo": "t", "corpo_md": "x"}, human_prov())
        with pytest.raises(NotFound):
            await store.get_kb(other_org, "s")

    @pytest.mark.asyncio
    async def test_search_kb_filters_and_paginates(self, store, org_id):
        for i in range(3):
            await store.create_kb(org_id, {
                "slug": f"s{i}", "categoria": "dominio" if i < 2 else "geral",
                "titulo": f"titulo {i}", "corpo_md": "conteudo sobre reciclagem",
            }, human_prov())

        items, total = await store.search_kb(
            org_id, consulta=None, categoria="dominio", subcategoria=None, tag=None, limite=1, offset=0,
        )
        assert total == 2
        assert len(items) == 1

        items, total = await store.search_kb(
            org_id, consulta="titulo 2", categoria=None, subcategoria=None, tag=None, limite=20, offset=0,
        )
        assert total == 1
        assert items[0]["slug"] == "s2"


class TestDecisions:
    @pytest.mark.asyncio
    async def test_create_and_codes_monotonic(self, store, org_id):
        codes = []
        for i in range(3):
            d = await store.create_decision(org_id, {"titulo": f"T{i}", "decisao": "X", "motivo": "Y"}, human_prov())
            codes.append(d["codigo"])
        assert codes == ["D-01", "D-02", "D-03"]

    @pytest.mark.asyncio
    async def test_codes_scoped_per_org(self, store, org_id):
        other_org = uuid4()
        d_a = await store.create_decision(org_id, {"titulo": "A", "decisao": "X", "motivo": "Y"}, human_prov())
        d_b = await store.create_decision(other_org, {"titulo": "B", "decisao": "X", "motivo": "Y"}, human_prov())
        assert d_a["codigo"] == d_b["codigo"] == "D-01"

    @pytest.mark.asyncio
    async def test_supersede_atomicity_and_two_revisions(self, store, org_id):
        d1 = await store.create_decision(org_id, {"titulo": "T1", "decisao": "X", "motivo": "Y"}, human_prov())

        nova, substituida = await store.supersede_decision(
            org_id, d1["codigo"], {"titulo": "T2", "decisao": "X2", "motivo": "Y2"}, human_prov(),
        )
        assert nova["substitui"] == d1["codigo"]
        assert nova["estado"] == "vigente"
        assert substituida["estado"] == "superseded"
        assert substituida["superseded_by"] == nova["codigo"]

        revs_new = await store.list_revisions(org_id, "decision", nova["id"])
        revs_old = await store.list_revisions(org_id, "decision", substituida["id"])
        assert [r["op"] for r in revs_new] == ["supersede"]
        assert [r["op"] for r in revs_old] == ["supersede", "create"]

    @pytest.mark.asyncio
    async def test_supersede_already_superseded_conflicts(self, store, org_id):
        d1 = await store.create_decision(org_id, {"titulo": "T", "decisao": "X", "motivo": "Y"}, human_prov())
        await store.supersede_decision(org_id, d1["codigo"], {"titulo": "T2", "decisao": "X2", "motivo": "Y2"}, human_prov())
        with pytest.raises(Conflict):
            await store.supersede_decision(org_id, d1["codigo"], {"titulo": "T3", "decisao": "X3", "motivo": "Y3"}, human_prov())

    @pytest.mark.asyncio
    async def test_supersede_unknown_codigo_not_found(self, store, org_id):
        with pytest.raises(NotFound):
            await store.supersede_decision(org_id, "D-99", {"titulo": "T", "decisao": "X", "motivo": "Y"}, human_prov())

    @pytest.mark.asyncio
    async def test_list_decisions_filters_by_estado(self, store, org_id):
        d1 = await store.create_decision(org_id, {"titulo": "T1", "decisao": "X", "motivo": "Y"}, human_prov())
        await store.create_decision(org_id, {"titulo": "T2", "decisao": "X", "motivo": "Y"}, human_prov())
        await store.supersede_decision(org_id, d1["codigo"], {"titulo": "T3", "decisao": "X", "motivo": "Y"}, human_prov())

        vigentes = await store.list_decisions(org_id, estado="vigente")
        superseded = await store.list_decisions(org_id, estado="superseded")
        assert len(vigentes) == 2
        assert len(superseded) == 1
        assert superseded[0]["codigo"] == d1["codigo"]


class TestOpenQuestions:
    @pytest.mark.asyncio
    async def test_answer_twice_conflicts(self, store, org_id):
        q = await store.create_question(org_id, {"pergunta": "?", "por_que_importa": "x", "bloqueia": "y"}, human_prov())
        answered = await store.answer_question(org_id, q["codigo"], "resposta", human_prov())
        assert answered["estado"] == "respondida"
        with pytest.raises(Conflict):
            await store.answer_question(org_id, q["codigo"], "de novo", human_prov())

    @pytest.mark.asyncio
    async def test_answer_unknown_not_found(self, store, org_id):
        with pytest.raises(NotFound):
            await store.answer_question(org_id, "Q-99", "x", human_prov())

    @pytest.mark.asyncio
    async def test_list_questions_estado_filter(self, store, org_id):
        q1 = await store.create_question(org_id, {"pergunta": "?1", "por_que_importa": "x", "bloqueia": "y"}, human_prov())
        q2 = await store.create_question(org_id, {"pergunta": "?2", "por_que_importa": "x", "bloqueia": "y"}, human_prov())
        await store.answer_question(org_id, q2["codigo"], "r", human_prov())

        assert [q["codigo"] for q in await store.list_questions(org_id, estado="aberta")] == [q1["codigo"]]
        assert [q["codigo"] for q in await store.list_questions(org_id, estado="respondida")] == [q2["codigo"]]
        assert len(await store.list_questions(org_id, estado="todas")) == 2


class TestRoadmapAndTasks:
    @pytest.mark.asyncio
    async def test_create_task_unknown_fase_invalid(self, store, org_id):
        with pytest.raises(Invalid):
            await store.create_task(org_id, {"titulo": "T", "fase": "P-nope"}, human_prov())

    @pytest.mark.asyncio
    async def test_create_task_known_fase_codes_are_three_digit(self, store, org_id):
        await _seed_phase(store, org_id, codigo="P1")
        task = await store.create_task(org_id, {"titulo": "Fazer X", "fase": "P1"}, human_prov())
        assert task["codigo"] == "T-001"
        assert task["estado"] == "pendente"

    @pytest.mark.asyncio
    async def test_update_task_unknown_not_found(self, store, org_id):
        with pytest.raises(NotFound):
            await store.update_task(org_id, "T-999", {"estado": "concluida"}, human_prov())

    @pytest.mark.asyncio
    async def test_update_phase_unknown_not_found(self, store, org_id):
        with pytest.raises(NotFound):
            await store.update_phase(org_id, "P-nope", {"estado": "concluida"}, human_prov())

    @pytest.mark.asyncio
    async def test_update_phase_partial(self, store, org_id):
        await _seed_phase(store, org_id, codigo="P1", estado="pendente")
        updated = await store.update_phase(org_id, "P1", {"estado": "em-andamento"}, human_prov())
        assert updated["estado"] == "em-andamento"
        assert updated["titulo"] == "Fase 1"  # untouched field survives partial update

    @pytest.mark.asyncio
    async def test_session_prep_shape(self, store, org_id):
        await _seed_phase(store, org_id, codigo="P1", estado="em-andamento", ordem=1)
        livre = await store.create_task(org_id, {"titulo": "Livre", "fase": "P1"}, human_prov())
        bloqueada = await store.create_task(
            org_id, {"titulo": "Bloqueada", "fase": "P1", "bloqueada_por": livre["codigo"]}, human_prov(),
        )
        pergunta = await store.create_question(
            org_id, {"pergunta": "?", "por_que_importa": "x", "bloqueia": bloqueada["codigo"]}, human_prov(),
        )

        prep = await store.session_prep(org_id)
        assert prep["fase_atual"]["codigo"] == "P1"
        assert [t["codigo"] for t in prep["proximas"]] == [livre["codigo"]]
        assert [t["codigo"] for t in prep["bloqueadas"]] == [bloqueada["codigo"]]
        assert prep["perguntas_abertas"] == 1
        assert [q["codigo"] for q in prep["perguntas_bloqueantes"]] == [pergunta["codigo"]]


class TestContentTimelineSources:
    @pytest.mark.asyncio
    async def test_create_content_codigo_is_three_digit(self, store, org_id):
        c = await store.create_content(org_id, {"tipo": "roteiro", "titulo": "T", "corpo_md": "x"}, human_prov())
        assert c["codigo"] == "C-001"

    @pytest.mark.asyncio
    async def test_create_source_unknown_kb_slug_not_found(self, store, org_id):
        with pytest.raises(NotFound):
            await store.create_source(org_id, {
                "url": "https://x.example", "titulo": "t", "trecho_citado": "c",
                "resumo": "r", "kb_slug": "nope", "vigencia_confirmada": True,
            }, human_prov())

    @pytest.mark.asyncio
    async def test_create_source_known_kb_slug(self, store, org_id):
        await store.create_kb(org_id, {"slug": "s", "categoria": "geral", "titulo": "t", "corpo_md": "x"}, human_prov())
        src = await store.create_source(org_id, {
            "url": "https://x.example", "titulo": "t", "trecho_citado": "c",
            "resumo": "r", "kb_slug": "s", "vigencia_confirmada": True,
        }, human_prov())
        assert src["kb_slug"] == "s"

    @pytest.mark.asyncio
    async def test_list_timeline_ordering_and_limit(self, store, org_id):
        await store.create_timeline_event(org_id, {"data": date(2026, 1, 1), "titulo": "old", "descricao": "d"}, human_prov())
        await store.create_timeline_event(org_id, {"data": date(2026, 6, 1), "titulo": "new", "descricao": "d"}, human_prov())
        items = await store.list_timeline(org_id, limite=1)
        assert len(items) == 1
        assert items[0]["titulo"] == "new"


class TestApprovalAssertion:
    @pytest.mark.asyncio
    async def test_reuse_raises_assertion_used_and_no_write_happened(self, store, org_id):
        approval_id = uuid4()
        prov = Provenance(author_kind="agent", agent_id=uuid4(), approval_id=approval_id)

        await store.create_kb(org_id, {"slug": "s1", "categoria": "geral", "titulo": "t", "corpo_md": "x"}, prov)

        with pytest.raises(AssertionUsed):
            await store.create_kb(org_id, {"slug": "s2", "categoria": "geral", "titulo": "t2", "corpo_md": "y"}, prov)

        with pytest.raises(NotFound):
            await store.get_kb(org_id, "s2")
        assert len(store.kb_entries) == 1

    @pytest.mark.asyncio
    async def test_supersede_consumes_approval_exactly_once_for_two_revisions(self, store, org_id):
        approval_id = uuid4()
        prov = Provenance(author_kind="agent", agent_id=uuid4(), approval_id=approval_id)
        d1 = await store.create_decision(org_id, {"titulo": "T", "decisao": "X", "motivo": "Y"}, human_prov())

        await store.supersede_decision(org_id, d1["codigo"], {"titulo": "T2", "decisao": "X2", "motivo": "Y2"}, prov)

        assert approval_id in store.approval_consumptions
        # a second write with the SAME approval_id is now rejected
        with pytest.raises(AssertionUsed):
            await store.create_decision(org_id, {"titulo": "T3", "decisao": "X3", "motivo": "Y3"}, prov)

    @pytest.mark.asyncio
    async def test_human_write_needs_no_approval(self, store, org_id):
        row = await store.create_kb(org_id, {"slug": "s", "categoria": "geral", "titulo": "t", "corpo_md": "x"}, human_prov())
        assert row["slug"] == "s"
        assert not store.approval_consumptions


class TestImportAndCounters:
    @pytest.mark.asyncio
    async def test_import_entity_idempotent_on_git_sha_and_natural_key(self, store, org_id):
        prov = Provenance(author_kind="import", user_id=uuid4(), git_sha="abc123")
        row1 = await store.import_entity(org_id, "kb_entry", "s1", {
            "categoria": "geral", "titulo": "T", "corpo_md": "x",
        }, prov)
        row2 = await store.import_entity(org_id, "kb_entry", "s1", {
            "categoria": "geral", "titulo": "T-changed-but-should-be-ignored", "corpo_md": "x",
        }, prov)

        assert row2["id"] == row1["id"]
        assert row2["titulo"] == "T"  # second call at the SAME git_sha is a no-op
        revs = await store.list_revisions(org_id, "kb_entry", row1["id"])
        assert len(revs) == 1

    @pytest.mark.asyncio
    async def test_import_entity_new_git_sha_writes_a_new_revision(self, store, org_id):
        row1 = await store.import_entity(
            org_id, "kb_entry", "s1", {"categoria": "geral", "titulo": "T", "corpo_md": "x"},
            Provenance(author_kind="import", git_sha="sha1"),
        )
        row2 = await store.import_entity(
            org_id, "kb_entry", "s1", {"categoria": "geral", "titulo": "T2", "corpo_md": "x"},
            Provenance(author_kind="import", git_sha="sha2"),
        )
        assert row2["id"] == row1["id"]
        assert row2["titulo"] == "T2"
        revs = await store.list_revisions(org_id, "kb_entry", row1["id"])
        assert len(revs) == 2
        assert all(r["op"] == "import" for r in revs)

    @pytest.mark.asyncio
    async def test_import_entity_unknown_type_invalid(self, store, org_id):
        with pytest.raises(Invalid):
            await store.import_entity(org_id, "nonsense", "x", {}, Provenance(author_kind="import"))

    @pytest.mark.asyncio
    async def test_seed_counters_takes_the_max(self, store, org_id):
        await store.seed_counters(org_id, {"D": 5})
        d = await store.create_decision(org_id, {"titulo": "T", "decisao": "X", "motivo": "Y"}, human_prov())
        assert d["codigo"] == "D-06"

        await store.seed_counters(org_id, {"D": 3})  # lower than current -> no-op
        d2 = await store.create_decision(org_id, {"titulo": "T2", "decisao": "X", "motivo": "Y"}, human_prov())
        assert d2["codigo"] == "D-07"

        await store.seed_counters(org_id, {"D": 20})  # higher -> takes effect
        d3 = await store.create_decision(org_id, {"titulo": "T3", "decisao": "X", "motivo": "Y"}, human_prov())
        assert d3["codigo"] == "D-21"


class TestTransaction:
    @pytest.mark.asyncio
    async def test_rolls_back_the_whole_batch_on_exception(self, store, org_id):
        await store.create_kb(org_id, {"slug": "keep", "categoria": "geral", "titulo": "t", "corpo_md": "x"}, human_prov())

        with pytest.raises(RuntimeError):
            async with store.transaction():
                await store.import_entity(
                    org_id, "kb_entry", "s2", {"categoria": "geral", "titulo": "t2", "corpo_md": "y"},
                    Provenance(author_kind="import", git_sha="sha1"),
                )
                raise RuntimeError("boom")

        with pytest.raises(NotFound):
            await store.get_kb(org_id, "s2")
        kept = await store.get_kb(org_id, "keep")
        assert kept["slug"] == "keep"

    @pytest.mark.asyncio
    async def test_commits_the_whole_batch_on_clean_exit(self, store, org_id):
        async with store.transaction():
            await store.import_entity(
                org_id, "kb_entry", "s3", {"categoria": "geral", "titulo": "t3", "corpo_md": "z"},
                Provenance(author_kind="import", git_sha="sha1"),
            )
            await store.seed_counters(org_id, {"D": 9})

        got = await store.get_kb(org_id, "s3")
        assert got["titulo"] == "t3"
        d = await store.create_decision(org_id, {"titulo": "T", "decisao": "X", "motivo": "Y"}, human_prov())
        assert d["codigo"] == "D-10"
