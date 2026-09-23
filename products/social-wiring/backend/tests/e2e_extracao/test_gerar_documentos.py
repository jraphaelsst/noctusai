"""Asserts `gerar_documentos.py` produces a complete, well-formed fixture
set — NOT that a live extractor reads it correctly (that is `verificar.py`'s
job, against a real database; this test is offline and reads no network).

Skips (does not fail) when `reportlab` / `fitz` (PyMuPDF) are not installed
in the current interpreter — both are backend runtime dependencies
(`products/social-wiring/backend/requirements.txt`), not seed/test
dependencies, so a bare `noctus.dev.pytest` run of a venv that never
installed the social-wiring backend's own requirements must not report a
false red for a missing THIRD-PARTY package this suite does not own.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("reportlab", reason="social-wiring backend runtime dep, not a seed/test dep")
pytest.importorskip("fitz", reason="social-wiring backend runtime dep (PyMuPDF), not a seed/test dep")

sys.path.insert(0, str(Path(__file__).parent))
import gerar_documentos as gd  # noqa: E402  (path insert must precede this)


# Every contract cell the sw-extraction-contract-gate-2026-09 roadmap's
# shared field-state-contract table names for a FILE-derived source (the
# manual-only fields listed in the roadmap's own "Manual-only contract
# data" section, and `clientes.certidao_estado_civil_emitida_em`, which
# migration 148 states in so many words is "never written by extraction",
# are correctly absent from this list).
CAMPOS_CONTRATO_POR_ARQUIVO = {
    "clientes.nome_oficial", "clientes.cpf", "clientes.rg",
    "clientes.rg_orgao_expedidor", "clientes.data_nascimento",
    "clientes.genero", "clientes.estado_civil", "clientes.regime_bens",
    "clientes.data_casamento", "clientes.nacionalidade",
    "clientes.endereco_cep", "clientes.endereco_logradouro",
    "clientes.endereco_numero", "clientes.endereco_complemento",
    "clientes.endereco_bairro", "clientes.endereco_cidade",
    "clientes.endereco_uf", "clientes.profissao",
    "imovel_dados.numero_matricula", "imovel_dados.numero_registro_imoveis",
    "imovel_dados.prefeitura_cadastro_imobiliario",
    "imovel_dados.situacao_onus", "imovel_dados.titulo_aquisitivo_texto",
    "imovel_documentos.numero", "imovel_documentos.emitida_em",
    "imovel_documentos.validade_ate", "imovel_documentos.resultado",
    "imovel_documentos.inscricao_imobiliaria",
    "certidao_resultados.numero", "certidao_resultados.emitida_em",
    "certidao_resultados.validade_ate", "certidao_resultados.resultado",
}


def test_gera_dois_arquivos_por_documento(tmp_path: Path) -> None:
    manifest = gd.gerar(tmp_path)
    for doc in gd.DOCUMENTOS:
        for variante in ("texto", "scan"):
            pdf = tmp_path / f"{doc['id']}_{variante}.pdf"
            assert pdf.exists(), f"faltando {pdf.name}"
            assert pdf.stat().st_size > 200, f"{pdf.name} parece vazio"
    assert len(manifest["documentos"]) == len(gd.DOCUMENTOS) * 2


def test_variante_scan_nao_tem_camada_de_texto(tmp_path: Path) -> None:
    """The whole point of the "scan" variant is that it exercises the
    vision leg of the ladder, never the pdfminer one — pdfminer.six must
    extract NOTHING from it."""
    from pdfminer.high_level import extract_text  # backend dep too

    manifest = gd.gerar(tmp_path)
    for doc in gd.DOCUMENTOS:
        scan_path = tmp_path / f"{doc['id']}_scan.pdf"
        texto = extract_text(str(scan_path)).strip()
        assert texto == "", (
            f"{scan_path.name} tem camada de texto ({len(texto)} chars) — "
            "não é um scan de verdade"
        )
        texto_path = tmp_path / f"{doc['id']}_texto.pdf"
        assert extract_text(str(texto_path)).strip() != "", (
            f"{texto_path.name} deveria ter camada de texto"
        )
    del manifest


def test_esperado_json_e_valido_e_cobre_todo_documento(tmp_path: Path) -> None:
    manifest = gd.gerar(tmp_path)
    esperado = json.loads((tmp_path / "esperado.json").read_text(encoding="utf-8"))

    assert set(esperado["documentos"]) == set(manifest["documentos"])
    for nome_arquivo, entrada in esperado["documentos"].items():
        assert entrada["uploads"], f"{nome_arquivo} sem nenhum upload esperado"
        for upload in entrada["uploads"]:
            assert upload["alvo"], f"{nome_arquivo}: upload sem alvo"
            assert upload["campos"], f"{nome_arquivo}: upload sem campos"
            for campo, valor in upload["campos"].items():
                assert "." in campo, f"campo mal formado: {campo!r}"
                assert valor not in (None, ""), (
                    f"{nome_arquivo}/{upload['alvo']}: {campo} esperado vazio"
                )


def test_todo_campo_do_contrato_file_derived_e_exercitado_ao_menos_uma_vez(
    tmp_path: Path,
) -> None:
    """The fixture set's REASON TO EXIST: every contract cell the roadmap
    marks as file-derived must be asserted by at least one document's
    `campos` — a gap here is a gap in the E2E proof, not just this test."""
    manifest = gd.gerar(tmp_path)
    esperado = json.loads((tmp_path / "esperado.json").read_text(encoding="utf-8"))

    cobertos: set[str] = set()
    for entrada in esperado["documentos"].values():
        for upload in entrada["uploads"]:
            cobertos.update(upload["campos"].keys())

    faltando = CAMPOS_CONTRATO_POR_ARQUIVO - cobertos
    assert not faltando, f"campos do contrato sem nenhuma fixture: {sorted(faltando)}"
    del manifest


def test_cpfs_gerados_sao_check_digit_validos() -> None:
    """Every fictional CPF this fixture set prints must pass the SAME
    mod-11 check the real extractor (`cpf.is_valid`) runs — an invalid
    synthetic CPF would make the extractor correctly refuse it, which is
    not the behaviour under test here."""
    import dados as d

    def is_valid(cpf: str) -> bool:
        digits = "".join(c for c in cpf if c.isdigit())
        if len(digits) != 11 or digits == digits[0] * 11:
            return False
        for tamanho in (9, 10):
            soma = sum(int(digits[i]) * (tamanho + 1 - i) for i in range(tamanho))
            resto = (soma * 10) % 11
            esperado = 0 if resto == 10 else resto
            if esperado != int(digits[tamanho]):
                return False
        return True

    for cpf in (
        d.RICARDO.cpf, d.CAMILA.cpf, d.FERNANDO.cpf,
        d.TERCEIRO_VENDEDOR_CPF, d.TERCEIRA_COMPRADORA_CPF,
    ):
        assert is_valid(cpf), f"CPF sintético inválido: {cpf}"


def test_gerar_e_deterministico_no_texto(tmp_path: Path) -> None:
    """Re-running the generator must not silently drift the fixture
    content — see `gerar_documentos.py`'s own note on `invariant=1` (text
    PDFs are byte-identical across runs) and on the scan variant's PDF
    container possibly varying in incidental metadata while its rendered
    pixel content stays seeded/deterministic."""
    out1, out2 = tmp_path / "a", tmp_path / "b"
    gd.gerar(out1)
    gd.gerar(out2)
    for doc in gd.DOCUMENTOS:
        nome = f"{doc['id']}_texto.pdf"
        assert (out1 / nome).read_bytes() == (out2 / nome).read_bytes(), (
            f"{nome} não é determinístico entre execuções"
        )
    assert (out1 / "esperado.json").read_text() == (out2 / "esperado.json").read_text()
