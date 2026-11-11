"""Shared fakes of the classifier tests: a Fake prompt registry row, the REAL seed LLM seam over a registered Fake
provider (so the budget, the spend guard and the usage ledger all run for real), and an in-memory intake store that
models migration 017's `record_classification` contract (unique key, one-transaction outcome change)."""
from __future__ import annotations

import uuid
from typing import Optional

import pytest

from noctusai_lib.integrations.llm import InMemoryUsageSink, LLMConfig, configure_llm, register
from noctusai_lib.integrations.llm.attribution import get_default_product, set_default_product
from noctusai_lib.integrations.llm.client import _reset_for_testing
from noctusai_lib.integrations.llm.providers import FakeProvider
from noctusai_lib.integrations.llm.spend_guard import configure_spend_guard
from noctusai_lib.integrations.prompt_registry import FakePromptRegistry, PromptEntry

from app.shadow import classificador as clf

VENDOR = "assistant-fake"
MODELO = "claude-haiku-5-5"
PROMPT = "PROMPT DE TESTE (fixture; o prompt real vive no registro)"
ORG = "11111111-1111-1111-1111-111111111111"


def resposta(sim: bool, motivo: Optional[str] = None, confianca: float = 0.9) -> str:
    motivo = motivo or ("propoe_horario" if sim else "sem_agendamento")
    return '{"is_scheduling": %s, "confidence": %s, "reason_code": "%s"}' % ("true" if sim else "false", confianca, motivo)


@pytest.fixture
def registro():
    return FakePromptRegistry([PromptEntry(
        chave=clf.CHAVE, nome="t", descricao="t", vendor=VENDOR, modelo=MODELO, prompt=PROMPT,
    )])


@pytest.fixture
def seam():
    """`seam(respostas)` -> the FakeProvider behind the real `chat_completion`; spend guard OFF unless a test sets it."""
    previous_product = get_default_product()
    providers: list[FakeProvider] = []

    def _make(respostas=(), usage=None):
        fake = FakeProvider(chat_responses=list(respostas), chat_usage=usage,
                            usage_provider="anthropic" if usage else None)
        register(VENDOR, lambda: fake)
        configure_llm(LLMConfig(key_provider=lambda p, org_id=None: "k", usage_sink=InMemoryUsageSink()))
        set_default_product("assistant")
        providers.append(fake)
        return fake

    yield _make
    _reset_for_testing()
    configure_spend_guard(reader=None, limits={})
    set_default_product(previous_product)


class FakeIntakeDb:
    """In-memory `IntakeDb`. Rows carry identifiers on purpose: the classifier must forward none of them."""

    def __init__(self):
        self.rows: dict[str, dict] = {}
        self.outputs: dict[tuple, dict] = {}
        self.desfechos: list[tuple] = []
        self.registros: list[dict] = []
        self.ler_colunas: list[str] = []

    def add(self, body: Optional[str], outcome: str = "pending") -> str:
        i = str(uuid.uuid4())
        self.rows[i] = {"id": i, "org_id": ORG, "outcome": outcome, "body": body,
                        "chat_ref": "ref-" + i, "waha_message_id": "w-" + i, "phone": "5511988887777"}
        return i

    def ler(self, intake_id):
        r = self.rows.get(intake_id)
        return None if r is None else {k: r[k] for k in ("id", "org_id", "outcome", "body")}

    def ja_classificado(self, intake_id, prompt_version, modelo):
        return (intake_id, prompt_version, modelo) in self.outputs

    def desfecho(self, intake_id, outcome, motivo):
        self.desfechos.append((intake_id, outcome, motivo))
        self.rows[intake_id]["outcome"] = outcome
        if outcome in ("skipped", "skipped_excluded"):  # 017: skipped_budget keeps the text
            self.rows[intake_id]["body"] = None

    def registrar(self, intake_id, r, *, primeira):
        chave = (intake_id, r.prompt_version, r.modelo)
        novo = chave not in self.outputs
        if novo:
            self.outputs[chave] = {"label": "agendamento" if r.classificacao.is_scheduling else "outro",
                                   "metadata": r.metadata("primeira" if primeira else "replay")}
        self.registros.append({"intake_id": intake_id, "inserted": novo, "primeira": primeira})
        if (primeira and self.rows[intake_id]["outcome"] in ("pending", "failed")) \
                or self.rows[intake_id]["outcome"] == "skipped_budget":
            self.rows[intake_id]["outcome"] = "classified"
        return {"inserted": novo}


@pytest.fixture
def db():
    return FakeIntakeDb()
