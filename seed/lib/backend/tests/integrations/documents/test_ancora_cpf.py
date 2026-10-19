"""`ancora.cpfs_com_dv_falho` — a mis-copied CPF marks the transcription.

The anchor must see the same CPF shapes `cpf.find_cpf` reads: the São Paulo
RG prints its CPF as `NNNNNNNNN/DD` (real deal-876 RG, 2026-10-19), so a
vision pass that mis-copies THAT number has shown it is not reading the page
faithfully — exactly like a mis-copied dash-form CPF.
"""
from __future__ import annotations

from noctusai_lib.integrations.documents.ancora import cpfs_com_dv_falho

VALIDO_BARRA = "412954238/98"
INVALIDO_BARRA = "412954238/99"


def test_a_valid_slash_cpf_under_its_label_is_no_failure():
    assert cpfs_com_dv_falho(f"NOME FULANO\nCPF: {VALIDO_BARRA}\nASSINATURA") == ()


def test_a_mis_copied_slash_cpf_under_its_label_fails_the_anchor():
    assert cpfs_com_dv_falho(f"CPF: {INVALIDO_BARRA}") == (INVALIDO_BARRA,)


def test_a_mis_copied_dotted_slash_cpf_fails_the_anchor():
    assert cpfs_com_dv_falho("CPF 412.954.238/99") == ("412.954.238/99",)


def test_the_dash_forms_still_behave_as_before():
    assert cpfs_com_dv_falho("CPF 412.954.238-98") == ()
    assert cpfs_com_dv_falho("CPF 412.954.238-99") == ("412.954.238-99",)
    assert cpfs_com_dv_falho("CPF: 41295423899") == ("41295423899",)


def test_a_date_beside_the_label_is_not_a_cpf():
    assert cpfs_com_dv_falho("CPF EMITIDO EM 27/04/2017") == ()
