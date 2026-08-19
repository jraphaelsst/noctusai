"""Unidade: app.database — tradução de erro do Postgres e guarda da service key."""
import pytest
from fastapi import HTTPException
from postgrest.exceptions import APIError

from app.config import settings
from app.database import execute, get_admin_client


class _QueryQueQuebra:
    def __init__(self, err):
        self._err = err

    def execute(self):
        raise self._err


class _QueryOk:
    def execute(self):
        return "resultado"


def test_execute_devolve_o_resultado_quando_nao_ha_erro():
    assert execute(_QueryOk()) == "resultado"


def test_unique_violation_vira_409():
    err = APIError({"message": "duplicate key value", "code": "23505"})
    with pytest.raises(HTTPException) as exc:
        execute(_QueryQueQuebra(err))
    assert exc.value.status_code == 409
    assert "Já existe" in exc.value.detail


def test_foreign_key_violation_vira_409_com_dica_de_vinculo():
    err = APIError({"message": "violates foreign key constraint", "code": "23503"})
    with pytest.raises(HTTPException) as exc:
        execute(_QueryQueQuebra(err))
    assert exc.value.status_code == 409
    assert "vínculo" in exc.value.detail


def test_violacao_de_rls_vira_403():
    err = APIError({"message": "new row violates row-level security", "code": "42501"})
    with pytest.raises(HTTPException) as exc:
        execute(_QueryQueQuebra(err))
    assert exc.value.status_code == 403


def test_erro_desconhecido_vira_400_com_a_mensagem_do_banco():
    err = APIError({"message": "coluna inexistente", "code": "42703"})
    with pytest.raises(HTTPException) as exc:
        execute(_QueryQueQuebra(err))
    assert exc.value.status_code == 400
    assert "coluna inexistente" in exc.value.detail


def test_get_admin_client_sem_service_key_da_503_com_instrucao(monkeypatch):
    """503, não 400 — a chave que falta é NOSSA, não do chamador.

    Este factory fica atrás do webhook PÚBLICO do Asaas, e o provedor lê o
    status para decidir se continua entregando: 400 diz "requisição malformada,
    não repita" sobre uma chamada perfeitamente válida, então uma chave que
    esquecemos de configurar pareceria culpa do provedor e envenenaria a fila
    de entrega em silêncio. Mesma classe do 401 que o seed devolvia quando não
    conseguia FALAR com o Supabase (corrigido em 2026-08-18): falha de
    infraestrutura nunca se disfarça de erro do cliente.
    """
    monkeypatch.setattr(settings, "supabase_service_role_key", "")
    with pytest.raises(HTTPException) as exc:
        get_admin_client()
    assert exc.value.status_code == 503
    assert "SUPABASE_SERVICE_ROLE_KEY" in exc.value.detail
