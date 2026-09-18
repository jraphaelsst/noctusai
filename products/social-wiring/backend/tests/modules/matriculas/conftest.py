"""Fixtures + a synthetic matrícula for the structured-matrícula tests (109).

🔴 EVERY NAME, NUMBER AND BANK BELOW IS INVENTED. The text also carries
deliberate typos and odd spacing ("Edificio Jacarandá Ficticio", "com  o
apto", "quitaçao") because the feature under test promises to quote them
byte for byte — a fixture without them could not catch a normaliser sneaking
into the output path.

Rows are seeded against the scoped mock `app.modules.matriculas.deps.
get_matriculas_client` resolves (the canonical `get_scoped_admin_client`,
cached per admin client), so a row seeded here is visible to a later request
in the same test.
"""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from noctusai_lib.integrations.documents import FakeMatriculaExtractor, TextSource
from noctusai_lib.integrations.documents.transcription import (
    TranscribedPage,
    Transcription,
)
from noctusai_lib.integrations.storage import FakeStorageBackend

from app.dependencies import coerce_org_uuid
from app.modules.imovel_hub.deps import (
    get_matricula_extractor_factory,
    get_storage_backend,
)
from app.modules.matriculas.deps import (
    get_background_client,
    get_matriculas_client,
    get_transcriber_factory,
)

ORG_RAW = "test-org-123"
ORG_ID = str(coerce_org_uuid(ORG_RAW))
CODIGO = "AP1234"

TEXTO = (
    "MATRÍCULA Nº 45.678 — FICHA 01\n"
    "IMÓVEL: Apartamento nº 12 do Edificio Jacarandá Ficticio, situado a Rua das "
    "Amostras, 99, com area privativa de 70,00m2 , confrontando com  o apto 11.\n"
    "PROPRIETÁRIA: Fulana de Teste Exemplar, brasileira, CPF 000.000.000-00.\n"
    "REGISTRO ANTERIOR: R-3/1.234 do 9º Oficio.\n"
    "\n"
    "R-1/45.678 - Em 10 de março de 2001. COMPRA E VENDA. Transmitente: Fulana de "
    "Teste Exemplar; adquirente: Beltrano Modelo. Valor R$ 100.000,00.\n"
    "R-2/45.678 - Em 11 de março de 2001. HIPOTECA em favor do Banco Imaginario S/A.\n"
    "AV-3/45.678 - Em 5 de maio de 2010. CANCELAMENTO da hipoteca objeto do R-2, "
    "por quitaçao.\n"
    "R-4/45.678 - Em 1 de junho de 2015. VENDA E COMPRA. Transmitente: Beltrano "
    "Modelo; adquirente: Cicrana Amostra.\n"
    "R-5/45.678 - Em 1 de junho de 2015. ALIENAÇÃO FIDUCIÁRIA em garantia ao "
    "Banco Ficticio.\n"
    "AV-6/45.678 - Em 2 de julho de 2020. Averba-se a INDISPONIBILIDADE de bens "
    "de Cicrana Amostra.\n"
)

#: (kind, numero) of every act the seed segmenter finds in `TEXTO`, in order.
ESPERADOS = [
    ("abertura", None),
    ("R", 1),
    ("R", 2),
    ("AV", 3),
    ("R", 4),
    ("R", 5),
    ("AV", 6),
]


def transcricao(texto: str) -> Transcription:
    return Transcription(
        pages=(TranscribedPage(number=1, text=texto, source=TextSource.TEXT_LAYER),),
        num_paginas=1,
    )


class StubTranscriber:
    def __init__(self, texto: str) -> None:
        self.texto = texto
        self.calls = 0

    async def transcribe(self, content, *, mimetype=None, filename=None):
        self.calls += 1
        return transcricao(self.texto)


