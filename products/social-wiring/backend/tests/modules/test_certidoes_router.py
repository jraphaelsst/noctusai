"""Certidões Negativas — HTTP-surface tests.

Ports `products/erp-imobiliario/backend/tests/routers/test_certidoes_router.py`
and adds what this port introduced: the org boundary (migration 091 replaced
ERP's `created_by = auth.uid()` scoping), the authorization check on
`/download`, and the storage seam behind `/download` + `/download-zip`.

`app/main.py` deliberately does NOT register this module yet — peer branches are
live in that file and the tech-lead wires ``MODULES`` at integration time (see
``app/modules/certidoes/__init__.py``). This module mounts the router onto the
shared ``app.main.app`` object IN-MEMORY at collection time, which touches
nothing on disk and is exactly what the real wiring step will do. Same approach
as ``tests/modules/n8n/conftest.py``.
"""
from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing import MockSupabaseClient, MockSupabaseResponse

from app.main import app as _app
from app.modules.certidoes import service
from app.modules.certidoes.deps import get_certidoes_client, get_storage_backend
from app.modules.certidoes.routers import certidoes as _certidoes_router_mod

_app.include_router(_certidoes_router_mod.router)

#: The module's single credential-resolution point. Substituting HERE (not
#: `noctusai_lib`'s `resolve_credential`) is the point of
#: `credentials.resolve_key`: the store behind it moved to the product-local
#: encrypted one and these tests did not have to follow it into two tiers.
_CRED = "app.modules.certidoes.credentials.resolve_api_key"

#: `coerce_org_uuid("test-org-123")` — the org the shared `client` fixture
#: authenticates as (`uuid5(NAMESPACE_OID, "test-org-123")`). Fixtures seed THIS
#: org so the authenticated caller and the seeded rows agree on "my org".
CALLER_ORG = "48ab962b-ec86-517e-9e42-7b581f622377"
OTHER_ORG = "22222222-2222-4222-8222-222222222222"
#: `VincularParteRequest.atendimento_parte_id` is a `UUID` field — a plain
#: slug like `"parte-001"` would 422 before the handler ever runs.
PARTE_ID = "33333333-3333-4333-8333-333333333333"

BASE = "/api/certidoes"


def _msg(resp) -> str:
    """The user-facing message out of the seed's error envelope.

    `noctusai_lib.primitives.exceptions.http_exception_handler` re-shapes every
    `HTTPException` into `{"error": {"code", "message"}}` — there is no top-level
    `detail` key on this platform, and a test reading one would `KeyError`
    rather than assert anything about the message.
    """
    return resp.json()["error"]["message"]


