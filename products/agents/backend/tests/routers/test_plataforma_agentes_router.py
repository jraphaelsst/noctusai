"""Platform AI-call registry: ``/api/studio/plataforma/agentes`` + ``/modelos`` 
the seed registry (reader and call helpers are tested in the seed). Fake registry bound through ``dependency_overrides`` -- nothing patched."""
from __future__ import annotations

from pathlib import Path

import pytest

from noctusai_lib.testing.migrations import migration_sql
from noctusai_lib.integrations.prompt_registry import ChamadaMedida, FakePromptRegistry, PromptEntry, modelos_permitidos
from app.routers.plataforma_agentes_router import get_prompt_registry_dep
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, agents_client  # noqa: F401 — fixture

CHAVE = "agents.eval_improver"
URL = "/api/studio/plataforma/agentes"
CORE = Path(__file__).resolve().parents[4] / "core"


def _row(**kw) -> PromptEntry:
    base = dict(chave=CHAVE, nome="Avaliador e corretor de agentes", descricao="d", vendor="anthropic",
                modelo="claude-opus-5-5", prompt="PROMPT ORIGINAL")
    return PromptEntry(**{**base, **kw})


@pytest.fixture
def kit(agents_client):
    from app.main import app

    store = FakePromptRegistry([_row()])
    app.dependency_overrides[get_prompt_registry_dep] = lambda: store
    agents_client.store = store
    try:
        yield agents_client
    finally:
        app.dependency_overrides.pop(get_prompt_registry_dep, None)


