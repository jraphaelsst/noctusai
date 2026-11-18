"""The interviewer's tool logic (``app.onboarding.entrevista``): every gate the model cannot talk its way past.

Ports are the Fakes (event store, SW port); the conversation is a list of ``Fala``. Asserted on what the LEDGER recorded and
what the apply WROTE, never on a status alone."""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.onboarding import aplicar as ap
from app.onboarding.entrevista import Entrevista, Fala, estado_dos_itens
from app.onboarding.sw_settings import FakeSwSettings
from app.stores._util import utcnow
from app.stores.onboarding_sessoes import FakeOnboardingStore
from app.studio.models import ConfigValidacao

from .test_onboarding_units import TODAS


class Kit:
    def __init__(self, stored: dict[str, str] | None = None) -> None:
        self.store = FakeOnboardingStore()
        self.org = uuid4()
        self.sessao = self.store.criar_sessao(
            uuid4(), uuid4(), alvo_org_id=self.org, agent_key="sdr-base", product="social-wiring", grant_id=uuid4(), created_by=uuid4())
        self.falas: list[Fala] = []
        self.stored = stored or {}
        self.spec_writes: list[dict[str, str]] = []
        self.sw = FakeSwSettings()
        self.recusa_apply: HTTPException | None = None
        self.e = Entrevista(
            sessao=self.sessao, store=self.store, falas=lambda: list(self.falas), declaradas=lambda: dict(TODAS),
            armazenados=lambda: dict(self.stored), config=ConfigValidacao(),
            aplicar_fn=self._aplicar,
        )

    def _aplicar(self, respostas):
        if self.recusa_apply:
            raise self.recusa_apply
        return ap.aplicar(
            respostas, org_id=self.org, declaradas=dict(TODAS), armazenados=dict(self.stored), config=ConfigValidacao(),
            gravar_specs=lambda v: self.spec_writes.append(dict(v)), sw=self.sw,
            ator=self.sessao.created_by, grant_id=self.sessao.grant_id)

    def diz(self, texto: str) -> None:
        self.falas.append(Fala(texto, utcnow()))

    def tipos(self) -> list[str]:
        return [e.event_type for e in self.store.eventos(self.sessao.id)]


@pytest.fixture
def kit() -> Kit:
    return Kit()


def test_progress_starts_with_operations_and_names_the_next_question(kit):
    p = kit.e.progresso()
    assert p["proximo"]["n"] == 9 and p["proximo"]["pergunta"]
    assert p["contagem"]["respondido"] == 0 and 1 in p["faltando_obrigatorios"]
    assert len(p["itens"]) == 41  # operations unknown: every item stays until item 9 answers


def test_answer_needs_the_clients_own_words_in_the_conversation(kit):
    r = kit.e.registrar_resposta(item=1, situacao="respondido", valor="Acme Imóveis", trecho="Acme Imóveis")
    assert r["erro"] == "trecho_nao_encontrado" and kit.tipos() == []  # nothing recorded for an invented quote
    kit.diz("A imobiliária se chama Acme Imóveis")
    r = kit.e.registrar_resposta(item=1, situacao="respondido", valor="Acme Imóveis", trecho="acme imoveis")  # case/accents folded
    assert r["ok"] and r["estado"] == "respondido" and kit.tipos() == ["resposta_registrada"]
    assert estado_dos_itens(kit.store.eventos(kit.sessao.id))[1]["valor"] == "Acme Imóveis"


def test_invalid_value_is_refused_with_the_reason_and_recorded_so_the_model_re_asks(kit):
    kit.diz("O CNPJ é 11.111.111/1111-11")
    r = kit.e.registrar_resposta(item=3, situacao="respondido", valor="11.111.111/1111-11", trecho="11.111.111/1111-11")
    assert r["ok"] is False and r["erro"] == "valor_recusado" and r["reperguntar"] is True and r["motivo"]
    assert kit.tipos() == ["resposta_recusada"]
    assert estado_dos_itens(kit.store.eventos(kit.sessao.id))[3]["estado"] == "recusado"
    assert kit.e.progresso()["itens"][0]["estado"] in ("aberto", "recusado")