def _consulta(**overrides) -> dict:
    row = {
        "id": "consulta-001",
        "org_id": CALLER_ORG,
        "created_by": "test-user-123",
        "tipo_documento": "cpf",
        "documento": "12345678901",
        "nome": "João da Silva",
        "data_nascimento": "1990-01-15",
        "genero": "M",
        "rg": None,
        "nome_mae": None,
        "nome_pai": None,
        "status": "pendente",
        "total_certidoes": 10,
        "concluidas": 0,
        "created_at": "2026-03-05T10:00:00+00:00",
        "updated_at": "2026-03-05T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def _resultado(**overrides) -> dict:
    row = {
        "id": "resultado-001",
        "consulta_id": "consulta-001",
        "org_id": CALLER_ORG,
        "tipo": "cnd_federal",
        "nome_display": "CND Federal (Receita)",
        "ordem": 1,
        "status": "pendente",
        "analise_ia": None,
        "arquivo_url": None,
        "arquivo_nome": None,
        "api_response": None,
        "erro_mensagem": None,
        "api_requested_at": None,
        "created_at": "2026-03-05T10:00:00+00:00",
        "updated_at": "2026-03-05T10:00:00+00:00",
    }
    row.update(overrides)
    return row


@pytest.fixture(autouse=True)
def _reset_recovery_throttle():
    """The 60-second recovery throttle is a module global.

    Reset per test so the recovery leg is exercised deterministically instead of
    depending on which test in the session ran first.
    """
    _certidoes_router_mod._last_stale_check = 0.0
    yield
    _certidoes_router_mod._last_stale_check = 0.0


@pytest.fixture
def certidoes_db():
    """Override this module's two DI seams and hand the test both doubles.

    A `FakeStorageBackend` rather than `MockSupabaseClient.storage` (a bare
    `MagicMock` that answers any call with another `MagicMock`) — an
    un-overridden storage seam would let a download test "pass" against garbage.
    """
    db = MockSupabaseClient(schema="social_wiring")
    storage = FakeStorageBackend()
    _app.dependency_overrides[get_certidoes_client] = lambda: db
    _app.dependency_overrides[get_storage_backend] = lambda: storage
    yield db, storage
    _app.dependency_overrides.pop(get_certidoes_client, None)
    _app.dependency_overrides.pop(get_storage_backend, None)


@pytest.fixture
def override_service():
    """Substitute service operations through the router's DI seam.

    🔴 THIS REPLACED EVERY `patch.object(service, "...", ...)` IN THIS FILE.

    The router resolves its collaborator with
    `Depends(get_certidoes_service)`, so a test swaps the DEPENDENCY and never
    the module. Two things follow that patching could not give us: production's
    service object is never mutated (so nothing leaks into the next test), and
    the operations NOT named here stay real — `dataclasses.replace` starts from
    a fresh all-real `build_default_service()`.

    Usage::

        override_service(processar_consulta=AsyncMock())

    → KB § PATTERNS/backend/di-test-seam.md (seam 1)
    """
    from app.modules.certidoes.deps import (
        build_default_service,
        get_certidoes_service,
    )

    prev = _app.dependency_overrides.get(get_certidoes_service)
    chosen: dict = {}

    def _apply(**ops):
        chosen.update(ops)
        svc = dataclasses.replace(build_default_service(), **chosen)
        _app.dependency_overrides[get_certidoes_service] = lambda: svc
        return svc

    yield _apply

    if prev is None:
        _app.dependency_overrides.pop(get_certidoes_service, None)
    else:
        _app.dependency_overrides[get_certidoes_service] = prev


def _put_blob(storage, key: str, data: bytes = b"%PDF-x") -> None:
    """Seed a blob into the SAME `FakeStorageBackend` the route resolves.

    Lets the download tests run the REAL `read_certidao_bytes` — including its
    key-vs-URL branch — instead of stubbing it out. `asyncio.run` because these
    are sync TestClient tests and the storage seam is async.
    """
    asyncio.run(storage.put(bucket=service.BUCKET, key=key, data=data))


def _seed(db, consultas=None, resultados=None):
    db.set_table_data("certidao_consultas", consultas if consultas is not None else [])
    db.set_table_data("certidao_resultados", resultados if resultados is not None else [])


# ---------------------------------------------------------------------------
# GET /tipos
# ---------------------------------------------------------------------------


class TestListarTipos:
    def test_retorna_os_dez_tipos(self, client, certidoes_db):
        resp = client.get(f"{BASE}/tipos")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 10
        assert data[0]["tipo"] == "cnd_federal"
        assert data[0]["nome"] == "CND Federal (Receita)"

    def test_cada_tipo_tem_tipo_nome_ordem(self, client, certidoes_db):
        for item in client.get(f"{BASE}/tipos").json()["data"]:
            assert set(item) == {"tipo", "nome", "ordem"}


# ---------------------------------------------------------------------------
# GET /consultas
# ---------------------------------------------------------------------------


class TestListarConsultas:
    def test_lista_vazia(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        resp = client.get(f"{BASE}/consultas")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_lista_com_dados(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        data = client.get(f"{BASE}/consultas").json()["data"]
        assert len(data) == 1
        assert data[0]["nome"] == "João da Silva"

    def test_nao_vaza_consultas_de_outra_org(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[
            _consulta(),
            _consulta(id="alheia", org_id=OTHER_ORG, nome="Outra Org"),
        ])
        data = client.get(f"{BASE}/consultas").json()["data"]
        assert [c["id"] for c in data] == ["consulta-001"]

    def test_nao_lista_consultas_excluidas(self, client, certidoes_db):
        """Migration 161: a soft-deleted consulta is invisible to the list,
        the same shape a hard-deleted one always was."""
        db, _ = certidoes_db
        _seed(db, consultas=[
            _consulta(),
            _consulta(
                id="excluida", nome="Excluída",
                excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
            ),
        ])
        data = client.get(f"{BASE}/consultas").json()["data"]
        assert [c["id"] for c in data] == ["consulta-001"]

    def test_conta_sucessos_e_erros_por_consulta(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(
            db,
            consultas=[_consulta()],
            resultados=[
                _resultado(id="r1", status="sucesso"),
                _resultado(id="r2", status="sucesso", ordem=2),
                _resultado(id="r3", status="erro", ordem=3),
                _resultado(id="r4", status="pendente", ordem=4),
            ],
        )
        row = client.get(f"{BASE}/consultas").json()["data"][0]
        assert row["concluidas"] == 2
        assert row["erros"] == 1

    def test_filtro_status(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[
            _consulta(),
            _consulta(id="c2", status="concluida"),
        ])
        data = client.get(f"{BASE}/consultas?status=concluida").json()["data"]
        assert [c["id"] for c in data] == ["c2"]

    def test_busca_aceita_nome_e_documento(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        assert client.get(f"{BASE}/consultas?busca=João").status_code == 200
        assert client.get(f"{BASE}/consultas?busca=123456").status_code == 200

    def test_page_invalida_e_422(self, client, certidoes_db):
        assert client.get(f"{BASE}/consultas?page=0").status_code == 422

    def test_page_size_excede_o_teto_e_422(self, client, certidoes_db):
        assert client.get(f"{BASE}/consultas?page_size=500").status_code == 422

    def test_resposta_traz_total_e_pagina(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        body = client.get(f"{BASE}/consultas?page=1&page_size=10").json()
        assert "total" in body or "total" in body.get("pagination", {})

    def test_recupera_trabalho_encalhado_uma_vez_por_minuto(
        self, client, certidoes_db, override_service
    ):
        """The recovery is throttled so a 3-second poll does not add a DB
        round-trip per tick. Two calls in a row must recover ONCE."""
        db, _ = certidoes_db
        _seed(db)
        rec = MagicMock(return_value=0)
        override_service(recover_stale_processando=rec, schedule_tjsp_for_org=MagicMock())
        client.get(f"{BASE}/consultas")
        client.get(f"{BASE}/consultas")
        assert rec.call_count == 1


# ---------------------------------------------------------------------------
# POST /consultas
# ---------------------------------------------------------------------------


class TestCriarConsulta:
    def _payload(self, **overrides):
        body = {
            "tipo_documento": "cpf",
            "documento": "12345678901",
            "nome": "João da Silva",
        }
        body.update(overrides)
        return body

    def test_cria_consulta_cpf(self, client, certidoes_db, override_service):
        db, _ = certidoes_db
        _seed(db)
        override_service(processar_consulta=AsyncMock())
        with patch(_CRED, return_value="tok"):
            resp = client.post(f"{BASE}/consultas", json=self._payload())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["tipo_documento"] == "cpf"
        # TJSP is opt-in (off by default) — nine, not ten.
        assert data["total_certidoes"] == 9
        assert data["org_id"] == CALLER_ORG

    def test_cria_consulta_cnpj(self, client, certidoes_db, override_service):
        db, _ = certidoes_db
        _seed(db)
        override_service(processar_consulta=AsyncMock())
        with patch(_CRED, return_value="tok"):
            resp = client.post(f"{BASE}/consultas", json=self._payload(
                tipo_documento="cnpj", documento="12345678000190", nome="Empresa XPTO"
            ))
        assert resp.status_code == 200

    def test_fan_out_grava_um_resultado_por_tipo(self, client, certidoes_db, override_service):
        db, _ = certidoes_db
        _seed(db)
        override_service(processar_consulta=AsyncMock())
        with patch(_CRED, return_value="tok"):
            client.post(f"{BASE}/consultas", json=self._payload(incluir_tjsp=True))
        # `inserted_payloads` FLATTENS a list-insert into one row per element.
        inserted = db.table("certidao_resultados").inserted_payloads
        assert len(inserted) == 10
        assert {r["tipo"] for r in inserted} == {
            c["tipo"] for c in service.CERTIDOES_CONFIG
        }
        assert sorted(r["ordem"] for r in inserted) == list(range(1, 11))
        assert all(r["org_id"] == CALLER_ORG for r in inserted)
        assert all(r["status"] == "pendente" for r in inserted)

    def test_tjsp_desativado_por_padrao_nao_cria_resultado_tjsp(
        self, client, certidoes_db, override_service
    ):
        db, _ = certidoes_db
        _seed(db)
        override_service(processar_consulta=AsyncMock())
        with patch(_CRED, return_value="tok"):
            resp = client.post(f"{BASE}/consultas", json=self._payload())
        assert resp.status_code == 200
        inserted = db.table("certidao_resultados").inserted_payloads
        assert len(inserted) == 9
        assert "tjsp" not in {r["tipo"] for r in inserted}
        # The switch is a request flag, never a consulta column.
        consulta_rows = db.table("certidao_consultas").inserted_payloads
        assert all("incluir_tjsp" not in r for r in consulta_rows)
        assert resp.json()["data"]["total_certidoes"] == 9

    def test_tjsp_ativado_cria_resultado_tjsp(self, client, certidoes_db, override_service):
        db, _ = certidoes_db
        _seed(db)
        override_service(processar_consulta=AsyncMock())
        with patch(_CRED, return_value="tok"):
            resp = client.post(f"{BASE}/consultas", json=self._payload(incluir_tjsp=True))
        assert resp.status_code == 200
        inserted = db.table("certidao_resultados").inserted_payloads
        assert "tjsp" in {r["tipo"] for r in inserted}
        assert resp.json()["data"]["total_certidoes"] == 10

    def test_dispara_o_processamento_em_background(self, client, certidoes_db, override_service):
        db, _ = certidoes_db
        _seed(db)
        proc = AsyncMock()
        override_service(processar_consulta=proc)
        with patch(_CRED, return_value="tok"):
            client.post(f"{BASE}/consultas", json=self._payload())
        proc.assert_awaited_once()

    def test_campos_opcionais_sao_persistidos(self, client, certidoes_db, override_service):
        db, _ = certidoes_db
        _seed(db)
        override_service(processar_consulta=AsyncMock())
        with patch(_CRED, return_value="tok"):
            resp = client.post(f"{BASE}/consultas", json=self._payload(
                data_nascimento="1990-01-15", genero="M", rg="123456789",
                nome_mae="Maria", nome_pai="José",
            ))
        data = resp.json()["data"]
        assert data["rg"] == "123456789"
        assert data["nome_mae"] == "Maria"

    def test_recusa_sem_token_infosimples_antes_de_gravar(self, client, certidoes_db):
        """🔴 Pre-flight, not post-mortem. Without this the consulta is created,
        ten resultados fan out, and all ten fail with the same message — a row
        the user now has to delete to learn something we knew up front."""
        db, _ = certidoes_db
        _seed(db)
        with patch(_CRED, return_value=None):
            resp = client.post(f"{BASE}/consultas", json=self._payload())
        assert resp.status_code == 422
        assert "InfoSimples" in _msg(resp)
        # VERBATIM the sentence `matriculas` + `settings_router` use. One
        # Settings page, one way of naming it.
        assert _msg(resp).endswith("Configure em Configurações → Chaves de API.")
        assert db.table("certidao_consultas").inserted_payloads == []

    def test_insert_sem_retorno_vira_500(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        db.set_sequential_responses(
            "certidao_consultas", [MockSupabaseResponse(data=[])]
        )
        with patch(_CRED, return_value="tok"):
            resp = client.post(f"{BASE}/consultas", json=self._payload())
        assert resp.status_code == 500

    # ── inbound validation (StrictHttpModel) ───────────────────────────

    def test_documento_curto_demais(self, client, certidoes_db):
        assert client.post(
            f"{BASE}/consultas", json=self._payload(documento="123")
        ).status_code == 422

    def test_documento_longo_demais(self, client, certidoes_db):
        assert client.post(
            f"{BASE}/consultas", json=self._payload(documento="1" * 30)
        ).status_code == 422

    def test_nome_curto_demais(self, client, certidoes_db):
        assert client.post(
            f"{BASE}/consultas", json=self._payload(nome="X")
        ).status_code == 422

    def test_tipo_documento_invalido(self, client, certidoes_db):
        assert client.post(
            f"{BASE}/consultas", json=self._payload(tipo_documento="rg")
        ).status_code == 422

    def test_genero_invalido(self, client, certidoes_db):
        assert client.post(
            f"{BASE}/consultas", json=self._payload(genero="X")
        ).status_code == 422

    def test_campos_obrigatorios_ausentes(self, client, certidoes_db):
        assert client.post(f"{BASE}/consultas", json={}).status_code == 422

    def test_campo_desconhecido_e_recusado_nao_ignorado(self, client, certidoes_db):
        """🔴 `extra="forbid"`. Pydantic's default is to SILENTLY DROP an
        unknown key, so a frontend sending `nomeMae` would get a 200 and a
        certidão issued without the mother's name — which for TJSP is a
        rejection three minutes later, attributed to nothing."""
        resp = client.post(f"{BASE}/consultas", json=self._payload(nomeMae="Maria"))
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /consultas/manual
# ---------------------------------------------------------------------------


class TestCriarConsultaManual:
    def _payload(self, **overrides):
        body = {
            "tipo_documento": "cpf",
            "documento": "12345678901",
            "nome": "Pessoa Fictícia de Teste",
        }
        body.update(overrides)
        return body

    def test_cria_sem_token_infosimples(self, client, certidoes_db):
        """🔴 THE point of this endpoint: no `_CRED` patch anywhere in this
        test — a missing/absent InfoSimples token must never block it,
        unlike `TestCriarConsulta.test_recusa_sem_token_infosimples_antes_
        de_gravar`."""
        db, _ = certidoes_db
        _seed(db)
        resp = client.post(f"{BASE}/consultas/manual", json=self._payload())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["origem"] == "manual"
        assert data["status"] == "pendente"
        assert data["total_certidoes"] == 13

    def test_nao_dispara_processamento_em_background(self, client, certidoes_db, override_service):
        db, _ = certidoes_db
        _seed(db)
        proc = AsyncMock()
        override_service(processar_consulta=proc)
        client.post(f"{BASE}/consultas/manual", json=self._payload())
        proc.assert_not_awaited()

    def test_fan_out_grava_treze_resultados(self, client, certidoes_db):
        """The ten automated types PLUS the three manual-only ones —
        `vincular_parte`'s eventual shape, produced up front instead of
        lazily on link."""
        db, _ = certidoes_db
        _seed(db)
        client.post(f"{BASE}/consultas/manual", json=self._payload())
        inserted = db.table("certidao_resultados").inserted_payloads
        assert len(inserted) == 13
        tipos = {r["tipo"] for r in inserted}
        assert tipos == {c["tipo"] for c in service.CERTIDOES_CONFIG} | {
            "serasa", "tjsp_esaj", "tjsp_eproc",
        }
        assert all(r["status"] == "pendente" for r in inserted)
        assert all(r["org_id"] == CALLER_ORG for r in inserted)

    def test_vincula_a_parte_no_mesmo_passo(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        db.set_table_data("atendimento_partes", [_parte()])
        resp = client.post(
            f"{BASE}/consultas/manual",
            json=self._payload(atendimento_parte_id=PARTE_ID),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["atendimento_parte_id"] == PARTE_ID
        assert data["cliente_id"] == "cliente-001"

    def test_parte_inexistente_e_404_nada_e_gravado(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        db.set_table_data("atendimento_partes", [])
        resp = client.post(
            f"{BASE}/consultas/manual",
            json=self._payload(atendimento_parte_id=PARTE_ID),
        )
        assert resp.status_code == 404
        assert db.table("certidao_consultas").inserted_payloads == []

    def test_vincula_ao_titular_no_mesmo_passo(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        db.set_table_data("clientes", [_cliente()])
        resp = client.post(
            f"{BASE}/consultas/manual",
            json=self._payload(cliente_id=CLIENTE_ID),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["cliente_id"] == CLIENTE_ID

    def test_cliente_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        db.set_table_data("clientes", [])
        resp = client.post(
            f"{BASE}/consultas/manual",
            json=self._payload(cliente_id=CLIENTE_ID),
        )
        assert resp.status_code == 404

    def test_ambos_os_vinculos_e_422(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        resp = client.post(
            f"{BASE}/consultas/manual",
            json=self._payload(atendimento_parte_id=PARTE_ID, cliente_id=CLIENTE_ID),
        )
        assert resp.status_code == 422
        assert db.table("certidao_consultas").inserted_payloads == []

    def test_campo_desconhecido_e_recusado(self, client, certidoes_db):
        resp = client.post(f"{BASE}/consultas/manual", json=self._payload(nomeMae="Maria"))
        assert resp.status_code == 422

    def test_incluir_tjsp_e_aceito_mas_ignorado(self, client, certidoes_db):
        """Inherited from `ConsultaCreate` (extra="forbid" would otherwise
        reject the field the Nova Consulta modal's shared form state can
        still carry), but this path never gates on it — TJSP's placeholder
        resultado is always part of the thirteen."""
        db, _ = certidoes_db
        _seed(db)
        resp = client.post(
            f"{BASE}/consultas/manual", json=self._payload(incluir_tjsp=True)
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total_certidoes"] == 13
        assert "incluir_tjsp" not in db.table("certidao_consultas").inserted_payloads[0]


# ---------------------------------------------------------------------------
# GET /consultas/{id}
# ---------------------------------------------------------------------------


class TestObterConsulta:
    def test_consulta_encontrada_com_resultados(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", status="sucesso"),
            _resultado(id="r2", status="erro", ordem=2),
        ])
        data = client.get(f"{BASE}/consultas/consulta-001").json()["data"]
        assert len(data["resultados"]) == 2
        assert data["concluidas"] == 1
        assert data["erros"] == 1

    def test_consulta_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        resp = client.get(f"{BASE}/consultas/nao-existe")
        assert resp.status_code == 404
        assert _msg(resp) == "Consulta não encontrada"

    def test_consulta_de_outra_org_e_404_nao_403(self, client, certidoes_db):
        """Its EXISTENCE is not this caller's business — a 403 would confirm
        that a consulta with that id exists somewhere."""
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta(id="alheia", org_id=OTHER_ORG)])
        assert client.get(f"{BASE}/consultas/alheia").status_code == 404

    def test_consulta_sem_resultados(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        data = client.get(f"{BASE}/consultas/consulta-001").json()["data"]
        assert data["resultados"] == []
        assert data["concluidas"] == 0


# ---------------------------------------------------------------------------
# POST /consultas/{id}/reprocessar
# ---------------------------------------------------------------------------


class TestReprocessarConsulta:
    def test_reprocessa_com_sucesso(self, client, certidoes_db, override_service):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", status="erro"),
        ])
        override_service(
            processar_consulta=AsyncMock(), schedule_tjsp_for_org=MagicMock()
        )
        resp = client.post(f"{BASE}/consultas/consulta-001/reprocessar")
        assert resp.status_code == 200
        assert "Reprocessamento" in resp.json()["message"]

    def test_erro_nao_tjsp_volta_para_pendente(self, client, certidoes_db, override_service):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", status="erro"),
        ])
        override_service(
            processar_consulta=AsyncMock(), schedule_tjsp_for_org=MagicMock()
        )
        client.post(f"{BASE}/consultas/consulta-001/reprocessar")
        assert db.table("certidao_resultados").select("*").eq(
            "id", "r1"
        ).execute().data[0]["status"] == "pendente"

    def test_erro_tjsp_volta_para_na_fila_nao_pendente(self, client, certidoes_db, override_service):
        """🔴 `pendente` would make the retry fire NOW, and a premature TJSP
        request resets their 30-minute counter — the retry would push the real
        attempt further away rather than closer."""
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r-tjsp", tipo="tjsp", ordem=7, status="erro"),
        ])
        sched = MagicMock()
        override_service(processar_consulta=AsyncMock(), schedule_tjsp_for_org=sched)
        client.post(f"{BASE}/consultas/consulta-001/reprocessar")
        assert db.table("certidao_resultados").select("*").eq(
            "id", "r-tjsp"
        ).execute().data[0]["status"] == "na_fila"
        sched.assert_called_once()

    def test_consulta_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        assert client.post(
            f"{BASE}/consultas/nao-existe/reprocessar"
        ).status_code == 404

    def test_consulta_de_outra_org_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta(id="alheia", org_id=OTHER_ORG)])
        assert client.post(
            f"{BASE}/consultas/alheia/reprocessar"
        ).status_code == 404


# ---------------------------------------------------------------------------
# POST /consultas/{id}/cancelar
# ---------------------------------------------------------------------------


class TestCancelarConsulta:
    def test_cancela_itens_em_andamento(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", status="pendente"),
            _resultado(id="r2", status="na_fila", tipo="tjsp", ordem=7),
        ])
        resp = client.post(f"{BASE}/consultas/consulta-001/cancelar")
        assert resp.status_code == 200
        assert resp.json()["data"]["cancelados"] == 2

    def test_consulta_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        assert client.post(f"{BASE}/consultas/x/cancelar").status_code == 404


# ---------------------------------------------------------------------------
# DELETE /consultas/{id}
# ---------------------------------------------------------------------------


class TestExcluirConsulta:
    """Migration 161: a soft-delete, not a hard one — see the module
    docstring's `🔴 THE arquivo_url CONTRACT` sibling on `excluir_consulta`
    itself for the prod incident this replaces."""

    def test_exclui_com_sucesso(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[])
        resp = client.delete(f"{BASE}/consultas/consulta-001")
        assert resp.status_code == 200
        assert "excluída" in resp.json()["message"]

    def test_estampa_excluida_em_e_por_na_consulta_e_nos_resultados(
        self, client, certidoes_db,
    ):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1"), _resultado(id="r2", ordem=2, tipo="trf3"),
        ])
        resp = client.delete(f"{BASE}/consultas/consulta-001")
        assert resp.status_code == 200

        # `certidoes_db`'s auth fixture is `CALLER_ORG` — the row still
        # exists (this is an UPDATE, not a DELETE), unlike the pre-161 shape
        # `test_estampa...` replaces: `db.table(...).select("*")` bypasses
        # the router's own `.is_("excluida_em", "null")` filter, so the raw
        # row is exactly what a direct table read would see.
        consulta = db.table("certidao_consultas").select("*").eq(
            "id", "consulta-001"
        ).execute().data[0]
        assert consulta["excluida_em"] is not None
        assert consulta["excluida_por"] is not None

        resultados = db.table("certidao_resultados").select("*").execute().data
        assert len(resultados) == 2
        assert all(r["excluida_em"] is not None for r in resultados)
        assert all(r["excluida_por"] is not None for r in resultados)

    def test_nao_apaga_os_blobs(self, client, certidoes_db, override_service):
        """🔴 The pre-161 hard-delete apagava blobs first — a soft-delete
        must NEVER touch storage: `restaurar_consulta` needs the files
        intact, and only the 30-day purge job removes them."""
        db, _ = certidoes_db
        key = f"{CALLER_ORG}/certidoes/consulta-001/cnd_federal_ab.pdf"
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", status="sucesso", arquivo_url=key),
        ])
        rm = AsyncMock()
        override_service(delete_storage_files=rm)
        resp = client.delete(f"{BASE}/consultas/consulta-001")
        assert resp.status_code == 200
        rm.assert_not_awaited()

    def test_consulta_ja_excluida_e_404(self, client, certidoes_db):
        """A second delete on an already-excluded consulta 404s — the same
        shape a hard-deleted one always gave a repeat caller."""
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta(
            excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
        )])
        assert client.delete(f"{BASE}/consultas/consulta-001").status_code == 404

    def test_consulta_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        assert client.delete(f"{BASE}/consultas/nao-existe").status_code == 404

    def test_consulta_de_outra_org_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta(id="alheia", org_id=OTHER_ORG)])
        assert client.delete(f"{BASE}/consultas/alheia").status_code == 404


