"""
DTO mapper shape tests — Phase 3b operational contract pinning.

These tests pin the operational DTO contract for raw-DB-row → HTTP-response
mappers added to PII-rich domains during Phase 3b of `erp-wiring`. They:

  1. Verify the mapper PROJECTS the whitelisted fields (frontend types contract).
  2. Verify the mapper STRIPS unknown / sensitive fields (silent-schema-drift +
     PII over-share defense).
  3. Verify None passthrough (caller-safe).

Defers `response_model=PydanticDTO` rollout to follow-up `erp-imobiliario-
dto-contract` per PROJECT.md §7 Q-E.

Direct-import / module-level — does NOT require the app fixture, so they run
green even while the worktree's seed `noctusai_lib.domain.ai.consent` import
is broken (pre-existing failure, out of Phase 3b scope).
"""
import pytest

from app.services.clientes_service import (
    _CLIENTE_DTO_FIELDS,
    cliente_row_to_dto,
    cliente_rows_to_dto,
)
from app.services.financeiro_service import (
    _LANCAMENTO_DTO_FIELDS,
    lancamento_row_to_dto,
    lancamento_rows_to_dto,
)
from app.services.contratos_service import (
    _CONTRATO_DTO_FIELDS,
    _PARCELA_DTO_FIELDS,
    contrato_row_to_dto,
    contrato_rows_to_dto,
    parcela_row_to_dto,
    parcela_rows_to_dto,
)
from app.services.locacoes_service import (
    _CONTRATO_LOCACAO_DTO_FIELDS,
    contrato_locacao_row_to_dto,
    contrato_locacao_rows_to_dto,
)
from app.services.propostas_service import (
    _PROPOSTA_DTO_FIELDS,
    proposta_row_to_dto,
    proposta_rows_to_dto,
)
from app.services.portal_cliente_service import (
    _CHAMADO_PORTAL_FIELDS,
    _PORTAL_ACESSO_ISSUED_FIELDS,
    _PORTAL_ACESSO_LISTING_FIELDS,
    chamado_portal_row_to_dto,
    chamado_portal_rows_to_dto,
    portal_acesso_issued_to_dto,
    portal_acesso_listing_rows_to_dto,
    portal_acesso_listing_to_dto,
)
from app.routers.portal_externo import (
    _PORTAL_TOKEN_ISSUED_FIELDS,
    _PORTAL_TOKEN_LISTING_FIELDS,
    portal_token_issued_to_dto,
    portal_token_listing_rows_to_dto,
    portal_token_listing_to_dto,
)


# ---------------------------------------------------------------------------
# Cliente DTO
# ---------------------------------------------------------------------------

class TestClienteRowToDto:
    def test_strips_unknown_fields(self):
        row = {
            "id": "c1",
            "nome": "João",
            "email": "joao@test.com",
            "telefone": "11999999999",
            "etapa_atual": "qualificacao",
            "arquivado": False,
            # Sensitive / internal columns that MUST be stripped:
            "internal_audit_trail": "secret",
            "auth_token_hash": "deadbeef",
            "rls_org_id": "should-not-leak",
        }
        dto = cliente_row_to_dto(row)
        assert "internal_audit_trail" not in dto
        assert "auth_token_hash" not in dto
        assert "rls_org_id" not in dto
        assert dto["nome"] == "João"
        assert dto["email"] == "joao@test.com"

    def test_projects_whitelist_only(self):
        row = {k: f"value-{k}" for k in _CLIENTE_DTO_FIELDS}
        row["extra_leak"] = "should-strip"
        dto = cliente_row_to_dto(row)
        assert set(dto.keys()) == set(_CLIENTE_DTO_FIELDS)
        assert "extra_leak" not in dto

    def test_none_passthrough(self):
        assert cliente_row_to_dto(None) is None
        assert cliente_row_to_dto({}) == {}

    def test_rows_to_dto(self):
        rows = [
            {"id": "c1", "nome": "A", "secret": "x"},
            {"id": "c2", "nome": "B", "secret": "y"},
        ]
        dtos = cliente_rows_to_dto(rows)
        assert len(dtos) == 2
        assert all("secret" not in d for d in dtos)
        assert [d["id"] for d in dtos] == ["c1", "c2"]

    def test_rows_to_dto_empty(self):
        assert cliente_rows_to_dto([]) == []
        assert cliente_rows_to_dto(None) == []


