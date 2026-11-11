"""The classifier's admin routes: strict 401 unauthenticated, 403 for a non-admin member, and the blind sample never
carrying the model's verdict."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from noctusai_lib.integrations.prompt_registry import configure_prompt_registry

from app.routers import classificacao_router as cr
from app.shadow import classificador as clf

ROTAS = [("get", "/api/classificacao/amostra"), ("post", "/api/classificacao/replay")]
LINHAS = [
    {"intake_id": "00000000-0000-0000-0000-0000000000a1", "output_id": "00000000-0000-0000-0000-0000000000b1",
     "body": "Pode ser quinta às 15h?", "received_at": "2026-11-10T12:00:00+00:00",
     "label": "agendamento", "confidence": 0.93, "reason_code": "propoe_horario", "estrato": "agendamento:alta"},
    {"intake_id": "00000000-0000-0000-0000-0000000000a2", "output_id": "00000000-0000-0000-0000-0000000000b2",
     "body": "Viu o jogo?", "received_at": "2026-11-10T12:01:00+00:00",
     "label": "outro", "confidence": 0.55, "reason_code": "sem_agendamento", "estrato": "outro:baixa"},
]


@pytest.mark.parametrize("metodo,rota", ROTAS)
def test_unauthenticated_is_strictly_401(client, metodo, rota):
    resp = getattr(client.raw(), metodo)(rota, **({"json": {"intake_ids": [LINHAS[0]["intake_id"]]}} if metodo == "post" else {}))
    assert resp.status_code == 401


@pytest.mark.parametrize("metodo,rota", ROTAS)
def test_a_member_who_is_not_an_org_admin_is_403(client, metodo, rota):
    resp = getattr(client, metodo)(rota, **({"json": {"intake_ids": [LINHAS[0]["intake_id"]]}} if metodo == "post" else {}))
    assert resp.status_code == 403


@pytest.fixture
def admin(client, registro):
    from app.main import app

    app.dependency_overrides[cr.require_org_admin] = lambda: (SimpleNamespace(id="user-1"), "t", "test-org-123")
    configure_prompt_registry(registro)
    client.mock_supabase.set_rpc_data("amostra_classificacoes", LINHAS)
    yield client
    app.dependency_overrides.pop(cr.require_org_admin, None)
    configure_prompt_registry(None)


@pytest.fixture
def registro():
    from noctusai_lib.integrations.prompt_registry import FakePromptRegistry, PromptEntry, invalidar_cache

    invalidar_cache()
    yield FakePromptRegistry([PromptEntry(chave=clf.CHAVE, nome="t", descricao="t", vendor="anthropic",
                                          modelo="claude-haiku-5-5", prompt="P")])
    invalidar_cache()


def test_blind_sample_returns_text_and_opaque_ids_only(admin):
    resp = admin.get("/api/classificacao/amostra?por_estrato=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["modo"] == "cego" and len(body["itens"]) == 2
    for item in body["itens"]:
        assert set(item) == {"intake_id", "output_id", "texto", "recebida_em"}
    # the items (what a labeller sees) carry no trace of the verdict; prompt_version legitimately names the registry key
    texto = json.dumps(body["itens"], ensure_ascii=False)
    for vazamento in ("agendamento", "outro", "0.93", "0.55", "propoe_horario", "sem_agendamento", "alta", "baixa"):
        assert vazamento not in texto
    (nome, params), = [c for c in admin.mock_supabase.rpc_calls if c[0] == "amostra_classificacoes"]
    assert params["p_prompt_version"] == clf.versao_do_prompt("P") and params["p_model"] == "claude-haiku-5-5"


def test_revealed_sample_adds_the_verdict(admin):
    resp = admin.get("/api/classificacao/amostra?modo=revelado")
    assert resp.status_code == 200
    item = resp.json()["itens"][0]
    assert {"label", "confidence", "reason_code", "estrato"} <= set(item)


def test_sample_rejects_an_unknown_mode(admin):
    assert admin.get("/api/classificacao/amostra?modo=tudo").status_code == 422


def test_replay_bounds_the_request(admin):
    assert admin.post("/api/classificacao/replay", json={"intake_ids": []}).status_code == 422
    assert admin.post("/api/classificacao/replay", json={"intake_ids": ["x"]}).status_code == 422
    many = ["00000000-0000-0000-0000-%012d" % n for n in range(201)]
    assert admin.post("/api/classificacao/replay", json={"intake_ids": many}).status_code == 422
    extra = {"intake_ids": [LINHAS[0]["intake_id"]], "prompt": "x"}
    assert admin.post("/api/classificacao/replay", json=extra).status_code == 422