# ---------------------------------------------------------------------------
# POST /consultas/{id}/restaurar
# ---------------------------------------------------------------------------


class TestRestaurarConsulta:
    def test_restaura_com_sucesso(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta(
            excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
        )], resultados=[
            _resultado(id="r1", excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1"),
        ])
        resp = client.post(f"{BASE}/consultas/consulta-001/restaurar")
        assert resp.status_code == 200
        assert resp.json()["data"]["excluida_em"] is None

        # It is visible again in the list, and its resultado is restored too.
        assert [c["id"] for c in client.get(f"{BASE}/consultas").json()["data"]] == ["consulta-001"]
        resultado = db.table("certidao_resultados").select("*").execute().data[0]
        assert resultado["excluida_em"] is None
        assert resultado["excluida_por"] is None

    def test_consulta_nunca_excluida_e_404(self, client, certidoes_db):
        """Nothing to restore — a mistaken id must 404, not silently no-op."""
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        assert client.post(f"{BASE}/consultas/consulta-001/restaurar").status_code == 404

    def test_consulta_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        assert client.post(f"{BASE}/consultas/nao-existe/restaurar").status_code == 404

    def test_consulta_de_outra_org_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta(
            id="alheia", org_id=OTHER_ORG,
            excluida_em="2026-09-01T10:00:00+00:00", excluida_por="user-1",
        )])
        assert client.post(f"{BASE}/consultas/alheia/restaurar").status_code == 404


