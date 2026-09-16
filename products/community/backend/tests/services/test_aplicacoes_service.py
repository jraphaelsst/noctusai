"""Tests for `AplicacoesService` / `PublicAplicacoesService` — contract
§Aplicações business rules (opcoes validation, approve idempotency,
public-submit validation)."""
import asyncio
from uuid import UUID

from noctusai_lib.testing import MockSupabaseClient

from app.services.aplicacoes_service import (
    AplicacoesService,
    AplicacoesServiceError,
    PublicAplicacoesService,
)

ORG = UUID("00000000-0000-0000-0000-000000000123")
PERGUNTA_ID = "11111111-1111-1111-1111-111111111111"
APLICACAO_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _aplicacao_row(**over) -> dict:
    base = {
        "id": APLICACAO_ID,
        "org_id": str(ORG),
        "nome": "Joana",
        "email": "joana@x.com",
        "telefone": None,
        "respostas": {},
        "status": "pendente",
        "motivo": None,
        "revisado_por": None,
        "revisado_em": None,
        "membro_id": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    base.update(over)
    return base


class TestPerguntaOpcoesValidation:
    def test_escolha_unica_without_opcoes_raises_422(self):
        mock = MockSupabaseClient()
        svc = AplicacoesService(mock, org_id=ORG)
        try:
            asyncio.run(svc.create_pergunta(payload={
                "pergunta": "Signo?", "tipo": "escolha_unica", "opcoes": [],
                "obrigatoria": True, "ordem": 0, "ativa": True,
            }))
            assert False, "expected AplicacoesServiceError"
        except AplicacoesServiceError as exc:
            assert exc.status_code == 422

    def test_texto_type_without_opcoes_is_fine(self):
        mock = MockSupabaseClient()
        svc = AplicacoesService(mock, org_id=ORG)
        result = asyncio.run(svc.create_pergunta(payload={
            "pergunta": "Nome?", "tipo": "texto", "opcoes": [],
            "obrigatoria": True, "ordem": 0, "ativa": True,
        }))
        assert result["pergunta"] == "Nome?"


class TestAprovarIdempotency:
    def test_already_approved_returns_same_membro(self):
        membro_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        mock = MockSupabaseClient()
        mock.set_table_data("aplicacoes", [_aplicacao_row(status="aprovada", membro_id=membro_id)])
        mock.set_table_data("membros", [{
            "id": membro_id, "org_id": str(ORG), "nome": "Joana", "email": "joana@x.com",
            "telefone": None, "status": "pendente", "plano_id": None, "origem": "aplicacao",
            "tags": [], "user_id": None, "observacoes": None, "entrou_em": None,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        svc = AplicacoesService(mock, org_id=ORG)
        result = asyncio.run(svc.aprovar(
            aplicacao_id=APLICACAO_ID, plano_id=None, ativar=False, revisor_id="u1",
        ))
        assert result["membro"]["id"] == membro_id

    def test_rejected_raises_409(self):
        mock = MockSupabaseClient()
        mock.set_table_data("aplicacoes", [_aplicacao_row(status="rejeitada")])
        svc = AplicacoesService(mock, org_id=ORG)
        try:
            asyncio.run(svc.aprovar(
                aplicacao_id=APLICACAO_ID, plano_id=None, ativar=False, revisor_id="u1",
            ))
            assert False, "expected AplicacoesServiceError"
        except AplicacoesServiceError as exc:
            assert exc.status_code == 409
            assert exc.detail == "Essa inscrição já foi rejeitada."


class TestPublicSubmitValidation:
    def test_missing_obrigatoria_raises_422(self):
        mock = MockSupabaseClient()
        mock.set_table_data("aplicacao_perguntas", [{
            "id": PERGUNTA_ID, "org_id": str(ORG), "pergunta": "Idade?", "tipo": "texto",
            "opcoes": [], "obrigatoria": True, "ordem": 0, "ativa": True,
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
        }])
        svc = PublicAplicacoesService(mock, org_id=ORG)
        try:
            asyncio.run(svc.submit(payload={
                "nome": "Joana", "email": "joana@x.com", "telefone": None, "respostas": {},
            }))
            assert False, "expected AplicacoesServiceError"
        except AplicacoesServiceError as exc:
            assert exc.status_code == 422
            assert exc.detail == "Responda todas as perguntas obrigatórias."

    def test_unknown_question_id_raises_422(self):
        mock = MockSupabaseClient()
        svc = PublicAplicacoesService(mock, org_id=ORG)
        try:
            asyncio.run(svc.submit(payload={
                "nome": "Joana", "email": "joana@x.com", "telefone": None,
                "respostas": {"does-not-exist": "x"},
            }))
            assert False, "expected AplicacoesServiceError"
        except AplicacoesServiceError as exc:
            assert exc.status_code == 422
            assert exc.detail == "Pergunta inválida no formulário."

    def test_duplicate_pendente_email_raises_409(self):
        mock = MockSupabaseClient()
        mock.set_table_data("aplicacoes", [_aplicacao_row(status="pendente")])
        svc = PublicAplicacoesService(mock, org_id=ORG)
        try:
            asyncio.run(svc.submit(payload={
                "nome": "Joana", "email": "joana@x.com", "telefone": None, "respostas": {},
            }))
            assert False, "expected AplicacoesServiceError"
        except AplicacoesServiceError as exc:
            assert exc.status_code == 409
