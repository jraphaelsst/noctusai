"""The academia in-process SDK MCP tools (contract §C / §E.4 / §E.5) — one
per academia tool Julia's allowlist exposes.

``build_academia_tools`` is a PER-TURN factory (not module-level ``@tool``
definitions) because every handler closes over a specific
``TurnContext``/``AcademiaApi``/agent identity/signing key — the same
reason ``build_launch_options`` (claude_runtime.py) is called fresh for
every ``run_turn``.

Handlers run in the CONTROL PLANE (this process), never in the Julia CLI
subprocess — that is the whole point of an in-process SDK MCP server
(contract §E.5 "Tools are in-process SDK MCP tools ... executed by the
control plane, not by the CLI").

**The ``_approval`` seam (contract §E.9 revision / §E.10, security review
2026-09-14).** ``can_use_tool`` (``claude_runtime.py``) injects ONLY
``{"approval_id": ...}`` into the handler's own ``args`` via
``PermissionResultAllow(updated_input=...)`` (the SDK forwards
``updated_input`` verbatim as the tool call's actual arguments — verified
live, ``claude_agent_sdk/_internal/query.py:512-514``). Every escrita
handler below treats that id as nothing more than a LOOKUP KEY: it reads
the ``approvals`` store's own row for it and checks every field itself
(decision, tool, conversation, requester, instance, freshness, and a
canonical-hash match of the ORIGINAL approved arguments against what the
CLI is sending now) before atomically consuming it and minting the §D
assertion from the STORED ``decided_by`` — never from anything the CLI
subprocess claims. This closes the hole the security review found: a
compromised CLI subprocess speaking the control protocol directly could
previously mint a valid assertion for a forged approver or a
bait-and-switched body, because the old handler trusted CLI-supplied
``approval_id``/``approved_by`` outright.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID

from claude_agent_sdk import SdkMcpTool, create_sdk_mcp_server, tool

from app.runtime.academia_api import AcademiaApi, AcademiaApiError
from app.runtime.assertion import canonical_body_sha256, mint_assertion
from app.runtime.types import TurnContext
from app.stores.approvals import ApprovalStore
from app.stores.errors import NotFound

logger = logging.getLogger(__name__)

__all__ = ["build_academia_tools"]

#: Contract §E.10 default when no override is threaded through
#: ``build_academia_tools`` (mirrors ``settings.approval_use_window_seconds``).
DEFAULT_APPROVAL_USE_WINDOW_SECONDS = 120


def _ok(payload: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def _error(exc: AcademiaApiError) -> dict[str, Any]:
    return _ok({"ok": False, "error": {"status": exc.status, "code": exc.code, "detail": exc.detail}})


def _refuse(code: str, detail: str, *, approval_id: Any, conversation_id: Any) -> dict[str, Any]:
    """Contract §E.10 "Refusals": the existing ``_ok`` error shape, PT-BR
    detail, no internal values — logged with ``approval_id``,
    ``conversation_id`` and the ``code``. Never mints, never calls
    academia."""
    logger.warning(
        "agents.approval.refused approval_id=%s conversation_id=%s code=%s",
        approval_id,
        conversation_id,
        code,
    )
    return _ok({"ok": False, "error": {"status": 403, "code": code, "detail": detail}})


def _as_datetime(value: Any) -> datetime | None:
    """Normalize a store-returned timestamp to a tz-aware ``datetime``.

    ``FakeApprovalStore`` already returns ``datetime`` objects;
    ``SupabaseApprovalStore`` returns whatever PostgREST's JSON gave it —
    an ISO-8601 string, never parsed into a ``datetime`` for us. Both are
    legitimate runtime shapes of the same ``ApprovalRecord.decided_at``
    field; this handler is the one place that does arithmetic on it, so
    it normalizes here rather than pushing a parsing contract onto every
    store implementation."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _leitura(
    name: str,
    description: str,
    schema: dict[str, Any],
    *,
    academia_api: AcademiaApi,
    path_fn: Callable[[dict[str, Any]], str],
    params_fn: Callable[[dict[str, Any]], dict[str, Any]] = lambda args: {},
) -> SdkMcpTool[Any]:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        try:
            result = await academia_api.get(path_fn(args), params=params_fn(args))
        except AcademiaApiError as exc:
            return _error(exc)
        return _ok(result)

    return tool(name, description, schema)(handler)