# ---------------------------------------------------------------------------
# GET /download
# ---------------------------------------------------------------------------


class TestDownloadCertidao:
    @pytest.mark.asyncio
    async def _noop(self):  # pragma: no cover - placeholder for asyncio marker
        return None

    def test_le_do_bucket_quando_arquivo_url_e_uma_chave(self, client, certidoes_db):
        """End-to-end through the REAL storage seam — the blob is seeded into
        the same `FakeStorageBackend` the route resolves, so this covers the
        key-vs-URL branch in `read_certidao_bytes` rather than assuming it."""
        db, storage = certidoes_db
        key = f"{CALLER_ORG}/certidoes/consulta-001/cnd_federal_ab.pdf"
        _seed(db, resultados=[_resultado(id="r1", arquivo_url=key)])
        asyncio.run(storage.put(bucket=service.BUCKET, key=key, data=b"%PDF-x"))

        resp = client.get(f"{BASE}/download", params={"url": key})
        assert resp.status_code == 200
        assert resp.content == b"%PDF-x"
        assert "attachment" in resp.headers["content-disposition"]

    def test_url_nao_pertencente_a_org_e_404(self, client, certidoes_db, override_service):
        """🔴 The ERP fetched whatever it was handed — an SSRF vector AND a
        cross-org read of any bucket key. The value has to be one this API
        gave THIS caller."""
        db, _ = certidoes_db
        _seed(db, resultados=[
            _resultado(id="alheio", org_id=OTHER_ORG,
                       arquivo_url=f"{OTHER_ORG}/certidoes/c/x.pdf"),
        ])
        read = AsyncMock()
        override_service(read_certidao_bytes=read)
        resp = client.get(
            f"{BASE}/download", params={"url": f"{OTHER_ORG}/certidoes/c/x.pdf"}
        )
        assert resp.status_code == 404
        read.assert_not_awaited()

    def test_host_arbitrario_e_404_nunca_buscado(self, client, certidoes_db, override_service):
        db, _ = certidoes_db
        _seed(db, resultados=[])
        read = AsyncMock()
        override_service(read_certidao_bytes=read)
        resp = client.get(
            f"{BASE}/download", params={"url": "http://169.254.169.254/latest/meta-data/"}
        )
        assert resp.status_code == 404
        read.assert_not_awaited()

    def test_arquivo_ilegivel_e_502(self, client, certidoes_db):
        db, _ = certidoes_db
        key = f"{CALLER_ORG}/certidoes/consulta-001/x.pdf"
        _seed(db, resultados=[_resultado(id="r1", arquivo_url=key)])
        # Nothing seeded at that key — the REAL seam answers None.
        assert client.get(
            f"{BASE}/download", params={"url": key}
        ).status_code == 502

    def test_url_obrigatoria(self, client, certidoes_db):
        assert client.get(f"{BASE}/download").status_code == 422

    def test_nome_de_arquivo_acentuado_nao_derruba_a_resposta(
        self, client, certidoes_db
    ):
        """🔴 REGRESSION. HTTP header values are latin-1 on the wire, so an
        accented `filename=` raised inside Starlette and 500'd the whole
        download — for anyone whose name has an accent. The ERP built the same
        header the same way. See `_content_disposition`."""
        db, storage = certidoes_db
        key = f"{CALLER_ORG}/certidoes/consulta-001/a.pdf"
        _seed(db, resultados=[_resultado(id="r1", arquivo_url=key)])
        _put_blob(storage, key)
        resp = client.get(
            f"{BASE}/download",
            params={"url": key, "filename": "certidão_João.pdf"},
        )
        assert resp.status_code == 200
        disp = resp.headers["content-disposition"]
        assert 'filename="certidao_Joao.pdf"' in disp
        assert "filename*=UTF-8''" in disp


