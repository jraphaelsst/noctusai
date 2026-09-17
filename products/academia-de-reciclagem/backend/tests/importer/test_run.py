"""Tests for `app/importer/run.py` — the transactional import orchestrator.

Runs against A1's real in-memory `FakeKnowledgeStore` (`app.knowledge`,
contract §A.11). Assertions read the store through its per-table row lists
(`kb_entries`, `tasks`, `decisions`, …), `kb_revisions` and `code_counters`
— the Fake's own state — looked up by each entity's §A.11 natural key.
"""
import json

import pytest

from app.importer.bundle import BundleInvalid, BundleLine
from app.importer.run import run_import
from app.knowledge import FakeKnowledgeStore

ORG_ID = "org-1"
USER_ID = "user-1"

# entity_type -> (FakeKnowledgeStore attribute, natural-key column) per §A.11.
_NATURAL_KEY = {
    "kb_entry": ("kb_entries", "slug"),
    "decision": ("decisions", "codigo"),
    "open_question": ("open_questions", "codigo"),
    "task": ("tasks", "codigo"),
}

_ALL_TABLES = (
    "kb_entries",
    "decisions",
    "open_questions",
    "roadmap_phases",
    "tasks",
    "content_drafts",
    "timeline_events",
    "research_sources",
)


def _row(store, entity_type, key):
    table, column = _NATURAL_KEY[entity_type]
    matches = [r for r in getattr(store, table) if r.get(column) == key and r.get("org_id") == ORG_ID]
    assert len(matches) == 1, f"expected exactly one {entity_type} {key!r}, found {len(matches)}"
    return matches[0]


def _counters_for_org(store):
    return {key[1]: value for key, value in store.code_counters.items() if key[0] == ORG_ID}


def _line(path, content, *, git_sha, committed_at, author="Alguem", message="update"):
    return BundleLine(
        path=path,
        git_sha=git_sha,
        git_author_raw=author,
        git_committed_at=committed_at,
        git_message=message,
        content=content,
    )


class TestBasicImport:
    @pytest.mark.asyncio
    async def test_report_shape_and_counts(self):
        store = FakeKnowledgeStore()
        lines = [
            _line(
                "KNOWLEDGE-BASE/GERAL/foo.md",
                "# Foo\n\nCorpo.",
                git_sha="sha1",
                committed_at="2026-01-01T00:00:00Z",
            ),
            _line(
                "KNOWLEDGE-BASE/DECISOES/0001-decisoes.md",
                "---\ndata: 2026-01-02\n---\n"
                "| # | Decisão | Motivo |\n|---|---|---|\n"
                "| D-01 | Texto | Motivo |\n",
                git_sha="sha2",
                committed_at="2026-01-02T00:00:00Z",
            ),
        ]

        report = await run_import(store, ORG_ID, lines, USER_ID)

        assert report["verificacao"]["revisoes_git"] == 2
        assert report["verificacao"]["revisoes_importadas"] == 2
        assert report["verificacao"]["entidades"] == {"kb_entry": 1, "decision": 1}
        assert report["verificacao"]["hashes_head_ok"] is True
        assert report["verificacao"]["codigos"]["D"] == 1
        assert report["avisos"] == []

    @pytest.mark.asyncio
    async def test_writes_land_in_the_store(self):
        store = FakeKnowledgeStore()
        lines = [
            _line(
                "KNOWLEDGE-BASE/GERAL/foo.md",
                "# Foo\n\nCorpo.",
                git_sha="sha1",
                committed_at="2026-01-01T00:00:00Z",
            )
        ]
        await run_import(store, ORG_ID, lines, USER_ID)

        entry = _row(store, "kb_entry", "geral-foo")
        assert entry["titulo"] == "Foo"
        assert len(store.kb_revisions) == 1
        revision = store.kb_revisions[0]
        assert revision["entity_type"] == "kb_entry"
        assert revision["entity_id"] == entry["id"]
        assert revision["op"] == "import"
        assert revision["author_kind"] == "import"
        assert revision["user_id"] == USER_ID
        assert revision["git_sha"] == "sha1"