# ---------------------------------------------------------------------------
# Lancamento DTO (financeiro)
# ---------------------------------------------------------------------------

class TestLancamentoRowToDto:
    def test_strips_unknown_fields(self):
        row = {
            "id": "l1",
            "tipo": "receita",
            "valor": 1500.0,
            "categoria": "venda",
            "descricao": "Comissão",
            "status": "pago",
            "data_vencimento": "2026-05-11",
            "org_id": "MUST-STRIP",  # not in operational contract
            "internal_audit_at": "MUST-STRIP",
        }
        dto = lancamento_row_to_dto(row)
        assert "org_id" not in dto
        assert "internal_audit_at" not in dto
        assert dto["valor"] == 1500.0
        assert dto["tipo"] == "receita"

    def test_projects_whitelist_only(self):
        row = {k: 1 for k in _LANCAMENTO_DTO_FIELDS}
        row["leak"] = 1
        dto = lancamento_row_to_dto(row)
        assert set(dto.keys()) == set(_LANCAMENTO_DTO_FIELDS)

    def test_none_passthrough(self):
        assert lancamento_row_to_dto(None) is None

    def test_rows_to_dto(self):
        dtos = lancamento_rows_to_dto([{"id": "l1", "leak": "x"}])
        assert dtos == [{"id": "l1"}]


# ---------------------------------------------------------------------------
# Contrato + Parcela DTO
# ---------------------------------------------------------------------------

class TestContratoRowToDto:
    def test_strips_unknown_fields(self):
        row = {
            "id": "k1",
            "tipo": "venda",
            "status": "ativo",
            "cliente_id": "c1",
            "imovel_id": "i1",
            "valor_total": 250000,
            "num_parcelas": 12,
            "data_inicio": "2026-05-11",
            "internal_only_score": 99,
        }
        dto = contrato_row_to_dto(row)
        assert "internal_only_score" not in dto
        assert dto["valor_total"] == 250000

    def test_projects_whitelist_only(self):
        row = {k: 1 for k in _CONTRATO_DTO_FIELDS}
        row["leak"] = 1
        dto = contrato_row_to_dto(row)
        assert set(dto.keys()) == set(_CONTRATO_DTO_FIELDS)

    def test_rows_to_dto(self):
        rows = [{"id": "k1", "leak": "x"}, {"id": "k2", "leak": "y"}]
        dtos = contrato_rows_to_dto(rows)
        assert [d["id"] for d in dtos] == ["k1", "k2"]
        assert all("leak" not in d for d in dtos)


class TestParcelaRowToDto:
    def test_strips_unknown_fields(self):
        row = {
            "id": "p1",
            "contrato_id": "k1",
            "numero": 1,
            "valor": 1000,
            "status": "pendente",
            "data_vencimento": "2026-06-11",
            "audit_internal": "x",
        }
        dto = parcela_row_to_dto(row)
        assert "audit_internal" not in dto
        assert dto["numero"] == 1

    def test_projects_whitelist_only(self):
        row = {k: 1 for k in _PARCELA_DTO_FIELDS}
        row["org_id"] = "MUST-STRIP"
        dto = parcela_row_to_dto(row)
        assert "org_id" not in dto
        assert set(dto.keys()) == set(_PARCELA_DTO_FIELDS)

    def test_rows_to_dto(self):
        dtos = parcela_rows_to_dto([{"id": "p1", "leak": "x"}])
        assert dtos == [{"id": "p1"}]


# ---------------------------------------------------------------------------
# ContratoLocacao DTO
# ---------------------------------------------------------------------------