# ---------------------------------------------------------------------------
# GET /consultas/{id}/download-zip
# ---------------------------------------------------------------------------


class TestDownloadZip:
    def test_zipa_os_sucessos(self, client, certidoes_db):
        import io
        import zipfile

        db, storage = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", status="sucesso", arquivo_nome="cnd_federal.pdf",
                       arquivo_url=f"{CALLER_ORG}/certidoes/consulta-001/a.pdf"),
            _resultado(id="r2", status="sucesso", ordem=2, tipo="trf3",
                       nome_display="Certidão TRF3 (Regional)",
                       arquivo_nome="trf3.pdf",
                       arquivo_url=f"{CALLER_ORG}/certidoes/consulta-001/b.pdf"),
        ])
        _put_blob(storage, f"{CALLER_ORG}/certidoes/consulta-001/a.pdf")
        _put_blob(storage, f"{CALLER_ORG}/certidoes/consulta-001/b.pdf")
        resp = client.get(f"{BASE}/consultas/consulta-001/download-zip")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"
        names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
        assert set(names) == {"cnd_federal.pdf", "trf3.pdf"}

    def test_nomes_duplicados_sao_desambiguados(self, client, certidoes_db):
        import io
        import zipfile

        db, storage = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", status="sucesso", arquivo_nome="trf3.pdf",
                       arquivo_url=f"{CALLER_ORG}/certidoes/consulta-001/a.pdf"),
            _resultado(id="r2", status="sucesso", ordem=2, arquivo_nome="trf3.pdf",
                       arquivo_url=f"{CALLER_ORG}/certidoes/consulta-001/b.pdf"),
        ])
        _put_blob(storage, f"{CALLER_ORG}/certidoes/consulta-001/a.pdf")
        _put_blob(storage, f"{CALLER_ORG}/certidoes/consulta-001/b.pdf")
        resp = client.get(f"{BASE}/consultas/consulta-001/download-zip")
        names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
        assert len(names) == 2, "a duplicate entry silently loses one file"

    def test_um_arquivo_indisponivel_nao_derruba_o_zip(self, client, certidoes_db):
        import io
        import zipfile

        db, storage = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", status="sucesso", arquivo_nome="a.pdf",
                       arquivo_url=f"{CALLER_ORG}/certidoes/consulta-001/a.pdf"),
            _resultado(id="r2", status="sucesso", ordem=2, arquivo_nome="b.pdf",
                       arquivo_url=f"{CALLER_ORG}/certidoes/consulta-001/b.pdf"),
        ])
        # Only ONE of the two blobs exists — the real seam answers None for the
        # other, which is exactly the production shape (a file we failed to
        # persist, or one deleted out from under us).
        _put_blob(storage, f"{CALLER_ORG}/certidoes/consulta-001/a.pdf")
        resp = client.get(f"{BASE}/consultas/consulta-001/download-zip")
        assert resp.status_code == 200
        assert zipfile.ZipFile(io.BytesIO(resp.content)).namelist() == ["a.pdf"]

    def test_sem_certidoes_disponiveis_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", status="erro"),
        ])
        resp = client.get(f"{BASE}/consultas/consulta-001/download-zip")
        assert resp.status_code == 404
        assert "Nenhuma certidão" in _msg(resp)

    def test_nenhum_arquivo_baixavel_e_502(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", status="sucesso", arquivo_nome="a.pdf",
                       arquivo_url=f"{CALLER_ORG}/certidoes/consulta-001/a.pdf"),
        ])
        # No blob seeded at all — every read answers None.
        assert client.get(
            f"{BASE}/consultas/consulta-001/download-zip"
        ).status_code == 502

    def test_consulta_de_outra_org_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta(id="alheia", org_id=OTHER_ORG)])
        assert client.get(
            f"{BASE}/consultas/alheia/download-zip"
        ).status_code == 404

    def test_nome_acentuado_no_zip_nao_derruba_a_resposta(
        self, client, certidoes_db
    ):
        """🔴 REGRESSION — same defect as `/download`, reached through the
        consulta's own `nome` ("João da Silva") rather than a query param."""
        db, storage = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", status="sucesso", arquivo_nome="a.pdf",
                       arquivo_url=f"{CALLER_ORG}/certidoes/consulta-001/a.pdf"),
        ])
        _put_blob(storage, f"{CALLER_ORG}/certidoes/consulta-001/a.pdf")
        resp = client.get(f"{BASE}/consultas/consulta-001/download-zip")
        assert resp.status_code == 200
        disp = resp.headers["content-disposition"]
        assert 'filename="certidoes_Joao_da_Silva_12345678901.zip"' in disp
        assert "filename*=UTF-8''" in disp