def test_a_refused_retry_never_un_confirms_a_confirmed_value(kit):
    kit.diz("CNPJ 11.222.333/0001-81")
    assert kit.e.registrar_resposta(item=3, situacao="respondido", valor="11.222.333/0001-81", trecho="11.222.333/0001-81")["ok"]
    kit.diz("na verdade 123")
    kit.e.registrar_resposta(item=3, situacao="respondido", valor="123", trecho="123")
    assert estado_dos_itens(kit.store.eventos(kit.sessao.id))[3]["estado"] == "respondido"


def test_dont_know_and_later_mark_pending_and_move_on(kit):
    r = kit.e.registrar_resposta(item=4, situacao="pendente", motivo="nao_sabe")
    assert r["ok"] and r["estado"] == "pendente"
    assert kit.e.registrar_resposta(item=5, situacao="pendente", motivo="talvez")["erro"] == "motivo_invalido"
    p = kit.e.progresso()
    assert p["proximo"]["n"] != 4  # set aside: asked again only after everything open
    assert 4 in p["faltando_obrigatorios"]  # still blocks go-live


def test_optional_default_is_accepted_only_when_it_is_the_items_default(kit):
    kit.diz("pode usar o padrão")
    ok = kit.e.registrar_resposta(item=7, situacao="respondido", valor="não", trecho="pode usar o padrão", origem="padrao")
    assert ok["ok"]
    ruim = kit.e.registrar_resposta(item=22, situacao="respondido", valor="sim", trecho="pode usar o padrão", origem="padrao")
    assert ruim["erro"] == "padrao_invalido" and ruim["padrao"] == "não"
    sem = kit.e.registrar_resposta(item=1, situacao="respondido", valor="x", trecho="pode usar o padrão", origem="padrao")
    assert sem["erro"] == "padrao_invalido"


def test_import_is_unconfirmed_and_an_imported_answer_needs_the_clients_yes(kit):
    r = kit.e.importar_configuracao(texto="1: Acme\ncnpj_oficial: 11.222.333/0001-81\nlinha solta")
    assert r["ok"] and [p["confirmado"] for p in r["propostas"]] == [False, False] and r["nao_reconhecidas"] == ["linha solta"]
    assert "sim explícito" in r["aviso"]
    assert estado_dos_itens(kit.store.eventos(kit.sessao.id))[1]["estado"] == "proposto"
    assert kit.e.progresso()["contagem"]["respondido"] == 0  # a proposal counts for nothing
    assert kit.e.registrar_resposta(item=1, situacao="respondido", valor="Acme", trecho="sim", origem="importado")["erro"] == "trecho_nao_encontrado"
    kit.diz("sim, está certo")
    assert kit.e.registrar_resposta(item=1, situacao="respondido", valor="Acme", trecho="sim, está certo", origem="importado")["ok"]
    # an item that was never imported cannot claim that origin
    assert kit.e.registrar_resposta(item=2, situacao="respondido", valor="Julia", trecho="sim", origem="importado")["erro"] == "nao_foi_importado"


def test_import_errors_are_payloads(kit):
    assert kit.e.importar_configuracao(texto="  ")["erro"] == "texto_vazio"
    assert kit.e.importar_configuracao(texto="x" * 70_000)["erro"] == "texto_muito_longo"


def test_not_applicable_item_is_refused(kit):
    kit.diz("só locação")
    assert kit.e.registrar_resposta(item=9, situacao="respondido", valor="locacao", trecho="só locação")["ok"]
    r = kit.e.registrar_resposta(item=28, situacao="respondido", valor="sim", trecho="só locação")
    assert r["erro"] == "item_nao_aplicavel"
    assert 28 not in [i["n"] for i in kit.e.progresso()["itens"]]


