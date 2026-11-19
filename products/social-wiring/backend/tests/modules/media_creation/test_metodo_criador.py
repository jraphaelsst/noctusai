"""Métodos de criadores: every shipped JSON validates against the one schema and the canonical block catalog.

Pure Python: no database, no mock. Real files from ``metodos_criadores/`` plus tmp-path files for the refusals.
"""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.media_creation import metodo_criador as mc
from app.modules.media_creation.estruturas_tipos_bloco import TIPO_NOMES


class TestShippedMethods:
    def test_every_shipped_file_loads_and_slug_matches_filename(self):
        metodos = mc.listar()
        assert {m.slug for m in metodos} >= {"alba-valeria", "elias-maman"}
        for m in metodos:
            assert (mc.DIRETORIO / f"{m.slug}.json").is_file()

    def test_every_step_uses_a_canonical_block(self):
        for m in mc.listar():
            for molde in m.moldes:
                assert all(e.bloco in TIPO_NOMES for e in molde.etapas), (m.slug, molde.slug)

    def test_alba_valeria_has_the_seven_moldes_in_order(self):
        m = mc.carregar("alba-valeria")
        assert [x.n for x in m.moldes] == [1, 2, 3, 4, 5, 6, 7]
        assert m.molde(6).slug == "pergunta-espelho-curta"
        assert m.molde("frase-de-autor-e-leitura").n == 7


def _valido() -> dict:
    return json.loads((mc.DIRETORIO / "alba-valeria.json").read_text(encoding="utf-8"))


def _escreve(tmp_path: Path, dados: dict, nome: str | None = None) -> str:
    slug = nome or dados["slug"]
    (tmp_path / f"{slug}.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return slug


class TestRefusals:
    def test_unknown_block_is_refused(self, tmp_path):
        dados = _valido()
        dados["moldes"][0]["etapas"][0]["bloco"] = "Gancho Inventado"
        with pytest.raises(ValidationError, match="catálogo canônico"):
            mc.carregar(_escreve(tmp_path, dados), tmp_path)

    def test_slug_must_match_filename(self, tmp_path):
        with pytest.raises(ValueError, match="não bate com o nome do arquivo"):
            mc.carregar(_escreve(tmp_path, _valido(), nome="outro-nome"), tmp_path)

    def test_moldes_must_be_numbered_in_order(self, tmp_path):
        dados = _valido()
        dados["moldes"][1]["n"] = 5
        with pytest.raises(ValidationError, match="numerados 1..N"):
            mc.carregar(_escreve(tmp_path, dados), tmp_path)

    def test_inverted_word_range_is_refused(self, tmp_path):
        dados = _valido()
        dados["moldes"][0]["palavras"] = [230, 150]
        with pytest.raises(ValidationError, match="palavras"):
            mc.carregar(_escreve(tmp_path, dados), tmp_path)

    def test_unknown_field_is_refused(self, tmp_path):
        dados = _valido()
        dados["transcricoes"] = ["texto da criadora"]
        with pytest.raises(ValidationError):
            mc.carregar(_escreve(tmp_path, dados), tmp_path)

    def test_missing_molde_names_the_options(self):
        with pytest.raises(KeyError, match="opções"):
            mc.carregar("alba-valeria").molde(99)

    def test_listar_raises_on_an_invalid_file_never_skips(self, tmp_path):
        _escreve(tmp_path, _valido())
        ruim = _valido()
        ruim["slug"] = "ruim"
        ruim["schema_version"] = 99
        _escreve(tmp_path, ruim)
        with pytest.raises(ValidationError, match="schema_version"):
            mc.listar(tmp_path)
