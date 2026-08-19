"""Infra de testes — nada de rede.

O client Supabase é substituído por um fake em memória (`FakeDB`) que
implementa o subconjunto do query builder do PostgREST que os services usam:
select/insert/update/delete + eq/gte/lte/in_/order. A autenticação é
substituída via `app.dependency_overrides`, então nenhum teste precisa de um
token real nem de um projeto Supabase de pé.

Duas escolhas que fazem o fake valer a pena:

1. **Defaults por tabela.** O insert aplica os mesmos DEFAULT da migration
   001 (`ativo=true`, `etapa='novo_lead'`, `status='agendado'`…). Sem isso o
   fake devolveria linhas que os `*Out` do Pydantic recusariam — e o teste
   estaria medindo o fake, não o app.
2. **Ordenação de verdade.** `.order()` ordena mesmo, porque parte da regra
   testada depende dela (a agenda sai por data+hora, o histórico da produção
   sai do mais recente para o mais antigo).

As variáveis de ambiente são definidas ANTES de importar `app.*`: o
`Settings()` do pydantic-settings é instanciado na importação do módulo e
falharia sem elas.

Nenhum `CORS_ORIGINS` é fixado aqui: desde a absorção pela plataforma o
default de `app/config.py` é `@registry:own:p-studio` (resolvido por
`noctusai_lib.config.cors_registry`), e é esse default — não um valor de
teste hardcoded — que `tests/test_main.py` exercita. Fixar um valor aqui
esconderia o comportamento real por trás de um valor de teste.
"""
import sys as _sys
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[4]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
# Inject BOTH seed package roots — sem isto `noctusai_seed` fica
# irresolvível num worktree assim que `purge_shadowing_editable_finders`
# derruba o editable finder do venv apontando pro checkout primário. Todo
# outro produto absorvido já carrega este bootstrap (ver
# `products/igig/backend/tests/conftest.py`); o P Studio era o único sem
# ele porque nasceu standalone, sem depender do `noctusai_seed`.
for _p in (_LIB, _FRAMEWORK):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location(
    "_bootstrap_conftest_helpers",
    _LIB / "noctusai_lib" / "testing" / "conftest_helpers.py",
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_mod.purge_shadowing_editable_finders(_LIB)

import copy
import os
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

# 🔴 ATRIBUI, nunca `setdefault`. `setdefault` lê como "forneça um padrão",
# mas o que ele faz é "o que o shell do dev exportou vence" — e o `.env` da
# plataforma carrega `ASAAS_WEBHOOK_TOKEN=` (presente, VAZIO). Qualquer
# processo que o carregue (o servidor MCP, logo o `predeploy_check`) exporta a
# chave, o `setdefault` a vê como já definida e não faz nada; a suíte roda com
# token esperado VAZIO e 15 dos 20 testes de webhook quebram num 503 que não
# tem relação com o que afirmam. Num shell limpo, todos passam.
#
# Pior que a flakiness: `SUPABASE_SERVICE_ROLE_KEY` e `PROVEDOR_COBRANCA`
# tinham o mesmo tratamento. Exporte os valores reais — que o `.env` tem — e a
# suíte monta um client service-role DE VERDADE e o adapter REAL do provedor de
# cobrança. Um `pytest` no shell errado alcançaria produção.
#
# `ENCRYPTION_KEY` entra em `clear` porque nela o que importa é ESTAR definida:
# definida ⇒ o caminho de credencial cifrada roda; ausente ⇒ não roda. String
# vazia não é o mesmo que ausente.
_mod.own_test_env(
    {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_ANON_KEY": "chave-fake-de-teste",
        "SUPABASE_SERVICE_ROLE_KEY": "",
        "P_STUDIO_ORG_ID": "00000000-0000-0000-0000-0000000000ff",
        # Provedor de cobrança: `fake` para nada tentar rede, e um token de
        # webhook conhecido para os testes de autenticação da rota pública.
        "PROVEDOR_COBRANCA": "fake",
        "ASAAS_WEBHOOK_TOKEN": "token-de-webhook-de-teste",
    },
    clear=("ENCRYPTION_KEY", "ASAAS_API_KEY", "ASAAS_BASE_URL"),
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from postgrest.exceptions import APIError  # noqa: E402

# Colunas realmente UUID no schema. Comparar uma delas com texto que não é UUID
# faz o Postgres LEVANTAR (22P02), não devolver vazio — e essa diferença já
# escondeu um bug real: o webhook usa `externalReference` como id de lançamento,
# e uma cobrança criada à mão no painel do Asaas traz texto livre ali. Contra o
# fake antigo (comparação de strings em Python) a busca devolvia "não achei" e a
# suíte inteira passava; contra o banco de verdade o evento estacionava como
# erro e voltava na fila de retry para sempre.
#
# A lista é explícita porque o sufixo `_id` não basta: `provedor_cobranca_id`,
# `provedor_cliente_id`, `evento_id` e `cobranca_id` são TEXT — guardam
# identificadores de terceiro, como `pay_001`.
COLUNAS_UUID = {
    "id", "org_id", "cliente_id", "negocio_id", "imovel_id", "captacao_id",
    "producao_id", "equipamento_id", "servico_id", "lancamento_id",
}


def _checar_tipo_uuid(field: str, value) -> None:
    if field not in COLUNAS_UUID or value is None:
        return
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise APIError({
            "code": "22P02",
            "message": f'invalid input syntax for type uuid: "{value}"',
        }) from None
from postgrest.exceptions import APIError  # noqa: E402

from app.config import settings  # noqa: E402
from app.dependencies import CurrentUser, get_current_user  # noqa: E402
from app.main import app  # noqa: E402

AGORA = "2026-07-31T12:00:00+00:00"


# ─────────────────────────────────────────────────────────────────────────
# Fake do query builder PostgREST
# ─────────────────────────────────────────────────────────────────────────

class FakeQuery:
    def __init__(self, db: "FakeDB", table: str):
        self._db = db
        self._table = table
        self._op = "select"
        self._filters: list[tuple[str, str, object]] = []
        self._orders: list[tuple[str, bool]] = []
        self._payload = None
        self._count = None
        self._limit = None
        self._conflito: list[str] = []

    # builders --------------------------------------------------------
    def select(self, *_args, count=None, **_kw):
        self._op = "select"
        self._count = count
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def update(self, changes):
        self._op = "update"
        self._payload = changes
        return self

    def delete(self):
        self._op = "delete"
        return self

    def upsert(self, row, on_conflict=None, **_kw):
        """INSERT … ON CONFLICT (<cols>) DO UPDATE, como o PostgREST.

        `on_conflict` é uma string separada por vírgula (`"org_id,provider"`),
        exatamente o que o `token_store` do seed passa. Reproduzido com a
        semântica do Postgres — conflito ATUALIZA a linha existente em vez de
        empilhar uma segunda — porque a alternativa (fake que sempre insere)
        deixaria passar precisamente o bug que o UPSERT existe para impedir:
        duas credenciais para o mesmo (org, provedor), com a leitura pegando
        a errada. Este produto já foi mordido duas vezes por um fake mais
        permissivo que o Postgres (ver `p-studio-2026-08.md § Open questions`);
        não é hora de abrir a terceira.
        """
        self._op = "upsert"
        self._payload = row
        self._conflito = [c.strip() for c in (on_conflict or "id").split(",")]
        return self

    def limit(self, n):
        self._limit = n
        return self

    def eq(self, field, value):
        _checar_tipo_uuid(field, value)
        self._filters.append(("eq", field, str(value)))
        return self

    def gte(self, field, value):
        self._filters.append(("gte", field, str(value)))
        return self

    def lte(self, field, value):
        self._filters.append(("lte", field, str(value)))
        return self

    def in_(self, field, values):
        self._filters.append(("in", field, [str(v) for v in values]))
        return self

    def order(self, field, desc=False, **_kw):
        self._orders.append((field, desc))
        return self

    # execução --------------------------------------------------------
    def _match(self, row) -> bool:
        for op, field, value in self._filters:
            actual = row.get(field)
            if actual is None:
                return False
            actual = str(actual)
            if op == "eq" and actual != value:
                return False
            if op == "gte" and actual < value:
                return False
            if op == "lte" and actual > value:
                return False
            if op == "in" and actual not in value:
                return False
        return True

    def _ordenar(self, rows: list[dict]) -> list[dict]:
        # PostgREST aplica os `order` na ordem declarada; um sort estável
        # aplicado do último critério para o primeiro produz o mesmo efeito.
        for field, desc in reversed(self._orders):
            rows.sort(
                key=lambda r: (r.get(field) is None, str(r.get(field) or "")),
                reverse=desc,
            )
        return rows

    def _checar_unique(self, rows: list[dict], nova: dict) -> None:
        """Reproduz as UNIQUE do schema, levantando 23505 como o Postgres.

        Sem isto o dedupe do webhook seria testado contra um banco que aceita
        tudo — o teste passaria e a proteção real nunca teria sido exercitada.
        Como no Postgres, NULL não colide com NULL.
        """
        for colunas in UNIQUES.get(self._table, []):
            valores = [nova.get(c) for c in colunas]
            if any(v is None for v in valores):
                continue
            for existente in rows:
                if [existente.get(c) for c in colunas] == valores:
                    raise APIError({
                        "code": "23505",
                        "message": f"duplicate key value violates unique constraint "
                                   f"on {self._table}({', '.join(colunas)})",
                    })

    def execute(self):
        rows = self._db.data.setdefault(self._table, [])

        if self._op == "select":
            data = self._ordenar([copy.deepcopy(r) for r in rows if self._match(r)])
            total = len(data)
            if self._limit is not None:
                data = data[: self._limit]
            return SimpleNamespace(data=data, count=total if self._count else None)

        if self._op == "insert":
            novas = self._payload if isinstance(self._payload, list) else [self._payload]
            inseridas = []
            for bruta in novas:
                row = {**DEFAULTS.get(self._table, {}), **bruta}
                row.setdefault("id", str(uuid.uuid4()))
                row.setdefault("created_at", AGORA)
                if "updated_at" in DEFAULTS.get(self._table, {}):
                    row.setdefault("updated_at", AGORA)
                self._checar_unique(rows, row)
                rows.append(row)
                inseridas.append(copy.deepcopy(row))
            return SimpleNamespace(data=inseridas, count=None)

        if self._op == "upsert":
            novas = self._payload if isinstance(self._payload, list) else [self._payload]
            resultado = []
            for bruta in novas:
                for campo, valor in bruta.items():
                    _checar_tipo_uuid(campo, valor)
                alvo = None
                for existente in rows:
                    if all(
                        str(existente.get(c)) == str(bruta.get(c))
                        for c in self._conflito
                    ):
                        alvo = existente
                        break
                if alvo is None:
                    row = {**DEFAULTS.get(self._table, {}), **bruta}
                    row.setdefault("id", str(uuid.uuid4()))
                    row.setdefault("created_at", AGORA)
                    rows.append(row)
                    resultado.append(copy.deepcopy(row))
                else:
                    alvo.update(bruta)
                    resultado.append(copy.deepcopy(alvo))
            return SimpleNamespace(data=resultado, count=None)

        if self._op == "update":
            atingidas = [r for r in rows if self._match(r)]
            for r in atingidas:
                r.update(self._payload)
                if "updated_at" in r:
                    r["updated_at"] = AGORA
            return SimpleNamespace(data=[copy.deepcopy(r) for r in atingidas], count=None)

        if self._op == "delete":
            mantidas, removidas = [], []
            for r in rows:
                (removidas if self._match(r) else mantidas).append(r)
            self._db.data[self._table] = mantidas
            return SimpleNamespace(data=[copy.deepcopy(r) for r in removidas], count=None)

        raise AssertionError(f"operação desconhecida: {self._op}")


class FakeDB:
    """Client Supabase fake: `db.table(nome)` → `FakeQuery` sobre memória."""

    def __init__(self, data: dict | None = None):
        self.data: dict[str, list[dict]] = data or {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


# ─────────────────────────────────────────────────────────────────────────
# Defaults por tabela — espelham os DEFAULT da migration 001
# ─────────────────────────────────────────────────────────────────────────

_TIMESTAMPS = {"created_at": AGORA, "updated_at": AGORA}

# Constraints UNIQUE do schema que o fake precisa reproduzir. Só as que têm
# significado para o comportamento testado — o resto seria cerimônia.
UNIQUES: dict[str, list[tuple[str, ...]]] = {
    # Migração 003: dedupe de webhook e guarda de cobrança duplicada.
    "provedor_eventos": [("provedor", "evento_id")],
    "lancamentos": [("provedor", "provedor_cobranca_id")],
}

DEFAULTS: dict[str, dict] = {
    "clientes": {
        "org_id": None, "nome": "Cliente", "empresa": None, "corretor": None,
        "email": None, "telefone": None, "cidade": None, "estado": None,
        "observacoes": None, "ativo": True,
        # Migration 003 — dados do pagador para emissão de cobrança.
        "cpf_cnpj": None, "cep": None, "endereco": None, "bairro": None,
        "provedor": None, "provedor_cliente_id": None,
        **_TIMESTAMPS,
    },
    "imoveis": {
        "org_id": None, "cliente_id": None, "codigo": "PS-000",
        "endereco": "Rua Sem Nome, 0", "condominio": None, "cidade": None,
        "estado": None, "tipo": "apartamento", "padrao": "medio", "area": None,
        "dormitorios": 0, "banheiros": 0, "vagas": 0, "valor": None,
        "maps_url": None, "observacoes": None, **_TIMESTAMPS,
    },
    "servicos": {
        "org_id": None, "nome": "Serviço", "categoria": None, "preco": 0,
        "prazo_dias": 3, "descricao": None, "ativo": True, **_TIMESTAMPS,
    },
    "equipamentos": {
        "org_id": None, "nome": "Equipamento", "marca": None, "modelo": None,
        "numero_serie": None, "categoria": None, "valor": 0, "quantidade": 1,
        "observacoes": None, "ativo": True, **_TIMESTAMPS,
    },
    "negocios": {
        "org_id": None, "cliente_id": None, "imovel_id": None, "titulo": None,
        "corretor": None, "etapa": "novo_lead", "valor": 0,
        "prazo_entrega": None, "forma_pagamento": None, "observacoes": None,
        **_TIMESTAMPS,
    },
    "negocio_servicos": {
        "org_id": None, "negocio_id": None, "servico_id": None, "preco": 0,
        "created_at": AGORA,
    },
    "captacoes": {
        "org_id": None, "negocio_id": None, "cliente_id": None,
        "imovel_id": None, "data": "2026-07-31", "hora": "09:00:00",
        "duracao_minutos": 120, "endereco": "Rua Sem Nome, 0", "maps_url": None,
        "responsavel": None, "status": "agendado", "observacoes": None,
        **_TIMESTAMPS,
    },
    "captacao_equipamentos": {
        "org_id": None, "captacao_id": None, "equipamento_id": None,
        "conferido": False, "created_at": AGORA,
    },
    "producoes": {
        "org_id": None, "negocio_id": None, "captacao_id": None,
        "cliente_id": None, "etapa": "agendado", "responsavel": None,
        "prazo_entrega": None, "entregue_em": None, "observacoes": None,
        **_TIMESTAMPS,
    },
    "producao_eventos": {
        "org_id": None, "producao_id": None, "etapa": "agendado",
        "tipo": "comentario", "responsavel": None, "comentario": None,
        "arquivo_url": None, "created_at": AGORA,
    },
    "lancamentos": {
        "org_id": None, "negocio_id": None, "cliente_id": None,
        "descricao": None, "valor": 0, "status": "a_faturar",
        "data_entrega": None, "vencimento": None, "pago_em": None,
        "forma_pagamento": None, "observacoes": None,
        # Migration 003 — espelho da cobrança no provedor.
        "provedor": None, "provedor_cobranca_id": None, "provedor_status": None,
        "url_fatura": None, "linha_digitavel": None, "pix_copia_e_cola": None,
        "sincronizado_em": None,
        **_TIMESTAMPS,
    },
    # Migration 008 — credenciais cifradas + ambiente ativo.
    "provedor_credenciais": {
        "org_id": None, "provider": None, "encrypted_tokens": None,
        "metadata": {}, **_TIMESTAMPS,
    },
    "integracao_config": {
        "org_id": None, "provedor": "asaas", "ambiente": "sandbox",
        "atualizado_em": AGORA,
    },
    "provedor_eventos": {
        "org_id": None, "provedor": "asaas", "evento_id": None, "tipo": None,
        "cobranca_id": None, "lancamento_id": None, "payload": {},
        "efeito": None, "erro": None, "processado_em": None,
        **_TIMESTAMPS,
    },
}


def make_row(table: str, **overrides) -> dict:
    """Linha realista da tabela, com os defaults do banco e id gerado."""
    return {
        **DEFAULTS[table],
        "id": str(uuid.uuid4()),
        "org_id": settings.org_id,
        **overrides,
    }


# ─────────────────────────────────────────────────────────────────────────
# Atalhos de data — testes de financeiro/dashboard dependem de "hoje"
# ─────────────────────────────────────────────────────────────────────────

HOJE = date.today()


def dias(n: int) -> str:
    """Data ISO deslocada de `n` dias a partir de hoje (negativo = passado)."""
    return (HOJE + timedelta(days=n)).isoformat()


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────

USER_ID = "00000000-0000-0000-0000-0000000000aa"
AUTH = {"Authorization": "Bearer token-fake"}


@pytest.fixture(autouse=True)
def _sem_rede(request, monkeypatch):
    """Impede qualquer conexão de rede fora dos testes `ao_vivo`.

    O docstring deste arquivo promete "nada de rede" desde sempre, mas era só
    uma promessa: nada verificava. Passou a importar de verdade quando uma
    chave de PRODUÇÃO do Asaas entrou no `.env` — o pydantic-settings lê o
    `.env` também durante os testes, então a credencial que emite boleto real
    está carregada no processo enquanto a suíte roda.

    O `PROVEDOR_COBRANCA=fake` acima já evita o caminho normal. Isto aqui é a
    segunda tranca, e é a que não depende de ninguém lembrar: um teste novo que
    monte um `ProvedorAsaas` à mão falha com mensagem clara em vez de emitir
    uma cobrança de verdade na conta do cliente.

    `MockTransport`, `FakeDB` e `TestClient` não abrem socket nenhum — o
    primeiro intercepta abaixo do `httpx.Client`, e o último fala ASGI em
    processo. Nada legítimo é bloqueado por isto.
    """
    if request.node.get_closest_marker("ao_vivo"):
        return

    import socket

    def recusar(*args, **kwargs):
        raise RuntimeError(
            "Este teste tentou abrir uma conexão de rede. A suíte padrão é "
            "offline por construção — use uma fixture gravada "
            "(tests/providers/conftest.py) ou marque o teste com "
            "@pytest.mark.ao_vivo."
        )

    monkeypatch.setattr(socket.socket, "connect", recusar)
    monkeypatch.setattr(socket, "create_connection", recusar)


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def client(fake_db):
    """TestClient autenticado como equipe do estúdio, com o FakeDB injetado.

    Não há papel por linha no P Studio: quem está na organização é equipe.
    Por isso existe um único client autenticado, e não um por papel.
    """
    user = CurrentUser(
        id=USER_ID,
        email="equipe@pstudio.app",
        nome="Equipe",
        org_id=settings.org_id,
        token="token-fake",
        db=fake_db,
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_anon():
    """TestClient sem override — exercita o guard real (401 sem header)."""
    app.dependency_overrides.clear()
    yield TestClient(app)


# ─────────────────────────────────────────────────────────────────────────
# Seeds compostos — o cenário mínimo que quase todo teste de domínio precisa
# ─────────────────────────────────────────────────────────────────────────

def seed_basico(fake_db: FakeDB) -> dict:
    """Um cliente, um imóvel, dois serviços e um equipamento."""
    cliente = make_row("clientes", nome="Imobiliária Alfa", empresa="Alfa Ltda")
    imovel = make_row(
        "imoveis", cliente_id=cliente["id"], codigo="PS-001",
        endereco="Av. Atlântica, 1500", tipo="cobertura", padrao="alto",
    )
    foto = make_row("servicos", nome="Ensaio fotográfico",
                    categoria="Fotografia", preco=950, prazo_dias=3)
    drone = make_row("servicos", nome="Cobertura com drone",
                     categoria="Aéreo", preco=700, prazo_dias=3)
    camera = make_row("equipamentos", nome="Sony A7 IV", categoria="camera")

    fake_db.data["clientes"] = [cliente]
    fake_db.data["imoveis"] = [imovel]
    fake_db.data["servicos"] = [foto, drone]
    fake_db.data["equipamentos"] = [camera]
    return {
        "cliente": cliente, "imovel": imovel,
        "foto": foto, "drone": drone, "camera": camera,
    }
