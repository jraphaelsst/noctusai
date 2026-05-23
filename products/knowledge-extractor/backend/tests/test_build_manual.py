"""Tests for the deterministic manual assembler (no LLM, no network)."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.methodology_service import assemble_manual_from_files, build_manual


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def methodology_dir(tmp_path: Path) -> Path:
    """A minimal fixture data_dir with _FRONT, two numbered modules, and _BACK."""
    data_dir = tmp_path / "data"
    meth_dir = data_dir / "methodology"
    meth_dir.mkdir(parents=True)

    (meth_dir / "_FRONT.md").write_text(
        "# Manual de Teste\n\n## Visão Geral\nConteúdo do front.\n\n---",
        encoding="utf-8",
    )

    (meth_dir / "1 MODULO UM.md").write_text(
        "# Módulo 1\n\nConteúdo do módulo um.",
        encoding="utf-8",
    )

    (meth_dir / "2-MODULO-DOIS.md").write_text(
        "# Módulo 2\n\nConteúdo do módulo dois.",
        encoding="utf-8",
    )

    (meth_dir / "ESTRUTURAS-DE-POST.md").write_text(
        "# Catálogo de Estruturas de Post\n\nConteúdo das estruturas.",
        encoding="utf-8",
    )

    (meth_dir / "REFERENCIAS.md").write_text(
        "# Referências\n\nBase bibliográfica.",
        encoding="utf-8",
    )

    (meth_dir / "ESQUEMA-BASE-DE-CONHECIMENTO.md").write_text(
        "# Esquema\n\nEsquema da base de conhecimento.",
        encoding="utf-8",
    )

    (meth_dir / "_BACK.md").write_text(
        "## Ética e durabilidade\n\nConteúdo do back.\n\n---\n\n## Procedência\n\nComo foi feito.",
        encoding="utf-8",
    )

    return data_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAssembleManualFromFiles:
    def test_front_precedes_detalhamento(self, methodology_dir: Path) -> None:
        """_FRONT.md content must appear before '# Detalhamento por Módulo'."""
        result = assemble_manual_from_files(methodology_dir)
        front_pos = result.index("# Manual de Teste")
        detalhamento_pos = result.index("# Detalhamento por Módulo")
        assert front_pos < detalhamento_pos

    def test_detalhamento_contains_both_modules(self, methodology_dir: Path) -> None:
        """Both numbered module files must appear in the Detalhamento section."""
        result = assemble_manual_from_files(methodology_dir)
        detalhamento_pos = result.index("# Detalhamento por Módulo")
        after = result[detalhamento_pos:]
        assert "Conteúdo do módulo um." in after
        assert "Conteúdo do módulo dois." in after

    def test_numeric_ordering(self, methodology_dir: Path) -> None:
        """Module 1 must appear before Module 2 in the output."""
        result = assemble_manual_from_files(methodology_dir)
        pos1 = result.index("Conteúdo do módulo um.")
        pos2 = result.index("Conteúdo do módulo dois.")
        assert pos1 < pos2

    def test_excluded_files_not_in_detalhamento(self, methodology_dir: Path) -> None:
        """_FRONT, _BACK, REFERENCIAS, ESQUEMA-* must NOT appear in Detalhamento section."""
        result = assemble_manual_from_files(methodology_dir)
        detalhamento_pos = result.index("# Detalhamento por Módulo")
        # The next top-level section after Detalhamento is _BACK's content
        back_pos = result.index("## Ética e durabilidade")
        detalhamento_body = result[detalhamento_pos:back_pos]

        assert "Base bibliográfica." not in detalhamento_body
        assert "Esquema da base de conhecimento." not in detalhamento_body

    def test_estruturas_in_appendix(self, methodology_dir: Path) -> None:
        """ESTRUTURAS-DE-POST.md must appear after the last numbered module."""
        result = assemble_manual_from_files(methodology_dir)
        pos_mod2 = result.index("Conteúdo do módulo dois.")
        pos_estruturas = result.index("Catálogo de Estruturas de Post")
        assert pos_mod2 < pos_estruturas

    def test_back_at_end(self, methodology_dir: Path) -> None:
        """_BACK.md content (Ética e Procedência) must appear after Detalhamento."""
        result = assemble_manual_from_files(methodology_dir)
        detalhamento_pos = result.index("# Detalhamento por Módulo")
        back_pos = result.index("## Ética e durabilidade")
        assert detalhamento_pos < back_pos

    def test_deterministic_same_output_twice(self, methodology_dir: Path) -> None:
        """Calling assemble_manual_from_files twice must return identical strings."""
        first = assemble_manual_from_files(methodology_dir)
        second = assemble_manual_from_files(methodology_dir)
        assert first == second

    def test_missing_front_raises(self, tmp_path: Path) -> None:
        """Missing _FRONT.md must raise FileNotFoundError."""
        data_dir = tmp_path / "data"
        (data_dir / "methodology").mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="_FRONT.md"):
            assemble_manual_from_files(data_dir)


class TestBuildManual:
    def test_writes_methodology_md(self, methodology_dir: Path) -> None:
        """build_manual must write data/METHODOLOGY.md and return its path."""
        out_path = build_manual(methodology_dir)
        assert out_path == methodology_dir / "METHODOLOGY.md"
        assert out_path.exists()

    def test_idempotent(self, methodology_dir: Path) -> None:
        """Calling build_manual twice must produce identical file contents."""
        path1 = build_manual(methodology_dir)
        content1 = path1.read_text(encoding="utf-8")
        path2 = build_manual(methodology_dir)
        content2 = path2.read_text(encoding="utf-8")
        assert content1 == content2

    def test_written_content_matches_assembler(self, methodology_dir: Path) -> None:
        """build_manual file content must match assemble_manual_from_files output."""
        expected = assemble_manual_from_files(methodology_dir)
        out_path = build_manual(methodology_dir)
        assert out_path.read_text(encoding="utf-8") == expected
