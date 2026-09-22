"""``StudioDefinitionStore`` — Fake behaviour (draft / clone / publish /
immutability / org scoping / clients / compiled prompts) and the Real
store's RPC + error-mapping contract.

The Real-store tests use a tiny recording double of the *Supabase client*
(an external service), never a patch of our own code: they pin the RPC names
and parameter shapes the 012 functions declare, the bare table names, and
the mapping of the trigger/function raises onto typed store errors.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.stores.errors import NotFound
from app.stores.studio_definitions import (
    FakeStudioDefinitionStore,
    SectionInput,
    StudioConflict,
    SupabaseStudioDefinitionStore,
    VersionImmutable,
    get_studio_definition_store,
)

ORG = UUID("11111111-1111-1111-1111-111111111111")
OTHER_ORG = UUID("22222222-2222-2222-2222-222222222222")
USER = UUID("33333333-3333-3333-3333-333333333333")


@pytest.fixture
def store() -> FakeStudioDefinitionStore:
    return FakeStudioDefinitionStore()


@pytest.fixture
def agent(store):
    return store.create_studio_agent(ORG, "isa", "Isa", "descr")


def _fill(store, draft_id):
    store.replace_sections(ORG, draft_id, [
        SectionInput(chave="identidade", titulo="Identidade", ordem=10, conteudo="x"),
        SectionInput(chave="regras", titulo="Regras", ordem=20, conteudo="y"),
    ])
    sk = store.create_skill(ORG, draft_id, nome="roteiro", descricao="d", corpo="c")
    store.upsert_skill_file(ORG, sk.id, caminho="references/a.md", titulo="A", conteudo="aaa")
    return sk


class TestAgents:
    def test_create_is_studio_inactive_claude_sdk(self, store, agent):
        assert agent.definition_mode == "studio"
        assert agent.runtime == "claude_sdk"
        assert agent.ativo is False
        assert agent.publicacao_limiar == pytest.approx(0.8)

    def test_key_taken(self, store, agent):
        with pytest.raises(StudioConflict) as exc:
            store.create_studio_agent(ORG, "isa", "Outra", None)
        assert exc.value.code == "key_taken"

    def test_same_key_other_org_is_independent(self, store, agent):
        store.create_studio_agent(OTHER_ORG, "isa", "Isa", None)
        assert [a.key for a in store.list_agents(OTHER_ORG)] == ["isa"]

    def test_update_rejects_unknown_fields_and_bad_limiar(self, store, agent):
        with pytest.raises(ValueError):
            store.update_agent(ORG, "isa", {"key": "other"})
        with pytest.raises(ValueError):
            store.update_agent(ORG, "isa", {"publicacao_limiar": 1.5})
        assert store.update_agent(ORG, "isa", {"publicacao_limiar": 0.9}).publicacao_limiar == 0.9

    def test_foreign_org_is_not_found(self, store, agent):
        with pytest.raises(NotFound):
            store.get_agent(OTHER_ORG, "isa")


class TestDrafts:
    def test_empty_draft_defaults(self, store, agent):
        d = store.create_draft(ORG, agent.id, None, USER)
        assert (d.versao, d.status, d.model, d.effort, d.max_turns) == (1, "rascunho", "claude-opus-5", "high", 40)
        assert d.tool_policy == {"web_search": True, "knowledge": True}
        assert d.based_on_version_id is None

    def test_one_draft_per_agent(self, store, agent):
        store.create_draft(ORG, agent.id, None, USER)
        with pytest.raises(StudioConflict) as exc:
            store.create_draft(ORG, agent.id, None, USER)
        assert exc.value.code == "draft_exists"

    def test_clone_deep_copies_settings_sections_skills_files(self, store, agent):
        v1 = store.create_draft(ORG, agent.id, None, USER)
        store.update_draft(ORG, v1.id, {"model": "claude-sonnet-5", "max_turns": 12})
        sk = _fill(store, v1.id)
        store.publish_version(ORG, v1.id, USER, None, "motivo suficientemente longo")

        v2 = store.create_draft(ORG, agent.id, v1.id, USER)
        assert v2.versao == 2 and v2.based_on_version_id == v1.id
        assert (v2.model, v2.max_turns) == ("claude-sonnet-5", 12)
        s1 = store.list_sections(ORG, v1.id)
        s2 = store.list_sections(ORG, v2.id)
        assert [(s.chave, s.conteudo) for s in s2] == [(s.chave, s.conteudo) for s in s1]
        assert not {s.id for s in s1} & {s.id for s in s2}
        sk2 = store.list_skills(ORG, v2.id)[0]
        assert sk2.id != sk.id and sk2.nome == "roteiro"
        files2 = store.list_version_skill_files(ORG, v2.id)
        assert [(f.skill_id, f.caminho, f.conteudo) for f in files2] == [(sk2.id, "references/a.md", "aaa")]
        # Editing the clone never touches the source.
        store.update_skill(ORG, sk2.id, {"corpo": "novo"})
        assert store.get_skill(ORG, sk.id).corpo == "c"

    def test_clone_from_foreign_version_is_not_found(self, store, agent):
        other = store.create_studio_agent(ORG, "other", "O", None)
        ov = store.create_draft(ORG, other.id, None, USER)
        with pytest.raises(NotFound):
            store.create_draft(ORG, agent.id, ov.id, USER)

    def test_update_draft_allowlists(self, store, agent):
        d = store.create_draft(ORG, agent.id, None, USER)
        for bad in ({"model": "gpt-4o"}, {"effort": "extreme"}, {"max_turns": 0}, {"max_turns": 201}, {"status": "ativa"}):
            with pytest.raises(ValueError):
                store.update_draft(ORG, d.id, bad)

    def test_replace_sections_keeps_ids_and_deletes_missing(self, store, agent):
        d = store.create_draft(ORG, agent.id, None, USER)
        first = store.replace_sections(ORG, d.id, [
            SectionInput(chave="a", titulo="A", ordem=1, conteudo="1"),
            SectionInput(chave="b", titulo="B", ordem=2, conteudo="2"),
        ])
        a_id = first[0].id
        second = store.replace_sections(ORG, d.id, [
            SectionInput(id=a_id, chave="a", titulo="A!", ordem=5, conteudo="1"),
            SectionInput(id=uuid4(), chave="c", titulo="C", ordem=1, conteudo="3"),
        ])
        assert [s.chave for s in second] == ["c", "a"]
        assert second[1].id == a_id and second[1].titulo == "A!"
        assert second[0].id not in {s.id for s in first}

    def test_replace_sections_duplicate_chave(self, store, agent):
        d = store.create_draft(ORG, agent.id, None, USER)
        with pytest.raises(StudioConflict) as exc:
            store.replace_sections(ORG, d.id, [
                SectionInput(chave="a", titulo="A", ordem=1), SectionInput(chave="a", titulo="B", ordem=2),
            ])
        assert exc.value.code == "chave_conflict"

    def test_skill_name_unique_per_version(self, store, agent):
        d = store.create_draft(ORG, agent.id, None, USER)
        store.create_skill(ORG, d.id, nome="s", descricao="d", corpo="c")
        with pytest.raises(StudioConflict) as exc:
            store.create_skill(ORG, d.id, nome="s", descricao="d", corpo="c")
        assert exc.value.code == "skill_exists"

    def test_skill_file_upsert_by_caminho(self, store, agent):
        d = store.create_draft(ORG, agent.id, None, USER)
        sk = store.create_skill(ORG, d.id, nome="s", descricao="d", corpo="c")
        f1 = store.upsert_skill_file(ORG, sk.id, caminho="a.md", titulo=None, conteudo="1")
        f2 = store.upsert_skill_file(ORG, sk.id, caminho="a.md", titulo="T", conteudo="22")
        assert f1.id == f2.id and f2.conteudo == "22"
        assert len(store.list_version_skill_files(ORG, d.id)) == 1


class TestPublishAndImmutability:
    def test_publish_flips_previous_active(self, store, agent):
        v1 = store.create_draft(ORG, agent.id, None, USER)
        run_id = uuid4()
        p1 = store.publish_version(ORG, v1.id, USER, run_id, None)
        assert (p1.status, p1.published_by, p1.eval_run_id) == ("ativa", USER, run_id)
        assert p1.published_at is not None
        v2 = store.create_draft(ORG, agent.id, v1.id, USER)
        store.publish_version(ORG, v2.id, USER, None, "override reason with twenty+ chars")
        assert store.get_version(ORG, v1.id).status == "substituida"
        assert store.get_active_version(ORG, agent.id).id == v2.id
        assert store.get_draft(ORG, agent.id) is None
        assert store.get_version(ORG, v2.id).publish_override_reason.startswith("override")

    def test_published_version_is_immutable_everywhere(self, store, agent):
        v1 = store.create_draft(ORG, agent.id, None, USER)
        sk = _fill(store, v1.id)
        f = store.list_version_skill_files(ORG, v1.id)[0]
        store.publish_version(ORG, v1.id, USER, None, "x" * 20)
        attempts = [
            lambda: store.update_draft(ORG, v1.id, {"notas": "n"}),
            lambda: store.set_compiled_hash(ORG, v1.id, "sha256:" + "0" * 64),
            lambda: store.replace_sections(ORG, v1.id, []),
            lambda: store.create_skill(ORG, v1.id, nome="z", descricao="d", corpo="c"),
            lambda: store.update_skill(ORG, sk.id, {"corpo": "z"}),
            lambda: store.delete_skill(ORG, sk.id),
            lambda: store.upsert_skill_file(ORG, sk.id, caminho="b.md", titulo=None, conteudo="b"),
            lambda: store.delete_skill_file(ORG, f.id),
            lambda: store.publish_version(ORG, v1.id, USER, None, None),
            lambda: store.discard_draft(ORG, v1.id),
        ]
        for attempt in attempts:
            with pytest.raises(VersionImmutable):
                attempt()
        assert len(store.list_sections(ORG, v1.id)) == 2

    def test_discard_removes_draft_and_children(self, store, agent):
        d = store.create_draft(ORG, agent.id, None, USER)
        _fill(store, d.id)
        store.discard_draft(ORG, d.id)
        assert store.get_draft(ORG, agent.id) is None
        with pytest.raises(NotFound):
            store.get_version(ORG, d.id)
        # versao numbering continues from the max remaining (none) → 1 again
        assert store.create_draft(ORG, agent.id, None, USER).versao == 1

    def test_versions_newest_first(self, store, agent):
        v1 = store.create_draft(ORG, agent.id, None, USER)
        store.publish_version(ORG, v1.id, USER, None, "x" * 20)
        store.create_draft(ORG, agent.id, v1.id, USER)
        assert [v.versao for v in store.list_versions(ORG, agent.id)] == [2, 1]

    def test_foreign_org_cannot_see_or_touch_versions(self, store, agent):
        d = store.create_draft(ORG, agent.id, None, USER)
        with pytest.raises(NotFound):
            store.get_version(OTHER_ORG, d.id)
        with pytest.raises(NotFound):
            store.update_draft(OTHER_ORG, d.id, {"notas": "x"})


class TestClientsAndCompiled:
    def test_clients_entries_and_counts(self, store, agent):
        c = store.create_client(ORG, agent.id, slug="marca-x", nome="Marca X")
        with pytest.raises(StudioConflict) as exc:
            store.create_client(ORG, agent.id, slug="marca-x", nome="Dup")
        assert exc.value.code == "client_exists"
        e1 = store.create_client_entry(ORG, c.id, tipo="marca", titulo="Tom", conteudo="leve")
        store.create_client_entry(ORG, c.id, tipo="nota", titulo="N")
        assert store.list_clients(ORG, agent.id)[0].total_entradas == 2
        assert [e.id for e in store.list_client_entries(ORG, c.id)][0] == e1.id
        with pytest.raises(ValueError):
            store.create_client_entry(ORG, c.id, tipo="inventado", titulo="x")
        store.update_client_entry(ORG, e1.id, {"status": "arquivado"})
        assert store.get_client_entry(ORG, e1.id).status == "arquivado"
        store.delete_client_entry(ORG, e1.id)
        with pytest.raises(NotFound):
            store.get_client_entry(ORG, e1.id)
        with pytest.raises(NotFound):
            store.get_client(OTHER_ORG, c.id)

    def test_compiled_prompt_is_write_once(self, store, agent):
        d = store.create_draft(ORG, agent.id, None, USER)
        h = "sha256:" + "a" * 64
        first = store.save_compiled_prompt(ORG, hash=h, version_id=d.id, client_id=None, texto="T1", manifest=[])
        again = store.save_compiled_prompt(ORG, hash=h, version_id=d.id, client_id=None, texto="T2", manifest=[{}])
        assert again == first and again.texto == "T1"
        with pytest.raises(NotFound):
            store.get_compiled_prompt(OTHER_ORG, h)

    def test_draft_with_stored_prompt_cannot_be_discarded(self, store, agent):
        """Mirrors the FK `compiled_prompts.version_id` (no cascade)."""
        d = store.create_draft(ORG, agent.id, None, USER)
        store.save_compiled_prompt(ORG, hash="sha256:" + "b" * 64, version_id=d.id, client_id=None, texto="T", manifest=[])
        with pytest.raises(StudioConflict) as exc:
            store.discard_draft(ORG, d.id)
        assert exc.value.code == "draft_referenced"


class TestFactory:
    def test_fake_without_service_role_key(self):
        class S:
            supabase_service_role_key = ""

        assert isinstance(get_studio_definition_store(S()), FakeStudioDefinitionStore)


# ── Real store: RPC names/params + error mapping ────────────────────────────


class _APIError(Exception):
    """Shape of ``postgrest.exceptions.APIError`` (``code`` + ``message``)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _Resp:
    def __init__(self, data: Any) -> None:
        self.data = data


