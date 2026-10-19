"""Lead identity: CPF checksum, masking, encryption round-trip, never-echo, audit on decrypt,
timing rule (ask only after visit intent), the `identificacao completa` rule atom, HTTP boundary."""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet

from app.qualificacao import engine
from app.qualificacao.ident_store import FakeIdentificacaoStore, get_identificacao_service, get_identificacao_store
from app.qualificacao.identificacao import (
    CAMPOS,
    EncryptionNotConfigured,
    IdentCipher,
    IdentificacaoService,
    RevelarNegado,
    mascarar_cpf,
    mascarar_email,
    mascarar_rg,
    validar_cpf,
    validar_email,
    validar_rg,
)
from app.qualificacao.lead_store import FakeLeadQualificacaoStore
from app.qualificacao.models import EstagioDef, EventoImovel, LeadSinais, ParametrosDef
from app.qualificacao.service import ItemPerfil, QualificacaoService
from tests.qualificacao.fixture_v1 import _em, _preenchido, versao_v1
from tests.qualificacao.harness import AGENTE, LEAD, ORG, OUTRA_ORG, publicar_v1

AGORA = datetime(2026, 10, 19, tzinfo=timezone.utc)
CPF = "529.982.247-25"  # valid check digits
KEY = Fernet.generate_key()


def novo(cipher=True):
    store = FakeIdentificacaoStore()
    return IdentificacaoService(store, IdentCipher(KEY) if cipher else None, agora=lambda: AGORA), store


def reg(svc, campo, valor, msgs, **kw):
    return svc.registrar_identificacao(ORG, LEAD, agent_id=AGENTE, campo=campo, valor=valor, mensagens_lead=msgs, **kw)


# ── validators ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cpf,ok", [
    ("529.982.247-25", True), ("52998224725", True), ("  529 982 247 25 ", True),
    ("529.982.247-24", False), ("111.111.111-11", False), ("123", False), ("", False), ("abc", False),
    ("168.995.350-09", True), ("168.995.350-08", False),
])
def test_cpf_check_digits(cpf, ok):
    assert validar_cpf(cpf)[0] is ok


def test_cpf_normalises_to_digits():
    assert validar_cpf(CPF) == (True, "52998224725")


@pytest.mark.parametrize("v,ok", [("ana@exemplo.com", True), ("A.B+c@sub.dominio.com.br", True), ("ana@", False),
                                  ("ana@exemplo", False), ("@x.com", False), ("a b@x.com", False)])
def test_email_syntax(v, ok):
    assert validar_email(v)[0] is ok


@pytest.mark.parametrize("v,ok,norm,uf", [
    ("12.345.678-9", True, "123456789", None), ("MG-12.345.678", True, "MG12345678", None),
    ("12.345.678-9 SP", True, "123456789", "SP"), ("1234", False, "", None), ("123456789012345", False, "", None),
    ("ABCDEFG", False, "", None), ("12.345.678-9/XX", True, "123456789XX", None),
])
def test_rg_shape(v, ok, norm, uf):
    r = validar_rg(v)
    assert r[0] is ok and r[1] == norm and r[2] == uf


def test_masking():
    assert mascarar_cpf("52998224725") == "***.***.***-25"
    assert mascarar_rg("123456789", "SP") == "*******89-SP"
    assert mascarar_email("ana@exemplo.com") == "a***@exemplo.com"


# ── registrar_identificacao ─────────────────────────────────────────────────

