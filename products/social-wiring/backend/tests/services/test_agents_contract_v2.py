"""Contract test: what SW sends to and reads from agents validates against agents' OWN generated JSON Schema.

julia-v2 CONTRACT 10.3: agents exports `ChannelTurnRequest` / `ChannelTurnResponse` / `operacional` to
`products/agents/backend/contracts/channels.v2.json` (generated, with a drift check on its side); SW validates every request
it builds and parses fixture responses against that file. The file is the ARBITER: when SW and the file disagree, SW is wrong.

NOC-REMEDIATE[julia-v2-agents-contract-schema]: `channels.v2.json` does not exist yet (A-RT publishes it with the channel
runtime rewire). Until it does, every test here SKIPS -- LOUDLY: the skip reason carries this marker, `pytest -rs` prints it and
`noctus.dev.scan_remediation_markers` lists it. When the file lands, the first run either passes (the Fake + builders already
follow section 8.1) or names the exact drift. — 2026-10-19
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.clients.agents import (
    STATUS_RESPONDEU,
    STATUS_SEM_ATENDIMENTO,
    TurnMessage,
    TurnRequest,
    parse_turn_result,
)
from app.services import julia_contexto_service as ctxsvc

REPO = Path(__file__).resolve().parents[5]
#: `AGENTS_CONTRACT_SCHEMA` points the test at another copy of the file (e.g. a peer worktree's, before it is merged).
SCHEMA_PATH = Path(os.environ.get("AGENTS_CONTRACT_SCHEMA") or REPO / "products" / "agents" / "backend" / "contracts" / "channels.v2.json")
AT = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
LEAD = "22222222-2222-4222-8222-222222222222"
THREAD = "11111111-1111-4111-8111-111111111111"

_MISSING = (
    "NOC-REMEDIATE[julia-v2-agents-contract-schema]: products/agents/backend/contracts/channels.v2.json is missing "
    "(A-RT publishes it) -- the SW <-> agents wire is NOT contract-verified until it lands"
)
pytestmark = pytest.mark.skipif(not SCHEMA_PATH.exists(), reason=_MISSING)
jsonschema = pytest.importorskip("jsonschema")


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _definition(root: dict[str, Any], *names: str) -> dict[str, Any]:
    """A sub-schema by any of `names`. agents' file maps each model name to a JSON Schema that carries its own `$defs`
    (`{"ChannelTurnRequest": {...}, "ChannelTurnResponse": {...}, "versao": "channels.v2"}`); a single-root layout
    (`$defs` at the top) is accepted too. A schema file with none of them is a LOUD failure, never a pass."""
    for name in names:
        if isinstance(root.get(name), dict):
            return root[name]
        for bucket in ("$defs", "definitions"):
            if name in (root.get(bucket) or {}):
                return {"$ref": f"#/{bucket}/{name}", "$defs": root.get("$defs", {}), "definitions": root.get("definitions", {})}
        for top in root.values():  # a model nested in a top-level schema's own `$defs` (e.g. ChannelContexto)
            if isinstance(top, dict) and name in (top.get("$defs") or {}):
                return {"$ref": f"#/$defs/{name}", "$defs": top["$defs"]}
    pytest.fail(f"channels.v2.json has none of {names} -- cannot verify SW's wire against it")


def _validate(instance: Any, sub: dict[str, Any]) -> None:
    jsonschema.Draft202012Validator(sub).validate(instance)


def _contexto() -> dict[str, Any]:
    return {
        "hash": "a" * 64, "agora": AT.isoformat(), "fuso": ctxsvc.FUSO,
        "estado": {
            "interacao_id": "33333333-3333-4333-8333-333333333333", "encerrado": False, "atendente_nome": "Carlos",
            "origem": {"canal_origem": "meta_ads", "codigo_imovel_campanha": "A123"},
            "credito": {"ativo": True, "consentimento": None},
        },
        "capacidades": {"ferramentas_sw": True},
    }


def _contexto_reengajamento(tier: str, **extra: Any) -> dict[str, Any]:
    ctx = _contexto()
    ctx["estado"] = {**ctx["estado"], "reengajamento": tier, **extra}
    return ctx


def _request(**over: Any) -> TurnRequest:
    base: dict[str, Any] = dict(
        agent_key="julia", connection_id="44444444-4444-4444-8444-444444444444", chat_id="5511900000000@c.us",
        phone_e164="+5511900000000", display_name="Ana", lead_ref=LEAD, contexto=_contexto(),
        messages=(TurnMessage(texto="oi", provider_message_id="m1", at=AT),),
    )
    base.update(over)
    return TurnRequest(**base)


class TestRequestsValidate:
    def test_a_lead_message_turn(self):
        _validate(_request().to_wire(), _definition(_schema(), "ChannelTurnRequest", "TurnRequest", "request"))

    def test_a_reengagement_turn_has_no_message(self):
        wire = _request(messages=(), gatilho="reengajamento", contexto=_contexto_reengajamento("horas")).to_wire()
        _validate(wire, _definition(_schema(), "ChannelTurnRequest", "TurnRequest", "request"))

    def test_a_regua_reengagement_with_the_base_text(self):
        wire = _request(messages=(), gatilho="reengajamento",
                        contexto=_contexto_reengajamento("regua", reescrever=True, texto_base="Oi, ainda procura imóvel?",
                                                         tentativa=2)).to_wire()
        _validate(wire, _definition(_schema(), "ChannelTurnRequest", "TurnRequest", "request"))

    def test_the_contexto_builder_output_validates(self):
        """The REAL builder (`julia_contexto_service.montar`) on a contato, not a hand-written dict."""
        from tests.support.julia_world import CONNECTION_ID, LEAD_CHAT, ORG_ID, World
        from app.services import julia_contatos_service as contatos

        w = World()
        w.seed_connection()
        c = contatos.obter_ou_criar_contato(w.sw, org_id=ORG_ID, connection_id=CONNECTION_ID, chat_id=LEAD_CHAT)
        c, _ = contatos.registrar_inbound(w.sw, c)
        contexto = ctxsvc.montar(w.sw, ORG_ID, c, interacao=contatos.abrir_interacao(w.sw, ORG_ID, c))
        contexto["estado"]["interacao_id"] = "33333333-3333-4333-8333-333333333333"  # the mock DB mints non-UUID ids
        _validate(contexto, _definition(_schema(), "ChannelContexto", "Contexto", "contexto"))

    def test_every_key_SW_sends_is_one_the_schema_declares(self):
        """The builders' key sets are SUBSETS of agents' closed schema (agents also tolerates retired v1 keys SW never sends)."""
        root = _schema()

        def props(*names: str) -> set[str]:
            sub = _definition(root, *names)
            defs = {**(sub.get("definitions") or {}), **(sub.get("$defs") or {})}
            return set((defs.get(names[0]) or sub).get("properties") or sub.get("properties") or {})

        contexto_props = set(_definition(root, "ChannelTurnRequest")["$defs"]["ChannelContexto"]["properties"])
        estado_props = set(_definition(root, "ChannelTurnRequest")["$defs"]["ContextoEstado"]["properties"])
        assert set(ctxsvc.CONTEXTO_CHAVES) <= contexto_props
        assert set(ctxsvc.ESTADO_CHAVES_AGENTS) <= estado_props
        assert {"conhecimento_md", "perguntas", "ferramentas", "acoes"}.isdisjoint(ctxsvc.CONTEXTO_CHAVES)


#: Statuses SW's parser tolerates that agents' schema does NOT list: `controle_indisponivel` is an HTTP 503 in agents (the
#: control could not be read), SW also accepts it as a status string defensively -- either way nothing is sent.
FORA_DO_CONTRATO = frozenset({"controle_indisponivel"})


def _status_do_schema() -> list[str]:
    resp = _definition(_schema(), "ChannelTurnResponse", "TurnResponse", "response")
    return list(resp["properties"]["status"]["enum"])


class TestResponsesValidate:
    def test_every_status_agents_can_answer_is_one_SW_understands(self):
        assert set(_status_do_schema()) <= set(STATUS_RESPONDEU) | set(STATUS_SEM_ATENDIMENTO)

    def test_the_only_statuses_SW_adds_are_the_declared_tolerated_ones(self):
        assert (set(STATUS_RESPONDEU) | set(STATUS_SEM_ATENDIMENTO)) - set(_status_do_schema()) == FORA_DO_CONTRATO

    @pytest.mark.parametrize("status", STATUS_RESPONDEU)
    def test_served_response(self, status):
        body = {
            "thread_id": THREAD, "conversation_id": THREAD, "status": status, "reply": {"partes": ["Oi!"]},
            "actions": [{"seq": 1, "type": "handoff", "motivo_codigo": "pedido_humano", "motivo": "quer humano"}],
            "participante": {"agent_key": "julia", "estado": "ativo"},
            "qualificacao": {"versao": "imob-lead@3", "estagio": "qualificado", "score": 61, "faltando": ["prazo_decisao"]},
            "conformidade": {"violacoes": []}, "usage": {"custo_usd": 0.01, "tokens_entrada": 10, "tokens_saida": 5},
        }
        _validate(body, _definition(_schema(), "ChannelTurnResponse", "TurnResponse", "response"))
        assert parse_turn_result(body).status == status  # and SW's own parser reads what the schema allows

    @pytest.mark.parametrize("status", sorted(set(STATUS_SEM_ATENDIMENTO) - FORA_DO_CONTRATO))
    def test_not_served_response(self, status):
        body = {"status": status, "reply": {"partes": []}, "actions": []}
        _validate(body, _definition(_schema(), "ChannelTurnResponse", "TurnResponse", "response"))
        assert not parse_turn_result(body).atendeu

    def test_lead_pronto_action(self):
        body = {
            "thread_id": THREAD, "conversation_id": THREAD, "status": "concluido", "reply": {"partes": []},
            "actions": [{"seq": 1, "type": "lead_pronto", "estagio": "pronto_para_corretor", "score": 78,
                         "valores": {"operacao": "compra"}, "imoveis_gostou": ["A123"], "intencoes_visita": ["A123"]},
                        {"seq": 2, "type": "intencao_visita", "codigo": "A123", "preferencia_horario": None}],
        }
        _validate(body, _definition(_schema(), "ChannelTurnResponse", "TurnResponse", "response"))
        assert [a.type for a in parse_turn_result(body).julia_actions] == ["lead_pronto", "intencao_visita"]
