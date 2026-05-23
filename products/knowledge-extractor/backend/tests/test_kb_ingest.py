"""Tests for the KB ingestion pipeline (app/services/kb_ingest.py).

Strategy: FakeVectorStore + deterministic fake embed_fn — no network, no OpenAI,
no Supabase, no real methodology files.

All methodology content is created in tmp_path fixtures.

Covers:
  - ingest_methodology returns correct documents/chunks_ingested counts.
  - Sections are chunked by H1/H2/H3 headings.
  - Clean chunks are embedded and upserted.
  - A chunk containing a policy violation (e.g. "@handle" or "10 mil seguidores")
    is SKIPPED and NOT stored.
  - _FRONT.md / _BACK.md are excluded.
  - Non-.md files are excluded.
  - Empty methodology dir raises FileNotFoundError.
  - Chunks with the same id from re-ingest overwrite (idempotent).
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from app.integrations.vectors.fake import FakeVectorStore
from app.services.kb_ingest import (
    _chunk_markdown,
    _collect_methodology_files,
    _is_included,
    ingest_methodology,
)


# ---------------------------------------------------------------------------
# Deterministic fake embed_fn
# ---------------------------------------------------------------------------

_EMBED_DIMS = 8


async def _fake_embed(text: str) -> list[float]:
    """Deterministic embedding: first 8 chars' ordinals, L2-normalised."""
    import math
    raw = [float(ord(c)) for c in (text + "\x00" * _EMBED_DIMS)[:_EMBED_DIMS]]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return [x / norm for x in raw]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLEAN_DOC = textwrap.dedent("""\
    # Metodologia de Conteúdo

    ## Os 7 gatilhos de atenção

    O método baseia-se nos primeiros 3 segundos do vídeo.

    ## Framework de criação

    1. Identifique o assunto viral usando os 5 passos.
    2. Aplique os 32 templates disponíveis.
""")

LEAKY_DOC = textwrap.dedent("""\
    # Módulo Exemplo

    ## Resultados obtidos

    Usando o método o @perfil_aluno chegou a 10 mil seguidores em um mês.
""")

ANOTHER_CLEAN_DOC = textwrap.dedent("""\
    # Estruturas de Post

    ## Template 01 — Conselho direto

    Seja específico em [área]. A ordem direta sem rodeios transmite liderança.

    ## Template 02 — Contraste

    Coisas que parecem [positivo] mas causam [negativo].
""")