class TestCommitTimeOrdering:
    @pytest.mark.asyncio
    async def test_lines_are_processed_oldest_commit_first_regardless_of_input_order(self):
        store = FakeKnowledgeStore()
        # Two commits editing the SAME task, fed to run_import in REVERSE
        # chronological order. The stored row must reflect the NEWER
        # (later-committed) content, proving processing order is derived
        # from git_committed_at, not list order.
        older = json.dumps(
            [{"codigo": "T-001", "titulo": "versao antiga", "fase": "P1",
              "detalhe": None, "estado": "pendente", "bloqueada_por": None}]
        )
        newer = json.dumps(
            [{"codigo": "T-001", "titulo": "versao nova", "fase": "P1",
              "detalhe": None, "estado": "em-andamento", "bloqueada_por": None}]
        )
        lines = [
            _line("projects/state/tasks.json", newer, git_sha="sha-newer",
                  committed_at="2026-02-01T00:00:00Z"),
            _line("projects/state/tasks.json", older, git_sha="sha-older",
                  committed_at="2026-01-01T00:00:00Z"),
        ]

        await run_import(store, ORG_ID, lines, USER_ID)

        assert _row(store, "task", "T-001")["titulo"] == "versao nova"


class TestAllOrNothingTransaction:
    @pytest.mark.asyncio
    async def test_a_raising_line_rolls_back_every_prior_write(self):
        store = FakeKnowledgeStore()
        lines = [
            _line(
                "KNOWLEDGE-BASE/GERAL/foo.md",
                "# Foo\n\nCorpo.",
                git_sha="sha1",
                committed_at="2026-01-01T00:00:00Z",
            ),
            # Missing frontmatter 'codigo' -> map_line raises BundleInvalid
            # mid-transaction.
            _line(
                "KNOWLEDGE-BASE/DECISOES/0005-sem-codigo.md",
                "## Contexto\n\nSem frontmatter codigo.\n",
                git_sha="sha2",
                committed_at="2026-01-02T00:00:00Z",
            ),
        ]

        with pytest.raises(BundleInvalid):
            await run_import(store, ORG_ID, lines, USER_ID)

        for table in _ALL_TABLES:
            assert getattr(store, table) == [], f"{table} was not rolled back"
        assert store.kb_revisions == []
        assert _counters_for_org(store) == {}


class TestJsonDiffRule:
    @pytest.mark.asyncio
    async def test_only_changed_items_produce_revisions(self):
        store = FakeKnowledgeStore()
        # Commit 1: two tasks. Commit 2: T-001 unchanged, T-002 changed.
        commit1 = json.dumps(
            [
                {"codigo": "T-001", "titulo": "Tarefa A", "fase": "P1",
                 "detalhe": None, "estado": "pendente", "bloqueada_por": None},
                {"codigo": "T-002", "titulo": "Tarefa B", "fase": "P1",
                 "detalhe": None, "estado": "pendente", "bloqueada_por": None},
            ]
        )
        commit2 = json.dumps(
            [
                {"codigo": "T-001", "titulo": "Tarefa A", "fase": "P1",
                 "detalhe": None, "estado": "pendente", "bloqueada_por": None},
                {"codigo": "T-002", "titulo": "Tarefa B", "fase": "P1",
                 "detalhe": None, "estado": "concluida", "bloqueada_por": None},
            ]
        )
        lines = [
            _line("projects/state/tasks.json", commit1, git_sha="sha1",
                  committed_at="2026-01-01T00:00:00Z"),
            _line("projects/state/tasks.json", commit2, git_sha="sha2",
                  committed_at="2026-01-02T00:00:00Z"),
        ]

        report = await run_import(store, ORG_ID, lines, USER_ID)

        # commit1: 2 revisions (T-001, T-002 first seen).
        # commit2: only T-002 changed -> 1 more revision. T-001 unchanged -> 0.
        assert report["verificacao"]["revisoes_importadas"] == 3
        assert report["verificacao"]["entidades"] == {"task": 3}
        assert len([r for r in store.kb_revisions if r["entity_type"] == "task"]) == 3
        assert _row(store, "task", "T-002")["estado"] == "concluida"


