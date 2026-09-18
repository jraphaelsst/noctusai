"""``noctus.dev.d4sign_contract_verify`` — agent-callable D4Sign contract harness.

Wraps ``noctusai_lib.testing.d4sign_harness.run_contract_harness`` so an
agent (or a human) can run the sandbox-or-real verification pass without a
shell round-trip — the same "runnable automation → MCP tool" posture as
``noctus.dev.sso_smoke`` / ``noctus.dev.sso_cors_smoke``, applied to the
signature-integration seed module (``projects/signature-integration-
CONTRACT.md`` §1.6).

``mode="sandbox"`` (default) needs no credentials and answers every marker
against the local ``D4SignSandbox``. ``mode="real"`` resolves D4Sign
credentials via the seed's ``resolve_credential`` chain (org_settings →
platform_settings → env) and, when configured, drives an actual D4Sign
account — never silently falling back to the sandbox when credentials are
missing; every marker instead reports ``not_configured``, mirroring
``sso_smoke``'s honesty contract.
"""
from __future__ import annotations

from typing import Any


def d4sign_contract_verify(
    mode: str = "sandbox",
    org_id: str | None = None,
    captured_webhook_path: str | None = None,
) -> dict[str, Any]:
    """Run the 6-marker D4Sign contract-verification harness.

    Args:
        mode: ``"sandbox"`` (default, no credentials needed) or ``"real"``
            (drives an actual D4Sign account resolved via ``org_id``).
        org_id: forwarded to the credential resolver for org-scoped lookup
            (``mode="real"`` only).
        captured_webhook_path: path to a JSON file ``{"body": "...",
            "headers": {...}}`` holding a REAL webhook D4Sign delivered —
            only consulted for the ``d4sign-webhook-type-post`` marker in
            ``mode="real"`` (no D4Sign API can trigger a live test
            delivery; see the harness module docstring).

    Returns:
        ``{ok, mode, generated_at, markers: [...], all_verified_live}``.
        ``ok`` is ``True`` iff mode="sandbox" ran cleanly OR mode="real"
        found zero ``contradicted_live`` markers — it is NEVER ``True`` on
        ``not_configured`` (never a faked pass, same contract as
        ``noctus.dev.sso_smoke``).
    """
    if mode not in ("sandbox", "real"):
        raise ValueError(f"mode must be 'sandbox' or 'real', got {mode!r}")

    # Imported lazily: this module must stay importable (and its `register`
    # cheap) without pulling httpx/starlette/the whole signature package at
    # server-import time — same rationale as every other lazy `from .real
    # import D4SignAdapter` in this codebase.
    from noctusai_lib.testing.d4sign_harness import run_contract_harness_sync

    report = run_contract_harness_sync(
        mode=mode,  # type: ignore[arg-type]
        org_id=org_id,
        captured_webhook_path=captured_webhook_path,
    )

    contradicted = [m.marker for m in report.markers if m.status == "contradicted_live"]
    not_configured = [m.marker for m in report.markers if m.status == "not_configured"]

    return {
        "ok": not contradicted and not not_configured,
        "mode": report.mode,
        "generated_at": report.generated_at.isoformat(),
        "all_verified_live": report.all_verified_live,
        "contradicted": contradicted,
        "not_configured": not_configured,
        "markers": [
            {
                "marker": m.marker,
                "question": m.question,
                "status": m.status,
                "detail": m.detail,
                "evidence": m.evidence,
            }
            for m in report.markers
        ],
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.d4sign_contract_verify",
        description=(
            "Run the D4Sign contract-verification harness (contract §1.6) — "
            "one named, executable assertion per NOC-REMEDIATE[d4sign-*] "
            "marker in noctusai_lib.integrations.signature.real. "
            "mode='sandbox' (default) drives the local D4SignSandbox, no "
            "credentials needed. mode='real' resolves org-scoped D4Sign "
            "credentials and drives an actual account — every marker "
            "reports status='not_configured' when credentials are missing "
            "(never a silent sandbox fallback, mirroring "
            "noctus.dev.sso_smoke's honesty contract). Each marker's "
            "status is one of sandbox_coherent | verified_live | "
            "contradicted_live | unverified_needs_live | not_configured — "
            "a sandbox run can NEVER report verified_live/contradicted_live, "
            "so it is never mistakable for a live-vendor confirmation."
        ),
    )
    def _d4sign_contract_verify(
        mode: str = "sandbox",
        org_id: str | None = None,
        captured_webhook_path: str | None = None,
    ) -> dict:
        return d4sign_contract_verify(
            mode=mode, org_id=org_id, captured_webhook_path=captured_webhook_path
        )


__all__ = ["d4sign_contract_verify", "register"]
