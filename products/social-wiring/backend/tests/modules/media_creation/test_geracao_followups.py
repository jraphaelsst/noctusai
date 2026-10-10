"""BE-P follow-ups: error-key spelling, shared ViralCard presenter, budget refusal at submit."""
from __future__ import annotations

import uuid

import anyio
import pytest
from fastapi import HTTPException

from noctusai_lib.integrations.llm import LLMBudgetExceeded
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.modules.media_creation.deps import BIBLIOTECA_BUCKET
from app.modules.media_creation.services import geracao_jobs
from app.modules.media_creation.services.viral_card import present_viral_card, viral_cards

ORG = "test-org-123"


class _Boom(FakeStorageBackend):
    async def signed_url(self, **_kw):
        raise RuntimeError("storage down")


def _seed_viral(c, **over):
    perfil, viral = str(uuid.uuid4()), str(uuid.uuid4())
    c.from_("cs_perfis_monitorados").insert({"id": perfil, "org_id": ORG, "handle": "alvo"}).execute()
    c.from_("cs_virais").insert({
        "id": viral, "org_id": ORG, "perfil_id": perfil, "codigo": 3, "permalink": "https://x/p",
        "thumbnail_path": "t/1.jpg", "gancho": "Um gancho", "e_viral": True, **over,
    }).execute()
    return viral


class TestErrorKeys:
    def test_geracao_indisponivel_uses_code_message(self):
        class Off:
            geracao_worker_enabled = False

        with pytest.raises(HTTPException) as exc:
            geracao_jobs.assert_geracao_disponivel(Off())
        assert exc.value.status_code == 503
        assert set(exc.value.detail) == {"code", "detail"} and exc.value.detail["code"] == "geracao_indisponivel"


class TestViralCardPresenter:
    def test_signs_from_the_private_library_bucket(self, client):
        vid = _seed_viral(client.mock_supabase)
        cards = anyio.run(lambda: viral_cards(client.mock_supabase, ORG, FakeStorageBackend(), [vid]))
        card = cards[vid]
        assert BIBLIOTECA_BUCKET == "sw-biblioteca"
        assert card["thumbnail_url"].startswith(f"fake://storage/{BIBLIOTECA_BUCKET}/t/1.jpg")
        assert card["perfil"]["handle"] == "alvo" and card["codigo"] == 3 and card["trecho"] == "Um gancho"

    def test_foreign_org_viral_is_absent(self, client):
        vid = _seed_viral(client.mock_supabase)
        assert anyio.run(lambda: viral_cards(client.mock_supabase, "other-org", FakeStorageBackend(), [vid])) == {}

    @pytest.mark.parametrize("storage", [None, _Boom()])
    def test_unsignable_thumbnail_is_none_not_an_error(self, client, storage):
        vid = _seed_viral(client.mock_supabase)
        card = anyio.run(lambda: viral_cards(client.mock_supabase, ORG, storage, [vid]))[vid]
        assert card["thumbnail_url"] is None and card["permalink"] == "https://x/p"

    def test_no_thumbnail_path(self):
        card = anyio.run(
            lambda: present_viral_card({"id": "v", "perfil_id": "p", "caption": "  a   b "}, None, FakeStorageBackend())
        )
        assert card["thumbnail_url"] is None and card["trecho"] == "a b" and card["perfil"]["handle"] == ""


class TestOrcamentoNoSubmit:
    def test_over_budget_is_503_orcamento_ia_excedido(self):
        async def hard_stop(org_id):
            raise LLMBudgetExceeded(org_id=org_id, spent_brl=10.0, budget_brl=5.0)

        with pytest.raises(HTTPException) as exc:
            anyio.run(lambda: geracao_jobs.assert_orcamento_ia(ORG, enforce=hard_stop))
        assert exc.value.status_code == 503
        assert exc.value.detail["code"] == "orcamento_ia_excedido" and exc.value.detail["detail"]

    def test_within_budget_passes(self):
        async def ok(org_id):
            return None

        anyio.run(lambda: geracao_jobs.assert_orcamento_ia(ORG, enforce=ok))

    def test_unconfigured_budget_module_fails_open_like_the_seed(self):
        anyio.run(lambda: geracao_jobs.assert_orcamento_ia(ORG))