def test_register_validates_requires_the_value_in_a_lead_message_and_never_echoes():
    svc, store = novo()
    r = reg(svc, "cpf", CPF, ["meu cpf e 529.982.247-25"])
    assert r.status == "registrado" and r.faltando == ("nome", "email", "rg")
    assert r.to_payload() == {"campo": "cpf", "status": "registrado", "faltando": ["nome", "email", "rg"]}
    assert "52998224725" not in repr(r) and CPF not in repr(r)
    # digits written differently in the message still match
    assert reg(svc, "cpf", "52998224725", ["cpf 529 982 247 25"]).status == "registrado"
    r = reg(svc, "cpf", CPF, ["oi, bom dia"])
    assert (r.status, r.codigo) == ("invalido", "valor_nao_confere")
    r = reg(svc, "cpf", "529.982.247-24", ["meu cpf 529.982.247-24"])
    assert (r.status, r.codigo) == ("invalido", "valor_invalido")
    assert reg(svc, "telefone", "11999990000", ["x"]).codigo == "campo_desconhecido"
    assert reg(svc, "cpf", 123, ["x"]).codigo == "valor_invalido"


def test_every_field_and_required_set_shrinks_to_empty():
    svc, _ = novo()
    msgs = ["Ana Paula Souza, ana@exemplo.com, cpf 529.982.247-25, rg 12.345.678-9 SP"]
    esperado = [("nome", "Ana Paula Souza", ("email", "cpf", "rg")), ("email", "ana@exemplo.com", ("cpf", "rg")),
                ("cpf", CPF, ("rg",)), ("rg", "12.345.678-9 SP", ())]
    for campo, valor, falta in esperado:
        r = reg(svc, campo, valor, msgs)
        assert r.status == "registrado" and r.faltando == falta, campo
    assert svc.faltando(ORG, LEAD) == ()
    assert svc.coletados(ORG, LEAD) == frozenset(CAMPOS)


def test_phone_is_automatic_from_the_channel_ref():
    svc, store = novo()
    svc.definir_telefone(ORG, LEAD, "+55 (11) 99999-0000")
    assert store.obter(ORG, LEAD).telefone == "5511999990000"
    assert "telefone" in svc.coletados(ORG, LEAD) and "telefone" not in CAMPOS
    with pytest.raises(ValueError):
        svc.definir_telefone(ORG, LEAD, "12")


def test_cpf_rg_are_encrypted_at_rest_and_round_trip():
    svc, store = novo()
    reg(svc, "cpf", CPF, [CPF]), reg(svc, "rg", "12.345.678-9 SP", ["rg 12.345.678-9 SP"])
    rec = store.obter(ORG, LEAD)
    assert "52998224725" not in (rec.cpf_cifrado or "") and "123456789" not in (rec.rg_cifrado or "")
    assert rec.cpf_cifrado.startswith("gAAAA") and rec.rg_cifrado.startswith("gAAAA")  # Fernet tokens
    assert rec.rg_uf == "SP" and len(rec.cpf_hash) == 64
    assert IdentCipher(KEY).decifrar(rec.cpf_cifrado) == "52998224725"
    assert rec.cpf_hash == IdentCipher(KEY).hash_cpf("52998224725")
    assert IdentCipher(Fernet.generate_key()).hash_cpf("52998224725") != rec.cpf_hash  # keyed, not a bare digest
    with pytest.raises(Exception):
        IdentCipher(Fernet.generate_key()).decifrar(rec.cpf_cifrado)


def test_without_an_encryption_key_cpf_rg_are_refused_never_stored_in_clear():
    svc, store = novo(cipher=False)
    with pytest.raises(EncryptionNotConfigured):
        reg(svc, "cpf", CPF, [CPF])
    assert store.obter(ORG, LEAD) is None
    assert reg(svc, "nome", "Ana Souza", ["Ana Souza"]).status == "registrado"  # not secret fields still work
    with pytest.raises(EncryptionNotConfigured):
        IdentCipher("")
    assert get_identificacao_service(SimpleNamespace(supabase_service_role_key=None, encryption_key="")) is not None


def test_value_never_reaches_logs(caplog):
    caplog.set_level(logging.DEBUG)
    svc, _ = novo()
    reg(svc, "cpf", CPF, [CPF])
    svc.mascarado(ORG, LEAD)
    assert "52998224725" not in caplog.text and CPF not in caplog.text


# ── masked default + audited reveal ─────────────────────────────────────────

