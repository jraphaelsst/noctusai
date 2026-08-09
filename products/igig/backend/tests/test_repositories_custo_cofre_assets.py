"""Custo/hora, Cofre de Acessos and visual assets — the §10 decisions.

Run against the REAL SQLite store with the REAL schema, so these prove the
migrations and the repositories agree.

The Cofre tests matter most: they assert the failure mode, not just the happy
path. A vault that quietly stores plaintext when the key is missing is worse
than no vault, because it looks like one.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from noctusai_lib.integrations.persistence import SqliteRecordStore

from app.repositories import Repositorios
from app.store import aplicar_schema_sqlite

ORG = "org-igig"
OUTRA_ORG = "org-outra"


@pytest.fixture
def repos() -> Repositorios:
    store = SqliteRecordStore(":memory:")
    aplicar_schema_sqlite(store)
    return Repositorios(store)


@pytest.fixture
def chave() -> bytes:
    return Fernet.generate_key()


@pytest.fixture
def cliente(repos: Repositorios) -> dict:
    return repos.cliente.criar(ORG, {"nome": "Padaria Sol"})


# ── Custo/hora — role default + per-person override ─────────────────
class TestCustoHora:
    def test_inherits_the_role_default(self, repos):
        funcao = repos.funcao.criar(ORG, {"nome": "designer", "custo_hora_padrao": 80.0})
        prof = repos.profissional.criar(ORG, {"nome": "Ana", "funcao_id": funcao["id"]})
        assert repos.profissional.custo_hora_efetivo(
            ORG, prof["id"], funcoes=repos.funcao
        ) == 80.0

    def test_override_wins_over_the_role_default(self, repos):
        funcao = repos.funcao.criar(ORG, {"nome": "designer", "custo_hora_padrao": 80.0})
        prof = repos.profissional.criar(
            ORG, {"nome": "Bia", "funcao_id": funcao["id"], "custo_hora_override": 140.0}
        )
        assert repos.profissional.custo_hora_efetivo(
            ORG, prof["id"], funcoes=repos.funcao
        ) == 140.0

    def test_zero_override_is_a_real_rate_not_an_absent_one(self, repos):
        """An unpaid intern costs 0 — that must not fall back to the role rate."""
        funcao = repos.funcao.criar(ORG, {"nome": "designer", "custo_hora_padrao": 80.0})
        prof = repos.profissional.criar(
            ORG, {"nome": "Estagiário", "funcao_id": funcao["id"], "custo_hora_override": 0.0}
        )
        assert repos.profissional.custo_hora_efetivo(
            ORG, prof["id"], funcoes=repos.funcao
        ) == 0.0

    def test_undefined_cost_raises_rather_than_silently_costing_zero(self, repos):
        """Silently returning 0 would understate every job this person touches."""
        prof = repos.profissional.criar(ORG, {"nome": "Sem função"})
        with pytest.raises(ValueError, match="custo_hora indefinido"):
            repos.profissional.custo_hora_efetivo(ORG, prof["id"], funcoes=repos.funcao)

    def test_role_names_are_unique_per_org(self, repos):
        from noctusai_lib.integrations.persistence import PersistenceError

        repos.funcao.criar(ORG, {"nome": "designer", "custo_hora_padrao": 80.0})
        with pytest.raises(PersistenceError):
            repos.funcao.criar(ORG, {"nome": "designer", "custo_hora_padrao": 90.0})

    def test_same_role_name_allowed_in_a_different_org(self, repos):
        repos.funcao.criar(ORG, {"nome": "designer", "custo_hora_padrao": 80.0})
        assert repos.funcao.criar(OUTRA_ORG, {"nome": "designer", "custo_hora_padrao": 50.0})

    def test_ativos_filters_inactive_people(self, repos):
        repos.profissional.criar(ORG, {"nome": "Ativa", "ativo": True})
        repos.profissional.criar(ORG, {"nome": "Saiu", "ativo": False})
        assert [p["nome"] for p in repos.profissional.ativos(ORG)] == ["Ativa"]


# ── Cofre de Acessos — Fernet at rest ───────────────────────────────
class TestCofreDeAcessos:
    def test_password_is_never_stored_in_plaintext(self, repos, cliente, chave):
        """The single most important assertion in this file."""
        segredo = "senha-super-secreta"
        registro = repos.acesso.guardar(
            ORG, cliente["id"], rotulo="Meta Business", senha=segredo, chave=chave
        )
        assert registro["senha_cifrada"] != segredo
        assert segredo not in str(registro)
        # And not anywhere in the raw row either.
        bruto = repos.acesso.buscar(ORG, registro["id"])
        assert segredo not in str(bruto)

    def test_round_trips_with_the_right_key(self, repos, cliente, chave):
        segredo = "senha-super-secreta"
        registro = repos.acesso.guardar(
            ORG, cliente["id"], rotulo="Meta Business", senha=segredo, chave=chave
        )
        assert repos.acesso.revelar_senha(ORG, registro["id"], chave) == segredo

    def test_a_different_key_cannot_decrypt(self, repos, cliente, chave):
        from cryptography.fernet import InvalidToken

        registro = repos.acesso.guardar(
            ORG, cliente["id"], rotulo="Meta", senha="x", chave=chave
        )
        with pytest.raises((InvalidToken, ValueError)):
            repos.acesso.revelar_senha(ORG, registro["id"], Fernet.generate_key())

    def test_refuses_to_store_a_password_without_a_key(self, repos, cliente):
        """A silent plaintext fallback is the failure this vault exists to prevent."""
        with pytest.raises(ValueError, match="texto puro"):
            repos.acesso.guardar(ORG, cliente["id"], rotulo="Meta", senha="segredo")

    def test_a_record_without_a_password_is_fine(self, repos, cliente):
        """Drive folder links and usernames are legitimate password-free rows."""
        registro = repos.acesso.guardar(
            ORG, cliente["id"], rotulo="Drive", url="https://drive.example/x"
        )
        assert registro["senha_cifrada"] is None
        assert repos.acesso.revelar_senha(ORG, registro["id"], Fernet.generate_key()) is None

    def test_listing_does_not_decrypt(self, repos, cliente, chave):
        segredo = "senha-super-secreta"
        repos.acesso.guardar(ORG, cliente["id"], rotulo="Meta", senha=segredo, chave=chave)
        listados = repos.acesso.do_cliente(ORG, cliente["id"])
        assert segredo not in str(listados)

    def test_cofre_is_org_scoped(self, repos, cliente, chave):
        registro = repos.acesso.guardar(
            ORG, cliente["id"], rotulo="Meta", senha="x", chave=chave
        )
        assert repos.acesso.do_cliente(OUTRA_ORG, cliente["id"]) == []
        from noctusai_lib.integrations.persistence import RecordNotFound

        with pytest.raises(RecordNotFound):
            repos.acesso.revelar_senha(OUTRA_ORG, registro["id"], chave)

    def test_deleting_a_client_removes_its_credentials(self, repos, cliente, chave):
        repos.acesso.guardar(ORG, cliente["id"], rotulo="Meta", senha="x", chave=chave)
        repos.cliente.remover(ORG, cliente["id"])
        assert repos.acesso.listar(ORG) == []


# ── Peças — storage keys, not bytes ─────────────────────────────────
class TestPecas:
    @pytest.fixture
    def pauta(self, repos, cliente) -> dict:
        return repos.pauta.criar(ORG, {"cliente_id": cliente["id"], "titulo": "Post"})

    def test_anexar_records_a_storage_key(self, repos, pauta):
        peca = repos.peca.anexar(
            ORG, pauta["id"], storage_key="igig/pautas/x.png",
            nome_arquivo="x.png", mime_type="image/png", tamanho_bytes=1234,
        )
        assert peca["storage_key"] == "igig/pautas/x.png"
        assert peca["ordem"] == 0

    def test_ordering_appends(self, repos, pauta):
        for i in range(3):
            repos.peca.anexar(ORG, pauta["id"], storage_key=f"k{i}")
        assert [p["ordem"] for p in repos.peca.da_pauta(ORG, pauta["id"])] == [0, 1, 2]

    def test_pecas_are_org_scoped(self, repos, pauta):
        repos.peca.anexar(ORG, pauta["id"], storage_key="k")
        assert repos.peca.da_pauta(OUTRA_ORG, pauta["id"]) == []

    def test_deleting_a_pauta_removes_its_pecas(self, repos, pauta):
        repos.peca.anexar(ORG, pauta["id"], storage_key="k")
        repos.pauta.remover(ORG, pauta["id"])
        assert repos.peca.listar(ORG) == []
