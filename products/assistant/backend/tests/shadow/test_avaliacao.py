"""Agreement math: nao_sei is outside the denominator; the matrix is exact; empty is None, never 0."""
import pytest

from app.shadow.avaliacao import calcular_concordancia


def L(v, r, n, pv="v1", m="m"):
    return {"prompt_version": pv, "modelo": m, "veredito": v, "rotulo": r, "n": n}


def test_agreement_counts_only_decided_labels():
    g, = calcular_concordancia([L("agendamento", "agendamento", 6), L("agendamento", "nao_agendamento", 2),
                                L("outro", "nao_agendamento", 10), L("outro", "agendamento", 2), L("outro", "nao_sei", 4)])
    assert (g["total"], g["nao_sei"], g["decididos"], g["concordam"]) == (24, 4, 20, 16)
    assert g["concordancia"] == 0.8
    assert g["matriz"] == {"agendamento": {"agendamento": 6, "nao_agendamento": 2, "nao_sei": 0},
                           "outro": {"agendamento": 2, "nao_agendamento": 10, "nao_sei": 4}}


def test_groups_are_per_prompt_version_and_model():
    gs = calcular_concordancia([L("agendamento", "agendamento", 1, "v1"), L("outro", "agendamento", 1, "v2"),
                                L("agendamento", "agendamento", 3, "v1", "m2")])
    assert [(g["prompt_version"], g["modelo"], g["concordancia"]) for g in gs] == [
        ("v1", "m", 1.0), ("v1", "m2", 1.0), ("v2", "m", 0.0)]


def test_only_nao_sei_has_no_agreement_rather_than_zero():
    g, = calcular_concordancia([L("outro", "nao_sei", 3)])
    assert g["decididos"] == 0 and g["concordancia"] is None


def test_empty_and_unknown_values():
    assert calcular_concordancia([]) == []
    with pytest.raises(ValueError):
        calcular_concordancia([L("talvez", "agendamento", 1)])