def test_default_display_is_masked():
    svc, _ = novo()
    msgs = ["Ana Souza ana@exemplo.com cpf 529.982.247-25 rg 12.345.678-9 SP"]
    for c, v in (("nome", "Ana Souza"), ("email", "ana@exemplo.com"), ("cpf", CPF), ("rg", "12.345.678-9 SP")):
        reg(svc, c, v, msgs)
    svc.definir_telefone(ORG, LEAD, "5511999990000")
    m = svc.mascarado(ORG, LEAD)
    assert m["cpf"] == "***.***.***-25" and m["rg"].endswith("89-SP") and m["email"] == "a***@exemplo.com"
    assert m["telefone"] == "***0000" and m["nome"] == "Ana Souza"
    assert "52998224725" not in str(m) and "529" not in m["cpf"]
    assert svc.mascarado(OUTRA_ORG, LEAD) is None


def test_reveal_writes_the_audit_row_first_and_returns_the_clear_values():
    svc, store = novo()
    reg(svc, "cpf", CPF, [CPF])
    quem = uuid4()
    out = svc.revelar(ORG, LEAD, ator_user_id=quem, motivo="conferir para a visita")
    assert out["cpf"] == "52998224725"
    [a] = store.listar_acessos(ORG, LEAD)
    assert (a.ator_user_id, a.campos, a.motivo, a.created_at) == (quem, ("cpf",), "conferir para a visita", AGORA)
    assert "52998224725" not in repr(a)


def test_reveal_failing_to_audit_returns_no_value():
    svc, store = novo()
    reg(svc, "cpf", CPF, [CPF])
    store.registrar_acesso = lambda a: (_ for _ in ()).throw(RuntimeError("audit down"))
    with pytest.raises(RuntimeError):
        svc.revelar(ORG, LEAD, ator_user_id=uuid4())


def test_reveal_unknown_lead_and_other_org():
    svc, _ = novo()
    reg(svc, "cpf", CPF, [CPF])
    with pytest.raises(RevelarNegado) as e:
        svc.revelar(OUTRA_ORG, LEAD, ator_user_id=uuid4())
    assert e.value.codigo == "sem_identificacao"


def test_delete_by_lead_erases_identity_through_the_qualification_service():
    svc, store = novo()
    reg(svc, "cpf", CPF, [CPF])
    padroes, _ = publicar_v1()
    q = QualificacaoService(padroes, FakeLeadQualificacaoStore(), identificacao=svc)
    assert q.apagar_por_lead(ORG, LEAD) == 1
    assert store.obter(ORG, LEAD) is None and q.apagar_por_lead(ORG, LEAD) == 0


# ── rules: identification criteria, completeness atom, timing ───────────────

def _versao_com_identificacao():
    v = versao_v1()
    base = next(c for c in v.criterios if c.chave == "nome")
    ident = [replace(base, chave=k, tipo="identificacao", grupo="contato", escopo="sdr", pontuacao={}, opcoes=(),
                     ordem=800 + i) for i, k in enumerate(CAMPOS)]
    criterios = tuple(c for c in v.criterios if c.chave not in CAMPOS) + tuple(ident)
    pronto = EstagioDef("pronto_para_corretor", "Pronto", 5,
                        {"todos": [{"algum": [_preenchido("deseja_visitar"), _em("prazo_decisao", "imediato")]},
                                   {"identificacao": "completa"}]}, conclusivo=True)
    estagios = tuple(pronto if e.chave == "pronto_para_corretor" else e for e in v.estagios)
    params = replace(v.parametros, pedir_identificacao_quando=_preenchido("deseja_visitar"))
    return replace(v, criterios=criterios, estagios=estagios, parametros=params)