class _Query:
    def __init__(self, recorder: "_RecordingClient", table: str | None, rpc: tuple | None = None) -> None:
        self._rec, self._table, self._rpc = recorder, table, rpc
        self.calls: list[tuple] = []

    def __getattr__(self, name):
        def _chain(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self
        return _chain

    def execute(self):
        self._rec.executed.append((self._table, self._rpc, list(self.calls)))
        outcome = self._rec.next_outcome()
        if isinstance(outcome, Exception):
            raise outcome
        return _Resp(outcome)


class _RecordingClient:
    """Records every ``schema().table()`` / ``schema().rpc()`` call and plays
    back queued outcomes (data or an exception)."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.schemas: list[str] = []
        self.tables: list[str] = []
        self.executed: list[tuple] = []

    def next_outcome(self):
        return self.outcomes.pop(0) if self.outcomes else []

    def schema(self, name: str):
        self.schemas.append(name)
        return self

    def table(self, name: str):
        self.tables.append(name)
        return _Query(self, name)

    def rpc(self, fn: str, params: dict):
        return _Query(self, None, (fn, params))


def _version_row(vid: UUID, status: str = "rascunho") -> dict:
    return {
        "id": str(vid), "org_id": str(ORG), "agent_id": str(uuid4()), "versao": 1, "status": status,
        "notas": None, "model": "claude-opus-5", "effort": "high", "max_turns": 40, "idioma": "pt-BR",
        "tool_policy": {"web_search": True, "knowledge": True}, "based_on_version_id": None,
        "created_by": str(USER), "published_by": None, "published_at": None, "compiled_hash": None,
        "eval_run_id": None, "publish_override_reason": None,
        "created_at": "2026-09-21T00:00:00+00:00", "updated_at": "2026-09-21T00:00:00+00:00",
    }


class TestSupabaseStore:
    def test_create_draft_calls_the_012_function(self):
        vid, agent_id, src = uuid4(), uuid4(), uuid4()
        client = _RecordingClient([str(vid), [_version_row(vid)]])
        rec = SupabaseStudioDefinitionStore(client).create_draft(ORG, agent_id, src, USER)
        _, rpc, _ = client.executed[0]
        assert rpc == ("create_agent_draft", {
            "p_org_id": str(ORG), "p_agent_id": str(agent_id),
            "p_source_version_id": str(src), "p_created_by": str(USER),
        })
        assert rec.id == vid
        assert set(client.schemas) == {"agents"}
        assert all("." not in t for t in client.tables)

    def test_publish_and_discard_params(self):
        vid, run = uuid4(), uuid4()
        client = _RecordingClient([None, [_version_row(vid, "ativa")], None])
        store = SupabaseStudioDefinitionStore(client)
        store.publish_version(ORG, vid, USER, run, None)
        store.discard_draft(ORG, vid)
        assert client.executed[0][1] == ("publish_agent_version", {
            "p_org_id": str(ORG), "p_version_id": str(vid), "p_published_by": str(USER),
            "p_eval_run_id": str(run), "p_override_reason": None,
        })
        assert client.executed[2][1] == ("discard_agent_draft", {"p_org_id": str(ORG), "p_version_id": str(vid)})

    @pytest.mark.parametrize(
        "error, expected, code",
        [
            (_APIError("P0001", "draft_exists"), StudioConflict, "draft_exists"),
            (_APIError("P0001", "version_immutable"), VersionImmutable, "version_immutable"),
            (_APIError("P0001", "agent_not_found"), NotFound, None),
            (_APIError("P0001", "version_not_found"), NotFound, None),
        ],
    )
    def test_rpc_errors_map_to_typed_errors(self, error, expected, code):
        client = _RecordingClient([error])
        with pytest.raises(expected) as exc:
            SupabaseStudioDefinitionStore(client).create_draft(ORG, uuid4(), None, USER)
        if code:
            assert exc.value.code == code

    def test_trigger_raise_on_child_write_maps_to_version_immutable(self):
        client = _RecordingClient([_APIError("P0001", "version_immutable")])
        with pytest.raises(VersionImmutable):
            SupabaseStudioDefinitionStore(client).create_skill(ORG, uuid4(), nome="s", descricao="d", corpo="c")

    def test_unique_violation_maps_to_the_route_code(self):
        client = _RecordingClient([_APIError("23505", "duplicate key value violates unique constraint")])
        with pytest.raises(StudioConflict) as exc:
            SupabaseStudioDefinitionStore(client).create_studio_agent(ORG, "isa", "Isa", None)
        assert exc.value.code == "key_taken"

    def test_unmapped_errors_propagate_unchanged(self):
        boom = _APIError("XX000", "something else")
        client = _RecordingClient([boom])
        with pytest.raises(_APIError) as exc:
            SupabaseStudioDefinitionStore(client).create_draft(ORG, uuid4(), None, USER)
        assert exc.value is boom

    def test_update_draft_on_published_row_is_immutable(self):
        vid = uuid4()
        # update ... .eq(status='rascunho') matches nothing; re-read shows ativa.
        client = _RecordingClient([[], [_version_row(vid, "ativa")]])
        with pytest.raises(VersionImmutable):
            SupabaseStudioDefinitionStore(client).update_draft(ORG, vid, {"notas": "x"})

    def test_reads_are_org_scoped_and_paged(self):
        client = _RecordingClient([[]])
        SupabaseStudioDefinitionStore(client).list_sections(ORG, uuid4())
        table, _, calls = client.executed[0]
        assert table == "agent_prompt_sections"
        names = [c[0] for c in calls]
        assert ("eq", ("org_id", str(ORG)), {}) in calls
        assert "range" in names
