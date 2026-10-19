"""A phantom `manual` hands the provenance back to the document (deal 876).

Prod audit, 2026-10-12 02:39: the seller's form was saved with NOTHING
changed and every document-read field was restamped `manual` — logged as an
admin "edit" whose `valor_anterior` equals its `valor_proposto`. The write is
fixed (`clientes_service._valor_inalterado`); the rows it already left are
healed on the next read of a document that states the SAME value
(`identidade_extracao_service._origem_antes_do_reenvio`). The state below is
exactly what that save left on prod (values replaced by fixtures).
"""
from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.card_hub import identidade_extracao_service as svc
from tests.modules.card_hub.conftest import cliente_row
from tests.modules.card_hub.test_identidade_d1_contrato import ORG_ID, ORG_UUID, _cliente, _conflitos

NOME = "SANTA MARIA FRACASSO"
CPF = "529.982.247-25"
RNE = "W-573.678-Z"
SALVO_EM = "2026-10-12T02:39:32.831620+00:00"


def _lidos(**campos):
    base = svc._lidos_vazios()
    base.update({k: (v, "media", "ROTULO", True) for k, v in campos.items()})
    return base


def _edicao_sem_mudanca(cid, campo, valor, origem_anterior, *, proposto=None) -> dict:
    """The audit row `clientes_service._registrar_edicao_manual_confirmada`
    wrote for the unchanged save."""
    return {
        "id": str(uuid4()), "org_id": ORG_ID, "cliente_id": cid, "campo": campo,
        "valor_anterior": valor, "origem_anterior": origem_anterior,
        "valor_proposto": valor if proposto is None else proposto,
        "origem_proposto": "manual", "confianca_proposta": None,
        "fonte_tabela": None, "fonte_id": None, "status": "aceito",
        "decidido_por": str(uuid4()), "decidido_em": SALVO_EM, "created_at": SALVO_EM,
    }


def _vendedora_apos_o_reenvio(scoped, *, conflitos=None, **extra) -> str:
    cid = str(uuid4())
    scoped.set_table_data("clientes", [cliente_row(
        cid, nome="Santa Maria Fracasso", nome_completo="Santa Maria Fracasso",
        nome_oficial=NOME, nome_oficial_origem="manual", nome_oficial_em=SALVO_EM,
        cpf=CPF, cpf_origem="manual", cpf_em=SALVO_EM,
        rg=RNE, rg_origem="manual", rg_em=SALVO_EM,
        rg_orgao_expedidor="DIREX", rg_orgao_expedidor_origem="manual",
        identidade_tipo="rne",
        **extra,
    )])
    scoped.set_table_data("cliente_campo_conflitos", conflitos if conflitos is not None else [
        _edicao_sem_mudanca(cid, "nome_oficial", NOME, "cnh"),
        _edicao_sem_mudanca(cid, "cpf", CPF, "cnh"),
        _edicao_sem_mudanca(cid, "rg", RNE, "ficha_cadastral"),
        _edicao_sem_mudanca(cid, "rg_orgao_expedidor", "DIREX", "ficha_cadastral"),
    ])
    return cid


def _ler_cnh(scoped, cid, documento_id):
    """Her CNH, as the seed reads it: name, CPF, and the RNE in its 4c box
    (`_valores_lidos` routes `fields.rne` into the `rg` pair)."""
    return svc.aplicar_campos_ao_cliente(
        scoped, ORG_UUID, UUID(cid), "cnh",
        _lidos(nome_oficial=NOME, cpf="52998224725", rg="W573678Z", rg_orgao_expedidor="DIREX"),
        documento_id=documento_id, ligar_pessoa=True,
    )


class TestReenvioSemMudanca:
    def test_the_cnh_takes_back_every_field_the_unchanged_save_erased(self, client, scoped):
        cid = _vendedora_apos_o_reenvio(scoped)
        cnh = uuid4()

        _, abertos = _ler_cnh(scoped, cid, cnh)

        row = _cliente(scoped, cid)
        assert abertos == []
        for campo in ("nome_oficial", "cpf", "rg", "rg_orgao_expedidor"):
            assert row[f"{campo}_origem"] == "cnh", campo
            assert row[f"{campo}_documento_id"] == str(cnh), campo
            assert row.get(f"{campo}_confirmado_em") is None, campo
        # Values untouched (the RNE keeps its stored punctuation).
        assert (row["nome_oficial"], row["cpf"], row["rg"]) == (NOME, CPF, RNE)
        auditoria = [
            c for c in _conflitos(scoped) if c.get("status") == "resolvido_automatico"
        ]
        assert {c["campo"] for c in auditoria} == {
            "nome_oficial", "cpf", "rg", "rg_orgao_expedidor",
        }
        assert all(svc.REGRA_REENVIO_SEM_MUDANCA in c["motivo_resolucao"] for c in auditoria)

    def test_a_typed_value_with_no_unchanged_save_behind_it_stays_manual(self, client, scoped):
        cid = _vendedora_apos_o_reenvio(scoped, conflitos=[])

        _ler_cnh(scoped, cid, uuid4())

        row = _cliente(scoped, cid)
        assert all(
            row[f"{c}_origem"] == "manual"
            for c in ("nome_oficial", "cpf", "rg", "rg_orgao_expedidor")
        )
        assert _conflitos(scoped) == []

    def test_a_real_edit_is_never_mistaken_for_a_resend(self, client, scoped):
        cid = _vendedora_apos_o_reenvio(scoped, conflitos=[])
        scoped.set_table_data("cliente_campo_conflitos", [
            _edicao_sem_mudanca(cid, "nome_oficial", "SANTA MARIA FRACASO", "cnh", proposto=NOME),
        ])

        _ler_cnh(scoped, cid, uuid4())

        assert _cliente(scoped, cid)["nome_oficial_origem"] == "manual"

    def test_a_human_confirmed_value_is_never_healed(self, client, scoped):
        cid = _vendedora_apos_o_reenvio(
            scoped, nome_oficial_confirmado_por=str(uuid4()),
            nome_oficial_confirmado_em="2026-10-13T00:00:00+00:00",
        )

        _ler_cnh(scoped, cid, uuid4())

        row = _cliente(scoped, cid)
        assert row["nome_oficial_origem"] == "manual"
        assert row["cpf_origem"] == "cnh"

    def test_a_lower_source_corroborates_but_never_takes_back(self, client, scoped):
        """The save erased a CNH-read CPF; a ficha (lower tier for `cpf`)
        reading the same CPF must not become its source."""
        cid = _vendedora_apos_o_reenvio(scoped)

        svc.aplicar_campos_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "ficha_cadastral",
            _lidos(nome_oficial=NOME, cpf=CPF), documento_id=uuid4(), ligar_pessoa=True,
        )

        assert _cliente(scoped, cid)["cpf_origem"] == "manual"

    def test_a_different_reading_never_overwrites_the_value(self, client, scoped):
        cid = _vendedora_apos_o_reenvio(scoped)

        svc.aplicar_campos_ao_cliente(
            scoped, ORG_UUID, UUID(cid), "cnh",
            _lidos(nome_oficial=NOME, cpf="111.444.777-35"), documento_id=uuid4(),
            ligar_pessoa=True,
        )

        row = _cliente(scoped, cid)
        assert row["cpf"] == CPF
        assert row["cpf_origem"] == "manual"
