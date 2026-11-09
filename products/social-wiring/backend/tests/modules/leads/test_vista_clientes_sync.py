"""Vista clientes -> our lead people (`vista_clientes_sync`, migration 337): FILL-EMPTY-ONLY, divergences warned never overwritten,
ambiguous matches, dry-run writes nothing, the allowlist, the LGPD identity flag, the resumable cursor. FakeVistaAdapter +
MockSupabaseClient (which validates every write against the migrations, so this pins 337's column set too). Synthetic data only."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from noctusai_lib.integrations.vista import FakeVistaAdapter, VistaError
from noctusai_lib.testing import MockSupabaseClient

from app.modules.leads.services import vista_clientes_sync as sync

ORG = uuid4()
ADMIN = str(uuid4())
C1, C2, C3 = str(uuid4()), str(uuid4()), str(uuid4())


@pytest.fixture(autouse=True)
def _core(monkeypatch):
    c = MockSupabaseClient()
    c.set_table_data("noctus_users", [{"id": ADMIN, "org_id": str(ORG), "org_role": "admin"}])
    c.set_table_data("notifications", [])
    monkeypatch.setattr("app.database.get_core_client", lambda: c)


def _pessoa(cid, nome="Ana", chave="+5511999990001", tipo="telefone", **kw):
    return {"id": cid, "org_id": str(ORG), "nome": nome, "chave_canonica": chave, "chave_tipo": tipo, "ativo": True, **kw}


def _db(*pessoas, estado=None):
    db = MockSupabaseClient().schema("social_wiring")
    db.set_table_data("clientes", [dict(p) for p in pessoas])
    db.set_table_data("vista_cliente_links", [])
    db.set_table_data("vista_cliente_avisos", [])
    db.set_table_data("vista_clientes_sync_estado", [dict(estado)] if estado else [])
    return db


def _vista(*itens):
    return FakeVistaAdapter(clientes=list(itens))


def _run(db, adapter, **kw):
    kw.setdefault("dry_run", False)
    return asyncio.run(sync.sincronizar(db, adapter, ORG, **kw))


def _row(db, tabela, **eq):
    return [r for r in db.table(tabela).select("*").execute().data if all(r.get(k) == v for k, v in eq.items())]


ANA = {"Codigo": "100", "Nome": "Ana Maria Souza", "Celular": "(11) 99999-0001", "EmailResidencial": "ana@x.com", "DataNascimento": "1985-03-02",
       "EstadoCivil": "Casada", "Profissao": "Engenheira", "Cliente": "Sim", "Proprietario": "Nao", "Fiador": "Nao",
       "SenhaWeb": "segredo", "UsuarioWeb": "ana", "Banco": "001", "CreditoSituacao": "ok"}


# ─── the allowlist ───────────────────────────────────────────────────────


def test_the_allowlist_excludes_every_forbidden_field_and_identity_is_gated():
    for flag in (False, True):
        assert not set(sync.VISTA_PROIBIDOS) & set(sync.campos_vista(flag))
    assert "CPFCNPJ" not in sync.campos_vista(False) and "RG" not in sync.campos_vista(False)
    assert {"CPFCNPJ", "RG"} <= set(sync.campos_vista(True))
    assert not {"NomeConjuge", "CPFConjuge"} & set(sync.campos_vista(True))  # spouse data is not imported at all
    assert not {"SenhaWeb", "CODIGO_CREDPAGO"} & set(sync.campos_vista(True))


def test_a_forbidden_field_is_dropped_on_arrival_even_if_vista_sends_it():
    m = sync.mapear_cliente({**ANA, "CODIGO_CREDPAGO": "x", "CPFCNPJ": "123.456.789-09"})
    assert "cpf" not in m["valores"]  # identity off => not even read
    assert all(v not in str(m) for v in ("segredo", "CODIGO_CREDPAGO"))


def test_the_fake_receives_only_the_allowlisted_projection():
    adapter = _vista(ANA)
    _run(_db(_pessoa(C1)), adapter)
    asked = adapter.clientes_fields_asked[0]
    assert set(asked) == set(sync.campos_vista(False)) and "SenhaWeb" not in asked and "CPFCNPJ" not in asked


# ─── the pure rule ───────────────────────────────────────────────────────


def test_fill_empty_never_overwrites_and_a_different_value_is_a_divergence():
    v = sync.mapear_cliente(ANA)
    fills, div = sync.planejar(v, _pessoa(C1, profissao="Medica", email=None, data_nascimento="1990-01-01"))
    assert "profissao" not in fills and "data_nascimento" not in fills  # ours present => untouched
    assert {d["campo"] for d in div} == {"profissao", "data_nascimento"}
    assert fills["email"] == "ana@x.com" and fills["estado_civil"] == "casado" and fills["nome_completo"] == "Ana Maria Souza"
    assert "celular" not in fills  # the phone key IS ours (phone-keyed person) and equals Vista's


def test_a_phone_or_email_of_ours_that_vista_also_holds_is_not_a_divergence():
    v = sync.mapear_cliente({**ANA, "FonePrincipal": "11 98888-7777", "EmailComercial": "ana@trabalho.com"})
    _, div = sync.planejar(v, _pessoa(C1, celular="+5511988887777", email="ANA@trabalho.com"))
    assert div == []


def test_an_address_is_a_block_never_half_ours_half_vista():
    v = sync.mapear_cliente({"Codigo": "1", "EnderecoResidencial": "Rua A", "CidadeResidencial": "Cotia", "CEPResidencial": "06700000"})
    fills, _ = sync.planejar(v, _pessoa(C1, endereco_cidade="Cotia"))
    assert not any(k.startswith("endereco_") for k in fills)
    fills, _ = sync.planejar(v, _pessoa(C1))
    assert fills["endereco_logradouro"] == "Rua A" and fills["endereco_cep"] == "06700-000"


def test_identity_values_are_masked_in_a_divergence():
    v = sync.mapear_cliente({"Codigo": "1", "CPFCNPJ": "529.982.247-25"}, identidade=True)
    _, div = sync.planejar(v, _pessoa(C1, cpf="111.444.777-35"), identidade=True)
    assert div == [{"campo": "cpf", "valor_nosso": "***735", "valor_vista": "***725"}]


# ─── the run ─────────────────────────────────────────────────────────────


def test_dry_run_reads_vista_and_writes_nothing():
    db = _db(_pessoa(C1))
    rel = _run(db, _vista(ANA), dry_run=True)
    assert rel["dry_run"] and rel["casados"] == 1 and rel["campos_preenchidos"] >= 4
    assert _row(db, "clientes")[0].get("email") is None
    assert not _row(db, "vista_cliente_links") and not _row(db, "vista_cliente_avisos") and not _row(db, "vista_clientes_sync_estado")
    assert rel["amostra"]["preenchimentos"][0]["campos"]  # field NAMES only
    assert "ana@x.com" not in str(rel)


def test_a_real_run_fills_empty_links_and_warns_on_a_difference_without_overwriting():
    db = _db(_pessoa(C1, profissao="Medica"))
    rel = _run(db, _vista(ANA))
    p = _row(db, "clientes", id=C1)[0]
    assert p["email"] == "ana@x.com" and p["email_origem"] == "vista" and p["estado_civil"] == "casado" and p["nome_completo"] == "Ana Maria Souza"
    assert p["profissao"] == "Medica"  # NEVER overwritten
    av = _row(db, "vista_cliente_avisos")
    assert [(a["tipo"], a["campo"], a["valor_nosso"], a["valor_vista"], a["status"]) for a in av] == [("campo_divergente", "profissao", "Medica", "Engenheira", "pendente")]
    assert _row(db, "vista_cliente_links")[0]["casado_por"] == "telefone" and rel["divergencias"] == 1
    assert _row(db, "vista_clientes_sync_estado")[0]["ultima_execucao_em"]


def test_rerunning_is_idempotent_no_duplicate_notice_and_novos_skips_linked():
    db = _db(_pessoa(C1, profissao="Medica"))
    _run(db, _vista(ANA))
    r2 = _run(db, _vista(ANA))
    assert r2["ja_vinculados"] == 1 and r2["casados"] == 0
    r3 = _run(db, _vista(ANA), modo="refazer")
    assert r3["casados"] == 1 and r3["campos_preenchidos"] == 0 and len(_row(db, "vista_cliente_avisos")) == 1


def test_two_people_for_one_vista_cliente_is_an_ambiguous_notice_and_no_write():
    db = _db(_pessoa(C1), _pessoa(C2, nome="Ana B", chave="ana@x.com", tipo="email"))
    rel = _run(db, _vista(ANA))
    assert rel["ambiguos"] == 1 and rel["casados"] == 0
    assert all(p.get("email") is None and p.get("estado_civil") is None for p in _row(db, "clientes"))
    av = _row(db, "vista_cliente_avisos")
    assert len(av) == 1 and av[0]["tipo"] == "match_ambiguo" and av[0]["cliente_id"] is None and set(av[0]["candidatos"]) == {C1, C2}
    assert not _row(db, "vista_cliente_links")


def test_an_unmatched_vista_cliente_is_counted_by_flag_and_never_created():
    db = _db(_pessoa(C1, chave="+5511000000000"))
    rel = _run(db, _vista({"Codigo": "7", "Nome": "Zed", "Celular": "11 97777-0000", "Cliente": "Nao", "Proprietario": "Sim", "Fiador": "Sim"}, {"Codigo": "8", "Nome": "Y"}))
    assert rel["sem_match"] == 2 and rel["sem_match_por_flag"] == {"cliente": 0, "proprietario": 1, "fiador": 1, "sem_flag": 1}
    assert len(_row(db, "clientes")) == 1


def test_identity_is_off_by_default_and_filled_only_when_the_flag_is_on():
    item = {**ANA, "CPFCNPJ": "529.982.247-25", "RG": "12.345.678-9", "RGEmissor": "SSP/SP"}
    db = _db(_pessoa(C1))
    _run(db, _vista(item))
    assert _row(db, "clientes")[0].get("cpf") is None
    db2 = _db(_pessoa(C1), estado={"org_id": str(ORG), "importar_identidade": True})
    _run(db2, _vista(item))
    p = _row(db2, "clientes")[0]
    assert p["cpf"] == "529.982.247-25" and p["cpf_origem"] == "vista" and p["rg"] == "12.345.678-9" and p["rg_orgao_expedidor"] == "SSP/SP"


def test_match_by_cpf_when_the_flag_is_on():
    db = _db(_pessoa(C1, chave="+5511000000000", cpf="529.982.247-25"), estado={"org_id": str(ORG), "importar_identidade": True})
    rel = _run(db, _vista({"Codigo": "5", "Nome": "Ana", "CPFCNPJ": "52998224725"}), dry_run=True)
    assert rel["casados"] == 1 and rel["amostra"]["casamentos"][0]["casado_por"] == "cpf"


def test_the_cursor_resumes_where_the_last_batch_stopped_and_ends_with_none():
    itens = [{"Codigo": str(n), "Nome": f"P{n}", "Celular": f"11 9{n:04d}-0000"} for n in range(1, 6)]
    db = _db()
    adapter = _vista(*itens)
    r1 = _run(db, adapter, limite=2)
    assert r1["lote"] == 2 and r1["proximo_cursor"] == "2"
    r2 = _run(db, adapter, limite=2, cursor=r1["proximo_cursor"])
    assert r2["lote"] == 2 and r2["proximo_cursor"] == "4"
    r3 = _run(db, adapter, limite=2, cursor=r2["proximo_cursor"])
    assert r3["lote"] == 1 and r3["proximo_cursor"] is None
    assert _row(db, "vista_clientes_sync_estado")[0]["ultimo_cursor"] is None


def test_a_vista_failure_leaves_the_cursor_and_the_report_carries_no_key():
    class Falha(FakeVistaAdapter):
        async def list_clientes(self, **kw):
            raise VistaError("boom <VISTA_API_KEY:redacted>")

    rel = _run(_db(), Falha(), cursor="100")
    assert rel["status"] == "erro" and rel["proximo_cursor"] == "100" and rel["lote"] == 0 and "SECRET" not in str(rel)


def test_config_bounds_the_rate_budget():
    db = _db()
    assert sync.salvar_config(db, ORG, vista_rps=2.0, importar_identidade=False)["vista_rps"] == 2.0
    with pytest.raises(ValueError):
        sync.salvar_config(db, ORG, vista_rps=50, importar_identidade=False)
