"""Shared builders: publish the fixture v1 into a Fake library store."""
from __future__ import annotations

from uuid import UUID, uuid4

from app.qualificacao.lead_store import FakeLeadQualificacaoStore
from app.qualificacao.service import QualificacaoService
from app.qualificacao.store import FakePadraoStore
from tests.qualificacao.fixture_v1 import versao_v1

ORG = UUID("11111111-1111-1111-1111-111111111111")
OUTRA_ORG = UUID("22222222-2222-2222-2222-222222222222")
LEAD = UUID("33333333-3333-3333-3333-333333333333")
AGENTE = UUID("44444444-4444-4444-4444-444444444444")
ADMIN = UUID("55555555-5555-5555-5555-555555555555")


def preencher_rascunho(store: FakePadraoStore, vid: UUID) -> None:
    v = versao_v1()
    for c in v.criterios:
        store.salvar_criterio(vid, c)
    for e in v.estagios:
        store.salvar_estagio(vid, e)
    store.salvar_parametros(vid, v.parametros)


def publicar_v1(store: FakePadraoStore | None = None) -> tuple[FakePadraoStore, UUID]:
    store = store or FakePadraoStore()
    padrao = store.criar_padrao("imob-lead", "Imobiliaria: lead", None)
    vid = store.criar_rascunho(padrao.id, "v1", None)
    preencher_rascunho(store, vid)
    store.publicar(vid, ADMIN)
    return store, vid


def montar_servico():
    padroes, vid = publicar_v1()
    leads = FakeLeadQualificacaoStore()
    return QualificacaoService(padroes, leads), padroes, leads, vid
