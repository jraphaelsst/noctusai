"""RG printed on a TJSP e-SAJ certidão -> the party's `rg` (check digit a CNH omits).

Synthetic data only (CPF `111.444.777-35`, RG `30.738.581-4` passes the SSP-SP DV)."""
from __future__ import annotations

from uuid import uuid4

from noctusai_lib.testing import MockSupabaseClient

from app.modules.certidoes import feed_parte
from tests.modules.test_certidoes_service import ORG

CPF = "111.444.777-35"
TEXTO = (
    "TRIBUNAL DE JUSTIÇA SISTEMA E-SAJ CERTIDÃO DE DISTRIBUIÇÃO CÍVEL\n"
    "Nome: MARIA TESTE\nRG: 30.738.581-4\nCPF: {cpf}\n"
)


def _db(cliente: dict) -> MockSupabaseClient:
    db = MockSupabaseClient(schema="social_wiring")
    for t in ("clientes", "cliente_campo_conflitos", "atendimento_partes", "atendimentos"):
        db.set_table_data(t, [])
    db.set_table_data("clientes", [cliente])
    return db


def _cliente(cid: str, **over) -> dict:
    row = {"id": cid, "org_id": ORG, "nome": "Maria", "cpf": CPF, "rg": "30738581",
           "rg_origem": "cnh", "rg_documento_id": None, "rg_confirmado_por": None,
           "rg_confirmado_em": None}
    row.update(over)
    return row


def _rodar(db, cid, cpf=CPF, tipo="tjsp_esaj"):
    return feed_parte.alimentar_rg_da_certidao(
        db, ORG, {"id": "c1", "cliente_id": cid}, tipo, (TEXTO.format(cpf=cpf),),
        resultado_id=str(uuid4()),
    )


def _row(db, cid):
    return db.table("clientes").select("*").eq("id", cid).execute().data[0]


class TestRgImpresso:
    def test_completa_o_dv_da_cnh_pendente_com_proveniencia_da_certidao(self):
        cid = str(uuid4())
        db = _db(_cliente(cid))
        out = _rodar(db, cid)
        row = _row(db, cid)
        assert out["status"] == "completado"
        assert row["rg"] == "30.738.581-4"
        assert row["rg_origem"] == "certidao"
        assert row["rg_confirmado_por"] is None and row["rg_confirmado_em"] is None
        auditoria = db.table("cliente_campo_conflitos").select("*").execute().data
        assert [a["status"] for a in auditoria] == ["resolvido_automatico"]
        assert "rg_completado_pela_certidao" in auditoria[0]["motivo_resolucao"]

    def test_valor_manual_ou_confirmado_nunca_e_tocado(self):
        for over in ({"rg_origem": "manual"}, {"rg_confirmado_em": "2026-10-01T00:00:00+00:00"}):
            cid = str(uuid4())
            db = _db(_cliente(cid, **over))
            assert _rodar(db, cid)["status"] == "protegido"
            assert _row(db, cid)["rg"] == "30738581"

    def test_cpf_diferente_e_ignorado(self):
        cid = str(uuid4())
        db = _db(_cliente(cid))
        assert _rodar(db, cid, cpf="529.982.247-25")["status"] == "cpf_divergente"
        assert _row(db, cid)["rg"] == "30738581"

    def test_base_diferente_abre_conflito_sem_sobrescrever(self):
        cid = str(uuid4())
        db = _db(_cliente(cid, rg="12345678", rg_origem="manual", rg_confirmado_em="2026-10-01T00:00:00+00:00"))
        out = _rodar(db, cid)
        assert _row(db, cid)["rg"] == "12345678"
        assert out["status"] != "completado"
        assert db.table("cliente_campo_conflitos").select("*").execute().data

    def test_rg_vazio_e_preenchido_pendente(self):
        cid = str(uuid4())
        db = _db(_cliente(cid, rg=None, rg_origem=None))
        assert _rodar(db, cid)["status"] == "aplicado"
        row = _row(db, cid)
        assert (row["rg"], row["rg_origem"], row["rg_confirmado_por"]) == ("30.738.581-4", "certidao", None)

    def test_tipo_sem_rg_impresso_e_sem_cliente_nao_fazem_nada(self):
        cid = str(uuid4())
        db = _db(_cliente(cid))
        assert _rodar(db, cid, tipo="cnd_federal")["status"] == "nada"
        assert feed_parte.alimentar_rg_da_certidao(
            db, ORG, {"id": "c1", "cliente_id": None}, "tjsp_esaj", (TEXTO.format(cpf=CPF),),
        )["status"] == "nada"
        assert _row(db, cid)["rg"] == "30738581"


class TestRgSoSpTemDv:
    """F95: the check digit is an SSP/SP feature; other UFs' CNH RG is complete."""

    def test_nao_sp_nao_e_completado_pela_certidao(self):
        for orgao in ("SSP AM", "SSP/RJ", "SSP-MG"):
            cid = str(uuid4())
            db = _db(_cliente(cid, rg_orgao_expedidor=orgao))
            assert _rodar(db, cid)["status"] == "ja_completo"
            assert _row(db, cid)["rg"] == "30738581"

    def test_sp_continua_sendo_completado(self):
        for orgao in ("SSP/SP", "SSP-SP", "SSP SP"):
            cid = str(uuid4())
            db = _db(_cliente(cid, rg_orgao_expedidor=orgao))
            assert _rodar(db, cid)["status"] == "completado"

    def test_checklist_e_contrato_usam_o_mesmo_predicado(self):
        from app.modules.card_hub import documento_checklist_service as svc

        def faltando(orgao):
            c = {"nome_oficial": "M", "rg": "18104746", "rg_origem": "cnh",
                 "rg_orgao_expedidor": orgao, "cpf": CPF}
            return "rg" in svc.campos_faltando(c, "identidade", {})

        assert faltando("SSP/SP") and faltando("SSP-SP")
        assert not faltando("SSP AM") and not faltando("SSP/RJ") and not faltando("SSP/MG")