class RecordingDB:
    """The detached half's service-role client: records writes + their scope.

    `MockSupabaseClient` has no column DEFAULTs (a row inserted without an
    org has no org for the org-scoped UPDATE to match) and keeps no update
    history, so the background task's OUTCOME and SCOPE are read here.
    """

    def __init__(self) -> None:
        self.updates: list[dict] = []
        self.update_predicates: list[list[tuple]] = []
        self.inserts: dict[str, list[dict]] = {}
        self._table: str = ""
        self._current: list[tuple] = []

    def table(self, name):
        self._table = name
        self._current = []
        return self

    def select(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    # `documento_retencao.dias_para` (migration 111 — `processar_extracao`
    # stamps `retencao_ate` alongside `texto_extraido`) reads the policy
    # table via `.select(...).is_(...)`. No policy is ever seeded on this
    # double, so `dias_para` reads "no policy" -> `None` -> `retencao_ate`
    # stays `None`, which is the safe default this double's tests rely on.
    def is_(self, _col, _val):
        return self

    def update(self, payload):
        self.updates.append(payload)
        self.update_predicates.append(self._current)
        return self

    def insert(self, payload):
        linhas = payload if isinstance(payload, list) else [payload]
        self.inserts.setdefault(self._table, []).extend(linhas)
        return self

    def eq(self, col, val):
        self._current.append((col, val))
        return self

    def execute(self):
        return type("_R", (), {"data": []})()


def _instalar(dep, valor):
    from app.main import app

    anterior = app.dependency_overrides.get(dep)
    app.dependency_overrides[dep] = valor

    def _restaurar():
        if anterior is None:
            app.dependency_overrides.pop(dep, None)
        else:
            app.dependency_overrides[dep] = anterior

    return _restaurar


@pytest.fixture
def scoped(client):
    return get_matriculas_client()


@pytest.fixture
def fake_storage(client):
    """Mandatory for any route touching storage — `MockSupabaseClient.storage`
    is a bare MagicMock that would 'succeed' against garbage."""
    backend = FakeStorageBackend()
    restaurar = _instalar(get_storage_backend, lambda: backend)
    yield backend
    restaurar()


@pytest.fixture
def fake_extractor(client):
    extractor = FakeMatriculaExtractor()
    restaurar = _instalar(get_matricula_extractor_factory, lambda: lambda _org: extractor)
    yield extractor
    restaurar()


@pytest.fixture
def stub_transcriber(client):
    """Mandatory for any route that schedules a transcription — the real
    factory can reach a vision model."""
    stub = StubTranscriber(TEXTO)
    restaurar = _instalar(get_transcriber_factory, lambda: lambda _org: stub)
    yield stub
    restaurar()


@pytest.fixture
def background_db(client):
    db = RecordingDB()
    restaurar = _instalar(get_background_client, lambda: db)
    yield db
    restaurar()


class FakeNotificationService:
    """Records every `notify_field_conflict` call instead of touching WAHA
    / SMTP / `notification_recipients` — migration 138's DI seam."""

    def __init__(self) -> None:
        self.conflitos: list[dict] = []

    async def notify_field_conflict(self, *, org_id, conflito, cliente_nome):
        self.conflitos.append(
            {"org_id": str(org_id), "conflito": conflito, "cliente_nome": cliente_nome}
        )
        from app.services.notification_service import DispatchOutcome

        return DispatchOutcome()


@pytest.fixture
def fake_notification_service(client):
    from app.modules.matriculas.deps import get_notification_service

    fake = FakeNotificationService()
    restaurar = _instalar(get_notification_service, lambda: fake)
    yield fake
    restaurar()


@pytest.fixture
def com_credencial():
    """The org's vision key resolves. Patches the CREDENTIAL RESOLVER (an
    external config source), not our guard — `check_required_credentials`
    still runs for real."""
    with patch(
        "app.modules.matriculas.service.resolve_credential", return_value="sk-test"
    ):
        yield


# ─── row builders ────────────────────────────────────────────────────────


def registry_row(codigo: str = CODIGO) -> dict:
    return {
        "id": str(uuid4()),
        "org_id": ORG_ID,
        "codigo_canonical": codigo,
        "codigo_display": codigo,
        "ativo_no_vista": True,
        "origem_descoberta": "sync",
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def extracao_row(
    id_: str | None = None,
    *,
    texto: str = TEXTO,
    status: str = "concluida",
    codigo: str | None = CODIGO,
    imovel_documento_id: str | None = None,
    arquivo_origem_id: str | None = None,
    substituida_por: str | None = None,
    possui_marcacao_bruta: bool = False,
    ruido: list | None = None,
) -> dict:
    return {
        "id": id_ or str(uuid4()),
        "org_id": ORG_ID,
        "user_id": "test-user-123",
        "nome_arquivo": "matricula.pdf",
        "tamanho_bytes": 1234,
        "num_paginas": 1,
        "texto_extraido": texto if status == "concluida" else None,
        "status": status,
        "erro_mensagem": None,
        "codigo": codigo,
        "imovel_documento_id": imovel_documento_id,
        "arquivo_origem_id": arquivo_origem_id,
        "substituida_por": substituida_por,
        "possui_marcacao_bruta": possui_marcacao_bruta,
        # Migration 136 — page furniture as offsets into `texto`. `[]` by
        # default (every existing test's fixture stays untouched); a test
        # exercising `_citacao`'s subtraction passes its own spans.
        "ruido": ruido if ruido is not None else [],
        "created_at": "2026-02-01T00:00:00+00:00",
        "updated_at": "2026-02-01T00:00:00+00:00",
    }


def arquivo_row(id_: str | None = None) -> dict:
    """A `matricula_extracao_arquivos` row (migration 135) — the standalone
    shape's retained PDF."""
    aid = id_ or str(uuid4())
    return {
        "id": aid,
        "org_id": ORG_ID,
        "storage_path": f"{ORG_ID}/matriculas/{aid}",
        "nome_original": "matricula-standalone.pdf",
        "mime_type": "application/pdf",
        "tamanho_bytes": 4096,
        "tipo_documento": "matricula",
        "enviado_por": None,
        "deleted_at": None,
        "delete_motivo": None,
        "retencao_ate": None,
        "created_at": "2026-01-02T00:00:00+00:00",
    }


def documento_row(
    id_: str | None = None,
    *,
    tipo_documento: str = "matricula",
    mime_type: str = "application/pdf",
) -> dict:
    did = id_ or str(uuid4())
    return {
        "id": did,
        "org_id": ORG_ID,
        "codigo": CODIGO,
        "storage_path": f"{ORG_ID}/imoveis/{CODIGO}/{did}",
        "nome_original": "matricula-ap1234.pdf",
        "mime_type": mime_type,
        "tamanho_bytes": 2048,
        "tipo_documento": tipo_documento,
        "extracao_status": None,
        "extracao_tentativas": 0,
        "enviado_por": None,
        "deleted_at": None,
        "delete_motivo": None,
        "created_at": "2026-01-02T00:00:00+00:00",
    }


def contrato_row(id_: str | None = None, *, deleted_at: str | None = None) -> dict:
    return {
        "id": id_ or str(uuid4()),
        "org_id": ORG_ID,
        "atendimento_id": str(uuid4()),
        "titulo": "Promessa de Venda e Compra",
        "modelo": "compra_venda",
        "status": "rascunho",
        "origem": "upload",
        "deleted_at": deleted_at,
        "created_at": "2026-03-01T00:00:00+00:00",
    }


def negociacao_row(atendimento_id: str, *, imovel_codigo: str | None = CODIGO) -> dict:
    """A minimal `atendimento_negociacao` row — only the column migration 111's
    `_exigir_codigo_compativel` reads (109's contract-selection tests need one
    per contrato so a matching `imovel_codigo` isn't itself the thing under
    test)."""
    return {
        "atendimento_id": atendimento_id,
        "org_id": ORG_ID,
        "imovel_codigo": imovel_codigo,
    }


def seed(
    scoped,
    *,
    registry=None,
    extracoes=None,
    atos=None,
    abertura_blocos=None,
    documentos=None,
    arquivos=None,
    dados=None,
    contratos=None,
    selecao=None,
    negociacoes=None,
    detalhes=None,
    permutas=None,
    qualificacoes=None,
    clientes=None,
) -> None:
    """Every table this flow reads, set explicitly — an unset table would
    carry rows over from whatever an earlier test seeded."""
    scoped.set_table_data("imovel_registry", registry or [])
    scoped.set_table_data("matricula_extracoes", extracoes or [])
    scoped.set_table_data("matricula_atos", atos or [])
    # Migration 136 — the abertura's typed sub-spans.
    scoped.set_table_data("matricula_abertura_blocos", abertura_blocos or [])
    scoped.set_table_data("matricula_ato_detalhes", detalhes or [])
    # Migration 137 — party qualification suggestions + the clientes they
    # may match against.
    scoped.set_table_data("matricula_qualificacoes", qualificacoes or [])
    scoped.set_table_data("clientes", clientes or [])
    # Migration 138 — admin-adjudicated field conflicts.
    scoped.set_table_data("cliente_campo_conflitos", [])
    scoped.set_table_data("permuta_ativos", permutas or [])
    scoped.set_table_data("imovel_documentos", documentos or [])
    scoped.set_table_data("imovel_documento_acessos", [])
    # Migration 135 — the standalone shape's retained-PDF table.
    scoped.set_table_data("matricula_extracao_arquivos", arquivos or [])
    scoped.set_table_data("imovel_dados", dados or [])
    scoped.set_table_data("atendimento_contratos", contratos or [])
    scoped.set_table_data("atendimento_contrato_matricula_atos", selecao or [])
    # 🔴 Defaults to one negociacao row PER CONTRATO, `imovel_codigo=CODIGO` —
    # migration 111's `definir_selecao` now refuses a selection whose
    # extração doesn't match the deal's imóvel, and most of this suite's
    # fixtures build a contrato + extração that agree on `CODIGO` already.
    # Pass `negociacoes=[]` explicitly to test the refusal itself.
    if negociacoes is None:
        negociacoes = [
            negociacao_row(c["atendimento_id"]) for c in (contratos or [])
        ]
    scoped.set_table_data("atendimento_negociacao", negociacoes)
