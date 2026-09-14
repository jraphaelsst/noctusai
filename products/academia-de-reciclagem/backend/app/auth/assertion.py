"""`X-Approval-Assertion` verification — contract §D.

Verifies the compact HS256 JWS a product-token write MUST carry (unless
the token is `human_personal` — §B.0's exception, handled by
`app.auth.provenance`, not here). Implements the 8 ordered checks
VERBATIM against contract §D:

    1. Signature       — try every configured key; academia accepts ANY.
    2. `aud`
    3. `exp`
    4. `org` == the resolved token's org
    5. `sub` == the resolved token's principal agent
    6. `body_sha256` == the canonical hash of the RECEIVED raw body
    7. `method` + `path` == the received request, and `tool` maps to
       that route per §C
    8. `approved_by` holds the WRITE role set in this org, checked at
       VERIFICATION time (not approval time)

Only step 8 is `approver_not_allowed`; every other failure (including a
missing/absent header) is `assertion_invalid`. The single-use `jti`
replay guard (`approval_consumptions`) is NOT enforced here — contract
§A.10/§D: its INSERT happens inside the store's write transaction, so a
verified-but-not-yet-consumed assertion can still be rejected by the
store as `AssertionUsed` (409) on a genuine replay race. This module
only ever raises the two 403 error classes below.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

import jwt

from noctusai_lib.api.auth.session.scopes import resolve_org_role

from app.auth.roles import WRITE

_AUDIENCE = "academia-de-reciclagem"

# §C: sibling tool name -> (method, path template) academia accepts a
# product-token write for. A route MAY accept more than one tool name —
# `kb.escrever`'s `PUT /api/kb/{slug}` (update-by-slug) and `kb.mover`'s
# `PUT /api/kb/{slug}` (rename via `novo_slug`) are the SAME HTTP route;
# §C's "same tool name" note is about the two tools sharing one MCP
# identity, not a 1:1 route<->tool mapping. A route absent from this map
# (e.g. `POST /api/kb/{slug}/archive` — no §C tool exists for it) can
# NEVER be reached by an agent-signed assertion: only a `human_personal`
# token (no assertion required) or an SSO user can call it.
_ROUTE_TOOLS: dict[tuple[str, str], frozenset[str]] = {
    ("POST", "/api/kb"): frozenset({"academia.kb.escrever"}),
    ("PUT", "/api/kb/{slug}"): frozenset({"academia.kb.escrever", "academia.kb.mover"}),
    ("POST", "/api/decisions"): frozenset({"academia.decisao.registrar"}),
    ("POST", "/api/decisions/{codigo}/supersede"): frozenset({"academia.decisao.substituir"}),
    ("POST", "/api/questions"): frozenset({"academia.pergunta.adicionar"}),
    ("POST", "/api/questions/{codigo}/answer"): frozenset({"academia.pergunta.responder"}),
    ("POST", "/api/timeline"): frozenset({"academia.historico.append"}),
    ("PATCH", "/api/roadmap/{codigo}"): frozenset({"academia.roadmap.atualizar"}),
    ("POST", "/api/tasks"): frozenset({"academia.tarefa.criar"}),
    ("PATCH", "/api/tasks/{codigo}"): frozenset({"academia.tarefa.atualizar"}),
    ("POST", "/api/content"): frozenset({"academia.conteudo.salvar"}),
    ("POST", "/api/sources"): frozenset({"academia.pesquisa.capturar_fonte"}),
}

_REQUIRED_CLAIMS = [
    "jti", "iss", "aud", "sub", "org", "tool", "method", "path",
    "body_sha256", "approved_by", "iat", "exp",
]


def _template_to_regex(template: str) -> re.Pattern[str]:
    parts = re.split(r"(\{[^/}]+\})", template)
    pattern = "".join(
        "[^/]+" if part.startswith("{") and part.endswith("}") else re.escape(part)
        for part in parts
    )
    return re.compile(f"^{pattern}$")


_ROUTE_TOOLS_COMPILED: list[tuple[str, re.Pattern[str], frozenset[str]]] = [
    (method, _template_to_regex(template), tools)
    for (method, template), tools in _ROUTE_TOOLS.items()
]


def _tools_for_route(method: str, path: str) -> frozenset[str]:
    for route_method, pattern, tools in _ROUTE_TOOLS_COMPILED:
        if route_method == method and pattern.match(path):
            return tools
    return frozenset()


def canonical_body_sha256(raw_body: bytes) -> str:
    """§D "Canonical JSON": UTF-8, sorted keys, no insignificant
    whitespace, re-derived from the RAW request body — never from the
    already-validated Pydantic model, whose own re-serialization could
    silently normalize away a signed-body mismatch (e.g. a field the
    model drops)."""
    parsed = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AssertionInvalidError(Exception):
    """403 `assertion_invalid` — any of §D steps 1–7 failed, or the
    header was absent for a caller that needs one."""


class ApproverNotAllowedError(Exception):
    """403 `approver_not_allowed` — §D step 8: `approved_by` does not
    hold the WRITE role set in this org."""


@dataclass(frozen=True)
class VerifiedAssertion:
    """The assertion claims the caller needs to build a `Provenance`
    (contract §B.0: `user_id = approved_by`, `agent_id = sub`,
    `approval_id = jti`)."""

    jti: UUID
    org_id: UUID
    agent_id: UUID
    approved_by: UUID
    requested_by: UUID | None
    tool: str


def verify_assertion(
    header_value: str | None,
    *,
    keys: list[str],
    ctx_org_id: UUID,
    ctx_principal_agent_id: UUID | None,
    method: str,
    path: str,
    raw_body: bytes,
    get_core_client: Callable[[], Any],
) -> VerifiedAssertion:
    """Run the §D 8-step verification. Returns the claims a `Provenance`
    is built from, or raises `AssertionInvalidError` /
    `ApproverNotAllowedError`."""
    if not header_value:
        raise AssertionInvalidError("missing X-Approval-Assertion header")

    # ── Step 1: signature — try every configured key; ANY may match.
    claims: dict[str, Any] | None = None
    for key in keys:
        try:
            claims = jwt.decode(
                header_value,
                key,
                algorithms=["HS256"],
                options={
                    "verify_aud": False,
                    "verify_exp": False,
                    "require": _REQUIRED_CLAIMS,
                },
            )
            break
        except jwt.InvalidSignatureError:
            continue
        except jwt.DecodeError:
            # Malformed token overall (bad base64/JSON) — no key will
            # ever match; still try the rest in case of an edge case,
            # but this is effectively terminal.
            continue
        except jwt.InvalidTokenError as exc:
            # Signature matched THIS key but a required claim is
            # missing / the shape is otherwise invalid — the right key
            # was found, so don't keep guessing at the rest.
            raise AssertionInvalidError(f"malformed assertion: {exc}") from exc
    if claims is None:
        raise AssertionInvalidError("signature did not match any configured key")

    # ── Step 2: aud
    if claims.get("aud") != _AUDIENCE:
        raise AssertionInvalidError(f"aud mismatch: {claims.get('aud')!r}")

    # ── Step 3: exp
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or exp < time.time():
        raise AssertionInvalidError("assertion expired")

    # ── Step 4: org == the resolved token's org
    if str(claims.get("org")) != str(ctx_org_id):
        raise AssertionInvalidError("org mismatch")

    # ── Step 5: sub == the resolved token's principal agent
    if ctx_principal_agent_id is None or str(claims.get("sub")) != str(ctx_principal_agent_id):
        raise AssertionInvalidError("sub does not match the token's principal agent")

    # ── Step 6: body hash
    if claims.get("body_sha256") != canonical_body_sha256(raw_body):
        raise AssertionInvalidError("body_sha256 mismatch")

    # ── Step 7: method/path exact match + tool -> route mapping
    if claims.get("method") != method or claims.get("path") != path:
        raise AssertionInvalidError("method/path mismatch")
    allowed_tools = _tools_for_route(method, path)
    if claims.get("tool") not in allowed_tools:
        raise AssertionInvalidError(f"tool {claims.get('tool')!r} does not map to {method} {path}")

    # ── Step 8: approver role (checked NOW, not at approval time)
    try:
        approved_by = UUID(str(claims["approved_by"]))
    except (ValueError, TypeError) as exc:
        raise AssertionInvalidError("approved_by is not a UUID") from exc
    role = resolve_org_role(get_core_client(), approved_by)
    if role not in WRITE:
        raise ApproverNotAllowedError()

    try:
        jti = UUID(str(claims["jti"]))
        agent_id = UUID(str(claims["sub"]))
    except (ValueError, TypeError) as exc:
        raise AssertionInvalidError("jti/sub is not a UUID") from exc

    requested_by_raw = claims.get("requested_by")
    requested_by: UUID | None = None
    if requested_by_raw:
        try:
            requested_by = UUID(str(requested_by_raw))
        except (ValueError, TypeError):
            requested_by = None

    return VerifiedAssertion(
        jti=jti,
        org_id=ctx_org_id,
        agent_id=agent_id,
        approved_by=approved_by,
        requested_by=requested_by,
        tool=str(claims["tool"]),
    )


__all__ = [
    "ApproverNotAllowedError",
    "AssertionInvalidError",
    "VerifiedAssertion",
    "canonical_body_sha256",
    "verify_assertion",
]
