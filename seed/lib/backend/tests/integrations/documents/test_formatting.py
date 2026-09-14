"""The shared formatting value objects and their persisted JSON form."""
import pytest

from noctusai_lib.integrations.documents.formatting import (
    FormatRange,
    Paragraph,
    ParagraphKind,
    Run,
    ranges_from_json,
    ranges_to_json,
)


class TestFormatRange:
    def test_rejeita_intervalo_vazio_ou_invertido(self):
        with pytest.raises(ValueError):
            FormatRange(start=5, end=5, bold=True)
        with pytest.raises(ValueError):
            FormatRange(start=6, end=5, bold=True)
        with pytest.raises(ValueError):
            FormatRange(start=-1, end=5, bold=True)

    def test_rejeita_intervalo_sem_formatacao(self):
        with pytest.raises(ValueError):
            FormatRange(start=0, end=3)


class TestJson:
    def test_ida_e_volta_ordenada(self):
        ranges = (
            FormatRange(start=10, end=20, underline=True),
            FormatRange(start=0, end=4, bold=True, underline=True),
        )
        data = ranges_to_json(ranges)
        assert data == [
            {"start": 0, "end": 4, "bold": True, "underline": True},
            {"start": 10, "end": 20, "bold": False, "underline": True},
        ]
        assert ranges_from_json(data) == tuple(sorted(ranges, key=lambda r: r.start))

    def test_none_e_linha_anterior_a_formatacao(self):
        assert ranges_from_json(None) == ()

    def test_entrada_malformada_falha_alto(self):
        with pytest.raises(KeyError):
            ranges_from_json([{"start": 0, "bold": True}])


def test_paragraph_text_concatena_runs():
    p = Paragraph(runs=(Run("R.1 - "), Run("ÔNUS", bold=True)), kind=ParagraphKind.QUOTE)
    assert p.text == "R.1 - ÔNUS"
