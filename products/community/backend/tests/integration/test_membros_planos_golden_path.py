"""Integration golden path — contract community-m1-contract.md:

create plano → submit application → approve → member exists with the
right status.

Drives the THREE services directly against ONE shared
`MockSupabaseClient` (mirrors how they share one Supabase project in
production) — no HTTP layer, no monkeypatching of our own code.
"""
import asyncio
from uuid import UUID

from noctusai_lib.testing import MockSupabaseClient

from app.services.aplicacoes_service import AplicacoesService, PublicAplicacoesService
from app.services.planos_service import PlanosService

ORG = UUID("00000000-0000-0000-0000-000000000123")


def test_golden_path_plano_to_aplicacao_to_membro():
    mock = MockSupabaseClient()
    planos = PlanosService(mock, org_id=ORG)
    public_aplicacoes = PublicAplicacoesService(mock, org_id=ORG)
    aplicacoes = AplicacoesService(mock, org_id=ORG)

    # 1. Manager creates a plano.
    plano = asyncio.run(planos.create(payload={
        "nome": "Círculo", "descricao": None, "preco_centavos": 9900,
        "ciclo": "mensal", "ordem": 0, "ativo": True,
        "entitlements": {
            "feed": True, "forum": True, "chat": True, "eventos": True,
            "conteudo_ids": [], "grupos_whatsapp": [], "conteudo_todos": False,
        },
    }))
    assert plano["membros_ativos"] == 0

    # 2. A manager-defined question exists (seeded directly — perguntas
    #    CRUD is covered elsewhere).
    pergunta_id = "11111111-1111-1111-1111-111111111111"
    mock.set_table_data("aplicacao_perguntas", [{
        "id": pergunta_id, "org_id": str(ORG), "pergunta": "Por que você quer entrar?",
        "tipo": "texto", "opcoes": [], "obrigatoria": True, "ordem": 0, "ativa": True,
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
    }])

    # 3. The public form is submitted (unauthenticated in production).
    aplicacao = asyncio.run(public_aplicacoes.submit(payload={
        "nome": "Joana Silva", "email": "joana@x.com", "telefone": None,
        "respostas": {pergunta_id: "Quero fazer parte da comunidade."},
    }))
    assert aplicacao["status"] == "pendente"

    # 4. A manager approves it, assigning the plano created in step 1 and
    #    activating on approval.
    result = asyncio.run(aplicacoes.aprovar(
        aplicacao_id=aplicacao["id"], plano_id=plano["id"], ativar=True,
        revisor_id="manager-1",
    ))

    assert result["aplicacao"]["status"] == "aprovada"
    assert result["aplicacao"]["membro_id"] == result["membro"]["id"]
    assert result["membro"]["status"] == "ativo"
    assert result["membro"]["plano_id"] == plano["id"]
    assert result["membro"]["origem"] == "aplicacao"
    assert result["membro"]["email"] == "joana@x.com"

    # 5. membros_ativos on the plano now reflects the newly active member.
    plano_after = asyncio.run(planos.get(plano_id=plano["id"]))
    assert plano_after["membros_ativos"] == 1

    # 6. Approving again is idempotent — same membro, no duplicate.
    result_again = asyncio.run(aplicacoes.aprovar(
        aplicacao_id=aplicacao["id"], plano_id=plano["id"], ativar=True,
        revisor_id="manager-1",
    ))
    assert result_again["membro"]["id"] == result["membro"]["id"]
