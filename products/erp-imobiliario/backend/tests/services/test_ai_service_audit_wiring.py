"""ai_service._dispatch_chat — audit row writes on every chat dispatch.

Verifies the seam wired in LLM-ERP rollout Step B: every ERP chat
dispatch goes through `_dispatch_chat(...)`, which builds an
`AuditRecord` and calls `get_audit_writer()(record)` before returning
(or before re-raising on failure).

The seed `make_audit_writer` factory + the `ToolCallAudit` ORM are
covered by `tests/services/test_audit_hook.py`. THIS file covers the
service-side wiring — that the helper actually writes the row + carries
the right tool_name + status — by replacing `get_audit_writer` with a
list-collector spy.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_dispatch_chat_writes_audit_row_on_success():
    """Happy path: chat_completion returns OK → one audit row written
    with status='success' + arguments + result['content']."""
    from app.services import ai_service

    collected: list = []

    def fake_writer():
        def write(record):
            collected.append(record)
        return write

    with patch.object(ai_service, "chat_completion", new=AsyncMock(return_value="reply")), \
         patch.object(ai_service, "get_audit_writer", new=fake_writer):
        result = await ai_service._dispatch_chat(
            tool_name="erp.lead_score",
            messages=[{"role": "user", "content": "hi"}],
            arguments={"foo": "bar"},
            user_id=7,
            model="gpt-4o-mini",
        )

    assert result == "reply"
    assert len(collected) == 1
    rec = collected[0]
    assert rec.tool_name == "erp.lead_score"
    assert rec.status == "success"
    assert rec.arguments == {"foo": "bar"}
    assert rec.result == {"content": "reply"}
    assert rec.user_id == 7
    assert rec.error is None


@pytest.mark.asyncio
async def test_dispatch_chat_writes_audit_row_on_failure_and_reraises():
    """On chat_completion exception: one audit row with status='failure'
    + error captured, AND the exception is re-raised so callers (e.g.
    draft_follow_up) keep their own fallback shape."""
    from app.services import ai_service

    collected: list = []

    def fake_writer():
        def write(record):
            collected.append(record)
        return write

    boom = RuntimeError("upstream LLM 503")

    with patch.object(ai_service, "chat_completion", new=AsyncMock(side_effect=boom)), \
         patch.object(ai_service, "get_audit_writer", new=fake_writer):
        with pytest.raises(RuntimeError, match="upstream LLM 503"):
            await ai_service._dispatch_chat(
                tool_name="erp.imovel_description",
                messages=[{"role": "user", "content": "x"}],
                arguments={"tipo": "apartamento"},
            )

    assert len(collected) == 1
    rec = collected[0]
    assert rec.tool_name == "erp.imovel_description"
    assert rec.status == "failure"
    assert rec.arguments == {"tipo": "apartamento"}
    assert rec.result is None
    assert "upstream LLM 503" in (rec.error or "")


@pytest.mark.asyncio
async def test_dispatch_chat_audit_writer_exception_does_not_break_dispatch():
    """If the audit writer itself raises (corrupt session, e.g.), the
    underlying chat result still returns — audit failures are best-effort
    and never escalate."""
    from app.services import ai_service

    def fake_writer():
        def write(record):
            raise RuntimeError("audit DB down")
        return write

    with patch.object(ai_service, "chat_completion", new=AsyncMock(return_value="ok")), \
         patch.object(ai_service, "get_audit_writer", new=fake_writer):
        result = await ai_service._dispatch_chat(
            tool_name="erp.suggest_price",
            messages=[{"role": "user", "content": "x"}],
        )

    # Audit failed but the dispatch still succeeded — best-effort contract.
    assert result == "ok"


@pytest.mark.asyncio
async def test_generate_description_emits_audit_row():
    """Smoke through the public `generate_description` entry: one audit
    row with the matching tool_name lands."""
    from app.services import ai_service

    collected: list = []

    def fake_writer():
        def write(record):
            collected.append(record)
        return write

    with patch.object(
        ai_service,
        "chat_completion",
        new=AsyncMock(return_value="TÍTULO: Apto bonito\nDESCRIÇÃO:\nÓtimo."),
    ), patch.object(ai_service, "get_audit_writer", new=fake_writer):
        await ai_service.generate_description(
            {"tipo_imovel": "Apartamento", "cidade": "SP", "bairro": "Pinheiros"}
        )

    assert any(r.tool_name == "erp.imovel_description" for r in collected)
