"""Contract §E.10 — the escrita handler trusts only the stored approval
row (security review, 2026-09-14).

Every test here calls ``_escrita``'s handler DIRECTLY (via the
``SdkMcpTool.handler`` the ``tool()`` decorator returns) — the exact
"stub CLI / direct handler calls" shape the contract's §E.10 test list
asks for. Never monkeypatches ``app.runtime.tools`` or the store: every
scenario is set up by calling the real ``FakeApprovalStore`` API.
"""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import jwt
import pytest

from app.runtime.academia_api import FakeAcademiaApi
from app.runtime.tools import _escrita
from app.runtime.types import TurnContext
from app.stores._util import utcnow
from app.stores.approvals import FakeApprovalStore

pytestmark = pytest.mark.asyncio

FULL_NAME = "mcp__academia__kb_escrever"
SECRET = "s3cr3t"
AUD = "academia-de-reciclagem"


def _ctx(**overrides) -> TurnContext:
    defaults = dict(
        org_id=uuid4(),
        conversation_id=uuid4(),
        requested_by=uuid4(),
        instance_id="inst-1",
        sdk_session_id=None,
    )
    defaults.update(overrides)
    return TurnContext(**defaults)


def _handler(*, academia_api, ctx, approvals, use_window_seconds=120, agent_id=None):
    """One escrita tool, wired exactly like ``kb_escrever`` (contract §C):
    ``PUT /api/kb/{slug}`` with ``{corpo_md, motivo}``."""
    sdk_tool = _escrita(
        "kb_escrever",
        "desc",
        {"type": "object", "properties": {}, "additionalProperties": True},
        academia_api=academia_api,
        agent_id=agent_id or uuid4(),
        secret=SECRET,
        aud=AUD,
        ctx=ctx,
        approvals=approvals,
        use_window_seconds=use_window_seconds,
        method_fn=lambda a: "PUT",
        path_fn=lambda a: f"/api/kb/{a.get('slug', 'x')}",
        body_fn=lambda a: {"corpo_md": a.get("corpo_md"), "motivo": a.get("motivo", "m")},
    )
    return sdk_tool.handler


def _seed(
    approvals: FakeApprovalStore,
    ctx: TurnContext,
    tool_input: dict,
    *,
    decision: str = "aprovada",
    tool_name: str = FULL_NAME,
    conversation_id=None,
    requested_by=None,
    instance_id=None,
    decided_at=None,
):
    record = approvals.create_pending(
        ctx.org_id,
        conversation_id or ctx.conversation_id,
        tool_name,
        tool_input,
        "resumo",
        instance_id or ctx.instance_id,
        requested_by or ctx.requested_by,
    )
    if decision == "expirada":
        approvals.expire_one(record.id)
    elif decision in ("aprovada", "negada"):
        approvals.decide(ctx.org_id, record.id, decision == "aprovada", uuid4())
    if decided_at is not None:
        approvals._rows[record.id]["decided_at"] = decided_at
    return approvals.get(ctx.org_id, record.id)


def _error_code(result: dict) -> str:
    payload = _payload(result)
    return payload["error"]["code"]


def _payload(result: dict) -> dict:
    import json

    return json.loads(result["content"][0]["text"])


class TestApprovalMissing:
    async def test_no_approval_field_refuses_approval_missing(self):
        approvals = FakeApprovalStore()
        ctx = _ctx()
        handler = _handler(academia_api=FakeAcademiaApi(), ctx=ctx, approvals=approvals)

        result = await handler({"slug": "x", "corpo_md": "y", "motivo": "m"})

        assert _error_code(result) == "approval_missing"

    async def test_unparseable_approval_id_refuses_approval_missing(self):
        approvals = FakeApprovalStore()
        ctx = _ctx()
        handler = _handler(academia_api=FakeAcademiaApi(), ctx=ctx, approvals=approvals)

        result = await handler(
            {"slug": "x", "corpo_md": "y", "motivo": "m", "_approval": {"approval_id": "not-a-uuid"}}
        )

        assert _error_code(result) == "approval_missing"


class TestForgedOrWrongStateApproval:
    async def test_forged_approval_id_refuses_approval_invalid_no_academia_call(self):
        approvals = FakeApprovalStore()
        academia_api = FakeAcademiaApi()
        ctx = _ctx()
        handler = _handler(academia_api=academia_api, ctx=ctx, approvals=approvals)

        result = await handler(
            {
                "slug": "x",
                "corpo_md": "y",
                "motivo": "m",
                "_approval": {"approval_id": str(uuid4())},
            }
        )

        assert _error_code(result) == "approval_invalid"
        assert academia_api.calls == []

    @pytest.mark.parametrize("decision", ["pendente", "negada", "expirada"])
    async def test_non_approved_decision_refuses_approval_invalid(self, decision):
        approvals = FakeApprovalStore()
        academia_api = FakeAcademiaApi()
        ctx = _ctx()
        tool_input = {"slug": "x", "corpo_md": "y", "motivo": "m"}
        approval = _seed(approvals, ctx, tool_input, decision=decision)
        handler = _handler(academia_api=academia_api, ctx=ctx, approvals=approvals)

        result = await handler({**tool_input, "_approval": {"approval_id": str(approval.id)}})

        assert _error_code(result) == "approval_invalid"
        assert academia_api.calls == []


