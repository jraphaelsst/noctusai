"""Julia wave 2 (lais-build-contract section 4): `/api/julia/perguntas`, the contato read route, the
`perguntas` contexto provider, the protected CPF/renda slots. Strict `== 401` on the auth boundary.

Seams: mock DB (the catalogue rows are PARSED from migration 269, so the seed itself is under test),
and the routes' own `Depends` factory `get_perguntas_client`. Nothing of ours is patched; no personal
data in fixtures (the CPF below is the well-known invalid test number, the renda is a round figure)."""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse
from noctusai_lib.testing.migrations import migration_path

from app.services import julia_acoes_service as acoes
from app.services import julia_contexto_service as contexto
from app.services import julia_perguntas_service as svc
from app.services import julia_slots_sensiveis as sens
from tests.support.julia_world import CONNECTION_ID, LEAD_CHAT, ORG_ID, OTHER_ORG_ID, World

MIGRATION = migration_path(Path(__file__).resolve().parents[2], "lais_perguntas")
_ROW = re.compile(
    r"^    \('(\w+)', '((?:[^']|'')*)', '((?:[^']|'')*)', '(\w+)', (NULL|'\w+'), (true|false), (true|false), "
    r"(NULL|'\w+'), (\d+)\)", re.M)
H = {"Authorization": "Bearer test-token"}
URL = "/api/julia/perguntas"
CONTATO_URL = f"/api/julia/contatos/{CONNECTION_ID}/{LEAD_CHAT}"
CPF_DE_TESTE = "111.111.111-11"


def catalogo_do_seed() -> list[dict]:
    rows = []
    for c, label, dica, cat, op, num, moeda, sensivel, ordem in _ROW.findall(MIGRATION.read_text(encoding="utf-8")):
        rows.append({"chave": c, "label": label.replace("''", "'"), "dica": dica.replace("''", "'"), "categoria": cat,
                     "operacao": None if op == "NULL" else op.strip("'"), "numerica": num == "true",
                     "moeda": moeda == "true", "sensivel": None if sensivel == "NULL" else sensivel.strip("'"),
                     "ordem": int(ordem)})
    return rows


class Scene:
    def __init__(self, tc, world):
        self.tc, self.w = tc, world

    def get(self, url):
        return self.tc.get(url, headers=H)

    def put(self, selecao):
        return self.tc.put(URL, json={"selecao": selecao}, headers=H)

    def rows(self, org=ORG_ID):
        return {r["chave"]: r for r in self.w.sw.table("julia_perguntas_org").select("*").execute().data if r["org_id"] == org}


def sel(*chaves, qual=()):
    return [{"chave": c, "qualificatoria": c in qual} for c in chaves]


def _scene(role):
    world = World()
    world.sw.set_table_data("julia_perguntas_catalogo", catalogo_do_seed())
    world.sw.set_table_data("julia_perguntas_org", [])
    world.core.set_table_data("noctus_users", [
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role},
    ])
    world.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=world.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=world.admin),
    ):
        from app.main import app
        from app.routers.julia_perguntas_router import get_perguntas_client

        app.dependency_overrides[get_perguntas_client] = lambda: world.sw
        yield Scene(TestClient(app), world)
        app.dependency_overrides.pop(get_perguntas_client, None)


@pytest.fixture
def admin():
    yield from _scene("owner")


@pytest.fixture
def member():
    yield from _scene("member")


# ── the seed ────────────────────────────────────────────────────────────────
class TestCatalogoSeed:
    def test_every_key_is_snake_case_unique_and_the_categories_are_the_six(self):
        rows = catalogo_do_seed()
        chaves = [r["chave"] for r in rows]
        assert len(chaves) == len(set(chaves)) and len(rows) >= 57
        assert all(re.fullmatch(r"[a-z][a-z0-9_]{1,63}", c) for c in chaves)
        assert {r["categoria"] for r in rows} == {"operacao", "lead", "imovel", "localizacao", "financeiro", "interesses"}
        assert [r["chave"] for r in rows if r["categoria"] == "operacao"] == ["objetivo"]

    def test_sensitive_marks_match_the_slot_protection_table(self):
        marcadas = {r["chave"]: r["sensivel"] for r in catalogo_do_seed() if r["sensivel"]}
        assert marcadas == sens.SENSIVEIS


# ── GET / PUT ───────────────────────────────────────────────────────────────
class TestAuth:
    @pytest.mark.parametrize("method,url", [("get", URL), ("put", URL), ("get", CONTATO_URL)])
    def test_no_token_is_exactly_401(self, admin, method, url):
        kw = {"json": {"selecao": []}} if method == "put" else {}
        assert getattr(admin.tc, method)(url, **kw).status_code == 401

    def test_a_member_can_read(self, member):
        assert member.get(URL).status_code == 200

    def test_a_member_cannot_write_403(self, member):
        assert member.put(sel("objetivo")).status_code == 403


