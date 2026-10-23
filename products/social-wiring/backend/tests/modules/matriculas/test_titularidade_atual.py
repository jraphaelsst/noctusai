"""`titulo_service.titularidade_atual` — the matrícula's CURRENT owners (the
adquirentes of the last ownership-transferring act, doação included) and that
act's transmitentes (the donors). Invented names/CPFs."""
from __future__ import annotations

from uuid import UUID

from app.modules.matriculas import titulo_service
from tests.modules.matriculas.conftest import (
    CODIGO,
    ORG_ID,
    extracao_row,
    registry_row,
    seed,
)

ORG = UUID(ORG_ID)

TEXTO_DOACAO = (
    "MATRÍCULA Nº 888\nTerreno ficticio.\n"
    "R-1/888 - Em 10/03/1988. DOAÇÃO. Os doadores PAI FICTICIO EXEMPLO, CPF 246.813.579-28, "
    "e MAE FICTICIA EXEMPLO, CPF 135.792.468-28, doaram aos donatários a seguir, a título de "
    "adiantamento de legítima. Transmitentes: PAI FICTICIO EXEMPLO, CPF 246.813.579-28; "
    "MAE FICTICIA EXEMPLO, CPF 135.792.468-28; adquirentes: FILHO UM FICTICIO, CPF "
    "314.159.265-90; FILHO DOIS FICTICIO, CPF 111.444.777-35.\n"
)


def test_a_doacao_names_the_donees_as_owners_and_the_donors_as_transmitentes(client, scoped):
    seed(scoped, registry=[registry_row()], extracoes=[extracao_row(texto=TEXTO_DOACAO)])
    r = titulo_service.titularidade_atual(scoped, ORG, CODIGO)
    assert r["natureza"] == "doacao"
    assert {p["nome"] for p in r["proprietarios"]} == {"FILHO UM FICTICIO", "FILHO DOIS FICTICIO"}
    assert {p["nome"] for p in r["transmitentes"]} == {"PAI FICTICIO EXEMPLO", "MAE FICTICIA EXEMPLO"}


def test_no_matricula_means_owners_unknown_not_nobody(client, scoped):
    seed(scoped, registry=[registry_row()])
    assert titulo_service.titularidade_atual(scoped, ORG, CODIGO) == {
        "natureza": None, "proprietarios": [], "transmitentes": [],
    }
