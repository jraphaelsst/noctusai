"""Tests for the anonymization guard (app/services/anonymization.py).

Strategy: fake-driven, no network, no filesystem I/O (scan_text used directly
for unit tests; scan_paths tested with tmp_path fixtures).

Policy under test (from methodology_service._POLICY):
  - No @handles.
  - No R$ figures.
  - No result-performance numbers (seguidores, views, faturamento, etc.).
  - No denylist brands ("CORE Educação").
  - Intrinsic-method numbers ("3 segundos", "7 gatilhos", …) must NOT be flagged.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.services.anonymization import Finding, scan_paths, scan_text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CLEAN_METHODOLOGY_TEXT = textwrap.dedent("""\
    # Metodologia de conteúdo

    ## Os 7 gatilhos de atenção

    O método baseia-se nos primeiros 3 segundos do vídeo para capturar atenção.
    Use os 7 gatilhos de forma estratégica ao longo do conteúdo.

    ## Framework de criação

    1. Identifique o assunto viral usando os 5 passos de pesquisa.
    2. Construa a headline com a fórmula dos 3 elementos.
    3. Aplique os 32 templates disponíveis no banco de padrões.

    ## Princípios de posicionamento

    A identidade de marca deve ser construída em torno de um núcleo de influência.
    Utilize os 3 pilares do método para guiar cada decisão de conteúdo.
    Aplique a regra dos 2 estágios de revisão antes de publicar.
""")

LEAKY_TEXT = textwrap.dedent("""\
    # Resultados e exemplos

    O criador @joao_influencer alcançou 10 mil seguidores em 30 dias.
    O faturamento foi de R$ 50.000 no primeiro mês.
    A CORE Educação recomenda esta abordagem.
    Crescimento de 200% em inscritos no canal.