class TestContratoLocacaoRowToDto:
    def test_strips_unknown_fields(self):
        row = {
            "id": "cl1",
            "imovel_id": "i1",
            "locatario_id": "l1",
            "valor_aluguel": 2500,
            "status": "ativo",
            "data_inicio": "2026-05-11",
            "data_fim": "2027-05-11",
            "indice_reajuste": "IGPM",
            "dia_vencimento": 10,
            "taxa_administracao": 10.0,
            "deprecated_field": "MUST-STRIP",
        }
        dto = contrato_locacao_row_to_dto(row)
        assert "deprecated_field" not in dto
        assert dto["valor_aluguel"] == 2500

    def test_projects_whitelist_only(self):
        row = {k: 1 for k in _CONTRATO_LOCACAO_DTO_FIELDS}
        row["leak"] = 1
        dto = contrato_locacao_row_to_dto(row)
        assert set(dto.keys()) == set(_CONTRATO_LOCACAO_DTO_FIELDS)

    def test_rows_to_dto(self):
        dtos = contrato_locacao_rows_to_dto([{"id": "cl1", "leak": "x"}])
        assert dtos == [{"id": "cl1"}]


# ---------------------------------------------------------------------------
# Proposta DTO
# ---------------------------------------------------------------------------

class TestPropostaRowToDto:
    def test_strips_unknown_fields(self):
        row = {
            "id": "pr1",
            "imovel_id": "i1",
            "cliente_id": "c1",
            "corretor_id": "co1",
            "valor_proposta": 100000,
            "status": "enviada",
            "historico": [],
            "scoring_internal": 0.87,
        }
        dto = proposta_row_to_dto(row)
        assert "scoring_internal" not in dto
        assert dto["valor_proposta"] == 100000
        assert dto["historico"] == []

    def test_projects_whitelist_only(self):
        row = {k: 1 for k in _PROPOSTA_DTO_FIELDS}
        row["leak"] = 1
        dto = proposta_row_to_dto(row)
        assert set(dto.keys()) == set(_PROPOSTA_DTO_FIELDS)

    def test_rows_to_dto(self):
        dtos = proposta_rows_to_dto([{"id": "pr1", "leak": "x"}])
        assert dtos == [{"id": "pr1"}]


# ---------------------------------------------------------------------------
# Portal cliente — TOKEN SECURITY (listing must hide token)
# ---------------------------------------------------------------------------

class TestPortalAcessoListing:
    def test_listing_hides_token(self):
        """SECURITY: admin listing endpoints MUST NOT leak portal bearer tokens."""
        row = {
            "id": "pa1",
            "cliente_id": "c1",
            "token": "SECRET-BEARER-TOKEN-MUST-NEVER-LEAK",
            "ativo": True,
            "created_at": "2026-05-11",
        }
        dto = portal_acesso_listing_to_dto(row)
        assert "token" not in dto, (
            "PORTAL TOKEN LEAK in listing — admin listing must hide raw bearer "
            "tokens. Re-issue via POST /gerar-acesso instead."
        )
        assert dto["cliente_id"] == "c1"

    def test_listing_rows_hide_tokens(self):
        rows = [
            {"id": "pa1", "cliente_id": "c1", "token": "tok-1", "ativo": True},
            {"id": "pa2", "cliente_id": "c2", "token": "tok-2", "ativo": True},
        ]
        dtos = portal_acesso_listing_rows_to_dto(rows)
        assert all("token" not in d for d in dtos)
        assert [d["id"] for d in dtos] == ["pa1", "pa2"]

    def test_listing_whitelist(self):
        row = {k: 1 for k in _PORTAL_ACESSO_LISTING_FIELDS}
        row["token"] = "MUST-STRIP"
        row["org_id"] = "MUST-STRIP"
        dto = portal_acesso_listing_to_dto(row)
        assert "token" not in dto
        assert "org_id" not in dto
        assert set(dto.keys()) == set(_PORTAL_ACESSO_LISTING_FIELDS)


class TestPortalAcessoIssued:
    def test_issued_includes_token(self):
        """POST /gerar-acesso is the one-shot token issue moment."""
        row = {
            "id": "pa1",
            "cliente_id": "c1",
            "token": "FRESH-TOKEN",
            "ativo": True,
            "created_at": "2026-05-11",
            "org_id": "MUST-STRIP",
        }
        dto = portal_acesso_issued_to_dto(row)
        assert dto["token"] == "FRESH-TOKEN"
        assert "org_id" not in dto

    def test_issued_whitelist(self):
        row = {k: 1 for k in _PORTAL_ACESSO_ISSUED_FIELDS}
        row["leak"] = 1
        dto = portal_acesso_issued_to_dto(row)
        assert set(dto.keys()) == set(_PORTAL_ACESSO_ISSUED_FIELDS)