# ---------------------------------------------------------------------------
# POST /resultados/{id}/upload
# ---------------------------------------------------------------------------


class TestUploadManual:
    def _file(self, content=b"%PDF-1.4 scan", ctype="application/pdf"):
        return {"file": ("certidao.pdf", content, ctype)}

    def test_upload_roda_o_mesmo_pipeline_do_automatico(
        self, client, certidoes_db, override_service
    ):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r1", resultado_origem="api", confirmado_por="user-1"),
        ])
        proc = AsyncMock(
            return_value={"status": "processando", "arquivo_nome": "cnd_federal.pdf"}
        )
        extrair = AsyncMock(return_value={"status": "sucesso"})
        override_service(process_manual_upload=proc, process_manual_extraction=extrair)
        resp = client.post(f"{BASE}/resultados/r1/upload", files=self._file())
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "processando"
        # The route hands the storage leg the CALLER's org, the resultado's
        # tipo and the PDF bytes — the contract the automated flow also
        # relies on. The extraction leg (scheduled via BackgroundTasks, not
        # awaited inline — the point of the split) gets the same PDF bytes
        # plus the resultado's provenance, so a human's prior confirmation is
        # still respected by the background job.
        kw = proc.await_args.kwargs
        assert kw["org_id"] == CALLER_ORG
        assert kw["tipo"] == "cnd_federal"
        assert kw["resultado_id"] == "r1"
        assert kw["pdf_bytes"] == b"%PDF-1.4 scan"

        extrair.assert_awaited_once()
        ekw = extrair.await_args.kwargs
        assert ekw["resultado_id"] == "r1"
        assert ekw["consulta_id"] == "consulta-001"
        assert ekw["pdf_bytes"] == b"%PDF-1.4 scan"
        assert ekw["resultado_origem_atual"] == "api"
        assert ekw["confirmado_por_atual"] == "user-1"

    def test_nao_pdf_e_422(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[_resultado(id="r1")])
        resp = client.post(
            f"{BASE}/resultados/r1/upload",
            files=self._file(b"nao e pdf", "text/plain"),
        )
        assert resp.status_code == 422
        assert "PDF" in _msg(resp)

    def test_arquivo_vazio_e_422(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[_resultado(id="r1")])
        resp = client.post(f"{BASE}/resultados/r1/upload", files=self._file(b""))
        assert resp.status_code == 422

    def test_resultado_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        assert client.post(
            f"{BASE}/resultados/sumiu/upload", files=self._file()
        ).status_code == 404

    def test_resultado_de_outra_org_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="alheio", org_id=OTHER_ORG),
        ])
        assert client.post(
            f"{BASE}/resultados/alheio/upload", files=self._file()
        ).status_code == 404


# ---------------------------------------------------------------------------
# GET /fila-tjsp
# ---------------------------------------------------------------------------


class TestFilaTjsp:
    def test_fila_vazia_sem_cooldown(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        data = client.get(f"{BASE}/fila-tjsp").json()["data"]
        assert data["items"] == []
        assert data["total_na_fila"] == 0
        assert data["cooldown"] == {"ativo": False}

    def test_itens_na_fila_com_posicao_e_nome(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r-tjsp", tipo="tjsp", ordem=7, status="na_fila"),
        ])
        data = client.get(f"{BASE}/fila-tjsp").json()["data"]
        assert data["total_na_fila"] == 1
        item = data["items"][0]
        assert item["posicao"] == 1
        assert item["nome"] == "João da Silva"
        assert item["documento"] == "12345678901"

    def test_cooldown_ativo_expoe_segundos_restantes(self, client, certidoes_db):
        db, _ = certidoes_db
        recent = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="r-tjsp", tipo="tjsp", ordem=7, status="sucesso",
                       api_requested_at=recent),
        ])
        cooldown = client.get(f"{BASE}/fila-tjsp").json()["data"]["cooldown"]
        assert cooldown["ativo"] is True
        assert cooldown["segundos_restantes"] > 0

    def test_fila_de_outra_org_nao_aparece(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="alheio", tipo="tjsp", ordem=7, status="na_fila",
                       org_id=OTHER_ORG),
        ])
        assert client.get(f"{BASE}/fila-tjsp").json()["data"]["total_na_fila"] == 0


# ---------------------------------------------------------------------------
# Contract-automation slice (migration 107)
# ---------------------------------------------------------------------------


def _parte(**overrides) -> dict:
    row = {
        "id": PARTE_ID,
        "org_id": CALLER_ORG,
        "atendimento_id": "atendimento-001",
        "cliente_id": "cliente-001",
        "papel": "conjuge",
        "lado": "comprador",
        "ordem": 0,
        "observacao": None,
        "created_at": "2026-03-05T10:00:00+00:00",
        "created_by": "test-user-123",
        "updated_at": None,
    }
    row.update(overrides)
    return row


