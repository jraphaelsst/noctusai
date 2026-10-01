"""Certidões — P0c additions (`sw-drive-extraction-P0c-contract.md` §C5/§D5).

WHAT THESE PIN
--------------
- `registrar_serasa_de_crednet`: fills an EMPTY `serasa` resultado; a prior
  Crednet-derived reading (`resultado_origem='ia'` + `fonte_cliente_
  documento_id`) is superseded only by a NEWER one; a MANUAL or CONFIRMED
  row is never touched;
- `aplicar_crednet_pendente`: the deferred half — a consulta linked AFTER a
  Crednet upload already exists still gets filled;
- `certidoes_por_empresa`: the same shape `certidoes_por_cliente` returns,
  filtered by `empresa_id`;
- `delete_storage_files`' purge-prefix safety fix: a `certidao_resultados.
  arquivo_url` pointing at a DIFFERENT surface's storage key (a Crednet
  upload's `cliente_documentos.storage_path`) is never deleted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import pytest
from noctusai_lib.testing import MockSupabaseClient

from app.modules.certidoes import service

ORG = "test-org-certidoes-p0c"

CONSULTAS = "certidao_consultas"
RESULTADOS = "certidao_resultados"


def _client(**tables) -> MockSupabaseClient:
    client = MockSupabaseClient(schema="social_wiring")
    for name, rows in tables.items():
        client.set_table_data(name, rows)
    return client


def _consulta(**overrides) -> dict:
    row = {
        "id": str(uuid4()), "org_id": ORG, "tipo_documento": "cpf",
        "documento": "41295423898", "nome": "Fulana de Teste",
        "data_nascimento": None, "genero": None, "rg": None,
        "nome_mae": None, "nome_pai": None,
        "cliente_id": None, "atendimento_parte_id": None, "empresa_id": None,
        "created_by": "user-1", "status": "pendente", "origem": "manual",
        "total_certidoes": 13, "concluidas": 0,
        "situacao_cadastral": None, "data_situacao": None, "situacao_origem": None,
        "excluida_em": None, "excluida_por": None,
        "created_at": "2026-03-05T10:00:00+00:00", "updated_at": "2026-03-05T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def _resultado(**overrides) -> dict:
    row = {
        "id": str(uuid4()), "consulta_id": "consulta-001", "org_id": ORG,
        "tipo": "serasa", "nome_display": "Serasa", "ordem": 11,
        "status": "pendente", "analise_ia": None,
        "arquivo_url": None, "arquivo_nome": None, "api_response": None,
        "erro_mensagem": None, "api_requested_at": None,
        "numero": None, "emitida_em": None, "validade_ate": None,
        "resultado": None, "resultado_origem": None,
        "fonte_cliente_documento_id": None,
        "confirmado_por": None, "confirmado_em": None,
        "estrutura_erro": None, "estrutura_tentativas": 0,
        "excluida_em": None, "excluida_por": None,
        "created_at": "2026-03-05T10:00:00+00:00", "updated_at": "2026-03-05T10:00:00+00:00",
    }
    row.update(overrides)
    return row


# The Crednet age gate (`certidao_max_dias`) is measured against the REAL
# clock, so fixtures are relative to today — a hard-coded date silently rots
# past the window.
_RECENTE = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0) - timedelta(days=5)
_RECENTE_ISO = _RECENTE.date().isoformat()
_ANTIGA = _RECENTE - timedelta(days=60)


@dataclass(frozen=True)
class _Leitura:
    cpf: Optional[str] = "41295423898"
    protocolo: Optional[str] = "9999999"
    consulta_em: Optional[datetime] = _RECENTE
    _constam: Optional[bool] = False

    def ocorrencias_constam(self) -> Optional[bool]:
        return self._constam


def _doc(**overrides) -> dict:
    row = {"id": str(uuid4()), "storage_path": f"{ORG}/clientes/cliente-1/doc-1"}
    row.update(overrides)
    return row


class TestRegistrarSerasaDeCrednet:
    def test_fills_when_targeted_by_cliente_id(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id=cliente_id)
        resultado = _resultado(consulta_id=consulta["id"])
        client = _client(**{CONSULTAS: [consulta], RESULTADOS: [resultado]})
        doc = _doc()

        atualizados = service.registrar_serasa_de_crednet(client, ORG, cliente_id, doc, _Leitura())

        assert atualizados == 1
        row = client.table(RESULTADOS).select("*").eq("id", resultado["id"]).execute().data[0]
        assert row["status"] == "sucesso"
        assert row["arquivo_url"] == doc["storage_path"]
        assert row["arquivo_nome"] == "serasa_crednet.pdf"
        assert row["resultado"] == "negativa"
        assert row["resultado_origem"] == "ia"
        assert row["fonte_cliente_documento_id"] == doc["id"]
        assert row["numero"] == "9999999"
        assert row["emitida_em"] == _RECENTE_ISO

    def test_positiva_when_ocorrencias_constam(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id=cliente_id)
        resultado = _resultado(consulta_id=consulta["id"])
        client = _client(**{CONSULTAS: [consulta], RESULTADOS: [resultado]})

        service.registrar_serasa_de_crednet(
            client, ORG, cliente_id, _doc(), _Leitura(_constam=True)
        )
        row = client.table(RESULTADOS).select("*").eq("id", resultado["id"]).execute().data[0]
        assert row["resultado"] == "positiva"

    def test_null_when_unreadable(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id=cliente_id)
        resultado = _resultado(consulta_id=consulta["id"])
        client = _client(**{CONSULTAS: [consulta], RESULTADOS: [resultado]})

        service.registrar_serasa_de_crednet(
            client, ORG, cliente_id, _doc(), _Leitura(_constam=None)
        )
        row = client.table(RESULTADOS).select("*").eq("id", resultado["id"]).execute().data[0]
        assert row["resultado"] is None

    def test_never_overwrites_a_manual_row(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id=cliente_id)
        resultado = _resultado(
            consulta_id=consulta["id"], status="sucesso", resultado="positiva",
            resultado_origem="manual",
        )
        client = _client(**{CONSULTAS: [consulta], RESULTADOS: [resultado]})

        atualizados = service.registrar_serasa_de_crednet(client, ORG, cliente_id, _doc(), _Leitura())

        assert atualizados == 0
        row = client.table(RESULTADOS).select("*").eq("id", resultado["id"]).execute().data[0]
        assert row["resultado"] == "positiva"
        assert row["resultado_origem"] == "manual"

    def test_never_overwrites_a_confirmed_row(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id=cliente_id)
        resultado = _resultado(
            consulta_id=consulta["id"], status="sucesso", resultado="negativa",
            resultado_origem="ia", fonte_cliente_documento_id=str(uuid4()),
            confirmado_por="user-1", confirmado_em="2026-09-01T00:00:00+00:00",
        )
        client = _client(**{CONSULTAS: [consulta], RESULTADOS: [resultado]})

        atualizados = service.registrar_serasa_de_crednet(client, ORG, cliente_id, _doc(), _Leitura())

        assert atualizados == 0

    def test_a_newer_crednet_supersedes_an_older_one(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id=cliente_id)
        old_doc_id = str(uuid4())
        resultado = _resultado(
            consulta_id=consulta["id"], status="sucesso", resultado="negativa",
            resultado_origem="ia", fonte_cliente_documento_id=old_doc_id,
            emitida_em=_ANTIGA.date().isoformat(),
        )
        client = _client(**{CONSULTAS: [consulta], RESULTADOS: [resultado]})
        novo_doc = _doc()

        atualizados = service.registrar_serasa_de_crednet(
            client, ORG, cliente_id, novo_doc, _Leitura(consulta_em=_RECENTE)
        )

        assert atualizados == 1
        row = client.table(RESULTADOS).select("*").eq("id", resultado["id"]).execute().data[0]
        assert row["fonte_cliente_documento_id"] == novo_doc["id"]
        assert row["emitida_em"] == _RECENTE_ISO

    def test_an_older_crednet_never_supersedes_a_newer_one(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id=cliente_id)
        newer_doc_id = str(uuid4())
        resultado = _resultado(
            consulta_id=consulta["id"], status="sucesso", resultado="negativa",
            resultado_origem="ia", fonte_cliente_documento_id=newer_doc_id,
            emitida_em=(_RECENTE + timedelta(days=2)).date().isoformat(),
        )
        client = _client(**{CONSULTAS: [consulta], RESULTADOS: [resultado]})

        atualizados = service.registrar_serasa_de_crednet(
            client, ORG, cliente_id, _doc(), _Leitura(consulta_em=_RECENTE - timedelta(days=3))
        )

        assert atualizados == 0

    def test_targets_only_matching_cpf_ignoring_punctuation(self):
        cliente_id = str(uuid4())
        matching = _consulta(cliente_id=cliente_id, documento="412.954.238-98")
        other = _consulta(cliente_id=cliente_id, documento="529.982.247-25")
        r1 = _resultado(consulta_id=matching["id"])
        r2 = _resultado(consulta_id=other["id"])
        client = _client(**{CONSULTAS: [matching, other], RESULTADOS: [r1, r2]})

        atualizados = service.registrar_serasa_de_crednet(client, ORG, cliente_id, _doc(), _Leitura())

        assert atualizados == 1
        assert (
            client.table(RESULTADOS).select("*").eq("id", r2["id"]).execute().data[0]["status"]
            == "pendente"
        )

    def test_no_matching_consulta_defers_returns_zero(self):
        client = _client(**{CONSULTAS: [], RESULTADOS: []})
        assert service.registrar_serasa_de_crednet(client, ORG, str(uuid4()), _doc(), _Leitura()) == 0


class TestAplicarCrednetPendente:
    def test_fills_retroactively_from_the_most_recent_matching_reading(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id=cliente_id)
        resultado = _resultado(consulta_id=consulta["id"])
        crednet_doc = {
            "id": str(uuid4()), "storage_path": f"{ORG}/clientes/{cliente_id}/crednet-doc",
            "extracao_crednet": {
                "cpf": "412.954.238-98", "protocolo": "1111111",
                "consulta_em": _RECENTE.isoformat(), "ocorrencias_constam": False,
            },
        }
        client = _client(**{
            CONSULTAS: [consulta], RESULTADOS: [resultado],
            "cliente_documentos": [
                {
                    **crednet_doc,
                    "org_id": ORG, "cliente_id": cliente_id,
                    "tipo_documento": "serasa_crednet", "extracao_status": "ok",
                    "deleted_at": None,
                }
            ],
        })

        aplicado = service.aplicar_crednet_pendente(client, ORG, consulta)

        assert aplicado is True
        row = client.table(RESULTADOS).select("*").eq("id", resultado["id"]).execute().data[0]
        assert row["status"] == "sucesso"
        assert row["numero"] == "1111111"

    def test_no_crednet_on_file_returns_false(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id=cliente_id)
        resultado = _resultado(consulta_id=consulta["id"])
        client = _client(
            **{CONSULTAS: [consulta], RESULTADOS: [resultado], "cliente_documentos": []}
        )

        assert service.aplicar_crednet_pendente(client, ORG, consulta) is False

    def test_cnpj_consulta_is_never_a_target(self):
        consulta = _consulta(tipo_documento="cnpj", cliente_id=str(uuid4()))
        client = _client(**{CONSULTAS: [consulta], RESULTADOS: [], "cliente_documentos": []})
        assert service.aplicar_crednet_pendente(client, ORG, consulta) is False


class TestCertidoesPorEmpresa:
    def test_filters_by_empresa_id_only(self):
        empresa_id = str(uuid4())
        outra_empresa_id = str(uuid4())
        c1 = _consulta(tipo_documento="cnpj", empresa_id=empresa_id, documento="11222333000181")
        c2 = _consulta(tipo_documento="cnpj", empresa_id=outra_empresa_id, documento="12345678000195")
        r1 = _resultado(consulta_id=c1["id"], tipo="cnd_federal")
        r2 = _resultado(consulta_id=c2["id"], tipo="cnd_federal")
        client = _client(**{CONSULTAS: [c1, c2], RESULTADOS: [r1, r2]})

        resultados = service.certidoes_por_empresa(client, ORG, empresa_id)

        assert len(resultados) == 1
        assert resultados[0]["id"] == r1["id"]

    def test_excludes_soft_deleted_consultas(self):
        empresa_id = str(uuid4())
        consulta = _consulta(
            tipo_documento="cnpj", empresa_id=empresa_id, excluida_em="2026-09-01T00:00:00+00:00"
        )
        resultado = _resultado(consulta_id=consulta["id"])
        client = _client(**{CONSULTAS: [consulta], RESULTADOS: [resultado]})

        assert service.certidoes_por_empresa(client, ORG, empresa_id) == []


class TestPurgePrefixSafety:
    """The 'required safety fix' (contract §C5): `delete_storage_files`
    must never delete a foreign surface's storage key — the Crednet -> serasa
    9 provenance means a `certidao_resultados.arquivo_url` can legitimately
    hold a `cliente_documentos.storage_path` verbatim."""

    @pytest.mark.asyncio
    async def test_a_foreign_crednet_key_is_never_deleted(self):
        from noctusai_lib.integrations.storage import FakeStorageBackend

        storage = FakeStorageBackend()
        cliente_key = f"{ORG}/clientes/cliente-1/crednet-doc.pdf"
        certidoes_key = f"{ORG}/certidoes/consulta-1/cnd_federal_abcd1234.pdf"
        await storage.put(
            bucket=service.BUCKET, key=cliente_key, data=b"x", content_type="application/pdf",
        )
        await storage.put(
            bucket=service.BUCKET, key=certidoes_key, data=b"x", content_type="application/pdf",
        )
        resultados = [
            {"arquivo_url": cliente_key},  # foreign — a Crednet upload
            {"arquivo_url": certidoes_key},  # this module's own key
        ]

        deleted = await service.delete_storage_files(resultados, storage)

        assert deleted == 1
        assert await storage.get(bucket=service.BUCKET, key=cliente_key) is not None
        assert await storage.get(bucket=service.BUCKET, key=certidoes_key) is None

    def test_is_certidoes_storage_key_matches_only_its_own_prefix(self):
        assert service._is_certidoes_storage_key(f"{ORG}/certidoes/x/y.pdf") is True
        assert service._is_certidoes_storage_key(f"{ORG}/clientes/x/y.pdf") is False
        assert service._is_certidoes_storage_key(f"{ORG}/empresas/x/y.pdf") is False


class TestCrednetMaisAntigaQueAJanelaDoContrato:
    """A Crednet older than `politica.certidao_max_dias` would land a cell the
    contract gate rejects anyway — it must leave the cell `pendente` instead."""

    def _alvo(self):
        cliente_id = str(uuid4())
        consulta = _consulta(cliente_id=cliente_id)
        resultado = _resultado(consulta_id=consulta["id"])
        return cliente_id, consulta, resultado, _client(**{CONSULTAS: [consulta], RESULTADOS: [resultado]})

    def _linha(self, client, resultado):
        return client.table(RESULTADOS).select("*").eq("id", resultado["id"]).execute().data[0]

    def test_registrar_ignora_crednet_velha(self):
        cliente_id, consulta, resultado, client = self._alvo()
        n = service.registrar_serasa_de_crednet(
            client, ORG, cliente_id, _doc(), _Leitura(consulta_em=_ANTIGA),
        )
        assert n == 0
        row = self._linha(client, resultado)
        assert row["status"] == "pendente" and row["numero"] is None

    def test_exatamente_no_limite_ja_e_velha(self):
        from app.modules.card_hub.contrato_gerador.politica import POLITICA_PADRAO

        limite = POLITICA_PADRAO.certidao_max_dias
        agora = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        cliente_id, consulta, resultado, client = self._alvo()
        assert service.registrar_serasa_de_crednet(
            client, ORG, cliente_id, _doc(), _Leitura(consulta_em=agora - timedelta(days=limite)),
        ) == 0
        assert service.registrar_serasa_de_crednet(
            client, ORG, cliente_id, _doc(),
            _Leitura(consulta_em=agora - timedelta(days=limite - 1)),
        ) == 1

    def test_aplicar_pendente_deixa_a_celula_pendente_com_crednet_velha(self):
        cliente_id, consulta, resultado, _ = self._alvo()
        crednet = {
            "id": str(uuid4()), "storage_path": f"{ORG}/clientes/{cliente_id}/crednet-doc",
            "extracao_crednet": {
                "cpf": "412.954.238-98", "protocolo": "1111111",
                "consulta_em": _ANTIGA.isoformat(), "ocorrencias_constam": False,
            },
        }
        client = _client(**{
            CONSULTAS: [consulta], RESULTADOS: [resultado],
            "cliente_documentos": [{
                **crednet, "org_id": ORG, "cliente_id": cliente_id,
                "tipo_documento": "serasa_crednet", "extracao_status": "ok", "deleted_at": None,
            }],
        })
        assert service.aplicar_crednet_pendente(client, ORG, consulta) is False
        row = self._linha(client, resultado)
        assert row["status"] == "pendente" and row["numero"] is None

    def test_crednet_sem_data_nao_e_pulada(self):
        cliente_id, consulta, resultado, client = self._alvo()
        assert service.registrar_serasa_de_crednet(
            client, ORG, cliente_id, _doc(), _Leitura(consulta_em=None),
        ) == 1