def _write_methodology(tmp_path: Path, files: dict[str, str]) -> Path:
    """Write methodology files to ``tmp_path/methodology/`` and return the data dir."""
    method_dir = tmp_path / "methodology"
    method_dir.mkdir(parents=True)
    for name, content in files.items():
        (method_dir / name).write_text(content, encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Unit: _is_included
# ---------------------------------------------------------------------------

class TestIsIncluded:
    def test_normal_md_included(self, tmp_path: Path) -> None:
        f = tmp_path / "modulo-1.md"
        f.touch()
        assert _is_included(f) is True

    def test_front_excluded(self, tmp_path: Path) -> None:
        f = tmp_path / "_FRONT.md"
        f.touch()
        assert _is_included(f) is False

    def test_back_excluded(self, tmp_path: Path) -> None:
        f = tmp_path / "_BACK.md"
        f.touch()
        assert _is_included(f) is False

    def test_non_md_excluded(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.touch()
        assert _is_included(f) is False

    def test_special_files_included(self, tmp_path: Path) -> None:
        for name in ("ESTRUTURAS-DE-POST.md", "REFERENCIAS.md", "ESQUEMA-BASE-DE-CONHECIMENTO.md"):
            f = tmp_path / name
            f.touch()
            assert _is_included(f) is True, name


# ---------------------------------------------------------------------------
# Unit: _collect_methodology_files
# ---------------------------------------------------------------------------

class TestCollectMethodologyFiles:
    def test_collects_md_excludes_underscored(self, tmp_path: Path) -> None:
        method_dir = tmp_path / "methodology"
        method_dir.mkdir()
        (method_dir / "module-1.md").write_text("content")
        (method_dir / "_FRONT.md").write_text("front")
        (method_dir / "data.csv").write_text("csv")
        files = _collect_methodology_files(method_dir)
        names = [f.name for f in files]
        assert "module-1.md" in names
        assert "_FRONT.md" not in names
        assert "data.csv" not in names

    def test_missing_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Methodology directory"):
            _collect_methodology_files(tmp_path / "nonexistent")


# ---------------------------------------------------------------------------
# Unit: _chunk_markdown
# ---------------------------------------------------------------------------

class TestChunkMarkdown:
    def test_no_headings(self) -> None:
        chunks = _chunk_markdown("Plain text without any headings.")
        assert len(chunks) == 1
        assert chunks[0] == "Plain text without any headings."

    def test_empty(self) -> None:
        assert _chunk_markdown("") == []
        assert _chunk_markdown("   \n  ") == []

    def test_splits_on_h1(self) -> None:
        text = "# Section A\n\nBody A.\n\n# Section B\n\nBody B."
        chunks = _chunk_markdown(text)
        assert len(chunks) == 2
        assert chunks[0].startswith("# Section A")
        assert chunks[1].startswith("# Section B")

    def test_splits_on_h2(self) -> None:
        text = "## Alpha\n\nContent alpha.\n\n## Beta\n\nContent beta."
        chunks = _chunk_markdown(text)
        assert len(chunks) == 2

    def test_preamble_kept(self) -> None:
        text = "Intro text before heading.\n\n# Section\n\nContent."
        chunks = _chunk_markdown(text)
        assert len(chunks) == 2
        assert chunks[0].startswith("Intro text")

    def test_h4_not_split(self) -> None:
        """H4+ should NOT split — they stay within their parent section."""
        text = "## Section\n\nBody.\n\n#### Deep subsection\n\nDeep content."
        chunks = _chunk_markdown(text)
        # H4 is NOT a split point; the whole section is one chunk
        assert len(chunks) == 1
        assert "Deep subsection" in chunks[0]

    def test_whitespace_chunks_dropped(self) -> None:
        text = "## Alpha\n\n   \n\n## Beta\n\nContent."
        chunks = _chunk_markdown(text)
        # "## Alpha\n\n   " collapses to just the heading — still kept
        # "## Beta\n\nContent." is kept
        assert all(c.strip() for c in chunks)


# ---------------------------------------------------------------------------
# Integration: ingest_methodology
# ---------------------------------------------------------------------------

class TestIngestMethodology:
    @pytest.mark.asyncio
    async def test_basic_ingest(self, tmp_path: Path) -> None:
        data_dir = _write_methodology(tmp_path, {"modulo-1.md": CLEAN_DOC})
        store = FakeVectorStore()
        result = await ingest_methodology(data_dir, store=store, embed_fn=_fake_embed)

        assert result["documents"] == 1
        assert result["chunks_ingested"] > 0
        assert result["chunks_skipped"] == 0
        assert len(store) == result["chunks_ingested"]

    @pytest.mark.asyncio
    async def test_multiple_files(self, tmp_path: Path) -> None:
        data_dir = _write_methodology(
            tmp_path,
            {
                "modulo-1.md": CLEAN_DOC,
                "ESTRUTURAS-DE-POST.md": ANOTHER_CLEAN_DOC,
            },
        )
        store = FakeVectorStore()
        result = await ingest_methodology(data_dir, store=store, embed_fn=_fake_embed)

        assert result["documents"] == 2
        assert result["chunks_ingested"] > 0

    @pytest.mark.asyncio
    async def test_excluded_files_not_ingested(self, tmp_path: Path) -> None:
        """_FRONT.md and _BACK.md must never appear in the store."""
        data_dir = _write_methodology(
            tmp_path,
            {
                "modulo-1.md": CLEAN_DOC,
                "_FRONT.md": "Front matter with @handle and 10 mil seguidores.",
                "_BACK.md": "Back matter — excluded.",
                "notes.txt": "Plain text file — excluded.",
            },
        )
        store = FakeVectorStore()
        result = await ingest_methodology(data_dir, store=store, embed_fn=_fake_embed)

        assert result["documents"] == 1  # only modulo-1.md
        for chunk_id in store.stored_ids():
            assert "_FRONT" not in chunk_id
            assert "_BACK" not in chunk_id

    @pytest.mark.asyncio
    async def test_leaky_chunk_skipped(self, tmp_path: Path) -> None:
        """A chunk with policy violations (@handle, result numbers) must be SKIPPED."""
        data_dir = _write_methodology(
            tmp_path,
            {"leaky-module.md": LEAKY_DOC},
        )
        store = FakeVectorStore()
        result = await ingest_methodology(data_dir, store=store, embed_fn=_fake_embed)

        # The leaky section "## Resultados obtidos" contains "@perfil_aluno"
        # and "10 mil seguidores" — both trigger the anonymization guard.
        assert result["chunks_skipped"] > 0
        # Ensure the leaky content is NOT in the store
        for chunk_id, (chunk, _) in store._store.items():
            assert "@perfil_aluno" not in chunk.content
            assert "10 mil seguidores" not in chunk.content

    @pytest.mark.asyncio
    async def test_handle_leak_skipped(self, tmp_path: Path) -> None:
        """@handle alone is enough to skip the chunk."""
        doc = textwrap.dedent("""\
            # Módulo Teste

            ## Seção limpa

            Este conteúdo não tem violações.

            ## Seção com handle

            Veja o @perfil_exemplo para referência.
        """)
        data_dir = _write_methodology(tmp_path, {"teste.md": doc})
        store = FakeVectorStore()
        result = await ingest_methodology(data_dir, store=store, embed_fn=_fake_embed)

        assert result["chunks_skipped"] >= 1
        # The clean section must still be ingested
        assert result["chunks_ingested"] >= 1
        # The leaky section must NOT be in the store
        for cid, (chunk, _) in store._store.items():
            assert "@perfil_exemplo" not in chunk.content

    @pytest.mark.asyncio
    async def test_result_number_leak_skipped(self, tmp_path: Path) -> None:
        """Result numbers like '10 mil seguidores' trigger the guard."""
        doc = textwrap.dedent("""\
            # Módulo Resultados

            ## Método

            Use os 7 gatilhos nos primeiros 3 segundos.

            ## Caso com número proibido

            Quem aplica esse método chega a 10 mil seguidores em 30 dias.
        """)
        data_dir = _write_methodology(tmp_path, {"resultados.md": doc})
        store = FakeVectorStore()
        result = await ingest_methodology(data_dir, store=store, embed_fn=_fake_embed)

        assert result["chunks_skipped"] >= 1
        for cid, (chunk, _) in store._store.items():
            assert "10 mil seguidores" not in chunk.content

    @pytest.mark.asyncio
    async def test_query_returns_ranked_hits(self, tmp_path: Path) -> None:
        """After ingest, querying with an embedded phrase should return ranked hits."""
        data_dir = _write_methodology(tmp_path, {"modulo-1.md": CLEAN_DOC})
        store = FakeVectorStore()
        await ingest_methodology(data_dir, store=store, embed_fn=_fake_embed)

        # Use the same embed_fn to get a query vector — hits should be non-empty.
        query_emb = await _fake_embed("gatilhos de atenção")
        hits = await store.query(query_emb, k=3)
        assert len(hits) >= 1
        # All hits must have a similarity in [0, 1]
        for h in hits:
            assert 0.0 <= h.score <= 1.0 + 1e-9

    @pytest.mark.asyncio
    async def test_ingest_is_idempotent(self, tmp_path: Path) -> None:
        """Running ingest twice should not grow the store (same ids overwrite)."""
        data_dir = _write_methodology(tmp_path, {"modulo-1.md": CLEAN_DOC})
        store = FakeVectorStore()
        r1 = await ingest_methodology(data_dir, store=store, embed_fn=_fake_embed)
        size_after_first = len(store)

        r2 = await ingest_methodology(data_dir, store=store, embed_fn=_fake_embed)
        size_after_second = len(store)

        assert size_after_first == size_after_second
        assert r1["chunks_ingested"] == r2["chunks_ingested"]

    @pytest.mark.asyncio
    async def test_missing_methodology_dir_raises(self, tmp_path: Path) -> None:
        store = FakeVectorStore()
        with pytest.raises(FileNotFoundError, match="Methodology directory"):
            await ingest_methodology(tmp_path, store=store, embed_fn=_fake_embed)