def test_unknown_or_malformed_item_is_a_payload_not_a_crash(kit):
    assert kit.e.registrar_resposta(item=99, situacao="respondido", valor="x", trecho="x")["erro"] == "item_desconhecido"
    assert kit.e.registrar_resposta(item="1", situacao="respondido")["erro"] == "item_invalido"
    assert kit.e.registrar_resposta(item=1, situacao="talvez")["erro"] == "situacao_invalida"


def _responde(kit: Kit, n: int, valor, fala: str) -> None:
    kit.diz(fala)
    r = kit.e.registrar_resposta(item=n, situacao="respondido", valor=valor, trecho=fala)
    assert r["ok"], r


def test_apply_requires_a_summary_then_a_yes_written_after_it_and_records_the_report(kit):
    _responde(kit, 1, "Acme Imóveis", "Acme Imóveis")
    assert kit.e.revisar_e_aplicar(fase="aplicar", confirmacao_cliente="sim")["erro"] == "resumo_desatualizado"
    res = kit.e.revisar_e_aplicar(fase="resumo")
    assert res["ok"] and res["itens"] == [{"n": 1, "titulo": "Nome comercial", "valor": "Acme Imóveis"}]
    assert 3 in res["faltando_obrigatorios"]
    # a yes that was said BEFORE the summary is not a confirmation of it
    antes = kit.e.revisar_e_aplicar(fase="aplicar", confirmacao_cliente="Acme Imóveis")
    assert antes["erro"] == "confirmacao_ausente" and kit.spec_writes == []
    kit.diz("pode aplicar")
    out = kit.e.revisar_e_aplicar(fase="aplicar", confirmacao_cliente="pode aplicar")
    assert out["ok"] and out["aplicados"] == 1 and out["proximo_passo"] == "modo_avaliacao"
    assert kit.spec_writes == [{"nome_imobiliaria": "Acme Imóveis"}]
    assert kit.tipos()[-2:] == ["resumo_apresentado", "aplicacao_executada"]


def test_a_changed_answer_after_the_summary_invalidates_it(kit):
    _responde(kit, 1, "Acme", "Acme")
    kit.e.revisar_e_aplicar(fase="resumo")
    _responde(kit, 2, "Ana", "chame de Ana")
    kit.diz("pode aplicar")
    assert kit.e.revisar_e_aplicar(fase="aplicar", confirmacao_cliente="pode aplicar")["erro"] == "resumo_desatualizado"
    assert kit.spec_writes == []


def test_summary_without_answers_and_bad_phase(kit):
    assert kit.e.revisar_e_aplicar(fase="resumo")["erro"] == "sem_respostas"
    assert kit.e.revisar_e_aplicar(fase="agora")["erro"] == "fase_invalida"


def test_a_route_level_refusal_comes_back_as_a_payload_the_model_can_say(kit):
    _responde(kit, 1, "Acme", "Acme")
    kit.e.revisar_e_aplicar(fase="resumo")
    kit.diz("aplique")
    kit.recusa_apply = HTTPException(409, {"detail": "A empresa não tem uma concessão ativa.", "code": "sem_concessao_ativa"})
    r = kit.e.revisar_e_aplicar(fase="aplicar", confirmacao_cliente="aplique")
    assert r["erro"] == "aplicacao_recusada" and r["codigo"] == "sem_concessao_ativa" and "concessão" in r["motivo"]
    assert "aplicacao_executada" not in kit.tipos()


def test_human_step_and_sw_items_are_reported_per_item(kit):
    _responde(kit, 20, "XML do portal", "usamos XML do portal")
    _responde(kit, 22, "não", "não informe o iptu")
    kit.e.revisar_e_aplicar(fase="resumo")
    kit.diz("ok pode")
    out = kit.e.revisar_e_aplicar(fase="aplicar", confirmacao_cliente="ok pode")
    estados = {i["n"]: i["estado"] for i in out["itens"]}
    assert estados[20] == "pendente_humano"
    assert 22 in estados and kit.sw.chamadas  # the SW port took the setting