class TestGet:
    def test_shape_and_the_locked_objetivo_default(self, admin):
        data = admin.get(URL).json()["data"]
        assert data["limites"] == {"max_ativas": 8, "max_qualificatorias": 5}
        por = {q["chave"]: q for q in data["catalogo"]}
        assert len(por) == len(catalogo_do_seed())
        assert set(por["objetivo"]) == {"chave", "label", "dica", "categoria", "operacao", "ativa", "qualificatoria",
                                        "bloqueada", "usada_em_criterio"}
        assert por["objetivo"]["ativa"] and por["objetivo"]["bloqueada"]
        assert [c for c, q in por.items() if q["ativa"]] == ["objetivo"]
        assert not any(q["usada_em_criterio"] for q in por.values())

    def test_another_orgs_selection_is_invisible(self, admin):
        admin.w.sw.set_table_data("julia_perguntas_org", [
            {"org_id": OTHER_ORG_ID, "chave": "nome", "ativa": True, "qualificatoria": True}])
        por = {q["chave"]: q for q in admin.get(URL).json()["data"]["catalogo"]}
        assert not por["nome"]["ativa"]


class TestPut:
    def test_full_replace_roundtrip(self, admin):
        r = admin.put(sel("objetivo", "nome", "faixa_preco", qual=("objetivo", "faixa_preco")))
        assert r.status_code == 200
        por = {q["chave"]: q for q in r.json()["data"]["catalogo"]}
        assert {c for c, q in por.items() if q["ativa"]} == {"objetivo", "nome", "faixa_preco"}
        assert por["faixa_preco"]["qualificatoria"] and not por["nome"]["qualificatoria"]
        r = admin.put(sel("objetivo", "bairro_desejado", qual=("objetivo",)))
        assert set(admin.rows()) == {"objetivo", "bairro_desejado"}
        assert r.json()["data"]["catalogo"] == admin.get(URL).json()["data"]["catalogo"]

    def test_objetivo_is_required(self, admin):
        r = admin.put(sel("nome"))
        assert r.status_code == 422 and r.json()["error"]["code"] == "objetivo_obrigatorio"
        assert admin.rows() == {}

    def test_ninth_active_is_refused(self, admin):
        ok = [q["chave"] for q in catalogo_do_seed() if q["chave"] != "objetivo"][:7]
        assert admin.put(sel("objetivo", *ok)).status_code == 200
        outro = [q["chave"] for q in catalogo_do_seed() if q["chave"] != "objetivo"][7]
        r = admin.put(sel("objetivo", *ok, outro))
        assert r.status_code == 422 and r.json()["error"]["code"] == "limite_ativas"
        assert len(admin.rows()) == 8

    def test_sixth_qualifying_is_refused(self, admin):
        chaves = [q["chave"] for q in catalogo_do_seed() if q["chave"] != "objetivo"][:5]
        r = admin.put(sel("objetivo", *chaves, qual=("objetivo", *chaves)))
        assert r.status_code == 422 and r.json()["error"]["code"] == "limite_qualificatorias"
        assert admin.put(sel("objetivo", *chaves, qual=("objetivo", *chaves[:4]))).status_code == 200

    def test_unknown_key_and_duplicates_are_422(self, admin):
        r = admin.put(sel("objetivo", "nao_existe"))
        assert r.status_code == 422 and r.json()["error"]["code"] == "chave_desconhecida"
        r = admin.put(sel("objetivo", "nome", "nome"))
        assert r.status_code == 422 and r.json()["error"]["code"] == "selecao_invalida"

    def test_unknown_body_field_is_422(self, admin):
        r = admin.tc.put(URL, json={"selecao": sel("objetivo"), "extra": 1}, headers=H)
        assert r.status_code == 422

    @pytest.fixture
    def criterio_de_preco(self):
        # the seam wave 3 binds its reader through; restored to the default (no criteria) afterwards
        svc.registrar_criterios(lambda _c, _o: {"faixa_preco": ["Preço até 900 mil"]})
        yield
        svc.registrar_criterios(svc._sem_criterios)  # noqa: SLF001

    def test_a_criterion_blocks_deactivation_409(self, admin, criterio_de_preco):
        admin.put(sel("objetivo", "faixa_preco", qual=("objetivo",)))
        r = admin.put(sel("objetivo"))
        assert r.status_code == 409 and r.json()["error"]["code"] == "usada_em_criterio"
        assert r.json()["error"]["details"]["criterios"] == ["Preço até 900 mil"]
        assert "faixa_preco" in admin.rows()
        por = {q["chave"]: q for q in admin.get(URL).json()["data"]["catalogo"]}
        assert por["faixa_preco"]["usada_em_criterio"]
        assert admin.put(sel("objetivo", "faixa_preco")).status_code == 200  # keeping it is fine