class TestVincularParte:
    def test_vincula_e_resolve_cliente_id_da_parte(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        db.set_table_data("atendimento_partes", [_parte()])
        resp = client.post(
            f"{BASE}/consultas/consulta-001/vincular-parte",
            json={"atendimento_parte_id": PARTE_ID},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["atendimento_parte_id"] == PARTE_ID
        assert data["cliente_id"] == "cliente-001"

    def test_faz_fan_out_dos_tres_tipos_manuais(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        db.set_table_data("atendimento_partes", [_parte()])
        client.post(
            f"{BASE}/consultas/consulta-001/vincular-parte",
            json={"atendimento_parte_id": PARTE_ID},
        )
        tipos = {
            r["tipo"]
            for r in db.table("certidao_resultados").select("*").execute().data
        }
        assert tipos == {"serasa", "tjsp_esaj", "tjsp_eproc"}

    def test_fan_out_e_idempotente(self, client, certidoes_db):
        """Linking the same parte twice must not duplicate the three manual
        placeholders — `vincular_parte` checks existing tipos first."""
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        db.set_table_data("atendimento_partes", [_parte()])
        client.post(
            f"{BASE}/consultas/consulta-001/vincular-parte",
            json={"atendimento_parte_id": PARTE_ID},
        )
        client.post(
            f"{BASE}/consultas/consulta-001/vincular-parte",
            json={"atendimento_parte_id": PARTE_ID},
        )
        rows = db.table("certidao_resultados").select("*").execute().data
        assert len(rows) == 3

    def test_nao_duplica_tipos_ja_existentes(self, client, certidoes_db):
        """A consulta already carrying the ten automated resultados (the
        normal `criar_consulta` fan-out) must not get a second `serasa`
        placeholder if one was already added by hand."""
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()], resultados=[
            _resultado(id="ja-existe", tipo="serasa", ordem=11),
        ])
        db.set_table_data("atendimento_partes", [_parte()])
        client.post(
            f"{BASE}/consultas/consulta-001/vincular-parte",
            json={"atendimento_parte_id": PARTE_ID},
        )
        serasas = [
            r for r in db.table("certidao_resultados").select("*").execute().data
            if r["tipo"] == "serasa"
        ]
        assert len(serasas) == 1

    def test_parte_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        db.set_table_data("atendimento_partes", [])
        resp = client.post(
            f"{BASE}/consultas/consulta-001/vincular-parte",
            json={"atendimento_parte_id": "00000000-0000-4000-8000-000000000000"},
        )
        assert resp.status_code == 404

    def test_parte_de_outra_org_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        db.set_table_data("atendimento_partes", [_parte(org_id=OTHER_ORG)])
        resp = client.post(
            f"{BASE}/consultas/consulta-001/vincular-parte",
            json={"atendimento_parte_id": PARTE_ID},
        )
        assert resp.status_code == 404

    def test_consulta_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        db.set_table_data("atendimento_partes", [_parte()])
        resp = client.post(
            f"{BASE}/consultas/nao-existe/vincular-parte",
            json={"atendimento_parte_id": PARTE_ID},
        )
        assert resp.status_code == 404

    def test_corpo_invalido_e_422(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        resp = client.post(
            f"{BASE}/consultas/consulta-001/vincular-parte", json={},
        )
        assert resp.status_code == 422


class TestListarResultadosPorParte:
    def test_lista_certidoes_da_parte(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(
            db,
            consultas=[_consulta(atendimento_parte_id=PARTE_ID)],
            resultados=[_resultado(id="r1")],
        )
        data = client.get(f"{BASE}/partes/{PARTE_ID}/resultados").json()["data"]
        assert [r["id"] for r in data] == ["r1"]

    def test_parte_sem_consultas_retorna_lista_vazia(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        assert client.get(f"{BASE}/partes/{PARTE_ID}/resultados").json()["data"] == []


class TestConfirmarOuCorrigirResultado:
    def test_corrige_campos_e_estampa_manual(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado()])
        resp = client.patch(
            f"{BASE}/resultados/resultado-001",
            json={"resultado": "positiva", "numero": "X-1"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["resultado"] == "positiva"
        assert data["numero"] == "X-1"
        assert data["resultado_origem"] == "manual"
        assert data["confirmado_por"] is not None
        assert data["confirmado_em"] is not None

    def test_corpo_vazio_ainda_confirma(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado(resultado="negativa", resultado_origem="api")])
        resp = client.patch(f"{BASE}/resultados/resultado-001", json={})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["resultado"] == "negativa"
        assert data["resultado_origem"] == "manual"

    def test_resultado_invalido_e_422(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado()])
        resp = client.patch(
            f"{BASE}/resultados/resultado-001",
            json={"resultado": "nao_e_um_valor_valido"},
        )
        assert resp.status_code == 422

    def test_campo_desconhecido_e_recusado(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado()])
        resp = client.patch(
            f"{BASE}/resultados/resultado-001", json={"campo_fantasma": "x"},
        )
        assert resp.status_code == 422

    def test_resultado_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        assert client.patch(
            f"{BASE}/resultados/sumiu", json={},
        ).status_code == 404

    def test_resultado_de_outra_org_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado(id="alheio", org_id=OTHER_ORG)])
        assert client.patch(
            f"{BASE}/resultados/alheio", json={},
        ).status_code == 404


# ---------------------------------------------------------------------------
# The titular's own certidões (migration 116) — vincular_parte's sibling for
# the one party it cannot reach.
# ---------------------------------------------------------------------------

CLIENTE_ID = "44444444-4444-4444-8444-444444444444"


def _cliente(**overrides) -> dict:
    row = {"id": CLIENTE_ID, "org_id": CALLER_ORG, "nome": "Titular"}
    row.update(overrides)
    return row