class TestChamadoPortal:
    def test_strips_unknown_fields(self):
        row = {
            "id": "ch1",
            "cliente_id": "c1",
            "portal_acesso_id": "pa1",
            "assunto": "Test",
            "descricao": "Body",
            "status": "aberto",
            "prioridade": "media",
            "internal_routing_hint": "MUST-STRIP",
        }
        dto = chamado_portal_row_to_dto(row)
        assert "internal_routing_hint" not in dto
        assert dto["assunto"] == "Test"

    def test_projects_whitelist_only(self):
        row = {k: 1 for k in _CHAMADO_PORTAL_FIELDS}
        row["leak"] = 1
        dto = chamado_portal_row_to_dto(row)
        assert set(dto.keys()) == set(_CHAMADO_PORTAL_FIELDS)

    def test_rows_to_dto(self):
        dtos = chamado_portal_rows_to_dto([{"id": "ch1", "leak": "x"}])
        assert dtos == [{"id": "ch1"}]


# ---------------------------------------------------------------------------
# Portal externo (portal_tokens) — TOKEN SECURITY (Phase 6 N=2 absorption of
# Phase 3b token-leak defense). Listing must hide raw bearer tokens; the
# one-shot issue at POST /gerar-link is the only token-shown surface.
# ---------------------------------------------------------------------------

class TestPortalTokenListing:
    def test_listing_hides_token(self):
        """SECURITY: admin listing endpoints MUST NOT leak portal bearer tokens."""
        row = {
            "id": "pt1",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos",
            "email": "carlos@test.com",
            "token": "SECRET-EXTERNO-TOKEN-MUST-NEVER-LEAK",
            "expires_at": "2026-08-11T00:00:00Z",
            "is_active": True,
            "created_at": "2026-05-11",
        }
        dto = portal_token_listing_to_dto(row)
        assert "token" not in dto, (
            "PORTAL TOKEN LEAK in listing — admin listing must hide raw bearer "
            "tokens. Re-issue via POST /gerar-link instead."
        )
        assert dto["nome"] == "Carlos"

    def test_listing_rows_hide_tokens(self):
        rows = [
            {"id": "pt1", "tipo": "proprietario", "nome": "Carlos", "token": "tok-1"},
            {"id": "pt2", "tipo": "locatario", "nome": "Ana", "token": "tok-2"},
        ]
        dtos = portal_token_listing_rows_to_dto(rows)
        assert all("token" not in d for d in dtos)
        assert [d["id"] for d in dtos] == ["pt1", "pt2"]

    def test_listing_whitelist(self):
        row = {k: 1 for k in _PORTAL_TOKEN_LISTING_FIELDS}
        row["token"] = "MUST-STRIP"
        row["org_id"] = "MUST-STRIP"
        dto = portal_token_listing_to_dto(row)
        assert "token" not in dto
        assert "org_id" not in dto
        assert set(dto.keys()) == set(_PORTAL_TOKEN_LISTING_FIELDS)

    def test_none_passthrough(self):
        assert portal_token_listing_to_dto(None) is None
        assert portal_token_listing_rows_to_dto(None) == []
        assert portal_token_listing_rows_to_dto([]) == []


class TestPortalTokenIssued:
    def test_issued_includes_token(self):
        """POST /gerar-link is the one-shot token issue moment."""
        row = {
            "id": "pt1",
            "tipo": "proprietario",
            "pessoa_id": "p1",
            "nome": "Carlos",
            "token": "FRESH-EXTERNO-TOKEN",
            "expires_at": "2026-08-11T00:00:00Z",
            "is_active": True,
            "created_at": "2026-05-11",
            "org_id": "MUST-STRIP",
        }
        dto = portal_token_issued_to_dto(row)
        assert dto["token"] == "FRESH-EXTERNO-TOKEN"
        assert "org_id" not in dto

    def test_issued_whitelist(self):
        row = {k: 1 for k in _PORTAL_TOKEN_ISSUED_FIELDS}
        row["leak"] = 1
        dto = portal_token_issued_to_dto(row)
        assert set(dto.keys()) == set(_PORTAL_TOKEN_ISSUED_FIELDS)

    def test_none_passthrough(self):
        assert portal_token_issued_to_dto(None) is None