def _escrita(
    name: str,
    description: str,
    schema: dict[str, Any],
    *,
    academia_api: AcademiaApi,
    agent_id: UUID,
    secret: str,
    aud: str,
    ctx: TurnContext,
    approvals: ApprovalStore,
    use_window_seconds: int,
    method_fn: Callable[[dict[str, Any]], str],
    path_fn: Callable[[dict[str, Any]], str],
    body_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> SdkMcpTool[Any]:
    # `create_sdk_mcp_server("academia", tools=[...])` prefixes whatever
    # leaf name `tool()` registers here into `mcp__academia__<name>` when
    # exposing it to Claude — `full_name` below is that FULL form, used
    # ONLY for the gate/assertion `tool` claim (must match
    # `app.runtime.gate.ESCRITA` and `ToolUseBlock.name` exactly). Passing
    # the already-prefixed form to `tool()` itself would double-prefix
    # and silently break every gate match.
    full_name = f"mcp__academia__{name}"

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        raw_approval = args.get("_approval")
        rest = {k: v for k, v in args.items() if k != "_approval"}

        # §E.10 step 1 — a missing or unparseable id refuses closed,
        # before any store read. No silent fallback: the gate is the only
        # legitimate caller of an escrita handler (contract §E.4/§E.9); an
        # `_approval` this shape means `can_use_tool` was bypassed somehow.
        raw_id = raw_approval.get("approval_id") if isinstance(raw_approval, dict) else None
        if not raw_id:
            return _refuse(
                "approval_missing",
                "Nenhuma aprovação associada a esta chamada.",
                approval_id=None,
                conversation_id=ctx.conversation_id,
            )
        try:
            approval_id = UUID(str(raw_id))
        except (ValueError, TypeError):
            return _refuse(
                "approval_missing",
                "Nenhuma aprovação associada a esta chamada.",
                approval_id=raw_id,
                conversation_id=ctx.conversation_id,
            )

        # §E.10 step 2 — the stored row is the ONLY source of truth for
        # everything that follows; a forged/unknown id refuses the same
        # as every other integrity failure below (never distinguished to
        # a caller that might be probing).
        try:
            record = approvals.get(ctx.org_id, approval_id)
        except NotFound:
            return _refuse(
                "approval_invalid",
                "Aprovação inválida — peça de novo.",
                approval_id=approval_id,
                conversation_id=ctx.conversation_id,
            )

        # §E.10 step 3 — every one of these must hold.
        decided_at = _as_datetime(record.decided_at)
        fresh = (
            decided_at is not None
            and (datetime.now(timezone.utc) - decided_at).total_seconds() <= use_window_seconds
        )
        same_call = canonical_body_sha256(dict(record.tool_input)) == canonical_body_sha256(rest)
        checks_ok = (
            record.decision == "aprovada"
            and record.tool_name == full_name
            and record.conversation_id == ctx.conversation_id
            and record.requested_by == ctx.requested_by
            and record.instance_id == ctx.instance_id
            and fresh
            and same_call
        )
        if not checks_ok:
            return _refuse(
                "approval_invalid",
                "Aprovação inválida — peça de novo.",
                approval_id=approval_id,
                conversation_id=ctx.conversation_id,
            )

        # §E.10 step 4 — the atomic single-use gate. `consume` returns a
        # row only the FIRST time; a replay (this call again, or a
        # concurrent second one) gets `None`.
        consumed = approvals.consume(ctx.org_id, approval_id)
        if consumed is None:
            return _refuse(
                "approval_used",
                "Esta aprovação já foi usada.",
                approval_id=approval_id,
                conversation_id=ctx.conversation_id,
            )

        # §E.10 step 5 — mint from the STORED, decided row. `approved_by`
        # is never read from the tool call's own arguments (contract
        # §E.9: `can_use_tool` no longer even injects it).
        method = method_fn(rest)
        path = path_fn(rest)
        body = body_fn(rest)
        assertion = mint_assertion(
            approval_id=approval_id,
            secret=secret,
            agent_id=agent_id,
            org_id=ctx.org_id,
            tool_name=full_name,
            method=method,
            path=path,
            body=body,
            approved_by=consumed.decided_by,
            requested_by=ctx.requested_by,
            aud=aud,
        )

        try:
            result = await academia_api.request(method, path, body=body, assertion=assertion)
        except AcademiaApiError as exc:
            return _error(exc)
        return _ok(result)

    return tool(name, description, schema)(handler)


def _obj(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_S = {"type": "string"}
_S_OPT = {"type": ["string", "null"]}
_I = {"type": "integer"}
_B = {"type": "boolean"}
_TAGS = {"type": "array", "items": {"type": "string"}}


def build_academia_tools(
    *,
    ctx: TurnContext,
    academia_api: AcademiaApi,
    agent_id: UUID,
    secret: str,
    aud: str,
    approvals: ApprovalStore,
    use_window_seconds: int = DEFAULT_APPROVAL_USE_WINDOW_SECONDS,
) -> Any:
    """Returns the ``McpSdkServerConfig`` ready for
    ``ClaudeAgentOptions.mcp_servers["academia"]`` — every §E.4 academia
    tool, bound to THIS turn's context/identity/signing key."""

    def _escrita_bound(
        name: str,
        description: str,
        schema: dict[str, Any],
        *,
        method_fn: Callable[[dict[str, Any]], str],
        path_fn: Callable[[dict[str, Any]], str],
        body_fn: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> SdkMcpTool[Any]:
        """Binds every §E.10 collaborator (``approvals``,
        ``use_window_seconds``) once per turn, so each of the 12 escrita
        registrations below only names what actually varies per tool."""
        return _escrita(
            name,
            description,
            schema,
            academia_api=academia_api,
            agent_id=agent_id,
            secret=secret,
            aud=aud,
            ctx=ctx,
            approvals=approvals,
            use_window_seconds=use_window_seconds,
            method_fn=method_fn,
            path_fn=path_fn,
            body_fn=body_fn,
        )

    leitura = [
        _leitura(
            "kb_buscar",
            "Busca entradas do KB da Academia de Reciclagem por texto, categoria, subcategoria ou tag.",
            _obj(
                {
                    "consulta": _S_OPT,
                    "categoria": _S_OPT,
                    "subcategoria": _S_OPT,
                    "tag": _S_OPT,
                    "limite": _I,
                    "offset": _I,
                },
                [],
            ),
            academia_api=academia_api,
            path_fn=lambda a: "/api/kb",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "kb_ler",
            "Lê uma entrada do KB pelo slug.",
            _obj({"slug": _S}, ["slug"]),
            academia_api=academia_api,
            path_fn=lambda a: f"/api/kb/{a['slug']}",
        ),
        _leitura(
            "decisao_listar",
            "Lista decisões do projeto, opcionalmente filtradas por estado.",
            _obj({"estado": _S_OPT}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/decisions",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "pergunta_listar",
            "Lista perguntas em aberto (ou respondidas/todas).",
            _obj({"estado": _S_OPT}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/questions",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "historico_timeline",
            "Lista eventos recentes do histórico do projeto.",
            _obj({"limite": _I}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/timeline",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "roadmap_ler",
            "Lê as fases do roadmap do projeto.",
            _obj({}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/roadmap",
        ),
        _leitura(
            "tarefa_listar",
            "Lista tarefas, opcionalmente filtradas por fase ou estado.",
            _obj({"fase": _S_OPT, "estado": _S_OPT}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/tasks",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "tarefa_preparar_sessao",
            "Retorna o resumo de início de sessão: fase atual, próximas tarefas, bloqueadas e perguntas bloqueantes.",
            _obj({}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/session-prep",
        ),
        _leitura(
            "conteudo_listar",
            "Lista conteúdos de treinamento (roteiro, trilha, quiz, copy...), opcionalmente por tipo.",
            _obj({"tipo": _S_OPT}, []),
            academia_api=academia_api,
            path_fn=lambda a: "/api/content",
            params_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _leitura(
            "conteudo_ler",
            "Lê um conteúdo de treinamento pelo código.",
            _obj({"codigo": _S}, ["codigo"]),
            academia_api=academia_api,
            path_fn=lambda a: f"/api/content/{a['codigo']}",
        ),
    ]

    def _kb_escrever_method(a: dict[str, Any]) -> str:
        return "PUT" if a.get("slug") else "POST"

    def _kb_escrever_path(a: dict[str, Any]) -> str:
        return f"/api/kb/{a['slug']}" if a.get("slug") else "/api/kb"

    def _kb_escrever_body(a: dict[str, Any]) -> dict[str, Any]:
        body = {"titulo": a["titulo"], "corpo_md": a["corpo_md"], "motivo": a["motivo"]}
        if a.get("categoria") is not None:
            body["categoria"] = a["categoria"]
        if a.get("subcategoria") is not None:
            body["subcategoria"] = a["subcategoria"]
        if not a.get("slug"):
            # POST /api/kb requires categoria (§B.1); PUT never rejects it.
            body.setdefault("categoria", a.get("categoria"))
        return body

    escrita = [
        _escrita_bound(
            "kb_escrever",
            "Cria ou atualiza uma entrada do KB. Sem slug: cria (POST). Com slug: atualiza (PUT).",
            _obj(
                {
                    "slug": _S_OPT,
                    "categoria": _S_OPT,
                    "subcategoria": _S_OPT,
                    "titulo": _S,
                    "corpo_md": _S,
                    "motivo": _S,
                },
                ["titulo", "corpo_md", "motivo"],
            ),
            method_fn=_kb_escrever_method,
            path_fn=_kb_escrever_path,
            body_fn=_kb_escrever_body,
        ),
        _escrita_bound(
            "kb_mover",
            "Move (renomeia) uma entrada do KB de um slug para outro.",
            _obj({"origem": _S, "destino": _S, "motivo": _S}, ["origem", "destino", "motivo"]),
            method_fn=lambda a: "PUT",
            path_fn=lambda a: f"/api/kb/{a['origem']}",
            body_fn=lambda a: {"novo_slug": a["destino"], "motivo": a["motivo"]},
        ),
        _escrita_bound(
            "decisao_registrar",
            "Registra uma nova decisão do projeto, com motivo.",
            _obj(
                {
                    "titulo": _S,
                    "contexto": _S_OPT,
                    "decisao": _S,
                    "motivo": _S,
                    "alternativas_rejeitadas": _S_OPT,
                    "relacionadas": _TAGS,
                },
                ["titulo", "decisao", "motivo"],
            ),
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/decisions",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _escrita_bound(
            "decisao_substituir",
            "Substitui uma decisão anterior por uma nova, mantendo o histórico (append-only).",
            _obj(
                {
                    "substitui": _S,
                    "titulo": _S,
                    "contexto": _S_OPT,
                    "decisao": _S,
                    "motivo": _S,
                    "alternativas_rejeitadas": _S_OPT,
                    "relacionadas": _TAGS,
                },
                ["substitui", "titulo", "decisao", "motivo"],
            ),
            method_fn=lambda a: "POST",
            path_fn=lambda a: f"/api/decisions/{a['substitui']}/supersede",
            body_fn=lambda a: {
                k: v for k, v in a.items() if v is not None and k != "substitui"
            },
        ),
        _escrita_bound(
            "pergunta_adicionar",
            "Registra uma pergunta em aberto, o motivo de importar e o que ela bloqueia.",
            _obj(
                {
                    "pergunta": _S,
                    "por_que_importa": _S,
                    "bloqueia": _S,
                    "destino_kb": _S_OPT,
                },
                ["pergunta", "por_que_importa", "bloqueia"],
            ),
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/questions",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _escrita_bound(
            "pergunta_responder",
            "Responde uma pergunta em aberto pelo código.",
            _obj({"codigo": _S, "resposta": _S}, ["codigo", "resposta"]),
            method_fn=lambda a: "POST",
            path_fn=lambda a: f"/api/questions/{a['codigo']}/answer",
            body_fn=lambda a: {"resposta": a["resposta"]},
        ),
        _escrita_bound(
            "historico_append",
            "Registra um evento no histórico do projeto.",
            _obj(
                {"titulo": _S, "descricao": _S, "data": _S_OPT},
                ["titulo", "descricao"],
            ),
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/timeline",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _escrita_bound(
            "roadmap_atualizar",
            "Atualiza uma fase do roadmap (estado, título, objetivo ou critério de conclusão).",
            _obj(
                {
                    "codigo": _S,
                    "estado": _S_OPT,
                    "titulo": _S_OPT,
                    "objetivo": _S_OPT,
                    "concluida_quando": _S_OPT,
                },
                ["codigo"],
            ),
            method_fn=lambda a: "PATCH",
            path_fn=lambda a: f"/api/roadmap/{a['codigo']}",
            body_fn=lambda a: {
                k: v for k, v in a.items() if v is not None and k != "codigo"
            },
        ),
        _escrita_bound(
            "tarefa_criar",
            "Cria uma nova tarefa dentro de uma fase do roadmap.",
            _obj(
                {
                    "titulo": _S,
                    "fase": _S,
                    "detalhe": _S_OPT,
                    "bloqueada_por": _S_OPT,
                },
                ["titulo", "fase"],
            ),
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/tasks",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _escrita_bound(
            "tarefa_atualizar",
            "Atualiza uma tarefa existente pelo código.",
            _obj(
                {
                    "codigo": _S,
                    "estado": _S_OPT,
                    "detalhe": _S_OPT,
                    "bloqueada_por": _S_OPT,
                },
                ["codigo"],
            ),
            method_fn=lambda a: "PATCH",
            path_fn=lambda a: f"/api/tasks/{a['codigo']}",
            body_fn=lambda a: {
                k: v for k, v in a.items() if v is not None and k != "codigo"
            },
        ),
        _escrita_bound(
            "conteudo_salvar",
            "Salva um conteúdo de treinamento (roteiro, trilha, quiz, copy...).",
            _obj(
                {
                    "tipo": _S,
                    "titulo": _S,
                    "corpo_md": _S,
                    "referencia": _S_OPT,
                    "fontes": _TAGS,
                },
                ["tipo", "titulo", "corpo_md"],
            ),
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/content",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
        _escrita_bound(
            "pesquisa_capturar_fonte",
            "Captura uma fonte de pesquisa (URL, trecho citado, resumo) e a vincula a uma entrada do KB.",
            _obj(
                {
                    "url": _S,
                    "titulo": _S,
                    "trecho_citado": _S,
                    "resumo": _S,
                    "kb_slug": _S,
                    "vigencia_confirmada": _B,
                    "exige_da_empresa": _S_OPT,
                },
                ["url", "titulo", "trecho_citado", "resumo", "kb_slug", "vigencia_confirmada"],
            ),
            method_fn=lambda a: "POST",
            path_fn=lambda a: "/api/sources",
            body_fn=lambda a: {k: v for k, v in a.items() if v is not None},
        ),
    ]

    return create_sdk_mcp_server("academia", tools=[*leitura, *escrita])
