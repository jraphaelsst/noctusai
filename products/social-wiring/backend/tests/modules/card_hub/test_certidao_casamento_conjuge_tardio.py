"""A spouse linked AFTER the certidão de casamento was read still gets her
facts (deal 876): the certidão sits on the titular, "Adicionar cônjuge" comes
later, and her estado civil / nacionalidade / gênero stayed pending forever.
"""
from __future__ import annotations

from uuid import uuid4

from app.modules.card_hub import identidade_extracao_service as svc
from app.services.conjuge_vinculo import vincular_conjuge
from noctusai_lib.testing import MockSupabaseClient

ORG = "00000000-0000-4000-8000-000000000001"


def _setup(nome_esposa="Maria Silva"):
    db = MockSupabaseClient().schema("social_wiring")
    titular, esposa, doc = str(uuid4()), str(uuid4()), str(uuid4())
    db.set_table_data("clientes", [
        {"id": titular, "org_id": ORG, "nome": "João Silva", "nome_oficial": "JOAO SILVA"},
        {"id": esposa, "org_id": ORG, "nome": nome_esposa, "nome_completo": nome_esposa},
    ])
    db.set_table_data("cliente_documentos", [{
        "id": doc, "org_id": ORG, "cliente_id": titular,
        "tipo_documento": "certidao_casamento", "extracao_status": "ok",
        "deleted_at": None, "extracao_descartada_em": None,
        "created_at": "2026-10-01T00:00:00+00:00",
        "extracao_estado_civil": "casado", "extracao_estado_civil_confianca": "alta",
        "extracao_regime_bens": "comunhao_parcial",
        "extracao_data_emissao": "2026-09-20",
        "extracao_conjuges": [
            {"titular": True, "nome": "JOAO SILVA", "cliente_id": titular},
            {"titular": False, "nome": "MARIA SILVA", "nome_anterior": None,
             "genero": "feminino", "nacionalidade": "brasileira",
             "data_nascimento": "1990-05-04", "cliente_id": None},
        ],
    }])
    return db, titular, esposa, doc


def _cliente(db, cid):
    return next(r for r in db.table("clientes").select("*").execute().data if r["id"] == cid)


def test_linking_applies_the_certidao_to_the_spouse():
    db, titular, esposa, doc = _setup()
    vincular_conjuge(db, ORG, esposa, titular)
    row = _cliente(db, esposa)
    assert row["estado_civil"] == "casado"
    assert row["estado_civil_origem"] == "certidao_casamento"
    assert row["estado_civil_documento_id"] == doc
    assert row["nacionalidade"] == "brasileira"
    assert row["genero"] == "Feminino"
    assert row["regime_bens"] == "comunhao_parcial"


def test_the_extracted_entry_records_the_spouse_cliente_id():
    db, titular, esposa, doc = _setup()
    vincular_conjuge(db, ORG, esposa, titular)
    d = db.table("cliente_documentos").select("*").execute().data[0]
    nao_titular = next(e for e in d["extracao_conjuges"] if not e["titular"])
    assert nao_titular["cliente_id"] == esposa


def test_a_different_named_spouse_is_not_filled_from_this_certidao():
    db, titular, esposa, _ = _setup(nome_esposa="Carla Oliveira")
    vincular_conjuge(db, ORG, esposa, titular)
    assert not _cliente(db, esposa).get("estado_civil")


def test_certidao_emission_date_answers_for_the_linked_spouse():
    db, titular, esposa, doc = _setup()
    assert svc.certidao_estado_civil_mais_recente(db, ORG, esposa) is None
    db.table("clientes").update({"conjuge_cliente_id": titular}).eq("id", esposa).execute()
    db.table("clientes").update({"conjuge_cliente_id": esposa}).eq("id", titular).execute()
    out = svc.certidao_estado_civil_mais_recente(db, ORG, esposa)
    assert out is not None and out["emitida_em"] == "2026-09-20"
    assert out["documento_id"] == doc