def _admin(c, role="admin"):
    c.mock_supabase.set_table_data("noctus_users", [{
        "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "role": role, "org_role": "owner"}])


ROUTES = [("get", URL, None), ("get", f"{URL}/{CHAVE}", None), ("patch", f"{URL}/{CHAVE}", {"prompt": "x"}),
          ("get", "/api/studio/plataforma/modelos", None)]


class TestBoundary:
    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_no_credential_is_401(self, kit, method, path, body):
        kw = {"json": body} if body is not None else {}
        assert getattr(kit.raw(), method)(path, **kw).status_code == 401

    @pytest.mark.parametrize("method,path,body", ROUTES)
    def test_non_platform_admin_is_403_and_nothing_changes(self, kit, method, path, body):
        _admin(kit, role="user")
        kw = {"json": body} if body is not None else {}
        resp = getattr(kit, method)(path, **kw)
        assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required"
        assert kit.store.obter(CHAVE).prompt == "PROMPT ORIGINAL"


class TestApi:
    def test_list_has_no_prompt_and_get_has_it(self, kit):
        _admin(kit)
        lst = kit.get(URL).json()
        assert [r["chave"] for r in lst] == [CHAVE] and "prompt" not in lst[0]
        assert kit.get(f"{URL}/{CHAVE}").json()["prompt"] == "PROMPT ORIGINAL"

    def test_unknown_key_is_404(self, kit):
        _admin(kit)
        assert kit.get(f"{URL}/nao.existe").status_code == 404
        assert kit.patch(f"{URL}/nao.existe", json={"prompt": "x"}).status_code == 404

    def test_malformed_logical_id_is_422(self, kit):
        _admin(kit)
        assert kit.get(f"{URL}/Agents-Eval").status_code == 422

    def test_patch_round_trip_persists_and_attributes(self, kit):
        _admin(kit)
        resp = kit.patch(f"{URL}/{CHAVE}", json={"prompt": "NOVO", "modelo": "claude-sonnet-5"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["prompt"] == "NOVO" and resp.json()["modelo"] == "claude-sonnet-5"
        again = kit.get(f"{URL}/{CHAVE}").json()
        assert again["prompt"] == "NOVO" and again["modelo"] == "claude-sonnet-5"
        assert again["atualizado_por"] == str(DEFAULT_USER_ID) and again["atualizado_em"]

    def test_patch_only_prompt_keeps_model(self, kit):
        _admin(kit)
        assert kit.patch(f"{URL}/{CHAVE}", json={"prompt": "so prompt"}).json()["modelo"] == "claude-opus-5-5"

    def test_invalid_model_is_422_and_writes_nothing(self, kit):
        _admin(kit)
        resp = kit.patch(f"{URL}/{CHAVE}", json={"modelo": "gpt-5.6-sol"})  # openai model on an anthropic row
        assert resp.status_code == 422 and resp.json()["code"] == "modelo_invalido"
        assert kit.patch(f"{URL}/{CHAVE}", json={"modelo": "inventado-9"}).status_code == 422
        assert kit.store.obter(CHAVE).modelo == "claude-opus-5-5"

    def test_switching_vendor_needs_a_model_of_that_vendor(self, kit):
        _admin(kit)
        # current model is anthropic's: switching only the vendor leaves an unroutable pair
        assert kit.patch(f"{URL}/{CHAVE}", json={"vendor": "openai"}).status_code == 422
        assert kit.patch(f"{URL}/{CHAVE}", json={"vendor": "openai", "modelo": "claude-sonnet-5"}).status_code == 422
        assert kit.store.obter(CHAVE).vendor == "anthropic"
        ok = kit.patch(f"{URL}/{CHAVE}", json={"vendor": "openai", "modelo": "gpt-5.6-sol"})
        assert ok.status_code == 200, ok.text
        assert (ok.json()["vendor"], ok.json()["modelo"]) == ("openai", "gpt-5.6-sol")
        assert kit.store.obter(CHAVE).vendor == "openai"

    def test_detail_carries_the_measurement_aggregate(self, kit):
        _admin(kit)
        for ms, ok, custo in [(100, True, 0.01), (300, True, 0.03), (900, False, None)]:
            kit.store.registrar_chamada(ChamadaMedida(CHAVE, "anthropic", "claude-opus-5-5", ms, ok, custo_usd=custo))
        kit.store.registrar_chamada(ChamadaMedida(CHAVE, "openai", "gpt-5.6-sol", 50, True, custo_usd=0.002))
        est = {(e["vendor"], e["modelo"]): e for e in kit.get(f"{URL}/{CHAVE}").json()["estatisticas"]}
        a = est[("anthropic", "claude-opus-5-5")]
        assert a["n"] == 3 and a["p50_latencia_ms"] == 300 and abs(a["custo_medio_usd"] - 0.02) < 1e-9
        assert abs(a["taxa_erro"] - 1 / 3) < 1e-9
        assert est[("openai", "gpt-5.6-sol")]["n"] == 1

    def test_empty_or_unknown_body_is_422(self, kit):
        _admin(kit)
        assert kit.patch(f"{URL}/{CHAVE}", json={}).status_code == 422
        assert kit.patch(f"{URL}/{CHAVE}", json={"vendor": "openai"}).status_code == 422

    def test_modelos_filter_by_vendor(self, kit):
        _admin(kit)
        ids = {m["id"] for m in kit.get("/api/studio/plataforma/modelos?vendor=anthropic").json()}
        assert "claude-opus-5-5" in ids and not any(i.startswith("gpt") for i in ids)
        assert kit.get("/api/studio/plataforma/modelos?vendor=gemini").status_code == 422
        both = {m["vendor"] for m in kit.get("/api/studio/plataforma/modelos").json()}
        assert both == {"anthropic", "openai"}


class TestCatalogAndMigration:
    def test_seed_model_is_in_the_catalog(self):
        assert "claude-opus-5-5" in {m["id"] for m in modelos_permitidos("anthropic")}

    def test_migration_is_service_only_tier_platform_with_one_seed_row(self):
        sql = migration_sql(CORE / "backend", "plataforma_agentes")
        assert "ENABLE ROW LEVEL SECURITY" in sql
        assert "REVOKE ALL ON public.plataforma_agentes FROM PUBLIC, anon, authenticated" in sql
        assert "COMMENT ON TABLE public.plataforma_agentes IS 'tier:platform'" in sql
        assert "COMMENT ON TABLE public.plataforma_agente_chamadas IS 'tier:platform'" in sql
        assert "REVOKE ALL ON public.plataforma_agente_chamadas FROM PUBLIC, anon, authenticated" in sql
        assert sql.count("INSERT INTO public.plataforma_agentes") == 1 and f"'{CHAVE}'" in sql
