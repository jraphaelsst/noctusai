"""Provenance construction — contract §B.0/§D.

Every `KnowledgeStore` write takes a `Provenance` (contract §A.11). This
module is the ONE place that decides which shape it takes, based on the
resolved `AuthContext`:

  - `caller_kind == "user"` (SSO):              human, `user_id=ctx.user_id`
  - `caller_kind == "product"` + `human_personal`:
                                                  human, `user_id=ctx.minted_by`
                                                  (no assertion — §B.0 exception)
  - `caller_kind == "product"` (else):           agent, `user_id=approved_by`,
                                                  `agent_id=sub`, `approval_id=jti`
                                                  (§D verification REQUIRED)
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from noctusai_lib.api.auth.session.types import AuthContext

from app.auth.assertion import (
    ApproverNotAllowedError,
    AssertionInvalidError,
    verify_assertion,
)
from app.dependencies import get_core_client
from app.knowledge import Provenance


async def build_write_provenance(
    ctx: AuthContext,
    request: Request,
    *,
    keys: list[str],
    motivo: str | None = None,
) -> Provenance:
    """Build the `Provenance` for a write route.

    Verifies the `X-Approval-Assertion` header (§D) when the caller is a
    non-`human_personal` product token — raises `HTTPException(403)`
    (`assertion_invalid` / `approver_not_allowed`) when it's missing or
    invalid. SSO users and `human_personal` tokens need no assertion.

    `keys` (the configured `approval_assertion_secrets` list) is an
    explicit parameter, not a module-level `settings` read — the DI seam
    a test overrides via
    `app.dependency_overrides[get_approval_assertion_keys]` instead of
    `monkeypatch.setattr(settings, "approval_assertion_secrets", ...)`
    (which trips `check_no_self_monkeypatch` — see
    `app.dependencies.get_approval_assertion_keys`'s own docstring; the
    social-wiring `get_settings` seam is the sibling pattern for the
    same rationale applied to the whole settings object).
    """
    if ctx.caller_kind == "user":
        return Provenance(author_kind="human", user_id=ctx.user_id, motivo=motivo)

    if ctx.human_personal:
        return Provenance(author_kind="human", user_id=ctx.minted_by, motivo=motivo)

    raw_body = await request.body()
    try:
        verified = verify_assertion(
            request.headers.get("X-Approval-Assertion"),
            keys=keys,
            ctx_org_id=ctx.org_id,
            ctx_principal_agent_id=ctx.principal_agent_id,
            method=request.method,
            path=request.url.path,
            raw_body=raw_body,
            get_core_client=get_core_client,
        )
    except AssertionInvalidError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "Aprovação inválida — peça de novo.",
                "code": "assertion_invalid",
            },
        ) from exc
    except ApproverNotAllowedError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "detail": "Quem aprovou não tem permissão para esta ação.",
                "code": "approver_not_allowed",
            },
        ) from exc

    return Provenance(
        author_kind="agent",
        user_id=verified.approved_by,
        agent_id=verified.agent_id,
        approval_id=verified.jti,
        motivo=motivo,
    )


__all__ = ["build_write_provenance"]