class TestCodeCounterSeeding:
    @pytest.mark.asyncio
    async def test_seeds_max_d_q_t_codes_seen(self):
        store = FakeKnowledgeStore()
        decision_content = (
            "---\ncodigo: D-07\ntitulo: X\ndata: 2026-01-01\nestado: vigente\n---\n"
            "## Decisão\n\nFazer X.\n\n## Motivo\n\nPorque sim.\n"
        )
        question_content = json.dumps(
            [{"codigo": "Q-03", "pergunta": "P?", "por_que_importa": "Importa",
              "bloqueia": "Nada", "destino_kb": None, "estado": "aberta",
              "resposta": None, "respondida_em": None}]
        )
        task_content = json.dumps(
            [{"codigo": "T-042", "titulo": "Y", "fase": "P1", "detalhe": None,
              "estado": "pendente", "bloqueada_por": None}]
        )
        lines = [
            _line("KNOWLEDGE-BASE/DECISOES/0007-x.md", decision_content,
                  git_sha="sha1", committed_at="2026-01-01T00:00:00Z"),
            _line("projects/state/open-questions.json", question_content,
                  git_sha="sha2", committed_at="2026-01-02T00:00:00Z"),
            _line("projects/state/tasks.json", task_content,
                  git_sha="sha3", committed_at="2026-01-03T00:00:00Z"),
        ]

        report = await run_import(store, ORG_ID, lines, USER_ID)

        assert report["verificacao"]["codigos"] == {"D": 7, "Q": 3, "T": 42}
        assert _counters_for_org(store) == {"D": 7, "Q": 3, "T": 42}


class TestWarnings:
    @pytest.mark.asyncio
    async def test_unmapped_path_produces_a_warning_not_an_error(self):
        store = FakeKnowledgeStore()
        lines = [
            _line("README.md", "# README\n\nQualquer coisa.", git_sha="sha1",
                  committed_at="2026-01-01T00:00:00Z"),
        ]
        report = await run_import(store, ORG_ID, lines, USER_ID)
        assert report["verificacao"]["revisoes_importadas"] == 0
        assert len(report["avisos"]) == 1
        assert "README.md" in report["avisos"][0]
        assert store.kb_revisions == []


class TestIdempotentReplay:
    @pytest.mark.asyncio
    async def test_rerunning_the_same_bundle_writes_no_additional_revisions(self):
        store = FakeKnowledgeStore()
        lines = [
            _line(
                "KNOWLEDGE-BASE/GERAL/foo.md",
                "# Foo\n\nCorpo.",
                git_sha="sha1",
                committed_at="2026-01-01T00:00:00Z",
            )
        ]

        await run_import(store, ORG_ID, lines, USER_ID)
        revisions_after_first_run = len(store.kb_revisions)

        await run_import(store, ORG_ID, lines, USER_ID)
        revisions_after_second_run = len(store.kb_revisions)

        assert revisions_after_first_run == 1
        assert revisions_after_second_run == revisions_after_first_run
        assert len(store.kb_entries) == 1


class TestFakeRefusesWhatPostgresRefuses:
    """The fake store must refuse a NULL in a NOT NULL column, as the real
    `import_bundle` RPC does (23502) — the first prod import failed on an
    untitled timeline section the fake had accepted."""

    @pytest.mark.asyncio
    async def test_a_decision_without_decisao_or_motivo_is_refused(self):
        from app.knowledge.errors import Invalid

        store = FakeKnowledgeStore()
        content = "---\ncodigo: D-09\ntitulo: X\ndata: 2026-01-01\n---\nsem secoes\n"
        lines = [_line("KNOWLEDGE-BASE/DECISOES/0009-x.md", content,
                       git_sha="sha1", committed_at="2026-01-01T00:00:00Z")]
        with pytest.raises(Invalid, match="decisao"):
            await run_import(store, ORG_ID, lines, USER_ID)

    @pytest.mark.asyncio
    async def test_an_untitled_timeline_section_imports(self):
        store = FakeKnowledgeStore()
        content = "## 2026-09-12\n\n- **Endurecimento do P2 — detalhe**\n"
        lines = [_line("KNOWLEDGE-BASE/HISTORICO/TIMELINE.md", content,
                       git_sha="sha1", committed_at="2026-01-01T00:00:00Z")]
        await run_import(store, ORG_ID, lines, USER_ID)
        assert [e["titulo"] for e in store.timeline_events] == ["Endurecimento do P2"]