def test_identification_version_publishes_and_forbids_points():
    v = _versao_com_identificacao()
    assert engine.validar_versao(v) == []
    pontua = replace(v.criterios[-1], pontuacao={"preenchido": 3})
    assert "pontuacao_invalida" in {x["code"] for x in engine.validar_versao(replace(v, criterios=(*v.criterios[:-1], pontua)))}
    bad = replace(v.estagios[2], regra={"identificacao": "parcial"})
    assert engine.validar_versao(replace(v, estagios=(*v.estagios[:2], bad, *v.estagios[3:])))


def test_complete_identification_atom_gates_pronto_para_corretor():
    v = _versao_com_identificacao()
    base = [ItemPerfil(k, x) for k, x in ()]
    from app.qualificacao.models import Registro
    regs = [Registro(k, val) for k, val in dict(operacao="compra", tipo_imovel="casa", faixa_preco={"max": 4},
            regioes=["a"], prazo_decisao="imediato", forma_pagamento="a_vista").items()]
    ev = [EventoImovel("A", "oferecido", lote=1), EventoImovel("A", "quer_visitar")]
    sem = engine.calcular(v, regs, ev, AGORA, sinais=LeadSinais(identificacao=frozenset({"nome", "email", "cpf"})))
    assert sem.estagio == "qualificado" and not sem.pode_concluir
    assert sem.identificacao_faltando == ("rg",)
    assert sem.faltando == ("rg",) and sem.proximo_criterio.chave == "rg"  # the next stage's atom pulls them in
    com = engine.calcular(v, regs, ev, AGORA, sinais=LeadSinais(identificacao=frozenset(CAMPOS)))
    assert com.estagio == "pronto_para_corretor" and com.pode_concluir and com.identificacao_faltando == ()
    assert com.valores["rg"] is True  # the FLAG, never the value
    assert "52998224725" not in str(com.valores)


def test_identification_is_only_suggested_after_visit_intent():
    v = _versao_com_identificacao()
    from app.qualificacao.models import Registro
    regs = [Registro(k, val) for k, val in dict(operacao="compra", tipo_imovel="casa", faixa_preco={"max": 4},
            regioes=["a"], prazo_decisao="3_6m", forma_pagamento="a_vista").items()]
    antes = engine.calcular(v, regs, [EventoImovel("A", "oferecido", lote=1)], AGORA)
    assert antes.pedir_identificacao is False
    assert antes.avaliar_payload()["identificacao_faltando"] == []  # hidden: not due yet
    assert not (set(antes.faltando) & set(CAMPOS))
    depois = engine.calcular(v, regs, [EventoImovel("A", "oferecido", lote=1), EventoImovel("A", "quer_visitar")], AGORA)
    assert depois.pedir_identificacao is True
    assert depois.avaliar_payload()["identificacao_faltando"] == ["nome", "email", "cpf", "rg"]
    assert depois.faltando[0] == "nome"


def test_registrar_perfil_refuses_identification_criteria_and_service_feeds_the_engine():
    ident, _ = novo()
    padroes, vid = publicar_v1()
    p = padroes.obter_padrao("imob-lead")
    nv = padroes.criar_rascunho(p.id, None, vid)
    v = _versao_com_identificacao()
    for c in v.criterios:
        padroes.salvar_criterio(nv, c)
    for e in v.estagios:
        padroes.salvar_estagio(nv, e)
    padroes.salvar_parametros(nv, v.parametros)
    padroes.publicar(nv, AGENTE)
    q = QualificacaoService(padroes, FakeLeadQualificacaoStore(), identificacao=ident)
    r = q.registrar_perfil(ORG, LEAD, agent_id=AGENTE, versao_id=nv, mensagens_lead=["meu cpf e 529.982.247-25"],
                           itens=[ItemPerfil("cpf", CPF, "529.982.247-25")])
    assert [(x.criterio, x.codigo) for x in r.recusados] == [("cpf", "usar_identificacao")]
    reg(ident, "cpf", CPF, [CPF])
    e = q.avaliar(ORG, LEAD, nv)
    assert e.valores["cpf"] is True and "cpf" not in e.identificacao_faltando and "nome" in e.identificacao_faltando
