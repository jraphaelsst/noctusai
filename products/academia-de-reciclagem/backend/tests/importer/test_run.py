"""Tests for `app/importer/run.py` — the transactional import orchestrator.

Uses the local `_fake_store.FakeKnowledgeStore` stand-in (see that
module's docstring) since `app/knowledge/` (A1) does not exist on this
branch yet.
"""
import json

import pytest

from app.importer.bundle import BundleInvalid, BundleLine
from app.importer.run import run_import
from tests.importer._fake_store import FakeKnowledgeStore

ORG_ID = "org-1"
USER_ID = "user-1"


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
        assert ("kb_entry", "geral-foo") in store.entities
        assert store.entities[("kb_entry", "geral-foo")]["titulo"] == "Foo"
        assert len(store.revisions) == 1
        assert store.revisions[0]["author_kind"] == "import"
        assert store.revisions[0]["user_id"] == USER_ID


class TestCommitTimeOrdering:
    @pytest.mark.asyncio
    async def test_lines_are_processed_oldest_commit_first_regardless_of_input_order(self):
        store = FakeKnowledgeStore()
        # Two commits editing the SAME task, fed to run_import in REVERSE
        # chronological order. The stored snapshot must reflect the
        # NEWER (later-committed) content, proving processing order is
        # derived from git_committed_at, not list order.
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

        assert store.entities[("task", "T-001")]["titulo"] == "versao nova"


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

        assert store.entities == {}
        assert store.revisions == []


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
        assert store.entities[("task", "T-002")]["estado"] == "concluida"


class TestCodeCounterSeeding:
    @pytest.mark.asyncio
    async def test_seeds_max_d_q_t_codes_seen(self):
        store = FakeKnowledgeStore()
        decision_content = (
            "---\ncodigo: D-07\ntitulo: X\ndata: 2026-01-01\nestado: vigente\n---\n"
        )
        question_content = json.dumps(
            [{"codigo": "Q-03", "pergunta": "P?", "por_que_importa": "Importa",
              "bloqueia": None, "destino_kb": None, "estado": "aberta",
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
        assert store.counters == {"D": 7, "Q": 3, "T": 42}


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
        revisions_after_first_run = len(store.revisions)

        await run_import(store, ORG_ID, lines, USER_ID)
        revisions_after_second_run = len(store.revisions)

        assert revisions_after_first_run == 1
        assert revisions_after_second_run == revisions_after_first_run