class TestBodyMismatch:
    async def test_approve_body_a_send_body_b_refuses_approval_invalid(self):
        approvals = FakeApprovalStore()
        academia_api = FakeAcademiaApi()
        ctx = _ctx()
        approved_input = {"slug": "x", "corpo_md": "TEXTO APROVADO", "motivo": "m"}
        approval = _seed(approvals, ctx, approved_input, decision="aprovada")
        handler = _handler(academia_api=academia_api, ctx=ctx, approvals=approvals)

        sent_input = {"slug": "x", "corpo_md": "TEXTO TROCADO", "motivo": "m"}
        result = await handler({**sent_input, "_approval": {"approval_id": str(approval.id)}})

        assert _error_code(result) == "approval_invalid"
        assert academia_api.calls == []


class TestCrossFieldMismatch:
    async def test_different_conversation_refuses_approval_invalid(self):
        approvals = FakeApprovalStore()
        ctx = _ctx()
        tool_input = {"slug": "x", "corpo_md": "y", "motivo": "m"}
        approval = _seed(approvals, ctx, tool_input, decision="aprovada", conversation_id=uuid4())
        handler = _handler(academia_api=FakeAcademiaApi(), ctx=ctx, approvals=approvals)

        result = await handler({**tool_input, "_approval": {"approval_id": str(approval.id)}})

        assert _error_code(result) == "approval_invalid"

    async def test_different_tool_refuses_approval_invalid(self):
        approvals = FakeApprovalStore()
        ctx = _ctx()
        tool_input = {"slug": "x", "corpo_md": "y", "motivo": "m"}
        approval = _seed(
            approvals, ctx, tool_input, decision="aprovada", tool_name="mcp__academia__kb_mover"
        )
        handler = _handler(academia_api=FakeAcademiaApi(), ctx=ctx, approvals=approvals)

        result = await handler({**tool_input, "_approval": {"approval_id": str(approval.id)}})

        assert _error_code(result) == "approval_invalid"

    async def test_different_instance_refuses_approval_invalid(self):
        approvals = FakeApprovalStore()
        ctx = _ctx()
        tool_input = {"slug": "x", "corpo_md": "y", "motivo": "m"}
        approval = _seed(
            approvals, ctx, tool_input, decision="aprovada", instance_id="some-other-instance"
        )
        handler = _handler(academia_api=FakeAcademiaApi(), ctx=ctx, approvals=approvals)

        result = await handler({**tool_input, "_approval": {"approval_id": str(approval.id)}})

        assert _error_code(result) == "approval_invalid"

    async def test_different_requester_refuses_approval_invalid(self):
        approvals = FakeApprovalStore()
        ctx = _ctx()
        tool_input = {"slug": "x", "corpo_md": "y", "motivo": "m"}
        approval = _seed(approvals, ctx, tool_input, decision="aprovada", requested_by=uuid4())
        handler = _handler(academia_api=FakeAcademiaApi(), ctx=ctx, approvals=approvals)

        result = await handler({**tool_input, "_approval": {"approval_id": str(approval.id)}})

        assert _error_code(result) == "approval_invalid"


class TestStaleness:
    async def test_stale_decided_at_refuses_approval_invalid(self):
        approvals = FakeApprovalStore()
        ctx = _ctx()
        tool_input = {"slug": "x", "corpo_md": "y", "motivo": "m"}
        stale = utcnow() - timedelta(seconds=200)
        approval = _seed(approvals, ctx, tool_input, decision="aprovada", decided_at=stale)
        handler = _handler(
            academia_api=FakeAcademiaApi(), ctx=ctx, approvals=approvals, use_window_seconds=120
        )

        result = await handler({**tool_input, "_approval": {"approval_id": str(approval.id)}})

        assert _error_code(result) == "approval_invalid"


class TestReplay:
    async def test_replay_of_a_consumed_approval_refuses_approval_used(self):
        approvals = FakeApprovalStore()
        academia_api = FakeAcademiaApi()
        ctx = _ctx()
        tool_input = {"slug": "x", "corpo_md": "y", "motivo": "m"}
        approval = _seed(approvals, ctx, tool_input, decision="aprovada")
        handler = _handler(academia_api=academia_api, ctx=ctx, approvals=approvals)
        args = {**tool_input, "_approval": {"approval_id": str(approval.id)}}

        first = await handler(args)
        assert "error" not in _payload(first)
        assert len(academia_api.calls) == 1

        second = await handler(args)
        assert _error_code(second) == "approval_used"
        assert len(academia_api.calls) == 1  # never called academia a second time


class TestHappyPath:
    async def test_happy_path_calls_academia_once_with_stored_decided_by(self):
        approvals = FakeApprovalStore()
        academia_api = FakeAcademiaApi()
        ctx = _ctx()
        tool_input = {"slug": "x", "corpo_md": "y", "motivo": "m"}
        approval = _seed(approvals, ctx, tool_input, decision="aprovada")
        decided_by = approvals.get(ctx.org_id, approval.id).decided_by
        agent_id = uuid4()
        handler = _handler(
            academia_api=academia_api, ctx=ctx, approvals=approvals, agent_id=agent_id
        )

        result = await handler({**tool_input, "_approval": {"approval_id": str(approval.id)}})

        assert "error" not in _payload(result)
        assert len(academia_api.calls) == 1
        call = academia_api.calls[0]
        assert call["method"] == "PUT"
        assert call["path"] == "/api/kb/x"
        claims = jwt.decode(
            call["assertion"], SECRET, algorithms=["HS256"], audience=AUD, issuer="agents"
        )
        assert claims["approved_by"] == str(decided_by)
        assert claims["jti"] == str(approval.id)
        assert claims["sub"] == str(agent_id)

        # The approval is now consumed — a second identical call refuses.
        consumed_row = approvals.get(ctx.org_id, approval.id)
        assert consumed_row.consumed_at is not None