# ── retired from the model path (julia-v2: the standard lives in agents) ────
class TestRetiradaDoCaminhoDoModelo:
    def test_the_questions_are_no_longer_a_contexto_provider(self):
        assert "perguntas" not in dict(contexto.PROVIDERS) and not hasattr(svc, "contexto_provider")

    def test_the_contexto_carries_no_question_list_even_when_the_org_picked_some(self, admin):
        admin.put(sel("objetivo", "nome", "faixa_preco", qual=("objetivo", "faixa_preco")))
        out = contexto.montar(admin.w.sw, ORG_ID, {"operacao": None, "slots": {}}, ferramentas_habilitadas=False)
        assert "perguntas" not in out and "perguntas" not in str(out)

    def test_salvar_slots_is_no_longer_a_handler_the_model_cannot_write_slots(self):
        assert "salvar_slots" not in acoes.HANDLERS and "definir_operacao" not in acoes.HANDLERS
        assert not hasattr(svc, "_h_salvar_slots")


# ── sensitive slots stay protected wherever they are stored ─────────────────
class TestSensiveis:
    def test_the_ledger_copy_is_sanitised_too(self):
        out = acoes.sanitizar_payload({"slots": {"cpf": CPF_DE_TESTE, "renda_familiar": "8000", "quartos": "3"}}, ORG_ID)
        assert CPF_DE_TESTE not in str(out) and "8000" not in str(out)
        assert out["slots"]["quartos"] == "3" and out["slots"]["renda_familiar"] == "faixa:5k_10k"

    @pytest.mark.parametrize("texto,faixa", [("1500", "ate_2k"), ("R$ 2.000,00", "2k_5k"), ("5 mil", "5k_10k"),
                                             ("10000", "10k_20k"), ("25k", "acima_20k"), ("3,5 mil", "2k_5k")])
    def test_renda_buckets(self, texto, faixa):
        assert sens.faixa_renda(texto) == f"faixa:{faixa}"


# ── contato read route ──────────────────────────────────────────────────────
class TestContato:
    def _seed(self, w, org=ORG_ID, slots=None):
        c = w.sw.table("julia_contatos").insert({
            "org_id": org, "connection_id": CONNECTION_ID, "chat_id": LEAD_CHAT, "nome": "Ana", "operacao": "compra",
            "slots": slots or {"faixa_preco": "900000", "quartos": "3"}}).execute().data[0]
        w.sw.table("julia_interacoes").insert({"org_id": org, "contato_id": c["id"], "operacao": "compra"}).execute()
        return c

    def test_a_member_who_is_not_the_owner_of_the_contato_is_403(self, member):
        self._seed(member.w)  # no responsavel, and no connection owned by the caller (A7)
        r = member.get(CONTATO_URL)
        assert r.status_code == 403 and r.json()["error"]["code"] == "sem_acesso"

    def test_shape_and_org_scoping(self, member):
        c = self._seed(member.w)
        member.w.sw.table("julia_contatos").update({"responsavel_user_id": TEST_USER_ID}).eq("id", c["id"]).execute()  # A7: owner
        d = member.get(CONTATO_URL).json()["data"]
        assert set(d) == {"contato", "slots", "interacao_atual"}
        assert d["contato"]["nome"] == "Ana" and d["interacao_atual"]["operacao"] == "compra"
        assert d["slots"] == {}  # neither slot is an active question (only objetivo is)

    def test_only_active_questions_show_their_values(self, admin):
        self._seed(admin.w)
        admin.put(sel("objetivo", "faixa_preco"))
        assert admin.get(CONTATO_URL).json()["data"]["slots"] == {"faixa_preco": "900000"}

    def test_another_orgs_contato_is_404(self, admin):
        self._seed(admin.w, org=OTHER_ORG_ID)
        r = admin.get(CONTATO_URL)
        assert r.status_code == 404 and r.json()["error"]["code"] == "contato_nao_encontrado"

    def test_unknown_chat_is_404_and_no_open_episode_is_null(self, admin):
        assert admin.get(CONTATO_URL).status_code == 404
        c = admin.w.sw.table("julia_contatos").insert({
            "org_id": ORG_ID, "connection_id": CONNECTION_ID, "chat_id": LEAD_CHAT}).execute().data[0]
        assert c and admin.get(CONTATO_URL).json()["data"]["interacao_atual"] is None