""")


# ---------------------------------------------------------------------------
# Clean text — zero findings
# ---------------------------------------------------------------------------

class TestCleanText:
    def test_no_findings_on_clean_methodology(self):
        findings = scan_text(CLEAN_METHODOLOGY_TEXT)
        assert findings == [], (
            f"Expected zero findings on clean text, got: {findings}"
        )

    def test_intrinsic_3_segundos_not_flagged(self):
        findings = scan_text("Os primeiros 3 segundos são críticos.")
        assert findings == []

    def test_intrinsic_7_gatilhos_not_flagged(self):
        findings = scan_text("Use os 7 gatilhos de atenção.")
        assert findings == []

    def test_intrinsic_32_templates_not_flagged(self):
        findings = scan_text("Há 32 templates disponíveis.")
        assert findings == []

    def test_intrinsic_5_passos_not_flagged(self):
        findings = scan_text("Siga os 5 passos do método.")
        assert findings == []

    def test_intrinsic_3_pilares_not_flagged(self):
        findings = scan_text("Os 3 pilares do método são fundamentais.")
        assert findings == []

    def test_intrinsic_3_elementos_not_flagged(self):
        findings = scan_text("A fórmula tem 3 elementos essenciais.")
        assert findings == []

    def test_plain_number_prose_not_flagged(self):
        # A plain number with no result noun should not fire.
        findings = scan_text("Existem 12 formas de abordagem.")
        assert findings == []

    def test_percent_without_result_context_not_flagged(self):
        # "50% do tempo" is a method ratio, not a result.
        findings = scan_text("Dedique 50% do tempo à pesquisa de assuntos.")
        assert findings == []


# ---------------------------------------------------------------------------
# Leaky text — all violations must be caught
# ---------------------------------------------------------------------------

class TestLeakyText:
    def _kinds(self, text: str, **kw) -> list[str]:
        return [f.kind for f in scan_text(text, **kw)]

    def test_handle_caught(self):
        findings = scan_text("Siga @joao_influencer para mais dicas.")
        kinds = [f.kind for f in findings]
        assert "handle" in kinds

    def test_handle_match_value(self):
        findings = scan_text("Contato: @nome_perfil.")
        handles = [f for f in findings if f.kind == "handle"]
        assert len(handles) == 1
        assert handles[0].match == "@nome_perfil"

    def test_currency_result_caught(self):
        findings = scan_text("Faturou R$ 50.000 no mês.")
        kinds = [f.kind for f in findings]
        assert "currency_result" in kinds

    def test_currency_result_no_space(self):
        findings = scan_text("Receita de R$12.000.")
        kinds = [f.kind for f in findings]
        assert "currency_result" in kinds

    def test_seguidores_result_caught(self):
        findings = scan_text("Chegou a 10 mil seguidores em 30 dias.")
        kinds = [f.kind for f in findings]
        assert "result_number" in kinds

    def test_views_result_caught(self):
        findings = scan_text("O vídeo teve 500k views.")
        kinds = [f.kind for f in findings]
        assert "result_number" in kinds

    def test_inscritos_result_caught(self):
        findings = scan_text("Canal com 200 mil inscritos.")
        kinds = [f.kind for f in findings]
        assert "result_number" in kinds

    def test_visualizacoes_result_caught(self):
        findings = scan_text("Acumulou 1,5 M de visualizações.")
        kinds = [f.kind for f in findings]
        assert "result_number" in kinds

    def test_faturamento_result_caught(self):
        findings = scan_text("Faturamento de 100 mil reais.")
        # Either as result_number (noun before number) or currency_result
        kinds = [f.kind for f in findings]
        assert "result_number" in kinds or "currency_result" in kinds

    def test_crescimento_percent_caught(self):
        findings = scan_text("Crescimento de 200% em inscritos no canal.")
        kinds = [f.kind for f in findings]
        assert "result_percent" in kinds or "result_number" in kinds

    def test_denylist_brand_caught(self):
        findings = scan_text("A CORE Educação recomenda.", denylist=None)
        kinds = [f.kind for f in findings]
        assert "denylist_brand" in kinds

    def test_denylist_brand_ascii_variant_caught(self):
        findings = scan_text("Parceria com CORE Educacao.")
        kinds = [f.kind for f in findings]
        assert "denylist_brand" in kinds

    def test_custom_denylist_caught(self):
        findings = scan_text("Empresa MarcaXYZ fez parceria.", denylist=["MarcaXYZ"])
        kinds = [f.kind for f in findings]
        assert "denylist_brand" in kinds

    def test_full_leaky_text_catches_all_categories(self):
        findings = scan_text(LEAKY_TEXT)
        kinds = {f.kind for f in findings}
        assert "handle" in kinds, f"handle not found in {kinds}"
        assert "result_number" in kinds, f"result_number not found in {kinds}"
        assert "currency_result" in kinds, f"currency_result not found in {kinds}"
        assert "denylist_brand" in kinds, f"denylist_brand not found in {kinds}"

    def test_finding_line_number(self):
        text = "Linha 1\n@handle_aqui\nLinha 3"
        findings = scan_text(text)
        handles = [f for f in findings if f.kind == "handle"]
        assert handles[0].line == 2

    def test_finding_context_is_stripped_line(self):
        text = "   @usuario_teste   "
        findings = scan_text(text)
        assert findings[0].context == "@usuario_teste"


# ---------------------------------------------------------------------------
# scan_paths — filesystem integration
# ---------------------------------------------------------------------------

class TestScanPaths:
    def test_scans_md_file(self, tmp_path: Path):
        md = tmp_path / "test.md"
        md.write_text("Canal com 50k seguidores.", encoding="utf-8")
        result = scan_paths([md])
        assert str(md) in result
        assert any(f.kind == "result_number" for f in result[str(md)])

    def test_scans_txt_file(self, tmp_path: Path):
        txt = tmp_path / "notes.txt"
        txt.write_text("@meu_perfil aqui.", encoding="utf-8")
        result = scan_paths([txt])
        assert str(txt) in result
        assert any(f.kind == "handle" for f in result[str(txt)])

    def test_skips_non_scannable_suffix(self, tmp_path: Path):
        docx = tmp_path / "doc.docx"
        # Write a fake docx (doesn't need to be real, just has .docx suffix)
        docx.write_bytes(b"PK\x03\x04fake docx bytes @handle")
        result = scan_paths([docx])
        # .docx is not in _SCANNABLE_SUFFIXES → skipped entirely
        assert str(docx) not in result

    def test_skips_binary_md_file(self, tmp_path: Path):
        # A .md file with a ZIP/PK magic header should be skipped.
        fake_bin = tmp_path / "weird.md"
        fake_bin.write_bytes(b"PK\x03\x04" + b"@handle")
        result = scan_paths([fake_bin])
        assert str(fake_bin) not in result

    def test_clean_file_present_with_empty_findings(self, tmp_path: Path):
        md = tmp_path / "clean.md"
        md.write_text(CLEAN_METHODOLOGY_TEXT, encoding="utf-8")
        result = scan_paths([md])
        assert str(md) in result
        assert result[str(md)] == []

    def test_multiple_paths(self, tmp_path: Path):
        clean = tmp_path / "clean.md"
        clean.write_text("Conteúdo limpo sem violações.", encoding="utf-8")
        leaky = tmp_path / "leaky.md"
        leaky.write_text("@perfil_vazou aqui.", encoding="utf-8")
        result = scan_paths([clean, leaky])
        assert result[str(clean)] == []
        assert any(f.kind == "handle" for f in result[str(leaky)])

    def test_accepts_string_paths(self, tmp_path: Path):
        md = tmp_path / "str_path.md"
        md.write_text("Texto limpo.", encoding="utf-8")
        result = scan_paths([str(md)])
        assert str(md) in result


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

class TestFindingDataclass:
    def test_finding_fields(self):
        f = Finding(kind="handle", match="@x", line=1, context="texto @x aqui")
        assert f.kind == "handle"
        assert f.match == "@x"
        assert f.line == 1
        assert f.context == "texto @x aqui"

    def test_finding_equality(self):
        f1 = Finding(kind="handle", match="@x", line=1, context="ctx")
        f2 = Finding(kind="handle", match="@x", line=1, context="ctx")
        assert f1 == f2