class TestVincularCliente:
    def test_vincula_o_titular_a_consulta(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        db.set_table_data("clientes", [_cliente()])
        resp = client.post(
            f"{BASE}/consultas/consulta-001/vincular-cliente",
            json={"cliente_id": CLIENTE_ID},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["cliente_id"] == CLIENTE_ID

    def test_faz_fan_out_dos_tres_tipos_manuais(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        db.set_table_data("clientes", [_cliente()])
        client.post(
            f"{BASE}/consultas/consulta-001/vincular-cliente",
            json={"cliente_id": CLIENTE_ID},
        )
        tipos = {
            r["tipo"]
            for r in db.table("certidao_resultados").select("*").execute().data
        }
        assert tipos == {"serasa", "tjsp_esaj", "tjsp_eproc"}

    def test_fan_out_e_idempotente(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        db.set_table_data("clientes", [_cliente()])
        client.post(
            f"{BASE}/consultas/consulta-001/vincular-cliente",
            json={"cliente_id": CLIENTE_ID},
        )
        client.post(
            f"{BASE}/consultas/consulta-001/vincular-cliente",
            json={"cliente_id": CLIENTE_ID},
        )
        rows = db.table("certidao_resultados").select("*").execute().data
        assert len(rows) == 3

    def test_cliente_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        db.set_table_data("clientes", [])
        resp = client.post(
            f"{BASE}/consultas/consulta-001/vincular-cliente",
            json={"cliente_id": CLIENTE_ID},
        )
        assert resp.status_code == 404

    def test_cliente_de_outra_org_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        db.set_table_data("clientes", [_cliente(org_id=OTHER_ORG)])
        resp = client.post(
            f"{BASE}/consultas/consulta-001/vincular-cliente",
            json={"cliente_id": CLIENTE_ID},
        )
        assert resp.status_code == 404

    def test_consulta_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        db.set_table_data("clientes", [_cliente()])
        resp = client.post(
            f"{BASE}/consultas/nao-existe/vincular-cliente",
            json={"cliente_id": CLIENTE_ID},
        )
        assert resp.status_code == 404

    def test_corpo_invalido_e_422(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        resp = client.post(
            f"{BASE}/consultas/consulta-001/vincular-cliente", json={},
        )
        assert resp.status_code == 422


class TestListarResultadosPorCliente:
    def test_lista_certidoes_do_cliente(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(
            db,
            consultas=[_consulta(cliente_id=CLIENTE_ID)],
            resultados=[_resultado(id="r1")],
        )
        data = client.get(f"{BASE}/clientes/{CLIENTE_ID}/resultados").json()["data"]
        assert [r["id"] for r in data] == ["r1"]

    def test_cliente_sem_consultas_retorna_lista_vazia(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        assert client.get(
            f"{BASE}/clientes/{CLIENTE_ID}/resultados"
        ).json()["data"] == []


class TestAtualizarSituacaoCadastralRoute:
    def test_grava_e_estampa_origem_manual(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        resp = client.patch(
            f"{BASE}/consultas/consulta-001/situacao-cadastral",
            json={"situacao_cadastral": "baixada", "data_situacao": "2026-01-01"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["situacao_cadastral"] == "baixada"
        assert data["situacao_origem"] == "manual"

    def test_situacao_invalida_e_422(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        resp = client.patch(
            f"{BASE}/consultas/consulta-001/situacao-cadastral",
            json={"situacao_cadastral": "nao_e_um_valor_valido"},
        )
        assert resp.status_code == 422

    def test_corpo_vazio_e_422(self, client, certidoes_db):
        """Unlike `confirmar_ou_corrigir_resultado`, there is no automated
        writer to lock out here — an empty body has nothing to confirm."""
        db, _ = certidoes_db
        _seed(db, consultas=[_consulta()])
        resp = client.patch(
            f"{BASE}/consultas/consulta-001/situacao-cadastral", json={},
        )
        assert resp.status_code == 422

    def test_consulta_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        resp = client.patch(
            f"{BASE}/consultas/nao-existe/situacao-cadastral",
            json={"situacao_cadastral": "ativa"},
        )
        assert resp.status_code == 404


class TestObterUrlResultado:
    def test_chave_de_storage_e_assinada(self, client, certidoes_db):
        db, storage = certidoes_db
        key = f"{CALLER_ORG}/certidoes/consulta-001/a.pdf"
        _seed(db, resultados=[_resultado(id="r1", arquivo_url=key)])
        resp = client.get(f"{BASE}/resultados/r1/url")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["url"].startswith("fake://storage/")
        assert data["expires_at"] is not None

    def test_loga_o_acesso_lgpd(self, client, certidoes_db):
        db, _ = certidoes_db
        key = f"{CALLER_ORG}/certidoes/consulta-001/a.pdf"
        _seed(db, resultados=[_resultado(id="r1", arquivo_url=key)])
        db.set_table_data("certidao_resultado_acessos", [])
        client.get(f"{BASE}/resultados/r1/url?intent=download")
        log = db.table("certidao_resultado_acessos").select("*").execute().data
        assert len(log) == 1
        assert log[0]["acao"] == "download"
        assert log[0]["documento_id"] == "r1"

    def test_url_externa_e_devolvida_sem_assinar(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[
            _resultado(id="r1", arquivo_url="https://infosimples.com/x.pdf"),
        ])
        data = client.get(f"{BASE}/resultados/r1/url").json()["data"]
        assert data["url"] == "https://infosimples.com/x.pdf"

    def test_sem_arquivo_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado(id="r1", arquivo_url=None)])
        assert client.get(f"{BASE}/resultados/r1/url").status_code == 404

    def test_resultado_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        assert client.get(f"{BASE}/resultados/sumiu/url").status_code == 404

    def test_intent_invalido_e_422(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado(id="r1")])
        assert client.get(
            f"{BASE}/resultados/r1/url?intent=apagar"
        ).status_code == 422


# ---------------------------------------------------------------------------
# GET /resultados/{id}/transcricao · GET /resultados/{id}/transcricao/pdf
# migration 113
# ---------------------------------------------------------------------------


class TestObterTranscricao:
    def test_com_transcricao_devolve_texto_html_e_formatacao(
        self, client, certidoes_db
    ):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado(
            id="r1",
            texto_extraido="Bold word here",
            formatacao=[{"start": 0, "end": 4, "bold": True, "underline": False}],
        )])
        resp = client.get(f"{BASE}/resultados/r1/transcricao")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["texto"] == "Bold word here"
        assert "<b>Bold</b>" in data["texto_html"]
        assert data["formatacao"] == [
            {"start": 0, "end": 4, "bold": True, "underline": False}
        ]

    def test_loga_o_acesso_lgpd(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado(id="r1", texto_extraido="texto")])
        db.set_table_data("certidao_resultado_acessos", [])
        client.get(f"{BASE}/resultados/r1/transcricao")
        log = db.table("certidao_resultado_acessos").select("*").execute().data
        assert len(log) == 1
        assert log[0]["acao"] == "view"
        assert log[0]["documento_id"] == "r1"

    def test_sem_transcricao_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado(id="r1", texto_extraido=None)])
        resp = client.get(f"{BASE}/resultados/r1/transcricao")
        assert resp.status_code == 404
        assert _msg(resp) == "Transcrição indisponível para esta certidão"

    def test_resultado_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        resp = client.get(f"{BASE}/resultados/sumiu/transcricao")
        assert resp.status_code == 404
        assert _msg(resp) == "Resultado não encontrado"

    def test_resultado_de_outra_org_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[
            _resultado(id="alheio", org_id=OTHER_ORG, texto_extraido="x"),
        ])
        assert client.get(f"{BASE}/resultados/alheio/transcricao").status_code == 404


class TestObterTranscricaoPdf:
    def test_pdf_com_titulo_e_texto(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado(
            id="r1", tipo="cnd_federal", nome_display="CND Federal",
            texto_extraido="Bold word here",
            formatacao=[{"start": 0, "end": 4, "bold": True, "underline": False}],
        )])
        resp = client.get(f"{BASE}/resultados/r1/transcricao/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:5] == b"%PDF-"
        assert (
            'filename="cnd_federal_transcricao.pdf"'
            in resp.headers["content-disposition"]
        )

        import fitz

        doc = fitz.open(stream=resp.content, filetype="pdf")
        texto = "".join(page.get_text() for page in doc)
        assert "Transcrição — CND Federal" in texto
        assert "Bold word here" in texto

    def test_sem_transcricao_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db, resultados=[_resultado(id="r1", texto_extraido=None)])
        resp = client.get(f"{BASE}/resultados/r1/transcricao/pdf")
        assert resp.status_code == 404

    def test_resultado_inexistente_e_404(self, client, certidoes_db):
        db, _ = certidoes_db
        _seed(db)
        resp = client.get(f"{BASE}/resultados/sumiu/transcricao/pdf")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth boundary
# ---------------------------------------------------------------------------


class TestAuthBoundary:
    """Every route refuses an unauthenticated caller with a strict 401.

    🔴 `== 401`, never `in (401, 404, 422)`. The permissive form passes when the
    route does not exist at all, and when validation runs BEFORE auth — both of
    which are the false-green this rule exists to catch.
    → KB § PATTERNS/compliance/auth-boundary-false-green.md
    """

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", f"{BASE}/tipos"),
            ("get", f"{BASE}/consultas"),
            ("post", f"{BASE}/consultas"),
            ("post", f"{BASE}/consultas/manual"),
            ("get", f"{BASE}/consultas/consulta-001"),
            ("post", f"{BASE}/consultas/consulta-001/reprocessar"),
            ("post", f"{BASE}/consultas/consulta-001/cancelar"),
            ("delete", f"{BASE}/consultas/consulta-001"),
            ("post", f"{BASE}/consultas/consulta-001/restaurar"),
            ("get", f"{BASE}/download?url=x&filename=y"),
            ("get", f"{BASE}/consultas/consulta-001/download-zip"),
            ("post", f"{BASE}/resultados/r1/upload"),
            ("get", f"{BASE}/fila-tjsp"),
            ("get", f"{BASE}/resultados/r1/transcricao"),
            ("get", f"{BASE}/resultados/r1/transcricao/pdf"),
        ],
    )
    def test_sem_token_e_401(self, anon_client, method, path):
        resp = getattr(anon_client, method)(path)
        assert resp.status_code == 401
